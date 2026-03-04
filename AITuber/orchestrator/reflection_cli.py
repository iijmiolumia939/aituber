"""reflection_cli: ReflectionRunner end-to-end CLI wiring.

Phase-1 Growth Loop (direct write):
  GapDashboard.load_all_gaps()
    → GapDashboard.get_top_gaps()
    → ReflectionRunner(backend).generate_proposals()
    → ProposalValidator.validate()
    → PolicyUpdater.append_entries()  (skipped when --dry-run)

Phase-2 staging (human approval flow):
  Same pipeline, but with --output staging.yml:
    → valid proposals written to staging file (NOT to behavior_policy.yml)
    → approve_cli reads staging file and lets human approve/reject

Usage:
    python -m orchestrator.reflection_cli [options]
    python -m orchestrator.reflection_cli --dry-run
    python -m orchestrator.reflection_cli --output proposals_staging.yml
    python -m orchestrator.reflection_cli --top-n 3 --model gpt-4o-mini

SRS refs: FR-REFL-01, FR-REFL-02, FR-REFL-03, FR-REFL-04, FR-APPR-01.
Resolves: TD-010 (ReflectionRunner backend wiring).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from orchestrator.gap_dashboard import _DEFAULT_GAPS_DIR, GapDashboard
from orchestrator.policy_updater import PolicyUpdater
from orchestrator.proposal_validator import ProposalValidator, ValidationStatus
from orchestrator.reflection_runner import ReflectionRunner

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from orchestrator.llm_client import LLMBackend

logger = logging.getLogger(__name__)

_DEFAULT_POLICY = "Assets/StreamingAssets/behavior_policy.yml"


# ── CLI ────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Return the ArgumentParser for reflection_cli.

    Flags
    -----
    --gaps-dir   Directory containing *.jsonl gap log files.
                 (default: Logs/capability_gaps)
    --policy     Path to behavior_policy.yml.
                 (default: Assets/StreamingAssets/behavior_policy.yml)
    --top-n      Maximum unique intents to send to the LLM. (default: 5)
    --dry-run    If set, skip the PolicyUpdater write step.
    --model      OpenAI model to use (passed via LLMConfig).  (default: gpt-4o-mini)
    """
    p = argparse.ArgumentParser(
        prog="reflection_cli",
        description="Run the ReflectionRunner Growth Loop end-to-end.",
    )
    p.add_argument(
        "--gaps-dir",
        default=_DEFAULT_GAPS_DIR,
        metavar="DIR",
        help="Directory containing capability gap JSONL files.",
    )
    p.add_argument(
        "--policy",
        default=_DEFAULT_POLICY,
        metavar="YAML",
        help="Path to behavior_policy.yml.",
    )
    p.add_argument(
        "--top-n",
        dest="top_n",
        type=int,
        default=5,
        metavar="N",
        help="Maximum unique intents to submit to the LLM (default: 5).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run the pipeline but do NOT write to behavior_policy.yml.",
    )
    p.add_argument(
        "--output",
        default=None,
        metavar="YAML",
        help=(
            "Write validated proposals to this staging YAML file instead of appending "
            "directly to behavior_policy.yml.  Used for Phase-2 human approval flow "
            "(approve_cli). Mutually exclusive with --dry-run."
        ),
    )
    p.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model name (default: gpt-4o-mini).",
    )
    return p


# ── Core pipeline ──────────────────────────────────────────────────────────


class ReflectionCLI:
    """Encapsulates the ReflectionRunner Growth Loop pipeline.

    Parameters
    ----------
    gaps_dir:     Path to capability gap JSONL directory.
    policy_path:  Path to behavior_policy.yml.
    top_n:        Maximum unique intents to submit to the LLM.
    dry_run:      When True, skip the PolicyUpdater write step.
    backend:      An LLMBackend instance.  When None, a real OpenAIBackend
                  is constructed from environment variables at run time.
    output_path:  When set, write valid proposals to this staging YAML file
                  instead of appending to behavior_policy.yml (Phase-2 flow).
    """

    def __init__(
        self,
        gaps_dir: str,
        policy_path: str,
        top_n: int = 5,
        dry_run: bool = False,
        backend: LLMBackend | None = None,
        output_path: str | None = None,
    ) -> None:
        self.gaps_dir = gaps_dir
        self.policy_path = policy_path
        self.top_n = top_n
        self.dry_run = dry_run
        self._backend = backend
        self.output_path = output_path

    # ── Step 1: load gaps ─────────────────────────────────────────────────

    def _load_top_gaps(self) -> list[dict]:
        dashboard = GapDashboard()
        all_gaps = dashboard.load_all_gaps(self.gaps_dir)
        if not all_gaps:
            logger.info("No capability gaps found in %s.", self.gaps_dir)
            return []
        return dashboard.get_top_gaps(all_gaps, top_n=self.top_n)

    # ── Step 2: generate proposals ────────────────────────────────────────

    async def _generate_proposals(self, top_gaps: list[dict]) -> list[dict]:
        runner = ReflectionRunner(backend=self._backend)
        try:
            return await runner.generate_proposals(top_gaps)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("ReflectionRunner raised an exception: %s", exc)
            return []

    # ── Step 3: validate proposals ────────────────────────────────────────

    def _validate(self, proposals: list[dict]) -> list[dict]:
        existing = PolicyUpdater().load_policy(self.policy_path)
        validator = ProposalValidator(existing_policy=existing)
        valid: list[dict] = []
        for proposal in proposals:
            result = validator.validate(proposal)
            if result.status == ValidationStatus.VALID:
                valid.append(proposal)
            else:
                logger.debug(
                    "Rejected proposal %s: [%s] %s",
                    proposal.get("intent", "?"),
                    result.status.value,
                    result.reason,
                )
        return valid

    # ── Step 4a: write staging file (Phase-2 flow) ────────────────────────

    def _write_staging(self, valid_proposals: list[dict]) -> None:
        """Write valid proposals to a staging YAML file for human review.

        FR-APPR-01
        """
        assert yaml is not None, "PyYAML is required for --output staging."  # noqa: S101
        path = Path(self.output_path)  # type: ignore[arg-type]
        path.write_text(
            yaml.dump(valid_proposals, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        print(
            f"Staged {len(valid_proposals)} proposal"
            f"{'s' if len(valid_proposals) != 1 else ''} to {self.output_path}. "
            "Run approve_cli to review."
        )

    # ── Step 4b: write policy ─────────────────────────────────────────────
    def _write(self, valid_proposals: list[dict]) -> None:
        n = PolicyUpdater().append_entries(self.policy_path, valid_proposals)
        print(f"Appended {n} entr{'y' if n == 1 else 'ies'} to {self.policy_path}")

    # ── Public entry point ────────────────────────────────────────────────

    async def run(self) -> int:
        """Execute the full pipeline. Returns exit code (always 0).

        FR-REFL-01: Loads gaps via GapDashboard.load_all_gaps.
        FR-REFL-02: Selects top-N via GapDashboard.get_top_gaps.
        FR-REFL-03: Generates + validates proposals.
        FR-REFL-04: Appends validated proposals (unless dry_run).
        """
        # Step 1
        top_gaps = self._load_top_gaps()
        if not top_gaps:
            return 0

        # Step 2
        proposals = await self._generate_proposals(top_gaps)
        logger.info("LLM generated %d raw proposals.", len(proposals))
        if not proposals:
            return 0

        # Step 3
        valid = self._validate(proposals)
        logger.info("%d / %d proposals passed validation.", len(valid), len(proposals))
        if not valid:
            return 0

        # Step 4
        if self.output_path:
            # Phase-2: stage for human approval (do NOT write policy directly)
            self._write_staging(valid)
        elif self.dry_run:
            print(
                f"[dry-run] Would append {len(valid)} entr"
                f"{'y' if len(valid) == 1 else 'ies'} to {self.policy_path}."
            )
        else:
            self._write(valid)

        return 0


# ── main ───────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments, build a real OpenAIBackend, and run the pipeline.

    This is the only place an OpenAIBackend is instantiated — keeping the rest
    of ReflectionCLI backend-agnostic (and easily testable with mocks).
    """
    from orchestrator.config import LLMConfig  # local import to avoid circular
    from orchestrator.llm_client import OpenAIBackend  # local import

    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Allow --model to override the config default.
    config = LLMConfig()
    config.model = args.model

    backend = OpenAIBackend(config)

    cli = ReflectionCLI(
        gaps_dir=args.gaps_dir,
        policy_path=args.policy,
        top_n=args.top_n,
        dry_run=args.dry_run,
        backend=backend,
        output_path=args.output,
    )
    return asyncio.run(cli.run())


if __name__ == "__main__":
    sys.exit(main())
