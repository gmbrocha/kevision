"""Diagnostic dump of the sheet-index page text geometry.

Run this BEFORE writing parse.py so we know:
  - which page holds the index
  - where the "REVISION #N" column headers live
  - how many "X" word entries there are and their positions
  - how many sheet-ID-shaped words there are

Usage:
  python experiments/2026_04_index_parser/explore.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parents[2]

SHEET_ID_RE = re.compile(
    r"^(?:GI|AD|AE|IN|PL|EL|EP|MP|MH|ME|E|M|S|SF|CS|RFP)\d{3}(?:\.\d+)?$"
)
ROW_NUM_RE = re.compile(r"^\d{1,3}$")

PDFS = [
    ("Revision #1", "revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf"),
    ("Revision #2", "revision_sets/Revision #2 - Mod 5 grab bar supports/260309 - Drawing Rev2- Steel Grab Bars.pdf"),
]

INDEX_HEADER_TOKENS = ("PAGE NO.", "SHEET NO.", "SHEET NAME")


def score_index_likelihood(page: fitz.Page) -> int:
    """Heuristic score for 'this page is the sheet index'.

    A real index has the table column headers AND many sheet-ID-shaped words.
    Narrative pages may mention 'SHEET INDEX' but won't have the table headers
    or hundreds of sheet IDs.
    """
    text_upper = (page.get_text("text") or "").upper()
    score = 0
    for token in INDEX_HEADER_TOKENS:
        if token in text_upper:
            score += 5  # heavy weight for actual table headers
    if "SHEET INDEX" in text_upper:
        score += 2
    words = page.get_text("words")
    sheet_id_count = sum(1 for w in words if SHEET_ID_RE.match((w[4] or "").strip()))
    # one point per 10 sheet IDs, capped
    score += min(20, sheet_id_count // 10)
    return score


def find_index_page(doc: fitz.Document) -> int | None:
    """Scan every page; pick the one that looks most like the sheet index."""
    best = (-1, None)  # (score, page_index)
    for i in range(doc.page_count):
        s = score_index_likelihood(doc[i])
        if s > best[0]:
            best = (s, i)
    return best[1] if best[0] > 0 else None


def dump_pdf(label: str, pdf_path: Path) -> None:
    print(f"\n========== {label}: {pdf_path.name} ==========")
    doc = fitz.open(pdf_path)
    try:
        # Also print per-page scores so we can see why a page won
        scores = [(i, score_index_likelihood(doc[i])) for i in range(doc.page_count)]
        ranked = sorted(scores, key=lambda kv: -kv[1])[:5]
        print(f"  top index-likelihood scores: {ranked}")

        idx_page_no = find_index_page(doc)
        if idx_page_no is None:
            print("  no SHEET INDEX page found")
            return
        page = doc[idx_page_no]
        print(f"  chosen index page = {idx_page_no}, size = {page.rect.width:.0f} x {page.rect.height:.0f}")

        # Find every revision-header occurrence on the page.
        for label_to_find in ("REVISION #1", "REVISION #2", "REVISION #3", "CONFORMED SET"):
            rects = page.search_for(label_to_find)
            if not rects:
                continue
            print(f"  '{label_to_find}': {len(rects)} occurrences")
            for r in rects[:6]:  # cap output
                print(f"    bbox = ({r.x0:.1f},{r.y0:.1f}) - ({r.x1:.1f},{r.y1:.1f})  w={r.x1-r.x0:.1f} h={r.y1-r.y0:.1f}")

        words = page.get_text("words")
        print(f"  total words on page: {len(words)}")

        x_words = [w for w in words if (w[4] or "").strip().upper() == "X"]
        print(f"  'X' words: {len(x_words)}")
        if x_words:
            xs = [w[0] for w in x_words]
            ys = [w[1] for w in x_words]
            print(f"    x range: {min(xs):.0f} .. {max(xs):.0f}")
            print(f"    y range: {min(ys):.0f} .. {max(ys):.0f}")
            print(f"    sample (first 6): {[(round(w[0],1), round(w[1],1)) for w in x_words[:6]]}")

        sheet_id_words = [w for w in words if SHEET_ID_RE.match((w[4] or "").strip())]
        print(f"  sheet-ID-shaped words: {len(sheet_id_words)}")
        if sheet_id_words:
            print(f"    sample (first 6): {[(w[4], round(w[0],1), round(w[1],1)) for w in sheet_id_words[:6]]}")

        row_num_words = [w for w in words if ROW_NUM_RE.match((w[4] or "").strip())]
        print(f"  row-number-shaped words (1-3 digit ints): {len(row_num_words)}")

        # Also dump column-header anchor — vertical "REVISION #N MM/DD/YYYY" that defines column x-range.
        rev_date_re = re.compile(r"REVISION\s+#\d+\s+\d{2}/\d{2}/\d{4}", re.IGNORECASE)
        full_text_blocks = page.get_text("dict").get("blocks", [])
        full_revs = []
        for block in full_text_blocks:
            for line in block.get("lines", []):
                line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                if rev_date_re.search(line_text):
                    bbox = line.get("bbox")
                    full_revs.append((line_text, bbox, line.get("dir")))
        print(f"  full 'REVISION #N MM/DD/YYYY' lines: {len(full_revs)}")
        for text, bbox, direction in full_revs[:8]:
            print(f"    '{text}'  bbox={bbox}  dir={direction}")
    finally:
        doc.close()


def main() -> int:
    for label, rel in PDFS:
        dump_pdf(label, REPO_ROOT / rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
