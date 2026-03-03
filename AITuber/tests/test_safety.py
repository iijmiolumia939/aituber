"""TC-SAFE-01: NG comment never reaches LLM.

Maps to: FR-SAFE-01.
"""

from __future__ import annotations

from orchestrator.safety import (
    NGCategory,
    SafetyVerdict,
    check_safety,
)


class TestSafetyFilter:
    """TC-SAFE-01: NG-confirmed comments never reach Bandit/LLM."""

    # ── NG: Personal information ──────────────────────────────────────

    def test_ng_email(self):
        result = check_safety("僕のメールは test@example.com だよ")
        assert result.verdict == SafetyVerdict.NG
        assert result.category == NGCategory.PERSONAL_INFORMATION

    def test_ng_phone(self):
        result = check_safety("090-1234-5678 に電話して")
        assert result.verdict == SafetyVerdict.NG
        assert result.category == NGCategory.PERSONAL_INFORMATION

    def test_ng_address_keyword(self):
        result = check_safety("住所を教えて")
        assert result.verdict == SafetyVerdict.NG
        assert result.category == NGCategory.PERSONAL_INFORMATION

    # ── NG: Hate / harassment ─────────────────────────────────────────

    def test_ng_hate_keyword(self):
        result = check_safety("死ね")
        assert result.verdict == SafetyVerdict.NG
        assert result.category == NGCategory.HATE_OR_HARASSMENT

    def test_ng_hate_slur(self):
        result = check_safety("ガイジ")
        assert result.verdict == SafetyVerdict.NG
        assert result.category == NGCategory.HATE_OR_HARASSMENT

    # ── NG: Self harm ─────────────────────────────────────────────────

    def test_ng_self_harm(self):
        result = check_safety("しにたい")
        assert result.verdict == SafetyVerdict.NG
        assert result.category == NGCategory.SELF_HARM

    def test_ng_self_harm_template(self):
        result = check_safety("自殺したい")
        assert result.verdict == SafetyVerdict.NG
        assert result.template_response is not None
        assert "専門窓口" in result.template_response

    # ── NG: Crime ─────────────────────────────────────────────────────

    def test_ng_crime(self):
        result = check_safety("爆破予告します")
        assert result.verdict == SafetyVerdict.NG
        assert result.category == NGCategory.CRIME_FACILITATION

    # ── OK: Normal messages ───────────────────────────────────────────

    def test_ok_normal(self):
        result = check_safety("今日の配信楽しいね！")
        assert result.verdict == SafetyVerdict.OK
        assert result.category is None

    def test_ok_empty(self):
        result = check_safety("")
        assert result.verdict == SafetyVerdict.OK

    def test_ok_whitespace(self):
        result = check_safety("   ")
        assert result.verdict == SafetyVerdict.OK

    def test_ok_greeting(self):
        result = check_safety("こんにちは！初見です")
        assert result.verdict == SafetyVerdict.OK

    # ── Template response present for all NG ──────────────────────────

    def test_ng_always_has_template(self):
        """Every NG result must include a template_response."""
        ng_texts = ["死ね", "住所教えて", "自殺", "爆破予告"]
        for text in ng_texts:
            result = check_safety(text)
            assert result.verdict == SafetyVerdict.NG, f"Expected NG for: {text}"
            assert result.template_response is not None, f"No template for: {text}"
            assert len(result.template_response) > 0

    # ── Priority: self_harm > hate ────────────────────────────────────

    def test_self_harm_priority_over_hate(self):
        """Self-harm keywords checked before hate keywords."""
        result = check_safety("死にたい")
        assert result.category == NGCategory.SELF_HARM

    # ── GRAYゾーン: LLM回避プロンプトで通過 ───────────────────────────

    def test_gray_politics(self):
        result = check_safety("政治の話しようよ")
        assert result.verdict == SafetyVerdict.GRAY
        assert result.avoidance_hint is not None
        assert len(result.avoidance_hint) > 0

    def test_gray_religion(self):
        result = check_safety("宗教について教えて")
        assert result.verdict == SafetyVerdict.GRAY

    def test_gray_age(self):
        result = check_safety("何歳ですか？")
        assert result.verdict == SafetyVerdict.GRAY

    def test_gray_does_not_block(self):
        """GRAYはNGではない → Bandit/LLMに到達する。"""
        result = check_safety("選挙の話題")
        assert result.verdict != SafetyVerdict.NG
        assert result.template_response is None

    def test_gray_avoidance_hint_present(self):
        """GRAY結果にはavoidance_hintが含まれる。"""
        result = check_safety("ギャンブルで稼ぎたい")
        assert result.verdict == SafetyVerdict.GRAY
        assert "別の話題" in result.avoidance_hint

    # ── MINORS_INAPPROPRIATE 検出 ─────────────────────────────────────

    def test_ng_minors_explicit(self):
        result = check_safety("児童ポルノは犯罪")
        assert result.verdict == SafetyVerdict.NG
        assert result.category == NGCategory.MINORS_INAPPROPRIATE

    def test_ng_minors_pattern(self):
        result = check_safety("未成年の性的な話題")
        assert result.verdict == SafetyVerdict.NG
        assert result.category == NGCategory.MINORS_INAPPROPRIATE

    def test_ng_minors_template_present(self):
        result = check_safety("ロリコンの話")
        assert result.verdict == SafetyVerdict.NG
        assert result.template_response is not None
        assert len(result.template_response) > 0
