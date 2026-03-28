"""B1 layer extraction functions — face, eyes, mouth, brows, neck."""

from __future__ import annotations

import numpy as np

from live2d_b1_config import (
    BBox,
    BROW_L_BBOX,
    BROW_R_BBOX,
    EYE_L_BBOX,
    EYE_L_CENTER,
    EYE_R_BBOX,
    EYE_R_CENTER,
    FACE_SKIN_BBOX,
    LANDMARKS,
    MOUTH_BBOX,
    NECK_BBOX,
)
from live2d_imgutil import (
    bbox_mask,
    dilate_mask,
    ellipse_mask,
    erode_mask,
    inpaint_skin,
    is_skin_color,
    luminance,
)


def extract_face_base(src: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, w = src.shape[:2]
    rgb = src[..., :3]
    alpha_src = src[..., 3]

    skin = is_skin_color(rgb)
    in_face_region = bbox_mask((h, w), FACE_SKIN_BBOX)
    has_content = alpha_src > 30

    face_skin = skin & in_face_region & has_content

    r, g, b = rgb[..., 0].astype(float), rgb[..., 1].astype(float), rgb[..., 2].astype(float)
    near_skin = (
        (r >= 180) & (g >= 120) & (b >= 100)
        & (r >= g * 0.9) & in_face_region & has_content
    )

    base_mask = face_skin | (near_skin & dilate_mask(face_skin, 5))
    base_mask = dilate_mask(base_mask, 8)
    base_mask = erode_mask(base_mask, 5)

    eye_l_fill = ellipse_mask(EYE_L_CENTER, 50, 35, (h, w))
    eye_r_fill = ellipse_mask(EYE_R_CENTER, 50, 35, (h, w))
    mouth_fill = ellipse_mask(LANDMARKS["mouth"], 55, 30, (h, w))

    needs_fill = (eye_l_fill | eye_r_fill | mouth_fill) & ~face_skin & in_face_region
    filled = inpaint_skin(src, needs_fill, face_skin, iterations=50)

    final_mask = base_mask | needs_fill
    padded_face = FACE_SKIN_BBOX.padded(20)
    region_clip = bbox_mask((h, w), padded_face)
    final_mask = final_mask & region_clip

    return filled, final_mask


def extract_neck_base(src: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, w = src.shape[:2]
    rgb = src[..., :3]
    alpha_src = src[..., 3]

    skin = is_skin_color(rgb)
    in_neck = bbox_mask((h, w), NECK_BBOX.padded(10))
    has_content = alpha_src > 30

    neck_skin = skin & in_neck & has_content

    r, g, b = rgb[..., 0].astype(float), rgb[..., 1].astype(float), rgb[..., 2].astype(float)
    near_skin = (r >= 180) & (g >= 120) & (b >= 100) & in_neck & has_content
    neck_mask = neck_skin | (near_skin & dilate_mask(neck_skin, 5))

    neck_mask = dilate_mask(neck_mask, 4)
    neck_mask = erode_mask(neck_mask, 2)

    overlap_bbox = BBox(NECK_BBOX.x1, NECK_BBOX.y1 - 30, NECK_BBOX.x2, NECK_BBOX.y1)
    overlap_region = bbox_mask((h, w), overlap_bbox)
    overlap_skin = skin & overlap_region & has_content
    neck_mask = neck_mask | overlap_skin

    return src, neck_mask


def extract_eye_part(
    src: np.ndarray,
    eye_center: tuple[int, int],
    eye_bbox: BBox,
    part: str,
) -> tuple[np.ndarray, np.ndarray]:
    h, w = src.shape[:2]
    rgb = src[..., :3]
    luma = luminance(rgb)
    alpha_src = src[..., 3]
    has_content = alpha_src > 30

    cx, cy = eye_center
    in_eye = bbox_mask((h, w), eye_bbox) & has_content

    skin = is_skin_color(rgb)
    not_skin = ~skin & in_eye

    eye_ellipse = ellipse_mask(eye_center, 38, 22, (h, w))
    eye_opening = eye_ellipse & in_eye

    if part == "white":
        sclera = (luma > 200) & eye_opening & not_skin & (luma < 250)
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        whitish = (r > 200) & (g > 190) & (b > 190) & eye_opening
        sclera = dilate_mask(sclera | whitish, 2) & eye_opening
        return src, sclera

    elif part == "iris":
        iris_region = ellipse_mask(eye_center, 22, 18, (h, w))
        dark_colored = (luma < 200) & iris_region & in_eye
        pupil = (luma < 120) & iris_region
        iris = dilate_mask(dark_colored | pupil, 2) & iris_region
        return src, iris

    elif part == "highlight":
        iris_region = ellipse_mask(eye_center, 22, 18, (h, w))
        highlights = (luma > 245) & iris_region & in_eye
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        near_white = (r > 245) & (g > 245) & (b > 245) & iris_region
        highlights = dilate_mask(highlights | near_white, 1) & eye_opening
        return src, highlights

    elif part == "eyelid_upper":
        upper_band = BBox(eye_bbox.x1, eye_bbox.y1, eye_bbox.x2, cy - 5)
        in_upper = bbox_mask((h, w), upper_band)
        dark_upper = (luma < 200) & in_upper & not_skin & has_content
        eyelash_band = BBox(cx - 35, cy - 28, cx + 35, cy - 8)
        in_lash = bbox_mask((h, w), eyelash_band)
        dark_lash = (luma < 210) & in_lash & not_skin & has_content
        upper_mask = dilate_mask(dark_upper | dark_lash, 1)
        return src, upper_mask

    elif part == "eyelid_lower":
        lower_band = BBox(eye_bbox.x1, cy + 5, eye_bbox.x2, eye_bbox.y2)
        in_lower = bbox_mask((h, w), lower_band)
        r, g, b = rgb[..., 0].astype(float), rgb[..., 1].astype(float), rgb[..., 2].astype(float)
        pinkish_edge = (r > 150) & (r < 230) & (g < 170) & (b < 180) & in_lower & has_content
        lower_mask = dilate_mask(erode_mask(pinkish_edge & ~skin, 1), 1)
        return src, lower_mask

    raise ValueError(f"Unknown eye part: {part}")


def extract_brow(src: np.ndarray, brow_bbox: BBox) -> tuple[np.ndarray, np.ndarray]:
    h, w = src.shape[:2]
    rgb = src[..., :3]
    luma = luminance(rgb)
    alpha_src = src[..., 3]
    has_content = alpha_src > 30

    in_brow = bbox_mask((h, w), brow_bbox) & has_content
    skin = is_skin_color(rgb)

    dark_brow = (luma < 200) & in_brow & ~skin
    dark_brow = erode_mask(dilate_mask(dark_brow, 1), 1)
    return src, dark_brow


def extract_mouth_part(src: np.ndarray, part: str) -> tuple[np.ndarray, np.ndarray]:
    h, w = src.shape[:2]
    rgb = src[..., :3]
    luma = luminance(rgb)
    alpha_src = src[..., 3]
    has_content = alpha_src > 30

    mouth_cx, mouth_cy = LANDMARKS["mouth"]
    in_mouth = bbox_mask((h, w), MOUTH_BBOX.padded(5)) & has_content
    skin = is_skin_color(rgb)

    r, g, b = rgb[..., 0].astype(float), rgb[..., 1].astype(float), rgb[..., 2].astype(float)

    if part == "upper":
        upper_band = BBox(MOUTH_BBOX.x1, MOUTH_BBOX.y1, MOUTH_BBOX.x2, mouth_cy)
        in_upper = bbox_mask((h, w), upper_band) & has_content
        lip_color = (r > 180) & (r < 255) & (g < 180) & (b < 190) & in_upper & ~skin
        lip_color = dilate_mask(lip_color | ((luma < 200) & in_upper & ~skin), 1)
        return src, lip_color

    elif part == "lower":
        lower_band = BBox(MOUTH_BBOX.x1, mouth_cy, MOUTH_BBOX.x2, MOUTH_BBOX.y2)
        in_lower = bbox_mask((h, w), lower_band) & has_content
        lip_color = (r > 180) & (r < 255) & (g < 180) & (b < 190) & in_lower & ~skin
        lip_color = dilate_mask(lip_color | ((luma < 200) & in_lower & ~skin), 1)
        return src, lip_color

    elif part == "inner":
        inner_region = ellipse_mask((mouth_cx, mouth_cy), 35, 15, (h, w))
        dark_inner = (luma < 140) & inner_region & has_content
        dark_inner = dilate_mask(dark_inner | ((luma < 100) & inner_region), 2) & inner_region
        return src, dark_inner

    elif part == "tongue":
        inner_region = ellipse_mask((mouth_cx, mouth_cy), 30, 12, (h, w))
        tongue_color = (r > 150) & (r < 230) & (g > 80) & (g < 150) & (b > 80) & (b < 160)
        dark_inner = (luma < 160) & inner_region
        tongue = tongue_color & inner_region & has_content & dilate_mask(dark_inner, 3)
        return src, tongue

    raise ValueError(f"Unknown mouth part: {part}")
