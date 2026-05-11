from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageDraw, ImageFont

from .revision_state.models import ChangeItem, CloudCandidate, SheetVersion
from .utils import clean_display_text, json_dumps, normalize_text, stable_id
from .workspace import WorkspaceStore


PRE_REVIEW_KEY = "scopeledger.pre_review.v1"
PRE_REVIEW_SCHEMA = "scopeledger.pre_review.v1"
PROMPT_VERSION = "scopeledger_pre_review_prompt_v1"
PRE_REVIEW_1 = "pre_review_1"
PRE_REVIEW_2 = "pre_review_2"
VALID_PRE_REVIEW_SOURCES = {PRE_REVIEW_1, PRE_REVIEW_2}
GEOMETRY_DECISIONS = {"same_box", "adjusted_box", "partial", "overmerged", "false_positive", "unclear"}
PRE_REVIEW_1_COLOR = "#0f766e"
PRE_REVIEW_2_COLOR = "#d97706"


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["geometry_decision", "boxes", "refined_text", "reason", "confidence", "tags"],
    "properties": {
        "geometry_decision": {"type": "string", "enum": sorted(GEOMETRY_DECISIONS)},
        "boxes": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
            },
        },
        "refined_text": {"type": "string"},
        "reason": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


PROMPT = """You are reviewing one detected drawing revision region before a human reviewer sees it.

You receive one large crop image. The colored rectangle on the image is Pre Review 1, the initial detected region. You also receive OCR text extracted near that region.

Tasks:
- Decide whether Pre Review 1 covers the whole visible revision cloud.
- Decide whether it appears to cover multiple separate clouds.
- Propose Pre Review 2 boxes when the region should be adjusted, split visually, or clarified.
- Refine the OCR text into the concise detail/scope text that should be presented to the reviewer.

Return crop-relative boxes as [x, y, width, height] in the image pixel coordinate system. If Pre Review 1 is already best, return the same box. If multiple boxes are appropriate, return multiple boxes, but they will remain one review item for now.

Policy:
- Do not auto-approve or auto-reject the item.
- Do not infer scope beyond visible evidence and OCR/context.
- Ignore random dimensions, standalone numbers, sheet index tables, title block noise, and broad unrelated text unless they are clearly part of the clouded scope.
- Treat your response as provisional pre-review metadata only; the human reviewer selection is final.

Return JSON only.
"""


@dataclass(frozen=True)
class PreReviewContext:
    item: ChangeItem
    cloud: CloudCandidate
    sheet: SheetVersion
    crop_path: Path
    crop_size: tuple[int, int]
    pre_review_1: dict[str, Any]
    cache_dir: Path


@dataclass(frozen=True)
class PreReviewRunSummary:
    total_count: int = 0
    pre_review_2_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    cache_hits: int = 0
    disabled_reason: str = ""

    def to_status(self) -> dict[str, object]:
        return {
            "pre_review_total_count": self.total_count,
            "pre_review_2_count": self.pre_review_2_count,
            "pre_review_skipped_count": self.skipped_count,
            "pre_review_failed_count": self.failed_count,
            "pre_review_cache_hits": self.cache_hits,
            "pre_review_disabled_reason": self.disabled_reason,
        }


class PreReviewProvider(Protocol):
    name: str
    enabled: bool
    disabled_reason: str

    def review(self, context: PreReviewContext) -> dict[str, Any] | None:
        ...


class DisabledPreReviewProvider:
    name = "disabled"
    enabled = False

    def __init__(self, reason: str = "disabled"):
        self.disabled_reason = reason

    def review(self, context: PreReviewContext) -> dict[str, Any] | None:
        return None


class OpenAIPreReviewProvider:
    name = "pre_review_api"
    enabled = True
    disabled_reason = ""

    def __init__(
        self,
        *,
        model: str = "gpt-5.5",
        max_retries: int = 2,
        retry_initial_delay: float = 1.5,
        image_format: str = "png",
    ):
        self.model = model
        self.max_retries = max_retries
        self.retry_initial_delay = retry_initial_delay
        self.image_format = image_format

    def review(self, context: PreReviewContext) -> dict[str, Any] | None:
        cache_dir = context.cache_dir / "cache"
        api_input_dir = context.cache_dir / "api_inputs"
        cache_dir.mkdir(parents=True, exist_ok=True)
        api_input_dir.mkdir(parents=True, exist_ok=True)
        cache_key = _cache_key(self.model, context)
        cache_path = cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            result = dict(payload.get("result") or {})
            result["cache_hit"] = True
            return result

        input_image = _write_api_overlay(context, api_input_dir / f"{cache_key}.{self.image_format}")
        raw_text = self._call_openai(context, input_image)
        payload = json.loads(raw_text)
        result = normalize_pre_review_2(payload, context)
        result["cache_hit"] = False
        cache_path.write_text(
            json_dumps(
                {
                    "schema": "scopeledger.pre_review_cache.v1",
                    "prompt_version": PROMPT_VERSION,
                    "model": self.model,
                    "item_id": context.item.id,
                    "cloud_id": context.cloud.id,
                    "api_input_path": str(input_image),
                    "result": result,
                }
            ),
            encoding="utf-8",
        )
        return result

    def _call_openai(self, context: PreReviewContext, input_image: Path) -> str:
        try:
            from openai import OpenAI  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("openai is not installed. Install requirements.txt before enabling pre-review.") from exc

        client = OpenAI()
        image_part: dict[str, Any] = {"type": "input_image", "image_url": _image_to_data_url(input_image)}
        prompt_context = json.dumps(
            {
                "prompt_version": PROMPT_VERSION,
                "sheet_id": context.sheet.sheet_id,
                "sheet_title": context.sheet.sheet_title,
                "page_number": context.sheet.page_number,
                "pre_review_1_crop_boxes": context.pre_review_1.get("crop_boxes", []),
                "pre_review_1_ocr_text": context.pre_review_1.get("text", ""),
                "pre_review_1_reason": context.pre_review_1.get("reason", ""),
                "confidence": context.cloud.confidence,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        content = [
            {"type": "input_text", "text": PROMPT + "\n\nCandidate context JSON:\n" + prompt_context},
            image_part,
        ]
        attempt = 0
        while True:
            try:
                response = client.responses.create(
                    model=self.model,
                    input=[{"role": "user", "content": content}],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "scopeledger_pre_review",
                            "schema": RESPONSE_SCHEMA,
                            "strict": True,
                        }
                    },
                )
                return _extract_response_text(response)
            except Exception as exc:
                if attempt >= self.max_retries or not _is_retryable_openai_error(exc):
                    raise
                attempt += 1
                retry_after = _retry_after_seconds(exc)
                delay = retry_after if retry_after is not None else self.retry_initial_delay * (2 ** (attempt - 1))
                time.sleep(min(max(0.0, delay), 30.0))


def build_pre_review_provider_from_env() -> PreReviewProvider:
    if not _truthy(os.getenv("SCOPELEDGER_PREREVIEW_ENABLED", "")):
        return DisabledPreReviewProvider("disabled")
    if not os.getenv("OPENAI_API_KEY"):
        return DisabledPreReviewProvider("missing_api_key")
    return OpenAIPreReviewProvider(model=os.getenv("SCOPELEDGER_PREREVIEW_MODEL", "gpt-5.5"))


def ensure_workspace_pre_review(
    store: WorkspaceStore,
    provider: PreReviewProvider | None = None,
    *,
    force: bool = False,
) -> PreReviewRunSummary:
    provider = provider or DisabledPreReviewProvider()
    sheets_by_id = {sheet.id: sheet for sheet in store.data.sheets}
    clouds_by_id = {cloud.id: cloud for cloud in store.data.clouds}
    updated_items: list[ChangeItem] = []
    total = 0
    pre_review_2_count = 0
    skipped = 0
    failed = 0
    cache_hits = 0
    changed = False

    for item in store.data.change_items:
        cloud = clouds_by_id.get(item.cloud_candidate_id or "")
        sheet = sheets_by_id.get(item.sheet_version_id)
        if not cloud or not sheet or item.provenance.get("source") != "visual-region":
            updated_items.append(item)
            continue

        total += 1
        context = build_pre_review_context(store, item, cloud, sheet)
        existing = pre_review_payload(item)
        selected = str(existing.get("selected") or PRE_REVIEW_1)
        if selected not in VALID_PRE_REVIEW_SOURCES:
            selected = PRE_REVIEW_1

        pre_review_2 = existing.get(PRE_REVIEW_2) if isinstance(existing.get(PRE_REVIEW_2), dict) else None
        status = str(existing.get("status") or "pending")
        error = ""
        if provider.enabled and context is not None and (force or not pre_review_2):
            try:
                pre_review_2 = provider.review(context)
                if pre_review_2:
                    status = "complete"
                    pre_review_2_count += 1
                    if pre_review_2.get("cache_hit"):
                        cache_hits += 1
            except Exception as exc:
                failed += 1
                status = "failed"
                error = _compact_error(exc)
        elif pre_review_2:
            pre_review_2_count += 1
        else:
            skipped += 1
            if not provider.enabled:
                status = "skipped"
            elif context is None:
                status = "missing_crop"

        pre_review_1 = context.pre_review_1 if context is not None else _fallback_pre_review_1(item, cloud)
        if selected == PRE_REVIEW_2 and not pre_review_2:
            selected = PRE_REVIEW_1
        payload: dict[str, Any] = {
            "schema": PRE_REVIEW_SCHEMA,
            "selected": selected,
            "status": status,
            "provider": provider.name,
            PRE_REVIEW_1: pre_review_1,
            PRE_REVIEW_2: pre_review_2 or _empty_pre_review_2(),
        }
        if error:
            payload["error"] = error

        provenance = {**item.provenance, PRE_REVIEW_KEY: payload}
        reviewer_text = item.reviewer_text
        if not reviewer_text:
            reviewer_text = selected_pre_review_text(payload) or item.raw_text
        updated = ChangeItem(
            id=item.id,
            sheet_version_id=item.sheet_version_id,
            cloud_candidate_id=item.cloud_candidate_id,
            sheet_id=item.sheet_id,
            detail_ref=item.detail_ref,
            raw_text=item.raw_text,
            normalized_text=item.normalized_text,
            provenance=provenance,
            status=item.status,
            reviewer_text=reviewer_text,
            reviewer_notes=item.reviewer_notes,
        )
        if updated != item:
            changed = True
        updated_items.append(updated)

    if changed:
        store.data.change_items = updated_items
        store.save()
    return PreReviewRunSummary(
        total_count=total,
        pre_review_2_count=pre_review_2_count,
        skipped_count=skipped,
        failed_count=failed,
        cache_hits=cache_hits,
        disabled_reason="" if provider.enabled else provider.disabled_reason,
    )


def build_pre_review_context(
    store: WorkspaceStore,
    item: ChangeItem,
    cloud: CloudCandidate,
    sheet: SheetVersion,
) -> PreReviewContext | None:
    crop_path = store.resolve_path(cloud.image_path)
    if not crop_path.exists():
        return None
    try:
        with Image.open(crop_path) as image:
            crop_size = image.size
    except Exception:
        return None
    pre_review_1 = _build_pre_review_1(item, cloud, sheet, crop_size)
    return PreReviewContext(
        item=item,
        cloud=cloud,
        sheet=sheet,
        crop_path=crop_path,
        crop_size=crop_size,
        pre_review_1=pre_review_1,
        cache_dir=store.output_dir / "pre_review",
    )


def pre_review_payload(item: ChangeItem) -> dict[str, Any]:
    value = item.provenance.get(PRE_REVIEW_KEY)
    return value if isinstance(value, dict) else {}


def selected_pre_review_text(payload: dict[str, Any]) -> str:
    selected = str(payload.get("selected") or PRE_REVIEW_1)
    entry = payload.get(selected)
    if isinstance(entry, dict):
        return str(entry.get("text") or "")
    return ""


def selected_pre_review_page_boxes(item: ChangeItem) -> list[list[float]]:
    payload = pre_review_payload(item)
    selected = str(payload.get("selected") or PRE_REVIEW_1)
    entry = payload.get(selected)
    if not isinstance(entry, dict):
        return []
    return _valid_boxes(entry.get("boxes"))


def select_pre_review_source(item: ChangeItem, source: str) -> ChangeItem:
    if source not in VALID_PRE_REVIEW_SOURCES:
        return item
    payload = pre_review_payload(item)
    if not payload:
        return item
    entry = payload.get(source)
    if not isinstance(entry, dict):
        return item
    if source == PRE_REVIEW_2 and not entry.get("available"):
        return item
    updated_payload = {**payload, "selected": source}
    text = str(entry.get("text") or item.raw_text)
    return ChangeItem(
        id=item.id,
        sheet_version_id=item.sheet_version_id,
        cloud_candidate_id=item.cloud_candidate_id,
        sheet_id=item.sheet_id,
        detail_ref=item.detail_ref,
        raw_text=item.raw_text,
        normalized_text=item.normalized_text,
        provenance={**item.provenance, PRE_REVIEW_KEY: updated_payload},
        status=item.status,
        reviewer_text=text,
        reviewer_notes=item.reviewer_notes,
    )


def build_pre_review_overlay_image(
    store: WorkspaceStore,
    item: ChangeItem,
    cloud: CloudCandidate,
    output_path: Path,
    *,
    include_all: bool,
) -> Path | None:
    crop_path = store.resolve_path(cloud.image_path)
    if not crop_path.exists():
        return None
    with Image.open(crop_path) as source:
        image = source.convert("RGB")
    payload = pre_review_payload(item)
    if not payload:
        payload = {
            "selected": PRE_REVIEW_1,
            PRE_REVIEW_1: _fallback_pre_review_1(item, cloud),
            PRE_REVIEW_2: _empty_pre_review_2(),
        }
    draw = ImageDraw.Draw(image)
    if include_all:
        _draw_entry_boxes(draw, image.size, payload.get(PRE_REVIEW_1), PRE_REVIEW_1_COLOR, "Pre Review 1")
        _draw_entry_boxes(draw, image.size, payload.get(PRE_REVIEW_2), PRE_REVIEW_2_COLOR, "Pre Review 2")
    else:
        selected = str(payload.get("selected") or PRE_REVIEW_1)
        color = PRE_REVIEW_2_COLOR if selected == PRE_REVIEW_2 else PRE_REVIEW_1_COLOR
        _draw_entry_boxes(draw, image.size, payload.get(selected), color, "Selected")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=True)
    return output_path


def normalize_pre_review_2(payload: dict[str, Any], context: PreReviewContext) -> dict[str, Any]:
    decision = str(payload.get("geometry_decision") or "unclear")
    if decision not in GEOMETRY_DECISIONS:
        decision = "unclear"
    crop_boxes = _normalize_crop_boxes(payload.get("boxes"), context.crop_size)
    if not crop_boxes:
        crop_boxes = _valid_boxes(context.pre_review_1.get("crop_boxes"))
    if not crop_boxes:
        crop_boxes = [[0.0, 0.0, float(context.crop_size[0]), float(context.crop_size[1])]]
    page_boxes = [_crop_box_to_sheet_box(box, context.cloud, context.sheet, context.crop_size) for box in crop_boxes]
    try:
        confidence = max(0.0, min(1.0, float(payload.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0
    tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
    return {
        "available": True,
        "source": PRE_REVIEW_2,
        "label": "Pre Review 2",
        "geometry_decision": decision,
        "boxes": page_boxes,
        "crop_boxes": crop_boxes,
        "text": clean_display_text(str(payload.get("refined_text") or context.pre_review_1.get("text") or "")),
        "reason": clean_display_text(str(payload.get("reason") or decision)),
        "confidence": round(confidence, 3),
        "tags": [clean_display_text(str(tag)) for tag in tags if clean_display_text(str(tag))],
    }


def _build_pre_review_1(
    item: ChangeItem,
    cloud: CloudCandidate,
    sheet: SheetVersion,
    crop_size: tuple[int, int],
) -> dict[str, Any]:
    crop_boxes = _pre_review_1_crop_boxes(cloud, sheet, crop_size)
    return {
        "available": True,
        "source": PRE_REVIEW_1,
        "label": "Pre Review 1",
        "geometry_decision": "same_box",
        "boxes": [[float(value) for value in cloud.bbox]],
        "crop_boxes": crop_boxes,
        "text": clean_display_text(item.raw_text or cloud.scope_text or cloud.nearby_text),
        "reason": clean_display_text(cloud.scope_reason or "initial detected region"),
        "confidence": round(float(cloud.confidence or 0.0), 3),
        "tags": [],
    }


def _fallback_pre_review_1(item: ChangeItem, cloud: CloudCandidate) -> dict[str, Any]:
    return {
        "available": True,
        "source": PRE_REVIEW_1,
        "label": "Pre Review 1",
        "geometry_decision": "same_box",
        "boxes": [[float(value) for value in cloud.bbox]],
        "crop_boxes": [],
        "text": clean_display_text(item.raw_text or cloud.scope_text or cloud.nearby_text),
        "reason": clean_display_text(cloud.scope_reason or "initial detected region"),
        "confidence": round(float(cloud.confidence or 0.0), 3),
        "tags": [],
    }


def _empty_pre_review_2() -> dict[str, Any]:
    return {
        "available": False,
        "source": PRE_REVIEW_2,
        "label": "Pre Review 2",
        "geometry_decision": "unclear",
        "boxes": [],
        "crop_boxes": [],
        "text": "",
        "reason": "",
        "confidence": 0.0,
        "tags": [],
    }


def _pre_review_1_crop_boxes(cloud: CloudCandidate, sheet: SheetVersion, crop_size: tuple[int, int]) -> list[list[float]]:
    metadata = cloud.metadata or {}
    raw_bbox = _xyxy_from_metadata(metadata.get("bbox_page_xyxy")) or _xyxy_from_xywh(metadata.get("bbox_page_xywh"))
    crop_box = _xyxy_from_metadata(metadata.get("crop_box_page_xyxy")) or _xyxy_from_xywh(metadata.get("crop_box_page_xywh"))
    if raw_bbox and crop_box:
        return [_raw_page_box_to_crop_box(raw_bbox, crop_box, crop_size)]
    sheet_box = _xyxy_from_xywh(cloud.bbox)
    crop_sheet_box = _crop_sheet_box_from_metadata(metadata, sheet) or sheet_box
    return [_raw_page_box_to_crop_box(sheet_box, crop_sheet_box, crop_size)]


def _crop_sheet_box_from_metadata(metadata: dict[str, Any], sheet: SheetVersion) -> list[float] | None:
    crop_box = _xyxy_from_metadata(metadata.get("crop_box_page_xyxy")) or _xyxy_from_xywh(metadata.get("crop_box_page_xywh"))
    if not crop_box:
        return None
    source_width = _positive_float(metadata.get("page_width"), sheet.width)
    source_height = _positive_float(metadata.get("page_height"), sheet.height)
    scale_x = float(sheet.width or source_width) / source_width if source_width else 1.0
    scale_y = float(sheet.height or source_height) / source_height if source_height else 1.0
    return [crop_box[0] * scale_x, crop_box[1] * scale_y, crop_box[2] * scale_x, crop_box[3] * scale_y]


def _crop_box_to_sheet_box(
    crop_box: list[float],
    cloud: CloudCandidate,
    sheet: SheetVersion,
    crop_size: tuple[int, int],
) -> list[float]:
    metadata = cloud.metadata or {}
    raw_crop = _xyxy_from_metadata(metadata.get("crop_box_page_xyxy")) or _xyxy_from_xywh(metadata.get("crop_box_page_xywh"))
    if not raw_crop:
        return [float(value) for value in cloud.bbox]
    crop_width, crop_height = crop_size
    x, y, width, height = crop_box
    raw_width = raw_crop[2] - raw_crop[0]
    raw_height = raw_crop[3] - raw_crop[1]
    raw_x1 = raw_crop[0] + (x / max(crop_width, 1)) * raw_width
    raw_y1 = raw_crop[1] + (y / max(crop_height, 1)) * raw_height
    raw_x2 = raw_crop[0] + ((x + width) / max(crop_width, 1)) * raw_width
    raw_y2 = raw_crop[1] + ((y + height) / max(crop_height, 1)) * raw_height
    source_width = _positive_float(metadata.get("page_width"), sheet.width)
    source_height = _positive_float(metadata.get("page_height"), sheet.height)
    scale_x = float(sheet.width or source_width) / source_width if source_width else 1.0
    scale_y = float(sheet.height or source_height) / source_height if source_height else 1.0
    return [
        round(raw_x1 * scale_x, 3),
        round(raw_y1 * scale_y, 3),
        round(max(1.0, raw_x2 - raw_x1) * scale_x, 3),
        round(max(1.0, raw_y2 - raw_y1) * scale_y, 3),
    ]


def _raw_page_box_to_crop_box(box_xyxy: list[float], crop_xyxy: list[float], crop_size: tuple[int, int]) -> list[float]:
    crop_width = max(1.0, crop_xyxy[2] - crop_xyxy[0])
    crop_height = max(1.0, crop_xyxy[3] - crop_xyxy[1])
    image_width, image_height = crop_size
    x1 = ((box_xyxy[0] - crop_xyxy[0]) / crop_width) * image_width
    y1 = ((box_xyxy[1] - crop_xyxy[1]) / crop_height) * image_height
    x2 = ((box_xyxy[2] - crop_xyxy[0]) / crop_width) * image_width
    y2 = ((box_xyxy[3] - crop_xyxy[1]) / crop_height) * image_height
    return _clip_crop_xywh([x1, y1, x2 - x1, y2 - y1], crop_size)


def _normalize_crop_boxes(boxes: Any, crop_size: tuple[int, int]) -> list[list[float]]:
    if not isinstance(boxes, list):
        return []
    normalized = []
    for value in boxes:
        if not isinstance(value, list) or len(value) != 4:
            continue
        try:
            box = [float(part) for part in value]
        except (TypeError, ValueError):
            continue
        clipped = _clip_crop_xywh(box, crop_size)
        if clipped[2] > 0 and clipped[3] > 0:
            normalized.append(clipped)
    return normalized[:8]


def _clip_crop_xywh(box: list[float], crop_size: tuple[int, int]) -> list[float]:
    image_width, image_height = crop_size
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


def _valid_boxes(value: Any) -> list[list[float]]:
    if not isinstance(value, list):
        return []
    boxes = []
    for item in value:
        if not isinstance(item, list) or len(item) != 4:
            continue
        try:
            box = [float(part) for part in item]
        except (TypeError, ValueError):
            continue
        if box[2] > 0 and box[3] > 0:
            boxes.append(box)
    return boxes


def _draw_entry_boxes(draw: ImageDraw.ImageDraw, image_size: tuple[int, int], entry: Any, color: str, label: str) -> None:
    if not isinstance(entry, dict) or not entry.get("available"):
        return
    boxes = _valid_boxes(entry.get("crop_boxes"))
    if not boxes:
        return
    line_width = max(4, round(max(image_size) / 180))
    font = ImageFont.load_default()
    for index, box in enumerate(boxes, start=1):
        x, y, width, height = box
        rect = (x, y, x + width, y + height)
        for offset in range(line_width):
            draw.rectangle(
                (rect[0] - offset, rect[1] - offset, rect[2] + offset, rect[3] + offset),
                outline=color,
            )
        text = label if len(boxes) == 1 else f"{label}.{index}"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        label_width = text_bbox[2] - text_bbox[0] + 8
        label_height = text_bbox[3] - text_bbox[1] + 6
        label_y = max(0, int(y) - label_height)
        draw.rectangle((int(x), label_y, int(x) + label_width, label_y + label_height), fill=color)
        draw.text((int(x) + 4, label_y + 3), text, fill="white", font=font)


def _write_api_overlay(context: PreReviewContext, output_path: Path) -> Path:
    with Image.open(context.crop_path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    _draw_entry_boxes(draw, image.size, context.pre_review_1, PRE_REVIEW_1_COLOR, "Pre Review 1")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=True)
    return output_path


def _xyxy_from_metadata(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(part) for part in value]
    except (TypeError, ValueError):
        return None
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def _xyxy_from_xywh(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, width, height = [float(part) for part in value]
    except (TypeError, ValueError):
        return None
    if width < 0:
        x += width
        width = abs(width)
    if height < 0:
        y += height
        height = abs(height)
    return [x, y, x + width, y + height]


def _positive_float(value: Any, fallback: Any) -> float:
    try:
        number = float(value or fallback or 1)
    except (TypeError, ValueError):
        number = float(fallback or 1)
    return number if number > 0 else 1.0


def _cache_key(model: str, context: PreReviewContext) -> str:
    crop_hash = hashlib.sha256(context.crop_path.read_bytes()).hexdigest()
    return stable_id(
        PROMPT_VERSION,
        model,
        context.item.id,
        context.cloud.id,
        crop_hash,
        context.pre_review_1.get("crop_boxes", []),
        normalize_text(str(context.pre_review_1.get("text") or "")),
    )


def _image_to_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return str(text)
    output = getattr(response, "output", None)
    if output:
        chunks: list[str] = []
        for item in output:
            for content in getattr(item, "content", []) or []:
                value = getattr(content, "text", None)
                if value:
                    chunks.append(str(value))
        if chunks:
            return "".join(chunks)
    return str(response)


def _error_status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        value = headers.get("retry-after") or headers.get("Retry-After")
    except AttributeError:
        return None
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _is_retryable_openai_error(exc: Exception) -> bool:
    status_code = _error_status_code(exc)
    if status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True
    text = str(exc).lower()
    return "rate limit" in text or "temporarily unavailable" in text or "timeout" in text


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _compact_error(exc: Exception, limit: int = 600) -> str:
    text = " ".join(str(exc).split()) or exc.__class__.__name__
    if len(text) <= limit:
        return text
    return f"{text[:limit - 3].rstrip()}..."
