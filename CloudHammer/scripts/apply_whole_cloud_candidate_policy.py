from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.infer.candidate_policy import CandidatePolicyParams, classify_whole_cloud_candidate
from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT
    / "runs"
    / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428"
    / "review_analysis"
    / "reviewed_candidates.jsonl"
)
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "runs"
    / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428"
    / "policy_v1"
)


def status_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row.get("review_status") or "unreviewed") for row in rows)
    accepted = counts.get("accept", 0)
    total = len(rows)
    return {
        "total": total,
        "accepted": accepted,
        "issues": total - accepted - counts.get("unreviewed", 0),
        "accept_rate": 0.0 if total == 0 else accepted / total,
        "statuses": dict(counts),
    }


def summarize(rows: list[dict[str, Any]], params: CandidatePolicyParams, input_path: Path, output_dir: Path) -> dict[str, Any]:
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_bucket[str(row["policy_bucket"])].append(row)
    return {
        "schema": "cloudhammer.whole_cloud_candidate_policy.v1",
        "input_manifest": str(input_path),
        "output_dir": str(output_dir),
        "params": params.__dict__,
        "total_candidates": len(rows),
        "by_policy_bucket": {bucket: status_summary(bucket_rows) for bucket, bucket_rows in sorted(by_bucket.items())},
        "overall": status_summary(rows),
    }


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Whole Cloud Candidate Policy",
        "",
        f"Input manifest: `{summary['input_manifest']}`",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Buckets",
        "",
        "| Bucket | Total | Accepted | Issues | Accept Rate | Statuses |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for bucket, row in summary["by_policy_bucket"].items():
        lines.append(
            f"| `{bucket}` | `{row['total']}` | `{row['accepted']}` | `{row['issues']}` | "
            f"`{row['accept_rate']:.1%}` | `{json.dumps(row['statuses'], sort_keys=True)}` |"
        )
    lines.extend(
        [
            "",
            "## Output Manifests",
            "",
            "- `candidates_with_policy.jsonl`: all candidates with policy fields attached",
            "- `auto_deliverable_candidate.jsonl`: high-trust candidates",
            "- `likely_false_positive.jsonl`: low-trust candidates safe to drop from default deliverable queue",
            "- `needs_split_review.jsonl`: overmerge-risk candidates",
            "- `low_priority_review.jsonl`: low-confidence candidates that still need review if recall is paramount",
            "- `review_candidate.jsonl`: normal review queue",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply measured review policy buckets to whole-cloud candidates.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--false-positive-confidence", type=float, default=0.45)
    parser.add_argument("--low-priority-confidence", type=float, default=0.65)
    parser.add_argument("--auto-candidate-min-confidence", type=float, default=0.80)
    parser.add_argument("--auto-candidate-max-confidence", type=float, default=0.95)
    parser.add_argument("--auto-candidate-max-members", type=int, default=5)
    parser.add_argument("--min-auto-fill-ratio", type=float, default=0.15)
    parser.add_argument("--split-risk-min-members", type=int, default=9)
    parser.add_argument("--split-risk-low-fill-ratio", type=float, default=0.15)
    parser.add_argument("--split-risk-low-fill-min-members", type=int, default=2)
    args = parser.parse_args()

    params = CandidatePolicyParams(
        false_positive_confidence=args.false_positive_confidence,
        low_priority_confidence=args.low_priority_confidence,
        auto_candidate_min_confidence=args.auto_candidate_min_confidence,
        auto_candidate_max_confidence=args.auto_candidate_max_confidence,
        auto_candidate_max_members=args.auto_candidate_max_members,
        min_auto_fill_ratio=args.min_auto_fill_ratio,
        split_risk_min_members=args.split_risk_min_members,
        split_risk_low_fill_ratio=args.split_risk_low_fill_ratio,
        split_risk_low_fill_min_members=args.split_risk_low_fill_min_members,
    )

    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for row in read_jsonl(input_path):
        enriched = dict(row)
        enriched.update(classify_whole_cloud_candidate(row, params))
        rows.append(enriched)

    write_jsonl(output_dir / "candidates_with_policy.jsonl", rows)
    for bucket in sorted({str(row["policy_bucket"]) for row in rows}):
        write_jsonl(output_dir / f"{bucket}.jsonl", [row for row in rows if row["policy_bucket"] == bucket])

    summary = summarize(rows, params, input_path, output_dir)
    write_json(output_dir / "policy_summary.json", summary)
    write_markdown(summary, output_dir / "policy_summary.md")

    print(f"wrote {output_dir / 'policy_summary.md'}")
    for bucket, row in summary["by_policy_bucket"].items():
        print(f"{bucket}: total={row['total']} accept={row['accepted']} accept_rate={row['accept_rate']:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
