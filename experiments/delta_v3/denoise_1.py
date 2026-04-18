"""denoise_1.py — Stage 1 denoising for Δ marker detection.

Renders a PDF page and produces a cleaned grayscale image suitable as input
to Δ-detection (Tier 1 contour search and Tier 2 outline-density check).

Pipeline:
  1. Render PDF page at 300 DPI to grayscale.
  2. Threshold: pixels > INK_THRESHOLD become white.
  3. Mask long vertical lines (>= V_MIN_LENGTH px).
  4. THICKNESS-AWARE long-horizontal-line mask (>= H_MIN_LENGTH px). For
     each contiguous horizontal run:
       - uniformly thin   -> mask entire run (dimensions, grid lines)
       - uniformly thick  -> mask entire run (walls)
       - mixed thickness  -> mask only the THICK columns; thin portions
                             survive (preserves Δ bases touching walls)
  5. Mask filled blobs (>= BLOB_AREA px AND >= BLOB_DENSITY fill density).
  6. Combine masks, dilate by 3x3, apply to the grayscale image (paint white).

Output:
  experiments/delta_v3/<pdf_stem>_p<page>_denoise_1.png

Usage:
  python experiments/delta_v3/denoise_1.py
  python experiments/delta_v3/denoise_1.py --pdf path/to.pdf --page 17

Defaults: AE122 (Revision #1, page 17), the canonical hard test fixture.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DETECTOR_DIR = REPO_ROOT / "experiments" / "2026_04_delta_marker_detector"
OUT_DIR = Path(__file__).parent

sys.path.insert(0, str(DETECTOR_DIR))
import detect_deltas  # noqa: E402

DEFAULT_PDF = REPO_ROOT / "revision_sets" / "Revision #1 - Drawing Changes" / "Revision #1 - Drawing Changes.pdf"
DEFAULT_PAGE = 17

# Tunables (px at 300 DPI)
INK_THRESHOLD = 150          # pixels > 150 -> white. Preserves anti-aliased Δ-base edges.
V_MIN_LENGTH = 30            # vertical-line mask kernel
H_MIN_LENGTH = 140           # horizontal-line mask kernel
THICK_KERNEL_H = 4           # vertical kernel for thick-only erosion;
                             # AE122: Δ base ~2-3 px, walls ~6-9 px
BLOB_AREA_MIN = 250          # filled-blob mask: min area
BLOB_DENSITY_MIN = 0.65      # filled-blob mask: min fill density (area / bbox_area)
FINAL_DILATE = 3             # final mask dilation kernel (px)


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
    # 1) Thick-only image: vertical erode then dilate-back.
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, thick_kernel_h))
    binary_thick = cv2.dilate(cv2.erode(binary, v_kernel), v_kernel)

    # 2) Long horizontal runs in the original.
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_length, 1))
    long_h_runs = cv2.dilate(cv2.erode(binary, h_kernel), h_kernel)

    # 3) Label each long run.
    n_labels, labels = cv2.connectedComponents(long_h_runs, connectivity=8)

    # 4) Per-label: does this run contain any thick ink?
    has_thick = np.zeros(n_labels, dtype=bool)
    overlap = (binary_thick > 0) & (labels > 0)
    if overlap.any():
        labels_with_thick = np.unique(labels[overlap])
        has_thick[labels_with_thick] = True

    # 5) Final mask:
    #    uniformly-thin runs -> mask everywhere in the run
    #    mixed/thick runs    -> mask only thick pixels
    final_mask = np.zeros_like(binary)
    uniform_thin_pixels = (~has_thick[labels]) & (labels > 0)
    final_mask[uniform_thin_pixels] = 255
    mixed_thick_pixels = has_thick[labels] & (binary_thick > 0) & (labels > 0)
    final_mask[mixed_thick_pixels] = 255

    return final_mask


# ---------------------------------------------------------------------------
# Stage-1 denoise
# ---------------------------------------------------------------------------


def denoise_stage_1(gray: np.ndarray) -> np.ndarray:
    out = gray.copy()
    out[out > INK_THRESHOLD] = 255

    _, binary = cv2.threshold(out, INK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)

    # Long vertical lines.
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, V_MIN_LENGTH))
    v_lines = cv2.dilate(cv2.erode(binary, v_kernel), v_kernel)

    # Long horizontal lines (thickness-aware).
    h_lines = horizontal_mask_thickness_aware(binary)

    # Filled blobs (columns, solid symbols).
    blob_mask = np.zeros_like(binary)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    for i in range(1, n_labels):
        x, y, w, h, area = stats[i]
        if area < BLOB_AREA_MIN:
            continue
        bbox_area = w * h
        if bbox_area <= 0:
            continue
        density = area / bbox_area
        if density >= BLOB_DENSITY_MIN:
            blob_mask[labels == i] = 255

    mask = cv2.bitwise_or(cv2.bitwise_or(v_lines, h_lines), blob_mask)
    mask = cv2.dilate(mask, np.ones((FINAL_DILATE, FINAL_DILATE), np.uint8), iterations=1)
    out[mask > 0] = 255
    return out


def output_path(pdf_path: Path, page: int) -> Path:
    return OUT_DIR / f"{pdf_path.stem}_p{page}_denoise_1.png"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--page", type=int, default=DEFAULT_PAGE)
    args = parser.parse_args()

    pdf_path = args.pdf if args.pdf.is_absolute() else (Path.cwd() / args.pdf).resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Rendering {pdf_path.name} page {args.page} at 300 DPI ...")
    gray, _ = detect_deltas.render_page_gray(pdf_path, args.page)
    print(f"  {gray.shape[1]}x{gray.shape[0]}")

    print(
        f"Stage-1 denoise (ink={INK_THRESHOLD}, v_len={V_MIN_LENGTH}, "
        f"h_len={H_MIN_LENGTH}, thick_h={THICK_KERNEL_H}) ..."
    )
    out_img = denoise_stage_1(gray)

    out_path = output_path(pdf_path, args.page)
    cv2.imwrite(str(out_path), out_img)
    print(f"  wrote {out_path.name}")


if __name__ == "__main__":
    main()
