"""Popica Phase 1 のレイヤー台帳 status を書き出し結果から同期するツール。

入力:
- export_report.json (tools/live2d_psd_export.py の出力)
- phase1_layers.csv

動作:
- デフォルトは dry-run（変更内容のみ表示）
- --apply を付けると CSV を更新
- 書き出し済み layer_name を Done に更新
- 未書き出しで InProgress のものは Todo に戻す（--reset-inprogress あり）

例:
  python tools/live2d_phase1_sync_status.py
  python tools/live2d_phase1_sync_status.py --apply
  python tools/live2d_phase1_sync_status.py --apply --reset-inprogress
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Change:
    layer_name: str
    old_status: str
    new_status: str
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync phase1 layer statuses from export report")
    parser.add_argument(
        "--csv",
        default="config/live2d/popica/phase1_layers.csv",
        help="Layer tracker CSV path",
    )
    parser.add_argument(
        "--report",
        default="output/live2d/popica/phase1/export_report.json",
        help="Export report JSON path",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to CSV (default: dry-run)",
    )
    parser.add_argument(
        "--reset-inprogress",
        action="store_true",
        help="Set non-exported InProgress layers back to Todo",
    )
    return parser.parse_args()


def resolve_path(project_root: Path, raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return (project_root / p).resolve()


def load_exported_layer_names(report_path: Path) -> set[str]:
    with report_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    exported = payload.get("exported", [])
    names: set[str] = set()
    for item in exported:
        name = str(item.get("layer_name", "")).strip()
        if name:
            names.add(name)
    return names


def load_rows(csv_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [dict(row) for row in reader]
        fieldnames = reader.fieldnames or []
    return rows, fieldnames


def compute_changes(
    rows: list[dict[str, str]],
    exported_names: set[str],
    reset_inprogress: bool,
) -> list[Change]:
    changes: list[Change] = []

    for row in rows:
        layer = (row.get("layer_name") or "").strip()
        status = (row.get("status") or "").strip()
        if not layer:
            continue

        if layer in exported_names and status.lower() != "done":
            changes.append(
                Change(
                    layer_name=layer,
                    old_status=status,
                    new_status="Done",
                    reason="exported",
                )
            )
            continue

        if reset_inprogress and layer not in exported_names and status.lower() == "inprogress":
            changes.append(
                Change(
                    layer_name=layer,
                    old_status=status,
                    new_status="Todo",
                    reason="not exported",
                )
            )

    return changes


def apply_changes(rows: list[dict[str, str]], changes: list[Change]) -> None:
    by_name = {c.layer_name: c for c in changes}
    for row in rows:
        layer = (row.get("layer_name") or "").strip()
        change = by_name.get(layer)
        if change is None:
            continue
        row["status"] = change.new_status


def save_rows(csv_path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_changes(changes: list[Change], apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"mode={mode}")
    print(f"changes={len(changes)}")
    if not changes:
        return

    for c in changes:
        print(f"- {c.layer_name}: {c.old_status} -> {c.new_status} ({c.reason})")


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]

    csv_path = resolve_path(project_root, args.csv)
    report_path = resolve_path(project_root, args.report)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    exported_names = load_exported_layer_names(report_path)
    rows, fieldnames = load_rows(csv_path)
    changes = compute_changes(rows, exported_names, args.reset_inprogress)

    print_changes(changes, args.apply)

    if args.apply and changes:
        apply_changes(rows, changes)
        save_rows(csv_path, rows, fieldnames)
        print(f"updated_csv={csv_path}")


if __name__ == "__main__":
    main()
