"""TC-DASH-01 〜 TC-DASH-12: GapDashboard unit tests.

Maps to: FR-DASH-01, FR-DASH-02.

TDD: these tests were written BEFORE the implementation.
Run: pytest AITuber/tests/test_gap_dashboard.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.gap_dashboard import GapDashboard

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_gap(
    *,
    intended_name: str = "some_action",
    gap_category: str = "missing_motion",
    priority_score: float = 0.0,
    stream_id: str = "stream_001",
) -> dict:
    return {
        "timestamp": "2026-03-03T12:00:00Z",
        "stream_id": stream_id,
        "trigger": "avatar_intent_ws",
        "current_state": "reacting",
        "intended_action": {"type": "intent", "name": intended_name, "param": ""},
        "fallback_used": "nod",
        "context": {"emotion": "happy", "look_target": "camera", "recent_comment": ""},
        "gap_category": gap_category,
        "priority_score": priority_score,
    }


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries),
        encoding="utf-8",
    )


# ── TC-DASH-01〜04: load_all_gaps ──────────────────────────────────────────


class TestLoadAllGaps:
    """TC-DASH-01〜04: JSONL ディレクトリ読み込み (FR-DASH-01)."""

    def test_single_file_loaded(self, tmp_path):
        """TC-DASH-01: 単一 JSONL ファイルの Gap をリストで返す。"""
        gaps = [_make_gap(intended_name="fly"), _make_gap(intended_name="dance")]
        _write_jsonl(tmp_path / "stream_001.jsonl", gaps)

        dashboard = GapDashboard()
        result = dashboard.load_all_gaps(str(tmp_path))

        assert len(result) == 2
        names = {g["intended_action"]["name"] for g in result}
        assert names == {"fly", "dance"}

    def test_multiple_files_aggregated(self, tmp_path):
        """TC-DASH-02: 複数 JSONL ファイルから全 Gap を集約する。"""
        _write_jsonl(tmp_path / "stream_001.jsonl", [_make_gap(intended_name="spin")])
        _write_jsonl(tmp_path / "stream_002.jsonl", [_make_gap(intended_name="jump")])

        dashboard = GapDashboard()
        result = dashboard.load_all_gaps(str(tmp_path))

        assert len(result) == 2
        names = {g["intended_action"]["name"] for g in result}
        assert names == {"spin", "jump"}

    def test_empty_directory_returns_empty_list(self, tmp_path):
        """TC-DASH-03: 空ディレクトリ → 空リストを返す（例外なし）。"""
        dashboard = GapDashboard()
        result = dashboard.load_all_gaps(str(tmp_path))

        assert result == []

    def test_nonexistent_directory_returns_empty_list(self, tmp_path):
        """TC-DASH-04: 存在しないディレクトリ → 空リストを返す（例外なし）。"""
        dashboard = GapDashboard()
        result = dashboard.load_all_gaps(str(tmp_path / "nonexistent"))

        assert result == []

    def test_non_jsonl_files_ignored(self, tmp_path):
        """TC-DASH-01b: .jsonl 以外のファイルは無視する。"""
        _write_jsonl(tmp_path / "stream_001.jsonl", [_make_gap(intended_name="nod")])
        (tmp_path / "readme.txt").write_text("ignored", encoding="utf-8")
        (tmp_path / "policy.yml").write_text("ignored", encoding="utf-8")

        dashboard = GapDashboard()
        result = dashboard.load_all_gaps(str(tmp_path))

        assert len(result) == 1

    def test_invalid_json_lines_skipped(self, tmp_path):
        """TC-DASH-01c: 不正 JSON 行をスキップして残りを集約する。"""
        valid = _make_gap(intended_name="valid_action")
        (tmp_path / "mixed.jsonl").write_text(
            "NOT_JSON\n" + json.dumps(valid, ensure_ascii=False) + "\nbad",
            encoding="utf-8",
        )
        dashboard = GapDashboard()
        result = dashboard.load_all_gaps(str(tmp_path))

        assert len(result) == 1
        assert result[0]["intended_action"]["name"] == "valid_action"


# ── TC-DASH-05: aggregate_by_category ─────────────────────────────────────


class TestAggregateByCategory:
    """TC-DASH-05: カテゴリ別集計 (FR-DASH-01)."""

    def test_category_counts(self):
        """TC-DASH-05: gap_category 別の件数を dict で返す。"""
        gaps = [
            _make_gap(gap_category="missing_motion"),
            _make_gap(gap_category="missing_motion"),
            _make_gap(gap_category="missing_behavior"),
        ]
        dashboard = GapDashboard()
        result = dashboard.aggregate_by_category(gaps)

        assert result["missing_motion"] == 2
        assert result["missing_behavior"] == 1

    def test_empty_gaps_returns_empty_dict(self):
        """TC-DASH-05b: 空リスト → 空 dict を返す。"""
        dashboard = GapDashboard()
        result = dashboard.aggregate_by_category([])

        assert result == {}

    def test_unknown_category_included(self):
        """TC-DASH-05c: gap_category が未知の値でも集計に含む。"""
        gaps = [_make_gap(gap_category="custom_category")]
        dashboard = GapDashboard()
        result = dashboard.aggregate_by_category(gaps)

        assert result["custom_category"] == 1


# ── TC-DASH-06: aggregate_by_intent ───────────────────────────────────────


class TestAggregateByIntent:
    """TC-DASH-06: intent 別集計 (FR-DASH-01)."""

    def test_intent_counts(self):
        """TC-DASH-06: intended_action.name 別の件数を dict で返す。"""
        gaps = [
            _make_gap(intended_name="point"),
            _make_gap(intended_name="point"),
            _make_gap(intended_name="jump"),
        ]
        dashboard = GapDashboard()
        result = dashboard.aggregate_by_intent(gaps)

        assert result["point"] == 2
        assert result["jump"] == 1

    def test_missing_intended_action_field_skipped(self):
        """TC-DASH-06b: intended_action フィールドがない Gap はスキップする。"""
        gaps = [
            _make_gap(intended_name="valid"),
            {"gap_category": "missing_motion"},  # no intended_action
        ]
        dashboard = GapDashboard()
        result = dashboard.aggregate_by_intent(gaps)

        assert result == {"valid": 1}


# ── TC-DASH-07〜08: compute_priority_scores ────────────────────────────────


class TestComputePriorityScores:
    """TC-DASH-07〜08: priority_score 算出 (FR-DASH-02, TD-011 解消)."""

    def test_higher_frequency_gives_higher_score(self):
        """TC-DASH-07: 発生頻度が高い intent ほど priority_score が高い。"""
        gaps = [
            _make_gap(intended_name="frequent", gap_category="missing_motion"),
            _make_gap(intended_name="frequent", gap_category="missing_motion"),
            _make_gap(intended_name="frequent", gap_category="missing_motion"),
            _make_gap(intended_name="rare", gap_category="missing_motion"),
        ]
        dashboard = GapDashboard()
        scores = dashboard.compute_priority_scores(gaps)

        assert scores["frequent"] > scores["rare"]

    def test_cheaper_category_gives_higher_score(self):
        """TC-DASH-08: cost_weight が低いカテゴリ（実装コスト小）は同頻度でも高スコア。"""
        gaps = [
            _make_gap(intended_name="motion_gap", gap_category="missing_motion"),
            _make_gap(intended_name="hard_gap", gap_category="capability_limit"),
        ]
        dashboard = GapDashboard()
        scores = dashboard.compute_priority_scores(gaps)

        # missing_motion (weight=1.0) > capability_limit (weight=5.0)
        assert scores["motion_gap"] > scores["hard_gap"]

    def test_empty_gaps_returns_empty_dict(self):
        """TC-DASH-07b: 空リスト → 空 dict を返す。"""
        dashboard = GapDashboard()
        scores = dashboard.compute_priority_scores([])

        assert scores == {}

    def test_scores_in_zero_to_one_range(self):
        """TC-DASH-07c: 全スコアは [0, 1] の範囲に収まる。"""
        gaps = [
            _make_gap(intended_name="a", gap_category="missing_motion"),
            _make_gap(intended_name="a", gap_category="missing_motion"),
            _make_gap(intended_name="b", gap_category="missing_behavior"),
        ]
        dashboard = GapDashboard()
        scores = dashboard.compute_priority_scores(gaps)

        for intent, score in scores.items():
            assert 0.0 <= score <= 1.0, f"score out of range for {intent}: {score}"

    def test_all_gaps_same_intent_gives_score_one(self):
        """TC-DASH-07d: 単一 intent のみ → その intent のスコアが最大 (1.0)。"""
        gaps = [_make_gap(intended_name="only_one", gap_category="missing_motion")] * 5
        dashboard = GapDashboard()
        scores = dashboard.compute_priority_scores(gaps)

        assert scores["only_one"] == pytest.approx(1.0)


# ── TC-DASH-09〜10: get_top_gaps ───────────────────────────────────────────


class TestGetTopGaps:
    """TC-DASH-09〜10: 上位 Gap フィルタリング (FR-DASH-02)."""

    def test_top_n_returns_n_items(self):
        """TC-DASH-09: top_n=3 のとき 3 件を返す。"""
        gaps = [_make_gap(intended_name=f"act_{i}") for i in range(10)]
        dashboard = GapDashboard()
        result = dashboard.get_top_gaps(gaps, top_n=3)

        assert len(result) == 3

    def test_top_n_sorted_by_priority_desc(self):
        """TC-DASH-09b: priority_score 降順で上位 N 件を返す。"""
        gaps = [
            _make_gap(intended_name="low", gap_category="capability_limit"),
            _make_gap(intended_name="high", gap_category="missing_motion"),
            _make_gap(intended_name="high", gap_category="missing_motion"),
        ]
        dashboard = GapDashboard()
        result = dashboard.get_top_gaps(gaps, top_n=2)

        # The top item should be "high" (higher score)
        top_names = [g["intended_action"]["name"] for g in result]
        assert top_names[0] == "high"

    def test_category_filter_applied(self):
        """TC-DASH-10: category フィルタを適用して対象カテゴリのみ返す。"""
        gaps = [
            _make_gap(intended_name="motion_a", gap_category="missing_motion"),
            _make_gap(intended_name="behavior_b", gap_category="missing_behavior"),
            _make_gap(intended_name="motion_c", gap_category="missing_motion"),
        ]
        dashboard = GapDashboard()
        result = dashboard.get_top_gaps(gaps, top_n=10, category="missing_motion")

        assert all(g["gap_category"] == "missing_motion" for g in result)
        assert len(result) == 2

    def test_top_n_larger_than_gaps_returns_all(self):
        """TC-DASH-09c: top_n がリストより大きい場合は全件返す。"""
        gaps = [_make_gap(intended_name="only")]
        dashboard = GapDashboard()
        result = dashboard.get_top_gaps(gaps, top_n=100)

        assert len(result) == 1

    def test_empty_gaps_returns_empty(self):
        """TC-DASH-09d: 空リスト → 空リストを返す。"""
        dashboard = GapDashboard()
        result = dashboard.get_top_gaps([], top_n=5)

        assert result == []


# ── TC-DASH-11: stream-level summary ──────────────────────────────────────


class TestStreamSummary:
    """TC-DASH-11: ストリーム別集計 (FR-DASH-01)."""

    def test_aggregate_by_stream(self):
        """TC-DASH-11: stream_id 別の Gap 件数を返す。"""
        gaps = [
            _make_gap(stream_id="stream_001"),
            _make_gap(stream_id="stream_001"),
            _make_gap(stream_id="stream_002"),
        ]
        dashboard = GapDashboard()
        result = dashboard.aggregate_by_stream(gaps)

        assert result["stream_001"] == 2
        assert result["stream_002"] == 1

    def test_empty_returns_empty(self):
        """TC-DASH-11b: 空リスト → 空 dict を返す。"""
        dashboard = GapDashboard()
        assert dashboard.aggregate_by_stream([]) == {}


# ── TC-DASH-12: build_summary ─────────────────────────────────────────────


class TestBuildSummary:
    """TC-DASH-12: 集計サマリ dict 生成 (FR-DASH-02)."""

    def test_summary_has_required_keys(self):
        """TC-DASH-12: サマリ dict に必須キーが揃っている。"""
        gaps = [
            _make_gap(intended_name="a", gap_category="missing_motion"),
            _make_gap(intended_name="b", gap_category="missing_behavior"),
        ]
        dashboard = GapDashboard()
        summary = dashboard.build_summary(gaps)

        assert "total_gaps" in summary
        assert "by_category" in summary
        assert "by_intent" in summary
        assert "top_gaps" in summary
        assert "streams" in summary

    def test_total_gaps_count_correct(self):
        """TC-DASH-12b: total_gaps が Gap リストの件数に一致する。"""
        gaps = [_make_gap() for _ in range(7)]
        dashboard = GapDashboard()
        summary = dashboard.build_summary(gaps)

        assert summary["total_gaps"] == 7

    def test_empty_gaps_summary(self):
        """TC-DASH-12c: 空リスト → total_gaps=0, 各 dict が空。"""
        dashboard = GapDashboard()
        summary = dashboard.build_summary([])

        assert summary["total_gaps"] == 0
        assert summary["by_category"] == {}
        assert summary["by_intent"] == {}
        assert summary["top_gaps"] == []
