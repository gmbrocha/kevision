"""Checkpoint 1: how much do stages 1+2 alone fix iteration 1's contour scoring?

Re-runs iteration 1's convexity-defect scoring on the cleaned images produced
by stages 1 (text mask) + 2 (line mask). If the cleaned image is enough to
make the old score meaningfully separate clouds from non-clouds, we can
shortcut stages 3-6.

Borrows iteration 1's score_cloud + render_overlay logic by importing them
from the iteration 1 folder (read-only — we don't modify it).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np

EXP_DIR = Path(__file__).parent
sys.path.insert(0, str(EXP_DIR))

from common import OUTPUT_DIR, PAGES, TestPage  # noqa: E402
from detect import run_stage1_text_mask, run_stage2_line_mask  # noqa: E402


def _load_iteration1() -> object:
    v1_path = EXP_DIR.parent / "2026_04_cloud_detector" / "detect.py"
    spec = importlib.util.spec_from_file_location("v1_detect", v1_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["v1_detect"] = module  # required for @dataclass to resolve types
    spec.loader.exec_module(module)
    return module


v1_detect = _load_iteration1()


def find_contours(cleaned_gray: np.ndarray) -> list[np.ndarray]:
    """Same threshold + close + RETR_TREE as iteration 1's find_candidate_contours."""
    _, binary = cv2.threshold(cleaned_gray, 200, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((3, 3), np.uint8)
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, _ = cv2.findContours(closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    return list(contours)


def score_and_overlay(page: TestPage, cleaned: np.ndarray, threshold: float = 0.40) -> dict:
    h, w = cleaned.shape
    page_perim_est = float(2 * (h + w))
    contours = find_contours(cleaned)
    scored = [(c, *v1_detect.score_cloud(c, page_perim_est)) for c in contours]
    out = OUTPUT_DIR / f"{page.label}_checkpoint1.png"
    n_clouds, reject_counts = v1_detect.render_overlay(cleaned, scored, out, threshold=threshold)
    return {
        "page": page.label,
        "contours": len(contours),
        "n_clouds": n_clouds,
        "reject_counts": reject_counts,
        "overlay": out,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Checkpoint 1: iteration-1 scorer on stage-1+2 cleaned images")
    print(f"score threshold: 0.40 (same as iteration 1)")

    summary = []
    for page in PAGES:
        print(f"\n--- {page.label}: {page.description}  [{page.page_kind}]")
        masked, _ = run_stage1_text_mask(page, save_overlays=False)
        cleaned, _, _ = run_stage2_line_mask(page, masked, save_overlays=False)
        result = score_and_overlay(page, cleaned)
        print(f"  contours after cleaning: {result['contours']}")
        print(f"  classified as clouds:    {result['n_clouds']}")
        relevant = {
            k: v for k, v in result["reject_counts"].items()
            if k in ("low_solidity", "high_solidity", "few_sig_defects", "low_arc_fraction", "below_threshold")
        }
        for k, v in sorted(relevant.items(), key=lambda kv: -kv[1]):
            print(f"    reject {k:<25} {v:>5}")
        print(f"  overlay -> {result['overlay'].name}")
        summary.append(result)

    print("\n=== CHECKPOINT 1 SUMMARY ===")
    print("(compare against iteration 1's original numbers: 6 / 11 / 4 / 2 / 1)")
    for r in summary:
        print(f"  {r['page']:<22}  contours={r['contours']:>5}   clouds={r['n_clouds']:>3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
