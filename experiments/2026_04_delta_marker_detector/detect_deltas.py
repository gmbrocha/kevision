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
MIN_TRIANGLE_PERIMETER = 80      # ~26 px per side, smallest plausible Δ
MAX_TRIANGLE_PERIMETER = 600     # generous upper bound
APPROX_EPSILON_FRAC = 0.05       # 5% of perimeter for approxPolyDP
SIDE_LENGTH_TOLERANCE = 0.18     # sides may differ by up to 18%
ANGLE_TOLERANCE_DEG = 14.0       # each angle within 14 deg of 60
DIGIT_TEXTS = set("123456789")


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
            out.append({
                "text": text,
                "bbox": (rect.x0, rect.y0, rect.x1, rect.y1),
                "centroid": (cx, cy),
            })
    finally:
        doc.close()
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
        if perimeter < MIN_TRIANGLE_PERIMETER or perimeter > MAX_TRIANGLE_PERIMETER:
            continue
        if len(contour) < 6:
            continue
        try:
            hull = cv2.convexHull(contour, returnPoints=True)
        except cv2.error:
            continue
        hull_perim = float(cv2.arcLength(hull, closed=True))
        if hull_perim < MIN_TRIANGLE_PERIMETER:
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
            color = (0, 200, 0)    # bright green — current revision
            label = digit
        else:
            color = (140, 140, 140)  # grey — older revision triangle
            label = digit
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

    candidates = find_triangle_candidates(gray)
    print(f"  triangle candidates (raw, pre-dedupe): {len(candidates)}")
    candidates = _dedupe_candidates(candidates)
    print(f"  after NMS: {len(candidates)}")

    digit_words = extract_digit_words_in_pixels(pdf_path, args.page, dpi=args.dpi)
    print(f"  PDF single-digit text words on page: {len(digit_words)}")

    deltas = assign_digits(candidates, digit_words)
    by_digit: dict[str, int] = {}
    no_digit = 0
    for d in deltas:
        if d.digit is None:
            no_digit += 1
        else:
            by_digit[d.digit] = by_digit.get(d.digit, 0) + 1
    print(f"\nResults:")
    for digit in sorted(by_digit):
        marker = "  <-- target" if digit == args.target_digit else ""
        print(f"  digit '{digit}': {by_digit[digit]:>3}{marker}")
    print(f"  no digit (candidate triangle, no enclosed digit): {no_digit}")

    out_path = args.out
    if out_path is None:
        out_path = OUTPUT_DIR / f"{pdf_path.stem}_p{args.page}_deltas.png"
    overlay = overlay_deltas(gray, deltas, target_digit=args.target_digit)
    cv2.imwrite(str(out_path), overlay)
    print(f"  overlay -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
