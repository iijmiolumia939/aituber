"""Safety filter – must run BEFORE Bandit and LLM.

SRS refs: FR-SAFE-01, safety.yml ordering, TC-SAFE-01.
NG-confirmed comments never reach Bandit/LLM.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class SafetyVerdict(Enum):
    OK = "ok"
    NG = "ng"
    GRAY = "gray"


class NGCategory(Enum):
    PERSONAL_INFORMATION = "personal_information"
    HATE_OR_HARASSMENT = "hate_or_harassment"
    CRIME_FACILITATION = "crime_facilitation"
    MINORS_INAPPROPRIATE = "minors_inappropriate"
    SELF_HARM = "self_harm"


# ── Template responses (from safety.yml) ──────────────────────────────

SAFE_TEMPLATES: dict[NGCategory, str] = {
    NGCategory.PERSONAL_INFORMATION: (
        "個人情報に関わる内容はお答えできないよ。別の話題にしよっか。"
    ),
    NGCategory.HATE_OR_HARASSMENT: ("その話題は誰かを傷つける可能性があるからやめよう。"),
    NGCategory.SELF_HARM: (
        "それは大事な話だね。つらいときは一人で抱えないで、" "身近な人や専門窓口に相談してね。"
    ),
    NGCategory.CRIME_FACILITATION: ("その話題にはお答えできないよ。別の話にしよっか。"),
    NGCategory.MINORS_INAPPROPRIATE: ("その話題にはお答えできないよ。別の話にしよっか。"),
}

# ── Keyword / pattern lists (lightweight first‑pass) ─────────────────
# In production, these would be loaded from an external config to be
# updatable without re-deployment.

_PERSONAL_INFO_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b\d{3}[-‐]?\d{4}[-‐]?\d{4}\b"),  # phone-like
    re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"),  # email
    re.compile(r"住所|自宅|電話番号|メールアドレス|本名"),
]

_HATE_KEYWORDS: list[re.Pattern[str]] = [
    re.compile(r"死ね|殺す|ころす|氏ね"),
    re.compile(r"ガイジ|きちがい|基地外|池沼"),
]

_SELF_HARM_KEYWORDS: list[re.Pattern[str]] = [
    re.compile(r"自殺|しにたい|死にたい|自傷|リスカ"),
]

_CRIME_KEYWORDS: list[re.Pattern[str]] = [
    re.compile(r"爆破予告|殺害予告|銃の作り方|ドラッグ|覚醒剤"),
]

_MINORS_KEYWORDS: list[re.Pattern[str]] = [
    re.compile(r"児童ポルノ|児ポ|ロリコン|ペドフィリア"),
    re.compile(r"未成年.*性的|小学生.*エロ|中学生.*エロ"),
    re.compile(r"子供.*裸|子ども.*裸"),
]

# ── Grayゾーン検出パターン (llm_avoidance_prompt で対処) ─────────────
_GRAY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"政治|宗教|選挙|投票"),
    re.compile(r"稼ぎ方|借金|ギャンブル"),
    re.compile(r"年齢|何歳|身長|体重|スリーサイズ"),
]


@dataclass(frozen=True)
class FilterResult:
    verdict: SafetyVerdict
    category: NGCategory | None = None
    template_response: str | None = None
    avoidance_hint: str | None = None  # GRAYゾーン用LLM回避ヒント


def _match_any(text: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def check_safety(text: str) -> FilterResult:
    """Run lightweight keyword / regex safety filter.

    Returns FilterResult with verdict, detected category, and template
    response for NG items.
    """
    if not text or not text.strip():
        return FilterResult(verdict=SafetyVerdict.OK)

    normalized = text.strip().lower()

    # Check each NG category in priority order
    if _match_any(normalized, _SELF_HARM_KEYWORDS):
        cat = NGCategory.SELF_HARM
        return FilterResult(
            verdict=SafetyVerdict.NG,
            category=cat,
            template_response=SAFE_TEMPLATES[cat],
        )

    if _match_any(normalized, _CRIME_KEYWORDS):
        cat = NGCategory.CRIME_FACILITATION
        return FilterResult(
            verdict=SafetyVerdict.NG,
            category=cat,
            template_response=SAFE_TEMPLATES[cat],
        )

    if _match_any(normalized, _HATE_KEYWORDS):
        cat = NGCategory.HATE_OR_HARASSMENT
        return FilterResult(
            verdict=SafetyVerdict.NG,
            category=cat,
            template_response=SAFE_TEMPLATES[cat],
        )

    if _match_any(normalized, _PERSONAL_INFO_PATTERNS):
        cat = NGCategory.PERSONAL_INFORMATION
        return FilterResult(
            verdict=SafetyVerdict.NG,
            category=cat,
            template_response=SAFE_TEMPLATES[cat],
        )

    if _match_any(normalized, _MINORS_KEYWORDS):
        cat = NGCategory.MINORS_INAPPROPRIATE
        return FilterResult(
            verdict=SafetyVerdict.NG,
            category=cat,
            template_response=SAFE_TEMPLATES[cat],
        )

    # ── Grayゾーン: LLM回避プロンプト付きで通過 ──────────────────────
    if _match_any(normalized, _GRAY_PATTERNS):
        return FilterResult(
            verdict=SafetyVerdict.GRAY,
            avoidance_hint=(
                "この話題はセンシティブな可能性があります。"
                "直接的な回答は避け、別の話題に自然に誘導してください。"
            ),
        )

    # Gray detection could be expanded; for now only clear NG or OK.
    return FilterResult(verdict=SafetyVerdict.OK)
