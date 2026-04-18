"""Run Tier 1 + Tier 2 detection on a pre-denoised image (skips build_delta_search_image).

Used to compare detector recall against the experimental denoise outputs in
experiments/delta_v2/.

Output:
  experiments/delta_v2/<input_stem>_deltas.png
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

DEFAULT_PDF = REPO_ROOT / "revision_sets" / "Revision #1 - Drawing Changes" / "Revision #1 - Drawing Changes.pdf"
DEFAULT_PAGE = 17
DEFAULT_TARGET_DIGIT = "1"


def run(pre_denoised_path: Path, pdf_path: Path, page: int, target_digit: str | None) -> None:
    delta_search_img = cv2.imread(str(pre_denoised_path), cv2.IMREAD_GRAYSCALE)
    if delta_search_img is None:
        print(f"ERROR: could not read {pre_denoised_path}", file=sys.stderr)
        sys.exit(1)
    print(f"Input denoised image: {pre_denoised_path.name}  ({delta_search_img.shape[1]}x{delta_search_img.shape[0]})")

    digit_words = detect_deltas.extract_digit_words_in_pixels(pdf_path, page)
    print(f"  PDF single-digit words on page {page}: {len(digit_words)}")

    candidates = detect_deltas._dedupe_candidates(detect_deltas.find_triangle_candidates(delta_search_img))
    tier1_deltas = detect_deltas.assign_digits(candidates, digit_words)
    tier1_with = [d for d in tier1_deltas if d.digit is not None]
    tier1_without = [d for d in tier1_deltas if d.digit is None]
    print(f"\nTier 1 (perim {detect_deltas.TIER1_MIN_PERIMETER}-{detect_deltas.TIER1_MAX_PERIMETER}px):")
    print(f"  candidates after NMS: {len(candidates)}")
    print(f"  with digit inside  : {len(tier1_with)}")
    print(f"  without digit       : {len(tier1_without)}")

    ratio = detect_deltas.calibrate_delta_size_ratio(tier1_with, digit_words)
    if ratio is None:
        ratio = detect_deltas.DELTA_SIDE_PER_DIGIT_HEIGHT_DEFAULT
        print(f"  no Tier 1 hits to calibrate; using default ratio {ratio:.2f}")
    else:
        print(f"  calibrated delta_side/digit_height ratio: {ratio:.2f}")

    tier1_positions = [d.digit_position for d in tier1_with if d.digit_position is not None]
    tier2_deltas = detect_deltas.find_digit_anchored_deltas(
        delta_search_img,
        digit_words,
        delta_size_ratio=ratio,
        excluded_digit_centroids=tier1_positions,
    )
    print(f"\nTier 2 (digit-anchored outline density >= {detect_deltas.TIER2_OUTLINE_DENSITY_THRESHOLD}):")
    print(f"  recovered markers: {len(tier2_deltas)}")
    if target_digit is not None:
        t2_target = sum(1 for d in tier2_deltas if d.digit == target_digit)
        print(f"  of which digit == '{target_digit}': {t2_target}")

    deltas = tier1_with + tier2_deltas + tier1_without
    overlay = detect_deltas.overlay_deltas(delta_search_img, deltas, target_digit=target_digit)

    out_path = OUT_DIR / f"{pre_denoised_path.stem}_deltas.png"
    cv2.imwrite(str(out_path), overlay)
    print(f"\nOverlay -> {out_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inputs", nargs="+", type=Path,
        default=[
            OUT_DIR / "03_denoise_AE122_threshold_150.png",
            OUT_DIR / "06_arcs_removed.png",
        ],
        help="Pre-denoised greyscale PNG(s) to feed into Tier 1/2 detection.",
    )
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--page", type=int, default=DEFAULT_PAGE)
    parser.add_argument("--target-digit", type=str, default=DEFAULT_TARGET_DIGIT)
    args = parser.parse_args()

    for inp in args.inputs:
        print("=" * 80)
        run(inp, args.pdf, args.page, args.target_digit)
        print()


if __name__ == "__main__":
    main()
