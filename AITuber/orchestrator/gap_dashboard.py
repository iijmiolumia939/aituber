"""GapDashboard: aggregate and visualise Capability Gap JSONL logs.

CLI usage:
    python -m orchestrator.gap_dashboard [options]
    python -m orchestrator.gap_dashboard --dir Logs/capability_gaps --top 5

SRS refs: FR-DASH-01, FR-DASH-02.
Resolves: TD-011 (priority_score 算出式の実装)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Cost weights by gap_category ──────────────────────────────────────────
# Lower weight = easier to implement = higher opportunity score.
# Values are relative implementation-cost estimates.
COST_WEIGHTS: dict[str, float] = {
    "missing_motion": 1.0,  # YAML 5 lines
    "missing_expression": 1.0,  # YAML 5 lines
    "missing_behavior": 1.5,  # WS protocol 10 lines
    "missing_integration": 3.0,  # new feature 50 lines
    "capability_limit": 5.0,  # C# + WS extension 100 lines
    "environment_limit": 4.0,  # Asset addition
    "unknown": 2.0,  # default
}

_DEFAULT_GAPS_DIR = "Logs/capability_gaps"


class GapDashboard:
    """Aggregate and surface the most important Capability Gaps.

    FR-DASH-01: load and parse JSONL files
    FR-DASH-02: compute priority_score and surface top-N gaps
    """

    # ── Loading ────────────────────────────────────────────────────────────

    def load_all_gaps(self, gaps_dir: str | None = None) -> list[dict]:
        """Read all *.jsonl files under *gaps_dir* and return a flat list of Gap dicts.

        FR-DASH-01
        Returns an empty list if the directory does not exist or contains no JSONL files.
        Skips non-JSON lines with a warning (tolerant parsing).
        """
        path = Path(gaps_dir or _DEFAULT_GAPS_DIR)
        if not path.exists() or not path.is_dir():
            logger.debug("Gap directory not found: %s – returning empty list.", path)
            return []

        all_gaps: list[dict] = []
        for jsonl_file in sorted(path.glob("*.jsonl")):
            for lineno, raw in enumerate(
                jsonl_file.read_text(encoding="utf-8").splitlines(), start=1
            ):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    all_gaps.append(json.loads(raw))
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Skipping invalid JSON in %s line %d: %s", jsonl_file.name, lineno, exc
                    )

        return all_gaps

    # ── Aggregation helpers ────────────────────────────────────────────────

    def aggregate_by_category(self, gaps: list[dict]) -> dict[str, int]:
        """Return a dict mapping gap_category → count.

        FR-DASH-01
        """
        counter: Counter[str] = Counter()
        for gap in gaps:
            cat = gap.get("gap_category", "unknown")
            counter[cat] += 1
        return dict(counter)

    def aggregate_by_intent(self, gaps: list[dict]) -> dict[str, int]:
        """Return a dict mapping intended_action.name → count.

        FR-DASH-01  Entries without intended_action are silently skipped.
        """
        counter: Counter[str] = Counter()
        for gap in gaps:
            action = gap.get("intended_action")
            if not isinstance(action, dict):
                continue
            name = action.get("name", "")
            if name:
                counter[name] += 1
        return dict(counter)

    def aggregate_by_stream(self, gaps: list[dict]) -> dict[str, int]:
        """Return a dict mapping stream_id → count.

        FR-DASH-01
        """
        counter: Counter[str] = Counter()
        for gap in gaps:
            stream = gap.get("stream_id", "unknown")
            counter[stream] += 1
        return dict(counter)

    # ── Priority scoring ───────────────────────────────────────────────────

    def compute_priority_scores(self, gaps: list[dict]) -> dict[str, float]:
        """Compute priority_score per unique intent.

        FR-DASH-02 / TD-011 解消

        Formula:
            score = (freq / total_gaps) × (1 / cost_weight[gap_category])

        where:
          - freq = number of occurrences of the intent
          - gap_category = most common category observed for that intent
          - cost_weight = COST_WEIGHTS[category] (default 2.0)

        Scores are guaranteed in [0.0, 1.0]:
          - freq / total_gaps ≤ 1.0 (by definition)
          - 1 / cost_weight ≤ 1.0 (minimum weight is 1.0)
        """
        total = len(gaps)
        if total == 0:
            return {}

        # Collect frequency and category counts per intent
        intent_freq: Counter[str] = Counter()
        intent_categories: defaultdict[str, Counter[str]] = defaultdict(Counter)

        for gap in gaps:
            action = gap.get("intended_action")
            if not isinstance(action, dict):
                continue
            name = action.get("name", "")
            if not name:
                continue
            cat = gap.get("gap_category", "unknown")
            intent_freq[name] += 1
            intent_categories[name][cat] += 1

        scores: dict[str, float] = {}
        for intent, freq in intent_freq.items():
            # Use the most common category for this intent
            dominant_cat = intent_categories[intent].most_common(1)[0][0]
            weight = COST_WEIGHTS.get(dominant_cat, COST_WEIGHTS["unknown"])
            scores[intent] = (freq / total) * (1.0 / weight)

        return scores

    # ── Top-N filtering ────────────────────────────────────────────────────

    def get_top_gaps(
        self,
        gaps: list[dict],
        *,
        top_n: int = 5,
        category: str | None = None,
    ) -> list[dict]:
        """Return the top-N unique-intent Gap entries sorted by priority_score.

        FR-DASH-02
        Args:
            gaps:     Full list of Gap dicts.
            top_n:    Maximum number of unique intents to return.
            category: If set, filter to this gap_category before ranking.
        Returns:
            List of one representative Gap dict per unique intent, sorted
            by priority_score descending, limited to top_n entries.
        """
        if not gaps:
            return []

        filtered = (
            gaps if category is None else [g for g in gaps if g.get("gap_category") == category]
        )
        if not filtered:
            return []

        scores = self.compute_priority_scores(filtered)

        # Keep one representative gap per intent (first occurrence)
        seen: set[str] = set()
        representatives: list[dict] = []
        for gap in filtered:
            action = gap.get("intended_action")
            if not isinstance(action, dict):
                continue
            name = action.get("name", "")
            if name and name not in seen:
                seen.add(name)
                # Attach computed score for sorting
                gap = dict(gap)
                gap["priority_score"] = scores.get(name, 0.0)
                representatives.append(gap)

        representatives.sort(key=lambda g: g.get("priority_score", 0.0), reverse=True)
        return representatives[:top_n]

    # ── Summary dict ──────────────────────────────────────────────────────

    def build_summary(self, gaps: list[dict], *, top_n: int = 5) -> dict:
        """Return a structured summary dict.

        FR-DASH-02
        Keys:
            total_gaps:  int
            by_category: dict[str, int]
            by_intent:   dict[str, int]
            by_intent_score: dict[str, float]
            top_gaps:    list[dict]  — top-N unique intents
            streams:     dict[str, int]
        """
        return {
            "total_gaps": len(gaps),
            "by_category": self.aggregate_by_category(gaps),
            "by_intent": self.aggregate_by_intent(gaps),
            "by_intent_score": self.compute_priority_scores(gaps),
            "top_gaps": self.get_top_gaps(gaps, top_n=top_n),
            "streams": self.aggregate_by_stream(gaps),
        }

    # ── Rich table rendering ───────────────────────────────────────────────

    def render_table(self, summary: dict) -> None:
        """Print a Rich-formatted summary table to stdout.

        Falls back to plain text if Rich is not installed.
        """
        try:
            from rich.console import Console

            self._render_rich(summary, Console())
        except ImportError:
            self._render_plain(summary)

    def _render_rich(self, summary: dict, console: object) -> None:  # pragma: no cover
        from rich.table import Table

        console.print(f"\n[bold cyan]Gap Dashboard[/bold cyan]  total={summary['total_gaps']}\n")

        # Category table
        cat_table = Table(title="By Category", show_lines=True)
        cat_table.add_column("Category", style="yellow")
        cat_table.add_column("Count", justify="right")
        for cat, count in sorted(summary["by_category"].items(), key=lambda x: -x[1]):
            cat_table.add_row(cat, str(count))
        console.print(cat_table)

        # Top gaps table
        top_table = Table(title="Top Gaps (by priority_score)", show_lines=True)
        top_table.add_column("Rank", justify="right")
        top_table.add_column("Intent")
        top_table.add_column("Category", style="yellow")
        top_table.add_column("Score", justify="right")
        for rank, gap in enumerate(summary["top_gaps"], start=1):
            name = gap.get("intended_action", {}).get("name", "?")
            cat = gap.get("gap_category", "?")
            score = gap.get("priority_score", 0.0)
            top_table.add_row(str(rank), name, cat, f"{score:.3f}")
        console.print(top_table)

    def _render_plain(self, summary: dict) -> None:  # pragma: no cover
        print(f"\n=== Gap Dashboard (total={summary['total_gaps']}) ===")
        print("\n[By Category]")
        for cat, count in sorted(summary["by_category"].items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")
        print("\n[Top Gaps]")
        for rank, gap in enumerate(summary["top_gaps"], start=1):
            name = gap.get("intended_action", {}).get("name", "?")
            cat = gap.get("gap_category", "?")
            score = gap.get("priority_score", 0.0)
            print(f"  {rank}. {name} [{cat}] score={score:.3f}")


# ── CLI entrypoint ─────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gap_dashboard",
        description="Aggregate and display Capability Gap statistics.",
    )
    parser.add_argument(
        "--dir",
        default=_DEFAULT_GAPS_DIR,
        help=f"Path to gap JSONL directory (default: {_DEFAULT_GAPS_DIR})",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        metavar="N",
        help="Show top N gaps by priority_score (default: 5)",
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Filter by gap_category",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output summary as JSON instead of Rich table",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI main function. Returns exit code (0 = success)."""
    args = _parse_args(argv)

    dashboard = GapDashboard()
    gaps = dashboard.load_all_gaps(args.dir)

    if not gaps:
        print(f"No gap logs found in: {args.dir}", file=sys.stderr)
        return 0

    summary = dashboard.build_summary(gaps, top_n=args.top)

    if args.category:
        summary["top_gaps"] = dashboard.get_top_gaps(gaps, top_n=args.top, category=args.category)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        dashboard.render_table(summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
