"""ReflectionRunner: Gap JSONL → LLM → BehaviorPolicy Proposals.

Batch processor for M2 autonomous-growth pipeline.

SRS refs: FR-REFL-01, FR-REFL-02.
Design: LLM-Modulo (Kambhampati et al. 2024) — LLM generates YAML proposals;
        external ProposalValidator verifies before any policy write.
"""

from __future__ import annotations

import json
import logging
import textwrap
from typing import Protocol

import yaml

logger = logging.getLogger(__name__)


# ── LLM Backend Protocol ───────────────────────────────────────────────────


class LLMBackend(Protocol):
    """Minimal async LLM interface (compatible with orchestrator.llm_client.LLMBackend)."""

    async def chat(self, system: str, user: str) -> tuple[str, float]:
        """Return (response_text, cost_yen)."""
        ...  # pragma: no cover


# ── System prompt ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = textwrap.dedent("""\
    あなたは AITuber の行動ポリシー設計者です。
    avatar が実行できなかった Intent（Capability Gap）のリストが与えられます。
    各 Gap に対して、behavior_policy.yml に追加すべきエントリを YAML リスト形式で提案してください。

    ## 出力形式（厳守）

    必ず以下の YAML リスト形式で出力してください。それ以外のテキストは含めないでください。

    ```yaml
    - intent: <snake_case の識別子>
      cmd: avatar_update  # または avatar_event
      gesture: <gesture名>  # avatar_update の場合
      emotion: <emotion名>  # 省略可
      look_target: <target>  # 省略可
      # avatar_event の場合:
      # event: <event名>
      # intensity: 1.0
      priority: 0
      notes: <このエントリの説明（1行）>
    ```

    ## ルール

    1. intent は英小文字・数字・アンダースコアのみ使用（例: point_at_screen）
    2. cmd は "avatar_update" または "avatar_event" のみ使用
    3. gesture / emotion / look_target / event のうち少なくとも1つを指定
    4. 1 Gap に対して 1 エントリを提案する（既存の gap_category を参考にする）
    5. 危険・有害・不適切なコンテンツを含めない
    6. 出力は YAML コードブロックのみ（説明文・コメントアウト外のテキスト禁止）
""")

# Few-shot example appended to user prompt
_FEW_SHOT_EXAMPLE = textwrap.dedent("""\
    ## 例

    Gap:
    {
      "intended_action": {"type": "intent", "name": "point_at_screen", "param": ""},
      "gap_category": "missing_motion",
      "fallback_used": "nod",
      "context": {"emotion": "happy"}
    }

    期待する YAML 出力:
    - intent: point_at_screen
      cmd: avatar_update
      gesture: point
      priority: 0
      notes: 画面を指差すジェスチャー

    ---
""")


# ── ReflectionRunner ───────────────────────────────────────────────────────


class ReflectionRunner:
    """Read Gap JSONL, call LLM, return BehaviorPolicy proposals.

    FR-REFL-01: load_gaps – parse JSONL into list[dict]
    FR-REFL-02: generate_proposals – LLM-Modulo batch call
    """

    def __init__(self, backend: LLMBackend | None = None) -> None:
        self._backend = backend  # None → real backend injected at call-time

    # ── Gap loading ────────────────────────────────────────────────────────

    def load_gaps(self, jsonl_path: str) -> list[dict]:
        """Parse a JSONL file of GapEntry objects into a list of dicts.

        FR-REFL-01
        Raises:
            FileNotFoundError: if the file does not exist.
        Skips lines that are not valid JSON (logs a warning per line).
        """
        from pathlib import Path

        path = Path(jsonl_path)
        if not path.exists():
            raise FileNotFoundError(f"Gap JSONL not found: {jsonl_path}")

        entries: list[dict] = []
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
                entries.append(entry)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping invalid JSON on line %d: %s", lineno, exc)

        return entries

    # ── Gap filtering / sorting ────────────────────────────────────────────

    def filter_gaps(
        self,
        gaps: list[dict],
        *,
        category: str | None = None,
        max_count: int = 20,
    ) -> list[dict]:
        """Filter gaps by gap_category and limit to max_count.

        FR-REFL-01
        Args:
            gaps:       Full list of GapEntry dicts.
            category:   If set, keep only entries matching gap_category.
            max_count:  Maximum number of entries to return (first N after filter).
        """
        if category is not None:
            result = [g for g in gaps if g.get("gap_category") == category]
        else:
            result = gaps
        return result[:max_count]

    def sort_by_priority(self, gaps: list[dict]) -> list[dict]:
        """Return a new list sorted by priority_score descending.

        FR-REFL-01  Does not mutate the input list.
        """
        return sorted(gaps, key=lambda g: g.get("priority_score", 0.0), reverse=True)

    # ── Prompt building ────────────────────────────────────────────────────

    def build_prompt(self, gaps: list[dict]) -> str:
        """Serialise gaps list into a LLM user-turn prompt.

        FR-REFL-02  Includes few-shot example and gap JSON dump.
        """
        lines: list[str] = [_FEW_SHOT_EXAMPLE, "## 解析対象の Gap リスト\n"]
        for i, gap in enumerate(gaps, start=1):
            # Summarise the gap for the prompt (keep it concise)
            summary = {
                "intended_action": gap.get("intended_action", {}),
                "gap_category": gap.get("gap_category", ""),
                "fallback_used": gap.get("fallback_used", ""),
                "context": gap.get("context", {}),
            }
            lines.append(f"### Gap {i}")
            lines.append(json.dumps(summary, ensure_ascii=False, indent=2))
            lines.append("")

        lines.append(
            "上記の各 Gap に対して YAML エントリを提案してください。"
            "yaml コードブロックのみを出力してください。"
        )
        return "\n".join(lines)

    # ── Proposal generation ────────────────────────────────────────────────

    async def generate_proposals(self, gaps: list[dict]) -> list[dict]:
        """Call LLM with a batch prompt and parse the YAML response.

        FR-REFL-02  LLM-Modulo: externally validated before any write.
        Returns an empty list on any LLM or parse failure (never raises).
        """
        if not gaps or self._backend is None:
            return []

        prompt = self.build_prompt(gaps)
        try:
            yaml_text, _cost = await self._backend.chat(_SYSTEM_PROMPT, prompt)
        except Exception as exc:
            logger.error("LLM call failed in generate_proposals: %s", exc)
            return []

        return self._parse_yaml_proposals(yaml_text)

    # ── YAML parsing ───────────────────────────────────────────────────────

    def _parse_yaml_proposals(self, yaml_text: str) -> list[dict]:
        """Parse LLM YAML output into a list of proposal dicts.

        Strips ```yaml ... ``` fences if present.
        Returns empty list on parse failure.
        """
        # Strip optional markdown code fences
        text = yaml_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            # Remove first and last fence lines
            text = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            )

        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            logger.warning("Failed to parse LLM YAML output: %s", exc)
            return []

        if not parsed:
            return []

        if not isinstance(parsed, list):
            logger.warning("Expected YAML list from LLM, got %s", type(parsed).__name__)
            return []

        # Filter to dicts only; skip malformed entries
        proposals = []
        for item in parsed:
            if isinstance(item, dict):
                proposals.append(item)
            else:
                logger.warning("Skipping non-dict YAML entry: %r", item)

        return proposals
