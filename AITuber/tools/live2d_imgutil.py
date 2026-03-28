"""Image processing utilities for Live2D cutout pipeline."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from live2d_b1_config import CANVAS_H, CANVAS_W


def luminance(arr: np.ndarray) -> np.ndarray:
    """Weighted grayscale luminance from RGB array (H,W,3+)."""
    return (
        0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    ).astype(np.float32)


def crop_region(arr: np.ndarray, bbox: "BBox") -> np.ndarray:
    return arr[bbox.y1 : bbox.y2, bbox.x1 : bbox.x2].copy()


def bbox_mask(shape_hw: tuple[int, int], bbox: "BBox") -> np.ndarray:
    mask = np.zeros(shape_hw, dtype=bool)
    mask[bbox.y1 : bbox.y2, bbox.x1 : bbox.x2] = True
    return mask


def dilate_mask(mask: np.ndarray, radius: int) -> np.ndarray:
    img = Image.fromarray((mask * 255).astype(np.uint8), "L")
    for _ in range(radius):
        img = img.filter(ImageFilter.MaxFilter(3))
    return np.array(img) > 127


def erode_mask(mask: np.ndarray, radius: int) -> np.ndarray:
    img = Image.fromarray((mask * 255).astype(np.uint8), "L")
    for _ in range(radius):
        img = img.filter(ImageFilter.MinFilter(3))
    return np.array(img) > 127


def smooth_alpha(mask: np.ndarray, blur_radius: int = 1) -> np.ndarray:
    img = Image.fromarray((mask * 255).astype(np.uint8), "L")
    if blur_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(blur_radius))
    return np.array(img)


def make_full_canvas_layer(
    src_rgba: np.ndarray, mask: np.ndarray, blur_edge: int = 1
) -> Image.Image:
    alpha = smooth_alpha(mask, blur_edge)
    out = np.zeros((CANVAS_H, CANVAS_W, 4), dtype=np.uint8)
    out[..., :3] = src_rgba[..., :3]
    src_alpha = src_rgba[..., 3].astype(np.float32) / 255.0
    mask_alpha = alpha.astype(np.float32) / 255.0
    out[..., 3] = (src_alpha * mask_alpha * 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def is_skin_color(rgb: np.ndarray) -> np.ndarray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (
        (r >= 200) & (g >= 140) & (b >= 120)
        & (r >= g) & (g >= b * 0.7)
        & (r - b < 150)
    )


def inpaint_skin(
    src_rgba: np.ndarray,
    mask_to_fill: np.ndarray,
    sample_mask: np.ndarray,
    iterations: int = 30,
) -> np.ndarray:
    result = src_rgba.copy()
    fill = mask_to_fill.copy()
    known = sample_mask.copy()

    for _ in range(iterations):
        if not fill.any():
            break
        boundary = dilate_mask(known, 1) & fill
        if not boundary.any():
            boundary = dilate_mask(known, 3) & fill
        if not boundary.any():
            break

        ys, xs = np.where(boundary)
        for y, x in zip(ys, xs):
            y1, y2 = max(0, y - 2), min(result.shape[0], y + 3)
            x1, x2 = max(0, x - 2), min(result.shape[1], x + 3)
            patch_known = known[y1:y2, x1:x2]
            if patch_known.any():
                patch_rgb = result[y1:y2, x1:x2, :3]
                mean_color = patch_rgb[patch_known].mean(axis=0).astype(np.uint8)
                result[y, x, :3] = mean_color
                result[y, x, 3] = 255
                known[y, x] = True
                fill[y, x] = False

    return result


def ellipse_mask(
    center: tuple[int, int], rx: int, ry: int, shape_hw: tuple[int, int]
) -> np.ndarray:
    img = Image.new("L", (shape_hw[1], shape_hw[0]), 0)
    draw = ImageDraw.Draw(img)
    draw.ellipse(
        [center[0] - rx, center[1] - ry, center[0] + rx, center[1] + ry],
        fill=255,
    )
    return np.array(img) > 127
