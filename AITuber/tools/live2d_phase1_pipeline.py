"""Popica Live2D Phase 1 の実行パイプライン。

処理:
1) PSDと台帳レイヤー名の一致検証
2) 一致レイヤーのPNG書き出し
3) 台帳進捗サマリ出力
4) pipeline_report.json 保存

例:
  python tools/live2d_phase1_pipeline.py --psd path/to/popica.psd
  python tools/live2d_phase1_pipeline.py --psd path/to/popica.psd --strict
  python tools/live2d_phase1_pipeline.py --psd path/to/popica.psd --validate-only
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from live2d_phase1_status import load_rows, summarize
from live2d_psd_export import (
    export_layers,
    load_psd,
    print_validation_report,
    read_names_from_csv_filtered,
    validate_layers,
)
from live2d_phase1_sync_status import (
    apply_changes,
    compute_changes,
    save_rows,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Popica Live2D Phase 1 pipeline")
    parser.add_argument("--psd", required=True, help="PSD file path")
    parser.add_argument(
        "--csv",
        default="config/live2d/popica/phase1_layers.csv",
        help="Layer tracker CSV path",
    )
    parser.add_argument(
        "--out-dir",
        default="output/live2d/popica/phase1",
        help="Export output directory",
    )
    parser.add_argument(
        "--batch",
        nargs="*",
        help="Optional batch filter (e.g. B1 B2)",
    )
    parser.add_argument(
        "--status",
        nargs="*",
        help="Optional status filter (e.g. Todo InProgress)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when validation has missing layers",
    )
    parser.add_argument(
        "--trim",
        action="store_true",
        help="Export trimmed images instead of full-canvas",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run validation and status summary without exporting images",
    )
    parser.add_argument(
        "--sync-status",
        action="store_true",
        help="Compute tracker status sync proposal from export result",
    )
    parser.add_argument(
        "--apply-sync",
        action="store_true",
        help="Apply tracker status sync to CSV (implies --sync-status)",
    )
    parser.add_argument(
        "--reset-inprogress",
        action="store_true",
        help="When syncing, reset non-exported InProgress layers to Todo",
    )
    return parser.parse_args()


def resolve_path(project_root: Path, value: str) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    return (project_root / p).resolve()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]

    psd_path = resolve_path(project_root, args.psd)
    csv_path = resolve_path(project_root, args.csv)
    out_dir = resolve_path(project_root, args.out_dir)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    out_dir.mkdir(parents=True, exist_ok=True)

    psd = load_psd(psd_path)
    batch_filter = {b.strip() for b in args.batch if b.strip()} if args.batch else None
    status_filter = {s.strip().lower() for s in args.status if s.strip()} if args.status else None
    target_names = set(read_names_from_csv_filtered(csv_path, batch_filter, status_filter))
    if not target_names:
        raise RuntimeError("CSVにlayer_nameが見つかりません。")

    validation = validate_layers(psd, target_names)
    print("=== Validation ===")
    print_validation_report(validation)

    exported_summary: dict[str, object] | None = None
    sync_summary: dict[str, object] | None = None
    if validation["missing_count"] > 0 and args.strict:
        raise SystemExit(2)

    if not args.validate_only:
        export_result = export_layers(psd, out_dir, target_names, use_full_canvas=not args.trim)
        export_report_path = out_dir / "export_report.json"
        with export_report_path.open("w", encoding="utf-8") as f:
            json.dump(export_result, f, ensure_ascii=False, indent=2)

        exported_summary = {
            "exported_count": len(export_result["exported"]),
            "missing_after_export": len(export_result["missing"]),
            "missing_layers": export_result["missing"],
            "export_report_path": str(export_report_path),
        }
        print("=== Export ===")
        print(f"- exported={exported_summary['exported_count']}")
        print(f"- missing={exported_summary['missing_after_export']}")
        print(f"- export_report={exported_summary['export_report_path']}")

        do_sync = args.sync_status or args.apply_sync
        if do_sync:
            rows_for_sync = load_rows(csv_path)
            exported_names = {
                str(item.get("layer_name", "")).strip()
                for item in export_result.get("exported", [])
                if str(item.get("layer_name", "")).strip()
            }
            changes = compute_changes(rows_for_sync, exported_names, args.reset_inprogress)

            sync_summary = {
                "changes": len(changes),
                "applied": bool(args.apply_sync),
                "reset_inprogress": bool(args.reset_inprogress),
                "preview": [
                    {
                        "layer_name": c.layer_name,
                        "old_status": c.old_status,
                        "new_status": c.new_status,
                        "reason": c.reason,
                    }
                    for c in changes[:20]
                ],
            }

            print("=== Sync Status ===")
            print(f"- changes={sync_summary['changes']}")
            print(f"- applied={sync_summary['applied']}")

            if args.apply_sync and changes:
                csv_rows, fieldnames = load_rows(csv_path)
                apply_changes(csv_rows, changes)
                save_rows(csv_path, csv_rows, fieldnames)
                print(f"- updated_csv={csv_path}")

    elif args.sync_status or args.apply_sync:
        print("=== Sync Status ===")
        print("- skipped: validate-only mode does not produce export result")

    rows = load_rows(csv_path)
    status_text = summarize(rows)
    print("=== Tracker Status ===")
    print(status_text)

    report = {
        "psd_path": str(psd_path),
        "csv_path": str(csv_path),
        "filters": {
            "batch": sorted(batch_filter) if batch_filter else None,
            "status": sorted(status_filter) if status_filter else None,
        },
        "validation": validation,
        "export": exported_summary,
        "sync": sync_summary,
        "status_summary": status_text,
    }

    report_path = out_dir / "pipeline_report.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("=== Output ===")
    print(f"- report={report_path}")


if __name__ == "__main__":
    main()
