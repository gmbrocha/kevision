"""Discovery: list every page of the fixture PDFs and the sheet ID we extract from it.

Run once to find the page indices for our test pages (GI104, AD104, SF110, etc.)
so the detection script can target real pages instead of guessing.
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parents[2]

SHEET_ID_PATTERN = re.compile(
    r"\b(?:GI|AD|AE|IN|PL|EL|EP|MP|MH|ME|E|M|S|SF|CS|RFP)\d{3}(?:\.\d+)?\b"
)

PDFS = [
    "revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf",
    "revision_sets/Revision #2 - Mod 5 grab bar supports/260309 - Drawing Rev2- Steel Grab Bars.pdf",
    "revision_sets/Revision #2 - Mod 5 grab bar supports/Drawing Rev2- Steel Grab Bars AE107.pdf",
    "revision_sets/Revision #2 - Mod 5 grab bar supports/Drawing Rev2- Steel Grab Bars R1 AE107.1.pdf",
]


def best_sheet_id(text: str) -> str | None:
    hits = SHEET_ID_PATTERN.findall(text or "")
    return hits[-1] if hits else None


def main() -> int:
    for rel_pdf in PDFS:
        pdf_path = REPO_ROOT / rel_pdf
        doc = fitz.open(pdf_path)
        print(f"\n=== {pdf_path.name} ({doc.page_count} pages) ===")
        for i in range(doc.page_count):
            page = doc[i]
            words = [
                word[4]
                for word in page.get_text("words")
                if word[0] >= page.rect.width * 0.64 and word[1] >= page.rect.height * 0.72
            ]
            title_block_text = " ".join(words)
            sheet_id = best_sheet_id(title_block_text) or best_sheet_id(page.get_text("text"))
            print(f"  page {i:>2}  sheet_id={sheet_id or '?':<10}  size={page.rect.width:.0f}x{page.rect.height:.0f}")
        doc.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
