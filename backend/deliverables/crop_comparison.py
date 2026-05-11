from __future__ import annotations

import math
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..revision_state.models import CloudCandidate, RevisionSet, SheetVersion
from ..revision_state.page_classification import sheet_is_index_like
from ..utils import parse_mmddyyyy
from ..workspace import WorkspaceStore


CONTEXT_PAD_MIN = 48.0
CONTEXT_PAD_MAX = 220.0
CONTEXT_PAD_FACTOR = 0.35
RENDER_ZOOM = 2.0
PANEL_WIDTH = 520
PANEL_HEIGHT = 430
HEADER_HEIGHT = 42
GAP = 18
BACKGROUND = (255, 255, 255)
PANEL_BACKGROUND = (248, 250, 252)
BORDER = (180, 190, 204)
TEXT = (17, 24, 39)
MUTED_TEXT = (71, 85, 105)
HIGHLIGHT = (15, 118, 110)


def find_previous_sheet_version(
    sheet: SheetVersion,
    sheets: list[SheetVersion],
    revision_sets_by_id: dict[str, RevisionSet],
) -> SheetVersion | None:
    if sheet_is_index_like(sheet):
        return None
    current_revision = revision_sets_by_id.get(sheet.revision_set_id)
    current_set_number = current_revision.set_number if current_revision else 0
    if current_set_number <= 1:
        return None
    candidates = [
        candidate
        for candidate in sheets
        if candidate.id != sheet.id
        and candidate.sheet_id == sheet.sheet_id
        and not sheet_is_index_like(candidate)
        and _is_prior_revision_set(candidate, current_set_number, revision_sets_by_id)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: _sheet_rank(candidate, revision_sets_by_id))


def _is_prior_revision_set(
    sheet: SheetVersion,
    current_set_number: int,
    revision_sets_by_id: dict[str, RevisionSet],
) -> bool:
    revision_set = revision_sets_by_id.get(sheet.revision_set_id)
    if not revision_set or revision_set.set_number <= 0:
        return False
    return revision_set.set_number < current_set_number


def build_cloud_comparison_image(
    store: WorkspaceStore,
    *,
    cloud: CloudCandidate,
    current_sheet: SheetVersion,
    previous_sheet: SheetVersion | None,
    output_path: Path,
    highlight_bboxes: list[list[float]] | None = None,
) -> Path | None:
    highlight_bboxes = highlight_bboxes or [cloud.bbox]
    context_bbox = _context_bbox(highlight_bboxes, current_sheet)
    current = _render_sheet_crop(
        store,
        current_sheet,
        context_bbox,
        highlight_bboxes=[_normalized_bbox(bbox) for bbox in highlight_bboxes],
    )
    if current is None:
        current = _open_existing_crop(store, cloud.image_path)
    if current is None:
        return None

    previous = None
    previous_label = "Previous revision"
    if previous_sheet is not None:
        previous_context = _scale_bbox(context_bbox, current_sheet, previous_sheet)
        previous_highlights = [_scale_bbox(_normalized_bbox(bbox), current_sheet, previous_sheet) for bbox in highlight_bboxes]
        previous = _render_sheet_crop(
            store,
            previous_sheet,
            previous_context,
            highlight_bboxes=previous_highlights,
        )
        previous_label = f"Previous: {_display_revision(previous_sheet, store)}"
    if previous is None:
        previous = _placeholder_panel_image("No previous sheet version")

    current_label = f"Current: {_display_revision(current_sheet, store)}"
    comparison = _compose(previous, current, previous_label=previous_label, current_label=current_label)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    comparison.save(output_path, format="PNG", optimize=True)
    return output_path


def _sheet_rank(sheet: SheetVersion, revision_sets_by_id: dict[str, RevisionSet]) -> tuple[int, tuple[int, int, int], int]:
    revision_set = revision_sets_by_id.get(sheet.revision_set_id)
    return (
        revision_set.set_number if revision_set else 0,
        parse_mmddyyyy(sheet.issue_date),
        sheet.page_number,
    )


def _display_revision(sheet: SheetVersion, store: WorkspaceStore) -> str:
    for revision_set in store.data.revision_sets:
        if revision_set.id == sheet.revision_set_id:
            return f"Rev {revision_set.set_number}"
    return "Rev"


def _normalized_bbox(values: list[int] | tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if len(values) < 4:
        return (0.0, 0.0, 0.0, 0.0)
    x, y, width, height = [float(value) for value in values[:4]]
    if width < 0:
        x += width
        width = abs(width)
    if height < 0:
        y += height
        height = abs(height)
    return (x, y, width, height)


def _context_bbox(bboxes: list[list[float]], sheet: SheetVersion) -> tuple[float, float, float, float]:
    normalized = [_normalized_bbox(bbox) for bbox in bboxes if len(bbox) >= 4]
    if not normalized:
        normalized = [(0.0, 0.0, 1.0, 1.0)]
    x1 = min(box[0] for box in normalized)
    y1 = min(box[1] for box in normalized)
    x2 = max(box[0] + box[2] for box in normalized)
    y2 = max(box[1] + box[3] for box in normalized)
    x, y, width, height = x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1)
    sheet_width = float(sheet.width or max(x + width, 1.0))
    sheet_height = float(sheet.height or max(y + height, 1.0))
    pad = max(CONTEXT_PAD_MIN, min(max(width, height) * CONTEXT_PAD_FACTOR, CONTEXT_PAD_MAX))
    left = max(0.0, x - pad)
    top = max(0.0, y - pad)
    right = min(sheet_width, x + width + pad)
    bottom = min(sheet_height, y + height + pad)
    return (left, top, max(1.0, right - left), max(1.0, bottom - top))


def _scale_bbox(
    bbox: tuple[float, float, float, float],
    source_sheet: SheetVersion,
    target_sheet: SheetVersion,
) -> tuple[float, float, float, float]:
    source_width = float(source_sheet.width or 1)
    source_height = float(source_sheet.height or 1)
    target_width = float(target_sheet.width or source_width)
    target_height = float(target_sheet.height or source_height)
    scale_x = target_width / source_width if source_width else 1.0
    scale_y = target_height / source_height if source_height else 1.0
    x, y, width, height = bbox
    return (x * scale_x, y * scale_y, width * scale_x, height * scale_y)


def _render_sheet_crop(
    store: WorkspaceStore,
    sheet: SheetVersion,
    bbox: tuple[float, float, float, float],
    *,
    highlight_bboxes: list[tuple[float, float, float, float]],
) -> Image.Image | None:
    pdf_path = store.resolve_path(sheet.source_pdf)
    if pdf_path.exists():
        rendered = _render_pdf_crop(pdf_path, sheet, bbox, highlight_bboxes=highlight_bboxes)
        if rendered is not None:
            return rendered
    return _render_image_crop(store, sheet, bbox, highlight_bboxes=highlight_bboxes)


def _render_pdf_crop(
    pdf_path: Path,
    sheet: SheetVersion,
    bbox: tuple[float, float, float, float],
    *,
    highlight_bboxes: list[tuple[float, float, float, float]],
) -> Image.Image | None:
    try:
        document = fitz.open(pdf_path)
    except Exception:
        return None
    try:
        if sheet.page_number < 1 or sheet.page_number > document.page_count:
            return None
        page = document[sheet.page_number - 1]
        sheet_width = float(sheet.width or page.rect.width or 1)
        sheet_height = float(sheet.height or page.rect.height or 1)
        scale_x = page.rect.width / sheet_width if sheet_width else 1.0
        scale_y = page.rect.height / sheet_height if sheet_height else 1.0
        x, y, width, height = bbox
        clip = fitz.Rect(
            max(0.0, x * scale_x),
            max(0.0, y * scale_y),
            min(page.rect.width, (x + width) * scale_x),
            min(page.rect.height, (y + height) * scale_y),
        )
        if clip.is_empty or clip.width <= 0 or clip.height <= 0:
            return None
        pix = page.get_pixmap(matrix=fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM), clip=clip, alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        for highlight_bbox in highlight_bboxes:
            rect = _highlight_rect(bbox, highlight_bbox, image.size)
            _draw_highlight(image, rect)
        return image
    finally:
        document.close()


def _render_image_crop(
    store: WorkspaceStore,
    sheet: SheetVersion,
    bbox: tuple[float, float, float, float],
    *,
    highlight_bboxes: list[tuple[float, float, float, float]],
) -> Image.Image | None:
    source_path = store.resolve_path(sheet.render_path)
    if not source_path.exists():
        return None
    try:
        with Image.open(source_path) as page:
            page = page.convert("RGB")
            sheet_width = float(sheet.width or page.width or 1)
            sheet_height = float(sheet.height or page.height or 1)
            scale_x = page.width / sheet_width if sheet_width else 1.0
            scale_y = page.height / sheet_height if sheet_height else 1.0
            x, y, width, height = bbox
            crop_box = (
                max(0, math.floor(x * scale_x)),
                max(0, math.floor(y * scale_y)),
                min(page.width, math.ceil((x + width) * scale_x)),
                min(page.height, math.ceil((y + height) * scale_y)),
            )
            if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
                return None
            image = page.crop(crop_box)
    except Exception:
        return None
    for highlight_bbox in highlight_bboxes:
        rect = _highlight_rect(bbox, highlight_bbox, image.size)
        _draw_highlight(image, rect)
    return image


def _highlight_rect(
    context_bbox: tuple[float, float, float, float],
    highlight_bbox: tuple[float, float, float, float],
    image_size: tuple[int, int],
) -> tuple[float, float, float, float]:
    context_x, context_y, context_width, context_height = context_bbox
    x, y, width, height = highlight_bbox
    scale_x = image_size[0] / context_width if context_width else 1.0
    scale_y = image_size[1] / context_height if context_height else 1.0
    return (
        (x - context_x) * scale_x,
        (y - context_y) * scale_y,
        (x + width - context_x) * scale_x,
        (y + height - context_y) * scale_y,
    )


def _draw_highlight(image: Image.Image, rect: tuple[float, float, float, float]) -> None:
    draw = ImageDraw.Draw(image)
    line_width = max(3, round(max(image.width, image.height) / 160))
    for offset in range(line_width):
        draw.rectangle(
            (
                rect[0] - offset,
                rect[1] - offset,
                rect[2] + offset,
                rect[3] + offset,
            ),
            outline=HIGHLIGHT,
        )


def _open_existing_crop(store: WorkspaceStore, path_text: str) -> Image.Image | None:
    if not path_text:
        return None
    path = store.resolve_path(path_text)
    if not path.exists():
        return None
    try:
        with Image.open(path) as image:
            return image.convert("RGB")
    except Exception:
        return None


def _compose(
    previous: Image.Image,
    current: Image.Image,
    *,
    previous_label: str,
    current_label: str,
) -> Image.Image:
    font = _font(22)
    small_font = _font(17)
    width = PANEL_WIDTH * 2 + GAP
    height = PANEL_HEIGHT
    canvas = Image.new("RGB", (width, height), BACKGROUND)
    _paste_panel(canvas, previous, x=0, label=previous_label, font=font, small_font=small_font)
    _paste_panel(canvas, current, x=PANEL_WIDTH + GAP, label=current_label, font=font, small_font=small_font)
    return canvas


def _paste_panel(
    canvas: Image.Image,
    image: Image.Image,
    *,
    x: int,
    label: str,
    font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    draw = ImageDraw.Draw(canvas)
    panel_box = (x, 0, x + PANEL_WIDTH, PANEL_HEIGHT)
    draw.rectangle(panel_box, fill=PANEL_BACKGROUND, outline=BORDER)
    draw.text((x + 14, 10), label, fill=TEXT, font=font)
    image_box = (x + 12, HEADER_HEIGHT, x + PANEL_WIDTH - 12, PANEL_HEIGHT - 12)
    target = (image_box[2] - image_box[0], image_box[3] - image_box[1])
    fitted = ImageOps.contain(image.convert("RGB"), target, Image.Resampling.LANCZOS)
    paste_x = image_box[0] + (target[0] - fitted.width) // 2
    paste_y = image_box[1] + (target[1] - fitted.height) // 2
    canvas.paste(fitted, (paste_x, paste_y))
    draw.rectangle((paste_x, paste_y, paste_x + fitted.width, paste_y + fitted.height), outline=BORDER)
    if image.width == 1 and image.height == 1:
        draw.text((x + 18, HEADER_HEIGHT + 18), "Unavailable", fill=MUTED_TEXT, font=small_font)


def _placeholder_panel_image(message: str) -> Image.Image:
    image = Image.new("RGB", (PANEL_WIDTH, PANEL_HEIGHT - HEADER_HEIGHT - 24), (241, 245, 249))
    draw = ImageDraw.Draw(image)
    draw.text((18, 18), message, fill=MUTED_TEXT, font=_font(20))
    return image


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()
