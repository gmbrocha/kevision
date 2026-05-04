from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs" / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428"
DEFAULT_MANIFEST = DEFAULT_RUN / "whole_cloud_candidates_manifest.jsonl"
DEFAULT_REVIEW_LOG = (
    ROOT
    / "data"
    / "whole_cloud_candidate_reviews"
    / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428.review.jsonl"
)
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "review_analysis"


def load_latest_reviews(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for line_number, row in enumerate(read_jsonl(path), start=1):
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id:
            raise ValueError(f"Missing candidate_id in {path} line {line_number}")
        latest[candidate_id] = row
    return latest


def merge_manifest_reviews(manifest_path: Path, review_log_path: Path) -> list[dict[str, Any]]:
    reviews = load_latest_reviews(review_log_path)
    rows: list[dict[str, Any]] = []
    for candidate in read_jsonl(manifest_path):
        candidate_id = str(candidate.get("candidate_id") or "")
        review = reviews.get(candidate_id)
        merged = dict(candidate)
        merged["review_status"] = None if review is None else review.get("status")
        merged["reviewed_at"] = None if review is None else review.get("reviewed_at")
        merged["reviewer"] = None if review is None else review.get("reviewer")
        merged["false_positive_reason"] = None if review is None else review.get("false_positive_reason")
        merged["false_positive_reason_label"] = None if review is None else review.get("false_positive_reason_label")
        merged["accept_reason"] = None if review is None else review.get("accept_reason")
        merged["accept_reason_label"] = None if review is None else review.get("accept_reason_label")
        merged["review_tags"] = None if review is None else review.get("review_tags")
        merged["review_note"] = None if review is None else review.get("review_note")
        rows.append(merged)
    return rows


def status_counter(rows: list[dict[str, Any]]) -> Counter:
    return Counter(str(row.get("review_status") or "unreviewed") for row in rows)


def grouped_status(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    buckets: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        buckets[str(row.get(field))][str(row.get("review_status") or "unreviewed")] += 1
    summary = []
    for key, counts in buckets.items():
        total = sum(counts.values())
        accepted = counts.get("accept", 0)
        summary.append(
            {
                field: key,
                "total": total,
                "accept": accepted,
                "non_accept": total - accepted,
                "accept_rate": 0.0 if total == 0 else accepted / total,
                "statuses": dict(counts),
            }
        )
    return sorted(summary, key=lambda row: (-int(row["total"]), str(row[field])))


def confidence_bins(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bins = [(0.0, 0.50), (0.50, 0.65), (0.65, 0.80), (0.80, 0.90), (0.90, 0.97), (0.97, 1.01)]
    output = []
    for lo, hi in bins:
        bucket_rows = [row for row in rows if lo <= float(row.get("whole_cloud_confidence") or 0.0) < hi]
        if not bucket_rows:
            continue
        counts = status_counter(bucket_rows)
        total = len(bucket_rows)
        accepted = counts.get("accept", 0)
        output.append(
            {
                "range": f"{lo:.2f}-{hi:.2f}",
                "min": lo,
                "max": hi,
                "total": total,
                "accept": accepted,
                "non_accept": total - accepted,
                "accept_rate": accepted / total,
                "statuses": dict(counts),
            }
        )
    return output


def reviewed_subset(rows: list[dict[str, Any]], status: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("review_status") == status]


def candidate_area_stats(rows: list[dict[str, Any]]) -> dict[str, float]:
    areas = [float(row.get("bbox_area") or 0.0) for row in rows]
    crop_areas = [float(row.get("crop_area") or 0.0) for row in rows]
    confidences = [float(row.get("whole_cloud_confidence") or 0.0) for row in rows]
    return {
        "median_bbox_area": statistics.median(areas) if areas else 0.0,
        "median_crop_area": statistics.median(crop_areas) if crop_areas else 0.0,
        "median_confidence": statistics.median(confidences) if confidences else 0.0,
    }


def summarize(rows: list[dict[str, Any]], manifest_path: Path, review_log_path: Path, output_dir: Path) -> dict[str, Any]:
    reviewed = [row for row in rows if row.get("review_status")]
    accepted = reviewed_subset(rows, "accept")
    rejected = [row for row in reviewed if row.get("review_status") != "accept"]
    summary = {
        "schema": "cloudhammer.whole_cloud_candidate_review_analysis.v1",
        "manifest_path": str(manifest_path),
        "review_log_path": str(review_log_path),
        "output_dir": str(output_dir),
        "total_candidates": len(rows),
        "reviewed_candidates": len(reviewed),
        "unreviewed_candidates": len(rows) - len(reviewed),
        "status_counts": dict(status_counter(rows)),
        "accepted_candidates": len(accepted),
        "rejected_or_issue_candidates": len(rejected),
        "overall_accept_rate": 0.0 if not reviewed else len(accepted) / len(reviewed),
        "by_size_bucket": grouped_status(reviewed, "size_bucket"),
        "by_confidence_tier": grouped_status(reviewed, "confidence_tier"),
        "by_member_count": grouped_status(reviewed, "member_count"),
        "by_pdf_stem": grouped_status(reviewed, "pdf_stem"),
        "by_false_positive_reason": grouped_status(reviewed_subset(rows, "false_positive"), "false_positive_reason"),
        "by_accept_reason": grouped_status(reviewed_subset(rows, "accept"), "accept_reason"),
        "confidence_bins": confidence_bins(reviewed),
        "area_stats_all": candidate_area_stats(reviewed),
        "area_stats_accept": candidate_area_stats(accepted),
        "area_stats_rejected_or_issue": candidate_area_stats(rejected),
    }
    return summary


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Whole Cloud Candidate Review Analysis",
        "",
        f"Manifest: `{summary['manifest_path']}`",
        f"Review log: `{summary['review_log_path']}`",
        "",
        "## Totals",
        "",
        f"- total candidates: `{summary['total_candidates']}`",
        f"- reviewed candidates: `{summary['reviewed_candidates']}`",
        f"- accepted candidates: `{summary['accepted_candidates']}`",
        f"- rejected/issue candidates: `{summary['rejected_or_issue_candidates']}`",
        f"- overall accept rate: `{summary['overall_accept_rate']:.1%}`",
        "",
        "## Status Counts",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]
    for status, count in sorted(summary["status_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| `{status}` | `{count}` |")

    def add_group(title: str, rows: list[dict[str, Any]], key: str) -> None:
        lines.extend(["", f"## {title}", "", f"| {key} | Total | Accept | Non-Accept | Accept Rate | Statuses |", "| --- | ---: | ---: | ---: | ---: | --- |"])
        for row in rows:
            lines.append(
                f"| `{row[key]}` | `{row['total']}` | `{row['accept']}` | `{row['non_accept']}` | "
                f"`{row['accept_rate']:.1%}` | `{json.dumps(row['statuses'], sort_keys=True)}` |"
            )

    add_group("By Confidence Tier", summary["by_confidence_tier"], "confidence_tier")
    add_group("By Size Bucket", summary["by_size_bucket"], "size_bucket")
    add_group("By Member Count", summary["by_member_count"], "member_count")
    add_group("By False Positive Reason", summary["by_false_positive_reason"], "false_positive_reason")
    add_group("By Accept Reason", summary["by_accept_reason"], "accept_reason")

    lines.extend(["", "## Confidence Bins", "", "| Confidence | Total | Accept | Non-Accept | Accept Rate | Statuses |", "| --- | ---: | ---: | ---: | ---: | --- |"])
    for row in summary["confidence_bins"]:
        lines.append(
            f"| `{row['range']}` | `{row['total']}` | `{row['accept']}` | `{row['non_accept']}` | "
            f"`{row['accept_rate']:.1%}` | `{json.dumps(row['statuses'], sort_keys=True)}` |"
        )

    lines.extend(
        [
            "",
            "## Output Manifests",
            "",
            "- `reviewed_candidates.jsonl`: all candidates with latest review status attached",
            "- `accepted_candidates.jsonl`: candidates marked `accept`",
            "- `false_positive_candidates.jsonl`: candidates marked `false_positive`",
            "- `overmerged_candidates.jsonl`: candidates marked `overmerged`",
            "- `partial_candidates.jsonl`: candidates marked `partial`",
            "- `issue_candidates.jsonl`: all non-accept reviewed candidates",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze whole-cloud candidate review feedback.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--review-log", type=Path, default=DEFAULT_REVIEW_LOG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    review_log_path = args.review_log.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = merge_manifest_reviews(manifest_path, review_log_path)
    summary = summarize(rows, manifest_path, review_log_path, output_dir)

    write_jsonl(output_dir / "reviewed_candidates.jsonl", rows)
    write_jsonl(output_dir / "accepted_candidates.jsonl", reviewed_subset(rows, "accept"))
    write_jsonl(
        output_dir / "tagged_accepted_candidates.jsonl",
        [row for row in reviewed_subset(rows, "accept") if row.get("accept_reason")],
    )
    write_jsonl(output_dir / "false_positive_candidates.jsonl", reviewed_subset(rows, "false_positive"))
    write_jsonl(
        output_dir / "tagged_false_positive_candidates.jsonl",
        [row for row in reviewed_subset(rows, "false_positive") if row.get("false_positive_reason")],
    )
    write_jsonl(output_dir / "overmerged_candidates.jsonl", reviewed_subset(rows, "overmerged"))
    write_jsonl(output_dir / "partial_candidates.jsonl", reviewed_subset(rows, "partial"))
    write_jsonl(output_dir / "issue_candidates.jsonl", [row for row in rows if row.get("review_status") and row.get("review_status") != "accept"])

    write_json(output_dir / "review_analysis_summary.json", summary)
    write_markdown(summary, output_dir / "review_analysis_summary.md")

    print(f"wrote {output_dir / 'review_analysis_summary.md'}")
    print(
        "reviewed={reviewed}/{total} accept={accept} issues={issues} statuses={statuses}".format(
            reviewed=summary["reviewed_candidates"],
            total=summary["total_candidates"],
            accept=summary["accepted_candidates"],
            issues=summary["rejected_or_issue_candidates"],
            statuses=summary["status_counts"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
