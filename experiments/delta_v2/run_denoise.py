"""Denoise-only runner. Outputs go to experiments/delta_v2/ named by step.

This is orchestration, not algorithm code -- it just runs the existing
build_delta_search_image function from detect_deltas.py with different
parameter overrides so we can compare effects in isolation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parents[2]
DETECTOR_DIR = REPO_ROOT / "experiments" / "2026_04_delta_marker_detector"
OUT_DIR = Path(__file__).parent

sys.path.insert(0, str(DETECTOR_DIR))
import detect_deltas  # noqa: E402

PDF_PATH = REPO_ROOT / "revision_sets" / "Revision #1 - Drawing Changes" / "Revision #1 - Drawing Changes.pdf"
PAGE = 17

print(f"Rendering {PDF_PATH.name} page {PAGE} at 300 DPI...")
gray, _ = detect_deltas.render_page_gray(PDF_PATH, PAGE)
print(f"  {gray.shape[1]}x{gray.shape[0]}")


def save(name: str) -> None:
    out_path = OUT_DIR / name
    img = detect_deltas.build_delta_search_image(gray)
    cv2.imwrite(str(out_path), img)
    print(f"  wrote {name}")


# --- Variant 1: current params (re-baseline) ---
detect_deltas.DELTA_SEARCH_INK_THRESHOLD = 100
detect_deltas.DELTA_SEARCH_HORIZONTAL_MIN_LENGTH = 140
print(f"\n[1] baseline: ink_threshold=100  horizontal_min_length=140")
save("01_denoise_AE122.png")

# --- Variant 2: horizontal masking effectively disabled ---
detect_deltas.DELTA_SEARCH_INK_THRESHOLD = 100
# Set length larger than the page width so morph open finds zero horizontals
detect_deltas.DELTA_SEARCH_HORIZONTAL_MIN_LENGTH = max(gray.shape[1] + 100, 13000)
print(f"\n[2] horizontal masking OFF: ink_threshold=100  horizontal_min_length={detect_deltas.DELTA_SEARCH_HORIZONTAL_MIN_LENGTH}")
save("02_denoise_AE122_no_horizontal.png")

# --- Variant 3: more permissive ink threshold ---
detect_deltas.DELTA_SEARCH_INK_THRESHOLD = 150
detect_deltas.DELTA_SEARCH_HORIZONTAL_MIN_LENGTH = 140
print(f"\n[3] permissive ink: ink_threshold=150  horizontal_min_length=140")
save("03_denoise_AE122_threshold_150.png")
