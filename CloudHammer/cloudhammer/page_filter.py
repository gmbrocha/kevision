from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


INDEX_RE = re.compile(
    r"\b("
    r"drawing\s+index|sheet\s+index|index\s+of\s+drawings|list\s+of\s+drawings|"
    r"drawing\s+list|sheet\s+list|table\s+of\s+contents|contents|index"
    r")\b",
    re.IGNORECASE,
)
COVER_RE = re.compile(r"\b(cover\s+sheet|title\s+sheet)\b|^\s*cover\s*$", re.IGNORECASE)
GENERAL_NOTES_RE = re.compile(r"\bgeneral\s+notes?\b", re.IGNORECASE)
PLAN_RE = re.compile(r"\b(plan|floor|roof|reflected|enlarged|demolition|demo|elevation|section|detail)\b", re.IGNORECASE)


@dataclass(frozen=True)
class PageFilterResult:
    is_excluded: bool
    exclude_reason: str


def classify_roi_source_page(row: dict) -> PageFilterResult:
    values = [
        str(row.get("pdf_stem") or ""),
        Path(str(row.get("pdf_path") or "")).stem,
        str(row.get("sheet_title") or ""),
        str(row.get("sheet_id") or ""),
        str(row.get("page_label") or ""),
        str(row.get("page_name") or ""),
        str(row.get("_page_text") or ""),
    ]
    text = " | ".join(value for value in values if value).strip()
    if not text:
        return PageFilterResult(False, "none")
    if INDEX_RE.search(text):
        return PageFilterResult(True, "index_page")
    if COVER_RE.search(text):
        return PageFilterResult(True, "cover_sheet")
    if GENERAL_NOTES_RE.search(text) and not PLAN_RE.search(text):
        return PageFilterResult(True, "non_drawing_sheet")
    return PageFilterResult(False, "none")


@lru_cache(maxsize=512)
def read_pdf_page_text(pdf_path: str, page_index: int) -> str:
    try:
        import fitz  # type: ignore

        doc = fitz.open(pdf_path)
        try:
            return doc[int(page_index)].get_text("text") or ""
        finally:
            doc.close()
    except Exception:
        return ""


def classify_roi_source_page_with_pdf_text(row: dict) -> PageFilterResult:
    enriched = dict(row)
    enriched["_page_text"] = read_pdf_page_text(str(row.get("pdf_path") or ""), int(row.get("page_index") or 0))
    return classify_roi_source_page(enriched)


def count_page_filter_results(rows: list[dict], inspect_pdf_text: bool = False) -> dict[str, int]:
    counts = {
        "total_pages": len(rows),
        "included_pages": 0,
        "excluded_pages": 0,
        "excluded_index_cover_pages": 0,
    }
    for row in rows:
        result = classify_roi_source_page_with_pdf_text(row) if inspect_pdf_text else classify_roi_source_page(row)
        if result.is_excluded:
            counts["excluded_pages"] += 1
            if result.exclude_reason in {"index_page", "cover_sheet"}:
                counts["excluded_index_cover_pages"] += 1
        else:
            counts["included_pages"] += 1
    return counts
