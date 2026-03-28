"""B1 Face/Eye/Mouth cutout tool for Popica Live2D Phase 1.

Creates 18 B1 layer PNGs (full-canvas) + a layered PSD for Cubism import.
Source: lumina_rgba.png (1024x1536 flat illustration).

Usage:
  python tools/live2d_b1_cutout.py
  python tools/live2d_b1_cutout.py --source path/to/image.png --out-dir output/live2d/popica/b1
  python tools/live2d_b1_cutout.py --preview  # save debug previews only
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from live2d_b1_config import (
    BROW_L_BBOX,
    BROW_R_BBOX,
    CANVAS_H,
    CANVAS_W,
    EYE_L_BBOX,
    EYE_L_CENTER,
    EYE_R_BBOX,
    EYE_R_CENTER,
)
from live2d_b1_extract import (
    extract_brow,
    extract_eye_part,
    extract_face_base,
    extract_mouth_part,
    extract_neck_base,
)
from live2d_imgutil import make_full_canvas_layer


# ---------------------------------------------------------------------------
# PSD creation using psd-tools
# ---------------------------------------------------------------------------

def create_layered_psd(
    layers: list[tuple[str, Image.Image]],
    output_path: Path,
    canvas_size: tuple[int, int] = (CANVAS_W, CANVAS_H),
) -> None:
    """Create a multi-layer PSD file using psd-tools internal API."""
    try:
        from psd_tools.constants import ChannelID, ColorMode, Compression  # noqa: F401
        from psd_tools.psd import PSD  # noqa: F401
        from psd_tools.psd.header import FileHeader  # noqa: F401
        from psd_tools.psd.layer_and_mask import (
            ChannelData,  # noqa: F401
            ChannelDataList,  # noqa: F401
            ChannelImageData,  # noqa: F401
            ChannelInfo,  # noqa: F401
            LayerAndMaskInformation,  # noqa: F401
            LayerFlags,  # noqa: F401
            LayerInfo,  # noqa: F401
            LayerRecord,  # noqa: F401
            LayerRecords,  # noqa: F401
        )
    except ImportError:
        print("WARNING: psd-tools internal API not fully available.")
        print("Falling back to flat PSD export.")
        _create_flat_psd(layers, output_path, canvas_size)
        return

    _create_psd_lowlevel(layers, output_path, canvas_size)


def _create_flat_psd(
    layers: list[tuple[str, Image.Image]],
    output_path: Path,
    canvas_size: tuple[int, int],
) -> None:
    """Fallback: create a flat PSD with the composite."""
    from psd_tools import PSDImage

    # Composite all layers
    composite = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    for _name, img in layers:
        composite = Image.alpha_composite(composite, img)
    # Save as flat PSD
    psd = PSDImage.frompil(composite)
    psd.save(str(output_path))


def _create_psd_lowlevel(
    layers: list[tuple[str, Image.Image]],
    output_path: Path,
    canvas_size: tuple[int, int],
) -> None:
    """Create multi-layer PSD using psd-tools low-level API."""
    from psd_tools.constants import BlendMode, ChannelID, ColorMode, Compression
    from psd_tools.psd import PSD
    from psd_tools.psd.header import FileHeader
    from psd_tools.psd.layer_and_mask import (
        ChannelData,
        ChannelDataList,
        ChannelImageData,
        ChannelInfo,
        LayerAndMaskInformation,
        LayerFlags,
        LayerInfo,
        LayerRecord,
        LayerRecords,
    )

    width, height = canvas_size

    header = FileHeader(
        version=1,
        channels=4,
        height=height,
        width=width,
        depth=8,
        color_mode=ColorMode.RGB,
    )

    layer_records = []
    channel_data_items = []

    for name, img in layers:
        img_rgba = img.convert("RGBA")
        arr = np.array(img_rgba)

        # Find bounding box of non-transparent pixels
        alpha = arr[:, :, 3]
        rows = np.any(alpha > 0, axis=1)
        cols = np.any(alpha > 0, axis=0)

        if not rows.any():
            # Empty layer, use 1x1 pixel
            top, bottom, left, right = 0, 1, 0, 1
            r_data = bytes([0])
            g_data = bytes([0])
            b_data = bytes([0])
            a_data = bytes([0])
        else:
            top = int(np.argmax(rows))
            bottom = int(height - np.argmax(rows[::-1]))
            left = int(np.argmax(cols))
            right = int(width - np.argmax(cols[::-1]))

            # Extract channel data for the bounding box
            crop = arr[top:bottom, left:right]
            r_data = crop[:, :, 0].tobytes()
            g_data = crop[:, :, 1].tobytes()
            b_data = crop[:, :, 2].tobytes()
            a_data = crop[:, :, 3].tobytes()

        # Create channel info entries
        channels = [
            (ChannelID.TRANSPARENCY_MASK, a_data),
            (ChannelID.CHANNEL_0, r_data),
            (ChannelID.CHANNEL_1, g_data),
            (ChannelID.CHANNEL_2, b_data),
        ]

        channel_info_list = []
        channel_data_list = []

        for ch_id, raw_data in channels:
            # length = 2 bytes compression header + raw data
            channel_info_list.append(
                ChannelInfo(id=ch_id, length=len(raw_data) + 2)
            )
            channel_data_list.append(
                ChannelData(compression=Compression.RAW, data=raw_data)
            )

        record = LayerRecord(
            top=top,
            bottom=bottom,
            left=left,
            right=right,
            channel_info=channel_info_list,
            signature=b"8BIM",
            blend_mode=BlendMode.NORMAL,
            opacity=255,
            flags=LayerFlags(),
            name=name,
        )

        layer_records.append(record)
        channel_data_items.append(ChannelDataList(items=channel_data_list))

    try:
        layer_info = LayerInfo(
            layer_count=len(layers),
            layer_records=LayerRecords(items=layer_records),
            channel_image_data=ChannelImageData(items=channel_data_items),
        )

        layer_and_mask = LayerAndMaskInformation(
            layer_info=layer_info,
        )

        psd = PSD(header=header, layer_and_mask_information=layer_and_mask)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            psd.write(f)
        print(f"PSD saved: {output_path}")
    except Exception as e:
        print(f"WARNING: Low-level PSD creation failed: {e}")
        print("Falling back to flat PSD.")
        _create_flat_psd(layers, output_path, canvas_size)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

@dataclass
class LayerResult:
    name: str
    csv_name: str
    mask_pixels: int = 0
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    file: str = ""


def run_b1_cutout(
    source_path: Path,
    out_dir: Path,
    create_psd: bool = True,
    preview_only: bool = False,
) -> list[LayerResult]:
    """Run full B1 cutout pipeline."""
    print(f"Loading source: {source_path}")
    src_img = Image.open(source_path).convert("RGBA")
    src = np.array(src_img)
    assert src.shape == (CANVAS_H, CANVAS_W, 4), f"Expected {CANVAS_W}x{CANVAS_H}, got {src_img.size}"

    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[LayerResult] = []
    psd_layers: list[tuple[str, Image.Image]] = []

    # Define all B1 layers in draw order (back to front)
    layer_specs = [
        # (csv_name, extraction_fn)
        ("Neck_Base", lambda: extract_neck_base(src)),
        ("Face_Base", lambda: extract_face_base(src)),
        ("Mouth_Inner_01", lambda: extract_mouth_part(src, "inner")),
        ("Tongue_01", lambda: extract_mouth_part(src, "tongue")),
        ("Mouth_Lower_01", lambda: extract_mouth_part(src, "lower")),
        ("Mouth_Upper_01", lambda: extract_mouth_part(src, "upper")),
        ("Eye_White_L_01", lambda: extract_eye_part(src, EYE_L_CENTER, EYE_L_BBOX, "white")),
        ("Eye_White_R_01", lambda: extract_eye_part(src, EYE_R_CENTER, EYE_R_BBOX, "white")),
        ("Eye_Iris_L_01", lambda: extract_eye_part(src, EYE_L_CENTER, EYE_L_BBOX, "iris")),
        ("Eye_Iris_R_01", lambda: extract_eye_part(src, EYE_R_CENTER, EYE_R_BBOX, "iris")),
        ("Eye_Highlight_L_01", lambda: extract_eye_part(src, EYE_L_CENTER, EYE_L_BBOX, "highlight")),
        ("Eye_Highlight_R_01", lambda: extract_eye_part(src, EYE_R_CENTER, EYE_R_BBOX, "highlight")),
        ("Eyelid_Upper_L_01", lambda: extract_eye_part(src, EYE_L_CENTER, EYE_L_BBOX, "eyelid_upper")),
        ("Eyelid_Upper_R_01", lambda: extract_eye_part(src, EYE_R_CENTER, EYE_R_BBOX, "eyelid_upper")),
        ("Eyelid_Lower_L_01", lambda: extract_eye_part(src, EYE_L_CENTER, EYE_L_BBOX, "eyelid_lower")),
        ("Eyelid_Lower_R_01", lambda: extract_eye_part(src, EYE_R_CENTER, EYE_R_BBOX, "eyelid_lower")),
        ("Brow_L_01", lambda: extract_brow(src, BROW_L_BBOX)),
        ("Brow_R_01", lambda: extract_brow(src, BROW_R_BBOX)),
    ]

    for csv_name, extract_fn in layer_specs:
        print(f"  Extracting: {csv_name} ...", end=" ", flush=True)
        filled_src, mask = extract_fn()
        pixel_count = int(mask.sum())

        if pixel_count == 0:
            print(f"WARN: 0 pixels extracted!")
            layer_img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        else:
            layer_img = make_full_canvas_layer(filled_src, mask, blur_edge=1)

        # Compute actual bbox
        arr = np.array(layer_img)
        alpha = arr[:, :, 3]
        if alpha.any():
            rows = np.any(alpha > 0, axis=1)
            cols = np.any(alpha > 0, axis=0)
            t, b = int(np.argmax(rows)), int(CANVAS_H - np.argmax(rows[::-1]))
            l, r = int(np.argmax(cols)), int(CANVAS_W - np.argmax(cols[::-1]))
            actual_bbox = (l, t, r, b)
        else:
            actual_bbox = (0, 0, 0, 0)

        print(f"OK ({pixel_count} px, bbox={actual_bbox})")

        result = LayerResult(
            name=csv_name,
            csv_name=csv_name,
            mask_pixels=pixel_count,
            bbox=actual_bbox,
        )

        if not preview_only:
            png_path = out_dir / f"{csv_name}.png"
            layer_img.save(str(png_path))
            result.file = str(png_path)

        results.append(result)
        psd_layers.append((csv_name, layer_img))

    # Save debug composite
    composite = Image.new("RGBA", (CANVAS_W, CANVAS_H), (255, 255, 255, 255))
    for _name, img in psd_layers:
        composite = Image.alpha_composite(composite, img)
    composite_path = out_dir / "b1_composite_preview.png"
    composite.save(str(composite_path))
    print(f"  Composite preview: {composite_path}")

    # Create PSD
    if create_psd and not preview_only:
        psd_path = out_dir / "b1_layers.psd"
        print(f"  Creating PSD: {psd_path}")
        try:
            create_layered_psd(psd_layers, psd_path)
        except Exception as e:
            print(f"  WARNING: PSD creation failed: {e}")
            print(f"  Layer PNGs are still available in {out_dir}")

    # Save report
    report = {
        "source": str(source_path),
        "output_dir": str(out_dir),
        "canvas_size": [CANVAS_W, CANVAS_H],
        "layers": [
            {
                "name": r.csv_name,
                "pixels": r.mask_pixels,
                "bbox": list(r.bbox),
                "file": r.file,
                "status": "ok" if r.mask_pixels > 0 else "empty",
            }
            for r in results
        ],
    }
    report_path = out_dir / "b1_export_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"  Report: {report_path}")

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="B1 Face/Eye/Mouth cutout for Popica")
    parser.add_argument(
        "--source",
        default="lumina_rgba.png",
        help="Source RGBA image (default: lumina_rgba.png)",
    )
    parser.add_argument(
        "--out-dir",
        default="output/live2d/popica/b1",
        help="Output directory",
    )
    parser.add_argument(
        "--no-psd",
        action="store_true",
        help="Skip PSD creation",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview mode: only save composite, no individual PNGs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]

    source = Path(args.source)
    if not source.is_absolute():
        source = (project_root / source).resolve()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (project_root / out_dir).resolve()

    results = run_b1_cutout(
        source_path=source,
        out_dir=out_dir,
        create_psd=not args.no_psd,
        preview_only=args.preview,
    )

    # Summary
    total = len(results)
    ok = sum(1 for r in results if r.mask_pixels > 0)
    empty = total - ok
    print(f"\nSummary: {ok}/{total} layers extracted ({empty} empty)")
    if empty:
        for r in results:
            if r.mask_pixels == 0:
                print(f"  EMPTY: {r.csv_name}")


if __name__ == "__main__":
    main()
