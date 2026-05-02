from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.contracts.detections import xyxy_to_xywh
from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs" / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428"
DEFAULT_MANIFEST = DEFAULT_RUN / "policy_v1" / "needs_split_review.jsonl"
DEFAULT_REVIEW_LOG = (
    ROOT
    / "data"
    / "whole_cloud_split_reviews"
    / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428.split_review.jsonl"
)
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "split_review_analysis"


def load_latest_reviews(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return latest
    for line_number, row in enumerate(read_jsonl(path), start=1):
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id:
            raise ValueError(f"Missing candidate_id in {path} line {line_number}")
        latest[candidate_id] = row
    return latest


def split_status(status: str | None) -> bool:
    return bool(status and (status.startswith("split_variant_") or status == "manual_split"))


def box_area(box: list[float] | tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = [float(value) for value in box]
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def union_box(boxes: list[list[float]]) -> list[float]:
    return [
        min(float(box[0]) for box in boxes),
        min(float(box[1]) for box in boxes),
        max(float(box[2]) for box in boxes),
        max(float(box[3]) for box in boxes),
    ]


def unique_sorted_ints(values: list[Any]) -> list[int]:
    output: set[int] = set()
    for value in values:
        if isinstance(value, list):
            output.update(unique_sorted_ints(value))
            continue
        try:
            output.add(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(output)


def repair_plan(marker_consistency: dict[str, Any] | None) -> tuple[set[int], dict[int, int], dict[int, str]]:
    if not isinstance(marker_consistency, dict):
        return set(), {}, {}

    drop_groups = {
        int(suspect["group_index"])
        for suspect in marker_consistency.get("drop_suspects") or []
        if suspect.get("group_index") is not None
    }
    merge_targets: dict[int, int] = {}
    merge_sources: dict[int, str] = {}
    for source_name, suspects in [
        ("auto_merge", marker_consistency.get("merge_suspects") or []),
        ("manual_resolved_merge", marker_consistency.get("resolved_ambiguous_merge_suspects") or []),
    ]:
        for suspect in suspects:
            if suspect.get("group_index") is None or suspect.get("merge_target_group") is None:
                continue
            source = int(suspect["group_index"])
            target = int(suspect["merge_target_group"])
            if source in drop_groups:
                continue
            merge_targets[source] = target
            merge_sources[source] = source_name
    return drop_groups, merge_targets, merge_sources


def merged_group_record(
    target_group: dict[str, Any],
    target_index: int,
    merged_source_groups: list[tuple[int, dict[str, Any]]],
) -> dict[str, Any]:
    groups = [(target_index, target_group), *merged_source_groups]
    boxes = [
        [float(value) for value in group["bbox_page_xyxy"]]
        for _, group in groups
        if isinstance(group.get("bbox_page_xyxy"), list) and len(group["bbox_page_xyxy"]) == 4
    ]
    merged = dict(target_group)
    merged_box = union_box(boxes)
    member_indexes = unique_sorted_ints([group.get("member_indexes") or [] for _, group in groups])
    member_count = sum(int(group.get("member_count") or 0) for _, group in groups) or len(member_indexes) or None
    confidences = [
        float(group.get("confidence"))
        for _, group in groups
        if group.get("confidence") is not None
    ]
    source_area = 0.0
    for _, group in groups:
        fill_ratio = group.get("fill_ratio")
        box = group.get("bbox_page_xyxy")
        if fill_ratio is None or not isinstance(box, list) or len(box) != 4:
            continue
        source_area += box_area(box) * float(fill_ratio)
    merged_area = box_area(merged_box)
    merged["bbox_page_xyxy"] = merged_box
    merged["bbox_page_xywh"] = xyxy_to_xywh(tuple(merged_box))
    merged["member_indexes"] = member_indexes
    if member_count is not None:
        merged["member_count"] = member_count
    if confidences:
        merged["confidence"] = max(confidences)
    if source_area > 0.0 and merged_area > 0.0:
        merged["fill_ratio"] = source_area / merged_area
    merged["split_source_group_indexes"] = [index for index, _ in groups]
    merged["split_repair_action"] = "merged_repair_groups"
    return merged


def repaired_proposal_groups(row: dict[str, Any], proposal: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    groups = proposal.get("groups") or []
    indexed_groups = [
        (index, group)
        for index, group in enumerate(groups, start=1)
        if isinstance(group, dict)
    ]
    drop_groups, merge_targets, merge_sources = repair_plan(row.get("split_marker_consistency"))
    by_index = {index: group for index, group in indexed_groups}
    merged_sources_by_target: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for source_index, target_index in merge_targets.items():
        if source_index not in by_index or target_index not in by_index:
            continue
        if source_index in drop_groups:
            continue
        merged_sources_by_target.setdefault(target_index, []).append((source_index, by_index[source_index]))

    repaired: list[tuple[int, dict[str, Any]]] = []
    for index, group in indexed_groups:
        if index in drop_groups:
            continue
        if index in merge_targets:
            continue
        merged_sources = merged_sources_by_target.get(index, [])
        if merged_sources:
            repaired_group = merged_group_record(group, index, merged_sources)
            repaired_group["split_repair_sources"] = [
                merge_sources.get(source_index, "merge")
                for source_index, _ in merged_sources
            ]
            repaired.append((index, repaired_group))
            continue
        repaired_group = dict(group)
        repaired_group.setdefault("split_source_group_indexes", [index])
        repaired_group.setdefault("split_repair_action", "kept")
        repaired.append((index, repaired_group))
    return repaired


def merge_manifest_reviews(manifest_path: Path, review_log_path: Path) -> list[dict[str, Any]]:
    latest = load_latest_reviews(review_log_path)
    rows: list[dict[str, Any]] = []
    for candidate in read_jsonl(manifest_path):
        candidate_id = str(candidate.get("candidate_id") or "")
        review = latest.get(candidate_id)
        merged = dict(candidate)
        merged["split_review_status"] = None if review is None else review.get("status")
        merged["split_review_status_detail"] = None if review is None else review.get("status_detail")
        merged["split_review_flags"] = None if review is None else review.get("review_flags")
        merged["split_reviewed_at"] = None if review is None else review.get("reviewed_at")
        merged["split_reviewer"] = None if review is None else review.get("reviewer")
        merged["selected_split_proposal"] = None if review is None else review.get("proposal")
        merged["split_proposal_summaries"] = None if review is None else review.get("proposal_summaries")
        merged["split_marker_consistency"] = None if review is None else review.get("marker_consistency")
        merged["split_repair_overrides"] = None if review is None else review.get("repair_overrides")
        rows.append(merged)
    return rows


def selected_split_group_rows(reviewed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in reviewed_rows:
        status = row.get("split_review_status")
        if not split_status(str(status) if status is not None else None):
            continue
        proposal = row.get("selected_split_proposal") or {}
        groups = repaired_proposal_groups(row, proposal)
        for output_group_index, (source_group_index, group) in enumerate(groups, start=1):
            bbox_xyxy = group.get("bbox_page_xyxy")
            if not isinstance(bbox_xyxy, list) or len(bbox_xyxy) != 4:
                continue
            split_group_id = f"{row['candidate_id']}_split_{output_group_index:03d}"
            rows.append(
                {
                    "schema": "cloudhammer.reviewed_whole_cloud_split_group.v1",
                    "split_group_id": split_group_id,
                    "parent_candidate_id": row["candidate_id"],
                    "split_review_status": status,
                    "split_review_status_detail": row.get("split_review_status_detail"),
                    "split_review_flags": row.get("split_review_flags"),
                    "split_repair_overrides": row.get("split_repair_overrides"),
                    "split_variant_index": proposal.get("variant_index"),
                    "split_variant_name": proposal.get("name"),
                    "split_variant_group_count": proposal.get("group_count"),
                    "split_group_index": output_group_index,
                    "split_source_group_index": source_group_index,
                    "split_source_group_indexes": group.get("split_source_group_indexes") or [source_group_index],
                    "split_repair_action": group.get("split_repair_action") or "kept",
                    "split_repair_sources": group.get("split_repair_sources"),
                    "pdf_path": row.get("pdf_path"),
                    "pdf_stem": row.get("pdf_stem"),
                    "page_number": row.get("page_number"),
                    "render_path": row.get("render_path"),
                    "parent_crop_image_path": row.get("crop_image_path"),
                    "bbox_page_xyxy": [float(value) for value in bbox_xyxy],
                    "bbox_page_xywh": group.get("bbox_page_xywh") or xyxy_to_xywh(tuple(float(value) for value in bbox_xyxy)),
                    "confidence": group.get("confidence"),
                    "member_count": group.get("member_count"),
                    "member_indexes": group.get("member_indexes"),
                    "group_fill_ratio": group.get("fill_ratio"),
                    "parent_bbox_page_xyxy": row.get("bbox_page_xyxy"),
                    "parent_member_count": row.get("member_count"),
                    "parent_group_fill_ratio": row.get("group_fill_ratio"),
                    "parent_whole_cloud_confidence": row.get("whole_cloud_confidence"),
                    "parent_marker_consistency": row.get("split_marker_consistency"),
                    "source_mode": "reviewed_split_group",
                }
            )
    return rows


def summarize(reviewed_rows: list[dict[str, Any]], split_group_rows: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    reviewed = [row for row in reviewed_rows if row.get("split_review_status")]
    status_counts = Counter(str(row.get("split_review_status") or "unreviewed") for row in reviewed_rows)
    selected = [row for row in reviewed if split_status(str(row.get("split_review_status")))]
    proposal_names = Counter(
        str((row.get("selected_split_proposal") or {}).get("name") or "none")
        for row in selected
    )
    proposal_indexes = Counter(
        str((row.get("selected_split_proposal") or {}).get("variant_index") or "none")
        for row in selected
    )
    selected_group_counts = Counter(
        str((row.get("selected_split_proposal") or {}).get("group_count") or "none")
        for row in selected
    )
    return {
        "schema": "cloudhammer.whole_cloud_split_review_analysis.v1",
        "output_dir": str(output_dir),
        "total_candidates": len(reviewed_rows),
        "reviewed_candidates": len(reviewed),
        "unreviewed_candidates": len(reviewed_rows) - len(reviewed),
        "status_counts": dict(status_counts),
        "selected_split_candidates": len(selected),
        "selected_split_groups": len(split_group_rows),
        "selected_proposal_names": dict(proposal_names),
        "selected_proposal_indexes": dict(proposal_indexes),
        "selected_group_counts": dict(selected_group_counts),
    }


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Whole Cloud Split Review Analysis",
        "",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Totals",
        "",
        f"- total split-risk candidates: `{summary['total_candidates']}`",
        f"- reviewed candidates: `{summary['reviewed_candidates']}`",
        f"- selected split candidates: `{summary['selected_split_candidates']}`",
        f"- selected split groups emitted: `{summary['selected_split_groups']}`",
        "",
        "## Status Counts",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]
    for status, count in sorted(summary["status_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{status}` | `{count}` |")

    lines.extend(["", "## Selected Proposal Names", "", "| Proposal | Count |", "| --- | ---: |"])
    for name, count in sorted(summary["selected_proposal_names"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{name}` | `{count}` |")

    lines.extend(["", "## Selected Group Counts", "", "| Groups Produced | Candidate Count |", "| --- | ---: |"])
    for group_count, count in sorted(summary["selected_group_counts"].items(), key=lambda item: (int(item[0]) if item[0].isdigit() else 999, item[0])):
        lines.append(f"| `{group_count}` | `{count}` |")

    lines.extend(
        [
            "",
            "## Output Manifests",
            "",
            "- `reviewed_split_candidates.jsonl`: split-risk candidates with latest split review attached",
            "- `selected_split_groups.jsonl`: one row per selected split group",
            "- `selected_split_candidates.jsonl`: candidates where a numbered split proposal was selected",
            "- `still_overmerged_candidates.jsonl`: candidates where no proposal was good enough",
            "- `current_ok_candidates.jsonl`: candidates where the current group was good as-is",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze whole-cloud split-review feedback.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--review-log", type=Path, default=DEFAULT_REVIEW_LOG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    review_log_path = args.review_log.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    reviewed_rows = merge_manifest_reviews(manifest_path, review_log_path)
    split_group_rows = selected_split_group_rows(reviewed_rows)
    selected_rows = [row for row in reviewed_rows if split_status(str(row.get("split_review_status")))]
    still_overmerged_rows = [row for row in reviewed_rows if row.get("split_review_status") == "still_overmerged"]
    current_ok_rows = [row for row in reviewed_rows if row.get("split_review_status") == "current_ok"]

    write_jsonl(output_dir / "reviewed_split_candidates.jsonl", reviewed_rows)
    write_jsonl(output_dir / "selected_split_candidates.jsonl", selected_rows)
    write_jsonl(output_dir / "selected_split_groups.jsonl", split_group_rows)
    write_jsonl(output_dir / "still_overmerged_candidates.jsonl", still_overmerged_rows)
    write_jsonl(output_dir / "current_ok_candidates.jsonl", current_ok_rows)

    summary = summarize(reviewed_rows, split_group_rows, output_dir)
    summary["manifest_path"] = str(manifest_path)
    summary["review_log_path"] = str(review_log_path)
    write_json(output_dir / "split_review_summary.json", summary)
    write_markdown(summary, output_dir / "split_review_summary.md")

    print(f"wrote {output_dir / 'split_review_summary.md'}")
    print(
        "reviewed={reviewed}/{total} selected_splits={selected} split_groups={groups} statuses={statuses}".format(
            reviewed=summary["reviewed_candidates"],
            total=summary["total_candidates"],
            selected=summary["selected_split_candidates"],
            groups=summary["selected_split_groups"],
            statuses=summary["status_counts"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
