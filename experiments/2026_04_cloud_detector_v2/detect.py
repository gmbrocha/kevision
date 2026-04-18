"""Iteration-2 cloud detector orchestrator.

Runs the full stack on each test page and saves per-stage overlay PNGs so we
can audit each filter independently.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from common import (
    OUTPUT_DIR,
    PAGES,
    TestPage,
    get_text_word_rects,
    gray_to_bgr,
    render_page_gray,
    save_overlay,
)
from stages.detect_scallops import (
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_SCALES,
    Scallop,
    detect_scallops,
    overlay_scallops,
)
from stages.mask_lines import mask_lines, overlay_line_mask
from stages.mask_text import mask_text, overlay_text_rects


def run_stage1_text_mask(page: TestPage, save_overlays: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Render the page, mask text. Returns (gray_after_text_mask, raw_gray)."""
    gray, zoom = render_page_gray(page.pdf_path, page.page_index)
    text_rects = get_text_word_rects(page.pdf_path, page.page_index, zoom)
    masked = mask_text(gray, text_rects)
    if save_overlays:
        save_overlay(
            overlay_text_rects(gray, text_rects),
            OUTPUT_DIR / f"{page.label}_01a_text_rects.png",
        )
        save_overlay(
            gray_to_bgr(masked),
            OUTPUT_DIR / f"{page.label}_01_text_masked.png",
        )
    return masked, gray


def run_stage2_line_mask(
    page: TestPage,
    text_masked: np.ndarray,
    save_overlays: bool = True,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Mask straight lines on the text-masked image. Returns (cleaned, line_mask, stats)."""
    cleaned, line_mask, stats = mask_lines(text_masked, page_kind=page.page_kind)
    if save_overlays:
        save_overlay(
            overlay_line_mask(text_masked, line_mask, color=(0, 0, 220)),
            OUTPUT_DIR / f"{page.label}_02a_lines_detected.png",
        )
        save_overlay(
            gray_to_bgr(cleaned),
            OUTPUT_DIR / f"{page.label}_02_lines_masked.png",
        )
    return cleaned, line_mask, stats


def run_stage3_scallops(
    page: TestPage,
    cleaned: np.ndarray,
    save_overlays: bool = True,
) -> list[Scallop]:
    """Detect scallop primitives on the cleaned image. Returns list of Scallop hits."""
    scallops = detect_scallops(cleaned)
    if save_overlays:
        save_overlay(
            overlay_scallops(cleaned, scallops),
            OUTPUT_DIR / f"{page.label}_03_scallops.png",
        )
    return scallops


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stages",
        type=str,
        default="1",
        help="Comma-separated stage numbers to run (default: 1)",
    )
    parser.add_argument(
        "--page",
        type=str,
        default=None,
        help="Run only the named test page (label match)",
    )
    args = parser.parse_args()
    stage_set = {int(s.strip()) for s in args.stages.split(",") if s.strip()}

    selected_pages = PAGES if args.page is None else [p for p in PAGES if p.label == args.page]
    if not selected_pages:
        print(f"No pages match label '{args.page}'")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Stages enabled: {sorted(stage_set)}  Pages: {[p.label for p in selected_pages]}")

    for page in selected_pages:
        print(f"\n--- {page.label}: {page.description}  [{page.page_kind}]")
        masked = None
        cleaned = None
        if 1 in stage_set:
            masked, raw = run_stage1_text_mask(page)
            altered = float(np.mean(masked != raw)) * 100.0
            print(
                f"  stage 1 (text mask): {altered:.1f}% of pixels altered. "
                f"overlay -> {(OUTPUT_DIR / f'{page.label}_01_text_masked.png').name}"
            )
        if 2 in stage_set:
            if masked is None:
                masked, _ = run_stage1_text_mask(page, save_overlays=False)
            cleaned, line_mask, stats = run_stage2_line_mask(page, masked)
            print(
                f"  stage 2 (line mask): "
                f"min_h/v={stats['min_line_length']}px, long={stats['min_long_length']}px, "
                f"coverage={stats['line_mask_coverage_pct']:.2f}%. "
                f"overlay -> {(OUTPUT_DIR / f'{page.label}_02_lines_masked.png').name}"
            )
        if 3 in stage_set:
            if cleaned is None:
                if masked is None:
                    masked, _ = run_stage1_text_mask(page, save_overlays=False)
                cleaned, _, _ = run_stage2_line_mask(page, masked, save_overlays=False)
            t0 = time.time()
            scallops = run_stage3_scallops(page, cleaned)
            elapsed = time.time() - t0
            counts = {o: 0 for o in ("TOP", "BOTTOM", "LEFT", "RIGHT")}
            for s in scallops:
                counts[s.orientation] += 1
            print(
                f"  stage 3 (scallops): {len(scallops)} detected in {elapsed:.1f}s "
                f"(TOP={counts['TOP']} BOTTOM={counts['BOTTOM']} LEFT={counts['LEFT']} RIGHT={counts['RIGHT']}) "
                f"scales={list(DEFAULT_SCALES)} thresh={DEFAULT_MATCH_THRESHOLD}. "
                f"overlay -> {(OUTPUT_DIR / f'{page.label}_03_scallops.png').name}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
