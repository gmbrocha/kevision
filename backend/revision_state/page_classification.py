from __future__ import annotations


INDEX_PAGE_MARKERS = (
    "SHEET INDEX",
    "DRAWING INDEX",
    "CONFORMED SET",
    "PAGE NO. SHEET NO.",
    "SHEET NO. SHEET NAME",
)


def sheet_is_index_like(sheet) -> bool:
    """Return True when a sheet record is a drawing index, not a drawing page."""

    title = " ".join((getattr(sheet, "sheet_title", "") or "").split()).upper()
    excerpt = " ".join((getattr(sheet, "page_text_excerpt", "") or "").split()).upper()
    combined = f"{title} {excerpt[:1000]}"
    if any(marker in combined for marker in INDEX_PAGE_MARKERS):
        return True
    return len(title) > 220 and title.count(" X ") >= 6
