"""Denoise variant: thickness-aware long-horizontal-line mask.

Same pipeline as run_denoise.py with INK_THRESHOLD=150, except the
long-horizontal-line mask is replaced. New rule for any contiguous horizontal
run >= MIN_LENGTH px in the binary:

  - Uniformly thin   (no thick portions)  -> mask the whole run
                                             (kills dimension lines, grid lines, hatching)
  - Uniformly thick  (no thin portions)   -> mask the whole run
                                             (kills walls)
  - Mixed thickness  (both thin and thick)-> mask ONLY the thick columns
                                             (Δ base touching a wall: wall masked, base survives)

Output: experiments/delta_v2/03_denoise_AE122_threshold_150_bases_fixed.png

Known limitation (logged to KNOWN_LIMITATIONS.md): a Δ base that happens to
be collinear with a long thin horizontal feature (e.g., dimension line passing
through the same row) will be classified as "uniformly thin" and nuked.
Expected to be rare on these drawings.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DETECTOR_DIR = REPO_ROOT / "experiments" / "2026_04_delta_marker_detector"
OUT_DIR = Path(__file__).parent

sys.path.insert(0, str(DETECTOR_DIR))
import detect_deltas  # noqa: E402

PDF_PATH = REPO_ROOT / "revision_sets" / "Revision #1 - Drawing Changes" / "Revision #1 - Drawing Changes.pdf"
PAGE = 17

INK_THRESHOLD = 150           # winning value from earlier A/B
H_MIN_LENGTH = 140            # same as production
THICK_KERNEL_H = 4            # vertical kernel: pixels >= 4 px tall = "thick"
                              # AE122: Δ base ~2-3 px, walls ~6-9 px


# ---------------------------------------------------------------------------
# Thickness-aware horizontal mask
# ---------------------------------------------------------------------------


def horizontal_mask_thickness_aware(
    binary: np.ndarray,
    min_length: int = H_MIN_LENGTH,
    thick_kernel_h: int = THICK_KERNEL_H,
) -> np.ndarray:
    """Build the long-horizontal-line mask with the mixed-thickness exception.

    `binary` is foreground=255 (inverted from grayscale).
    Returned mask is 0/255 with 255 = pixels to be wiped.
    """
    # 1) Thick-only image: vertical erode then dilate-back so thick pixels
    #    keep their full vertical extent. Thin (<= thick_kernel_h - 1 px) ink
    #    is annihilated by the erode and never returns.
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, thick_kernel_h))
    binary_thick = cv2.dilate(cv2.erode(binary, v_kernel), v_kernel)

    # 2) Long horizontal runs in the original (pixel-perfect masks of every
    #    contiguous horizontal run >= min_length px).
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_length, 1))
    long_h_runs = cv2.dilate(cv2.erode(binary, h_kernel), h_kernel)

    # 3) Connected-components on the long-run mask. Each component = one
    #    horizontal run (possibly with thin extensions; vertical adjacency
    #    can merge stacked runs but that's fine -- they share the same
    #    "has-thick?" decision either way).
    n_labels, labels = cv2.connectedComponents(long_h_runs, connectivity=8)

    # 4) Per-label: does this run contain any thick ink?
    has_thick = np.zeros(n_labels, dtype=bool)
    overlap = (binary_thick > 0) & (labels > 0)
    if overlap.any():
        labels_with_thick = np.unique(labels[overlap])
        has_thick[labels_with_thick] = True

    # 5) Build the final mask:
    #    - uniformly-thin runs (no thick portion): mask everywhere in the run
    #    - mixed/thick runs: mask ONLY the thick pixels of the run
    final_mask = np.zeros_like(binary)

    uniform_thin_pixels = (~has_thick[labels]) & (labels > 0)
    final_mask[uniform_thin_pixels] = 255

    mixed_run_thick_pixels = has_thick[labels] & (binary_thick > 0) & (labels > 0)
    final_mask[mixed_run_thick_pixels] = 255

    return final_mask


# ---------------------------------------------------------------------------
# Custom build_delta_search_image (same as production, but with new H mask)
# ---------------------------------------------------------------------------


def build_delta_search_image_bases_fixed(gray: np.ndarray) -> np.ndarray:
    out = gray.copy()
    out[out > INK_THRESHOLD] = 255

    _, binary = cv2.threshold(out, INK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)

    # vertical lines: unchanged
    v_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, detect_deltas.DELTA_SEARCH_VERTICAL_MIN_LENGTH)
    )
    v_lines = cv2.dilate(cv2.erode(binary, v_kernel), v_kernel)

    # horizontal lines: NEW thickness-aware mask
    h_lines = horizontal_mask_thickness_aware(binary)

    # filled-blob mask: unchanged
    blob_mask = np.zeros_like(binary)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    for i in range(1, n_labels):
        x, y, w, h, area = stats[i]
        if area < detect_deltas.DELTA_SEARCH_BLOB_AREA_MIN:
            continue
        bbox_area = w * h
        if bbox_area <= 0:
            continue
        density = area / bbox_area
        if density >= detect_deltas.DELTA_SEARCH_BLOB_DENSITY_MIN:
            blob_mask[labels == i] = 255

    mask = cv2.bitwise_or(cv2.bitwise_or(v_lines, h_lines), blob_mask)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    out[mask > 0] = 255
    return out


def main() -> None:
    print(f"Rendering {PDF_PATH.name} page {PAGE} at 300 DPI...")
    gray, _ = detect_deltas.render_page_gray(PDF_PATH, PAGE)
    print(f"  {gray.shape[1]}x{gray.shape[0]}")

    print(f"Building thickness-aware delta-search image"
          f" (ink_threshold={INK_THRESHOLD}, h_min_length={H_MIN_LENGTH},"
          f" thick_kernel_h={THICK_KERNEL_H})...")
    out_img = build_delta_search_image_bases_fixed(gray)

    out_path = OUT_DIR / "03_denoise_AE122_threshold_150_bases_fixed.png"
    cv2.imwrite(str(out_path), out_img)
    print(f"  wrote {out_path.name}")


if __name__ == "__main__":
    main()
