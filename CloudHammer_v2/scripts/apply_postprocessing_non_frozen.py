from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from build_postprocessing_apply_dry_run_comparison import (
    DEFAULT_OUTPUT_DIR as DEFAULT_COMPARISON_DIR,
    candidate_source_page_key,
)
from build_postprocessing_dry_run_plan import (
    DEFAULT_FROZEN_MANIFEST,
    box_area,
    candidate_by_id,
    candidate_page_keys,
    frozen_page_keys,
    project_path,
    read_json,
    read_jsonl,
    round_box,
    write_json,
    write_jsonl,
    xyxy_to_xywh,
)


DEFAULT_OUTPUT_DIR = DEFAULT_COMPARISON_DIR.parent / "postprocessing_apply_non_frozen_20260505"


def confidence_tier(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def normalize_bbox(row: dict[str, Any]) -> list[float]:
    box = row.get("bbox_page_xyxy")
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError(f"Candidate {row.get('candidate_id')} has invalid bbox_page_xyxy")
    values = [float(value) for value in box]
    x1, y1, x2, y2 = values
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def base_confidence(row: dict[str, Any]) -> float | None:
    for key in ("whole_cloud_confidence", "confidence"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def copy_crop_fields(base: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "crop_image_path",
        "crop_box_page_xyxy",
        "crop_box_page_xywh",
        "crop_width",
        "crop_height",
        "crop_area",
    ]
    return {key: base.get(key) for key in keys if key in base}


def make_postprocessed_row_from_preview(
    preview: dict[str, Any],
    source_candidates: dict[str, dict[str, Any]],
    *,
    source_manifest: Path,
) -> dict[str, Any]:
    source_ids = [str(value) for value in preview.get("source_candidate_ids") or []]
    base = source_candidates[source_ids[0]]
    box = normalize_bbox(preview)
    confidence = base_confidence(preview)
    action = str(preview.get("preview_action") or "")
    crop_fields = {}
    crop_status = "needs_regeneration_for_postprocessed_bbox"
    if action == "unchanged":
        crop_fields = copy_crop_fields(base)
        crop_status = "source_crop_preserved"

    row = {
        "schema": "cloudhammer_v2.postprocessed_non_frozen_candidate.v1",
        "candidate_id": preview["candidate_id"],
        "source_candidate_ids": source_ids,
        "source_candidate_manifest": str(source_manifest),
        "postprocessing_status": "applied_non_frozen_derived",
        "postprocessing_action": action,
        "postprocessing_label": preview.get("label") or "",
        "postprocessing_provenance": preview.get("postprocessing_provenance") or {},
        "confidence": confidence,
        "whole_cloud_confidence": confidence,
        "confidence_tier": confidence_tier(confidence),
        "confidence_policy": preview.get("confidence_policy"),
        "source_confidences": preview.get("source_confidences") or [],
        "bbox_page_xyxy": round_box(box),
        "bbox_page_xywh": round_box(xyxy_to_xywh(box)),
        "bbox_width": round(box[2] - box[0], 3),
        "bbox_height": round(box[3] - box[1], 3),
        "bbox_area": round(box_area(box), 3),
        "page_width": preview.get("page_width"),
        "page_height": preview.get("page_height"),
        "page_number": preview.get("page_number"),
        "pdf_path": preview.get("pdf_path"),
        "pdf_stem": preview.get("pdf_stem"),
        "render_path": preview.get("render_path"),
        "source_page_key": preview.get("source_page_key"),
        "source_mode": "postprocessed_non_frozen_candidate",
        "crop_status": crop_status,
    }
    row.update(crop_fields)
    return row


def make_carried_row(
    source: dict[str, Any],
    *,
    source_manifest: Path,
) -> dict[str, Any]:
    box = normalize_bbox(source)
    confidence = base_confidence(source)
    row = {
        "schema": "cloudhammer_v2.postprocessed_non_frozen_candidate.v1",
        "candidate_id": source["candidate_id"],
        "source_candidate_ids": [source["candidate_id"]],
        "source_candidate_manifest": str(source_manifest),
        "postprocessing_status": "applied_non_frozen_derived",
        "postprocessing_action": "carried_through_not_flagged_by_diagnostic",
        "postprocessing_label": "",
        "postprocessing_provenance": {
            "reason": "source candidate was not referenced by the reviewed postprocessing diagnostic apply preview"
        },
        "confidence": confidence,
        "whole_cloud_confidence": confidence,
        "confidence_tier": source.get("confidence_tier") or confidence_tier(confidence),
        "confidence_policy": "source_confidence",
        "source_confidences": [] if confidence is None else [round(confidence, 6)],
        "bbox_page_xyxy": round_box(box),
        "bbox_page_xywh": round_box(xyxy_to_xywh(box)),
        "bbox_width": round(box[2] - box[0], 3),
        "bbox_height": round(box[3] - box[1], 3),
        "bbox_area": round(box_area(box), 3),
        "page_width": source.get("page_width"),
        "page_height": source.get("page_height"),
        "page_number": source.get("page_number"),
        "pdf_path": source.get("pdf_path"),
        "pdf_stem": source.get("pdf_stem"),
        "render_path": source.get("render_path"),
        "source_page_key": candidate_source_page_key(source),
        "source_mode": "postprocessed_non_frozen_candidate",
        "crop_status": "source_crop_preserved",
    }
    row.update(copy_crop_fields(source))
    return row


def validate_comparison(summary: dict[str, Any], preview_rows: list[dict[str, Any]], change_rows: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    if summary.get("unresolved_manual_geometry_rows_after_geometry_review") != 0:
        errors.append("comparison has unresolved manual geometry rows")
    if summary.get("preview_output_candidates") != len(preview_rows):
        errors.append("preview row count does not match comparison summary")
    if summary.get("change_records") != len(change_rows):
        errors.append("change row count does not match comparison summary")
    candidate_ids = [str(row.get("candidate_id") or "") for row in preview_rows]
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("preview contains duplicate candidate_id values")
    for row in preview_rows:
        box = normalize_bbox(row)
        if box[2] <= box[0] or box[3] <= box[1]:
            errors.append(f"preview candidate {row.get('candidate_id')} has non-positive bbox")
    if errors:
        raise ValueError("Accepted comparison is not apply-ready:\n" + "\n".join(errors))


def suppressed_source_records(change_rows: list[dict[str, Any]], output_candidate_ids: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for change in change_rows:
        action = str(change.get("action_type") or "")
        source_ids = [str(value) for value in change.get("source_candidate_ids") or []]
        output_ids = [str(value) for value in change.get("output_candidate_ids") or []]
        for source_id in source_ids:
            if source_id in output_candidate_ids:
                continue
            records.append(
                {
                    "schema": "cloudhammer_v2.postprocessed_non_frozen_suppressed_source.v1",
                    "source_candidate_id": source_id,
                    "suppression_reason": action,
                    "replaced_by_candidate_ids": output_ids,
                    "change_record": change,
                }
            )
    return sorted(records, key=lambda row: row["source_candidate_id"])


def build_applied_manifest(
    *,
    comparison_dir: Path,
    frozen_manifest: Path,
    approval_note: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    summary_path = comparison_dir / "postprocessing_apply_dry_run_summary.json"
    preview_path = comparison_dir / "postprocessing_apply_dry_run_candidate_preview.jsonl"
    changes_path = comparison_dir / "postprocessing_apply_dry_run_changes.jsonl"

    comparison_summary = read_json(summary_path)
    preview_rows = read_jsonl(preview_path)
    change_rows = read_jsonl(changes_path)
    validate_comparison(comparison_summary, preview_rows, change_rows)

    source_candidate_manifest = project_path(comparison_summary.get("source_candidate_manifest"))
    if source_candidate_manifest is None or not source_candidate_manifest.exists():
        raise FileNotFoundError(f"Source candidate manifest not found: {comparison_summary.get('source_candidate_manifest')}")

    source_candidates = candidate_by_id(read_jsonl(source_candidate_manifest))
    referenced_source_ids = {
        str(source_id)
        for change in change_rows
        for source_id in change.get("source_candidate_ids") or []
    }
    if len(referenced_source_ids) != comparison_summary.get("referenced_source_candidates"):
        raise ValueError("Referenced source candidate count does not match comparison summary")

    missing_source_ids = sorted(source_id for source_id in referenced_source_ids if source_id not in source_candidates)
    if missing_source_ids:
        raise KeyError(f"Referenced source candidates missing from source manifest: {missing_source_ids[:20]}")

    applied_rows = [
        make_postprocessed_row_from_preview(preview, source_candidates, source_manifest=source_candidate_manifest)
        for preview in preview_rows
    ]

    for candidate_id, source in sorted(source_candidates.items()):
        if candidate_id in referenced_source_ids:
            continue
        applied_rows.append(make_carried_row(source, source_manifest=source_candidate_manifest))

    applied_rows = sorted(applied_rows, key=lambda row: (str(row.get("render_path") or ""), str(row["candidate_id"])))
    output_ids = {str(row["candidate_id"]) for row in applied_rows}
    if len(output_ids) != len(applied_rows):
        raise ValueError("Applied manifest contains duplicate candidate_id values")

    frozen_keys = frozen_page_keys(frozen_manifest)
    frozen_violations = [
        str(row["candidate_id"])
        for row in applied_rows
        if candidate_page_keys(row) & frozen_keys
    ]
    if frozen_violations:
        raise ValueError(f"Frozen page guard violation in applied manifest: {frozen_violations[:20]}")

    suppressed_rows = suppressed_source_records(change_rows, output_ids)
    action_counts = Counter(str(row.get("postprocessing_action") or "") for row in applied_rows)
    crop_status_counts = Counter(str(row.get("crop_status") or "") for row in applied_rows)
    summary = {
        "schema": "cloudhammer_v2.postprocessed_non_frozen_apply_summary.v1",
        "status": "applied_non_frozen_derived_manifest_written",
        "approval_note": approval_note,
        "comparison_dir": str(comparison_dir),
        "comparison_summary": str(summary_path),
        "source_candidate_manifest": str(source_candidate_manifest),
        "frozen_manifest_guard": str(frozen_manifest),
        "source_manifest_candidates": len(source_candidates),
        "referenced_source_candidates": len(referenced_source_ids),
        "carried_through_unflagged_candidates": len(source_candidates) - len(referenced_source_ids),
        "postprocessed_output_candidates": len(applied_rows),
        "candidate_count_delta_vs_source_manifest": len(applied_rows) - len(source_candidates),
        "suppressed_source_candidates": len(suppressed_rows),
        "postprocessing_actions": dict(sorted(action_counts.items())),
        "crop_status": dict(sorted(crop_status_counts.items())),
        "comparison_warnings_carried_forward": comparison_summary.get("warnings") or [],
        "guardrails": [
            "derived_manifest_only",
            "non_frozen_source_manifest_only",
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
    return applied_rows, suppressed_rows, summary


def markdown_summary(summary: dict[str, Any], output_dir: Path) -> str:
    lines = [
        "# Postprocessed Non-Frozen Candidate Manifest",
        "",
        "Status: derived non-frozen apply output. This writes a new manifest from the accepted apply dry-run comparison and does not mutate the legacy source manifest.",
        "",
        f"Approval note: {summary['approval_note']}",
        "",
        "## Counts",
        "",
        f"- source manifest candidates: `{summary['source_manifest_candidates']}`",
        f"- referenced source candidates: `{summary['referenced_source_candidates']}`",
        f"- carried-through unflagged candidates: `{summary['carried_through_unflagged_candidates']}`",
        f"- postprocessed output candidates: `{summary['postprocessed_output_candidates']}`",
        f"- candidate count delta vs source manifest: `{summary['candidate_count_delta_vs_source_manifest']}`",
        f"- suppressed source candidates: `{summary['suppressed_source_candidates']}`",
        "",
        "## Postprocessing Actions",
        "",
    ]
    for key, value in summary["postprocessing_actions"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Crop Status", ""])
    for key, value in summary["crop_status"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Warnings Carried Forward", ""])
    if summary["comparison_warnings_carried_forward"]:
        for warning in summary["comparison_warnings_carried_forward"]:
            lines.append(f"- `{warning['warning_type']}`: `{warning}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Artifacts", ""])
    lines.append(f"- `{output_dir / 'postprocessed_non_frozen_candidates_manifest.jsonl'}`")
    lines.append(f"- `{output_dir / 'postprocessed_non_frozen_suppressed_sources.jsonl'}`")
    lines.append(f"- `{output_dir / 'postprocessed_non_frozen_apply_summary.json'}`")
    lines.append(f"- `{output_dir / 'postprocessed_non_frozen_apply_summary.md'}`")
    lines.extend(
        [
            "",
            "Safety: no labels, eval manifests, prediction files, model files, source candidate manifests, datasets, training data, or threshold-tuning inputs were edited.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply the accepted non-frozen postprocessing preview into a derived candidate manifest."
    )
    parser.add_argument("--comparison-dir", type=Path, default=DEFAULT_COMPARISON_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--frozen-manifest", type=Path, default=DEFAULT_FROZEN_MANIFEST)
    parser.add_argument(
        "--approval-note",
        default="accepted by user in Codex session on 2026-05-05",
        help="Human approval/provenance note for the accepted preview.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    applied_rows, suppressed_rows, summary = build_applied_manifest(
        comparison_dir=args.comparison_dir,
        frozen_manifest=args.frozen_manifest,
        approval_note=args.approval_note,
    )
    summary["output_dir"] = str(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "postprocessed_non_frozen_candidates_manifest.jsonl", applied_rows)
    write_jsonl(output_dir / "postprocessed_non_frozen_suppressed_sources.jsonl", suppressed_rows)
    write_json(output_dir / "postprocessed_non_frozen_apply_summary.json", summary)
    (output_dir / "postprocessed_non_frozen_apply_summary.md").write_text(
        markdown_summary(summary, output_dir), encoding="utf-8"
    )

    print("Postprocessing non-frozen apply output")
    print(f"- source_manifest_candidates: {summary['source_manifest_candidates']}")
    print(f"- postprocessed_output_candidates: {summary['postprocessed_output_candidates']}")
    print(f"- suppressed_source_candidates: {summary['suppressed_source_candidates']}")
    print(f"- output_dir: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
