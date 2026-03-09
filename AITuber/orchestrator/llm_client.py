"""LLM client with retry + template fallback.

SRS refs: FR-LLM-01, TC-LLM-01, NFR-COST-01.
Retry max 2 → template mode without stopping speech.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Protocol

from orchestrator.character import CharacterConfig, load_character
from orchestrator.config import LLMConfig

logger = logging.getLogger(__name__)


# Sentence boundary characters used by generate_reply_stream() to split LLM output.
_SENTENCE_ENDS = frozenset("。！？\n")

# ── Template-mode responses ───────────────────────────────────────────

# テンプレート応答は CharacterConfig から動的にロードされる。
# フォールバック用のデフォルト値。
_DEFAULT_TEMPLATES: list[str] = [
    "ちょっと考え中…少し待ってね！",
    "おっと、うまく言葉が出てこないや。次のコメント読むね！",
    "えーっと、ちょっとフリーズしちゃった！次いこう！",
    "あはは、頭が真っ白になっちゃった！",
]

# モジュールレベルのテンプレートリスト（キャラクター読み込み後に上書きされる）
TEMPLATE_RESPONSES: list[str] = list(_DEFAULT_TEMPLATES)

_template_idx = 0


def _next_template() -> str:
    global _template_idx
    resp = TEMPLATE_RESPONSES[_template_idx % len(TEMPLATE_RESPONSES)]
    _template_idx += 1
    return resp


# ── Cost tracking (NFR-COST-01) ──────────────────────────────────────


class CostTracker:
    """Track LLM spend per hour. Yen-based guard-rail."""

    def __init__(self, target: float = 150.0, hard_limit: float = 300.0) -> None:
        self._target = target
        self._hard_limit = hard_limit
        self._records: list[tuple[float, float]] = []  # (timestamp, yen)

    def record(self, yen: float) -> None:
        self._records.append((time.time(), yen))
        self._prune()

    def hourly_spend(self) -> float:
        self._prune()
        return sum(y for _, y in self._records)

    def is_over_target(self) -> bool:
        return self.hourly_spend() >= self._target

    def is_over_hard_limit(self) -> bool:
        return self.hourly_spend() >= self._hard_limit

    @property
    def template_ratio(self) -> float:
        """NFR-COST-01: ソフトターゲット超過時のテンプレート率。

        spend < target → 0.0 (全件 LLM)
        target <= spend < hard → (spend - target) / (hard - target)
        spend >= hard → 1.0 (全件テンプレート)
        """
        spend = self.hourly_spend()
        if spend < self._target:
            return 0.0
        if self._hard_limit <= self._target:
            return 1.0
        ratio = (spend - self._target) / (self._hard_limit - self._target)
        return min(1.0, ratio)

    def _prune(self) -> None:
        cutoff = time.time() - 3600
        self._records = [(t, y) for t, y in self._records if t > cutoff]


# ── LLM Client Protocol ──────────────────────────────────────────────


class LLMBackend(Protocol):
    async def chat(self, system: str, user: str) -> tuple[str, float]:
        """Return (response_text, cost_yen)."""
        ...


# ── OpenAI-based backend ─────────────────────────────────────────────


class OpenAIBackend:
    """Thin wrapper around OpenAI ChatCompletion."""

    def __init__(self, config: LLMConfig) -> None:
        self._cfg = config
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import openai

            kwargs: dict = {
                "api_key": self._cfg.api_key,
                "timeout": self._cfg.timeout_sec,
            }
            # FR-LLM-BACKEND-01: OpenAI 互換エンドポイントへの切替
            if self._cfg.base_url is not None:
                kwargs["base_url"] = self._cfg.base_url
            self._client = openai.AsyncOpenAI(**kwargs)

    async def chat(self, system: str, user: str) -> tuple[str, float]:
        self._ensure_client()
        resp = await self._client.chat.completions.create(
            model=self._cfg.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=256,
        )
        text = resp.choices[0].message.content or ""
        # 概算コスト (USD→JPY)。プロバイダ・モデルによって実単価は異なる。
        # gpt-4o-mini 相当の単価を基準値として使用。
        prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
        completion_tokens = resp.usage.completion_tokens if resp.usage else 0
        cost_usd = (prompt_tokens * 0.15 + completion_tokens * 0.60) / 1_000_000
        cost_yen = cost_usd * 150  # approximate USD→JPY
        return text, cost_yen

    async def chat_stream(self, system: str, user: str) -> AsyncGenerator[str, None]:
        """FR-LLM-STREAM-01: Stream token chunks from OpenAI-compatible API.

        Yields raw token strings as they arrive. The caller is responsible
        for sentence-boundary splitting.
        """
        self._ensure_client()
        stream = await self._client.chat.completions.create(
            model=self._cfg.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=256,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# ── Result ────────────────────────────────────────────────────────────


@dataclass
class LLMResult:
    text: str
    is_template: bool = False
    cost_yen: float = 0.0
    retries_used: int = 0


# ── LLM Client with fallback ─────────────────────────────────────────


class LLMClient:
    """LLM caller with retry (max 2) and template fallback.

    FR-LLM-01: If LLM API fails, continue with template mode.
    キャラクター設定は config/character.yml から読み込む。
    """

    MAX_HISTORY_TURNS: int = 10

    def __init__(
        self,
        config: LLMConfig | None = None,
        backend: LLMBackend | None = None,
        character: CharacterConfig | None = None,
    ) -> None:
        self._cfg = config or LLMConfig()
        self._backend = backend or OpenAIBackend(self._cfg)
        self._character = character or load_character()
        self._system_prompt = self._character.system_prompt
        self._cost_tracker = CostTracker(
            target=self._cfg.cost_target_yen_per_hour,
            hard_limit=self._cfg.cost_hard_limit_yen_per_hour,
        )
        self._history: list[tuple[str, str]] = []  # (user, assistant)
        # FR-E1-01: dynamic world context fragment injected into system prompt
        self._world_context_fragment: str = ""

        # テンプレート応答をキャラクター設定から更新
        global TEMPLATE_RESPONSES
        if self._character.template_responses:
            TEMPLATE_RESPONSES[:] = self._character.template_responses

    @property
    def cost_tracker(self) -> CostTracker:
        return self._cost_tracker

    def _build_user_message(self, user_text: str) -> str:
        """直近の会話履歴をコンテキストとしてユーザーメッセージに含める。"""
        if not self._history:
            return user_text
        lines: list[str] = ["[会話履歴]"]
        for u, a in self._history:
            lines.append(f"視聴者: {u}")
            lines.append(f"あなた: {a}")
        lines.append(f"\n[最新コメント]\n視聴者: {user_text}")
        return "\n".join(lines)

    def clear_history(self) -> None:
        """会話履歴をクリア。"""
        self._history.clear()

    def set_world_context_fragment(self, fragment: str) -> None:
        """Update the world-context text injected into every system prompt.

        FR-E1-01: Called by Orchestrator whenever WorldContext is updated.
        Pass empty string to disable injection.
        """
        self._world_context_fragment = fragment

    async def warmup(self) -> None:
        """GPU へのモデルロードを事前に完了させる (初回レイテンシ回避).

        ローカル LLM (Ollama 等) は初回推論時にモデルを VRAM へロードするため
        数秒かかる。起動時にダミーリクエストを投げておくことで、配信中の
        初回コメント応答を高速化する。
        """
        try:
            await self._backend.chat(self._system_prompt, "起動テスト")
            logger.info("[LLM] warmup complete.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LLM] warmup failed (non-fatal): %s", exc)

    async def generate_reply(
        self, user_text: str, *, avoidance_hint: str | None = None
    ) -> LLMResult:
        """Generate a reply. Falls back to template on failure.

        FR-LLM-01: Retry max 2, then template mode.
        NFR-COST-01: Skip LLM if over hard limit.
        If *avoidance_hint* is given (GRAYゾーン), append it to system prompt.
        """
        # Cost guard-rail (hard limit)
        if self._cost_tracker.is_over_hard_limit():
            logger.warning("LLM cost hard limit exceeded; using template mode.")
            return LLMResult(text=_next_template(), is_template=True)

        # NFR-COST-01: ソフトターゲット超過 → 確率的にテンプレートモード
        ratio = self._cost_tracker.template_ratio
        if ratio > 0 and random.random() < ratio:
            logger.info("NFR-COST-01 soft limit: template_ratio=%.2f; using template.", ratio)
            return LLMResult(text=_next_template(), is_template=True)

        system = self._system_prompt
        if self._world_context_fragment:
            # FR-E1-01: prepend world context so the avatar knows where it is
            system = f"{system}\n\n{self._world_context_fragment}"
        if avoidance_hint:
            system = f"{system}\n\n【注意】{avoidance_hint}"

        user_msg = self._build_user_message(user_text)

        retries = 0
        while retries <= self._cfg.max_retries:
            try:
                text, cost_yen = await self._backend.chat(system, user_msg)
                self._cost_tracker.record(cost_yen)
                self._history.append((user_text, text))
                if len(self._history) > self.MAX_HISTORY_TURNS:
                    self._history = self._history[-self.MAX_HISTORY_TURNS :]
                return LLMResult(text=text, cost_yen=cost_yen, retries_used=retries)
            except Exception as exc:
                retries += 1
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s", retries, self._cfg.max_retries + 1, exc
                )

        # All retries exhausted → template mode
        logger.error("LLM API exhausted retries; switching to template mode.")
        return LLMResult(text=_next_template(), is_template=True, retries_used=retries)

    async def generate_reply_stream(
        self,
        user_text: str,
        *,
        avoidance_hint: str | None = None,
    ) -> AsyncGenerator[LLMResult, None]:
        """FR-LLM-STREAM-01: Stream reply as sentence-level LLMResult chunks.

        Yields one LLMResult per sentence boundary (。！？) so callers can
        pipeline TTS and audio playback while the LLM is still generating.
        Falls back to a single ``generate_reply()`` yield when the backend
        does not expose ``chat_stream()``.

        Cost is recorded in _cost_tracker after the full stream completes.
        History is appended with the concatenated full text.
        """
        # Cost guard-rails (same as generate_reply)
        if self._cost_tracker.is_over_hard_limit():
            logger.warning("LLM cost hard limit exceeded; using template mode.")
            yield LLMResult(text=_next_template(), is_template=True)
            return

        ratio = self._cost_tracker.template_ratio
        if ratio > 0 and random.random() < ratio:
            logger.info("NFR-COST-01 soft limit: template_ratio=%.2f; using template.", ratio)
            yield LLMResult(text=_next_template(), is_template=True)
            return

        # Fallback: backend without streaming support
        if not hasattr(self._backend, "chat_stream"):
            result = await self.generate_reply(user_text, avoidance_hint=avoidance_hint)
            yield result
            return

        system = self._system_prompt
        if self._world_context_fragment:
            system = f"{system}\n\n{self._world_context_fragment}"
        if avoidance_hint:
            system = f"{system}\n\n【注意】{avoidance_hint}"

        user_msg = self._build_user_message(user_text)
        buf = ""
        all_tokens: list[str] = []

        try:
            async for token in self._backend.chat_stream(system, user_msg):
                buf += token
                all_tokens.append(token)
                # Flush complete sentences from the front of the buffer
                while True:
                    idx = next(
                        (i for i, ch in enumerate(buf) if ch in _SENTENCE_ENDS), -1
                    )
                    if idx < 0:
                        break
                    sentence = buf[: idx + 1].strip()
                    buf = buf[idx + 1 :]
                    if sentence:
                        yield LLMResult(text=sentence)
        except Exception as exc:
            logger.warning(
                "LLM stream error: %s; yielding template. "
                "Check LLM_BASE_URL / OPENAI_API_KEY in .env.",
                exc,
            )
            yield LLMResult(text=_next_template(), is_template=True)
            return

        # Yield any trailing text without sentence-end punctuation
        remainder = buf.strip()
        if remainder:
            yield LLMResult(text=remainder)

        # Record accumulated cost + history
        full_text = "".join(all_tokens).strip()
        if full_text:
            prompt_tokens = (len(system) + len(user_msg)) // 2
            completion_tokens = len(full_text) // 2
            cost_usd = (prompt_tokens * 0.15 + completion_tokens * 0.60) / 1_000_000
            cost_yen = cost_usd * 150
            self._cost_tracker.record(cost_yen)
            self._history.append((user_text, full_text))
            if len(self._history) > self.MAX_HISTORY_TURNS:
                self._history = self._history[-self.MAX_HISTORY_TURNS :]

    async def generate_idle_talk(self, hints: list[str] | None = None) -> LLMResult:
        """LLMでアイドルトークを動的に生成する。

        hints からランダムに方向性を選び、
        LLM に自由にトークを生成させる。
        """
        hint_text = ""
        if hints:
            chosen = random.choice(hints)
            hint_text = f"\nヒント: {chosen}"

        idle_prompt = (
            "配信中、コメントがしばらく来ていません。"
            "リスナーに話しかけるように自由にトークしてください。"
            "時事・趣味・雑学・質問など何でもOKです。"
            "リスナーに質問を投げかけたり、1〜3文程度で短く話してください。"
            "前のアイドルトークと被らないようバリエーションをつけてください。"
            f"{hint_text}"
        )

        return await self.generate_reply(idle_prompt)
