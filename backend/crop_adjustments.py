from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw, ImageFont

from .pre_review import PRE_REVIEW_1, pre_review_payload, selected_pre_review_page_boxes
from .revision_state.models import ChangeItem, CloudCandidate, SheetVersion
from .workspace import WorkspaceStore


CROP_ADJUSTMENT_KEY = "scopeledger.crop_adjustment.v1"
CROP_ADJUSTMENT_SCHEMA = "scopeledger.crop_adjustment.v1"
ADJUSTED_CROP_TARGET_WIDTH = 1800.0
ADJUSTED_CROP_MAX_SCALE = 4.0
ADJUSTED_CROP_MIN_SCALE = 2.0
ADJUSTED_CROP_PAD_MIN = 24.0
ADJUSTED_CROP_PAD_MAX = 120.0
ADJUSTED_CROP_PAD_FACTOR = 0.16
ADJUSTED_BOX_COLOR = "#0f766e"


class CropAdjustmentError(ValueError):
    pass


@dataclass(frozen=True)
class CropAdjustmentContext:
    enabled: bool
    reason: str
    image_path: Path | None = None
    image_size: tuple[int, int] = (0, 0)
    crop_box: list[float] | None = None
    source_page_box: list[float] | None = None
    using_adjusted_crop: bool = False


@dataclass(frozen=True)
class CropAdjustmentResult:
    item: ChangeItem
    payload: dict[str, Any]
    human_result_overrides: dict[str, Any]
    image_path: Path
    crop_box: list[float]
    page_box: list[float]


def crop_adjustment_payload(item: ChangeItem) -> dict[str, Any]:
    value = item.provenance.get(CROP_ADJUSTMENT_KEY)
    return value if isinstance(value, dict) else {}


def selected_review_page_boxes(item: ChangeItem, cloud: CloudCandidate | None = None) -> list[list[float]]:
    adjustment = crop_adjustment_payload(item)
    adjusted_boxes = _valid_boxes(adjustment.get("page_boxes"))
    if adjusted_boxes:
        return adjusted_boxes
    selected_boxes = selected_pre_review_page_boxes(item)
    if selected_boxes:
        return selected_boxes
    if cloud:
        return [[float(value) for value in cloud.bbox]]
    return []


def crop_adjustment_template_context(
    store: WorkspaceStore,
    item: ChangeItem,
    cloud: CloudCandidate | None,
    sheet: SheetVersion,
) -> dict[str, Any]:
    if not cloud:
        return {"enabled": False, "reason": "No detected region is available."}
    context = build_crop_adjustment_context(store, item, cloud, sheet)
    if not context.enabled or not context.crop_box:
        return {"enabled": False, "reason": context.reason}
    return {
        "enabled": True,
        "reason": context.reason,
        "crop_box": context.crop_box,
        "image_width": context.image_size[0],
        "image_height": context.image_size[1],
        "using_adjusted_crop": context.using_adjusted_crop,
    }


def build_crop_adjustment_context(
    store: WorkspaceStore,
    item: ChangeItem,
    cloud: CloudCandidate,
    sheet: SheetVersion,
) -> CropAdjustmentContext:
    adjustment = crop_adjustment_payload(item)
    adjusted_path = _resolved_existing_asset_path(store, adjustment.get("crop_image_path"))
    adjusted_source_box = _xywh_from_value(adjustment.get("render_clip_page_box"))
    adjusted_crop_box = _first_valid_box(adjustment.get("crop_boxes"))
    if adjusted_path and adjusted_source_box and adjusted_crop_box:
        image_size = _image_size(adjusted_path)
        if image_size:
            return CropAdjustmentContext(
                enabled=True,
                reason="Adjusted crop is active.",
                image_path=adjusted_path,
                image_size=image_size,
                crop_box=_clip_crop_xywh(adjusted_crop_box, image_size),
                source_page_box=adjusted_source_box,
                using_adjusted_crop=True,
            )

    crop_path = _resolved_existing_path(store, cloud.image_path)
    if not crop_path:
        return CropAdjustmentContext(enabled=False, reason="The crop image is not available.")
    image_size = _image_size(crop_path)
    if not image_size:
        return CropAdjustmentContext(enabled=False, reason="The crop image could not be read.")
    source_page_box = _source_crop_page_box(cloud, sheet)
    if not source_page_box:
        return CropAdjustmentContext(enabled=False, reason="This region cannot be adjusted safely.")
    crop_box = _selected_crop_box(item, cloud, image_size)
    if not crop_box:
        return CropAdjustmentContext(enabled=False, reason="This region does not have an adjustable box.")
    return CropAdjustmentContext(
        enabled=True,
        reason="Ready",
        image_path=crop_path,
        image_size=image_size,
        crop_box=crop_box,
        source_page_box=source_page_box,
    )


def apply_crop_adjustment(
    store: WorkspaceStore,
    item: ChangeItem,
    cloud: CloudCandidate,
    sheet: SheetVersion,
    crop_box: list[Any],
    *,
    reviewer_id: str | None,
    review_session_id: str | None,
) -> CropAdjustmentResult:
    context = build_crop_adjustment_context(store, item, cloud, sheet)
    if not context.enabled or not context.source_page_box:
        raise CropAdjustmentError(context.reason or "This crop cannot be adjusted.")
    normalized_crop_box = _normalize_crop_box(crop_box, context.image_size)
    page_box = crop_box_to_page_box(normalized_crop_box, context.source_page_box, context.image_size)
    adjustment_id = str(uuid.uuid4())
    output_path = store.assets_dir / "crop_adjustments" / f"{item.id}_{adjustment_id}.png"
    render_result = render_adjusted_crop(
        store,
        sheet,
        page_box,
        output_path,
    )
    payload = {
        "schema": CROP_ADJUSTMENT_SCHEMA,
        "adjustment_id": adjustment_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reviewer_id": reviewer_id,
        "review_session_id": review_session_id,
        "crop_image_path": store.display_path(render_result["image_path"]),
        "source_image_path": store.display_path(context.image_path) if context.image_path else "",
        "source_image_size": [context.image_size[0], context.image_size[1]],
        "source_crop_box": normalized_crop_box,
        "crop_boxes": [render_result["crop_box"]],
        "page_boxes": [page_box],
        "render_clip_page_box": render_result["render_clip_page_box"],
        "image_width": render_result["image_size"][0],
        "image_height": render_result["image_size"][1],
    }
    updated_item = replace(item, provenance={**item.provenance, CROP_ADJUSTMENT_KEY: payload})
    human_result_overrides = {
        "final_geometry": {"boxes": [page_box]},
        "crop_adjustment": payload,
    }
    return CropAdjustmentResult(
        item=updated_item,
        payload=payload,
        human_result_overrides=human_result_overrides,
        image_path=render_result["image_path"],
        crop_box=render_result["crop_box"],
        page_box=page_box,
    )


def crop_box_to_page_box(crop_box: list[float], source_page_box: list[float], image_size: tuple[int, int]) -> list[float]:
    image_width, image_height = image_size
    source_x, source_y, source_width, source_height = source_page_box
    x, y, width, height = crop_box
    page_x1 = source_x + (x / max(float(image_width), 1.0)) * source_width
    page_y1 = source_y + (y / max(float(image_height), 1.0)) * source_height
    page_x2 = source_x + ((x + width) / max(float(image_width), 1.0)) * source_width
    page_y2 = source_y + ((y + height) / max(float(image_height), 1.0)) * source_height
    return [
        round(page_x1, 3),
        round(page_y1, 3),
        round(max(1.0, page_x2 - page_x1), 3),
        round(max(1.0, page_y2 - page_y1), 3),
    ]


def render_adjusted_crop(
    store: WorkspaceStore,
    sheet: SheetVersion,
    page_box: list[float],
    output_path: Path,
) -> dict[str, Any]:
    source_pdf = store.resolve_path(sheet.source_pdf)
    if not source_pdf.exists():
        raise CropAdjustmentError("The source drawing PDF is not available.")
    x, y, width, height = page_box
    if width <= 0 or height <= 0:
        raise CropAdjustmentError("The adjusted crop is too small.")
    pad = max(ADJUSTED_CROP_PAD_MIN, min(max(width, height) * ADJUSTED_CROP_PAD_FACTOR, ADJUSTED_CROP_PAD_MAX))
    try:
        document = fitz.open(source_pdf)
    except Exception as exc:
        raise CropAdjustmentError("The adjusted crop could not be rendered from the source PDF.") from exc
    try:
        page = document[sheet.page_number - 1]
        page_rect = page.rect
        sheet_width = float(sheet.width or page_rect.width)
        sheet_height = float(sheet.height or page_rect.height)
        clip_sheet_x1 = max(0.0, x - pad)
        clip_sheet_y1 = max(0.0, y - pad)
        clip_sheet_x2 = min(sheet_width, x + width + pad)
        clip_sheet_y2 = min(sheet_height, y + height + pad)
        scale_x = page_rect.width / sheet_width
        scale_y = page_rect.height / sheet_height
        clip = fitz.Rect(
            clip_sheet_x1 * scale_x,
            clip_sheet_y1 * scale_y,
            clip_sheet_x2 * scale_x,
            clip_sheet_y2 * scale_y,
        )
        if clip.width <= 0 or clip.height <= 0:
            raise CropAdjustmentError("The adjusted crop is outside the drawing page.")
        crop_scale = min(ADJUSTED_CROP_MAX_SCALE, max(ADJUSTED_CROP_MIN_SCALE, ADJUSTED_CROP_TARGET_WIDTH / max(clip.width, 1.0)))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pix = page.get_pixmap(matrix=fitz.Matrix(crop_scale, crop_scale), clip=clip, alpha=False)
        pix.save(output_path)
    except CropAdjustmentError:
        raise
    except Exception as exc:
        raise CropAdjustmentError("The adjusted crop could not be rendered from the source PDF.") from exc
    finally:
        document.close()

    try:
        with Image.open(output_path) as image:
            image = image.convert("RGB")
            image_width, image_height = image.size
            render_clip_page_box = [
                round(clip_sheet_x1, 3),
                round(clip_sheet_y1, 3),
                round(max(1.0, clip_sheet_x2 - clip_sheet_x1), 3),
                round(max(1.0, clip_sheet_y2 - clip_sheet_y1), 3),
            ]
            crop_box = _page_box_to_crop_box(page_box, render_clip_page_box, image.size)
            _draw_adjusted_box(image, crop_box)
            image.save(output_path, format="PNG", optimize=True)
    except Exception as exc:
        raise CropAdjustmentError("The adjusted crop image could not be finalized.") from exc

    return {
        "image_path": output_path,
        "image_size": [image_width, image_height],
        "crop_box": crop_box,
        "render_clip_page_box": render_clip_page_box,
    }


def build_selected_review_overlay_image(
    store: WorkspaceStore,
    item: ChangeItem,
    cloud: CloudCandidate,
    output_path: Path,
    *,
    include_all: bool,
) -> Path | None:
    adjustment = crop_adjustment_payload(item)
    adjusted_path = _resolved_existing_asset_path(store, adjustment.get("crop_image_path"))
    if adjusted_path:
        return adjusted_path
    from .pre_review import build_pre_review_overlay_image

    return build_pre_review_overlay_image(store, item, cloud, output_path, include_all=include_all)


def _source_crop_page_box(cloud: CloudCandidate, sheet: SheetVersion) -> list[float] | None:
    metadata = cloud.metadata or {}
    crop_box = _xyxy_from_value(metadata.get("crop_box_page_xyxy")) or _xyxy_from_xywh(metadata.get("crop_box_page_xywh"))
    if not crop_box:
        return None
    source_width = _positive_float(metadata.get("page_width"), sheet.width)
    source_height = _positive_float(metadata.get("page_height"), sheet.height)
    scale_x = float(sheet.width or source_width) / source_width if source_width else 1.0
    scale_y = float(sheet.height or source_height) / source_height if source_height else 1.0
    return [
        round(crop_box[0] * scale_x, 3),
        round(crop_box[1] * scale_y, 3),
        round(max(1.0, crop_box[2] - crop_box[0]) * scale_x, 3),
        round(max(1.0, crop_box[3] - crop_box[1]) * scale_y, 3),
    ]


def _selected_crop_box(item: ChangeItem, cloud: CloudCandidate, image_size: tuple[int, int]) -> list[float] | None:
    payload = pre_review_payload(item)
    selected = str(payload.get("selected") or PRE_REVIEW_1)
    entry = payload.get(selected)
    if isinstance(entry, dict):
        crop_boxes = _valid_boxes(entry.get("crop_boxes"))
        if crop_boxes:
            return _union_crop_boxes(crop_boxes, image_size)
    fallback = _first_valid_box(_fallback_cloud_crop_boxes(cloud, image_size))
    return fallback


def _fallback_cloud_crop_boxes(cloud: CloudCandidate, image_size: tuple[int, int]) -> list[list[float]]:
    metadata = cloud.metadata or {}
    raw_bbox = _xyxy_from_value(metadata.get("bbox_page_xyxy")) or _xyxy_from_xywh(metadata.get("bbox_page_xywh"))
    crop_box = _xyxy_from_value(metadata.get("crop_box_page_xyxy")) or _xyxy_from_xywh(metadata.get("crop_box_page_xywh"))
    if not raw_bbox or not crop_box:
        return []
    return [_raw_page_box_to_crop_box(raw_bbox, crop_box, image_size)]


def _normalize_crop_box(value: list[Any], image_size: tuple[int, int]) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        raise CropAdjustmentError("Choose a valid crop box.")
    try:
        box = [float(part) for part in value]
    except (TypeError, ValueError) as exc:
        raise CropAdjustmentError("Choose a valid crop box.") from exc
    clipped = _clip_crop_xywh(box, image_size)
    min_size = 8.0
    if clipped[2] < min_size or clipped[3] < min_size:
        raise CropAdjustmentError("The adjusted crop is too small.")
    return clipped


def _page_box_to_crop_box(page_box: list[float], source_page_box: list[float], image_size: tuple[int, int]) -> list[float]:
    source_x, source_y, source_width, source_height = source_page_box
    x, y, width, height = page_box
    image_width, image_height = image_size
    crop_x1 = ((x - source_x) / max(source_width, 1.0)) * image_width
    crop_y1 = ((y - source_y) / max(source_height, 1.0)) * image_height
    crop_x2 = ((x + width - source_x) / max(source_width, 1.0)) * image_width
    crop_y2 = ((y + height - source_y) / max(source_height, 1.0)) * image_height
    return _clip_crop_xywh([crop_x1, crop_y1, crop_x2 - crop_x1, crop_y2 - crop_y1], image_size)


def _raw_page_box_to_crop_box(box_xyxy: list[float], crop_xyxy: list[float], crop_size: tuple[int, int]) -> list[float]:
    crop_width = max(1.0, crop_xyxy[2] - crop_xyxy[0])
    crop_height = max(1.0, crop_xyxy[3] - crop_xyxy[1])
    image_width, image_height = crop_size
    x1 = ((box_xyxy[0] - crop_xyxy[0]) / crop_width) * image_width
    y1 = ((box_xyxy[1] - crop_xyxy[1]) / crop_height) * image_height
    x2 = ((box_xyxy[2] - crop_xyxy[0]) / crop_width) * image_width
    y2 = ((box_xyxy[3] - crop_xyxy[1]) / crop_height) * image_height
    return _clip_crop_xywh([x1, y1, x2 - x1, y2 - y1], crop_size)


def _union_crop_boxes(boxes: list[list[float]], image_size: tuple[int, int]) -> list[float]:
    clipped = [_clip_crop_xywh(box, image_size) for box in boxes if box[2] > 0 and box[3] > 0]
    if not clipped:
        return [0.0, 0.0, float(image_size[0]), float(image_size[1])]
    x1 = min(box[0] for box in clipped)
    y1 = min(box[1] for box in clipped)
    x2 = max(box[0] + box[2] for box in clipped)
    y2 = max(box[1] + box[3] for box in clipped)
    return _clip_crop_xywh([x1, y1, x2 - x1, y2 - y1], image_size)


def _clip_crop_xywh(box: list[float], image_size: tuple[int, int]) -> list[float]:
    image_width, image_height = image_size
    x, y, width, height = box
    if width < 0:
        x += width
        width = abs(width)
    if height < 0:
        y += height
        height = abs(height)
    x1 = max(0.0, min(float(image_width), x))
    y1 = max(0.0, min(float(image_height), y))
    x2 = max(0.0, min(float(image_width), x + width))
    y2 = max(0.0, min(float(image_height), y + height))
    return [round(x1, 3), round(y1, 3), round(max(0.0, x2 - x1), 3), round(max(0.0, y2 - y1), 3)]


def _draw_adjusted_box(image: Image.Image, crop_box: list[float]) -> None:
    draw = ImageDraw.Draw(image)
    x, y, width, height = crop_box
    rect = (x, y, x + width, y + height)
    line_width = max(4, round(max(image.size) / 180))
    for offset in range(line_width):
        draw.rectangle(
            (rect[0] - offset, rect[1] - offset, rect[2] + offset, rect[3] + offset),
            outline=ADJUSTED_BOX_COLOR,
        )
    label = "Adjusted"
    font = ImageFont.load_default()
    text_bbox = draw.textbbox((0, 0), label, font=font)
    label_width = text_bbox[2] - text_bbox[0] + 8
    label_height = text_bbox[3] - text_bbox[1] + 6
    label_y = max(0, int(y) - label_height)
    draw.rectangle((int(x), label_y, int(x) + label_width, label_y + label_height), fill=ADJUSTED_BOX_COLOR)
    draw.text((int(x) + 4, label_y + 3), label, fill="white", font=font)


def _resolved_existing_path(store: WorkspaceStore, value: Any) -> Path | None:
    if not value:
        return None
    path = store.resolve_path(str(value))
    return path if path.exists() else None


def _resolved_existing_asset_path(store: WorkspaceStore, value: Any) -> Path | None:
    path = _resolved_existing_path(store, value)
    if not path:
        return None
    try:
        path.resolve().relative_to(store.assets_dir.resolve())
    except ValueError:
        return None
    return path


def _image_size(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


def _valid_boxes(value: Any) -> list[list[float]]:
    if not isinstance(value, list):
        return []
    boxes = []
    for item in value:
        box = _xywh_from_value(item)
        if box:
            boxes.append(box)
    return boxes


def _first_valid_box(value: Any) -> list[float] | None:
    boxes = _valid_boxes(value)
    return boxes[0] if boxes else None


def _xywh_from_value(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, width, height = [float(part) for part in value]
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return [round(x, 3), round(y, 3), round(width, 3), round(height, 3)]


def _xyxy_from_value(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(part) for part in value]
    except (TypeError, ValueError):
        return None
    if x1 == x2 or y1 == y2:
        return None
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def _xyxy_from_xywh(value: Any) -> list[float] | None:
    box = _xywh_from_value(value)
    if not box:
        return None
    x, y, width, height = box
    return [x, y, x + width, y + height]


def _positive_float(*values: Any) -> float:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return 0.0
