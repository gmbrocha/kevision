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
    return bool(status and status.startswith("split_variant_"))


def merge_manifest_reviews(manifest_path: Path, review_log_path: Path) -> list[dict[str, Any]]:
    latest = load_latest_reviews(review_log_path)
    rows: list[dict[str, Any]] = []
    for candidate in read_jsonl(manifest_path):
        candidate_id = str(candidate.get("candidate_id") or "")
        review = latest.get(candidate_id)
        merged = dict(candidate)
        merged["split_review_status"] = None if review is None else review.get("status")
        merged["split_reviewed_at"] = None if review is None else review.get("reviewed_at")
        merged["split_reviewer"] = None if review is None else review.get("reviewer")
        merged["selected_split_proposal"] = None if review is None else review.get("proposal")
        merged["split_proposal_summaries"] = None if review is None else review.get("proposal_summaries")
        rows.append(merged)
    return rows


def selected_split_group_rows(reviewed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in reviewed_rows:
        status = row.get("split_review_status")
        if not split_status(str(status) if status is not None else None):
            continue
        proposal = row.get("selected_split_proposal") or {}
        groups = proposal.get("groups") or []
        for group_index, group in enumerate(groups, start=1):
            bbox_xyxy = group.get("bbox_page_xyxy")
            if not isinstance(bbox_xyxy, list) or len(bbox_xyxy) != 4:
                continue
            split_group_id = f"{row['candidate_id']}_split_{group_index:03d}"
            rows.append(
                {
                    "schema": "cloudhammer.reviewed_whole_cloud_split_group.v1",
                    "split_group_id": split_group_id,
                    "parent_candidate_id": row["candidate_id"],
                    "split_review_status": status,
                    "split_variant_index": proposal.get("variant_index"),
                    "split_variant_name": proposal.get("name"),
                    "split_variant_group_count": proposal.get("group_count"),
                    "split_group_index": group_index,
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
