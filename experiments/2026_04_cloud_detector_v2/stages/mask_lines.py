"""Stage 2: mask long straight lines via morphological extraction.

Cloud scallops are arcs all the way around — there's no straight run longer
than a couple of pixels between adjacent scallops. So we can aggressively
mask any long straight horizontal/vertical line without touching cloud
geometry.

We use morphological erosion with long horizontal and vertical kernels.
Pixels that survive a horizontal-kernel erosion belong to a horizontal line
of at least kernel-length pixels; same logic for vertical. This is O(image)
instead of Hough's O(thousands_of_segments_squared) and gives us a clean
binary mask of "structural framework" without ever enumerating segments.

Diagonal walls/lines aren't covered by this v1 — most architectural
framework is axis-aligned, and diagonals are also less likely to confuse
the cloud scallop detector (scallops aren't diagonal). We can add a
rotated-kernel pass later if needed.
"""
from __future__ import annotations

import cv2
import numpy as np

# Tunables (300 DPI baseline). Lines shorter than these get IGNORED — survive into the next stage.
MIN_LINE_LEN_INDEX = 60        # px; shorter is fine, index has lots of small lines
MIN_LINE_LEN_DRAWING = 80      # px; drawings have more structure, slightly longer floor
MIN_LINE_LEN_LONG = 250        # px; "very long" lines (borders, section dividers) always masked
DILATE_LINE_MASK = 2           # px; expand the structural mask slightly so we kill anti-aliasing fringe
CLOSE_AFTER_KERNEL = 3         # px; bridge tiny cloud-arc gaps where a line was crossed


def _extract_axis_lines(binary: np.ndarray, min_length: int, axis: str) -> np.ndarray:
    """Return a binary mask of pixels belonging to axis-aligned lines >= min_length.

    `binary` is an inverted binary (foreground/ink = white).
    `axis` is 'h' or 'v'.
    """
    if axis == "h":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_length, 1))
    elif axis == "v":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_length))
    else:
        raise ValueError(f"axis must be 'h' or 'v', got {axis!r}")

    eroded = cv2.erode(binary, kernel, iterations=1)
    # dilate back up to recover full line thickness
    dilated = cv2.dilate(eroded, kernel, iterations=1)
    return dilated


def mask_lines(
    gray: np.ndarray,
    page_kind: str = "drawing",
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Mask long horizontal/vertical lines on `gray`. Returns (cleaned_gray, line_mask, stats).

    `line_mask` is the binary mask of pixels we removed (useful for overlays).
    `stats` is a small dict with diagnostics.
    """
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

    min_len = MIN_LINE_LEN_INDEX if page_kind == "index" else MIN_LINE_LEN_DRAWING

    h_lines = _extract_axis_lines(binary, min_len, "h")
    v_lines = _extract_axis_lines(binary, min_len, "v")
    long_h = _extract_axis_lines(binary, MIN_LINE_LEN_LONG, "h")
    long_v = _extract_axis_lines(binary, MIN_LINE_LEN_LONG, "v")
    line_mask = cv2.bitwise_or(cv2.bitwise_or(h_lines, v_lines), cv2.bitwise_or(long_h, long_v))

    if DILATE_LINE_MASK > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (DILATE_LINE_MASK * 2 + 1,) * 2)
        line_mask = cv2.dilate(line_mask, kernel, iterations=1)

    cleaned = gray.copy()
    cleaned[line_mask > 0] = 255

    if CLOSE_AFTER_KERNEL > 0:
        # Bridge tiny gaps in cloud arcs where a structural line crossed them.
        binary_after = cv2.threshold(cleaned, 200, 255, cv2.THRESH_BINARY_INV)[1]
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (CLOSE_AFTER_KERNEL,) * 2)
        closed = cv2.morphologyEx(binary_after, cv2.MORPH_CLOSE, kernel, iterations=1)
        cleaned = 255 - closed

    coverage_pct = float(np.mean(line_mask > 0)) * 100.0
    stats = {
        "page_kind": page_kind,
        "min_line_length": int(min_len),
        "min_long_length": int(MIN_LINE_LEN_LONG),
        "line_mask_coverage_pct": coverage_pct,
    }
    return cleaned, line_mask, stats


def overlay_line_mask(
    gray: np.ndarray,
    line_mask: np.ndarray,
    color: tuple[int, int, int] = (0, 0, 220),
) -> np.ndarray:
    """Diagnostic overlay: original page with the structural-line mask painted in color."""
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    bgr[line_mask > 0] = color
    return bgr
