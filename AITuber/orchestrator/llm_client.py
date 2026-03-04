"""LLM client with retry + template fallback.

SRS refs: FR-LLM-01, TC-LLM-01, NFR-COST-01.
Retry max 2 → template mode without stopping speech.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Protocol

from orchestrator.character import CharacterConfig, load_character
from orchestrator.config import LLMConfig

logger = logging.getLogger(__name__)


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

    async def generate_idle_talk(
        self, hints: list[str] | None = None
    ) -> LLMResult:
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
