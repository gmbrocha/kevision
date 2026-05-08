from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from build_postprocessing_dry_run_plan import (
    DEFAULT_DIAGNOSTIC_DIR,
    DEFAULT_FROZEN_MANIFEST,
    box_area,
    box_from_candidate,
    candidate_by_id,
    candidate_page_keys,
    frozen_page_keys,
    normalize_xyxy,
    project_path,
    read_csv,
    read_json,
    read_jsonl,
    round_box,
    safe_stem,
    split_ids,
    write_json,
    write_jsonl,
    xyxy_to_xywh,
)


DEFAULT_DRY_RUN_DIR = DEFAULT_DIAGNOSTIC_DIR / "dry_run_postprocessor_20260505"
DEFAULT_GEOMETRY_REVIEW = (
    DEFAULT_DRY_RUN_DIR / "blocked_geometry_review" / "postprocessing_geometry_review.reviewed.csv"
)
DEFAULT_OUTPUT_DIR = DEFAULT_DRY_RUN_DIR / "postprocessing_apply_dry_run_20260505"

COMPONENT_SCHEMA = "cloudhammer_v2.postprocessing_dry_run_component_action.v1"
CANDIDATE_SCHEMA = "cloudhammer_v2.postprocessing_dry_run_candidate_action.v1"
ROW_SCHEMA = "cloudhammer_v2.postprocessing_dry_run_row_action.v1"


def parse_bbox_field(value: str, context: str) -> list[float]:
    if not value or not value.strip():
        raise ValueError(f"{context}: missing bbox")
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError(f"{context}: bbox must be a list")
    return normalize_xyxy(payload)


def parse_child_boxes(value: str, context: str) -> list[dict[str, Any]]:
    if not value or not value.strip():
        raise ValueError(f"{context}: missing child_bboxes_json")
    payload = json.loads(value)
    if not isinstance(payload, list):
        raise ValueError(f"{context}: child_bboxes_json must be a list")
    children: list[dict[str, Any]] = []
    for index, child in enumerate(payload, start=1):
        child_context = f"{context} child {index}"
        if isinstance(child, dict):
            if "bbox_xyxy" not in child:
                raise ValueError(f"{child_context}: missing bbox_xyxy")
            box = normalize_xyxy(child["bbox_xyxy"])
            label = str(child.get("label") or f"child_{index:03d}")
            source_ids = [str(item) for item in child.get("source_candidate_ids") or []]
        elif isinstance(child, list):
            box = normalize_xyxy(child)
            label = f"child_{index:03d}"
            source_ids = []
        else:
            raise ValueError(f"{child_context}: expected dict or bbox list")
        children.append(
            {
                "child_index": index,
                "bbox_xyxy": round_box(box),
                "label": label,
                "source_candidate_ids": source_ids,
            }
        )
    return children


def source_row_numbers(row: dict[str, str]) -> list[int]:
    numbers: list[int] = []
    for raw in split_ids(row.get("source_row_numbers")) or [row.get("source_row_numbers") or ""]:
        for part in str(raw).replace(",", "|").split("|"):
            part = part.strip()
            if not part:
                continue
            try:
                numbers.append(int(part))
            except ValueError:
                pass
    return numbers


def candidate_source_page_key(candidate: dict[str, Any]) -> str:
    pdf_stem = str(candidate.get("pdf_stem") or "")
    page_number = candidate.get("page_number")
    if pdf_stem and page_number not in (None, ""):
        try:
            return f"{safe_stem(pdf_stem)}:p{int(page_number) - 1:04d}"
        except ValueError:
            pass
    render_path = candidate.get("render_path")
    if render_path:
        return f"render:{Path(str(render_path)).stem}"
    return ""


def sort_candidate_ids(candidate_ids: set[str]) -> list[str]:
    return sorted(candidate_ids, key=lambda value: (value.lower(), value))


def output_id_for_component(component_id: str) -> str:
    return f"postproc_{component_id}"


def output_id_for_child(source_candidate_id: str, child_index: int) -> str:
    return f"{source_candidate_id}__postproc_child_{child_index:03d}"


def first_known_candidate(
    source_ids: list[str], candidates: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    for source_id in source_ids:
        if source_id in candidates:
            return candidates[source_id]
    raise KeyError(f"No known source candidate among {source_ids}")


def confidence_values(source_ids: list[str], candidates: dict[str, dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for source_id in source_ids:
        candidate = candidates.get(source_id)
        if not candidate:
            continue
        for key in ("whole_cloud_confidence", "confidence"):
            value = candidate.get(key)
            if value not in (None, ""):
                try:
                    values.append(float(value))
                    break
                except (TypeError, ValueError):
                    pass
    return values


def make_preview_candidate(
    *,
    output_candidate_id: str,
    source_candidate_ids: list[str],
    bbox_xyxy: list[float],
    preview_action: str,
    provenance: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
    label: str = "",
    confidence_policy: str = "max_source_confidence",
) -> dict[str, Any]:
    base = first_known_candidate(source_candidate_ids, candidates)
    box = normalize_xyxy(bbox_xyxy)
    width = box[2] - box[0]
    height = box[3] - box[1]
    confidences = confidence_values(source_candidate_ids, candidates)
    confidence = max(confidences) if confidences else None
    return {
        "schema": "cloudhammer_v2.postprocessing_apply_dry_run_candidate_preview.v1",
        "candidate_id": output_candidate_id,
        "source_candidate_ids": source_candidate_ids,
        "source_page_key": candidate_source_page_key(base),
        "preview_action": preview_action,
        "label": label,
        "bbox_page_xyxy": round_box(box),
        "bbox_page_xywh": round_box(xyxy_to_xywh(box)),
        "bbox_width": round(width, 3),
        "bbox_height": round(height, 3),
        "bbox_area": round(box_area(box), 3),
        "confidence": None if confidence is None else round(confidence, 6),
        "whole_cloud_confidence": None if confidence is None else round(confidence, 6),
        "confidence_policy": confidence_policy,
        "source_confidences": [round(value, 6) for value in confidences],
        "page_width": base.get("page_width"),
        "page_height": base.get("page_height"),
        "page_number": base.get("page_number"),
        "pdf_path": base.get("pdf_path"),
        "pdf_stem": base.get("pdf_stem"),
        "render_path": base.get("render_path"),
        "source_candidate_manifest_schema": base.get("schema"),
        "source_mode": "postprocessing_apply_dry_run_preview",
        "postprocessing_provenance": provenance,
    }


def make_change_record(
    *,
    action_type: str,
    source_candidate_ids: list[str],
    output_candidate_ids: list[str],
    before_boxes: list[list[float]],
    after_boxes: list[list[float]],
    provenance: dict[str, Any],
    notes: str = "",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    before_area = sum(box_area(box) for box in before_boxes)
    after_area = sum(box_area(box) for box in after_boxes)
    return {
        "schema": "cloudhammer_v2.postprocessing_apply_dry_run_change.v1",
        "action_type": action_type,
        "source_candidate_ids": source_candidate_ids,
        "output_candidate_ids": output_candidate_ids,
        "before_candidate_count": len(source_candidate_ids),
        "after_candidate_count": len(output_candidate_ids),
        "before_bbox_area_sum": round(before_area, 3),
        "after_bbox_area_sum": round(after_area, 3),
        "area_ratio_after_vs_before": None if before_area <= 0 else round(after_area / before_area, 6),
        "before_bboxes_xyxy": [round_box(box) for box in before_boxes],
        "after_bboxes_xyxy": [round_box(box) for box in after_boxes],
        "provenance": provenance,
        "notes": notes,
        "warnings": warnings or [],
    }


def load_plan_rows(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    component_actions: dict[str, dict[str, Any]] = {}
    candidate_actions: dict[str, dict[str, Any]] = {}
    row_actions: list[dict[str, Any]] = []
    for row in read_jsonl(path):
        schema = row.get("schema")
        if schema == COMPONENT_SCHEMA:
            component_actions[str(row["component_id"])] = row
        elif schema == CANDIDATE_SCHEMA:
            candidate_actions[str(row["candidate_id"])] = row
        elif schema == ROW_SCHEMA:
            row_actions.append(row)
    return component_actions, candidate_actions, row_actions


def validate_geometry_rows(rows: list[dict[str, str]]) -> None:
    errors: list[str] = []
    allowed = {"merge_with_component", "component_bbox", "child_bboxes", "corrected_bbox"}
    for index, row in enumerate(rows, start=1):
        item_id = row.get("geometry_item_id") or f"row {index}"
        if row.get("review_status") != "reviewed":
            errors.append(f"{item_id}: review_status is {row.get('review_status')!r}, expected 'reviewed'")
        decision = row.get("geometry_decision") or ""
        if decision not in allowed:
            errors.append(f"{item_id}: unsupported geometry_decision {decision!r}")
        if decision in {"component_bbox", "corrected_bbox"}:
            try:
                parse_bbox_field(row.get("corrected_bbox_xyxy") or "", item_id)
            except ValueError as exc:
                errors.append(str(exc))
        if decision == "child_bboxes":
            try:
                parse_child_boxes(row.get("child_bboxes_json") or "", item_id)
            except ValueError as exc:
                errors.append(str(exc))
    if errors:
        raise ValueError("Reviewed geometry CSV is not apply-preview ready:\n" + "\n".join(errors[:30]))


def build_apply_preview(
    *,
    diagnostic_dir: Path,
    dry_run_dir: Path,
    geometry_review_csv: Path,
    frozen_manifest: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    diagnostic_summary = read_json(diagnostic_dir / "postprocessing_diagnostic_summary.json")
    source_candidate_manifest = project_path(diagnostic_summary.get("source_candidate_manifest"))
    if source_candidate_manifest is None or not source_candidate_manifest.exists():
        raise FileNotFoundError(f"Candidate manifest not found: {diagnostic_summary.get('source_candidate_manifest')}")

    source_candidates = candidate_by_id(read_jsonl(source_candidate_manifest))
    component_plans, candidate_plans, row_actions = load_plan_rows(dry_run_dir / "postprocessing_dry_run_plan.jsonl")
    geometry_rows = read_csv(geometry_review_csv)
    validate_geometry_rows(geometry_rows)

    geometry_by_decision = Counter(row.get("geometry_decision") or "" for row in geometry_rows)
    component_bbox_rows: dict[str, dict[str, str]] = {}
    merge_component_by_candidate: dict[str, str] = {}
    split_rows_by_candidate: dict[str, list[dict[str, str]]] = defaultdict(list)
    corrected_rows_by_candidate: dict[str, dict[str, str]] = {}
    warnings: list[dict[str, Any]] = []
    errors: list[str] = []

    for row in geometry_rows:
        decision = row.get("geometry_decision")
        item_id = row.get("geometry_item_id") or ""
        source_ids = split_ids(row.get("source_candidate_ids"))
        if decision == "component_bbox":
            component_bbox_rows[item_id] = row
        elif decision == "merge_with_component":
            targets = split_ids(row.get("target_candidate_ids"))
            if len(targets) != 1:
                errors.append(f"{item_id}: merge_with_component needs exactly one target component id")
                continue
            for source_id in source_ids:
                merge_component_by_candidate[source_id] = targets[0]
        elif decision == "child_bboxes":
            for source_id in source_ids:
                split_rows_by_candidate[source_id].append(row)
        elif decision == "corrected_bbox":
            for source_id in source_ids:
                corrected_rows_by_candidate[source_id] = row

    if errors:
        raise ValueError("Reviewed geometry CSV has invalid merge/component links:\n" + "\n".join(errors[:30]))

    chosen_split_rows: dict[str, dict[str, str]] = {}
    ignored_split_rows: dict[str, list[dict[str, str]]] = {}
    for source_id, rows in split_rows_by_candidate.items():
        sorted_rows = sorted(rows, key=lambda row: (source_row_numbers(row), row.get("geometry_item_id") or ""))
        chosen = sorted_rows[-1]
        chosen_split_rows[source_id] = chosen
        ignored = sorted_rows[:-1]
        if ignored:
            ignored_split_rows[source_id] = ignored
            warnings.append(
                {
                    "warning_type": "duplicate_child_geometry_rows_collapsed",
                    "source_candidate_id": source_id,
                    "kept_geometry_item_id": chosen.get("geometry_item_id"),
                    "ignored_geometry_item_ids": [row.get("geometry_item_id") for row in ignored],
                    "reason": "Multiple reviewed split rows targeted the same source candidate; the latest source row was used for the apply-preview.",
                }
            )

    referenced_candidate_ids: set[str] = set(candidate_plans)
    for row in row_actions:
        referenced_candidate_ids.update(str(item) for item in row.get("candidate_ids") or [])
    for row in geometry_rows:
        referenced_candidate_ids.update(split_ids(row.get("source_candidate_ids")))
        targets = split_ids(row.get("target_candidate_ids"))
        for target in targets:
            if not target.startswith("merge_component_"):
                referenced_candidate_ids.add(target)
    referenced_candidate_ids = {candidate_id for candidate_id in referenced_candidate_ids if candidate_id}

    unknown_source_ids = sorted(candidate_id for candidate_id in referenced_candidate_ids if candidate_id not in source_candidates)
    if unknown_source_ids:
        raise KeyError(f"Referenced candidates missing from source manifest: {unknown_source_ids[:20]}")

    frozen_keys = frozen_page_keys(frozen_manifest)
    frozen_violations = [
        candidate_id
        for candidate_id in sort_candidate_ids(referenced_candidate_ids)
        if candidate_page_keys(source_candidates[candidate_id]) & frozen_keys
    ]
    if frozen_violations:
        raise ValueError(f"Frozen page guard violation in postprocessing apply preview: {frozen_violations[:20]}")

    preview_candidates: list[dict[str, Any]] = []
    change_records: list[dict[str, Any]] = []
    output_candidate_ids: set[str] = set()
    consumed_source_ids: set[str] = set()
    action_source_counts: Counter[str] = Counter()
    action_output_counts: Counter[str] = Counter()

    # Reviewed merge components supersede their source fragment candidates.
    for component_id, component_row in sorted(component_bbox_rows.items()):
        source_ids = split_ids(component_row.get("source_candidate_ids"))
        if component_id not in component_plans:
            warnings.append(
                {
                    "warning_type": "component_bbox_without_dry_run_component_plan",
                    "component_id": component_id,
                    "source_candidate_ids": source_ids,
                }
            )
        missing_merge_links = [
            source_id
            for source_id in source_ids
            if merge_component_by_candidate.get(source_id) not in {None, component_id}
        ]
        if missing_merge_links:
            warnings.append(
                {
                    "warning_type": "component_source_has_conflicting_merge_link",
                    "component_id": component_id,
                    "source_candidate_ids": missing_merge_links,
                }
            )
        bbox = parse_bbox_field(component_row.get("corrected_bbox_xyxy") or "", component_id)
        output_id = output_id_for_component(component_id)
        provenance = {
            "review_source": "postprocessing_geometry_review.reviewed.csv",
            "geometry_item_id": component_id,
            "geometry_decision": "component_bbox",
            "source_row_numbers": source_row_numbers(component_row),
            "dry_run_component_id": component_id,
        }
        preview_candidates.append(
            make_preview_candidate(
                output_candidate_id=output_id,
                source_candidate_ids=source_ids,
                bbox_xyxy=bbox,
                preview_action="merge_component_bbox",
                provenance=provenance,
                candidates=source_candidates,
            )
        )
        before_boxes = [box_from_candidate(source_candidates[source_id]) for source_id in source_ids]
        change_records.append(
            make_change_record(
                action_type="merge_component_bbox",
                source_candidate_ids=source_ids,
                output_candidate_ids=[output_id],
                before_boxes=before_boxes,
                after_boxes=[bbox],
                provenance=provenance,
                notes="Reviewed geometry collapses same-cloud fragments into one component bbox.",
            )
        )
        consumed_source_ids.update(source_ids)
        output_candidate_ids.add(output_id)
        action_source_counts["merge_component_bbox"] += len(source_ids)
        action_output_counts["merge_component_bbox"] += 1

    # Reviewed split rows replace overmerged source candidates with child boxes.
    for source_id, split_row in sorted(chosen_split_rows.items()):
        if source_id in consumed_source_ids:
            warnings.append(
                {
                    "warning_type": "split_source_already_consumed",
                    "source_candidate_id": source_id,
                    "kept_geometry_item_id": split_row.get("geometry_item_id"),
                }
            )
            continue
        children = parse_child_boxes(split_row.get("child_bboxes_json") or "", split_row.get("geometry_item_id") or source_id)
        child_output_ids: list[str] = []
        child_boxes: list[list[float]] = []
        ignored_rows = ignored_split_rows.get(source_id, [])
        for child in children:
            child_index = int(child["child_index"])
            output_id = output_id_for_child(source_id, child_index)
            child_output_ids.append(output_id)
            child_boxes.append(child["bbox_xyxy"])
            provenance = {
                "review_source": "postprocessing_geometry_review.reviewed.csv",
                "geometry_item_id": split_row.get("geometry_item_id"),
                "geometry_decision": "child_bboxes",
                "source_row_numbers": source_row_numbers(split_row),
                "child_index": child_index,
                "ignored_duplicate_geometry_item_ids": [row.get("geometry_item_id") for row in ignored_rows],
            }
            preview_candidates.append(
                make_preview_candidate(
                    output_candidate_id=output_id,
                    source_candidate_ids=[source_id],
                    bbox_xyxy=child["bbox_xyxy"],
                    preview_action="split_child_bbox",
                    provenance=provenance,
                    candidates=source_candidates,
                    label=child.get("label") or "",
                    confidence_policy="source_parent_confidence",
                )
            )
            output_candidate_ids.add(output_id)
        before_box = box_from_candidate(source_candidates[source_id])
        change_records.append(
            make_change_record(
                action_type="split_child_bboxes",
                source_candidate_ids=[source_id],
                output_candidate_ids=child_output_ids,
                before_boxes=[before_box],
                after_boxes=child_boxes,
                provenance={
                    "review_source": "postprocessing_geometry_review.reviewed.csv",
                    "geometry_item_id": split_row.get("geometry_item_id"),
                    "geometry_decision": "child_bboxes",
                    "source_row_numbers": source_row_numbers(split_row),
                    "ignored_duplicate_geometry_item_ids": [row.get("geometry_item_id") for row in ignored_rows],
                },
                notes="Reviewed geometry replaces an overmerged candidate with explicit child cloud boxes.",
                warnings=(
                    ["duplicate_child_geometry_rows_collapsed"] if ignored_rows else []
                ),
            )
        )
        consumed_source_ids.add(source_id)
        action_source_counts["split_child_bboxes"] += 1
        action_output_counts["split_child_bboxes"] += len(child_output_ids)

    # Reviewed corrected bbox rows resolve tighten_adjust/manual-geometry cases.
    for source_id, corrected_row in sorted(corrected_rows_by_candidate.items()):
        if source_id in consumed_source_ids:
            warnings.append(
                {
                    "warning_type": "corrected_bbox_source_already_consumed",
                    "source_candidate_id": source_id,
                    "geometry_item_id": corrected_row.get("geometry_item_id"),
                }
            )
            continue
        bbox = parse_bbox_field(corrected_row.get("corrected_bbox_xyxy") or "", corrected_row.get("geometry_item_id") or source_id)
        source_candidate = source_candidates[source_id]
        provenance = {
            "review_source": "postprocessing_geometry_review.reviewed.csv",
            "geometry_item_id": corrected_row.get("geometry_item_id"),
            "geometry_decision": "corrected_bbox",
            "source_row_numbers": source_row_numbers(corrected_row),
        }
        preview_candidates.append(
            make_preview_candidate(
                output_candidate_id=source_id,
                source_candidate_ids=[source_id],
                bbox_xyxy=bbox,
                preview_action="corrected_bbox_update",
                provenance=provenance,
                candidates=source_candidates,
            )
        )
        change_records.append(
            make_change_record(
                action_type="corrected_bbox_update",
                source_candidate_ids=[source_id],
                output_candidate_ids=[source_id],
                before_boxes=[box_from_candidate(source_candidate)],
                after_boxes=[bbox],
                provenance=provenance,
                notes="Reviewed corrected bbox replaces the original candidate bbox.",
            )
        )
        consumed_source_ids.add(source_id)
        output_candidate_ids.add(source_id)
        action_source_counts["corrected_bbox_update"] += 1
        action_output_counts["corrected_bbox_update"] += 1

    # Deterministic tighten actions from the reviewed diagnostic dry-run plan.
    for source_id, candidate_plan in sorted(candidate_plans.items()):
        if source_id in consumed_source_ids:
            continue
        tighten_update = candidate_plan.get("tighten_update")
        if not tighten_update:
            continue
        bbox = normalize_xyxy(tighten_update["proposed_bbox_xyxy"])
        provenance = {
            "review_source": "postprocessing_diagnostic_review_log.reviewed.csv",
            "dry_run_source": "postprocessing_dry_run_plan.jsonl",
            "review_row_numbers": candidate_plan.get("review_row_numbers") or [],
            "review_decisions": candidate_plan.get("review_decisions") or [],
        }
        preview_candidates.append(
            make_preview_candidate(
                output_candidate_id=source_id,
                source_candidate_ids=[source_id],
                bbox_xyxy=bbox,
                preview_action="tighten_bbox",
                provenance=provenance,
                candidates=source_candidates,
            )
        )
        change_records.append(
            make_change_record(
                action_type="tighten_bbox",
                source_candidate_ids=[source_id],
                output_candidate_ids=[source_id],
                before_boxes=[box_from_candidate(source_candidates[source_id])],
                after_boxes=[bbox],
                provenance=provenance,
                notes="Reviewed diagnostic tighten action uses the dry-run tight member bbox.",
            )
        )
        consumed_source_ids.add(source_id)
        output_candidate_ids.add(source_id)
        action_source_counts["tighten_bbox"] += 1
        action_output_counts["tighten_bbox"] += 1

    # Carry through any referenced candidates that are unaffected by the reviewed postprocessing plan.
    for source_id in sort_candidate_ids(referenced_candidate_ids - consumed_source_ids):
        bbox = box_from_candidate(source_candidates[source_id])
        provenance = {
            "review_source": "postprocessing_diagnostic_review_log.reviewed.csv",
            "dry_run_source": "postprocessing_dry_run_plan.jsonl",
            "reason": "no reviewed postprocessing geometry change",
            "candidate_plan": candidate_plans.get(source_id, {}),
        }
        preview_candidates.append(
            make_preview_candidate(
                output_candidate_id=source_id,
                source_candidate_ids=[source_id],
                bbox_xyxy=bbox,
                preview_action="unchanged",
                provenance=provenance,
                candidates=source_candidates,
                confidence_policy="source_confidence",
            )
        )
        change_records.append(
            make_change_record(
                action_type="unchanged",
                source_candidate_ids=[source_id],
                output_candidate_ids=[source_id],
                before_boxes=[bbox],
                after_boxes=[bbox],
                provenance=provenance,
                notes="Candidate remains unchanged by the current reviewed postprocessing plan.",
            )
        )
        output_candidate_ids.add(source_id)
        action_source_counts["unchanged"] += 1
        action_output_counts["unchanged"] += 1

    manual_row_actions = [
        row
        for row in row_actions
        if row.get("proposed_action") in {"manual_geometry_required", "manual_split_required"}
    ]
    unresolved_manual_rows: list[dict[str, Any]] = []
    for row in manual_row_actions:
        resolved = False
        decision = row.get("review_decision")
        row_candidate_ids = [str(item) for item in row.get("candidate_ids") or []]
        if decision == "expand":
            resolved = all(candidate_id in merge_component_by_candidate for candidate_id in row_candidate_ids)
        elif decision == "split":
            resolved = all(candidate_id in chosen_split_rows for candidate_id in row_candidate_ids)
        elif decision == "tighten_adjust":
            resolved = all(candidate_id in corrected_rows_by_candidate for candidate_id in row_candidate_ids)
        if not resolved:
            unresolved_manual_rows.append(
                {
                    "row_number": row.get("row_number"),
                    "review_decision": decision,
                    "candidate_ids": row_candidate_ids,
                    "blocked_reason": row.get("blocked_reason"),
                }
            )

    action_area_stats: dict[str, dict[str, Any]] = {}
    for action_type in sorted({record["action_type"] for record in change_records}):
        records = [record for record in change_records if record["action_type"] == action_type]
        before_area = sum(float(record["before_bbox_area_sum"]) for record in records)
        after_area = sum(float(record["after_bbox_area_sum"]) for record in records)
        action_area_stats[action_type] = {
            "change_records": len(records),
            "source_candidates": sum(int(record["before_candidate_count"]) for record in records),
            "output_candidates": sum(int(record["after_candidate_count"]) for record in records),
            "before_bbox_area_sum": round(before_area, 3),
            "after_bbox_area_sum": round(after_area, 3),
            "area_ratio_after_vs_before": None if before_area <= 0 else round(after_area / before_area, 6),
        }

    preview_candidates = sorted(preview_candidates, key=lambda row: (row["source_page_key"], row["candidate_id"]))
    change_records = sorted(change_records, key=lambda row: (row["action_type"], "|".join(row["source_candidate_ids"])))

    summary = {
        "schema": "cloudhammer_v2.postprocessing_apply_dry_run_comparison_summary.v1",
        "status": "report_first_dry_run_only",
        "diagnostic_dir": str(diagnostic_dir),
        "dry_run_dir": str(dry_run_dir),
        "geometry_review_csv": str(geometry_review_csv),
        "source_candidate_manifest": str(source_candidate_manifest),
        "frozen_manifest_guard": str(frozen_manifest),
        "reviewed_diagnostic_rows": len(read_csv(diagnostic_dir / "postprocessing_diagnostic_review_log.reviewed.csv")),
        "reviewed_geometry_rows": len(geometry_rows),
        "geometry_decisions": dict(sorted(geometry_by_decision.items())),
        "referenced_source_candidates": len(referenced_candidate_ids),
        "preview_output_candidates": len(preview_candidates),
        "candidate_count_delta": len(preview_candidates) - len(referenced_candidate_ids),
        "change_records": len(change_records),
        "source_candidates_by_action": dict(sorted(action_source_counts.items())),
        "output_candidates_by_action": dict(sorted(action_output_counts.items())),
        "action_area_stats": action_area_stats,
        "manual_geometry_row_actions_before_geometry_review": len(manual_row_actions),
        "unresolved_manual_geometry_rows_after_geometry_review": len(unresolved_manual_rows),
        "unresolved_manual_geometry_rows": unresolved_manual_rows,
        "warnings": warnings,
        "guardrails": [
            "dry_run_only",
            "report_first_only",
            "no_source_candidate_manifest_edits",
            "no_truth_label_edits",
            "no_eval_manifest_edits",
            "no_prediction_file_edits",
            "no_model_file_edits",
            "no_dataset_or_training_data_writes",
            "not_threshold_tuning",
            "excluded_page_disjoint_real_frozen_pages",
        ],
    }
    return preview_candidates, change_records, summary


def markdown_summary(summary: dict[str, Any], output_dir: Path) -> str:
    lines = [
        "# Postprocessing Apply Dry-Run Comparison",
        "",
        "Status: report-first dry-run only. This preview converts the reviewed diagnostic and geometry logs into candidate-level behavior without editing any source manifest.",
        "",
        "Safety: no labels, eval manifests, prediction files, model files, source candidate manifests, datasets, training data, or threshold-tuning inputs were edited.",
        "",
        "## Inputs",
        "",
        f"- reviewed diagnostic rows: `{summary['reviewed_diagnostic_rows']}`",
        f"- reviewed geometry rows: `{summary['reviewed_geometry_rows']}`",
        f"- source candidate manifest: `{summary['source_candidate_manifest']}`",
        f"- frozen manifest guard: `{summary['frozen_manifest_guard']}`",
        "",
        "## Candidate Count Comparison",
        "",
        f"- referenced source candidates: `{summary['referenced_source_candidates']}`",
        f"- preview output candidates: `{summary['preview_output_candidates']}`",
        f"- candidate count delta: `{summary['candidate_count_delta']}`",
        "",
        "## Output Candidates By Action",
        "",
    ]
    for key, value in summary["output_candidates_by_action"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Source Candidates By Action", ""])
    for key, value in summary["source_candidates_by_action"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Geometry Decisions Consumed", ""])
    for key, value in summary["geometry_decisions"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Resolution Check", ""])
    lines.append(
        f"- manual geometry row actions before geometry review: `{summary['manual_geometry_row_actions_before_geometry_review']}`"
    )
    lines.append(
        f"- unresolved manual geometry rows after geometry review: `{summary['unresolved_manual_geometry_rows_after_geometry_review']}`"
    )
    lines.extend(["", "## Warnings", ""])
    if summary["warnings"]:
        for warning in summary["warnings"]:
            lines.append(f"- `{warning['warning_type']}`: `{warning}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Artifacts", ""])
    lines.append(f"- `{output_dir / 'postprocessing_apply_dry_run_candidate_preview.jsonl'}`")
    lines.append(f"- `{output_dir / 'postprocessing_apply_dry_run_changes.jsonl'}`")
    lines.append(f"- `{output_dir / 'postprocessing_apply_dry_run_summary.json'}`")
    lines.append(f"- `{output_dir / 'postprocessing_apply_dry_run_summary.md'}`")
    lines.extend(
        [
            "",
            "Next step: inspect this comparison and decide whether to implement an explicit non-frozen postprocessing apply path.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a report-first postprocessing apply/dry-run comparison from reviewed diagnostic and geometry logs."
    )
    parser.add_argument("--diagnostic-dir", type=Path, default=DEFAULT_DIAGNOSTIC_DIR)
    parser.add_argument("--dry-run-dir", type=Path, default=DEFAULT_DRY_RUN_DIR)
    parser.add_argument("--geometry-review-csv", type=Path, default=DEFAULT_GEOMETRY_REVIEW)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--frozen-manifest", type=Path, default=DEFAULT_FROZEN_MANIFEST)
    args = parser.parse_args()

    output_dir = args.output_dir
    preview_candidates, change_records, summary = build_apply_preview(
        diagnostic_dir=args.diagnostic_dir,
        dry_run_dir=args.dry_run_dir,
        geometry_review_csv=args.geometry_review_csv,
        frozen_manifest=args.frozen_manifest,
    )
    summary["output_dir"] = str(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "postprocessing_apply_dry_run_candidate_preview.jsonl", preview_candidates)
    write_jsonl(output_dir / "postprocessing_apply_dry_run_changes.jsonl", change_records)
    write_json(output_dir / "postprocessing_apply_dry_run_summary.json", summary)
    (output_dir / "postprocessing_apply_dry_run_summary.md").write_text(
        markdown_summary(summary, output_dir), encoding="utf-8"
    )

    print("Postprocessing apply dry-run comparison")
    print(f"- referenced_source_candidates: {summary['referenced_source_candidates']}")
    print(f"- preview_output_candidates: {summary['preview_output_candidates']}")
    print(f"- candidate_count_delta: {summary['candidate_count_delta']}")
    print(f"- unresolved_manual_geometry_rows: {summary['unresolved_manual_geometry_rows_after_geometry_review']}")
    print(f"- output_dir: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
