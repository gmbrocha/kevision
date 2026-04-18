"""Stage 3 + 4: detect scallop primitives via multi-scale template matching, tag orientation.

A single scallop = one ∩/∪/⊃/⊂ arc. We build a small bank of canonical templates
at several scales and four orientations, run cv2.matchTemplate over the cleaned
image, threshold the response, and apply non-maximum suppression to dedupe
nearby/overlapping hits.

Each surviving Scallop carries:
  - apex (x, y)        — the peak of the bulge (where the arc is "highest")
  - radius              — template scale that matched
  - orientation         — TOP / BOTTOM / LEFT / RIGHT (which way the bulge points)
  - confidence          — normalized match score 0..1

The orientation tag is the geometric DNA we use in stages 5-6 to assemble
scallops into runs and runs into closed loops.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

Orientation = Literal["TOP", "BOTTOM", "LEFT", "RIGHT"]
ORIENTATIONS: tuple[Orientation, ...] = ("TOP", "BOTTOM", "LEFT", "RIGHT")

# Template scales (arc radius in pixels at 300 DPI). Calibrated for our fixture.
DEFAULT_SCALES: tuple[int, ...] = (12, 18, 28, 42, 60)
DEFAULT_LINE_THICKNESS: int = 3
DEFAULT_MATCH_THRESHOLD: float = 0.50  # cv2.TM_CCOEFF_NORMED response
DEFAULT_NMS_RADIUS_MULT: float = 0.7   # NMS radius = scallop radius * this
TEMPLATE_PAD: int = 4

# Orientation -> BGR overlay color
ORIENTATION_COLORS: dict[Orientation, tuple[int, int, int]] = {
    "TOP":    (0, 0, 230),    # red    — top edge of cloud (bulges up)
    "BOTTOM": (0, 200, 0),    # green  — bottom edge (bulges down)
    "LEFT":   (230, 0, 0),    # blue   — left edge (bulges left)
    "RIGHT":  (0, 200, 200),  # yellow — right edge (bulges right)
}


@dataclass(frozen=True)
class Scallop:
    x: int
    y: int
    radius: int
    orientation: Orientation
    confidence: float


def make_scallop_template(
    radius: int,
    orientation: Orientation,
    line_thickness: int = DEFAULT_LINE_THICKNESS,
) -> np.ndarray:
    """Build a single-scallop template (white background, black arc)."""
    pad = TEMPLATE_PAD
    if orientation in ("TOP", "BOTTOM"):
        h = radius + 2 * pad
        w = 2 * radius + 2 * pad
    else:
        h = 2 * radius + 2 * pad
        w = radius + 2 * pad
    img = np.full((h, w), 255, dtype=np.uint8)

    if orientation == "TOP":
        # ∩ apex at the top; arc opens downward
        cv2.ellipse(img, (w // 2, h - pad), (radius, radius), 0, 180, 360, color=0, thickness=line_thickness)
    elif orientation == "BOTTOM":
        # ∪ apex at the bottom; arc opens upward
        cv2.ellipse(img, (w // 2, pad), (radius, radius), 0, 0, 180, color=0, thickness=line_thickness)
    elif orientation == "LEFT":
        # ⊃ apex at the left; arc opens rightward
        cv2.ellipse(img, (w - pad, h // 2), (radius, radius), 0, 90, 270, color=0, thickness=line_thickness)
    elif orientation == "RIGHT":
        # ⊂ apex at the right; arc opens leftward
        cv2.ellipse(img, (pad, h // 2), (radius, radius), 0, -90, 90, color=0, thickness=line_thickness)
    else:
        raise ValueError(f"unknown orientation {orientation}")
    return img


def _apex_from_match(template_corner: tuple[int, int], orientation: Orientation, radius: int, template_shape: tuple[int, int]) -> tuple[int, int]:
    x, y = template_corner
    th, tw = template_shape
    if orientation == "TOP":
        return (x + tw // 2, y + TEMPLATE_PAD)
    if orientation == "BOTTOM":
        return (x + tw // 2, y + th - TEMPLATE_PAD)
    if orientation == "LEFT":
        return (x + TEMPLATE_PAD, y + th // 2)
    if orientation == "RIGHT":
        return (x + tw - TEMPLATE_PAD, y + th // 2)
    raise ValueError(orientation)


def detect_scallops(
    cleaned_gray: np.ndarray,
    scales: tuple[int, ...] = DEFAULT_SCALES,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
    nms_radius_mult: float = DEFAULT_NMS_RADIUS_MULT,
) -> list[Scallop]:
    """Find scallops in `cleaned_gray` (white background, dark ink). Returns NMS'd hits."""
    candidates: list[Scallop] = []
    for radius in scales:
        for orient in ORIENTATIONS:
            template = make_scallop_template(radius, orient)
            result = cv2.matchTemplate(cleaned_gray, template, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(result >= threshold)
            for y, x in zip(ys.tolist(), xs.tolist()):
                apex_x, apex_y = _apex_from_match((x, y), orient, radius, template.shape)
                candidates.append(
                    Scallop(
                        x=int(apex_x),
                        y=int(apex_y),
                        radius=int(radius),
                        orientation=orient,
                        confidence=float(result[y, x]),
                    )
                )
    return _nms(candidates, nms_radius_mult)


def _nms(scallops: list[Scallop], radius_mult: float) -> list[Scallop]:
    """Greedy NMS: keep highest-confidence first; suppress same-orientation neighbors within `radius_mult * radius`."""
    scallops_sorted = sorted(scallops, key=lambda s: -s.confidence)
    kept: list[Scallop] = []
    for cand in scallops_sorted:
        suppressed = False
        for k in kept:
            if k.orientation != cand.orientation:
                continue
            r = max(k.radius, cand.radius) * radius_mult
            d = ((k.x - cand.x) ** 2 + (k.y - cand.y) ** 2) ** 0.5
            if d < r:
                suppressed = True
                break
        if not suppressed:
            kept.append(cand)
    return kept


def overlay_scallops(gray: np.ndarray, scallops: list[Scallop], thickness: int = 4) -> np.ndarray:
    """Draw each detected scallop as a colored arc on top of the page (gray)."""
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for s in scallops:
        color = ORIENTATION_COLORS[s.orientation]
        if s.orientation == "TOP":
            cv2.ellipse(bgr, (s.x, s.y), (s.radius, s.radius), 0, 180, 360, color, thickness)
        elif s.orientation == "BOTTOM":
            cv2.ellipse(bgr, (s.x, s.y), (s.radius, s.radius), 0, 0, 180, color, thickness)
        elif s.orientation == "LEFT":
            cv2.ellipse(bgr, (s.x, s.y), (s.radius, s.radius), 0, 90, 270, color, thickness)
        elif s.orientation == "RIGHT":
            cv2.ellipse(bgr, (s.x, s.y), (s.radius, s.radius), 0, -90, 90, color, thickness)
    return bgr
