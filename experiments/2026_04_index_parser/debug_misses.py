"""Diagnose why some X marks aren't producing CSV rows.

For every X word on the index page, report:
  - position (in normalized coords)
  - which header column it falls inside (if any)
  - distance to the nearest header column (if not inside one)
  - whether row-data extraction produced a sheet_number for it
  - whether dedup dropped it
"""
from __future__ import annotations

import sys
from pathlib import Path

EXP_DIR = Path(__file__).parent
sys.path.insert(0, str(EXP_DIR))

import fitz  # noqa: E402

from parse import (  # noqa: E402
    COLUMN_X_TOLERANCE,
    ROW_Y_TOLERANCE,
    SHEET_ID_RE,
    _normalized_words,
    extract_row_data,
    find_index_page,
    find_revision_headers,
    word_centroid,
    words_on_same_row,
)


def main(pdf_rel: str, revision_label: str) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    pdf_path = repo_root / pdf_rel
    doc = fitz.open(pdf_path)
    page_idx = find_index_page(doc)
    page = doc[page_idx]
    headers = find_revision_headers(page, revision_label)
    print(f"PDF: {pdf_path.name}")
    print(f"Index page: {page_idx}")
    print(f"Revision: {revision_label}")
    print(f"Headers found: {len(headers)}")
    for i, h in enumerate(headers):
        x_lo, x_hi = h.column_x_extent
        print(f"  header {i}: bbox=({h.bbox[0]:.1f},{h.bbox[1]:.1f},{h.bbox[2]:.1f},{h.bbox[3]:.1f})  "
              f"col_x_extent=[{x_lo:.1f},{x_hi:.1f}]  text='{h.full_text}'")

    words = _normalized_words(page)
    x_words = [w for w in words if (w[4] or "").strip().upper() == "X"]
    print(f"\nTotal X words on page: {len(x_words)}")

    # Count Xs that fall in any of our header columns
    in_columns = []
    out_of_columns = []
    for w in x_words:
        cx, cy = word_centroid(w)
        matched = None
        for h_idx, h in enumerate(headers):
            x_lo, x_hi = h.column_x_extent
            if x_lo <= cx <= x_hi:
                matched = h_idx
                break
        if matched is not None:
            in_columns.append((w, matched))
        else:
            out_of_columns.append(w)

    print(f"  in-column: {len(in_columns)}")
    print(f"  out-of-column: {len(out_of_columns)}")

    # For each in-column X, attempt extraction
    seen_keys: set[tuple[str, str]] = set()
    accepted = 0
    no_sheet = 0
    deduped = 0
    no_sheet_examples = []
    deduped_examples = []
    for w, h_idx in in_columns:
        cx, cy = word_centroid(w)
        row_words = words_on_same_row(words, cy)
        row_number, sheet_number, sheet_name = extract_row_data(row_words, cx)
        if not sheet_number:
            no_sheet += 1
            if len(no_sheet_examples) < 8:
                # show what's on this row to debug
                row_text = sorted(
                    [(round(rw[0], 1), (rw[4] or "").strip()) for rw in row_words if (rw[4] or "").strip()],
                    key=lambda kv: kv[0],
                )
                no_sheet_examples.append({
                    "x_pos": (round(cx, 1), round(cy, 1)),
                    "header": h_idx,
                    "row_words": row_text[:12],
                })
            continue
        key = (row_number, sheet_number)
        if key in seen_keys:
            deduped += 1
            if len(deduped_examples) < 5:
                deduped_examples.append({
                    "key": key,
                    "x_pos": (round(cx, 1), round(cy, 1)),
                    "header": h_idx,
                })
            continue
        seen_keys.add(key)
        accepted += 1

    print(f"\nIn-column X marks breakdown:")
    print(f"  accepted into CSV: {accepted}")
    print(f"  no sheet ID on row: {no_sheet}")
    print(f"  duplicate (already accepted by another physical column): {deduped}")

    if no_sheet_examples:
        print(f"\nFirst few 'no sheet ID' cases (where extract_row_data returned no sheet_number):")
        for ex in no_sheet_examples:
            print(f"  X at {ex['x_pos']} (column {ex['header']})")
            print(f"    row words: {ex['row_words']}")

    if deduped_examples:
        print(f"\nFirst few duplicate cases:")
        for ex in deduped_examples:
            print(f"  {ex['key']}  X at {ex['x_pos']} (column {ex['header']})")

    if out_of_columns:
        # Group out-of-column Xs by their x-coordinate (rounded) to see column clusters
        from collections import Counter
        x_clusters = Counter(round(word_centroid(w)[0], 0) for w in out_of_columns)
        print(f"\nOut-of-column X marks grouped by x-coordinate (top clusters):")
        header_centers = sorted({(h.bbox[0] + h.bbox[2]) / 2 for h in headers})
        print(f"  REVISION #1 header x-centers: {[round(c,1) for c in header_centers]}")
        for x_pos, count in sorted(x_clusters.items(), key=lambda kv: -kv[1])[:15]:
            nearest_dist = min(abs(x_pos - c) for c in header_centers)
            marker = "  <-- WITHIN 50px of a Rev 1 column" if nearest_dist < 50 else ""
            print(f"    x={x_pos:>7}  count={count:>3}  nearest Rev 1 header: {nearest_dist:.1f}px away{marker}")

    print(f"\nTolerances in use: COLUMN_X_TOLERANCE={COLUMN_X_TOLERANCE}, ROW_Y_TOLERANCE={ROW_Y_TOLERANCE}")
    doc.close()
    return 0


if __name__ == "__main__":
    sys.exit(
        main(
            "revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf",
            "REVISION #1",
        )
    )
