from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs" / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428"
DEFAULT_BASE_ANALYSIS_DIR = DEFAULT_RUN / "split_review_analysis"
DEFAULT_RESCUE_ANALYSIS_DIR = DEFAULT_BASE_ANALYSIS_DIR / "still_overmerged_rescue_analysis"
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "split_review_analysis_with_rescue"


def rows_by_candidate(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate_id = str(row.get("candidate_id") or row.get("parent_candidate_id") or "")
        if candidate_id:
            output[candidate_id] = row
    return output


def parent_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(row.get("parent_candidate_id") or row.get("candidate_id") or "")
        for row in rows
        if row.get("parent_candidate_id") or row.get("candidate_id")
    }


def read_rows(path: Path) -> list[dict[str, Any]]:
    return list(read_jsonl(path))


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Split Review Analysis With Rescue",
        "",
        f"Base analysis: `{summary['base_analysis_dir']}`",
        f"Rescue analysis: `{summary['rescue_analysis_dir']}`",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Totals",
        "",
        f"- base selected split groups: `{summary['base_selected_split_groups']}`",
        f"- rescue selected split groups: `{summary['rescue_selected_split_groups']}`",
        f"- combined selected split groups: `{summary['combined_selected_split_groups']}`",
        f"- base still-overmerged parents: `{summary['base_still_overmerged']}`",
        f"- rescued parent candidates: `{summary['rescued_parent_candidates']}`",
        f"- remaining still-overmerged parents: `{summary['remaining_still_overmerged']}`",
        "",
        "## Status Counts",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]
    for status, count in sorted(summary["status_counts"].items()):
        lines.append(f"| `{status}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Output Manifests",
            "",
            "- `reviewed_split_candidates.jsonl`: base reviewed rows with rescued parents replaced by rescue reviews",
            "- `selected_split_candidates.jsonl`: base selected rows plus rescue selected rows",
            "- `selected_split_groups.jsonl`: base selected groups plus repaired rescue selected groups",
            "- `still_overmerged_candidates.jsonl`: base still-overmerged rows minus rescued parents",
            "- `current_ok_candidates.jsonl`: base current-ok rows unchanged",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply still-overmerged rescue split reviews to a base split analysis.")
    parser.add_argument("--base-analysis-dir", type=Path, default=DEFAULT_BASE_ANALYSIS_DIR)
    parser.add_argument("--rescue-analysis-dir", type=Path, default=DEFAULT_RESCUE_ANALYSIS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    base_dir = args.base_analysis_dir.resolve()
    rescue_dir = args.rescue_analysis_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    base_reviewed = read_rows(base_dir / "reviewed_split_candidates.jsonl")
    base_selected_candidates = read_rows(base_dir / "selected_split_candidates.jsonl")
    base_selected_groups = read_rows(base_dir / "selected_split_groups.jsonl")
    base_still_overmerged = read_rows(base_dir / "still_overmerged_candidates.jsonl")
    base_current_ok = read_rows(base_dir / "current_ok_candidates.jsonl")

    rescue_reviewed = read_rows(rescue_dir / "reviewed_split_candidates.jsonl")
    rescue_selected_candidates = read_rows(rescue_dir / "selected_split_candidates.jsonl")
    rescue_selected_groups = read_rows(rescue_dir / "selected_split_groups.jsonl")

    rescued_ids = parent_ids(rescue_selected_groups) | {
        str(row.get("candidate_id"))
        for row in rescue_selected_candidates
        if row.get("candidate_id")
    }

    rescue_reviewed_by_id = rows_by_candidate(rescue_reviewed)
    reviewed: list[dict[str, Any]] = []
    seen_reviewed: set[str] = set()
    for row in base_reviewed:
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id in rescue_reviewed_by_id:
            reviewed.append(rescue_reviewed_by_id[candidate_id])
            seen_reviewed.add(candidate_id)
        else:
            reviewed.append(row)
    for candidate_id, row in rescue_reviewed_by_id.items():
        if candidate_id not in seen_reviewed:
            reviewed.append(row)

    selected_candidates = [
        row
        for row in base_selected_candidates
        if str(row.get("candidate_id") or "") not in rescued_ids
    ] + rescue_selected_candidates
    selected_groups = [
        row
        for row in base_selected_groups
        if str(row.get("parent_candidate_id") or "") not in rescued_ids
    ] + rescue_selected_groups
    still_overmerged = [
        row
        for row in base_still_overmerged
        if str(row.get("candidate_id") or "") not in rescued_ids
    ]

    write_jsonl(output_dir / "reviewed_split_candidates.jsonl", reviewed)
    write_jsonl(output_dir / "selected_split_candidates.jsonl", selected_candidates)
    write_jsonl(output_dir / "selected_split_groups.jsonl", selected_groups)
    write_jsonl(output_dir / "still_overmerged_candidates.jsonl", still_overmerged)
    write_jsonl(output_dir / "current_ok_candidates.jsonl", base_current_ok)

    summary = {
        "schema": "cloudhammer.split_review_analysis_with_rescue.v1",
        "base_analysis_dir": str(base_dir),
        "rescue_analysis_dir": str(rescue_dir),
        "output_dir": str(output_dir),
        "base_selected_split_groups": len(base_selected_groups),
        "rescue_selected_split_groups": len(rescue_selected_groups),
        "combined_selected_split_groups": len(selected_groups),
        "base_still_overmerged": len(base_still_overmerged),
        "rescued_parent_candidates": len(rescued_ids),
        "remaining_still_overmerged": len(still_overmerged),
        "status_counts": dict(Counter(str(row.get("split_review_status") or "unreviewed") for row in reviewed)),
    }
    write_json(output_dir / "split_review_with_rescue_summary.json", summary)
    write_markdown(summary, output_dir / "split_review_with_rescue_summary.md")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
