"""TC-M4-01 〜 TC-M4-08: M4 Top-Gap manual implementation tests.

Verifies the Phase-1 growth loop:
  sample fixture JSONL  →  GapDashboard  →  top intents  →  behavior_policy.yml

SRS refs: FR-DASH-01, FR-DASH-02.
Resolves: TD-011 (validated end-to-end via priority_score ordering).

TDD: TC-M4-06, TC-M4-07, TC-M4-08 FAIL until behavior_policy.yml entries are added.
Run: pytest AITuber/tests/test_m4_policy_growth.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.gap_dashboard import GapDashboard
from orchestrator.policy_updater import PolicyUpdater
from orchestrator.proposal_validator import ProposalValidator, ValidationStatus

# ── Paths ──────────────────────────────────────────────────────────────────

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sample_gaps"
_POLICY_YML = (
    Path(__file__).parent.parent / "Assets" / "StreamingAssets" / "behavior_policy.yml"
)

# Intents expected to be surfaced by GapDashboard from the fixture
_EXPECTED_TOP5 = {
    "clap_hands", "thumbs_up", "express_embarrassed", "laugh_out_loud", "point_at_camera"
}
_NEW_INTENTS = [
    "clap_hands",
    "thumbs_up",
    "express_embarrassed",
    "laugh_out_loud",
    "point_at_camera",
    "spin_360",
    "express_sleepy",
]


# ── Fixtures (pytest) ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def dashboard() -> GapDashboard:
    return GapDashboard()


@pytest.fixture(scope="module")
def fixture_gaps(dashboard: GapDashboard) -> list[dict]:
    return dashboard.load_all_gaps(str(_FIXTURE_DIR))


@pytest.fixture(scope="module")
def summary(dashboard: GapDashboard, fixture_gaps: list[dict]) -> dict:
    return dashboard.build_summary(fixture_gaps)


# ── TC-M4-01: top intent is clap_hands ────────────────────────────────────


class TestFixtureTopGap:
    def test_top_intent_is_clap_hands(
        self, dashboard: GapDashboard, fixture_gaps: list[dict]
    ) -> None:
        """TC-M4-01: fixture 読み込み後、priority_score 1位は clap_hands。

        clap_hands: 12/65 × (1/1.0) = 0.1846 → 正規化後 1.0 (最高)
        """
        top = dashboard.get_top_gaps(fixture_gaps, top_n=1)
        assert len(top) == 1
        name = top[0]["intended_action"]["name"]
        assert name == "clap_hands", f"Expected clap_hands but got {name!r}"

    def test_top5_are_cheap_categories(
        self, dashboard: GapDashboard, fixture_gaps: list[dict]
    ) -> None:
        """TC-M4-02: top-5 はすべて missing_motion または missing_expression (cost_weight=1.0)。

        capability_limit (weight=5.0) の sing_intro / dance_move は top-5 に入らない。
        """
        top5 = dashboard.get_top_gaps(fixture_gaps, top_n=5)
        assert len(top5) == 5
        cheap_cats = {"missing_motion", "missing_expression"}
        for gap in top5:
            cat = gap["gap_category"]
            assert cat in cheap_cats, (
                f"Expected cheap category in top-5, got {cat!r} for "
                f"intent={gap['intended_action']['name']!r}"
            )

    def test_capability_limit_not_in_top5(
        self, dashboard: GapDashboard, fixture_gaps: list[dict]
    ) -> None:
        """TC-M4-03: capability_limit の sing_intro / dance_move は top-5 に含まれない。

        cost_weight=5.0 により score が抑制される。
        """
        top5 = dashboard.get_top_gaps(fixture_gaps, top_n=5)
        expensive_intents = {"sing_intro", "dance_move"}
        surfaced = {g["intended_action"]["name"] for g in top5}
        overlap = surfaced & expensive_intents
        assert not overlap, f"Expensive intents appeared in top-5: {overlap}"

    def test_expected_top5_intents_present(
        self, dashboard: GapDashboard, fixture_gaps: list[dict]
    ) -> None:
        """TC-M4-04: top-5 に期待する 5 intents がすべて含まれる。"""
        top5 = dashboard.get_top_gaps(fixture_gaps, top_n=5)
        surfaced = {g["intended_action"]["name"] for g in top5}
        assert surfaced == _EXPECTED_TOP5, (
            f"Top-5 mismatch.\n  expected: {_EXPECTED_TOP5}\n  got: {surfaced}"
        )


# ── TC-M4-05: total_gaps count ─────────────────────────────────────────────


class TestFixtureSummary:
    def test_total_gaps_count(self, summary: dict) -> None:
        """TC-M4-05: fixture の total_gaps は 65。"""
        assert summary["total_gaps"] == 65

    def test_missing_motion_is_largest_category(self, summary: dict) -> None:
        """TC-M4-05b: missing_motion が最多カテゴリ (12+9+6+5+4 = 36件)。"""
        by_cat = summary["by_category"]
        assert by_cat["missing_motion"] == 36

    def test_category_filter_missing_motion(
        self, dashboard: GapDashboard, fixture_gaps: list[dict]
    ) -> None:
        """TC-M4-05c: --category missing_motion のトップは clap_hands。"""
        top = dashboard.get_top_gaps(fixture_gaps, top_n=1, category="missing_motion")
        assert top[0]["intended_action"]["name"] == "clap_hands"


# ── TC-M4-06: behavior_policy.yml 新エントリ存在確認 ──────────────────────────


class TestPolicyEntries:
    """TC-M4-06: behavior_policy.yml に M4 由来のエントリが追加されている。

    NOTE: これらのテストは behavior_policy.yml にエントリが追加されるまで FAIL する。
    """

    @pytest.fixture(scope="class")
    def loaded_entries(self) -> list[dict]:
        updater = PolicyUpdater()
        return updater.load_policy(str(_POLICY_YML))

    @pytest.fixture(scope="class")
    def loaded_intents(self, loaded_entries: list[dict]) -> set[str]:
        return {e.get("intent", "") for e in loaded_entries}

    @pytest.mark.parametrize("intent", _NEW_INTENTS)
    def test_new_intent_exists(self, intent: str, loaded_intents: set[str]) -> None:
        """TC-M4-06: 各新規 intent が behavior_policy.yml に存在する。"""
        assert intent in loaded_intents, (
            f"Intent {intent!r} not found in behavior_policy.yml. "
            f"Add an entry: '- intent: {intent}'"
        )


# ── TC-M4-07: ProposalValidator で VALID ──────────────────────────────────


class TestNewEntriesValidation:
    """TC-M4-07: M4 で追加する各エントリが ProposalValidator を通過する。"""

    _NEW_PROPOSALS = [
        {"intent": "clap_hands", "cmd": "avatar_update", "gesture": "clap"},
        {"intent": "thumbs_up", "cmd": "avatar_update", "gesture": "thumbs_up"},
        {
            "intent": "express_embarrassed",
            "cmd": "avatar_update",
            "emotion": "embarrassed",
        },
        {
            "intent": "laugh_out_loud",
            "cmd": "avatar_update",
            "gesture": "laugh",
            "emotion": "happy",
        },
        {
            "intent": "point_at_camera",
            "cmd": "avatar_update",
            "gesture": "point_forward",
        },
        {"intent": "spin_360", "cmd": "avatar_update", "gesture": "spin"},
        {"intent": "express_sleepy", "cmd": "avatar_update", "emotion": "sleepy"},
    ]

    @pytest.fixture(scope="class")
    def validator(self) -> ProposalValidator:
        # Pass existing intents so DUPLICATE check doesn't collide with entries
        # already in behavior_policy.yml (pre-M4 ones).
        updater = PolicyUpdater()
        existing = updater.load_policy(str(_POLICY_YML))
        existing_intents = {e.get("intent", "") for e in existing}
        # Exclude new intents from the existing set so they are NOT marked DUPLICATE
        # during the validation run (they will be added fresh).
        existing_no_new = existing_intents - set(_NEW_INTENTS)
        return ProposalValidator(existing_policy=[{"intent": i} for i in existing_no_new])

    @pytest.mark.parametrize(
        "proposal",
        _NEW_PROPOSALS,
        ids=[p["intent"] for p in _NEW_PROPOSALS],
    )
    def test_proposal_valid(self, proposal: dict, validator: ProposalValidator) -> None:
        """TC-M4-07: 各 proposal が VALID ステータスを返す。"""
        result = validator.validate(proposal)
        assert result.status == ValidationStatus.VALID, (
            f"Proposal for {proposal['intent']!r} failed validation: {result.reason}"
        )


# ── TC-M4-08: PolicyUpdater.load_policy ───────────────────────────────────


class TestPolicyLoader:
    """TC-M4-08: behavior_policy.yml が正常にロードされ、全エントリが有効。"""

    @pytest.fixture(scope="class")
    def all_entries(self) -> list[dict]:
        updater = PolicyUpdater()
        return updater.load_policy(str(_POLICY_YML))

    def test_policy_loads_without_error(self, all_entries: list[dict]) -> None:
        """TC-M4-08a: ロード時に例外が発生しない。"""
        assert isinstance(all_entries, list)
        assert len(all_entries) > 0

    def test_all_entries_have_intent_and_cmd(self, all_entries: list[dict]) -> None:
        """TC-M4-08b: 全エントリに intent と cmd フィールドがある。"""
        for entry in all_entries:
            assert "intent" in entry, f"Entry missing 'intent': {entry}"
            assert "cmd" in entry, f"Entry missing 'cmd': {entry}"

    def test_entry_count_includes_m4_additions(self, all_entries: list[dict]) -> None:
        """TC-M4-08c: M4 追加後のエントリ数 ≥ 既存 (pre-M4) + 7。

        pre-M4 には 15 エントリ存在したため、合計 ≥ 22。
        """
        assert len(all_entries) >= 22, (
            f"Expected ≥22 entries after M4, got {len(all_entries)}. "
            "Ensure M4 entries were appended to behavior_policy.yml."
        )
