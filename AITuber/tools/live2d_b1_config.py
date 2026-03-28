"""B1 cutout configuration — landmarks, bounding boxes, colour thresholds."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CANVAS_W, CANVAS_H = 1024, 1536

LANDMARKS = {
    "viewer_left_eye": (387, 191),
    "viewer_right_eye": (628, 191),
    "nose": (508, 260),
    "mouth": (508, 336),
}

EYE_L_CENTER = LANDMARKS["viewer_right_eye"]  # (628, 191)
EYE_R_CENTER = LANDMARKS["viewer_left_eye"]  # (387, 191)


@dataclass
class BBox:
    """Axis-aligned bounding box (inclusive pixel coords)."""

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    def padded(self, px: int) -> "BBox":
        return BBox(
            max(0, self.x1 - px),
            max(0, self.y1 - px),
            min(CANVAS_W, self.x2 + px),
            min(CANVAS_H, self.y2 + px),
        )


# Bounding boxes
FACE_SKIN_BBOX = BBox(390, 100, 640, 400)
NECK_BBOX = BBox(410, 370, 610, 440)

EYE_L_BBOX = BBox(
    EYE_L_CENTER[0] - 45, EYE_L_CENTER[1] - 30,
    EYE_L_CENTER[0] + 45, EYE_L_CENTER[1] + 30,
)
EYE_R_BBOX = BBox(
    EYE_R_CENTER[0] - 45, EYE_R_CENTER[1] - 30,
    EYE_R_CENTER[0] + 45, EYE_R_CENTER[1] + 30,
)

BROW_L_BBOX = BBox(
    EYE_L_CENTER[0] - 40, EYE_L_CENTER[1] - 50,
    EYE_L_CENTER[0] + 40, EYE_L_CENTER[1] - 15,
)
BROW_R_BBOX = BBox(
    EYE_R_CENTER[0] - 40, EYE_R_CENTER[1] - 50,
    EYE_R_CENTER[0] + 40, EYE_R_CENTER[1] - 15,
)

MOUTH_BBOX = BBox(455, 310, 565, 365)

# Colour thresholds
SKIN_MIN = np.array([200, 160, 140], dtype=np.uint8)
SKIN_MAX = np.array([255, 255, 255], dtype=np.uint8)

SCLERA_LUMA_MIN = 220
IRIS_LUMA_MAX = 180
HIGHLIGHT_LUMA_MIN = 245
MOUTH_INNER_LUMA_MAX = 120
EYELID_LUMA_MAX = 190
