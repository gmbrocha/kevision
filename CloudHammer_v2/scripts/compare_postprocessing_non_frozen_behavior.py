from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from apply_postprocessing_non_frozen import DEFAULT_OUTPUT_DIR as DEFAULT_APPLY_DIR
from build_postprocessing_apply_dry_run_comparison import candidate_source_page_key
from build_postprocessing_dry_run_plan import (
    box_area,
    box_from_candidate,
    candidate_by_id,
    candidate_page_keys,
    frozen_page_keys,
    project_path,
    read_json,
    read_jsonl,
    round_box,
    write_json,
    write_jsonl,
)


DEFAULT_OUTPUT_DIR = DEFAULT_APPLY_DIR.parent / "postprocessing_behavior_comparison_20260505"


def row_box(row: dict[str, Any]) -> list[float]:
    if isinstance(row.get("bbox_page_xyxy"), list):
        return box_from_candidate(row)
    raise ValueError(f"Candidate row has no bbox_page_xyxy: {row.get('candidate_id')}")


def row_area(row: dict[str, Any]) -> float:
    return box_area(row_box(row))


def source_page_key(row: dict[str, Any]) -> str:
    return str(row.get("source_page_key") or candidate_source_page_key(row))


def area_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    areas = [row_area(row) for row in rows]
    if not areas:
        return {
            "count": 0,
            "area_sum": 0.0,
            "area_mean": 0.0,
            "area_median": 0.0,
            "area_min": 0.0,
            "area_max": 0.0,
        }
    return {
        "count": len(areas),
        "area_sum": round(sum(areas), 3),
        "area_mean": round(mean(areas), 3),
        "area_median": round(median(areas), 3),
        "area_min": round(min(areas), 3),
        "area_max": round(max(areas), 3),
    }


def ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def validate_inputs(
    source_rows: list[dict[str, Any]],
    postprocessed_rows: list[dict[str, Any]],
    suppressed_rows: list[dict[str, Any]],
    apply_summary: dict[str, Any],
    frozen_manifest: Path,
) -> None:
    errors: list[str] = []
    source_ids = [str(row.get("candidate_id") or "") for row in source_rows]
    post_ids = [str(row.get("candidate_id") or "") for row in postprocessed_rows]
    if len(source_ids) != len(set(source_ids)):
        errors.append("source manifest has duplicate candidate_id values")
    if len(post_ids) != len(set(post_ids)):
        errors.append("postprocessed manifest has duplicate candidate_id values")
    if len(source_rows) != apply_summary.get("source_manifest_candidates"):
        errors.append("source manifest count does not match apply summary")
    if len(postprocessed_rows) != apply_summary.get("postprocessed_output_candidates"):
        errors.append("postprocessed manifest count does not match apply summary")
    if len(suppressed_rows) != apply_summary.get("suppressed_source_candidates"):
        errors.append("suppressed source count does not match apply summary")

    for row in [*source_rows, *postprocessed_rows]:
        box = row_box(row)
        if box[2] <= box[0] or box[3] <= box[1]:
            errors.append(f"{row.get('candidate_id')}: non-positive bbox")

    frozen_keys = frozen_page_keys(frozen_manifest)
    source_frozen = [
        str(row.get("candidate_id"))
        for row in source_rows
        if candidate_page_keys(row) & frozen_keys
    ]
    post_frozen = [
        str(row.get("candidate_id"))
        for row in postprocessed_rows
        if candidate_page_keys(row) & frozen_keys
    ]
    if source_frozen or post_frozen:
        errors.append(f"frozen page guard violation: source={source_frozen[:10]} postprocessed={post_frozen[:10]}")

    if errors:
        raise ValueError("Behavior comparison inputs are invalid:\n" + "\n".join(errors[:30]))


def build_source_mapping(
    source_rows: list[dict[str, Any]],
    postprocessed_rows: list[dict[str, Any]],
    suppressed_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    post_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in postprocessed_rows:
        for source_id in row.get("source_candidate_ids") or []:
            post_by_source[str(source_id)].append(row)

    suppressed_by_source = {
        str(row["source_candidate_id"]): row
        for row in suppressed_rows
    }

    records: list[dict[str, Any]] = []
    for source in sorted(source_rows, key=lambda row: str(row.get("candidate_id"))):
        source_id = str(source["candidate_id"])
        outputs = sorted(post_by_source.get(source_id, []), key=lambda row: str(row.get("candidate_id")))
        suppressed = suppressed_by_source.get(source_id)
        source_area = row_area(source)
        output_area = sum(row_area(row) for row in outputs)
        output_actions = sorted({str(row.get("postprocessing_action") or "") for row in outputs})
        if suppressed:
            behavior = "replaced"
        elif outputs and outputs[0].get("candidate_id") == source_id and output_actions:
            behavior = output_actions[0]
        elif outputs:
            behavior = "derived_output"
        else:
            behavior = "dropped_without_replacement"
        records.append(
            {
                "schema": "cloudhammer_v2.postprocessing_non_frozen_source_behavior.v1",
                "source_candidate_id": source_id,
                "source_page_key": source_page_key(source),
                "behavior": behavior,
                "source_bbox_xyxy": round_box(row_box(source)),
                "source_bbox_area": round(source_area, 3),
                "output_candidate_ids": [str(row["candidate_id"]) for row in outputs],
                "output_actions": output_actions,
                "output_candidate_count": len(outputs),
                "output_bbox_area_sum": round(output_area, 3),
                "area_ratio_output_vs_source": ratio(output_area, source_area),
                "suppressed": suppressed is not None,
                "suppression_reason": "" if not suppressed else str(suppressed.get("suppression_reason") or ""),
                "crop_statuses": sorted({str(row.get("crop_status") or "") for row in outputs}),
            }
        )
    return records


def build_page_records(
    source_rows: list[dict[str, Any]],
    postprocessed_rows: list[dict[str, Any]],
    suppressed_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    post_by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        source_by_page[source_page_key(row)].append(row)
    for row in postprocessed_rows:
        post_by_page[source_page_key(row)].append(row)

    suppressed_source_ids = {str(row["source_candidate_id"]) for row in suppressed_rows}
    suppressed_by_page: Counter[str] = Counter()
    for row in source_rows:
        if str(row["candidate_id"]) in suppressed_source_ids:
            suppressed_by_page[source_page_key(row)] += 1

    pages = sorted(set(source_by_page) | set(post_by_page))
    records: list[dict[str, Any]] = []
    for page in pages:
        source_page_rows = source_by_page.get(page, [])
        post_page_rows = post_by_page.get(page, [])
        source_area = sum(row_area(row) for row in source_page_rows)
        post_area = sum(row_area(row) for row in post_page_rows)
        action_counts = Counter(str(row.get("postprocessing_action") or "") for row in post_page_rows)
        crop_status_counts = Counter(str(row.get("crop_status") or "") for row in post_page_rows)
        records.append(
            {
                "schema": "cloudhammer_v2.postprocessing_non_frozen_page_behavior.v1",
                "source_page_key": page,
                "source_candidate_count": len(source_page_rows),
                "postprocessed_candidate_count": len(post_page_rows),
                "candidate_count_delta": len(post_page_rows) - len(source_page_rows),
                "suppressed_source_candidates": int(suppressed_by_page.get(page, 0)),
                "source_bbox_area_sum": round(source_area, 3),
                "postprocessed_bbox_area_sum": round(post_area, 3),
                "area_delta": round(post_area - source_area, 3),
                "area_ratio_postprocessed_vs_source": ratio(post_area, source_area),
                "postprocessing_actions": dict(sorted(action_counts.items())),
                "crop_status": dict(sorted(crop_status_counts.items())),
            }
        )
    return records


def build_comparison(
    *,
    apply_dir: Path,
    frozen_manifest: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    apply_summary = read_json(apply_dir / "postprocessed_non_frozen_apply_summary.json")
    source_manifest = project_path(apply_summary.get("source_candidate_manifest"))
    if source_manifest is None or not source_manifest.exists():
        raise FileNotFoundError(f"Source candidate manifest not found: {apply_summary.get('source_candidate_manifest')}")

    source_rows = read_jsonl(source_manifest)
    postprocessed_rows = read_jsonl(apply_dir / "postprocessed_non_frozen_candidates_manifest.jsonl")
    suppressed_rows = read_jsonl(apply_dir / "postprocessed_non_frozen_suppressed_sources.jsonl")
    validate_inputs(source_rows, postprocessed_rows, suppressed_rows, apply_summary, frozen_manifest)

    source_stats = area_stats(source_rows)
    post_stats = area_stats(postprocessed_rows)
    source_area = float(source_stats["area_sum"])
    post_area = float(post_stats["area_sum"])
    actions = Counter(str(row.get("postprocessing_action") or "") for row in postprocessed_rows)
    crop_status = Counter(str(row.get("crop_status") or "") for row in postprocessed_rows)
    suppression_reasons = Counter(str(row.get("suppression_reason") or "") for row in suppressed_rows)

    source_behavior_records = build_source_mapping(source_rows, postprocessed_rows, suppressed_rows)
    page_records = build_page_records(source_rows, postprocessed_rows, suppressed_rows)

    behavior_counts = Counter(str(row.get("behavior") or "") for row in source_behavior_records)
    page_delta_counts = Counter(
        "candidate_count_decreased" if row["candidate_count_delta"] < 0 else
        "candidate_count_increased" if row["candidate_count_delta"] > 0 else
        "candidate_count_same"
        for row in page_records
    )
    summary = {
        "schema": "cloudhammer_v2.postprocessing_non_frozen_behavior_comparison_summary.v1",
        "status": "report_first_behavior_comparison_only",
        "apply_dir": str(apply_dir),
        "source_candidate_manifest": str(source_manifest),
        "postprocessed_manifest": str(apply_dir / "postprocessed_non_frozen_candidates_manifest.jsonl"),
        "suppressed_sources": str(apply_dir / "postprocessed_non_frozen_suppressed_sources.jsonl"),
        "frozen_manifest_guard": str(frozen_manifest),
        "source_candidate_count": len(source_rows),
        "postprocessed_candidate_count": len(postprocessed_rows),
        "candidate_count_delta": len(postprocessed_rows) - len(source_rows),
        "source_page_count": len({source_page_key(row) for row in source_rows}),
        "postprocessed_page_count": len({source_page_key(row) for row in postprocessed_rows}),
        "suppressed_source_candidates": len(suppressed_rows),
        "source_area_stats": source_stats,
        "postprocessed_area_stats": post_stats,
        "bbox_area_delta": round(post_area - source_area, 3),
        "bbox_area_ratio_postprocessed_vs_source": ratio(post_area, source_area),
        "postprocessing_actions": dict(sorted(actions.items())),
        "source_behavior_counts": dict(sorted(behavior_counts.items())),
        "suppression_reasons": dict(sorted(suppression_reasons.items())),
        "crop_status": dict(sorted(crop_status.items())),
        "page_count_delta_buckets": dict(sorted(page_delta_counts.items())),
        "largest_page_area_reductions": sorted(
            page_records,
            key=lambda row: row["area_delta"],
        )[:5],
        "largest_page_count_changes": sorted(
            page_records,
            key=lambda row: (abs(row["candidate_count_delta"]), abs(row["area_delta"])),
            reverse=True,
        )[:5],
        "guardrails": [
            "report_first_only",
            "non_frozen_source_manifest_only",
            "no_source_candidate_manifest_edits",
            "no_truth_label_edits",
            "no_eval_manifest_edits",
            "no_prediction_file_edits",
            "no_model_file_edits",
            "no_dataset_or_training_data_writes",
            "not_threshold_tuning",
            "excluded_page_disjoint_real_frozen_pages",
            "not_eval_scoring",
        ],
    }
    return source_behavior_records, page_records, summary


def markdown_summary(summary: dict[str, Any], output_dir: Path) -> str:
    lines = [
        "# Non-Frozen Postprocessing Behavior Comparison",
        "",
        "Status: report-first metadata comparison only. This compares the original non-frozen source candidate manifest with the derived postprocessed manifest.",
        "",
        "Safety: no labels, eval manifests, predictions, model files, source manifests, datasets, training data, crops, or threshold-tuning inputs were edited.",
        "",
        "## Counts",
        "",
        f"- source candidates: `{summary['source_candidate_count']}`",
        f"- postprocessed candidates: `{summary['postprocessed_candidate_count']}`",
        f"- candidate count delta: `{summary['candidate_count_delta']}`",
        f"- suppressed source candidates: `{summary['suppressed_source_candidates']}`",
        f"- source pages: `{summary['source_page_count']}`",
        f"- postprocessed pages: `{summary['postprocessed_page_count']}`",
        "",
        "## BBox Area",
        "",
        f"- source bbox area sum: `{summary['source_area_stats']['area_sum']}`",
        f"- postprocessed bbox area sum: `{summary['postprocessed_area_stats']['area_sum']}`",
        f"- bbox area delta: `{summary['bbox_area_delta']}`",
        f"- bbox area ratio postprocessed/source: `{summary['bbox_area_ratio_postprocessed_vs_source']}`",
        "",
        "## Postprocessing Actions",
        "",
    ]
    for key, value in summary["postprocessing_actions"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Source Behavior Counts", ""])
    for key, value in summary["source_behavior_counts"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Crop Status", ""])
    for key, value in summary["crop_status"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Page Count Delta Buckets", ""])
    for key, value in summary["page_count_delta_buckets"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Largest Page Area Reductions", ""])
    for row in summary["largest_page_area_reductions"]:
        lines.append(
            f"- `{row['source_page_key']}`: candidates `{row['source_candidate_count']}` -> "
            f"`{row['postprocessed_candidate_count']}`, area delta `{row['area_delta']}`"
        )
    lines.extend(["", "## Artifacts", ""])
    lines.append(f"- `{output_dir / 'postprocessing_non_frozen_behavior_by_source.jsonl'}`")
    lines.append(f"- `{output_dir / 'postprocessing_non_frozen_behavior_by_page.jsonl'}`")
    lines.append(f"- `{output_dir / 'postprocessing_non_frozen_behavior_summary.json'}`")
    lines.append(f"- `{output_dir / 'postprocessing_non_frozen_behavior_summary.md'}`")
    lines.extend(
        [
            "",
            "Next step: if crop-based inspection/export is needed, regenerate crops for the rows marked `needs_regeneration_for_postprocessed_bbox`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare original non-frozen candidates against the derived postprocessed manifest."
    )
    parser.add_argument("--apply-dir", type=Path, default=DEFAULT_APPLY_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--frozen-manifest", type=Path, default=Path("CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.human_audited.jsonl"))
    args = parser.parse_args()

    output_dir = args.output_dir
    source_behavior_records, page_records, summary = build_comparison(
        apply_dir=args.apply_dir,
        frozen_manifest=args.frozen_manifest,
    )
    summary["output_dir"] = str(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "postprocessing_non_frozen_behavior_by_source.jsonl", source_behavior_records)
    write_jsonl(output_dir / "postprocessing_non_frozen_behavior_by_page.jsonl", page_records)
    write_json(output_dir / "postprocessing_non_frozen_behavior_summary.json", summary)
    (output_dir / "postprocessing_non_frozen_behavior_summary.md").write_text(
        markdown_summary(summary, output_dir), encoding="utf-8"
    )

    print("Non-frozen postprocessing behavior comparison")
    print(f"- source_candidates: {summary['source_candidate_count']}")
    print(f"- postprocessed_candidates: {summary['postprocessed_candidate_count']}")
    print(f"- candidate_count_delta: {summary['candidate_count_delta']}")
    print(f"- bbox_area_ratio_postprocessed_vs_source: {summary['bbox_area_ratio_postprocessed_vs_source']}")
    print(f"- output_dir: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
