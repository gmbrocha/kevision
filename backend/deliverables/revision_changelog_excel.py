"""Revision changelog Excel exporter.

This module owns the current workbook layout used for the review/export
deliverable. The schema is documented in `docs/revision_changelog_format.md`.

One row per (sheet, detail) group of approved change items. Sub-items inside a
group stack as numbered bullets (`1)`, `2)`, ...) inside the merged
`Scope Included` cell. The cropped cloud image is embedded in column F.

Columns intentionally preserve the current downstream workbook shape,
including the historical `Qoute Received?` typo.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage

from ..revision_state.models import ChangeItem, RevisionSet, SheetVersion
from ..utils import clean_display_text
from ..workspace import WorkspaceStore


COLUMNS: list[tuple[str, float]] = [
    ("Correlation ", 12),
    ("Drawing #", 12),
    ("Revision # ", 24),
    ("Detail #", 18),
    ("Scope Included ", 60),
    ("Detail View ", 40),
    ("", 30),
    ("Responsible Contractor", 22),
    ("Cost?", 10),
    ("Qoute Received?", 16),
]

ROWS_PER_GROUP = 14
SCOPE_COL = 5
DETAIL_VIEW_COL = 6
CROP_TARGET_PX = (520, ROWS_PER_GROUP * 18)
HEADER_FILL = "111827"
HEADER_TEXT = "FFFFFF"
BLOCK_FILL = "FFFFFF"
BLOCK_ALT_FILL = "F8FAFC"
META_FILL = "EEF3F8"
META_ALT_FILL = "E7EEF6"
CROP_FILL = "FFFFFF"
BORDER_COLOR = "CDD6E2"
BORDER_STRONG_COLOR = "7D8DA1"
ACCENT_COLOR = "0F766E"


@dataclass
class RevisionChangelogRow:
    correlation: str
    drawing: str
    revision: str
    detail: str
    scope_lines: list[str]
    crop_path: str | None
    item_ids: list[str]


def write_revision_changelog(store: WorkspaceStore, output_path: Path) -> Path:
    rows = _build_rows(store)
    _write_workbook(rows, output_path)
    return output_path


def _build_rows(store: WorkspaceStore) -> list[RevisionChangelogRow]:
    revision_sets_by_id = {rs.id: rs for rs in store.data.revision_sets}
    sheets_by_id = {sheet.id: sheet for sheet in store.data.sheets}
    clouds_by_id = {cloud.id: cloud for cloud in store.data.clouds}

    approved = [item for item in store.data.change_items if item.status == "approved"]
    groups: dict[tuple[str, str, str], list[ChangeItem]] = {}
    for item in approved:
        key = _group_key(item)
        groups.setdefault(key, []).append(item)

    grouped_rows: list[tuple[str, int, RevisionChangelogRow]] = []
    sheet_counters: dict[str, int] = {}
    for (sheet_id, group_kind, group_ref), items in groups.items():
        sheet_counters[sheet_id] = sheet_counters.get(sheet_id, 0) + 1
        seq = sheet_counters[sheet_id]
        canonical_sheet = items[0]
        sheet = sheets_by_id.get(canonical_sheet.sheet_version_id)
        revision_set = revision_sets_by_id.get(sheet.revision_set_id) if sheet else None
        crop_path = _pick_crop_path(items, clouds_by_id)
        detail_ref = group_ref if group_kind == "detail" else None
        revision_row = RevisionChangelogRow(
            correlation=_format_correlation(sheet_id, seq),
            drawing=_format_drawing(sheet_id),
            revision=_format_revision(revision_set),
            detail=_format_detail(detail_ref),
            scope_lines=_collect_scope_lines(items),
            crop_path=crop_path,
            item_ids=[item.id for item in items],
        )
        grouped_rows.append((sheet_id, seq, revision_row))

    grouped_rows.sort(key=lambda triple: (triple[0], triple[1]))
    return [row for _, _, row in grouped_rows]


def _group_key(item: ChangeItem) -> tuple[str, str, str]:
    if item.detail_ref:
        return (item.sheet_id, "detail", item.detail_ref)
    if item.cloud_candidate_id:
        return (item.sheet_id, "cloud", item.cloud_candidate_id)
    return (item.sheet_id, "item", item.id)


def _format_correlation(sheet_id: str, seq: int) -> str:
    digits = "".join(re.findall(r"\d+", sheet_id))
    if not digits:
        return f"{sheet_id}.{seq}"
    return f"{digits}.{seq}"


def _format_drawing(sheet_id: str) -> str:
    match = re.match(r"^([A-Za-z]+)[-\s]?(\d.*)$", sheet_id.strip())
    if not match:
        return sheet_id
    letters, rest = match.groups()
    return f"{letters.upper()}-{rest}"


def _format_revision(revision_set: RevisionSet | None) -> str:
    if revision_set is None:
        return ""
    label = clean_display_text(revision_set.label) or f"Revision #{revision_set.set_number}"
    base = re.split(r"\s+-\s+", label, maxsplit=1)[0]
    if revision_set.set_date:
        return f"{base} - {revision_set.set_date}"
    return base


def _format_detail(detail_ref: str | None) -> str:
    if not detail_ref:
        return "N/A - Cloud Only "
    cleaned = clean_display_text(detail_ref)
    if not cleaned:
        return "N/A - Cloud Only "
    if cleaned.lower().startswith("detail"):
        return f"{cleaned} "
    return f"Detail {cleaned} "


def _collect_scope_lines(items: list[ChangeItem]) -> list[str]:
    seen: set[str] = set()
    lines: list[str] = []
    for item in items:
        text = clean_display_text(item.reviewer_text or item.raw_text)
        if not text:
            continue
        for piece in re.split(r"\s*\|\s*|\s*;\s*|[\r\n]+", text):
            line = clean_display_text(piece).strip(" -|:,.;")
            if not line:
                continue
            normalized = line.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            lines.append(line)
    return lines


def _pick_crop_path(items: list[ChangeItem], clouds_by_id: dict[str, object]) -> str | None:
    for item in items:
        cloud_id = item.cloud_candidate_id
        if not cloud_id:
            continue
        cloud = clouds_by_id.get(cloud_id)
        if cloud is None:
            continue
        path = getattr(cloud, "image_path", "")
        if path and Path(path).exists():
            return path
    return None


def _write_workbook(rows: list[RevisionChangelogRow], output_path: Path) -> None:
    wb = Workbook()
    wb.properties.creator = "KEVISION"
    wb.properties.title = "Revision Changelog"
    ws = wb.active
    ws.title = "Sheet1"
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A2"
    ws.sheet_properties.tabColor = ACCENT_COLOR

    header_font = Font(bold=True, color=HEADER_TEXT)
    header_fill = PatternFill("solid", fgColor=HEADER_FILL)
    thin = Side(border_style="thin", color=BORDER_COLOR)
    strong = Side(border_style="medium", color=BORDER_STRONG_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    wrap = Alignment(wrap_text=True, vertical="top")
    center_wrap = Alignment(wrap_text=True, vertical="top", horizontal="center")

    for idx, (header, width) in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = border
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.row_dimensions[1].height = 30

    cursor = 2
    for row_index, revision_row in enumerate(rows):
        block_top = cursor
        block_bottom = cursor + ROWS_PER_GROUP - 1
        is_alt = row_index % 2 == 1

        ws.cell(row=block_top, column=1, value=revision_row.correlation).alignment = wrap
        ws.cell(row=block_top, column=2, value=revision_row.drawing).alignment = wrap
        ws.cell(row=block_top, column=3, value=revision_row.revision).alignment = wrap
        ws.cell(row=block_top, column=4, value=revision_row.detail).alignment = wrap

        scope_text = _format_scope_text(revision_row.scope_lines)
        scope_cell = ws.cell(row=block_top, column=SCOPE_COL, value=scope_text)
        scope_cell.alignment = wrap

        block_fill = PatternFill("solid", fgColor=BLOCK_ALT_FILL if is_alt else BLOCK_FILL)
        meta_fill = PatternFill("solid", fgColor=META_ALT_FILL if is_alt else META_FILL)
        crop_fill = PatternFill("solid", fgColor=CROP_FILL)
        for r in range(block_top, block_bottom + 1):
            ws.row_dimensions[r].height = 19
            for c in range(1, len(COLUMNS) + 1):
                cell = ws.cell(row=r, column=c)
                cell.fill = meta_fill if c <= 4 else (crop_fill if c == DETAIL_VIEW_COL else block_fill)
                cell.alignment = center_wrap if c <= 4 else wrap
                cell.border = Border(
                    left=thin,
                    right=thin,
                    top=strong if r == block_top else thin,
                    bottom=strong if r == block_bottom else thin,
                )
                if r == block_top and c <= 4:
                    cell.font = Font(bold=True, color="111827")

        if block_bottom > block_top:
            ws.merge_cells(
                start_row=block_top, start_column=SCOPE_COL,
                end_row=block_bottom, end_column=SCOPE_COL,
            )
            ws.merge_cells(
                start_row=block_top, start_column=DETAIL_VIEW_COL,
                end_row=block_bottom, end_column=DETAIL_VIEW_COL,
            )

        if revision_row.crop_path:
            try:
                _embed_image(ws, revision_row.crop_path, anchor_row=block_top, anchor_col=DETAIL_VIEW_COL)
            except Exception:
                ws.cell(row=block_top, column=DETAIL_VIEW_COL, value=f"[crop: {Path(revision_row.crop_path).name}]")

        cursor = block_bottom + 1

    last_column = get_column_letter(len(COLUMNS))
    ws.auto_filter.ref = f"A1:{last_column}{max(ws.max_row, 1)}"
    ws.print_title_rows = "1:1"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)


def _format_scope_text(lines: list[str]) -> str:
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]
    return "\n".join(f"{i}) {line}" for i, line in enumerate(lines, 1))


def _embed_image(ws, image_path: str, *, anchor_row: int, anchor_col: int) -> None:
    """Resize the source crop to fit the merged cell area and anchor it there.

    openpyxl's image insertion takes pixel dimensions; we resize through Pillow
    first so the embedded PNG is small (Kevin's file uses ~500px-wide crops).
    """
    target_w, target_h = CROP_TARGET_PX
    with PILImage.open(image_path) as src:
        src.load()
        src = src.convert("RGB") if src.mode in ("RGBA", "P") else src
        src.thumbnail((target_w, target_h), PILImage.LANCZOS)
        buf = io.BytesIO()
        src.save(buf, format="PNG", optimize=True)
        buf.seek(0)
    img = XLImage(buf)
    img.anchor = f"{get_column_letter(anchor_col)}{anchor_row}"
    ws.add_image(img)
