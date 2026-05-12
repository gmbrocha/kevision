from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .crop_adjustments import CROP_ADJUSTMENT_KEY, crop_adjustment_payload, selected_review_page_boxes
from .legend_context import LEGEND_CONTEXT_KEY, legend_context_payload
from .pre_review import PRE_REVIEW_KEY, pre_review_payload
from .revision_state.models import ChangeItem, CloudCandidate, ReviewEvent, RevisionSet, SheetVersion
from .utils import clean_display_text, json_dumps, normalize_text
from .workspace import WorkspaceStore


REVIEW_EVENT_SCHEMA = "scopeledger.review_event.v1"
REVIEW_EVENT_APP_VERSION = "scopeledger_app_review_events_v1"
REVIEW_CAPTURE_ENV = "REVIEW_CAPTURE"
REVIEW_CAPTURE_DISABLED_VALUES = {"0", "false", "no", "off", "disabled"}
VALID_REVIEW_EVENT_ACTIONS = {
    "accept",
    "reject",
    "resize",
    "merge",
    "split",
    "relabel",
    "needs_followup",
    "undo",
    "comment",
}


@dataclass(frozen=True)
class BulkReviewUpdateResult:
    updated_count: int
    events: list[ReviewEvent]
    updated_items: list[ChangeItem]


def record_review_update(
    store: WorkspaceStore,
    *,
    project_id: str,
    change_id: str,
    changes: dict[str, Any],
    reviewer_id: str | None,
    review_session_id: str | None,
    action: str | None = None,
    notes: str | None = None,
    human_result_overrides: dict[str, Any] | None = None,
) -> tuple[ChangeItem, ReviewEvent | None]:
    before = store.get_change_item(change_id)
    after = replace(before, **changes)
    inferred_action = _valid_action(action) or classify_review_action(before, after)
    event = (
        build_review_event(
            store,
            project_id=project_id,
            before_item=before,
            after_item=after,
            action=inferred_action,
            reviewer_id=reviewer_id,
            review_session_id=review_session_id,
            notes=notes,
            human_result_overrides=human_result_overrides,
        )
        if inferred_action and review_capture_enabled()
        else None
    )

    updated_items: list[ChangeItem] = []
    for item in store.data.change_items:
        updated_items.append(after if item.id == change_id else item)
    store.data.change_items = updated_items
    if event is not None:
        store.data.review_events.append(event)
    store.save()
    return after, event


def record_bulk_review_updates(
    store: WorkspaceStore,
    *,
    project_id: str,
    item_changes: dict[str, dict[str, Any]],
    reviewer_id: str | None,
    review_session_id: str | None,
    action: str | None = None,
    notes: str | None = None,
) -> BulkReviewUpdateResult:
    if not item_changes:
        return BulkReviewUpdateResult(updated_count=0, events=[], updated_items=[])

    requested_changes = {change_id: changes for change_id, changes in item_changes.items() if changes}
    if not requested_changes:
        return BulkReviewUpdateResult(updated_count=0, events=[], updated_items=[])

    events: list[ReviewEvent] = []
    updated_items: list[ChangeItem] = []
    new_items: list[ChangeItem] = []
    explicit_action = _valid_action(action)
    capture_enabled = review_capture_enabled()
    for before in store.data.change_items:
        changes = requested_changes.get(before.id)
        if changes is None:
            new_items.append(before)
            continue
        after = replace(before, **changes)
        if after == before:
            new_items.append(before)
            continue
        inferred_action = explicit_action or classify_review_action(before, after)
        if inferred_action and capture_enabled:
            events.append(
                build_review_event(
                    store,
                    project_id=project_id,
                    before_item=before,
                    after_item=after,
                    action=inferred_action,
                    reviewer_id=reviewer_id,
                    review_session_id=review_session_id,
                    notes=notes,
                )
            )
        new_items.append(after)
        updated_items.append(after)

    if not updated_items:
        return BulkReviewUpdateResult(updated_count=0, events=[], updated_items=[])

    store.data.change_items = new_items
    if events:
        store.data.review_events.extend(events)
    store.save()
    return BulkReviewUpdateResult(updated_count=len(updated_items), events=events, updated_items=updated_items)


def record_internal_review_event(
    store: WorkspaceStore,
    *,
    project_id: str,
    change_id: str,
    action: str,
    reviewer_id: str | None = None,
    review_session_id: str | None = None,
    notes: str | None = None,
    human_result_overrides: dict[str, Any] | None = None,
) -> ReviewEvent | None:
    if action not in VALID_REVIEW_EVENT_ACTIONS:
        raise ValueError(f"Unsupported review event action: {action}")
    if not review_capture_enabled():
        return None
    item = store.get_change_item(change_id)
    event = build_review_event(
        store,
        project_id=project_id,
        before_item=item,
        after_item=item,
        action=action,
        reviewer_id=reviewer_id,
        review_session_id=review_session_id,
        notes=notes,
        human_result_overrides=human_result_overrides,
    )
    store.data.review_events.append(event)
    store.save()
    return event


def review_capture_enabled() -> bool:
    value = os.getenv(REVIEW_CAPTURE_ENV, "true").strip().lower()
    return value not in REVIEW_CAPTURE_DISABLED_VALUES


def build_review_event(
    store: WorkspaceStore,
    *,
    project_id: str,
    before_item: ChangeItem,
    after_item: ChangeItem,
    action: str,
    reviewer_id: str | None,
    review_session_id: str | None,
    notes: str | None = None,
    human_result_overrides: dict[str, Any] | None = None,
) -> ReviewEvent:
    if action not in VALID_REVIEW_EVENT_ACTIONS:
        raise ValueError(f"Unsupported review event action: {action}")
    sheet = _get_optional_sheet(store, before_item.sheet_version_id)
    cloud = _get_optional_cloud(store, before_item.cloud_candidate_id)
    revision_set = _get_revision_set(store, sheet.revision_set_id if sheet else "")
    original_candidate = _original_candidate_snapshot(before_item, cloud, sheet, revision_set)
    ai_suggestion = _ai_suggestion_snapshot(after_item)
    human_result = _human_result_snapshot(after_item, cloud, human_result_overrides)
    ocr_context = _ocr_context_snapshot(before_item, cloud)
    pipeline = _pipeline_metadata(after_item, cloud)
    return ReviewEvent(
        id=str(uuid.uuid4()),
        project_id=project_id,
        sheet_id=before_item.sheet_id,
        revision_id=revision_set.id if revision_set else (sheet.revision_set_id if sheet else None),
        candidate_id=before_item.cloud_candidate_id or before_item.id,
        change_item_id=before_item.id,
        review_session_id=review_session_id,
        reviewer_id=reviewer_id,
        created_at=_utc_now(),
        action=action,
        original_candidate_json=_json_safe(original_candidate),
        ai_suggestion_json=_json_safe(ai_suggestion) if ai_suggestion else None,
        human_result_json=_json_safe(human_result),
        ocr_context_json=_json_safe(ocr_context),
        detector_name=pipeline.get("detector_name"),
        detector_version=pipeline.get("detector_version"),
        pipeline_version=pipeline.get("pipeline_version"),
        model_version=pipeline.get("model_version"),
        app_version=REVIEW_EVENT_APP_VERSION,
        notes=notes if notes is not None else clean_display_text(after_item.reviewer_notes),
    )


def classify_review_action(before: ChangeItem, after: ChangeItem) -> str | None:
    if after.status == "approved" and before.status != "approved":
        return "accept"
    if after.status == "rejected" and before.status != "rejected":
        return "reject"
    if after.status == "pending" and before.status != "pending":
        return "needs_followup"
    if _pre_review_payload(before) != _pre_review_payload(after):
        return "relabel"
    if normalize_text(before.reviewer_text or before.raw_text) != normalize_text(after.reviewer_text or after.raw_text):
        return "relabel"
    if clean_display_text(before.reviewer_notes) != clean_display_text(after.reviewer_notes):
        return "comment"
    return None


def export_review_events_jsonl(
    store: WorkspaceStore,
    *,
    project_id: str,
    output_path: Path | None = None,
) -> Path:
    output = output_path or store.output_dir / f"review_events_{project_id}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(event) for event in store.data.review_events if event.project_id == project_id]
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return output


def _valid_action(action: str | None) -> str | None:
    if not action:
        return None
    return action if action in VALID_REVIEW_EVENT_ACTIONS else None


def _original_candidate_snapshot(
    item: ChangeItem,
    cloud: CloudCandidate | None,
    sheet: SheetVersion | None,
    revision_set: RevisionSet | None,
) -> dict[str, Any]:
    item_payload = asdict(item)
    provenance = dict(item_payload.get("provenance") or {})
    provenance.pop(PRE_REVIEW_KEY, None)
    provenance.pop(CROP_ADJUSTMENT_KEY, None)
    provenance.pop(LEGEND_CONTEXT_KEY, None)
    item_payload["provenance"] = provenance
    return {
        "schema": REVIEW_EVENT_SCHEMA,
        "change_item": item_payload,
        "cloud_candidate": asdict(cloud) if cloud else None,
        "sheet_version": asdict(sheet) if sheet else None,
        "revision_set": asdict(revision_set) if revision_set else None,
    }


def _ai_suggestion_snapshot(item: ChangeItem) -> dict[str, Any] | None:
    payload = pre_review_payload(item)
    if not payload:
        return None
    return {
        "schema": "scopeledger.review_event.ai_suggestion.v1",
        "kind": "pre_review",
        "payload": payload,
    }


def _human_result_snapshot(
    item: ChangeItem,
    cloud: CloudCandidate | None,
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    selected_boxes = selected_review_page_boxes(item, cloud)
    adjustment = crop_adjustment_payload(item)
    payload = {
        "schema": "scopeledger.review_event.human_result.v1",
        "status": item.status,
        "final_label": item.status,
        "final_text": clean_display_text(item.reviewer_text or item.raw_text),
        "notes": clean_display_text(item.reviewer_notes),
        "selected_pre_review": _pre_review_payload(item).get("selected"),
        "final_geometry": {"boxes": selected_boxes},
        "crop_adjustment": adjustment or None,
        "merged_candidate_ids": [],
        "split_child_geometries": [],
        "reject_reason": None,
        "follow_up_status": item.status == "pending",
    }
    if overrides:
        payload.update(overrides)
    return payload


def _ocr_context_snapshot(item: ChangeItem, cloud: CloudCandidate | None) -> dict[str, Any]:
    provenance = item.provenance or {}
    return {
        "schema": "scopeledger.review_event.ocr_context.v1",
        "item_raw_text": item.raw_text,
        "item_reviewer_text": item.reviewer_text,
        "cloud_nearby_text": cloud.nearby_text if cloud else "",
        "cloud_scope_text": cloud.scope_text if cloud else "",
        "cloud_scope_reason": cloud.scope_reason if cloud else "",
        "cloud_scope_signal": cloud.scope_signal if cloud else 0.0,
        "cloud_scope_method": cloud.scope_method if cloud else "",
        "detail_ref": item.detail_ref or (cloud.detail_ref if cloud else None),
        "scope_context_bbox": provenance.get("scope_context_bbox", []),
        "scope_text_reason": provenance.get("scope_text_reason", ""),
        "scope_text_method": provenance.get("scope_text_method", ""),
        "scope_text_word_count": provenance.get("scope_text_word_count", ""),
        "legend_context": legend_context_payload(item),
    }


def _pipeline_metadata(item: ChangeItem, cloud: CloudCandidate | None) -> dict[str, str | None]:
    metadata = dict(cloud.metadata) if cloud else {}
    provenance = item.provenance or {}
    return {
        "detector_name": str(cloud.extraction_method) if cloud else str(provenance.get("extraction_method") or "") or None,
        "detector_version": _first_text(metadata, "detector_version", "cloudhammer_detector_version", "checkpoint_name"),
        "pipeline_version": _first_text(metadata, "pipeline_version", "cloudhammer_pipeline_version", "policy_bucket")
        or str(provenance.get("extraction_method") or "") or None,
        "model_version": _first_text(metadata, "model_version", "model_path", "cloudhammer_model_path"),
    }


def _pre_review_payload(item: ChangeItem) -> dict[str, Any]:
    payload = pre_review_payload(item)
    return payload if isinstance(payload, dict) else {}


def _first_text(values: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _get_optional_sheet(store: WorkspaceStore, sheet_version_id: str) -> SheetVersion | None:
    try:
        return store.get_sheet(sheet_version_id)
    except KeyError:
        return None


def _get_optional_cloud(store: WorkspaceStore, cloud_id: str | None) -> CloudCandidate | None:
    if not cloud_id:
        return None
    try:
        return store.get_cloud(cloud_id)
    except KeyError:
        return None


def _get_revision_set(store: WorkspaceStore, revision_set_id: str) -> RevisionSet | None:
    for revision_set in store.data.revision_sets:
        if revision_set.id == revision_set_id:
            return revision_set
    return None


def _json_safe(value: Any) -> Any:
    return json.loads(json_dumps(value))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
