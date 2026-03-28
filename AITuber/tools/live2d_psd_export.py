"""Live2D向けにPSDレイヤーを書き出す補助ツール。

機能:
- PSDレイヤー一覧の表示
- CSVのlayer_name列に一致するレイヤーだけを書き出し
- フルキャンバス座標を維持したPNGとして出力

例:
  python tools/live2d_psd_export.py --psd path/to/model.psd --list
  python tools/live2d_psd_export.py --psd path/to/model.psd --csv config/live2d/popica/phase1_layers.csv --out-dir output/live2d/popica
  python tools/live2d_psd_export.py --psd path/to/model.psd --names Face_Base Eye_White_L_01
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LayerInfo:
    name: str
    path: str
    left: int
    top: int
    right: int
    bottom: int


def sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "layer"


def load_psd(psd_path: Path):
    try:
        from psd_tools import PSDImage
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "psd-tools が未インストールです。pip install psd-tools Pillow を実行してください。"
        ) from exc
    return PSDImage.open(psd_path)


def iter_leaf_layers(psd):
    for layer in psd.descendants():
        if layer.is_group():
            continue
        if getattr(layer, "is_empty", lambda: False)():
            continue
        yield layer


def build_layer_path(layer) -> str:
    names = []
    current = layer
    while current is not None and current.parent is not None:
        names.append(current.name or "Unnamed")
        current = current.parent
    return "/".join(reversed(names))


def collect_layer_infos(psd) -> list[LayerInfo]:
    infos: list[LayerInfo] = []
    for layer in iter_leaf_layers(psd):
        infos.append(
            LayerInfo(
                name=layer.name or "Unnamed",
                path=build_layer_path(layer),
                left=int(layer.left),
                top=int(layer.top),
                right=int(layer.right),
                bottom=int(layer.bottom),
            )
        )
    return infos


def read_names_from_csv(csv_path: Path) -> list[str]:
    names: list[str] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("layer_name") or "").strip()
            if name:
                names.append(name)
    return names


def read_names_from_csv_filtered(
    csv_path: Path,
    batch_filter: set[str] | None,
    status_filter: set[str] | None,
) -> list[str]:
    names: list[str] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("layer_name") or "").strip()
            batch = (row.get("batch") or "").strip()
            status = (row.get("status") or "").strip().lower()

            if not name:
                continue
            if batch_filter is not None and batch not in batch_filter:
                continue
            if status_filter is not None and status not in status_filter:
                continue
            names.append(name)
    return names


def write_layer_png(psd, layer, out_path: Path, use_full_canvas: bool) -> dict:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Pillow が未インストールです。pip install Pillow を実行してください。"
        ) from exc

    rendered = layer.composite()
    if rendered is None:
        return {
            "file": str(out_path),
            "status": "skipped",
            "reason": "composite returned None",
        }

    if use_full_canvas:
        canvas = Image.new("RGBA", psd.size, (0, 0, 0, 0))
        canvas.paste(rendered, (int(layer.left), int(layer.top)), rendered)
        canvas.save(out_path)
    else:
        rendered.save(out_path)

    return {
        "file": str(out_path),
        "status": "ok",
        "left": int(layer.left),
        "top": int(layer.top),
        "right": int(layer.right),
        "bottom": int(layer.bottom),
    }


def export_layers(psd, out_dir: Path, target_names: set[str], use_full_canvas: bool) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "exported": [],
        "missing": sorted(target_names),
    }

    for layer in iter_leaf_layers(psd):
        layer_name = (layer.name or "").strip()
        if layer_name not in target_names:
            continue

        safe_name = sanitize_filename(layer_name)
        out_path = out_dir / f"{safe_name}.png"

        # 同名レイヤーが存在するケースに備えて連番で回避
        suffix = 1
        while out_path.exists():
            out_path = out_dir / f"{safe_name}_{suffix:02d}.png"
            suffix += 1

        exported = write_layer_png(psd, layer, out_path, use_full_canvas)
        exported["layer_name"] = layer_name
        exported["layer_path"] = build_layer_path(layer)
        result["exported"].append(exported)

        if layer_name in result["missing"]:
            result["missing"].remove(layer_name)

    return result


def validate_layers(psd, target_names: set[str]) -> dict:
    psd_names = sorted(
        {(layer.name or "").strip() for layer in iter_leaf_layers(psd) if layer.name}
    )
    psd_name_set = set(psd_names)
    expected = sorted(target_names)

    matched = [name for name in expected if name in psd_name_set]
    missing = [name for name in expected if name not in psd_name_set]

    suggestions: dict[str, list[str]] = {}
    for name in missing:
        close = difflib.get_close_matches(name, psd_names, n=3, cutoff=0.55)
        if close:
            suggestions[name] = close

    return {
        "expected_count": len(expected),
        "psd_leaf_count": len(psd_names),
        "matched_count": len(matched),
        "missing_count": len(missing),
        "matched": matched,
        "missing": missing,
        "suggestions": suggestions,
    }


def print_validation_report(report: dict) -> None:
    print("validation_summary:")
    print(f"- expected={report['expected_count']}")
    print(f"- psd_leaf={report['psd_leaf_count']}")
    print(f"- matched={report['matched_count']}")
    print(f"- missing={report['missing_count']}")

    if report["missing"]:
        print("missing_layers:")
        for name in report["missing"]:
            print(f"- {name}")
            if name in report["suggestions"]:
                print(f"  suggestions: {', '.join(report['suggestions'][name])}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live2D PSD layer exporter")
    parser.add_argument("--psd", required=True, help="PSD file path")
    parser.add_argument(
        "--out-dir",
        default="output/live2d/popica/phase1",
        help="Output directory (default: output/live2d/popica/phase1)",
    )
    parser.add_argument(
        "--csv",
        default="config/live2d/popica/phase1_layers.csv",
        help="CSV path containing layer_name column",
    )
    parser.add_argument(
        "--names",
        nargs="*",
        help="Optional explicit layer names. If omitted, CSV layer_name is used.",
    )
    parser.add_argument(
        "--batch",
        nargs="*",
        help="Optional batch filter when reading from CSV (e.g. B1 B2)",
    )
    parser.add_argument(
        "--status",
        nargs="*",
        help="Optional status filter when reading from CSV (e.g. Todo InProgress)",
    )
    parser.add_argument("--list", action="store_true", help="List PSD leaf layers and exit")
    parser.add_argument(
        "--trim",
        action="store_true",
        help="Export trimmed layer image only (default is full canvas for Live2D)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error when any target layer is missing",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate expected layer names against PSD and exit without exporting",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]

    psd_path = Path(args.psd)
    if not psd_path.is_absolute():
        psd_path = (project_root / psd_path).resolve()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (project_root / out_dir).resolve()

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = (project_root / csv_path).resolve()

    psd = load_psd(psd_path)

    if args.list:
        infos = collect_layer_infos(psd)
        print(f"leaf_layers={len(infos)}")
        for info in infos:
            print(f"{info.name}\t{info.path}\t[{info.left},{info.top},{info.right},{info.bottom}]")
        return

    if args.names:
        target_names = {n.strip() for n in args.names if n.strip()}
    else:
        batch_filter = {b.strip() for b in args.batch if b.strip()} if args.batch else None
        status_filter = (
            {s.strip().lower() for s in args.status if s.strip()} if args.status else None
        )
        target_names = set(read_names_from_csv_filtered(csv_path, batch_filter, status_filter))

    if not target_names:
        raise RuntimeError(
            "書き出し対象レイヤーがありません。--names か --csv を確認してください。"
        )

    validation = validate_layers(psd, target_names)

    if args.validate_only:
        print_validation_report(validation)
        report_path = out_dir / "validation_report.json"
        out_dir.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(validation, f, ensure_ascii=False, indent=2)
        print(f"report={report_path}")

        if validation["missing_count"] > 0 and args.strict:
            raise SystemExit(2)
        return

    result = export_layers(psd, out_dir, target_names, use_full_canvas=not args.trim)

    report_path = out_dir / "export_report.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"exported={len(result['exported'])}")
    print(f"missing={len(result['missing'])}")
    print(f"report={report_path}")

    if result["missing"]:
        print("missing_layers:")
        for name in result["missing"]:
            print(f"- {name}")
        if args.strict:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
