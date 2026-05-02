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
DEFAULT_INPUT = DEFAULT_RUN / "marker_anchor_suppression_v1" / "marker_anchor_retained_candidates.jsonl"
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "marker_anchor_retained_review_v1"


RISK_BUCKETS = {
    "marker_in_crop_not_touching",
    "marker_near_candidate",
    "no_near_matching_marker",
}


def confidence(row: dict[str, Any]) -> float:
    return float(row.get("whole_cloud_confidence") or row.get("confidence") or 0.0)


def review_priority(row: dict[str, Any]) -> tuple[int, float, int, str]:
    bucket = str(row.get("marker_anchor_bucket") or "")
    bucket_rank = {
        "no_near_matching_marker": 0,
        "marker_in_crop_not_touching": 1,
        "marker_near_candidate": 2,
    }.get(bucket, 9)
    return (
        bucket_rank,
        confidence(row),
        int(row.get("member_count") or 0),
        str(row.get("candidate_id") or ""),
    )


def needs_retained_review(row: dict[str, Any]) -> bool:
    if row.get("marker_fp_review_status") in {"accept", "partial", "false_positive"}:
        return False
    if row.get("is_split_replacement"):
        return False
    bucket = str(row.get("marker_anchor_bucket") or "")
    if bucket not in RISK_BUCKETS:
        return False
    if bucket == "no_near_matching_marker":
        return confidence(row) >= 0.45
    return True


def summarize(rows: list[dict[str, Any]], queue: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    return {
        "schema": "cloudhammer.marker_anchor_retained_review_queue.v1",
        "output_dir": str(output_dir),
        "retained_candidates": len(rows),
        "review_queue_candidates": len(queue),
        "by_marker_anchor_bucket_all": dict(Counter(str(row.get("marker_anchor_bucket")) for row in rows)),
        "by_marker_anchor_bucket_queue": dict(Counter(str(row.get("marker_anchor_bucket")) for row in queue)),
        "by_size_bucket_queue": dict(Counter(str(row.get("size_bucket")) for row in queue)),
        "by_confidence_tier_queue": dict(Counter(str(row.get("confidence_tier")) for row in queue)),
    }


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Marker Anchor Retained Review Queue",
        "",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Totals",
        "",
        f"- retained candidates: `{summary['retained_candidates']}`",
        f"- review queue candidates: `{summary['review_queue_candidates']}`",
        "",
        "## Queue By Marker Bucket",
        "",
        "| Bucket | Count |",
        "| --- | ---: |",
    ]
    for bucket, count in sorted(summary["by_marker_anchor_bucket_queue"].items()):
        lines.append(f"| `{bucket}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `review_queue.jsonl`: retained marker-risk candidates for targeted review",
            "- `review_queue_summary.json`: machine-readable summary",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build targeted review queue from retained marker-anchor risk buckets.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = list(read_jsonl(input_path))
    queue = sorted([row for row in rows if needs_retained_review(row)], key=review_priority)
    write_jsonl(output_dir / "review_queue.jsonl", queue)
    summary = summarize(rows, queue, output_dir)
    summary["input_manifest"] = str(input_path)
    write_json(output_dir / "review_queue_summary.json", summary)
    write_markdown(summary, output_dir / "review_queue_summary.md")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
