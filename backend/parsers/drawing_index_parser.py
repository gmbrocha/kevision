"""Drawing-index parser.

For a given PDF and target revision (for example, ``REVISION #1``), find the
index page, locate every X mark in the target revision column, and extract the
row number, sheet number, and sheet name directly from the PDF text layer.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import fitz

SHEET_ID_RE = re.compile(r"^[A-Z]{1,3}\d{3,4}(?:\.\d+)?$")
ROW_NUM_RE = re.compile(r"^\d{1,3}$")
INDEX_HEADER_TOKENS = ("PAGE NO.", "SHEET NO.", "SHEET NAME")
REVISION_DATE_RE = re.compile(r"REVISION\s+#\d+\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)

ROW_Y_TOLERANCE = 6.0
COLUMN_X_TOLERANCE = 6.0
ROW_NUMBER_MAX_DISTANCE_FROM_SHEET_ID = 120.0
SHEET_ID_MAX_DISTANCE_FROM_X = 1100.0


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
    x_position: str


@dataclass
class HeaderBlock:
    label: str
    bbox: tuple[float, float, float, float]
    full_text: str

    @property
    def column_x_extent(self) -> tuple[float, float]:
        return (self.bbox[0] - COLUMN_X_TOLERANCE, self.bbox[2] + COLUMN_X_TOLERANCE)


def _transform_bbox(bbox: tuple, mat: fitz.Matrix) -> tuple[float, float, float, float]:
    rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3]) * mat
    rect.normalize()
    return (rect.x0, rect.y0, rect.x1, rect.y1)


def _normalized_words(page: fitz.Page) -> list[tuple]:
    mat = page.rotation_matrix
    out = []
    for word in page.get_text("words"):
        x0, y0, x1, y1 = _transform_bbox((word[0], word[1], word[2], word[3]), mat)
        out.append((x0, y0, x1, y1, word[4], *word[5:]))
    return out


def _normalized_lines(page: fitz.Page) -> list[dict]:
    mat = page.rotation_matrix
    rotation = page.rotation
    out: list[dict] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if not text:
                continue
            bbox = _transform_bbox(tuple(line.get("bbox", (0, 0, 0, 0))), mat)
            dx, dy = line.get("dir", (1.0, 0.0))
            ndx = mat.a * dx + mat.c * dy
            ndy = mat.b * dx + mat.d * dy
            out.append({"text": text, "bbox": bbox, "dir": (ndx, ndy), "rotation": rotation})
    return out


def score_index_likelihood(page: fitz.Page) -> int:
    text_upper = (page.get_text("text") or "").upper()
    score = 0
    for token in INDEX_HEADER_TOKENS:
        if token in text_upper:
            score += 5
    if "SHEET INDEX" in text_upper:
        score += 2
    words = page.get_text("words")
    sheet_id_count = sum(1 for word in words if SHEET_ID_RE.match((word[4] or "").strip()))
    score += min(20, sheet_id_count // 10)
    return score


def find_index_page(doc: fitz.Document) -> int | None:
    best = (-1, None)
    for index in range(doc.page_count):
        score = score_index_likelihood(doc[index])
        if score > best[0]:
            best = (score, index)
    return best[1] if best[0] > 0 else None


def find_revision_headers(page: fitz.Page, revision_label: str) -> list[HeaderBlock]:
    headers: list[HeaderBlock] = []
    label_upper = revision_label.upper()
    for line in _normalized_lines(page):
        text = line["text"]
        if label_upper not in text.upper():
            continue
        if not REVISION_DATE_RE.search(text):
            continue
        bbox = line["bbox"]
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if height < 50 or width > height:
            continue
        headers.append(HeaderBlock(label=revision_label, bbox=bbox, full_text=text))
    return headers


def word_centroid(word: tuple) -> tuple[float, float]:
    return ((word[0] + word[2]) / 2.0, (word[1] + word[3]) / 2.0)


def find_x_marks_in_column(words: list[tuple], header: HeaderBlock) -> list[tuple]:
    x_lo, x_hi = header.column_x_extent
    out = []
    for word in words:
        if (word[4] or "").strip().upper() != "X":
            continue
        cx, _ = word_centroid(word)
        if x_lo <= cx <= x_hi:
            out.append(word)
    return out


def words_on_same_row(words: list[tuple], target_y: float) -> list[tuple]:
    return [word for word in words if abs(((word[1] + word[3]) / 2.0) - target_y) < ROW_Y_TOLERANCE]


def extract_row_data(row_words: list[tuple], x_left_bound: float) -> tuple[str, str, str]:
    candidate_words = [
        word
        for word in row_words
        if ((word[0] + word[2]) / 2.0) < x_left_bound
        and (x_left_bound - ((word[0] + word[2]) / 2.0)) < SHEET_ID_MAX_DISTANCE_FROM_X
    ]
    candidate_words.sort(key=lambda word: word[0])

    sheet_id_word = None
    for word in reversed(candidate_words):
        if SHEET_ID_RE.match((word[4] or "").strip()):
            sheet_id_word = word
            break
    if sheet_id_word is None:
        return "", "", ""

    sheet_number = (sheet_id_word[4] or "").strip()
    sheet_id_x_left = sheet_id_word[0]
    sheet_id_x_right = sheet_id_word[2]

    row_number = ""
    candidate_x = -1.0
    for word in candidate_words:
        if word[0] >= sheet_id_x_left:
            break
        text = (word[4] or "").strip()
        if not ROW_NUM_RE.match(text):
            continue
        gap = sheet_id_x_left - word[2]
        if gap > ROW_NUMBER_MAX_DISTANCE_FROM_SHEET_ID:
            continue
        if word[0] > candidate_x:
            candidate_x = word[0]
            row_number = text

    sheet_name_parts: list[str] = []
    for word in candidate_words:
        if word[0] < sheet_id_x_right:
            continue
        text = (word[4] or "").strip()
        if not text:
            continue
        if text.upper() == "X":
            break
        if SHEET_ID_RE.match(text):
            continue
        sheet_name_parts.append(text)

    return row_number, sheet_number, " ".join(sheet_name_parts).strip()


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
            raise RuntimeError(f"No '{revision_label}' column header found on index page {page_idx} of {pdf_path}")

        revision_date = ""
        for header in headers:
            match = REVISION_DATE_RE.search(header.full_text)
            if match:
                revision_date = match.group(1)
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
                        source_pdf=pdf_path.name,
                        index_page_index=page_idx,
                        row_number=row_number,
                        sheet_number=sheet_number,
                        sheet_name=sheet_name,
                        x_position=f"{cx:.1f},{cy:.1f}",
                    )
                )
    finally:
        doc.close()

    items.sort(key=lambda item: (int(item.row_number) if item.row_number.isdigit() else 9999, item.sheet_number))
    return items


def write_csv(items: list[RevisionItem], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(items[0]).keys()) if items else [
        "revision_label",
        "revision_date",
        "revision_set",
        "source_pdf",
        "index_page_index",
        "row_number",
        "sheet_number",
        "sheet_name",
        "x_position",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse a drawing index page for revision items.")
    parser.add_argument("pdf", type=Path, help="Path to the PDF containing the sheet index")
    parser.add_argument("--revision", type=str, required=True, help="Revision header label to extract, e.g. 'REVISION #1'")
    parser.add_argument("-o", "--output", type=Path, default=None, help="CSV output path")
    parser.add_argument("--revision-set-label", type=str, default=None, help="Friendly name for the revision set")
    args = parser.parse_args(argv)

    pdf_path = args.pdf if args.pdf.is_absolute() else (Path.cwd() / args.pdf).resolve()
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return 1

    items = parse_index(pdf_path, args.revision, revision_set_label=args.revision_set_label)
    output = args.output or Path.cwd() / "drawing_index.csv"
    write_csv(items, output)
    print(f"Wrote {len(items)} revision item(s) to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
