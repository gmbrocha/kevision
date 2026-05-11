from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from .crop_adjustments import CropAdjustmentError, build_crop_adjustment_context, crop_box_to_page_box, render_adjusted_crop
from .pre_review import PRE_REVIEW_1, PRE_REVIEW_2, PRE_REVIEW_KEY
from .review_events import build_review_event
from .review_queue import ensure_queue_order, is_superseded, replacement_queue_order
from .revision_state.models import ChangeItem, CloudCandidate, ReviewEvent, SheetVersion
from .utils import clean_display_text, normalize_text
from .workspace import WorkspaceStore


GEOMETRY_CORRECTION_KEY = "scopeledger.geometry_correction.v1"
GEOMETRY_CORRECTION_SCHEMA = "scopeledger.geometry_correction.v1"
MIN_CORRECTION_BOX_SIZE = 8.0


class GeometryCorrectionError(ValueError):
    pass


@dataclass(frozen=True)
class GeometryCorrectionResult:
    parent_item: ChangeItem
    child_items: list[ChangeItem]
    child_clouds: list[CloudCandidate]
    event: ReviewEvent


def apply_geometry_correction(
    store: WorkspaceStore,
    parent_item: ChangeItem,
    parent_cloud: CloudCandidate,
    sheet: SheetVersion,
    *,
    mode: str,
    crop_boxes: list[Any],
    project_id: str,
    reviewer_id: str | None,
    review_session_id: str | None,
) -> GeometryCorrectionResult:
    if mode not in {"overmerge", "partial"}:
        raise GeometryCorrectionError("Choose a valid correction type.")
    if is_superseded(parent_item):
        raise GeometryCorrectionError("This review item has already been corrected.")

    store.data.change_items, _ = ensure_queue_order(store.data.change_items)
    parent_item = store.get_change_item(parent_item.id)
    context = build_crop_adjustment_context(store, parent_item, parent_cloud, sheet)
    if not context.enabled or not context.source_page_box:
        raise GeometryCorrectionError(context.reason or "This crop cannot be corrected.")

    normalized_crop_boxes = _normalize_crop_boxes(crop_boxes, context.image_size)
    if mode == "overmerge" and len(normalized_crop_boxes) < 2:
        raise GeometryCorrectionError("Draw at least two boxes before saving a split.")
    if mode == "partial" and len(normalized_crop_boxes) != 1:
        raise GeometryCorrectionError("Draw one corrected box before saving.")

    created_at = _utc_now()
    correction_id = str(uuid.uuid4())
    page_boxes = [crop_box_to_page_box(box, context.source_page_box, context.image_size) for box in normalized_crop_boxes]
    child_clouds: list[CloudCandidate] = []
    child_items: list[ChangeItem] = []
    starter_text = clean_display_text(parent_item.reviewer_text or parent_item.raw_text or parent_cloud.scope_text or parent_cloud.nearby_text)

    for index, (crop_box, page_box) in enumerate(zip(normalized_crop_boxes, page_boxes), start=1):
        child_cloud_id = f"{parent_cloud.id}__{mode}_{correction_id[:8]}_{index}"
        child_item_id = f"{parent_item.id}__{mode}_{correction_id[:8]}_{index}"
        output_path = store.assets_dir / "geometry_corrections" / f"{child_item_id}.png"
        try:
            render_result = render_adjusted_crop(store, sheet, page_box, output_path)
        except CropAdjustmentError as exc:
            raise GeometryCorrectionError(str(exc)) from exc

        payload = _correction_payload(
            correction_id=correction_id,
            mode=mode,
            index=index,
            created_at=created_at,
            reviewer_id=reviewer_id,
            review_session_id=review_session_id,
            parent_item=parent_item,
            parent_cloud=parent_cloud,
            source_image_path=store.display_path(context.image_path) if context.image_path else "",
            source_image_size=context.image_size,
            source_crop_box=crop_box,
            page_box=page_box,
            render_result=render_result,
        )
        cloud = _replacement_cloud(
            parent_cloud=parent_cloud,
            child_cloud_id=child_cloud_id,
            page_box=page_box,
            image_path=str(render_result["image_path"].resolve()),
            sheet=sheet,
            payload=payload,
            starter_text=starter_text,
        )
        child = _replacement_item(
            parent_item=parent_item,
            child_item_id=child_item_id,
            child_cloud=cloud,
            index=index,
            mode=mode,
            payload=payload,
            starter_text=starter_text,
        )
        child_clouds.append(cloud)
        child_items.append(child)

    reason = "overmerge_split" if mode == "overmerge" else "partial_correction"
    superseded_parent = replace(
        parent_item,
        superseded_by_change_item_ids=[item.id for item in child_items],
        superseded_reason=reason,
        superseded_at=created_at,
    )
    action = "split" if mode == "overmerge" else "resize"
    event = build_review_event(
        store,
        project_id=project_id,
        before_item=parent_item,
        after_item=superseded_parent,
        action=action,
        reviewer_id=reviewer_id,
        review_session_id=review_session_id,
        human_result_overrides={
            "final_geometry": {"boxes": page_boxes},
            "replacement_change_item_ids": [item.id for item in child_items],
            "replacement_cloud_candidate_ids": [cloud.id for cloud in child_clouds],
            "split_child_geometries": [
                {
                    "change_item_id": item.id,
                    "cloud_candidate_id": cloud.id,
                    "page_box": box,
                    "crop_box": crop_box,
                }
                for item, cloud, box, crop_box in zip(child_items, child_clouds, page_boxes, normalized_crop_boxes)
            ],
            "correction_mode": mode,
            "superseded_reason": reason,
        },
    )

    _replace_parent_and_insert_children(store, superseded_parent, child_items)
    store.data.clouds.extend(child_clouds)
    store.data.review_events.append(event)
    store.save()
    return GeometryCorrectionResult(parent_item=superseded_parent, child_items=child_items, child_clouds=child_clouds, event=event)


def _replace_parent_and_insert_children(store: WorkspaceStore, parent: ChangeItem, children: list[ChangeItem]) -> None:
    updated: list[ChangeItem] = []
    inserted = False
    for item in store.data.change_items:
        if item.id == parent.id:
            updated.append(parent)
            updated.extend(children)
            inserted = True
        elif item.id not in {child.id for child in children}:
            updated.append(item)
    if not inserted:
        updated.append(parent)
        updated.extend(children)
    store.data.change_items = updated


def _replacement_cloud(
    *,
    parent_cloud: CloudCandidate,
    child_cloud_id: str,
    page_box: list[float],
    image_path: str,
    sheet: SheetVersion,
    payload: dict[str, Any],
    starter_text: str,
) -> CloudCandidate:
    x, y, width, height = page_box
    render_clip = payload.get("render_clip_page_box") or []
    metadata = {
        **(parent_cloud.metadata or {}),
        GEOMETRY_CORRECTION_KEY: payload,
        "reviewer_corrected": True,
        "parent_cloud_candidate_id": parent_cloud.id,
        "bbox_page_xywh": page_box,
        "bbox_page_xyxy": [x, y, round(x + width, 3), round(y + height, 3)],
        "crop_box_page_xywh": render_clip,
        "crop_box_page_xyxy": _xyxy_from_xywh(render_clip),
        "page_width": sheet.width,
        "page_height": sheet.height,
    }
    return CloudCandidate(
        id=child_cloud_id,
        sheet_version_id=parent_cloud.sheet_version_id,
        bbox=[int(round(x)), int(round(y)), int(round(width)), int(round(height))],
        image_path=image_path,
        page_image_path=parent_cloud.page_image_path or sheet.render_path,
        confidence=parent_cloud.confidence,
        extraction_method=parent_cloud.extraction_method,
        nearby_text=starter_text,
        detail_ref=parent_cloud.detail_ref,
        scope_text=starter_text,
        scope_reason=parent_cloud.scope_reason or "reviewer-corrected-region",
        scope_signal=parent_cloud.scope_signal,
        scope_method=parent_cloud.scope_method,
        metadata=metadata,
    )


def _replacement_item(
    *,
    parent_item: ChangeItem,
    child_item_id: str,
    child_cloud: CloudCandidate,
    index: int,
    mode: str,
    payload: dict[str, Any],
    starter_text: str,
) -> ChangeItem:
    pre_review_payload = {
        "schema": "scopeledger.pre_review.v1",
        "selected": PRE_REVIEW_1,
        "status": "reviewer_corrected",
        "provider": "reviewer",
        PRE_REVIEW_1: {
            "available": True,
            "source": PRE_REVIEW_1,
            "label": "Pre Review 1",
            "geometry_decision": "same_box",
            "boxes": [[float(value) for value in child_cloud.bbox]],
            "crop_boxes": payload.get("crop_boxes", []),
            "text": starter_text,
            "reason": "reviewer corrected region",
            "confidence": round(float(child_cloud.confidence or 0.0), 3),
            "tags": ["reviewer-corrected"],
        },
        PRE_REVIEW_2: {
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
        },
    }
    return ChangeItem(
        id=child_item_id,
        sheet_version_id=parent_item.sheet_version_id,
        cloud_candidate_id=child_cloud.id,
        sheet_id=parent_item.sheet_id,
        detail_ref=parent_item.detail_ref if mode == "partial" else _split_detail_ref(parent_item.detail_ref, index),
        raw_text=starter_text,
        normalized_text=normalize_text(starter_text),
        provenance={
            **parent_item.provenance,
            "source": "visual-region",
            "parent_change_item_id": parent_item.id,
            "parent_cloud_candidate_id": parent_item.cloud_candidate_id,
            "correction_mode": mode,
            "correction_index": index,
            GEOMETRY_CORRECTION_KEY: payload,
            PRE_REVIEW_KEY: pre_review_payload,
        },
        status="pending",
        reviewer_text=starter_text,
        reviewer_notes=parent_item.reviewer_notes,
        queue_order=replacement_queue_order(parent_item, index - 1),
        parent_change_item_id=parent_item.id,
    )


def _correction_payload(
    *,
    correction_id: str,
    mode: str,
    index: int,
    created_at: str,
    reviewer_id: str | None,
    review_session_id: str | None,
    parent_item: ChangeItem,
    parent_cloud: CloudCandidate,
    source_image_path: str,
    source_image_size: tuple[int, int],
    source_crop_box: list[float],
    page_box: list[float],
    render_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": GEOMETRY_CORRECTION_SCHEMA,
        "correction_id": correction_id,
        "mode": mode,
        "index": index,
        "created_at": created_at,
        "reviewer_id": reviewer_id,
        "review_session_id": review_session_id,
        "parent_change_item_id": parent_item.id,
        "parent_cloud_candidate_id": parent_cloud.id,
        "source_image_path": source_image_path,
        "source_image_size": [source_image_size[0], source_image_size[1]],
        "source_crop_box": source_crop_box,
        "crop_boxes": [render_result["crop_box"]],
        "page_boxes": [page_box],
        "crop_image_path": str(render_result["image_path"].resolve()),
        "render_clip_page_box": render_result["render_clip_page_box"],
        "image_width": render_result["image_size"][0],
        "image_height": render_result["image_size"][1],
    }


def _normalize_crop_boxes(values: list[Any], image_size: tuple[int, int]) -> list[list[float]]:
    if not isinstance(values, list):
        raise GeometryCorrectionError("Draw a valid correction box.")
    boxes = [_normalize_crop_box(value, image_size) for value in values]
    if not boxes:
        raise GeometryCorrectionError("Draw a correction box before saving.")
    return boxes


def _normalize_crop_box(value: Any, image_size: tuple[int, int]) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        raise GeometryCorrectionError("Draw a valid correction box.")
    try:
        x, y, width, height = [float(part) for part in value]
    except (TypeError, ValueError) as exc:
        raise GeometryCorrectionError("Draw a valid correction box.") from exc
    if width < 0:
        x += width
        width = abs(width)
    if height < 0:
        y += height
        height = abs(height)
    image_width, image_height = image_size
    x1 = max(0.0, min(float(image_width), x))
    y1 = max(0.0, min(float(image_height), y))
    x2 = max(0.0, min(float(image_width), x + width))
    y2 = max(0.0, min(float(image_height), y + height))
    clipped = [round(x1, 3), round(y1, 3), round(max(0.0, x2 - x1), 3), round(max(0.0, y2 - y1), 3)]
    if clipped[2] < MIN_CORRECTION_BOX_SIZE or clipped[3] < MIN_CORRECTION_BOX_SIZE:
        raise GeometryCorrectionError("The correction box is too small.")
    return clipped


def _split_detail_ref(detail_ref: str | None, index: int) -> str | None:
    if not detail_ref:
        return f"Cloud {index}"
    return f"{detail_ref}.{index}"


def _xyxy_from_xywh(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        return []
    x, y, width, height = [float(part) for part in value]
    return [round(x, 3), round(y, 3), round(x + width, 3), round(y + height, 3)]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
