"""Quick diagnostic — show what's where on a page."""
from __future__ import annotations

import sys
from pathlib import Path

EXP_DIR = Path(__file__).parent
sys.path.insert(0, str(EXP_DIR))

import fitz  # noqa: E402

from detect_deltas import (  # noqa: E402
    DEFAULT_DPI,
    extract_digit_words_in_pixels,
    find_triangle_candidates,
    render_page_gray,
    _dedupe_candidates,
    _native_to_pixel_matrix,
)


def main(pdf_path: str, page_index: int) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    pdf = repo_root / pdf_path
    doc = fitz.open(pdf)
    page = doc[page_index]
    print(f"PDF: {pdf.name}  page {page_index}")
    print(f"  rotation: {page.rotation}")
    print(f"  rect (display): {page.rect}")
    print(f"  mediabox (native): {page.mediabox}")
    print(f"  rotation_matrix: {page.rotation_matrix}")
    doc.close()

    gray, _ = render_page_gray(pdf, page_index)
    print(f"  rendered: {gray.shape[1]}x{gray.shape[0]}")
    candidates = _dedupe_candidates(find_triangle_candidates(gray))
    print(f"\nTriangles found: {len(candidates)}")
    for i, c in enumerate(candidates):
        print(f"  [{i}] centroid=({c.centroid[0]:.0f},{c.centroid[1]:.0f}) perim={c.perimeter:.0f} sides={[round(s,1) for s in c.side_lengths]}")

    digit_words = extract_digit_words_in_pixels(pdf, page_index)
    one_words = [w for w in digit_words if w["text"] == "1"]
    print(f"\n'1' digit words on page: {len(one_words)} (out of {len(digit_words)} total digit words)")
    for w in one_words[:30]:
        print(f"  '1' centroid=({w['centroid'][0]:.0f},{w['centroid'][1]:.0f}) bbox={tuple(round(c,0) for c in w['bbox'])}")

    # For each triangle, find nearest '1' digit
    print(f"\nFor each triangle, distance to nearest '1' digit:")
    for i, c in enumerate(candidates):
        nearest_d = float("inf")
        nearest_pos = None
        for w in one_words:
            d = ((c.centroid[0] - w["centroid"][0]) ** 2 + (c.centroid[1] - w["centroid"][1]) ** 2) ** 0.5
            if d < nearest_d:
                nearest_d = d
                nearest_pos = w["centroid"]
        print(f"  triangle [{i}] at ({c.centroid[0]:.0f},{c.centroid[1]:.0f}) -- nearest '1' at {nearest_pos[0]:.0f},{nearest_pos[1]:.0f} (dist={nearest_d:.1f}px, perim={c.perimeter:.0f})")
    return 0


if __name__ == "__main__":
    sys.exit(main(
        "revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf",
        17,
    ))
