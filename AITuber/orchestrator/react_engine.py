"""ReAct (Reasoning + Acting) engine for YUI.A.

Implements a tool-augmented LLM loop:
    Think → Act (tool call) → Observe → Think → ... → Final answer

SRS refs: FR-LLM-REACT-01.
Closes #64.

Supported tools:
- web_search  : DuckDuckGo Instant Answer API (no API key required)
- read_config : Read a file under AITuber/config/ (read-only, safe paths only)

Loop safety:
- max_turns (default 3): hard cap on think→act cycles
- On any tool error: observation = error message, loop continues
- If max_turns exceeded: run one final generate_reply() without tools
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.config import LLMConfig
from orchestrator.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Path to config directory — read_config tool is sandboxed here
_CONFIG_DIR = Path(__file__).parent.parent / "config"

# Allowlist of files that read_config may serve.
# Memory files (goal_memory, semantic_memory, etc.) are excluded to prevent
# internal-state disclosure during live streams.  FR-LLM-REACT-01 / L4.
_READ_CONFIG_ALLOWLIST: frozenset[str] = frozenset(
    {
        "character.yml",
        "behavior_policy.yml",
    }
)

# Compiled keyword pattern used to gate tool-augmented queries.  L2.
_TOOL_KEYWORDS = re.compile(
    r"検索|調べて|教えて|ニュース|天気|今日|最新|"
    r"weather|search|news|today|latest|what is|what's",
    re.IGNORECASE,
)


def _needs_tools(user_text: str) -> bool:
    """Return True when the query likely needs a tool call.

    Heuristic to avoid unnecessary tools API round-trips for conversational
    messages.  The LLM still decides via tool_choice="auto".
    FR-LLM-REACT-01.
    """
    return bool(_TOOL_KEYWORDS.search(user_text))


# ── Tool definitions (OpenAI function-call schema) ───────────────────

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web using DuckDuckGo and return a brief summary. "
                "Use this when the viewer asks about current events, weather, "
                "news, or any information not in your training data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query in Japanese or English.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_config",
            "description": (
                "Read a configuration or memory file from the AITuber config directory. "
                "Use this to recall goal_memory, behavior policies, or character settings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": (
                            "Filename inside the config/ directory, e.g. "
                            "'goal_memory.jsonl' or 'behavior_policy.yml'."
                        ),
                    }
                },
                "required": ["filename"],
            },
        },
    },
]

# ── System prompt addon for ReAct mode ───────────────────────────────

_REACT_SYSTEM_ADDON = """
あなたはツールを使って質問に答えられます。
ツールが必要な場合は function call を使ってください。
ツールが不要な場合は直接回答してください。
応答は視聴者向けに短く・自然な日本語でまとめてください。
"""

# ── Data classes ──────────────────────────────────────────────────────


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class ReActStep:
    turn: int
    thought: str | None  # LLM テキスト（ツール呼び出しでない場合）
    tool_call: ToolCall | None
    observation: str | None  # ツール実行結果


@dataclass
class ReActResult:
    """Final result from a ReAct loop."""

    answer: str
    steps: list[ReActStep] = field(default_factory=list)
    is_template: bool = False
    tools_used: list[str] = field(default_factory=list)


# ── Tool implementations ──────────────────────────────────────────────


def _web_search(query: str, timeout: float = 8.0) -> str:
    """DuckDuckGo Instant Answer API — no key required.

    Returns a plain-text summary (≤400 chars).
    """
    params = urllib.parse.urlencode({"q": query, "format": "json", "no_html": "1"})
    url = f"https://api.duckduckgo.com/?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AITuber/1.0 (+https://github.com/iijmiolumia939/aituber)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return f"[検索エラー: {exc}]"

    # AbstractText が最も信頼できる要約
    abstract = data.get("AbstractText", "").strip()
    if abstract:
        return abstract[:400]

    # RelatedTopics のトップを使う
    topics = data.get("RelatedTopics", [])
    snippets: list[str] = []
    for t in topics[:3]:
        if isinstance(t, dict) and t.get("Text"):
            snippets.append(t["Text"][:120])
    if snippets:
        return "\n".join(snippets)[:400]

    return f"「{query}」の検索結果は見つかりませんでした。"


def _read_config(filename: str) -> str:
    """Read a file from the config directory. Path traversal is blocked."""
    # Sanitise: allow only basename (no slashes / dotdot)
    safe_name = Path(filename).name
    if not safe_name or safe_name != filename:
        return "[エラー: ファイル名にパス区切り文字は使えません]"

    # FR-LLM-REACT-01 L4: allowlist — block memory/secret files
    if safe_name not in _READ_CONFIG_ALLOWLIST:
        return f"[エラー: {safe_name} はアクセス許可されていません]"

    target = _CONFIG_DIR / safe_name
    if not target.exists():
        return f"[エラー: {safe_name} は存在しません]"

    content = target.read_text(encoding="utf-8")
    # Truncate large files
    if len(content) > 2000:
        content = content[:2000] + "\n... (省略)"
    return content


def _dispatch_tool(call: ToolCall) -> str:
    """Execute a tool call and return the observation string."""
    if call.name == "web_search":
        query = call.arguments.get("query", "")
        if not query:
            return "[エラー: query が空です]"
        return _web_search(query)

    if call.name == "read_config":
        filename = call.arguments.get("filename", "")
        if not filename:
            return "[エラー: filename が空です]"
        return _read_config(filename)

    return f"[エラー: 未知のツール '{call.name}']"


# ── OpenAI tool-call backend ─────────────────────────────────────────


class ReActBackend:
    """Manages the multi-turn OpenAI tools API conversation.

    Separated from LLMClient to avoid coupling streaming / cost logic.
    """

    def __init__(self, cfg: LLMConfig) -> None:
        self._cfg = cfg
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import openai

            kwargs: dict[str, Any] = {
                "api_key": self._cfg.api_key or "ollama",
                "timeout": self._cfg.timeout_sec,
            }
            if self._cfg.base_url:
                kwargs["base_url"] = self._cfg.base_url
            self._client = openai.AsyncOpenAI(**kwargs)
        return self._client

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Single OpenAI chat/completions call that may include tool calls.

        Returns the raw choice dict so the caller can inspect finish_reason.
        """
        client = self._ensure_client()
        resp = await client.chat.completions.create(
            model=self._cfg.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=512,
            temperature=0.3,
        )
        choice = resp.choices[0]
        return {
            "finish_reason": choice.finish_reason,
            "content": choice.message.content or "",
            "tool_calls": choice.message.tool_calls or [],
            # For appending back to messages
            "message": choice.message,
        }


# ── ReAct Engine ─────────────────────────────────────────────────────


class ReActEngine:
    """Tool-augmented ReAct loop for YUI.A.

    Usage::

        engine = ReActEngine(llm_client, cfg)
        result = await engine.run("今日の東京の天気を教えて")
        print(result.answer)  # "今日の東京は晴れで気温は20℃です！"

    FR-LLM-REACT-01.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        cfg: LLMConfig | None = None,
        max_turns: int = 3,
    ) -> None:
        self._llm = llm_client
        self._backend = ReActBackend(cfg or LLMConfig())
        self._max_turns = max_turns

    # ── Public API ────────────────────────────────────────────────────

    async def run(self, user_text: str) -> ReActResult:
        """Run the ReAct loop for user_text.

        Short-circuits to generate_reply() for non-tool queries to avoid
        unnecessary round-trips.  Falls back on any error.  FR-LLM-REACT-01.
        """
        # Non-tool query: skip ReAct overhead entirely
        if not _needs_tools(user_text):
            try:
                result = await self._llm.generate_reply(user_text)
                return ReActResult(answer=result.text, is_template=result.is_template)
            except Exception as exc:
                logger.warning("ReActEngine direct reply failed: %s", exc)
                return ReActResult(answer="エラーが発生しました。", is_template=True)

        # Tool-required query: run full ReAct loop
        try:
            return await self._react_loop(user_text)
        except Exception as exc:
            logger.warning("ReActEngine error, falling back to generate_reply: %s", exc)

        # Second fallback: isolated try/except (D2)
        try:
            result = await self._llm.generate_reply(user_text)
            return ReActResult(answer=result.text, is_template=result.is_template)
        except Exception as exc2:
            logger.error("ReActEngine fallback generate_reply also failed: %s", exc2)
            return ReActResult(answer="エラーが発生しました。", is_template=True)

    # ── Internal ──────────────────────────────────────────────────────

    async def _react_loop(self, user_text: str) -> ReActResult:
        """Core ReAct loop implementation."""
        steps: list[ReActStep] = []
        tools_used: list[str] = []

        # Build initial message list  (FR-LLM-REACT-01 L3: use public getter)
        sys_prompt, world_ctx = self._llm.react_context()
        system = sys_prompt + _REACT_SYSTEM_ADDON
        if world_ctx:
            system = f"{system}\n\n{world_ctx}"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ]

        for turn in range(self._max_turns):
            choice = await self._backend.chat_with_tools(messages, _TOOLS)

            finish_reason = choice["finish_reason"]
            content = choice["content"]
            raw_tool_calls = choice["tool_calls"]

            if finish_reason == "stop" or not raw_tool_calls:
                # LLM produced a direct answer — done
                steps.append(
                    ReActStep(turn=turn, thought=content, tool_call=None, observation=None)
                )
                return ReActResult(answer=content, steps=steps, tools_used=tools_used)

            # Process tool calls (OpenAI can return multiple, but we handle one at a time)
            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in raw_tool_calls
                    ],
                }
            )

            for tc in raw_tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                tool_call = ToolCall(name=tc.function.name, arguments=args)
                logger.info("ReAct turn %d: calling %s(%s)", turn + 1, tool_call.name, args)

                observation = _dispatch_tool(tool_call)
                tools_used.append(tool_call.name)

                steps.append(
                    ReActStep(
                        turn=turn,
                        thought=content or None,
                        tool_call=tool_call,
                        observation=observation,
                    )
                )

                # Append tool result to messages
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": observation,
                    }
                )

        # max_turns exceeded — one final call without tools
        logger.warning(
            "ReAct max_turns=%d exceeded; doing final reply without tools",
            self._max_turns,
        )
        fallback = await self._llm.generate_reply(user_text)
        return ReActResult(
            answer=fallback.text,
            steps=steps,
            is_template=fallback.is_template,
            tools_used=tools_used,
        )
