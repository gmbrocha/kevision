"""Δ revision-marker detector.

Find every equilateral-triangle outline on a drawing page that contains a
single revision digit (1, 2, 3, ...). For Rev N processing, callers can
filter to triangles whose enclosed digit == N.

Approach:
  1. Threshold the rendered page.
  2. findContours(RETR_LIST). For each contour:
     - skip too small / too large
     - take convex hull, simplify with approxPolyDP at ~5% perimeter epsilon
     - accept if the simplified hull has exactly 3 vertices forming a
       near-equilateral triangle (sides within 15% of each other,
       angles within 12 degrees of 60 deg).
  3. Cross-reference with PDF text layer to find a single-digit word whose
     centroid sits inside each triangle. Triangles with no digit are
     reported separately as candidate-but-unconfirmed.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import fitz
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_DIR = Path(__file__).parent
OUTPUT_DIR = EXPERIMENT_DIR / "output"

DEFAULT_DPI = 300

# Geometry tunables (px at 300 DPI)
APPROX_EPSILON_FRAC = 0.05       # 5% of perimeter for approxPolyDP
SIDE_LENGTH_TOLERANCE = 0.18     # sides may differ by up to 18%
ANGLE_TOLERANCE_DEG = 14.0       # each angle within 14 deg of 60
DIGIT_TEXTS = set("123456789")

# Δ size is per-PDF, not per-project. Two PDFs at the same render DPI can produce
# Δs at different pixel sizes if their internal user-space units differ. Solution:
# predict Δ size per-digit from the digit's bbox height, using a fixed ratio. The
# ratio itself is auto-calibrated on each page from any clean Tier-1 hits (with
# fallback to a default measured from AE109).
DELTA_SIDE_PER_DIGIT_HEIGHT_DEFAULT = 1.8   # ratio: Δ_side ≈ 1.8 × digit bbox height
TIER1_MIN_PERIMETER = 90    # widened to handle the multi-size case (sides ~30-130 px)
TIER1_MAX_PERIMETER = 400

# Tier 2 (digit-anchored outline + interior check) tunables
DELTA_LINE_THICKNESS = 3
DIGIT_BBOX_MAX_HEIGHT = 80        # Δ-internal digits are single small characters
DIGIT_BBOX_MAX_WIDTH = 50
DIGIT_BBOX_MIN_HEIGHT = 12        # filter out micro-text (subscripts, etc.)
TIER2_OUTLINE_DENSITY_THRESHOLD = 0.55   # fraction of outline samples that must be on ink
TIER2_INTERIOR_EMPTINESS_THRESHOLD = 0.80  # interior (excluding digit) must be mostly white
TIER2_DIGIT_BBOX_PAD = 4          # expand digit bbox by this many px when masking it out of interior
TIER2_OUTLINE_SAMPLES_PER_SIDE = 30      # how finely to sample each triangle side
TIER2_NEIGHBORHOOD_RADIUS = 3            # how far to look around each sample for an ink pixel
TIER2_CENTROID_SEARCH = (-8, -4, 0, 4, 8)  # offsets (px) to try for triangle centroid placement
TIER2_SIZE_SCALES = (0.85, 1.00, 1.15)  # try these multiples of the predicted Δ size per digit
TIER2_DEDUPE_RADIUS = 30          # px; if a Tier-2 hit lands within this of a Tier-1 hit, dedupe

# Δ-search-image preprocessing tunables
DELTA_SEARCH_INK_THRESHOLD = 100         # tighter than render threshold (200) -- only true ink survives
DELTA_SEARCH_VERTICAL_MIN_LENGTH = 30    # mask vertical lines longer than this (kills label rectangles)
DELTA_SEARCH_HORIZONTAL_MIN_LENGTH = 140 # mask horizontal lines longer than this (kills walls)
                                         # NB: Δ has 1 horizontal side; with sides up to ~120px we keep
                                         # the Δ base intact but kill walls/dimensions
DELTA_SEARCH_BLOB_AREA_MIN = 250         # filled blobs >= this many px AND >= 65% density get masked
DELTA_SEARCH_BLOB_DENSITY_MIN = 0.65


@dataclass
class DeltaCandidate:
    polygon: np.ndarray  # 3x2 int array of triangle vertices in pixel coords
    centroid: tuple[float, float]
    perimeter: float
    side_lengths: tuple[float, float, float]
    angles_deg: tuple[float, float, float]


@dataclass
class DeltaMarker:
    candidate: DeltaCandidate
    digit: str | None  # "1" / "2" / ... or None if no digit found inside
    digit_position: tuple[float, float] | None
    tier: int = 1                 # 1 = clean equilateral contour; 2 = digit-anchored template
    confidence: float = 1.0       # only meaningful for Tier 2 (template match score)


# ---------------------------------------------------------------------------
# PDF rendering and text extraction (handles page rotation)
# ---------------------------------------------------------------------------


def _native_to_pixel_matrix(page: fitz.Page, dpi: int) -> fitz.Matrix:
    """Matrix that maps native (un-rotated) PDF coords to displayed pixel coords.

    PyMuPDF gotcha: page.get_pixmap(matrix=Matrix(zoom, zoom)) auto-applies
    page.rotation; the rendered pixmap is in DISPLAY orientation. But
    page.get_text("words") returns text in NATIVE coords. To map those text
    bboxes into the rendered pixel space we apply page.rotation_matrix first
    (native -> displayed PDF units) then scale by zoom (PDF units -> pixels).
    """
    zoom = dpi / 72.0
    return page.rotation_matrix * fitz.Matrix(zoom, zoom)


def render_page_gray(pdf_path: Path, page_index: int, dpi: int = DEFAULT_DPI) -> tuple[np.ndarray, fitz.Matrix]:
    """Render a page to grayscale at `dpi`. Returns (image, native->pixel matrix).

    Image is in DISPLAYED orientation (PyMuPDF auto-applies page.rotation when
    given a plain scale matrix). Text bboxes can be mapped into the same
    pixel space via `rect * native_to_pixel`.
    """
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        zoom = dpi / 72.0
        # IMPORTANT: pass scale-only here. PyMuPDF auto-applies page.rotation.
        # Composing with page.rotation_matrix would suppress the auto-rotate.
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        native_to_pixel = _native_to_pixel_matrix(page, dpi)
    finally:
        doc.close()
    return img, native_to_pixel


def extract_digit_words_in_pixels(pdf_path: Path, page_index: int, dpi: int = DEFAULT_DPI) -> list[dict]:
    """Return single-digit text words on the page with bboxes mapped to pixel coords."""
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        mat = _native_to_pixel_matrix(page, dpi)
        out = []
        for w in page.get_text("words"):
            text = (w[4] or "").strip()
            if text not in DIGIT_TEXTS:
                continue
            rect = fitz.Rect(w[0], w[1], w[2], w[3]) * mat
            rect.normalize()
            cx = (rect.x0 + rect.x1) / 2.0
            cy = (rect.y0 + rect.y1) / 2.0
            bh = rect.y1 - rect.y0
            bw = rect.x1 - rect.x0
            out.append({
                "text": text,
                "bbox": (rect.x0, rect.y0, rect.x1, rect.y1),
                "centroid": (cx, cy),
                "height": float(bh),
                "width": float(bw),
            })
    finally:
        doc.close()
    return out


# ---------------------------------------------------------------------------
# Δ-search image preprocessing
# ---------------------------------------------------------------------------


def build_delta_search_image(gray: np.ndarray) -> np.ndarray:
    """Produce a temporary "Δ-search" version of the page with non-Δ stuff masked.

    Strips:
      - greyscale / faint linework (tight ink threshold)
      - long vertical lines (Δs have NO vertical sides; rectangles do, so
        label-rectangles vanish)
      - long horizontal lines (walls, dimensions; Δs have 1 short horizontal
        side that survives the length cutoff)
      - filled blobs (column squares, solid symbols)

    Original `gray` is untouched. Returned image is the same dtype as `gray`,
    with masked features painted white (255).
    """
    out = gray.copy()
    # Tight threshold: gray pixels (faint background, bleed-through) -> white
    out[out > DELTA_SEARCH_INK_THRESHOLD] = 255

    # Build inverted binary for line/blob detection
    _, binary = cv2.threshold(out, DELTA_SEARCH_INK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)

    # Long vertical lines
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, DELTA_SEARCH_VERTICAL_MIN_LENGTH))
    v_lines = cv2.dilate(cv2.erode(binary, v_kernel), v_kernel)

    # Long horizontal lines (Δ base survives the length cutoff)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (DELTA_SEARCH_HORIZONTAL_MIN_LENGTH, 1))
    h_lines = cv2.dilate(cv2.erode(binary, h_kernel), h_kernel)

    # Filled blobs: connected components above area threshold AND high fill density
    blob_mask = np.zeros_like(binary)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    for i in range(1, n_labels):
        x, y, w, h, area = stats[i]
        if area < DELTA_SEARCH_BLOB_AREA_MIN:
            continue
        bbox_area = w * h
        if bbox_area <= 0:
            continue
        density = area / bbox_area
        if density >= DELTA_SEARCH_BLOB_DENSITY_MIN:
            blob_mask[labels == i] = 255

    # Mask = union of vertical/horizontal/blob; paint white in the output gray
    mask = cv2.bitwise_or(cv2.bitwise_or(v_lines, h_lines), blob_mask)
    # Slight dilation of the mask to absorb anti-aliasing fringe
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    out[mask > 0] = 255
    return out


# ---------------------------------------------------------------------------
# Triangle geometry
# ---------------------------------------------------------------------------


def _polygon_centroid(poly: np.ndarray) -> tuple[float, float]:
    pts = poly.reshape(-1, 2).astype(np.float64)
    return (float(pts[:, 0].mean()), float(pts[:, 1].mean()))


def _side_lengths(poly: np.ndarray) -> tuple[float, float, float]:
    pts = poly.reshape(-1, 2).astype(np.float64)
    a = float(np.linalg.norm(pts[1] - pts[0]))
    b = float(np.linalg.norm(pts[2] - pts[1]))
    c = float(np.linalg.norm(pts[0] - pts[2]))
    return (a, b, c)


def _interior_angles_deg(poly: np.ndarray) -> tuple[float, float, float]:
    pts = poly.reshape(-1, 2).astype(np.float64)
    angles = []
    for i in range(3):
        prev_pt = pts[(i - 1) % 3]
        curr_pt = pts[i]
        next_pt = pts[(i + 1) % 3]
        v1 = prev_pt - curr_pt
        v2 = next_pt - curr_pt
        denom = (np.linalg.norm(v1) * np.linalg.norm(v2)) or 1e-9
        cos_a = float(np.clip(np.dot(v1, v2) / denom, -1.0, 1.0))
        angles.append(float(np.degrees(np.arccos(cos_a))))
    return tuple(angles)  # type: ignore[return-value]


def _is_equilateral(side_lens: tuple[float, float, float], angles_deg: tuple[float, float, float]) -> bool:
    a, b, c = side_lens
    longest = max(a, b, c)
    shortest = min(a, b, c)
    if shortest <= 0:
        return False
    if (longest - shortest) / longest > SIDE_LENGTH_TOLERANCE:
        return False
    for ang in angles_deg:
        if abs(ang - 60.0) > ANGLE_TOLERANCE_DEG:
            return False
    return True


def _point_in_polygon(point: tuple[float, float], poly: np.ndarray) -> bool:
    return cv2.pointPolygonTest(poly.astype(np.float32), point, False) >= 0


# ---------------------------------------------------------------------------
# Detection pipeline
# ---------------------------------------------------------------------------


def find_triangle_candidates(gray: np.ndarray) -> list[DeltaCandidate]:
    """Find candidate equilateral triangles on a grayscale page."""
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    # light dilate so thin triangle outlines connect cleanly through any small breaks
    binary = cv2.dilate(binary, np.ones((2, 2), np.uint8), iterations=1)
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    candidates: list[DeltaCandidate] = []
    for contour in contours:
        perimeter = float(cv2.arcLength(contour, closed=True))
        if perimeter < TIER1_MIN_PERIMETER or perimeter > TIER1_MAX_PERIMETER:
            continue
        if len(contour) < 6:
            continue
        try:
            hull = cv2.convexHull(contour, returnPoints=True)
        except cv2.error:
            continue
        hull_perim = float(cv2.arcLength(hull, closed=True))
        if hull_perim < TIER1_MIN_PERIMETER:
            continue
        approx = cv2.approxPolyDP(hull, APPROX_EPSILON_FRAC * hull_perim, closed=True)
        if approx.shape[0] != 3:
            continue
        side_lens = _side_lengths(approx)
        angles = _interior_angles_deg(approx)
        if not _is_equilateral(side_lens, angles):
            continue
        candidates.append(
            DeltaCandidate(
                polygon=approx.reshape(3, 2),
                centroid=_polygon_centroid(approx),
                perimeter=hull_perim,
                side_lengths=side_lens,
                angles_deg=angles,
            )
        )
    return candidates


def _dedupe_candidates(candidates: list[DeltaCandidate], min_centroid_dist: float = 8.0) -> list[DeltaCandidate]:
    """Greedy NMS: a single triangle outline can produce two contours (outer + inner edge)."""
    keep: list[DeltaCandidate] = []
    for cand in sorted(candidates, key=lambda c: -c.perimeter):
        too_close = False
        for k in keep:
            d = ((cand.centroid[0] - k.centroid[0]) ** 2 + (cand.centroid[1] - k.centroid[1]) ** 2) ** 0.5
            if d < min_centroid_dist:
                too_close = True
                break
        if not too_close:
            keep.append(cand)
    return keep


def assign_digits(candidates: list[DeltaCandidate], digit_words: list[dict]) -> list[DeltaMarker]:
    out: list[DeltaMarker] = []
    used_words = set()
    for cand in candidates:
        chosen_text = None
        chosen_centroid = None
        for i, w in enumerate(digit_words):
            if i in used_words:
                continue
            if _point_in_polygon(w["centroid"], cand.polygon):
                chosen_text = w["text"]
                chosen_centroid = w["centroid"]
                used_words.add(i)
                break
        out.append(DeltaMarker(candidate=cand, digit=chosen_text, digit_position=chosen_centroid))
    return out


# ---------------------------------------------------------------------------
# Tier 2: digit-anchored template matching
# ---------------------------------------------------------------------------


def _equilateral_vertices(centroid: tuple[float, float], side: float, orientation: str) -> np.ndarray:
    """Return the 3 vertices of an equilateral triangle with given centroid + side.

    For 'up' (▲): apex at top.
    For 'down' (▽): apex at bottom.
    """
    cx, cy = centroid
    r = side / np.sqrt(3.0)        # centroid -> vertex distance
    half = side / 2.0
    inradius = side / (2.0 * np.sqrt(3.0))
    if orientation == "up":
        return np.array([
            [cx,        cy - r],
            [cx - half, cy + inradius],
            [cx + half, cy + inradius],
        ], dtype=np.float64)
    return np.array([
        [cx,        cy + r],
        [cx - half, cy - inradius],
        [cx + half, cy - inradius],
    ], dtype=np.float64)


def _interior_emptiness(
    binary: np.ndarray,
    vertices: np.ndarray,
    digit_bbox: tuple[float, float, float, float],
    digit_pad: int = TIER2_DIGIT_BBOX_PAD,
) -> float:
    """Fraction of pixels inside the triangle (excluding the digit's bbox) that are NOT ink.

    A real Δ marker has only the digit inside; surrounding interior is white. A
    false-positive position (e.g., inside a dense drawing region) has lots of
    ink in the triangle interior even excluding the digit -> low emptiness.

    `binary` is foreground=white. Returns 1.0 = fully empty, 0.0 = fully filled.
    """
    h, w = binary.shape
    # Triangle interior mask
    tri_mask = np.zeros_like(binary)
    cv2.fillPoly(tri_mask, [vertices.astype(np.int32)], 255)
    # Subtract the digit's bbox (with a little pad)
    dx0, dy0, dx1, dy1 = digit_bbox
    dx0 = max(0, int(round(dx0)) - digit_pad)
    dy0 = max(0, int(round(dy0)) - digit_pad)
    dx1 = min(w, int(round(dx1)) + digit_pad)
    dy1 = min(h, int(round(dy1)) + digit_pad)
    if dx1 > dx0 and dy1 > dy0:
        tri_mask[dy0:dy1, dx0:dx1] = 0
    interior_pixels = int(cv2.countNonZero(tri_mask))
    if interior_pixels == 0:
        return 0.0
    ink_in_interior = int(cv2.countNonZero(cv2.bitwise_and(binary, tri_mask)))
    return 1.0 - (ink_in_interior / interior_pixels)


def _outline_density(
    binary: np.ndarray,
    centroid: tuple[float, float],
    side: float,
    orientation: str,
    samples_per_side: int = TIER2_OUTLINE_SAMPLES_PER_SIDE,
    neighborhood_radius: int = TIER2_NEIGHBORHOOD_RADIUS,
) -> float:
    """Fraction of points along the expected triangle outline that land on ink pixels.

    `binary` must be foreground=white (so non-zero = ink).
    Samples points along each of the 3 sides; for each, looks within a small
    neighborhood for any ink pixel. Tolerates partial occlusion gracefully:
    if the cloud arc replaces part of the outline with cloud-arc ink, those
    samples still count as positive (they're still on dark pixels).
    """
    vertices = _equilateral_vertices(centroid, side, orientation)
    h, w = binary.shape
    total = 0
    hits = 0
    for i in range(3):
        v0 = vertices[i]
        v1 = vertices[(i + 1) % 3]
        for s in range(samples_per_side):
            t = s / (samples_per_side - 1) if samples_per_side > 1 else 0.5
            sx = int(round(v0[0] + t * (v1[0] - v0[0])))
            sy = int(round(v0[1] + t * (v1[1] - v0[1])))
            if not (0 <= sx < w and 0 <= sy < h):
                continue
            total += 1
            x_lo = max(0, sx - neighborhood_radius)
            x_hi = min(w, sx + neighborhood_radius + 1)
            y_lo = max(0, sy - neighborhood_radius)
            y_hi = min(h, sy + neighborhood_radius + 1)
            if binary[y_lo:y_hi, x_lo:x_hi].any():
                hits += 1
    if total == 0:
        return 0.0
    return hits / total


def calibrate_delta_size_ratio(tier1_deltas: list[DeltaMarker], digit_words: list[dict]) -> float | None:
    """From clean Tier-1 hits with attributed digits, compute the per-page
    ratio (Δ_side / digit_height). Returns None if too few samples.

    The ratio is then used to predict Δ size for digits that don't have a clean
    Tier-1 detection (so Tier 2 can target the right size).
    """
    digit_height_by_centroid = {(round(d["centroid"][0], 1), round(d["centroid"][1], 1)): d["height"] for d in digit_words}
    samples: list[float] = []
    for d in tier1_deltas:
        if d.digit_position is None:
            continue
        key = (round(d.digit_position[0], 1), round(d.digit_position[1], 1))
        h = digit_height_by_centroid.get(key)
        if h is None or h <= 0:
            continue
        side_mean = float(np.mean(d.candidate.side_lengths))
        samples.append(side_mean / h)
    if not samples:
        return None
    return float(np.median(samples))


def find_digit_anchored_deltas(
    gray: np.ndarray,
    digit_words: list[dict],
    delta_size_ratio: float = DELTA_SIDE_PER_DIGIT_HEIGHT_DEFAULT,
    excluded_digit_centroids: list[tuple[float, float]] | None = None,
    threshold: float = TIER2_OUTLINE_DENSITY_THRESHOLD,
    debug_target_digit: str | None = None,
) -> list[DeltaMarker]:
    """For each candidate digit, check whether a Δ outline exists around it.

    Predicts Δ size per-digit via `digit.height * delta_size_ratio`, then
    samples along the expected triangle outline + checks interior emptiness
    at multiple sub-scales (TIER2_SIZE_SCALES). This handles per-page Δ-size
    variation that we discovered exists between AE109 and AE122.

    `gray` should be the Δ-search-image (post-denoise), not the raw rendered page.
    """
    excluded = excluded_digit_centroids or []
    _, binary = cv2.threshold(gray, DELTA_SEARCH_INK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)

    out: list[DeltaMarker] = []
    for digit in digit_words:
        bbox = digit["bbox"]
        bh = float(digit["height"])
        bw = float(digit["width"])
        if bh > DIGIT_BBOX_MAX_HEIGHT or bw > DIGIT_BBOX_MAX_WIDTH:
            continue
        if bh < DIGIT_BBOX_MIN_HEIGHT:
            continue

        cx, cy = digit["centroid"]
        if any(((cx - ex) ** 2 + (cy - ey) ** 2) ** 0.5 < TIER2_DEDUPE_RADIUS for ex, ey in excluded):
            continue

        predicted_side = bh * delta_size_ratio
        candidate_sides = [predicted_side * s for s in TIER2_SIZE_SCALES]

        best_density = 0.0
        best_emptiness = 0.0
        best_side: float | None = None
        best_centroid: tuple[float, float] | None = None
        best_orientation: str | None = None
        for side in candidate_sides:
            for dx in TIER2_CENTROID_SEARCH:
                for dy in TIER2_CENTROID_SEARCH:
                    for orient in ("up", "down"):
                        centroid = (cx + dx, cy + dy)
                        density = _outline_density(binary, centroid, side, orient)
                        if density < threshold:
                            continue
                        vertices = _equilateral_vertices(centroid, side, orient)
                        emptiness = _interior_emptiness(binary, vertices, bbox)
                        if emptiness < TIER2_INTERIOR_EMPTINESS_THRESHOLD:
                            continue
                        if density > best_density:
                            best_density = density
                            best_emptiness = emptiness
                            best_side = side
                            best_centroid = centroid
                            best_orientation = orient

        if debug_target_digit and digit["text"] == debug_target_digit:
            print(f"    [debug] digit '{digit['text']}' h={bh:.0f} predicted_side={predicted_side:.0f} "
                  f"best_density={best_density:.2f} best_side={best_side} "
                  f"orient={best_orientation}")

        if best_centroid is None or best_orientation is None or best_side is None:
            continue

        polygon = _equilateral_vertices(best_centroid, best_side, best_orientation).astype(np.int32)
        if not _point_in_polygon((cx, cy), polygon):
            continue

        sides = _side_lengths(polygon)
        angles = _interior_angles_deg(polygon)
        candidate = DeltaCandidate(
            polygon=polygon,
            centroid=_polygon_centroid(polygon),
            perimeter=float(sum(sides)),
            side_lengths=sides,
            angles_deg=angles,
        )
        out.append(DeltaMarker(
            candidate=candidate,
            digit=digit["text"],
            digit_position=(cx, cy),
            tier=2,
            confidence=float(best_density),
        ))
    return out


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------


def overlay_deltas(
    gray: np.ndarray,
    deltas: list[DeltaMarker],
    target_digit: str | None = None,
) -> np.ndarray:
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for d in deltas:
        digit = d.digit
        if digit is None:
            color = (60, 60, 200)  # red — candidate triangle, no digit
            label = "?"
        elif target_digit is not None and digit == target_digit:
            # bright green for tier 1, slightly cyan-shifted for tier 2 to distinguish
            color = (0, 200, 0) if d.tier == 1 else (200, 200, 0)
            label = digit if d.tier == 1 else f"{digit}*"  # asterisk = template-anchored
        else:
            color = (140, 140, 140)  # grey — older revision triangle
            label = digit if d.tier == 1 else f"{digit}*"
        cv2.polylines(bgr, [d.candidate.polygon.astype(np.int32)], isClosed=True, color=color, thickness=4)
        cx, cy = int(d.candidate.centroid[0]), int(d.candidate.centroid[1])
        cv2.putText(bgr, label, (cx - 12, cy + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, color, 4)
    return bgr


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path, help="PDF path")
    parser.add_argument("--page", type=int, default=0, help="Zero-indexed page number")
    parser.add_argument("--target-digit", type=str, default=None,
                        help="Highlight only Δs containing this digit (e.g., '2' for Rev 2)")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output PNG path (defaults to output/<pdf_stem>_p<page>_deltas.png)")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    args = parser.parse_args()

    pdf_path = args.pdf if args.pdf.is_absolute() else (Path.cwd() / args.pdf).resolve()
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    gray, _ = render_page_gray(pdf_path, args.page, dpi=args.dpi)
    print(f"Rendered {pdf_path.name} page {args.page} at {args.dpi} DPI -> {gray.shape[1]}x{gray.shape[0]}")

    # Build the Δ-search image (denoised version used for both Tier 1 and Tier 2)
    delta_search_img = build_delta_search_image(gray)
    save_path = OUTPUT_DIR / f"{pdf_path.stem}_p{args.page}_delta_search.png"
    cv2.imwrite(str(save_path), delta_search_img)
    print(f"  delta-search image (denoised) -> {save_path.name}")

    digit_words = extract_digit_words_in_pixels(pdf_path, args.page, dpi=args.dpi)
    print(f"  PDF single-digit text words on page: {len(digit_words)}")

    # Tier 1: clean equilateral triangle contours on the denoised image
    candidates = _dedupe_candidates(find_triangle_candidates(delta_search_img))
    print(f"\nTier 1 (clean equilateral contour on denoised image, perim {TIER1_MIN_PERIMETER}-{TIER1_MAX_PERIMETER}px):")
    print(f"  triangle candidates after NMS: {len(candidates)}")
    tier1_deltas = assign_digits(candidates, digit_words)
    tier1_with_digit = [d for d in tier1_deltas if d.digit is not None]
    tier1_no_digit = [d for d in tier1_deltas if d.digit is None]
    print(f"  with digit inside (real markers): {len(tier1_with_digit)}")
    print(f"  no digit (candidate triangle, no enclosed digit): {len(tier1_no_digit)}")

    # Calibrate per-page Δ-side / digit-height ratio from Tier 1 hits.
    calibrated_ratio = calibrate_delta_size_ratio(tier1_with_digit, digit_words)
    if calibrated_ratio is not None:
        ratio = calibrated_ratio
        print(f"  calibrated delta_side/digit_height ratio from Tier 1: {ratio:.2f}")
    else:
        ratio = DELTA_SIDE_PER_DIGIT_HEIGHT_DEFAULT
        print(f"  no Tier 1 hits to calibrate; using default ratio {ratio:.2f}")

    # Tier 2: per-digit predicted size, multi-scale around it
    tier1_digit_positions = [d.digit_position for d in tier1_with_digit if d.digit_position is not None]
    tier2_deltas = find_digit_anchored_deltas(
        delta_search_img, digit_words,
        delta_size_ratio=ratio,
        excluded_digit_centroids=tier1_digit_positions,
        debug_target_digit=args.target_digit,
    )
    print(f"\nTier 2 (digit-anchored outline-density, predicted size per digit, threshold={TIER2_OUTLINE_DENSITY_THRESHOLD}):")
    print(f"  recovered markers: {len(tier2_deltas)}")

    deltas = tier1_with_digit + tier2_deltas + tier1_no_digit  # last for visibility only
    by_digit: dict[str, dict[int, int]] = {}
    for d in deltas:
        if d.digit is None:
            continue
        by_digit.setdefault(d.digit, {}).setdefault(d.tier, 0)
        by_digit[d.digit][d.tier] += 1
    print(f"\nFinal results (Tier 1 + Tier 2 merged):")
    for digit in sorted(by_digit):
        tiers = by_digit[digit]
        total = sum(tiers.values())
        breakdown = " + ".join(f"T{t}={tiers[t]}" for t in sorted(tiers))
        marker = "  <-- target" if digit == args.target_digit else ""
        print(f"  digit '{digit}': {total} ({breakdown}){marker}")
    print(f"  candidate triangles with no digit (faint red in overlay): {len(tier1_no_digit)}")

    out_path = args.out
    if out_path is None:
        out_path = OUTPUT_DIR / f"{pdf_path.stem}_p{args.page}_deltas.png"
    overlay = overlay_deltas(gray, deltas, target_digit=args.target_digit)
    cv2.imwrite(str(out_path), overlay)
    print(f"  overlay -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
