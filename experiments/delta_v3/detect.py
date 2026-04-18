"""detect.py — Run Tier 1 + Tier 2 Δ detection on a pre-denoised image.

Skips build_delta_search_image (assumes the input is already denoised).
Output is an overlay PNG written to experiments/delta_v3/<--out>.png.

Usage:
  python experiments/delta_v3/detect.py --input path/to/denoised.png --out detection_test_1
  python experiments/delta_v3/detect.py  # uses defaults: AE122 final-stage output, --out detection
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parents[2]
DETECTOR_DIR = REPO_ROOT / "experiments" / "2026_04_delta_marker_detector"
OUT_DIR = Path(__file__).parent

sys.path.insert(0, str(DETECTOR_DIR))
import detect_deltas  # noqa: E402

sys.path.insert(0, str(OUT_DIR))
from denoise_2 import output_path as denoise_2_output_path  # noqa: E402

DEFAULT_PDF = REPO_ROOT / "revision_sets" / "Revision #1 - Drawing Changes" / "Revision #1 - Drawing Changes.pdf"
DEFAULT_PAGE = 17
DEFAULT_TARGET_DIGIT = "1"


def run(pre_denoised_path: Path, pdf_path: Path, page: int, target_digit: str | None, out_stem: str) -> None:
    img = cv2.imread(str(pre_denoised_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        print(f"ERROR: could not read {pre_denoised_path}", file=sys.stderr)
        sys.exit(1)
    print(f"Input: {pre_denoised_path.name}  ({img.shape[1]}x{img.shape[0]})")

    digit_words = detect_deltas.extract_digit_words_in_pixels(pdf_path, page)
    print(f"  PDF single-digit words on page {page}: {len(digit_words)}")

    candidates = detect_deltas._dedupe_candidates(detect_deltas.find_triangle_candidates(img))
    tier1 = detect_deltas.assign_digits(candidates, digit_words)
    tier1_with = [d for d in tier1 if d.digit is not None]
    tier1_no = [d for d in tier1 if d.digit is None]
    print(f"\nTier 1 (perim {detect_deltas.TIER1_MIN_PERIMETER}-{detect_deltas.TIER1_MAX_PERIMETER}px):")
    print(f"  candidates after NMS : {len(candidates)}")
    print(f"  with digit inside    : {len(tier1_with)}")
    print(f"  without digit        : {len(tier1_no)}")

    ratio = detect_deltas.calibrate_delta_size_ratio(tier1_with, digit_words)
    if ratio is None:
        ratio = detect_deltas.DELTA_SIDE_PER_DIGIT_HEIGHT_DEFAULT
        print(f"  no Tier 1 hits to calibrate; using default ratio {ratio:.2f}")
    else:
        print(f"  calibrated delta_side/digit_height ratio: {ratio:.2f}")

    tier1_positions = [d.digit_position for d in tier1_with if d.digit_position is not None]
    tier2 = detect_deltas.find_digit_anchored_deltas(
        img, digit_words,
        delta_size_ratio=ratio,
        excluded_digit_centroids=tier1_positions,
    )
    print(f"\nTier 2 (digit-anchored outline density >= {detect_deltas.TIER2_OUTLINE_DENSITY_THRESHOLD}):")
    print(f"  recovered markers: {len(tier2)}")
    if target_digit is not None:
        t2_target = sum(1 for d in tier2 if d.digit == target_digit)
        print(f"  of which digit == '{target_digit}': {t2_target}")

    deltas = tier1_with + tier2 + tier1_no
    overlay = detect_deltas.overlay_deltas(img, deltas, target_digit=target_digit)

    out_path = OUT_DIR / f"{out_stem}.png"
    cv2.imwrite(str(out_path), overlay)
    print(f"\nOverlay -> {out_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path, default=None,
        help="Pre-denoised greyscale PNG. Defaults to denoise_2 output for the given pdf+page.",
    )
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--page", type=int, default=DEFAULT_PAGE)
    parser.add_argument("--target-digit", type=str, default=DEFAULT_TARGET_DIGIT)
    parser.add_argument("--out", type=str, default="detection",
                        help="Output filename stem (no extension). File written to experiments/delta_v3/<out>.png")
    args = parser.parse_args()

    pdf_path = args.pdf if args.pdf.is_absolute() else (Path.cwd() / args.pdf).resolve()
    in_path = args.input or denoise_2_output_path(pdf_path, args.page)
    if not in_path.exists():
        print(f"ERROR: input not found: {in_path}", file=sys.stderr)
        sys.exit(1)

    run(in_path, pdf_path, args.page, args.target_digit, args.out)


if __name__ == "__main__":
    main()
