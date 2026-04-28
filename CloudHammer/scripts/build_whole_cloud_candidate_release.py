from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.infer.candidate_release import attach_release_decisions, summarize_release_rows
from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs" / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428"
DEFAULT_POLICY_MANIFEST = DEFAULT_RUN / "policy_v1" / "candidates_with_policy.jsonl"
DEFAULT_REVIEW_LOG = (
    ROOT
    / "data"
    / "whole_cloud_candidate_reviews"
    / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428.audit80.review.jsonl"
)
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "release_v1"


def load_latest_reviews(paths: list[Path]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for path in paths:
        if not path.exists():
            continue
        for row in read_jsonl(path):
            candidate_id = str(row.get("candidate_id") or "")
            if candidate_id:
                latest[candidate_id] = row
    return latest


def merge_reviews(policy_rows: list[dict[str, Any]], reviews: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    merged_rows: list[dict[str, Any]] = []
    for row in policy_rows:
        merged = dict(row)
        review = reviews.get(str(row.get("candidate_id") or ""))
        if review is not None:
            merged["review_status"] = review.get("status")
            merged["review_status_label"] = review.get("status_label")
            merged["reviewed_at"] = review.get("reviewed_at")
            merged["reviewer"] = review.get("reviewer")
        else:
            merged["review_status"] = None
            merged["review_status_label"] = None
            merged["reviewed_at"] = None
            merged["reviewer"] = None
        merged_rows.append(merged)
    return merged_rows


def rows_for_action(rows: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("release_action") == action]


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Whole Cloud Candidate Release",
        "",
        f"Policy manifest: `{summary['policy_manifest']}`",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Totals",
        "",
        f"- total candidates: `{summary['total_candidates']}`",
        f"- release candidates: `{summary['release_candidates']}`",
        f"- needs split review: `{summary['needs_split_review']}`",
        f"- normal review queue: `{summary['review_candidates']}`",
        f"- low-priority review queue: `{summary['low_priority_review']}`",
        f"- quarantined candidates: `{summary['quarantined_candidates']}`",
        "",
        "## Release Actions",
        "",
        "| Action | Count |",
        "| --- | ---: |",
    ]
    for action, count in sorted(summary["by_release_action"].items()):
        lines.append(f"| `{action}` | `{count}` |")

    lines.extend(["", "## Release Reasons", "", "| Reason | Count |", "| --- | ---: |"])
    for reason, count in sorted(summary["by_release_reason"].items()):
        lines.append(f"| `{reason}` | `{count}` |")

    lines.extend(["", "## Review Status", "", "| Status | Count |", "| --- | ---: |"])
    for status, count in sorted(summary["by_review_status"].items()):
        lines.append(f"| `{status}` | `{count}` |")

    lines.extend(
        [
            "",
            "## Output Manifests",
            "",
            "- `all_candidates_with_release_decision.jsonl`: every policy candidate with review and release routing attached",
            "- `release_candidates.jsonl`: default export set",
            "- `release_human_accept_candidates.jsonl`: release candidates admitted by human accept",
            "- `release_policy_auto_candidates.jsonl`: release candidates admitted by policy auto route",
            "- `split_review_queue.jsonl`: candidates that need split/overmerge work",
            "- `review_queue.jsonl`: normal non-auto candidates for later human review",
            "- `low_priority_review_queue.jsonl`: low-confidence candidates held out by default",
            "- `likely_false_positive_quarantine.jsonl`: policy false-positive quarantine",
            "- `human_rejected_quarantine.jsonl`: reviewed false positive, partial, or uncertain candidates",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a whole-cloud candidate release and follow-up review queues.")
    parser.add_argument("--policy-manifest", type=Path, default=DEFAULT_POLICY_MANIFEST)
    parser.add_argument("--review-log", action="append", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    policy_manifest = args.policy_manifest.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    policy_rows = list(read_jsonl(policy_manifest))
    review_logs = args.review_log or [DEFAULT_REVIEW_LOG]
    reviews = load_latest_reviews([path.resolve() for path in review_logs])
    rows = attach_release_decisions(merge_reviews(policy_rows, reviews))

    release_rows = rows_for_action(rows, "release_candidate")
    split_rows = rows_for_action(rows, "needs_split_review")
    review_rows = rows_for_action(rows, "review_candidate")
    low_priority_rows = rows_for_action(rows, "low_priority_review")
    likely_fp_rows = rows_for_action(rows, "quarantine_likely_false_positive")
    human_rejected_rows = rows_for_action(rows, "quarantine_human_rejected")

    write_jsonl(output_dir / "all_candidates_with_release_decision.jsonl", rows)
    write_jsonl(output_dir / "release_candidates.jsonl", release_rows)
    write_jsonl(
        output_dir / "release_human_accept_candidates.jsonl",
        [row for row in release_rows if row.get("release_reason") == "human_accept"],
    )
    write_jsonl(
        output_dir / "release_policy_auto_candidates.jsonl",
        [row for row in release_rows if row.get("release_reason") == "policy_auto_deliverable_candidate"],
    )
    write_jsonl(output_dir / "split_review_queue.jsonl", split_rows)
    write_jsonl(output_dir / "review_queue.jsonl", review_rows)
    write_jsonl(output_dir / "low_priority_review_queue.jsonl", low_priority_rows)
    write_jsonl(output_dir / "likely_false_positive_quarantine.jsonl", likely_fp_rows)
    write_jsonl(output_dir / "human_rejected_quarantine.jsonl", human_rejected_rows)

    summary = summarize_release_rows(rows)
    summary.update(
        {
            "schema": "cloudhammer.whole_cloud_candidate_release.v1",
            "policy_manifest": str(policy_manifest),
            "review_logs": [str(path.resolve()) for path in review_logs if path.exists()],
            "output_dir": str(output_dir),
        }
    )
    write_json(output_dir / "release_summary.json", summary)
    write_markdown(summary, output_dir / "release_summary.md")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
