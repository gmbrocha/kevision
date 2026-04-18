"""Sheet-index parser.

For a given PDF and target revision (e.g. "REVISION #1"), find the index page,
locate every X mark in the target revision's column, and extract the
(row number, sheet number, sheet name) for each. Write to CSV.

The index is text + table grid in the source PDF -- no CV needed.

Some PDFs carry a non-zero `page.rotation` (e.g., Rev 2's index has rotation=90).
We apply `page.rotation_matrix` to every word/header bbox once at the top so
everything below works in a single canonical orientation that matches what
you see on screen: column headers vertical, rows horizontal, X marks stacking
down each revision's column.

Usage:
    python parse.py <pdf_path> --revision "REVISION #2" -o output/rev2.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parents[2]

# Sheet IDs are 1-3 uppercase letters + 3+ digits (optional .N suffix). The fixture
# uses prefixes like GI, AD, AE, IN, PL, EL, EP, MP, MH, S, SF, QH, FA, etc.
# Permissive pattern future-proofs against unseen prefixes (T-, FP-, PA- etc.).
SHEET_ID_RE = re.compile(r"^[A-Z]{1,3}\d{3,4}(?:\.\d+)?$")
ROW_NUM_RE = re.compile(r"^\d{1,3}$")
INDEX_HEADER_TOKENS = ("PAGE NO.", "SHEET NO.", "SHEET NAME")
REVISION_DATE_RE = re.compile(r"REVISION\s+#\d+\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)

# Tolerances in display-space PDF units (~pixels at 72 DPI for these PDFs)
ROW_Y_TOLERANCE = 6.0      # words within +/- this y-distance of an X are on the same row
COLUMN_X_TOLERANCE = 6.0   # X word x-centroid must be within +/- this of header x-extent


@dataclass
class RevisionItem:
    revision_label: str
    revision_date: str
    revision_set: str
    source_pdf: str
    index_page_index: int
    row_number: str
    sheet_number: str
    sheet_name: str
    x_position: str  # "x,y" in display-space coords; useful for debugging


# ---------------------------------------------------------------------------
# Coordinate normalization
# ---------------------------------------------------------------------------


def _transform_bbox(bbox: tuple, mat: fitz.Matrix) -> tuple[float, float, float, float]:
    """Apply a PyMuPDF Matrix to a (x0, y0, x1, y1) bbox; return normalized rect."""
    rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3]) * mat
    rect.normalize()
    return (rect.x0, rect.y0, rect.x1, rect.y1)


def _normalized_words(page: fitz.Page) -> list[tuple]:
    """Return page words with bboxes transformed into display-rotated space."""
    mat = page.rotation_matrix
    out = []
    for w in page.get_text("words"):
        x0, y0, x1, y1 = _transform_bbox((w[0], w[1], w[2], w[3]), mat)
        out.append((x0, y0, x1, y1, w[4], *w[5:]))
    return out


def _normalized_lines(page: fitz.Page) -> list[dict]:
    """Return page text-dict lines with bboxes transformed into display-rotated space.

    Each line dict has: text, bbox (tuple), dir (tuple).
    """
    mat = page.rotation_matrix
    rotation = page.rotation  # 0/90/180/270
    out: list[dict] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if not text:
                continue
            bbox = _transform_bbox(tuple(line.get("bbox", (0, 0, 0, 0))), mat)
            dx, dy = line.get("dir", (1.0, 0.0))
            # Apply same rotation to the direction vector (no translation).
            # rotation_matrix.a..f = (a, b, c, d, e, f) -> rotated dir = (a*dx + c*dy, b*dx + d*dy)
            ndx = mat.a * dx + mat.c * dy
            ndy = mat.b * dx + mat.d * dy
            out.append({"text": text, "bbox": bbox, "dir": (ndx, ndy), "rotation": rotation})
    return out


# ---------------------------------------------------------------------------
# Index page detection
# ---------------------------------------------------------------------------


def score_index_likelihood(page: fitz.Page) -> int:
    text_upper = (page.get_text("text") or "").upper()
    score = 0
    for token in INDEX_HEADER_TOKENS:
        if token in text_upper:
            score += 5
    if "SHEET INDEX" in text_upper:
        score += 2
    words = page.get_text("words")
    sheet_id_count = sum(1 for w in words if SHEET_ID_RE.match((w[4] or "").strip()))
    score += min(20, sheet_id_count // 10)
    return score


def find_index_page(doc: fitz.Document) -> int | None:
    best = (-1, None)
    for i in range(doc.page_count):
        s = score_index_likelihood(doc[i])
        if s > best[0]:
            best = (s, i)
    return best[1] if best[0] > 0 else None


# ---------------------------------------------------------------------------
# Header geometry (in canonical / display-space coords)
# ---------------------------------------------------------------------------


@dataclass
class HeaderBlock:
    label: str
    bbox: tuple[float, float, float, float]
    full_text: str

    @property
    def column_x_extent(self) -> tuple[float, float]:
        return (self.bbox[0] - COLUMN_X_TOLERANCE, self.bbox[2] + COLUMN_X_TOLERANCE)


def find_revision_headers(page: fitz.Page, revision_label: str) -> list[HeaderBlock]:
    """Find every occurrence of e.g. 'REVISION #1 MM/DD/YYYY' on the page."""
    headers: list[HeaderBlock] = []
    label_upper = revision_label.upper()
    for line in _normalized_lines(page):
        text = line["text"]
        if label_upper not in text.upper():
            continue
        if not REVISION_DATE_RE.search(text):
            continue
        bbox = line["bbox"]
        # Skip tiny stray hits (e.g., the "REVISION #1" mention in revision-history boxes)
        # by requiring a tall narrow rect (vertical column header in display space).
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if height < 50 or width > height:
            continue
        headers.append(HeaderBlock(label=revision_label, bbox=bbox, full_text=text))
    return headers


# ---------------------------------------------------------------------------
# X-mark and row resolution
# ---------------------------------------------------------------------------


def word_centroid(word: tuple) -> tuple[float, float]:
    return ((word[0] + word[2]) / 2.0, (word[1] + word[3]) / 2.0)


def find_x_marks_in_column(words: list[tuple], header: HeaderBlock) -> list[tuple]:
    """Return X words whose x-centroid falls within the header's column."""
    x_lo, x_hi = header.column_x_extent
    out = []
    for w in words:
        if (w[4] or "").strip().upper() != "X":
            continue
        cx, _ = word_centroid(w)
        if x_lo <= cx <= x_hi:
            out.append(w)
    return out


def words_on_same_row(words: list[tuple], target_y: float) -> list[tuple]:
    return [w for w in words if abs(((w[1] + w[3]) / 2.0) - target_y) < ROW_Y_TOLERANCE]


ROW_NUMBER_MAX_DISTANCE_FROM_SHEET_ID = 120.0  # px; row num column sits just left of sheet ID
SHEET_ID_MAX_DISTANCE_FROM_X = 1100.0  # px; sheet ID for an X must be in the same physical column


def extract_row_data(
    row_words: list[tuple],
    x_left_bound: float,
) -> tuple[str, str, str]:
    """Pull (row_number, sheet_number, sheet_name) for one row of an index column.

    `x_left_bound` is the x-coordinate of the X mark whose row we're extracting.
    The index page has multiple physical columns side-by-side, each with its
    own sheet-ID + sheet-name + X-columns block. We must only consider words
    in the same physical column block as the X — i.e., words with center_x
    strictly less than `x_left_bound` AND within
    SHEET_ID_MAX_DISTANCE_FROM_X of it. Otherwise we'd resolve to a sheet
    ID from the column to the left.
    """
    candidate_words = [
        w for w in row_words
        if ((w[0] + w[2]) / 2.0) < x_left_bound
        and (x_left_bound - ((w[0] + w[2]) / 2.0)) < SHEET_ID_MAX_DISTANCE_FROM_X
    ]
    candidate_words.sort(key=lambda w: w[0])

    # Pick the rightmost sheet ID — closest to the X = same physical column.
    sheet_id_word = None
    for w in reversed(candidate_words):
        if SHEET_ID_RE.match((w[4] or "").strip()):
            sheet_id_word = w
            break
    if sheet_id_word is None:
        return "", "", ""
    sheet_number = (sheet_id_word[4] or "").strip()
    sheet_id_x_left = sheet_id_word[0]
    sheet_id_x_right = sheet_id_word[2]

    # Row number = numeric word just left of the sheet ID (skip the tiny "1"
    # inside the delta-marker triangle in the far-left margin).
    row_number = ""
    candidate_x = -1.0
    for w in candidate_words:
        if w[0] >= sheet_id_x_left:
            break
        text = (w[4] or "").strip()
        if not ROW_NUM_RE.match(text):
            continue
        gap = sheet_id_x_left - w[2]
        if gap > ROW_NUMBER_MAX_DISTANCE_FROM_SHEET_ID:
            continue
        if w[0] > candidate_x:
            candidate_x = w[0]
            row_number = text

    # Sheet name = words between the sheet ID and the X (still in same physical column).
    sheet_name_parts: list[str] = []
    for w in candidate_words:
        if w[0] < sheet_id_x_right:
            continue
        text = (w[4] or "").strip()
        if not text:
            continue
        if text.upper() == "X":
            break
        if SHEET_ID_RE.match(text):
            continue
        sheet_name_parts.append(text)

    sheet_name = " ".join(sheet_name_parts).strip()
    return row_number, sheet_number, sheet_name


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------


def parse_index(
    pdf_path: Path,
    revision_label: str,
    revision_set_label: str | None = None,
) -> list[RevisionItem]:
    doc = fitz.open(pdf_path)
    try:
        page_idx = find_index_page(doc)
        if page_idx is None:
            raise RuntimeError(f"No index page found in {pdf_path}")
        page = doc[page_idx]

        headers = find_revision_headers(page, revision_label)
        if not headers:
            raise RuntimeError(
                f"No '{revision_label}' column header found on index page {page_idx} of {pdf_path}"
            )

        revision_date = ""
        for h in headers:
            m = REVISION_DATE_RE.search(h.full_text)
            if m:
                revision_date = m.group(1)
                break

        words = _normalized_words(page)
        items: list[RevisionItem] = []
        seen_keys: set[tuple[str, str]] = set()

        for header in headers:
            for x_word in find_x_marks_in_column(words, header):
                cx, cy = word_centroid(x_word)
                row_words = words_on_same_row(words, cy)
                row_number, sheet_number, sheet_name = extract_row_data(row_words, cx)
                if not sheet_number:
                    continue
                key = (row_number, sheet_number)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                items.append(
                    RevisionItem(
                        revision_label=revision_label,
                        revision_date=revision_date,
                        revision_set=revision_set_label or pdf_path.parent.name,
                        source_pdf=str(pdf_path),
                        index_page_index=page_idx,
                        row_number=row_number,
                        sheet_number=sheet_number,
                        sheet_name=sheet_name,
                        x_position=f"{cx:.1f},{cy:.1f}",
                    )
                )
    finally:
        doc.close()

    items.sort(key=lambda it: (
        int(it.row_number) if it.row_number.isdigit() else 9999,
        it.sheet_number,
    ))
    return items


def write_csv(items: list[RevisionItem], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(items[0]).keys()) if items else [
        "revision_label", "revision_date", "revision_set", "source_pdf",
        "index_page_index", "row_number", "sheet_number", "sheet_name", "x_position",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse a sheet-index page for revision items.")
    parser.add_argument("pdf", type=Path, help="Path to the PDF containing the sheet index")
    parser.add_argument(
        "--revision", type=str, required=True,
        help="Revision header label to extract, e.g. 'REVISION #1' or 'REVISION #2'",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="CSV output path (defaults to experiments/.../output/<stem>__<rev>.csv)",
    )
    parser.add_argument(
        "--revision-set-label", type=str, default=None,
        help="Friendly name for the revision set (defaults to PDF parent folder name)",
    )
    args = parser.parse_args()

    pdf_path = args.pdf if args.pdf.is_absolute() else (Path.cwd() / args.pdf).resolve()
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return 1

    items = parse_index(pdf_path, args.revision, revision_set_label=args.revision_set_label)
    output = args.output
    if output is None:
        slug = args.revision.replace(" ", "_").replace("#", "").lower()
        output = Path(__file__).parent / "output" / f"{pdf_path.stem}__{slug}.csv"

    write_csv(items, output)
    print(f"Wrote {len(items)} revision item(s) to {output}")
    if items:
        print(f"  date: {items[0].revision_date}")
        print(f"  index page: {items[0].index_page_index}")
        print(f"  first 8 rows:")
        for item in items[:8]:
            print(f"    row={item.row_number:>3}  {item.sheet_number:<10}  {item.sheet_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
