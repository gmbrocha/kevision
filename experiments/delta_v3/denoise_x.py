"""denoise_x.py — Long-line wipe (any angle).

Sits between denoise_1 and denoise_2. Detects and wipes long line segments
at any angle, eliminating the "X-pattern false positive" failure mode where
two long crossing lines (e.g., a layout X with a digit in each quadrant) are
mistaken by Tier 2 for the slant sides of 4 different equilateral triangles.

Pipeline (operates on denoise_1 grayscale + PDF text layer):
  1. Pre-erase alpha-containing words and 90°-rotated words. Without this,
     Hough finds thousands of spurious short segments from text strokes.
  2. cv2.HoughLinesP with minLineLength=180 px, maxLineGap=10. 180 px is
     safely above the largest Δ side observed on these drawings (~130 px),
     so this threshold cannot wipe a Δ outline by accident.
  3. Paint each detected segment white at thickness=2.

Output:
  experiments/delta_v3/<pdf_stem>_p<page>_denoise_x.png

Usage:
  python experiments/delta_v3/denoise_x.py
  python experiments/delta_v3/denoise_x.py --pdf path/to.pdf --page 17

Then chain into stage 2 with the explicit input flag:
  python experiments/delta_v3/denoise_2.py --input experiments/delta_v3/<denoise_x_output>.png

Defaults: AE122 (Revision #1, page 17).

Why this lives BETWEEN stage 1 and 2:
  Stage 2's halo gate keeps ink only inside ~75 px of any pure-numeric upright
  digit. If an X arm passes through 4 digit quadrants, stage 2 fragments it
  into 4 sub-150 px pieces — too short to detect as a "long line" without a
  threshold low enough to start eating real Δ sides. We wipe the X arms while
  they're still intact, before stage 2 gets a chance to fragment them.
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

sys.path.insert(0, str(OUT_DIR))
from denoise_1 import output_path as denoise_1_output_path  # noqa: E402
from denoise_2 import (  # noqa: E402
    collect_words,
    contains_alpha,
    erase_bboxes,
    is_rotated_left,
)

DEFAULT_PDF = REPO_ROOT / "revision_sets" / "Revision #1 - Drawing Changes" / "Revision #1 - Drawing Changes.pdf"
DEFAULT_PAGE = 17

# Stage-1 ink threshold mirrors denoise_1.INK_THRESHOLD; only used here for
# binarization before Hough.
INK_THRESHOLD = 150

# Hough tunables
HOUGH_MIN_LINE_LENGTH = 180        # max observed Δ side ~130 px; this protects them
HOUGH_MAX_LINE_GAP = 10            # bridge tiny aliasing gaps within a single line
HOUGH_VOTE_THRESHOLD = 100         # min number of accumulator votes for a line
HOUGH_RHO = 1                      # px
HOUGH_THETA = np.pi / 180          # 1° angular resolution

# Wipe thickness (px); 2 px covers the ink itself and one fringe pixel.
LINE_WIPE_THICKNESS = 2


def detect_long_lines(binary: np.ndarray) -> np.ndarray | None:
    """Return Hough line segments as an (N, 1, 4) array or None if nothing found."""
    return cv2.HoughLinesP(
        binary,
        rho=HOUGH_RHO,
        theta=HOUGH_THETA,
        threshold=HOUGH_VOTE_THRESHOLD,
        minLineLength=HOUGH_MIN_LINE_LENGTH,
        maxLineGap=HOUGH_MAX_LINE_GAP,
    )


def denoise_stage_x(stage1_img: np.ndarray, words: list[dict]) -> np.ndarray:
    img = stage1_img.copy()

    # Step 1: pre-erase text (alpha + rotated). Text strokes produce thousands
    # of short Hough segments that bog down the detector and add noise.
    alpha_words = [w for w in words if contains_alpha(w["text"])]
    rotated_words = [w for w in words if is_rotated_left(w["dir"])]
    erase_bboxes(img, [w["bbox"] for w in alpha_words])
    erase_bboxes(img, [w["bbox"] for w in rotated_words])
    print(f"  pre-erase: {len(alpha_words)} alpha + {len(rotated_words)} rotated words")

    # Step 2: binarize and Hough.
    binary = cv2.threshold(img, INK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)[1]
    print(f"  Hough (min_length={HOUGH_MIN_LINE_LENGTH}, max_gap={HOUGH_MAX_LINE_GAP},"
          f" vote_threshold={HOUGH_VOTE_THRESHOLD}) ...")
    lines = detect_long_lines(binary)
    n_lines = 0 if lines is None else len(lines)
    print(f"  found {n_lines} long line segments")

    # Step 3: paint detected segments white onto the (text-pre-erased) image.
    if lines is not None:
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            cv2.line(img, (int(x1), int(y1)), (int(x2), int(y2)), 255, LINE_WIPE_THICKNESS)

    return img


def output_path(pdf_path: Path, page: int) -> Path:
    return OUT_DIR / f"{pdf_path.stem}_p{page}_denoise_x.png"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--page", type=int, default=DEFAULT_PAGE)
    parser.add_argument(
        "--input", type=Path, default=None,
        help="Path to denoise_1 output. Defaults to the path implied by --pdf and --page.",
    )
    args = parser.parse_args()

    pdf_path = args.pdf if args.pdf.is_absolute() else (Path.cwd() / args.pdf).resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    in_path = args.input or denoise_1_output_path(pdf_path, args.page)
    if not in_path.exists():
        print(f"ERROR: input image not found: {in_path}", file=sys.stderr)
        print(f"       run denoise_1.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {in_path.name} ...")
    stage1 = cv2.imread(str(in_path), cv2.IMREAD_GRAYSCALE)
    if stage1 is None:
        print(f"ERROR: could not read {in_path}", file=sys.stderr)
        sys.exit(1)
    print(f"  {stage1.shape[1]}x{stage1.shape[0]}")

    print(f"Reading text layer from {pdf_path.name} page {args.page} ...")
    words = collect_words(pdf_path, args.page)
    print(f"  {len(words)} words on page")

    out_img = denoise_stage_x(stage1, words)

    out_path = output_path(pdf_path, args.page)
    cv2.imwrite(str(out_path), out_img)
    print(f"  wrote {out_path.name}")


if __name__ == "__main__":
    main()
