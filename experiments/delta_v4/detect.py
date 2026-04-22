"""delta_v4: geometry-first delta detector.

Fresh restart after the contour-first and digit-anchored attempts went sideways.
This version does NOT seed from the PDF text layer. It searches for the actual
triangle geometry first, then uses the text layer only as a secondary check.

Core idea:
  1. Run a line-segment detector on the denoised page.
  2. Keep only segments that could plausibly be one side of an upright delta:
     horizontal base, left diagonal, right diagonal.
  3. Pair left/right diagonals into equilateral-ish triangles and verify that
     the implied base is really present in the ink.
  4. Score the local support along all three sides and reject candidates whose
     interiors are too noisy.
  5. Only after geometry passes, look for a PDF digit whose centroid lies
     inside the triangle. That digit boosts confidence but does not drive the
     search.

The canonical fixture is Rev1 page 17 (AE122), using delta_v3's denoise_2.png.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import fitz
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).parent / "output"

DEFAULT_IMAGE = REPO_ROOT / "experiments" / "delta_v3" / "Revision #1 - Drawing Changes_p17_denoise_2.png"
DEFAULT_GT_OVERLAY = (
    REPO_ROOT
    / "experiments"
    / "delta_v3"
    / "Revision #1 - Drawing Changes_p17_denoise_2_DELTAS_HIGHLIGHTED.png"
)
DEFAULT_PDF = (
    REPO_ROOT
    / "revision_sets"
    / "Revision #1 - Drawing Changes"
    / "Revision #1 - Drawing Changes.pdf"
)
DEFAULT_PAGE = 17
DEFAULT_DPI = 300

# Image preprocessing.
INK_THRESHOLD = 225
CLOSE_KERNEL = 3

# Line-segment filtering.
MIN_SEGMENT_LENGTH = 26.0
MAX_SEGMENT_LENGTH = 120.0
BASE_ANGLE_TOLERANCE_DEG = 10.0
SIDE_ANGLE_TOLERANCE_DEG = 12.0
MERGE_ANGLE_TOLERANCE_DEG = 8.0
MERGE_PERPENDICULAR_TOLERANCE = 4.5
MERGE_GAP_TOLERANCE = 18.0

# Triangle geometry gates.
APEX_DISTANCE_TOLERANCE = 18.0
BASELINE_Y_TOLERANCE = 18.0
SIDE_LENGTH_RATIO_TOLERANCE = 0.28
BASE_LENGTH_RATIO_TOLERANCE = 0.30
HEIGHT_RATIO_TOLERANCE = 0.28
APEX_ENDPOINT_DISTANCE_MAX = 55.0
APEX_EXTENSION_ABOVE_TOP_MAX = 48.0
APEX_EXTENSION_BELOW_TOP_MAX = 18.0

# Triangle verification.
SIDE_SUPPORT_MIN = 0.62
BASE_SUPPORT_MIN = 0.48
INTERIOR_INK_RATIO_MAX = 0.18
BASE_SEGMENT_BONUS_MIN = 0.45

# Final scoring / dedupe.
GEOMETRY_SCORE_MIN = 0.63
GEOMETRY_ONLY_SCORE_MIN = 0.78
TEXT_DIGIT_BONUS = 0.12
TARGET_DIGIT_BONUS = 0.08
NMS_RADIUS = 40.0
GT_MATCH_RADIUS = 80.0

# Fixed-size second pass. The detector auto-calibrates this from the first pass
# when it can, then searches from partial base fragments using that one size.
DEFAULT_CANONICAL_SIDE = 120.0
FIXED_BASE_SEED_MIN = 22.0
FIXED_BASE_SEED_MAX_MULT = 1.25
FIXED_BASE_MIN_OVERLAP = 12.0
FIXED_BASE_MIN_OVERLAP_FRAC = 0.15
FIXED_SIDE_SUPPORT_MIN = 0.60
FIXED_INTERIOR_INK_RATIO_MAX = 0.22
FIXED_GEOMETRY_SCORE_MIN = 0.66

# Debug visualization.
SAMPLE_RADIUS = 2
SIDE_SAMPLE_COUNT = 28
BASE_SAMPLE_COUNT = 24

PDF_TEXT_LAYER_SOURCE = "pdf_text_layer"


@dataclass(frozen=True)
class DigitWord:
    text: str
    bbox: tuple[float, float, float, float]
    centroid: tuple[float, float]


@dataclass(frozen=True)
class DigitAttachment:
    text: str | None
    index: int | None
    source: str | None
    centroid: tuple[float, float] | None
    bbox: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class Segment:
    p0: tuple[float, float]
    p1: tuple[float, float]
    length: float
    kind: str  # BASE / LEFT / RIGHT

    @property
    def midpoint(self) -> tuple[float, float]:
        return ((self.p0[0] + self.p1[0]) / 2.0, (self.p0[1] + self.p1[1]) / 2.0)

    @property
    def top(self) -> tuple[float, float]:
        return self.p0

    @property
    def bottom(self) -> tuple[float, float]:
        return self.p1

    @property
    def left(self) -> tuple[float, float]:
        return self.p0

    @property
    def right(self) -> tuple[float, float]:
        return self.p1


@dataclass(frozen=True)
class TriangleCandidate:
    apex: tuple[float, float]
    left_base: tuple[float, float]
    right_base: tuple[float, float]
    side_length: float
    side_support: float
    base_support: float
    interior_ink_ratio: float
    base_segment_overlap: float
    geometry_score: float
    score: float
    digit: str | None
    digit_index: int | None
    digit_source: str | None
    digit_centroid: tuple[float, float] | None
    digit_bbox: tuple[float, float, float, float] | None

    @property
    def centroid(self) -> tuple[float, float]:
        ax, ay = self.apex
        lx, ly = self.left_base
        rx, ry = self.right_base
        return ((ax + lx + rx) / 3.0, (ay + ly + ry) / 3.0)

    @property
    def polygon(self) -> np.ndarray:
        return np.array([self.apex, self.left_base, self.right_base], dtype=np.int32)


def _native_to_pixel_matrix(page: fitz.Page, dpi: int) -> fitz.Matrix:
    zoom = dpi / 72.0
    return page.rotation_matrix * fitz.Matrix(zoom, zoom)


def extract_digit_words_in_pixels(pdf_path: Path, page_index: int, dpi: int = DEFAULT_DPI) -> list[DigitWord]:
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        mat = _native_to_pixel_matrix(page, dpi)
        out: list[DigitWord] = []
        for w in page.get_text("words"):
            text = (w[4] or "").strip()
            if len(text) != 1 or not text.isdigit():
                continue
            rect = fitz.Rect(w[0], w[1], w[2], w[3]) * mat
            rect.normalize()
            cx = (rect.x0 + rect.x1) / 2.0
            cy = (rect.y0 + rect.y1) / 2.0
            out.append(
                DigitWord(
                    text=text,
                    bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
                    centroid=(cx, cy),
                )
            )
    finally:
        doc.close()
    return out


def preprocess_image(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    work = gray.copy()
    work[work > INK_THRESHOLD] = 255
    binary = cv2.threshold(work, INK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)[1]
    if CLOSE_KERNEL > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (CLOSE_KERNEL, CLOSE_KERNEL))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    search_gray = 255 - binary
    return search_gray, binary


def _angle_deg(p0: tuple[float, float], p1: tuple[float, float]) -> float:
    return math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))


def _orientation_bucket(angle_deg: float) -> str | None:
    ori = angle_deg % 180.0
    if min(abs(ori - 0.0), abs(ori - 180.0)) <= BASE_ANGLE_TOLERANCE_DEG:
        return "BASE"
    if abs(ori - 60.0) <= SIDE_ANGLE_TOLERANCE_DEG or abs(ori - 120.0) <= SIDE_ANGLE_TOLERANCE_DEG:
        return "SIDE"
    return None


def _segment_angle(seg: Segment) -> float:
    return _angle_deg(seg.p0, seg.p1) % 180.0


def _angle_delta(a: float, b: float) -> float:
    diff = abs(a - b) % 180.0
    return min(diff, 180.0 - diff)


def _point_line_distance(point: tuple[float, float], p0: tuple[float, float], p1: tuple[float, float]) -> float:
    x0, y0 = p0
    x1, y1 = p1
    px, py = point
    denom = math.hypot(x1 - x0, y1 - y0)
    if denom <= 1e-6:
        return math.hypot(px - x0, py - y0)
    return abs((y1 - y0) * px - (x1 - x0) * py + x1 * y0 - y1 * x0) / denom


def _projection_interval(
    ref_p0: tuple[float, float],
    ref_p1: tuple[float, float],
    points: list[tuple[float, float]],
) -> tuple[float, float]:
    ux = ref_p1[0] - ref_p0[0]
    uy = ref_p1[1] - ref_p0[1]
    norm = math.hypot(ux, uy)
    if norm <= 1e-6:
        return (0.0, 0.0)
    ux /= norm
    uy /= norm
    vals = [((px - ref_p0[0]) * ux + (py - ref_p0[1]) * uy) for px, py in points]
    return (min(vals), max(vals))


def _interval_gap(a0: float, a1: float, b0: float, b1: float) -> float:
    if a1 < b0:
        return b0 - a1
    if b1 < a0:
        return a0 - b1
    return 0.0


def can_merge_segments(a: Segment, b: Segment) -> bool:
    if a.kind != b.kind:
        return False
    if _angle_delta(_segment_angle(a), _segment_angle(b)) > MERGE_ANGLE_TOLERANCE_DEG:
        return False

    distances = (
        _point_line_distance(a.p0, b.p0, b.p1),
        _point_line_distance(a.p1, b.p0, b.p1),
        _point_line_distance(b.p0, a.p0, a.p1),
        _point_line_distance(b.p1, a.p0, a.p1),
    )
    if max(distances) > MERGE_PERPENDICULAR_TOLERANCE:
        return False

    a0, a1 = _projection_interval(a.p0, a.p1, [a.p0, a.p1])
    b0, b1 = _projection_interval(a.p0, a.p1, [b.p0, b.p1])
    return _interval_gap(a0, a1, b0, b1) <= MERGE_GAP_TOLERANCE


def merge_two_segments(a: Segment, b: Segment) -> Segment:
    points = [a.p0, a.p1, b.p0, b.p1]
    if a.kind == "BASE":
        left = min(points, key=lambda p: (p[0], p[1]))
        right = max(points, key=lambda p: (p[0], -p[1]))
        y = float(np.mean([p[1] for p in points]))
        p0 = (left[0], y)
        p1 = (right[0], y)
    elif a.kind == "LEFT":
        p0 = min(points, key=lambda p: p[1])
        p1 = max(points, key=lambda p: p[1])
        if p0[0] <= p1[0]:
            p0 = min(points, key=lambda p: (p[1], -p[0]))
            p1 = max(points, key=lambda p: (p[1], -p[0]))
    else:
        p0 = min(points, key=lambda p: p[1])
        p1 = max(points, key=lambda p: p[1])
        if p0[0] >= p1[0]:
            p0 = min(points, key=lambda p: (p[1], p[0]))
            p1 = max(points, key=lambda p: (p[1], p[0]))
    return Segment(p0, p1, math.hypot(p1[0] - p0[0], p1[1] - p0[1]), a.kind)


def merge_collinear_segments(segments: list[Segment]) -> list[Segment]:
    merged = segments[:]
    changed = True
    while changed:
        changed = False
        out: list[Segment] = []
        consumed = [False] * len(merged)
        for i, seg in enumerate(merged):
            if consumed[i]:
                continue
            current = seg
            for j in range(i + 1, len(merged)):
                if consumed[j]:
                    continue
                other = merged[j]
                if can_merge_segments(current, other):
                    current = merge_two_segments(current, other)
                    consumed[j] = True
                    changed = True
            out.append(current)
            consumed[i] = True
        merged = out
    return merged


def detect_segments(search_gray: np.ndarray) -> tuple[list[Segment], list[Segment], list[Segment]]:
    lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_ADV)
    raw = lsd.detect(search_gray)[0]
    bases: list[Segment] = []
    lefts: list[Segment] = []
    rights: list[Segment] = []
    if raw is None:
        return bases, lefts, rights

    for line in raw:
        x1, y1, x2, y2 = map(float, line[0])
        length = math.hypot(x2 - x1, y2 - y1)
        if length < MIN_SEGMENT_LENGTH or length > MAX_SEGMENT_LENGTH:
            continue

        bucket = _orientation_bucket(_angle_deg((x1, y1), (x2, y2)))
        if bucket is None:
            continue

        if bucket == "BASE":
            if x1 <= x2:
                bases.append(Segment((x1, y1), (x2, y2), length, "BASE"))
            else:
                bases.append(Segment((x2, y2), (x1, y1), length, "BASE"))
            continue

        if y1 <= y2:
            top = (x1, y1)
            bottom = (x2, y2)
        else:
            top = (x2, y2)
            bottom = (x1, y1)

        if abs(top[0] - bottom[0]) < 2.0:
            continue
        if top[0] > bottom[0]:
            lefts.append(Segment(top, bottom, length, "LEFT"))
        else:
            rights.append(Segment(top, bottom, length, "RIGHT"))

    bases = merge_collinear_segments(bases)
    lefts = merge_collinear_segments(lefts)
    rights = merge_collinear_segments(rights)
    return bases, lefts, rights


def line_support(
    binary: np.ndarray,
    p0: tuple[float, float],
    p1: tuple[float, float],
    sample_count: int,
    radius: int = SAMPLE_RADIUS,
) -> float:
    h, w = binary.shape
    hits = 0
    total = 0
    for i in range(sample_count):
        t = i / (sample_count - 1) if sample_count > 1 else 0.5
        x = int(round(p0[0] + t * (p1[0] - p0[0])))
        y = int(round(p0[1] + t * (p1[1] - p0[1])))
        if not (0 <= x < w and 0 <= y < h):
            continue
        total += 1
        x0 = max(0, x - radius)
        x1 = min(w, x + radius + 1)
        y0 = max(0, y - radius)
        y1 = min(h, y + radius + 1)
        if np.any(binary[y0:y1, x0:x1] > 0):
            hits += 1
    return hits / total if total else 0.0


def base_segment_overlap(
    bases: list[Segment],
    left_base: tuple[float, float],
    right_base: tuple[float, float],
    side_length: float,
) -> float:
    expected_x0 = min(left_base[0], right_base[0])
    expected_x1 = max(left_base[0], right_base[0])
    expected_span = max(1.0, expected_x1 - expected_x0)
    expected_y = (left_base[1] + right_base[1]) / 2.0

    best = 0.0
    for seg in bases:
        if abs(seg.midpoint[1] - expected_y) > BASELINE_Y_TOLERANCE:
            continue
        if seg.length < 0.45 * side_length or seg.length > 1.4 * side_length:
            continue
        overlap_x0 = max(expected_x0, seg.left[0])
        overlap_x1 = min(expected_x1, seg.right[0])
        if overlap_x1 <= overlap_x0:
            continue
        overlap = (overlap_x1 - overlap_x0) / expected_span
        if overlap > best:
            best = overlap
    return float(best)


def interior_ink_ratio(binary: np.ndarray, polygon: np.ndarray, side_length: float) -> float:
    mask = np.zeros_like(binary)
    cv2.fillPoly(mask, [polygon.astype(np.int32)], 255)

    # Remove the border band so we measure only the real interior, not the outline.
    border_pad = max(4, int(round(side_length * 0.08)))
    if border_pad > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (border_pad * 2 + 1, border_pad * 2 + 1))
        mask = cv2.erode(mask, kernel, iterations=1)

    # Mask out the small center patch where the revision digit lives.
    cx = int(round(np.mean(polygon[:, 0])))
    cy = int(round(np.mean(polygon[:, 1])))
    digit_radius = max(8, int(round(side_length * 0.16)))
    cv2.circle(mask, (cx, cy), digit_radius, 0, -1)

    interior_pixels = int(cv2.countNonZero(mask))
    if interior_pixels <= 0:
        return 1.0
    ink_pixels = int(cv2.countNonZero(cv2.bitwise_and(binary, mask)))
    return ink_pixels / interior_pixels


def point_in_polygon(point: tuple[float, float], polygon: np.ndarray) -> bool:
    return cv2.pointPolygonTest(polygon.astype(np.float32), point, False) >= 0


def attach_digit(
    polygon: np.ndarray,
    digit_words: list[DigitWord],
    target_digit: str | None,
) -> DigitAttachment:
    inside: list[tuple[int, DigitWord]] = []
    for idx, word in enumerate(digit_words):
        if point_in_polygon(word.centroid, polygon):
            inside.append((idx, word))
    if not inside:
        return DigitAttachment(
            text=None,
            index=None,
            source=None,
            centroid=None,
            bbox=None,
        )
    if target_digit is not None:
        for idx, word in inside:
            if word.text == target_digit:
                return DigitAttachment(
                    text=word.text,
                    index=idx,
                    source=PDF_TEXT_LAYER_SOURCE,
                    centroid=word.centroid,
                    bbox=word.bbox,
                )
    idx, word = inside[0]
    return DigitAttachment(
        text=word.text,
        index=idx,
        source=PDF_TEXT_LAYER_SOURCE,
        centroid=word.centroid,
        bbox=word.bbox,
    )


def geometry_score(
    side_support: float,
    base_support: float,
    interior_ratio: float,
    base_overlap: float,
) -> float:
    interior_score = 1.0 - min(1.0, interior_ratio / max(INTERIOR_INK_RATIO_MAX, 1e-6))
    return (
        0.42 * side_support
        + 0.28 * base_support
        + 0.18 * interior_score
        + 0.12 * min(1.0, base_overlap / BASE_SEGMENT_BONUS_MIN)
    )


def line_intersection(a: Segment, b: Segment) -> tuple[float, float] | None:
    x1, y1 = a.p0
    x2, y2 = a.p1
    x3, y3 = b.p0
    x4, y4 = b.p1
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) <= 1e-6:
        return None
    det1 = x1 * y2 - y1 * x2
    det2 = x3 * y4 - y3 * x4
    px = (det1 * (x3 - x4) - (x1 - x2) * det2) / denom
    py = (det1 * (y3 - y4) - (y1 - y2) * det2) / denom
    return (float(px), float(py))


def x_at_y(seg: Segment, y: float) -> float | None:
    x0, y0 = seg.p0
    x1, y1 = seg.p1
    if abs(y1 - y0) <= 1e-6:
        return None
    t = (y - y0) / (y1 - y0)
    return float(x0 + t * (x1 - x0))


def build_candidates_from_intersections(
    binary: np.ndarray,
    bases: list[Segment],
    lefts: list[Segment],
    rights: list[Segment],
    digit_words: list[DigitWord],
    target_digit: str | None,
) -> list[TriangleCandidate]:
    candidates: list[TriangleCandidate] = []

    for left in lefts:
        for right in rights:
            if right.top[0] <= left.top[0]:
                continue

            apex = line_intersection(left, right)
            if apex is None:
                continue

            if math.hypot(apex[0] - left.top[0], apex[1] - left.top[1]) > APEX_ENDPOINT_DISTANCE_MAX:
                continue
            if math.hypot(apex[0] - right.top[0], apex[1] - right.top[1]) > APEX_ENDPOINT_DISTANCE_MAX:
                continue
            if apex[1] < min(left.top[1], right.top[1]) - APEX_EXTENSION_ABOVE_TOP_MAX:
                continue
            if apex[1] > min(left.top[1], right.top[1]) + APEX_EXTENSION_BELOW_TOP_MAX:
                continue
            if not (left.bottom[0] < apex[0] < right.bottom[0]):
                continue

            for base in bases:
                base_y = base.midpoint[1]
                if base_y <= apex[1] + 18.0:
                    continue

                lx = x_at_y(left, base_y)
                rx = x_at_y(right, base_y)
                if lx is None or rx is None:
                    continue
                if rx <= lx:
                    continue
                if base.right[0] < lx - 12.0 or base.left[0] > rx + 12.0:
                    continue

                left_base = (lx, base_y)
                right_base = (rx, base_y)
                side_len_left = math.hypot(left_base[0] - apex[0], left_base[1] - apex[1])
                side_len_right = math.hypot(right_base[0] - apex[0], right_base[1] - apex[1])
                side_mean = (side_len_left + side_len_right) / 2.0
                if side_mean < MIN_SEGMENT_LENGTH or side_mean > MAX_SEGMENT_LENGTH:
                    continue
                if abs(side_len_left - side_len_right) / side_mean > SIDE_LENGTH_RATIO_TOLERANCE:
                    continue

                base_length = right_base[0] - left_base[0]
                if abs(base_length - side_mean) / side_mean > BASE_LENGTH_RATIO_TOLERANCE:
                    continue

                height = ((left_base[1] + right_base[1]) / 2.0) - apex[1]
                expected_height = side_mean * math.sqrt(3.0) / 2.0
                if expected_height <= 0:
                    continue
                if abs(height - expected_height) / expected_height > HEIGHT_RATIO_TOLERANCE:
                    continue

                side_left_support = line_support(binary, apex, left_base, SIDE_SAMPLE_COUNT)
                side_right_support = line_support(binary, apex, right_base, SIDE_SAMPLE_COUNT)
                side_support = min(side_left_support, side_right_support)
                if side_support < SIDE_SUPPORT_MIN:
                    continue

                base_support = line_support(binary, left_base, right_base, BASE_SAMPLE_COUNT)
                base_overlap = base_segment_overlap([base], left_base, right_base, side_mean)
                if base_support < BASE_SUPPORT_MIN and base_overlap < BASE_SEGMENT_BONUS_MIN:
                    continue

                polygon = np.array([apex, left_base, right_base], dtype=np.int32)
                interior_ratio = interior_ink_ratio(binary, polygon, side_mean)
                if interior_ratio > INTERIOR_INK_RATIO_MAX:
                    continue

                geom = geometry_score(side_support, base_support, interior_ratio, base_overlap)
                if geom < GEOMETRY_SCORE_MIN:
                    continue

                digit_attachment = attach_digit(polygon, digit_words, target_digit)
                score = geom
                if digit_attachment.text is not None:
                    score += TEXT_DIGIT_BONUS
                    if target_digit is not None and digit_attachment.text == target_digit:
                        score += TARGET_DIGIT_BONUS
                elif geom < GEOMETRY_ONLY_SCORE_MIN:
                    continue

                candidates.append(
                    TriangleCandidate(
                        apex=apex,
                        left_base=left_base,
                        right_base=right_base,
                        side_length=side_mean,
                        side_support=side_support,
                        base_support=base_support,
                        interior_ink_ratio=interior_ratio,
                        base_segment_overlap=base_overlap,
                        geometry_score=geom,
                        score=score,
                        digit=digit_attachment.text,
                        digit_index=digit_attachment.index,
                        digit_source=digit_attachment.source,
                        digit_centroid=digit_attachment.centroid,
                        digit_bbox=digit_attachment.bbox,
                    )
                )
    return candidates


def build_candidates_from_endpoints(
    binary: np.ndarray,
    bases: list[Segment],
    lefts: list[Segment],
    rights: list[Segment],
    digit_words: list[DigitWord],
    target_digit: str | None,
) -> list[TriangleCandidate]:
    candidates: list[TriangleCandidate] = []

    for left in lefts:
        for right in rights:
            if right.top[0] <= left.top[0]:
                continue

            apex_distance = math.hypot(left.top[0] - right.top[0], left.top[1] - right.top[1])
            if apex_distance > APEX_DISTANCE_TOLERANCE:
                continue

            side_mean = (left.length + right.length) / 2.0
            if abs(left.length - right.length) / side_mean > SIDE_LENGTH_RATIO_TOLERANCE:
                continue

            if abs(left.bottom[1] - right.bottom[1]) > BASELINE_Y_TOLERANCE:
                continue
            if right.bottom[0] <= left.bottom[0]:
                continue

            base_length = math.hypot(right.bottom[0] - left.bottom[0], right.bottom[1] - left.bottom[1])
            if abs(base_length - side_mean) / side_mean > BASE_LENGTH_RATIO_TOLERANCE:
                continue

            apex = ((left.top[0] + right.top[0]) / 2.0, (left.top[1] + right.top[1]) / 2.0)
            left_base = left.bottom
            right_base = right.bottom

            height = ((left_base[1] + right_base[1]) / 2.0) - apex[1]
            expected_height = side_mean * math.sqrt(3.0) / 2.0
            if expected_height <= 0:
                continue
            if abs(height - expected_height) / expected_height > HEIGHT_RATIO_TOLERANCE:
                continue

            side_left_support = line_support(binary, apex, left_base, SIDE_SAMPLE_COUNT)
            side_right_support = line_support(binary, apex, right_base, SIDE_SAMPLE_COUNT)
            side_support = min(side_left_support, side_right_support)
            if side_support < SIDE_SUPPORT_MIN:
                continue

            base_support = line_support(binary, left_base, right_base, BASE_SAMPLE_COUNT)
            base_overlap = base_segment_overlap(bases, left_base, right_base, side_mean)
            if base_support < BASE_SUPPORT_MIN and base_overlap < BASE_SEGMENT_BONUS_MIN:
                continue

            polygon = np.array([apex, left_base, right_base], dtype=np.int32)
            interior_ratio = interior_ink_ratio(binary, polygon, side_mean)
            if interior_ratio > INTERIOR_INK_RATIO_MAX:
                continue

            geom = geometry_score(side_support, base_support, interior_ratio, base_overlap)
            if geom < GEOMETRY_SCORE_MIN:
                continue

            digit_attachment = attach_digit(polygon, digit_words, target_digit)
            score = geom
            if digit_attachment.text is not None:
                score += TEXT_DIGIT_BONUS
                if target_digit is not None and digit_attachment.text == target_digit:
                    score += TARGET_DIGIT_BONUS
            elif geom < GEOMETRY_ONLY_SCORE_MIN:
                continue

            candidates.append(
                TriangleCandidate(
                    apex=apex,
                    left_base=left_base,
                    right_base=right_base,
                    side_length=side_mean,
                    side_support=side_support,
                    base_support=base_support,
                    interior_ink_ratio=interior_ratio,
                    base_segment_overlap=base_overlap,
                    geometry_score=geom,
                    score=score,
                    digit=digit_attachment.text,
                    digit_index=digit_attachment.index,
                    digit_source=digit_attachment.source,
                    digit_centroid=digit_attachment.centroid,
                    digit_bbox=digit_attachment.bbox,
                )
            )
    return candidates


def build_candidates(
    binary: np.ndarray,
    bases: list[Segment],
    lefts: list[Segment],
    rights: list[Segment],
    digit_words: list[DigitWord],
    target_digit: str | None,
) -> list[TriangleCandidate]:
    endpoint_candidates = build_candidates_from_endpoints(binary, bases, lefts, rights, digit_words, target_digit)
    intersection_candidates = build_candidates_from_intersections(binary, bases, lefts, rights, digit_words, target_digit)
    return endpoint_candidates + intersection_candidates


def estimate_canonical_side_length(detections: list[TriangleCandidate]) -> float:
    if len(detections) < 3:
        return DEFAULT_CANONICAL_SIDE
    lengths = [d.side_length for d in detections]
    return float(np.median(np.asarray(lengths, dtype=np.float32)))


def build_candidates_from_fixed_size_bases(
    binary: np.ndarray,
    bases: list[Segment],
    digit_words: list[DigitWord],
    target_digit: str | None,
    canonical_side: float,
) -> list[TriangleCandidate]:
    candidates: list[TriangleCandidate] = []
    height = canonical_side * math.sqrt(3.0) / 2.0

    for seg in bases:
        if seg.length < FIXED_BASE_SEED_MIN or seg.length > canonical_side * FIXED_BASE_SEED_MAX_MULT:
            continue

        base_y = seg.midpoint[1]
        centers = (
            seg.midpoint[0],
            seg.left[0] + canonical_side / 2.0,
            seg.right[0] - canonical_side / 2.0,
        )

        for cx in centers:
            left_base = (cx - canonical_side / 2.0, base_y)
            right_base = (cx + canonical_side / 2.0, base_y)
            apex = (cx, base_y - height)

            overlap = max(0.0, min(right_base[0], seg.right[0]) - max(left_base[0], seg.left[0]))
            if overlap < max(FIXED_BASE_MIN_OVERLAP, FIXED_BASE_MIN_OVERLAP_FRAC * canonical_side):
                continue

            side_left_support = line_support(binary, apex, left_base, SIDE_SAMPLE_COUNT)
            side_right_support = line_support(binary, apex, right_base, SIDE_SAMPLE_COUNT)
            side_support = min(side_left_support, side_right_support)
            if side_support < FIXED_SIDE_SUPPORT_MIN:
                continue

            base_support = line_support(binary, left_base, right_base, BASE_SAMPLE_COUNT)
            polygon = np.array([apex, left_base, right_base], dtype=np.int32)
            interior_ratio = interior_ink_ratio(binary, polygon, canonical_side)
            if interior_ratio > FIXED_INTERIOR_INK_RATIO_MAX:
                continue

            interior_score = 1.0 - min(1.0, interior_ratio / FIXED_INTERIOR_INK_RATIO_MAX)
            overlap_score = min(1.0, overlap / canonical_side)
            geom = (
                0.52 * side_support
                + 0.16 * base_support
                + 0.20 * interior_score
                + 0.12 * overlap_score
            )
            if geom < FIXED_GEOMETRY_SCORE_MIN:
                continue

            digit_attachment = attach_digit(polygon, digit_words, target_digit)
            score = geom
            if digit_attachment.text is not None:
                score += TEXT_DIGIT_BONUS
                if target_digit is not None and digit_attachment.text == target_digit:
                    score += TARGET_DIGIT_BONUS
            elif geom < GEOMETRY_ONLY_SCORE_MIN:
                continue

            candidates.append(
                TriangleCandidate(
                    apex=apex,
                    left_base=left_base,
                    right_base=right_base,
                    side_length=canonical_side,
                    side_support=side_support,
                    base_support=base_support,
                    interior_ink_ratio=interior_ratio,
                    base_segment_overlap=overlap / canonical_side,
                    geometry_score=geom,
                    score=score,
                    digit=digit_attachment.text,
                    digit_index=digit_attachment.index,
                    digit_source=digit_attachment.source,
                    digit_centroid=digit_attachment.centroid,
                    digit_bbox=digit_attachment.bbox,
                )
            )
    return candidates


def dedupe_candidates(candidates: list[TriangleCandidate]) -> list[TriangleCandidate]:
    kept: list[TriangleCandidate] = []
    used_digit_indices: set[int] = set()

    for cand in sorted(candidates, key=lambda c: (-c.score, -c.geometry_score)):
        if cand.digit_index is not None and cand.digit_index in used_digit_indices:
            continue
        if any(math.hypot(cand.centroid[0] - k.centroid[0], cand.centroid[1] - k.centroid[1]) < NMS_RADIUS for k in kept):
            continue
        kept.append(cand)
        if cand.digit_index is not None:
            used_digit_indices.add(cand.digit_index)
    return kept


def extract_ground_truth_centers(overlay_path: Path) -> list[tuple[float, float]]:
    img = cv2.imread(str(overlay_path))
    if img is None:
        raise FileNotFoundError(overlay_path)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 40, 40), (90, 255, 255))
    n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

    centers: list[tuple[float, float]] = []
    for idx in range(1, n_labels):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < 50:
            continue
        cx, cy = centroids[idx]
        centers.append((float(cx), float(cy)))
    return centers


def evaluate_against_ground_truth(
    detections: list[TriangleCandidate],
    gt_centers: list[tuple[float, float]],
) -> tuple[int, int, int]:
    used: set[int] = set()
    matched = 0
    for det in detections:
        best_idx = None
        best_dist = float("inf")
        for idx, gt in enumerate(gt_centers):
            if idx in used:
                continue
            dist = math.hypot(det.centroid[0] - gt[0], det.centroid[1] - gt[1])
            if dist < best_dist:
                best_dist = dist
                best_idx = idx
        if best_idx is not None and best_dist <= GT_MATCH_RADIUS:
            used.add(best_idx)
            matched += 1
    misses = len(gt_centers) - matched
    false_positives = len(detections) - matched
    return matched, misses, false_positives


def overlay_detections(
    gray: np.ndarray,
    detections: list[TriangleCandidate],
    target_digit: str | None,
) -> np.ndarray:
    out = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for det in detections:
        if det.digit is None:
            color = (0, 165, 255)  # orange: geometry-only
            label = "?"
        elif target_digit is not None and det.digit == target_digit:
            color = (0, 220, 0)  # bright green: target digit
            label = det.digit
        elif target_digit is None:
            color = (0, 220, 0)
            label = det.digit
        else:
            color = (160, 160, 160)  # grey: other digit
            label = det.digit

        cv2.polylines(out, [det.polygon], isClosed=True, color=color, thickness=4)
        cx, cy = map(int, det.centroid)
        cv2.putText(
            out,
            f"{label} {det.score:.2f}",
            (cx - 25, cy + 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )
    return out


def partition_detections(
    detections: list[TriangleCandidate],
    target_digit: str | None,
) -> tuple[list[TriangleCandidate], list[TriangleCandidate], list[TriangleCandidate]]:
    active: list[TriangleCandidate] = []
    historical: list[TriangleCandidate] = []
    geometry_only: list[TriangleCandidate] = []
    for det in detections:
        if det.digit is None:
            geometry_only.append(det)
        elif target_digit is None or det.digit == target_digit:
            active.append(det)
        else:
            historical.append(det)
    return active, historical, geometry_only


def digit_counts(detections: list[TriangleCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for det in detections:
        if det.digit is None:
            continue
        counts[det.digit] = counts.get(det.digit, 0) + 1
    return counts


def digit_source_counts(detections: list[TriangleCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for det in detections:
        if det.digit is None or det.digit_source is None:
            continue
        counts[det.digit_source] = counts.get(det.digit_source, 0) + 1
    return counts


def serialize_detection(det: TriangleCandidate, target_digit: str | None) -> dict:
    status = "geometry_only"
    if det.digit is not None:
        status = "active" if target_digit is None or det.digit == target_digit else "historical"
    return {
        "digit": det.digit,
        "digit_source": det.digit_source,
        "digit_centroid": (
            {
                "x": float(det.digit_centroid[0]),
                "y": float(det.digit_centroid[1]),
            }
            if det.digit_centroid is not None
            else None
        ),
        "digit_bbox": (
            {
                "x0": float(det.digit_bbox[0]),
                "y0": float(det.digit_bbox[1]),
                "x1": float(det.digit_bbox[2]),
                "y1": float(det.digit_bbox[3]),
            }
            if det.digit_bbox is not None
            else None
        ),
        "status": status,
        "center": {
            "x": float(det.centroid[0]),
            "y": float(det.centroid[1]),
        },
        "triangle": {
            "apex": {"x": float(det.apex[0]), "y": float(det.apex[1])},
            "left_base": {"x": float(det.left_base[0]), "y": float(det.left_base[1])},
            "right_base": {"x": float(det.right_base[0]), "y": float(det.right_base[1])},
        },
        "side_length_px": float(det.side_length),
        "score": float(det.score),
        "geometry_score": float(det.geometry_score),
        "side_support": float(det.side_support),
        "base_support": float(det.base_support),
        "interior_ink_ratio": float(det.interior_ink_ratio),
        "base_segment_overlap": float(det.base_segment_overlap),
    }


def write_results_json(
    output_path: Path,
    image_path: Path,
    pdf_path: Path | None,
    page_index: int,
    target_digit: str | None,
    pdf_digit_words_count: int,
    canonical_side: float,
    detections: list[TriangleCandidate],
) -> None:
    active, historical, geometry_only = partition_detections(detections, target_digit)
    payload = {
        "image_path": str(image_path),
        "pdf_path": str(pdf_path) if pdf_path is not None else None,
        "page_index": int(page_index),
        "target_digit": target_digit,
        "pdf_digit_words_count": int(pdf_digit_words_count),
        "canonical_side_px": float(canonical_side),
        "summary": {
            "total_detections": len(detections),
            "active_count": len(active),
            "historical_count": len(historical),
            "geometry_only_count": len(geometry_only),
            "by_digit": digit_counts(detections),
            "by_digit_source": digit_source_counts(detections),
        },
        "all_deltas": [serialize_detection(det, target_digit) for det in detections],
        "active_deltas": [serialize_detection(det, target_digit) for det in active],
        "historical_deltas": [serialize_detection(det, target_digit) for det in historical],
        "geometry_only_deltas": [serialize_detection(det, target_digit) for det in geometry_only],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def print_summary(
    bases: list[Segment],
    lefts: list[Segment],
    rights: list[Segment],
    target_digit: str | None,
    pdf_digit_words_count: int,
    canonical_side: float,
    seed_detections: list[TriangleCandidate],
    raw_candidates: list[TriangleCandidate],
    detections: list[TriangleCandidate],
    gt_centers: list[tuple[float, float]] | None,
) -> None:
    active, historical, geometry_only = partition_detections(detections, target_digit)
    counts = digit_counts(detections)
    source_counts = digit_source_counts(detections)
    print(f"segments: base={len(bases)} left={len(lefts)} right={len(rights)}")
    print(f"cached PDF digit glyphs: {pdf_digit_words_count}")
    print(f"seed detections for size calibration: {len(seed_detections)}")
    print(f"canonical side length: {canonical_side:.2f}px")
    print(f"triangle candidates before NMS: {len(raw_candidates)}")
    print(f"final detections after NMS: {len(detections)}")
    print("detections by digit:")
    if counts:
        for digit in sorted(counts, key=lambda d: int(d)):
            suffix = "  <-- target" if target_digit is not None and digit == target_digit else ""
            print(f"  digit '{digit}': {counts[digit]}{suffix}")
    else:
        print("  none with attached digits")
    if source_counts:
        print("digit attachment sources:")
        for source, count in sorted(source_counts.items()):
            print(f"  {source}: {count}")
    if geometry_only:
        print(f"  geometry-only: {len(geometry_only)}")
    if target_digit is not None:
        print(f"active anchors for revision '{target_digit}': {len(active)}")
        print(f"historical deltas kept for context: {len(historical)}")
    for idx, det in enumerate(sorted(detections, key=lambda d: (d.centroid[1], d.centroid[0])), start=1):
        cx, cy = det.centroid
        digit_label = det.digit or "?"
        if det.digit_source:
            digit_label = f"{digit_label}@{det.digit_source}"
        print(
            f"  #{idx:02d} center=({cx:.1f},{cy:.1f}) digit={digit_label} "
            f"score={det.score:.3f} geom={det.geometry_score:.3f} "
            f"side={det.side_support:.2f} base={det.base_support:.2f} "
            f"interior={det.interior_ink_ratio:.3f}"
        )
    if gt_centers is not None:
        matched, misses, false_positives = evaluate_against_ground_truth(detections, gt_centers)
        print(
            f"ground truth: matched={matched} / {len(gt_centers)} "
            f"misses={misses} false_positives={false_positives}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE, help="Input grayscale/delta-search image.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF, help="Source PDF for text-layer digit lookup.")
    parser.add_argument("--page", type=int, default=DEFAULT_PAGE, help="Zero-indexed page number in --pdf.")
    parser.add_argument("--target-digit", type=str, default="1", help="Expected revision digit; used only as a bonus.")
    parser.add_argument("--ground-truth-overlay", type=Path, default=None, help="Optional highlighted PNG for quick scoring.")
    parser.add_argument("--out", type=Path, default=None, help="Output overlay PNG path.")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional JSON output path for all/active delta handoff.")
    args = parser.parse_args()

    image_path = args.image if args.image.is_absolute() else (Path.cwd() / args.image).resolve()
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        print(f"Could not read image: {image_path}")
        return 1

    pdf_path: Path | None = None
    pdf_digit_words: list[DigitWord] = []
    if args.pdf:
        pdf_path = args.pdf if args.pdf.is_absolute() else (Path.cwd() / args.pdf).resolve()
        if pdf_path.exists():
            # Geometry comes from the denoised raster. Digit labels and their
            # coordinates come from the PDF text layer cached here once.
            pdf_digit_words = extract_digit_words_in_pixels(pdf_path, args.page, dpi=DEFAULT_DPI)
        else:
            print(f"warning: pdf not found, skipping text-layer check: {pdf_path}")

    search_gray, binary = preprocess_image(gray)
    bases, lefts, rights = detect_segments(search_gray)
    seed_candidates = build_candidates(binary, bases, lefts, rights, pdf_digit_words, args.target_digit)
    seed_detections = dedupe_candidates(seed_candidates)
    canonical_side = estimate_canonical_side_length(seed_detections)
    fixed_size_candidates = build_candidates_from_fixed_size_bases(
        binary,
        bases,
        pdf_digit_words,
        args.target_digit,
        canonical_side,
    )
    raw_candidates = seed_candidates + fixed_size_candidates
    detections = dedupe_candidates(raw_candidates)

    gt_centers = None
    gt_overlay_arg = args.ground_truth_overlay
    if gt_overlay_arg is None and image_path == DEFAULT_IMAGE:
        gt_overlay_arg = DEFAULT_GT_OVERLAY
    if gt_overlay_arg:
        gt_path = gt_overlay_arg if gt_overlay_arg.is_absolute() else (Path.cwd() / gt_overlay_arg).resolve()
        if gt_path.exists():
            gt_centers = extract_ground_truth_centers(gt_path)

    print_summary(
        bases,
        lefts,
        rights,
        args.target_digit,
        len(pdf_digit_words),
        canonical_side,
        seed_detections,
        raw_candidates,
        detections,
        gt_centers,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = args.out
    if out_path is None:
        out_path = OUTPUT_DIR / f"{image_path.stem}_delta_v4_overlay.png"
    overlay = overlay_detections(gray, detections, args.target_digit)
    cv2.imwrite(str(out_path), overlay)
    print(f"overlay -> {out_path}")

    json_out_path = args.json_out
    if json_out_path is None:
        json_out_path = out_path.with_name(f"{out_path.stem}_results.json")
    write_results_json(
        json_out_path,
        image_path,
        pdf_path,
        args.page,
        args.target_digit,
        len(pdf_digit_words),
        canonical_side,
        detections,
    )
    print(f"json -> {json_out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
