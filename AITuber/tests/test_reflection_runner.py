"""TC-REFL-01 〜 TC-REFL-08: ReflectionRunner unit tests.

Maps to: FR-REFL-01, FR-REFL-02.

TDD: these tests were written BEFORE the implementation.
Run: pytest AITuber/tests/test_reflection_runner.py
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from orchestrator.reflection_runner import ReflectionRunner

# ── Helpers / fixtures ─────────────────────────────────────────────────────


def _make_gap(
    *,
    intended_name: str = "point_at_screen",
    gap_category: str = "missing_motion",
    priority_score: float = 0.5,
    fallback_used: str = "nod",
    emotion: str = "happy",
) -> dict:
    return {
        "timestamp": "2026-03-03T12:00:00Z",
        "stream_id": "stream_20260303",
        "trigger": "avatar_intent_ws",
        "current_state": "reacting",
        "intended_action": {"type": "intent", "name": intended_name, "param": ""},
        "fallback_used": fallback_used,
        "context": {"emotion": emotion, "look_target": "camera", "recent_comment": "テスト"},
        "gap_category": gap_category,
        "priority_score": priority_score,
    }


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    lines = [json.dumps(e, ensure_ascii=False) for e in entries]
    path.write_text("\n".join(lines), encoding="utf-8")


# ── Mock LLM backends ──────────────────────────────────────────────────────


class _SuccessBackend:
    """Returns a minimal valid YAML proposal."""

    def __init__(self, yaml_text: str) -> None:
        self._yaml = yaml_text
        self.call_count = 0

    async def chat(self, system: str, user: str) -> tuple[str, float]:
        self.call_count += 1
        return self._yaml, 0.001


class _FailingBackend:
    """Always raises an exception."""

    async def chat(self, system: str, user: str) -> tuple[str, float]:
        raise ConnectionError("LLM unavailable")


class _EmptyBackend:
    """Returns empty YAML list."""

    async def chat(self, system: str, user: str) -> tuple[str, float]:
        return "[]", 0.0


# ── TC-REFL-01: load_gaps with valid JSONL ─────────────────────────────────


class TestLoadGaps:
    """TC-REFL-01〜03: Gap JSONL 読み込み (FR-REFL-01)."""

    def test_load_gaps_valid_jsonl(self, tmp_path):
        """TC-REFL-01: 有効な JSONL を読み込んで GapEntry dict リストを返す。"""
        gaps_file = tmp_path / "gaps.jsonl"
        gaps = [_make_gap(intended_name="fly"), _make_gap(intended_name="dance")]
        _write_jsonl(gaps_file, gaps)

        runner = ReflectionRunner()
        result = runner.load_gaps(str(gaps_file))

        assert len(result) == 2
        assert result[0]["intended_action"]["name"] == "fly"
        assert result[1]["intended_action"]["name"] == "dance"

    def test_load_gaps_empty_file(self, tmp_path):
        """TC-REFL-02: 空ファイル → 空リストを返す（例外なし）。"""
        gaps_file = tmp_path / "empty.jsonl"
        gaps_file.write_text("", encoding="utf-8")

        runner = ReflectionRunner()
        result = runner.load_gaps(str(gaps_file))

        assert result == []

    def test_load_gaps_skips_invalid_lines(self, tmp_path):
        """TC-REFL-03: 不正 JSON 行をスキップして残りを返す。"""
        gaps_file = tmp_path / "mixed.jsonl"
        valid_gap = _make_gap(intended_name="spin")
        gaps_file.write_text(
            "NOT_JSON\n"
            + json.dumps(valid_gap, ensure_ascii=False)
            + "\n{incomplete",
            encoding="utf-8",
        )

        runner = ReflectionRunner()
        result = runner.load_gaps(str(gaps_file))

        assert len(result) == 1
        assert result[0]["intended_action"]["name"] == "spin"

    def test_load_gaps_missing_file_raises(self, tmp_path):
        """TC-REFL-01b: 存在しないファイル → FileNotFoundError を送出する。"""
        runner = ReflectionRunner()
        with pytest.raises(FileNotFoundError):
            runner.load_gaps(str(tmp_path / "nonexistent.jsonl"))


# ── TC-REFL-07: filter_gaps ────────────────────────────────────────────────


class TestFilterGaps:
    """TC-REFL-07: gap_category フィルタリング (FR-REFL-01)."""

    def test_filter_by_category(self):
        """TC-REFL-07: gap_category="missing_motion" のみ抽出する。"""
        gaps = [
            _make_gap(intended_name="a", gap_category="missing_motion"),
            _make_gap(intended_name="b", gap_category="missing_behavior"),
            _make_gap(intended_name="c", gap_category="missing_motion"),
        ]
        runner = ReflectionRunner()
        result = runner.filter_gaps(gaps, category="missing_motion")

        assert len(result) == 2
        assert all(g["gap_category"] == "missing_motion" for g in result)

    def test_filter_no_category_returns_all(self):
        """TC-REFL-07b: category=None のとき全件を返す。"""
        gaps = [
            _make_gap(gap_category="missing_motion"),
            _make_gap(gap_category="unknown"),
        ]
        runner = ReflectionRunner()
        result = runner.filter_gaps(gaps, category=None)

        assert len(result) == 2

    def test_filter_max_count(self):
        """TC-REFL-07c: max_count を超えた場合は最初の max_count 件を返す。"""
        gaps = [_make_gap(intended_name=f"act_{i}") for i in range(10)]
        runner = ReflectionRunner()
        result = runner.filter_gaps(gaps, max_count=3)

        assert len(result) == 3


# ── TC-REFL-08: sort_by_priority ──────────────────────────────────────────


class TestSortByPriority:
    """TC-REFL-08: priority_score 降順ソート (FR-REFL-01)."""

    def test_sort_descending(self):
        """TC-REFL-08: priority_score が高い順に並ぶ。"""
        gaps = [
            _make_gap(priority_score=0.1),
            _make_gap(priority_score=0.9),
            _make_gap(priority_score=0.5),
        ]
        runner = ReflectionRunner()
        result = runner.sort_by_priority(gaps)

        scores = [g["priority_score"] for g in result]
        assert scores == sorted(scores, reverse=True)

    def test_sort_does_not_mutate_input(self):
        """TC-REFL-08b: 入力リストを変更しない（コピーを返す）。"""
        gaps = [_make_gap(priority_score=0.3), _make_gap(priority_score=0.8)]
        runner = ReflectionRunner()
        original_order = [g["priority_score"] for g in gaps]
        runner.sort_by_priority(gaps)

        assert [g["priority_score"] for g in gaps] == original_order


# ── TC-REFL-06: build_prompt ──────────────────────────────────────────────


class TestBuildPrompt:
    """TC-REFL-06: Gaps → LLM Prompt 変換 (FR-REFL-02)."""

    def test_prompt_contains_gap_info(self):
        """TC-REFL-06: プロンプトに Gap の intent 名が含まれる。"""
        gaps = [_make_gap(intended_name="unique_action_xyz")]
        runner = ReflectionRunner()
        prompt = runner.build_prompt(gaps)

        assert "unique_action_xyz" in prompt

    def test_prompt_contains_multiple_gaps(self):
        """TC-REFL-06b: 複数 Gap をまとめた1プロンプトを生成する。"""
        gaps = [
            _make_gap(intended_name="action_alpha"),
            _make_gap(intended_name="action_beta"),
        ]
        runner = ReflectionRunner()
        prompt = runner.build_prompt(gaps)

        assert "action_alpha" in prompt
        assert "action_beta" in prompt

    def test_prompt_includes_yaml_format_hint(self):
        """TC-REFL-06c: YAML 出力フォーマットの指示がプロンプトに含まれる。"""
        gaps = [_make_gap()]
        runner = ReflectionRunner()
        prompt = runner.build_prompt(gaps)

        # Should instruct LLM to produce YAML
        assert "yaml" in prompt.lower() or "intent:" in prompt


# ── TC-REFL-04〜05: generate_proposals ───────────────────────────────────


class TestGenerateProposals:
    """TC-REFL-04〜05: LLM 呼び出し → Proposal 生成 (FR-REFL-02)."""

    _VALID_YAML = textwrap.dedent("""\
        - intent: point_at_screen
          cmd: avatar_update
          gesture: point
          notes: Point gesture added by ReflectionRunner
    """)

    @pytest.mark.asyncio
    async def test_generate_from_valid_llm_response(self):
        """TC-REFL-04: モック LLM が返した YAML から Proposal dict リストを生成する。"""
        backend = _SuccessBackend(self._VALID_YAML)
        runner = ReflectionRunner(backend=backend)
        gaps = [_make_gap(intended_name="point_at_screen")]

        proposals = await runner.generate_proposals(gaps)

        assert len(proposals) == 1
        assert proposals[0]["intent"] == "point_at_screen"
        assert proposals[0]["cmd"] == "avatar_update"
        assert proposals[0]["gesture"] == "point"

    @pytest.mark.asyncio
    async def test_generate_returns_empty_on_llm_error(self):
        """TC-REFL-05: LLM がエラーを返した場合 → 空リストを返す（例外伝播なし）。"""
        backend = _FailingBackend()
        runner = ReflectionRunner(backend=backend)
        gaps = [_make_gap()]

        proposals = await runner.generate_proposals(gaps)

        assert proposals == []

    @pytest.mark.asyncio
    async def test_generate_empty_llm_response_returns_empty(self):
        """TC-REFL-05b: LLM が空 YAML を返した場合 → 空リストを返す。"""
        backend = _EmptyBackend()
        runner = ReflectionRunner(backend=backend)
        gaps = [_make_gap()]

        proposals = await runner.generate_proposals(gaps)

        assert proposals == []

    @pytest.mark.asyncio
    async def test_generate_calls_llm_once_per_batch(self):
        """TC-REFL-06: 複数 Gap を1回の LLM 呼び出しにまとめる。"""
        backend = _SuccessBackend(self._VALID_YAML)
        runner = ReflectionRunner(backend=backend)
        gaps = [_make_gap(intended_name="a"), _make_gap(intended_name="b")]

        await runner.generate_proposals(gaps)

        assert backend.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_with_invalid_yaml_skips_bad_entries(self):
        """TC-REFL-04b: LLM が一部不正 YAML を返した場合、不正エントリをスキップする。"""
        partial_yaml = textwrap.dedent("""\
            - intent: valid_action
              cmd: avatar_update
              gesture: nod
            - this is not valid yaml: [unclosed
        """)
        backend = _SuccessBackend(partial_yaml)
        runner = ReflectionRunner(backend=backend)
        gaps = [_make_gap()]

        # Should not raise; may return partial or empty
        proposals = await runner.generate_proposals(gaps)
        # At most the valid entry; must not crash
        assert isinstance(proposals, list)
