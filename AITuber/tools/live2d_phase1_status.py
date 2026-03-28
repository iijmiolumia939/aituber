"""Popica Live2D Phase 1 進捗集計ツール。

使い方:
  python tools/live2d_phase1_status.py
  python tools/live2d_phase1_status.py --csv config/live2d/popica/phase1_layers.csv

出力:
  - 全体進捗
  - バッチ別進捗
  - 依存を満たした次アクション候補
  - QCゲート別の未完了件数
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LayerRow:
    layer_name: str
    batch: str
    dependency: str
    qc_gate: str
    status: str


def load_rows(csv_path: Path) -> list[LayerRow]:
    rows: list[LayerRow] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                LayerRow(
                    layer_name=(row.get("layer_name") or "").strip(),
                    batch=(row.get("batch") or "").strip(),
                    dependency=(row.get("dependency") or "").strip(),
                    qc_gate=(row.get("qc_gate") or "").strip(),
                    status=(row.get("status") or "").strip(),
                )
            )
    return rows


def pct(done: int, total: int) -> float:
    if total == 0:
        return 0.0
    return done * 100.0 / total


def is_done(status: str) -> bool:
    return status.lower() == "done"


def is_in_progress(status: str) -> bool:
    return status.lower() == "inprogress"


def find_ready_todo(rows: list[LayerRow]) -> list[LayerRow]:
    status_map = {r.layer_name: r.status for r in rows}
    ready: list[LayerRow] = []
    for r in rows:
        if r.status.lower() != "todo":
            continue
        dep = r.dependency
        if dep in ("", "None", "none"):
            ready.append(r)
            continue
        if is_done(status_map.get(dep, "")):
            ready.append(r)
    return ready


def summarize(rows: list[LayerRow]) -> str:
    total = len(rows)
    done = sum(1 for r in rows if is_done(r.status))
    in_progress = sum(1 for r in rows if is_in_progress(r.status))
    todo = total - done - in_progress

    lines: list[str] = []
    lines.append("=== Popica Live2D Phase 1 Status ===")
    lines.append(f"Total: {total}  Done: {done}  InProgress: {in_progress}  Todo: {todo}")
    lines.append(f"Progress: {pct(done, total):.1f}%")
    lines.append("")

    in_progress_rows = [r for r in rows if is_in_progress(r.status)]
    lines.append("[InProgress]")
    if in_progress_rows:
        for r in in_progress_rows:
            lines.append(f"- {r.layer_name} ({r.batch}, gate {r.qc_gate})")
    else:
        lines.append("- none")
    lines.append("")

    by_batch: dict[str, list[LayerRow]] = defaultdict(list)
    for r in rows:
        by_batch[r.batch].append(r)

    lines.append("[Batch Summary]")
    for batch in sorted(by_batch.keys()):
        batch_rows = by_batch[batch]
        b_total = len(batch_rows)
        b_done = sum(1 for r in batch_rows if is_done(r.status))
        b_in = sum(1 for r in batch_rows if is_in_progress(r.status))
        b_todo = b_total - b_done - b_in
        lines.append(
            f"- {batch}: {b_done}/{b_total} done ({pct(b_done, b_total):.1f}%), in-progress {b_in}, todo {b_todo}"
        )
    lines.append("")

    ready = find_ready_todo(rows)
    lines.append("[Ready Todo (dependency satisfied)]")
    if ready:
        for r in ready:
            lines.append(f"- {r.layer_name} ({r.batch}, gate {r.qc_gate})")
    else:
        lines.append("- none")
        if in_progress_rows:
            lines.append("- tip: finish in-progress layers first to unlock dependent todo layers")
    lines.append("")

    gate_counter = Counter(r.qc_gate for r in rows if not is_done(r.status))
    lines.append("[Gate Remaining]")
    for gate in sorted(gate_counter.keys()):
        lines.append(f"- {gate}: {gate_counter[gate]} layers not done")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Popica Live2D Phase 1 status")
    parser.add_argument(
        "--csv",
        type=str,
        default="config/live2d/popica/phase1_layers.csv",
        help="Layer tracker CSV path (relative to AITuber/)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    csv_path = project_root / args.csv

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    rows = load_rows(csv_path)
    if not rows:
        print("No rows found.")
        return

    print(summarize(rows))


if __name__ == "__main__":
    main()
