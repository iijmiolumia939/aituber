"""Theory of Mind Estimator — viewer intent/sentiment classification.

FR-E3-01: Infers viewer intent, sentiment, and familiarity from comment context.
Issue: #13 E-3 Theory of Mind

References:
  Wilf et al. (2023), SimToM, arXiv:2311.10227
  Park et al. (2023), Generative Agents, arXiv:2304.03442 §5

Design: Rule-based MVP for deterministic testing; LLM upgrade path via
        Callable[str] override.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Constants ────────────────────────────────────────────────────────

_QUESTION_PATTERNS = re.compile(
    r"なに|何|どう|どこ|いつ|だれ|誰|なぜ|なんで|どれ|どんな|どのくらい"
    r"|(what|who|when|where|why|how|which)\b|[？?]",
    re.IGNORECASE,
)
_PRAISE_PATTERNS = re.compile(
    r"(すごい|かわいい|かっこいい|最高|好き|ありがとう|ありがとございます"
    r"|えらい|天才|素敵|癒し|神|ファン|応援|awesome|cute|great|love|thanks|nice)",
    re.IGNORECASE,
)
_TEASE_PATTERNS = re.compile(
    r"(うそ|嘘|ヤバい|やばい|草|笑|ｗ+|w+|ざこ|弱い|無理|ひどい|バカ|ほんとに|マジか)",
    re.IGNORECASE,
)
_CONCERN_PATTERNS = re.compile(
    r"(大丈夫|だいじょうぶ|心配|つらい|辛い|疲れ|元気ない|具合|ok\?|worry|sad|tired)",
    re.IGNORECASE,
)
_POSITIVE_PATTERNS = re.compile(
    r"(嬉しい|楽し|いい|笑|좋아|好き|最高|ありがとう|happy|good|fun|love|nice)",
    re.IGNORECASE,
)
_NEGATIVE_PATTERNS = re.compile(
    r"(悲し|sad|つまらない|嫌い|怖い|恐ろしい|ひどい|bad|boring|hate|scary)",
    re.IGNORECASE,
)

# Familiarity thresholds (based on # of previous episodes from same author)
_NEWCOMER_THRESHOLD = 0
_REGULAR_THRESHOLD = 3
_SUPERCHATTER_THRESHOLD = 15


@dataclass
class TomEstimate:
    """Viewer perspective estimate.

    FR-E3-01.

    Attributes:
        intent: comment intent category
        sentiment: emotional polarity
        familiarity: viewer relationship tier
        knowledge_assumed: what the viewer likely already knows about YUI.A
    """

    intent: str  # "question" | "praise" | "tease" | "concern" | "neutral"
    sentiment: str  # "positive" | "negative" | "neutral"
    familiarity: str  # "newcomer" | "regular" | "superchatter"
    knowledge_assumed: str  # short description of assumed knowledge


class TomEstimator:
    """Estimate viewer Theory-of-Mind from a comment.

    FR-E3-01: perspective-taking for adaptive responses.
    """

    def estimate(
        self,
        comment: str,
        author: str = "",
        episode_count: int = 0,
    ) -> TomEstimate:
        """Classify a viewer comment.

        Args:
            comment: raw comment text.
            author: display name (used for logging only).
            episode_count: number of past episodes from this author (for familiarity).

        Returns:
            TomEstimate dataclass.
        """
        intent = self._classify_intent(comment)
        sentiment = self._classify_sentiment(comment)
        familiarity = self._classify_familiarity(episode_count)
        knowledge = self._infer_knowledge(familiarity)

        return TomEstimate(
            intent=intent,
            sentiment=sentiment,
            familiarity=familiarity,
            knowledge_assumed=knowledge,
        )

    # ── Private classifiers ──────────────────────────────────────────

    @staticmethod
    def _classify_intent(text: str) -> str:
        """Rule-based intent classification.

        Priority: question > concern > praise > tease > neutral.
        """
        if _QUESTION_PATTERNS.search(text):
            return "question"
        if _CONCERN_PATTERNS.search(text):
            return "concern"
        if _PRAISE_PATTERNS.search(text):
            return "praise"
        if _TEASE_PATTERNS.search(text):
            return "tease"
        return "neutral"

    @staticmethod
    def _classify_sentiment(text: str) -> str:
        pos = bool(_POSITIVE_PATTERNS.search(text))
        neg = bool(_NEGATIVE_PATTERNS.search(text))
        if pos and not neg:
            return "positive"
        if neg and not pos:
            return "negative"
        return "neutral"

    @staticmethod
    def _classify_familiarity(episode_count: int) -> str:
        if episode_count >= _SUPERCHATTER_THRESHOLD:
            return "superchatter"
        if episode_count >= _REGULAR_THRESHOLD:
            return "regular"
        return "newcomer"

    @staticmethod
    def _infer_knowledge(familiarity: str) -> str:
        if familiarity == "newcomer":
            return "YUI.A が何者かを知らない可能性が高い"
        if familiarity == "regular":
            return "YUI.A の基本設定は知っている"
        return "YUI.A の詳細な設定・口調・習慣を熟知している"

    def to_prompt_fragment(self, estimate: TomEstimate) -> str:
        """Return a [TOM] block to inject into system prompt.

        FR-E3-01.
        """
        return (
            f"[TOM]\n"
            f"視聴者の意図: {estimate.intent}\n"
            f"感情極性: {estimate.sentiment}\n"
            f"親しさ: {estimate.familiarity}\n"
            f"想定知識: {estimate.knowledge_assumed}"
        )
