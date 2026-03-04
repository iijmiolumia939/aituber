"""approve_cli: Human approval flow for LLM-generated BehaviorPolicy proposals.

Phase-2 Growth Loop:
  proposals_staging.yml (written by reflection_cli --output)
    → interactive y/n review (or --auto-approve for CI)
    → approved proposals appended to behavior_policy.yml
    → staging file cleared

Usage:
    python -m orchestrator.approve_cli [options]
    python -m orchestrator.approve_cli --auto-approve          # CI mode
    python -m orchestrator.approve_cli --staging my_staging.yml

SRS refs: FR-APPR-01, FR-APPR-02, FR-APPR-03.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

import yaml

from orchestrator.policy_updater import PolicyUpdater

logger = logging.getLogger(__name__)

_DEFAULT_STAGING = "proposals_staging.yml"
_DEFAULT_POLICY = "Assets/StreamingAssets/behavior_policy.yml"


# ── CLI ────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Return the ArgumentParser for approve_cli.

    Flags
    -----
    --staging YAML     Path to proposals staging YAML file.
                       (default: proposals_staging.yml)
    --policy YAML      Path to behavior_policy.yml.
                       (default: Assets/StreamingAssets/behavior_policy.yml)
    --auto-approve     Approve all proposals without prompting (CI/test mode).
    --auto-reject      Reject all proposals without prompting (test mode).
    """
    p = argparse.ArgumentParser(
        prog="approve_cli",
        description="Interactively review and approve LLM-generated BehaviorPolicy proposals.",
    )
    p.add_argument(
        "--staging",
        default=_DEFAULT_STAGING,
        metavar="YAML",
        help="Path to the proposals staging YAML file (written by reflection_cli --output).",
    )
    p.add_argument(
        "--policy",
        default=_DEFAULT_POLICY,
        metavar="YAML",
        help="Path to behavior_policy.yml.",
    )
    p.add_argument(
        "--auto-approve",
        dest="auto_approve",
        action="store_true",
        default=False,
        help="Approve all proposals automatically (non-interactive; for CI).",
    )
    p.add_argument(
        "--auto-reject",
        dest="auto_reject",
        action="store_true",
        default=False,
        help="Reject all proposals automatically (for testing).",
    )
    return p


# ── Core logic ─────────────────────────────────────────────────────────────


class ApproveCLI:
    """Interactive human-approval flow for staged BehaviorPolicy proposals.

    Parameters
    ----------
    staging_path:   Path to the proposals staging YAML.
    policy_path:    Path to behavior_policy.yml.
    auto_approve:   When True, approve all proposals without prompting.
    auto_reject:    When True, reject all proposals without prompting.
    input_fn:       Callable used to read user input.  Defaults to the
                    built-in ``input()``.  Inject a custom callable in tests
                    to avoid touching stdin.

    FR-APPR-01: Load proposals from staging file.
    FR-APPR-02: Prompt user to approve/reject each proposal interactively.
    FR-APPR-03: --auto-approve for non-interactive CI mode.
    """

    def __init__(
        self,
        staging_path: str,
        policy_path: str,
        auto_approve: bool = False,
        auto_reject: bool = False,
        input_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.staging_path = Path(staging_path)
        self.policy_path = policy_path
        self.auto_approve = auto_approve
        self.auto_reject = auto_reject
        self._input = input_fn or input

    # ── Step 1: load staging ──────────────────────────────────────────────

    def _load_staging(self) -> list[dict]:
        """Read and parse the staging YAML file.

        Returns an empty list when the file is missing or empty.
        FR-APPR-01
        """
        if not self.staging_path.exists():
            logger.info("Staging file not found: %s", self.staging_path)
            return []
        text = self.staging_path.read_text(encoding="utf-8").strip()
        if not text:
            logger.info("Staging file is empty: %s", self.staging_path)
            return []
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            logger.warning("Could not parse staging file: %s", exc)
            return []
        if not isinstance(data, list):
            logger.warning("Staging file is not a YAML list; skipping.")
            return []
        return [p for p in data if isinstance(p, dict)]

    # ── Step 2: review proposals ──────────────────────────────────────────

    def _review(self, proposals: list[dict]) -> list[dict]:
        """Return the subset of proposals approved by the user.

        FR-APPR-02: interactive y/n per proposal.
        FR-APPR-03: skip prompts when auto_approve/auto_reject is set.
        """
        if self.auto_approve:
            logger.info("Auto-approving all %d proposals.", len(proposals))
            return list(proposals)
        if self.auto_reject:
            logger.info("Auto-rejecting all %d proposals.", len(proposals))
            return []

        approved: list[dict] = []
        for i, proposal in enumerate(proposals, start=1):
            intent = proposal.get("intent", "?")
            gesture = proposal.get("gesture", "")
            notes = proposal.get("notes", "")
            print(f"\n[{i}/{len(proposals)}] intent={intent!r}  gesture={gesture!r}")
            if notes:
                print(f"  notes: {notes}")
            raw = self._input("  Approve? [y/N] ").strip().lower()
            if raw == "y":
                approved.append(proposal)
            elif raw == "q":
                print("Review aborted.")
                break
        return approved

    # ── Step 3: write approved + clear staging ────────────────────────────

    def _commit(self, approved: list[dict]) -> int:
        """Append approved proposals to policy and clear the staging file.

        Returns the number of entries actually appended.
        """
        n = 0
        if approved:
            n = PolicyUpdater().append_entries(self.policy_path, approved)
            print(f"Appended {n} entr{'y' if n == 1 else 'ies'} to {self.policy_path}.")
        # Always clear staging after a successful review run.
        self.staging_path.write_text("", encoding="utf-8")
        return n

    # ── Public entry point ────────────────────────────────────────────────

    def run(self) -> int:
        """Execute the approval flow.  Returns exit code (always 0).

        FR-APPR-01 → FR-APPR-02 → FR-APPR-03
        """
        proposals = self._load_staging()
        if not proposals:
            return 0

        approved = self._review(proposals)

        rejected = len(proposals) - len(approved)
        logger.info(
            "Review complete: %d approved, %d rejected.",
            len(approved),
            rejected,
        )

        self._commit(approved)
        return 0


# ── main ───────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and run the approval flow."""
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cli = ApproveCLI(
        staging_path=args.staging,
        policy_path=args.policy,
        auto_approve=args.auto_approve,
        auto_reject=args.auto_reject,
    )
    return cli.run()


if __name__ == "__main__":
    sys.exit(main())
