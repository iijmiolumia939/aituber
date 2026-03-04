"""TC-M6-01 〜 TC-M6-07: approve_cli human-approval flow tests.

Phase-2 Growth Loop:
  proposals_staging.yml → ApproveCLI → behavior_policy.yml (approved only)

SRS refs: FR-APPR-01, FR-APPR-02, FR-APPR-03.

TDD: tests written BEFORE implementation.
Run: pytest AITuber/tests/test_approve_cli.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

from orchestrator.approve_cli import ApproveCLI, build_parser

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_proposal(intent: str) -> dict:
    return {
        "intent": intent,
        "cmd": "avatar_update",
        "gesture": f"{intent}_gesture",
        "priority": 0,
        "notes": f"Auto-generated for {intent}",
    }


def _write_staging(path: Path, proposals: list[dict]) -> None:
    path.write_text(
        yaml.dump(proposals, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )


# ── TC-M6-01: staging file does not exist ─────────────────────────────────


class TestMissingOrEmptyStaging:
    def test_nonexistent_staging_returns_zero(self, tmp_path: Path) -> None:
        """TC-M6-01: staging ファイルが存在しない → 終了コード 0、policy 未変更。"""
        policy = tmp_path / "bp.yml"
        policy.write_text("", encoding="utf-8")

        cli = ApproveCLI(
            staging_path=str(tmp_path / "no_staging.yml"),
            policy_path=str(policy),
            auto_approve=True,
        )
        result = cli.run()
        assert result == 0
        assert policy.read_text(encoding="utf-8") == ""

    def test_empty_staging_returns_zero(self, tmp_path: Path) -> None:
        """TC-M6-02: staging ファイルが空 → 終了コード 0、policy 未変更。"""
        staging = tmp_path / "staging.yml"
        staging.write_text("", encoding="utf-8")
        policy = tmp_path / "bp.yml"
        policy.write_text("", encoding="utf-8")

        cli = ApproveCLI(
            staging_path=str(staging),
            policy_path=str(policy),
            auto_approve=True,
        )
        result = cli.run()
        assert result == 0
        assert policy.read_text(encoding="utf-8") == ""


# ── TC-M6-03: auto-approve ────────────────────────────────────────────────


class TestAutoApprove:
    def test_auto_approve_appends_all_to_policy(self, tmp_path: Path) -> None:
        """TC-M6-03: --auto-approve → 全提案が policy に追記される。"""
        proposals = [_make_proposal("clap"), _make_proposal("wave")]
        staging = tmp_path / "staging.yml"
        _write_staging(staging, proposals)
        policy = tmp_path / "bp.yml"
        policy.write_text("", encoding="utf-8")

        cli = ApproveCLI(
            staging_path=str(staging),
            policy_path=str(policy),
            auto_approve=True,
        )
        result = cli.run()
        assert result == 0
        content = policy.read_text(encoding="utf-8")
        assert "clap" in content
        assert "wave" in content


# ── TC-M6-04: auto-reject ─────────────────────────────────────────────────


class TestAutoReject:
    def test_auto_reject_leaves_policy_unchanged(self, tmp_path: Path) -> None:
        """TC-M6-04: --auto-reject → 全提案が却下、policy 未変更。"""
        proposals = [_make_proposal("spin")]
        staging = tmp_path / "staging.yml"
        _write_staging(staging, proposals)
        policy = tmp_path / "bp.yml"
        policy.write_text("", encoding="utf-8")

        cli = ApproveCLI(
            staging_path=str(staging),
            policy_path=str(policy),
            auto_reject=True,
        )
        result = cli.run()
        assert result == 0
        assert policy.read_text(encoding="utf-8") == ""


# ── TC-M6-05: interactive y/n ─────────────────────────────────────────────


class TestInteractiveApproval:
    def test_partial_approval_via_input_fn(self, tmp_path: Path) -> None:
        """TC-M6-05: 対話型 y/n → y の提案のみ policy に追記される。"""
        proposals = [
            _make_proposal("intent_a"),
            _make_proposal("intent_b"),
            _make_proposal("intent_c"),
        ]
        staging = tmp_path / "staging.yml"
        _write_staging(staging, proposals)
        policy = tmp_path / "bp.yml"
        policy.write_text("", encoding="utf-8")

        # Approve first and third, reject second
        responses = iter(["y", "n", "y"])

        cli = ApproveCLI(
            staging_path=str(staging),
            policy_path=str(policy),
            input_fn=lambda _: next(responses),
        )
        result = cli.run()
        assert result == 0
        content = policy.read_text(encoding="utf-8")
        assert "intent_a" in content
        assert "intent_b" not in content
        assert "intent_c" in content


# ── TC-M6-06: staging cleared after run ───────────────────────────────────


class TestStagingCleared:
    def test_staging_file_is_cleared_after_auto_approve(self, tmp_path: Path) -> None:
        """TC-M6-06: 承認後 staging ファイルがクリアされる。"""
        proposals = [_make_proposal("nod_deep")]
        staging = tmp_path / "staging.yml"
        _write_staging(staging, proposals)
        policy = tmp_path / "bp.yml"
        policy.write_text("", encoding="utf-8")

        cli = ApproveCLI(
            staging_path=str(staging),
            policy_path=str(policy),
            auto_approve=True,
        )
        cli.run()

        # Staging should be cleared (empty list or empty file)
        content = staging.read_text(encoding="utf-8").strip()
        assert content == "" or content == "[]" or content == "null"


# ── TC-M6-07: CLI argparser ───────────────────────────────────────────────


class TestParser:
    def test_parser_defaults(self) -> None:
        """TC-M6-07: build_parser() のデフォルト値検証。"""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.auto_approve is False
        assert args.auto_reject is False

    def test_auto_approve_flag(self) -> None:
        """TC-M6-07b: --auto-approve フラグ。"""
        parser = build_parser()
        args = parser.parse_args(["--auto-approve"])
        assert args.auto_approve is True

    def test_auto_reject_flag(self) -> None:
        """TC-M6-07c: --auto-reject フラグ。"""
        parser = build_parser()
        args = parser.parse_args(["--auto-reject"])
        assert args.auto_reject is True

    def test_staging_and_policy_flags(self) -> None:
        """TC-M6-07d: --staging と --policy フラグ。"""
        parser = build_parser()
        args = parser.parse_args(["--staging", "s.yml", "--policy", "p.yml"])
        assert args.staging == "s.yml"
        assert args.policy == "p.yml"
