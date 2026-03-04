"""TC-M5-01 〜 TC-M5-09 + TC-M6-08/09: reflection_cli end-to-end pipeline tests.

Verifies the full Phase-1 Growth Loop wiring:
  GapDashboard → ReflectionRunner(backend) → ProposalValidator → PolicyUpdater

Also covers Phase-2 staging output (--output flag) for M6.

SRS refs: FR-REFL-01, FR-REFL-02, FR-REFL-03, FR-REFL-04, FR-APPR-01.
Resolves: TD-010 (backend wiring).

TDD: tests written BEFORE implementation.
Run: pytest AITuber/tests/test_reflection_cli.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import will fail until reflection_cli.py is created — that's expected TDD red.
from orchestrator.reflection_cli import ReflectionCLI, build_parser

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_gap(intent: str, category: str = "missing_motion") -> dict:
    return {
        "timestamp": "2026-03-04T10:00:00Z",
        "stream_id": "stream_test",
        "trigger": "avatar_intent_ws",
        "current_state": "reacting",
        "intended_action": {"type": "intent", "name": intent, "param": ""},
        "fallback_used": "nod",
        "context": {"emotion": "happy", "look_target": "camera", "recent_comment": ""},
        "gap_category": category,
        "priority_score": 0.0,
    }


def _write_gaps(path: Path, gaps: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(g, ensure_ascii=False) for g in gaps), encoding="utf-8"
    )


_VALID_YAML_RESPONSE = """\
```yaml
- intent: new_gesture
  cmd: avatar_update
  gesture: wave
  priority: 0
  notes: New gesture from LLM
```
"""

_INVALID_YAML_RESPONSE = "これは有効な YAML ではありません: {{"


# ── TC-M5-01: empty gaps dir ───────────────────────────────────────────────


class TestEmptyOrMissingGapsDir:
    def test_nonexistent_dir_returns_zero(self, tmp_path: Path) -> None:
        """TC-M5-01: gaps_dir が存在しない → exit code 0、policy 変更なし。"""
        nonexistent = tmp_path / "no_such_dir"
        policy = tmp_path / "behavior_policy.yml"
        policy.write_text("", encoding="utf-8")

        cli = ReflectionCLI(
            gaps_dir=str(nonexistent),
            policy_path=str(policy),
            top_n=5,
            dry_run=True,
        )
        result = asyncio.run(cli.run())
        assert result == 0

    def test_empty_dir_returns_zero(self, tmp_path: Path) -> None:
        """TC-M5-02: gaps ディレクトリが空 → exit code 0。"""
        gaps_dir = tmp_path / "gaps"
        gaps_dir.mkdir()
        policy = tmp_path / "behavior_policy.yml"
        policy.write_text("", encoding="utf-8")

        cli = ReflectionCLI(
            gaps_dir=str(gaps_dir),
            policy_path=str(policy),
            top_n=5,
            dry_run=True,
        )
        result = asyncio.run(cli.run())
        assert result == 0


# ── TC-M5-03/04: LLM backend responses ────────────────────────────────────


class TestWithMockBackend:
    @pytest.fixture
    def gaps_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "gaps"
        d.mkdir()
        gaps = [_make_gap("clap_hands")] * 3 + [_make_gap("thumbs_up")] * 2
        _write_gaps(d / "stream_001.jsonl", gaps)
        return d

    @pytest.fixture
    def policy_path(self, tmp_path: Path) -> Path:
        p = tmp_path / "behavior_policy.yml"
        p.write_text("", encoding="utf-8")
        return p

    def test_valid_yaml_response_generates_proposals(
        self, gaps_dir: Path, policy_path: Path
    ) -> None:
        """TC-M5-03: mock backend が valid YAML → proposals が生成される。"""
        mock_backend = MagicMock()
        mock_backend.chat = AsyncMock(return_value=(_VALID_YAML_RESPONSE, 0.01))

        cli = ReflectionCLI(
            gaps_dir=str(gaps_dir),
            policy_path=str(policy_path),
            top_n=5,
            dry_run=True,
            backend=mock_backend,
        )
        result = asyncio.run(cli.run())
        assert result == 0
        # backend.chat must have been called at least once
        mock_backend.chat.assert_called_once()

    def test_invalid_yaml_response_zero_proposals(
        self, gaps_dir: Path, policy_path: Path
    ) -> None:
        """TC-M5-04: mock backend が invalid YAML → proposals=0件、exit 0。"""
        mock_backend = MagicMock()
        mock_backend.chat = AsyncMock(return_value=(_INVALID_YAML_RESPONSE, 0.01))

        cli = ReflectionCLI(
            gaps_dir=str(gaps_dir),
            policy_path=str(policy_path),
            top_n=5,
            dry_run=True,
            backend=mock_backend,
        )
        result = asyncio.run(cli.run())
        assert result == 0

    def test_backend_exception_returns_zero_exit(
        self, gaps_dir: Path, policy_path: Path
    ) -> None:
        """TC-M5-07: backend が例外送出 → proposals=0件、CLI は 0 で終了。"""
        mock_backend = MagicMock()
        mock_backend.chat = AsyncMock(side_effect=RuntimeError("API error"))

        cli = ReflectionCLI(
            gaps_dir=str(gaps_dir),
            policy_path=str(policy_path),
            top_n=5,
            dry_run=True,
            backend=mock_backend,
        )
        result = asyncio.run(cli.run())
        assert result == 0


# ── TC-M5-05/06: dry_run behavior ─────────────────────────────────────────


class TestDryRun:
    @pytest.fixture
    def setup(self, tmp_path: Path):
        gaps_dir = tmp_path / "gaps"
        gaps_dir.mkdir()
        gaps = [_make_gap("new_intent")] * 5
        _write_gaps(gaps_dir / "stream.jsonl", gaps)
        policy = tmp_path / "bp.yml"
        policy.write_text("", encoding="utf-8")
        return gaps_dir, policy

    def test_dry_run_does_not_write_policy(self, setup: Any) -> None:
        """TC-M5-05: dry_run=True → behavior_policy.yml は変更されない。"""
        gaps_dir, policy = setup
        original_content = policy.read_text(encoding="utf-8")

        mock_backend = MagicMock()
        mock_backend.chat = AsyncMock(return_value=(_VALID_YAML_RESPONSE, 0.01))

        cli = ReflectionCLI(
            gaps_dir=str(gaps_dir),
            policy_path=str(policy),
            top_n=5,
            dry_run=True,
            backend=mock_backend,
        )
        asyncio.run(cli.run())

        assert policy.read_text(encoding="utf-8") == original_content

    def test_non_dry_run_writes_valid_proposals(self, setup: Any) -> None:
        """TC-M5-06: dry_run=False + valid proposal → policy に追記される。"""
        gaps_dir, policy = setup

        mock_backend = MagicMock()
        mock_backend.chat = AsyncMock(return_value=(_VALID_YAML_RESPONSE, 0.01))

        cli = ReflectionCLI(
            gaps_dir=str(gaps_dir),
            policy_path=str(policy),
            top_n=5,
            dry_run=False,
            backend=mock_backend,
        )
        asyncio.run(cli.run())

        content = policy.read_text(encoding="utf-8")
        assert "new_gesture" in content


# ── TC-M5-08: --top-n limits LLM input ────────────────────────────────────


class TestTopN:
    def test_top_n_limits_gaps_sent_to_llm(self, tmp_path: Path) -> None:
        """TC-M5-08: --top-n N → LLM には最大 N unique-intent の gap を渡す。"""
        gaps_dir = tmp_path / "gaps"
        gaps_dir.mkdir()
        # 6 distinct intents × 2 each = 12 gaps
        intents = [f"intent_{i}" for i in range(6)]
        gaps = []
        for intent in intents:
            gaps.extend([_make_gap(intent)] * 2)
        _write_gaps(gaps_dir / "stream.jsonl", gaps)

        policy = tmp_path / "bp.yml"
        policy.write_text("", encoding="utf-8")

        mock_backend = MagicMock()
        _yaml = "- intent: x\n  cmd: avatar_update\n  gesture: g"
        mock_backend.chat = AsyncMock(return_value=(_yaml, 0.01))

        cli = ReflectionCLI(
            gaps_dir=str(gaps_dir),
            policy_path=str(policy),
            top_n=3,
            dry_run=True,
            backend=mock_backend,
        )
        asyncio.run(cli.run())

        # Inspect what was passed to the LLM build_prompt via call args
        call_args = mock_backend.chat.call_args
        assert call_args is not None
        user_prompt = call_args[0][1] if call_args[0] else call_args[1].get("user", "")
        # At most 3 intents should appear in the prompt
        present = sum(1 for intent in intents if intent in user_prompt)
        assert present <= 3


# ── TC-M5-09: CLI argparser ────────────────────────────────────────────────


class TestParser:
    def test_parser_defaults(self) -> None:
        """TC-M5-09: build_parser() のデフォルト値検証。"""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.top_n == 5
        assert args.dry_run is False

    def test_parser_dry_run_flag(self) -> None:
        """TC-M5-09b: --dry-run フラグが True になる。"""
        parser = build_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_parser_top_n(self) -> None:
        """TC-M5-09c: --top-n N を解析できる。"""
        parser = build_parser()
        args = parser.parse_args(["--top-n", "10"])
        assert args.top_n == 10


# ── TC-M6-08/09: --output staging flag ────────────────────────────────────


class TestOutputFlag:
    @pytest.fixture
    def setup(self, tmp_path: Path):
        gaps_dir = tmp_path / "gaps"
        gaps_dir.mkdir()
        gaps = [_make_gap("new_motion")] * 3
        _write_gaps(gaps_dir / "stream.jsonl", gaps)
        policy = tmp_path / "bp.yml"
        policy.write_text("", encoding="utf-8")
        staging = tmp_path / "staging.yml"
        return gaps_dir, policy, staging

    def test_output_flag_writes_staging_file(self, setup: Any) -> None:
        """TC-M6-08: --output 指定 → staging.yml に proposals が書き込まれる。"""
        gaps_dir, policy, staging = setup

        mock_backend = MagicMock()
        mock_backend.chat = AsyncMock(return_value=(_VALID_YAML_RESPONSE, 0.01))

        cli = ReflectionCLI(
            gaps_dir=str(gaps_dir),
            policy_path=str(policy),
            top_n=5,
            dry_run=False,
            backend=mock_backend,
            output_path=str(staging),
        )
        result = asyncio.run(cli.run())
        assert result == 0
        assert staging.exists()
        content = staging.read_text(encoding="utf-8")
        assert "new_gesture" in content

    def test_output_flag_does_not_write_policy(self, setup: Any) -> None:
        """TC-M6-09: --output 指定時は behavior_policy.yml を変更しない。"""
        gaps_dir, policy, staging = setup
        original = policy.read_text(encoding="utf-8")

        mock_backend = MagicMock()
        mock_backend.chat = AsyncMock(return_value=(_VALID_YAML_RESPONSE, 0.01))

        cli = ReflectionCLI(
            gaps_dir=str(gaps_dir),
            policy_path=str(policy),
            top_n=5,
            dry_run=False,
            backend=mock_backend,
            output_path=str(staging),
        )
        asyncio.run(cli.run())
        assert policy.read_text(encoding="utf-8") == original

    def test_parser_output_flag(self) -> None:
        """TC-M6-10: --output フラグを解析できる。"""
        parser = build_parser()
        args = parser.parse_args(["--output", "staging.yml"])
        assert args.output == "staging.yml"

    def test_parser_output_default_is_none(self) -> None:
        """TC-M6-11: --output のデフォルトは None。"""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.output is None
