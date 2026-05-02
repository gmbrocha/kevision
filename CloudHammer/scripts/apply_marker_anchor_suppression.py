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
DEFAULT_MARKER_ANCHORS = DEFAULT_RUN / "marker_anchor_analysis_v1" / "candidates_with_marker_anchors.jsonl"
DEFAULT_MARKER_FP_REVIEWED = DEFAULT_RUN / "marker_fp_review_analysis" / "reviewed_candidates.jsonl"
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "marker_anchor_suppression_v1"


def rows_by_candidate(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row["candidate_id"]): row
        for row in rows
        if row.get("candidate_id")
    }


def confidence(row: dict[str, Any]) -> float:
    return float(row.get("whole_cloud_confidence") or row.get("confidence") or 0.0)


def reviewed_status(row: dict[str, Any]) -> str | None:
    status = row.get("marker_fp_review_status")
    return None if status is None else str(status)


def suppression_decision(row: dict[str, Any], confidence_threshold: float) -> dict[str, Any]:
    status = reviewed_status(row)
    if status == "false_positive":
        return {
            "marker_anchor_suppressed": True,
            "marker_anchor_suppression_reason": "reviewed_marker_fp_false_positive",
            "marker_anchor_suppression_reviewed": True,
        }
    if status in {"accept", "partial", "overmerged", "uncertain"}:
        return {
            "marker_anchor_suppressed": False,
            "marker_anchor_suppression_reason": f"reviewed_{status}_protected",
            "marker_anchor_suppression_reviewed": True,
        }
    if bool(row.get("is_split_replacement")):
        return {
            "marker_anchor_suppressed": False,
            "marker_anchor_suppression_reason": "split_replacement_protected",
            "marker_anchor_suppression_reviewed": False,
        }
    if row.get("correction_source") != "original_candidate":
        return {
            "marker_anchor_suppressed": False,
            "marker_anchor_suppression_reason": "non_original_candidate_protected",
            "marker_anchor_suppression_reviewed": False,
        }
    if (
        row.get("marker_anchor_bucket") == "no_near_matching_marker"
        and confidence(row) < confidence_threshold
    ):
        return {
            "marker_anchor_suppressed": True,
            "marker_anchor_suppression_reason": f"no_near_matching_marker_confidence_lt_{confidence_threshold:.2f}",
            "marker_anchor_suppression_reviewed": False,
        }
    return {
        "marker_anchor_suppressed": False,
        "marker_anchor_suppression_reason": "not_suppression_candidate",
        "marker_anchor_suppression_reviewed": False,
    }


def merge_reviews(anchor_rows: list[dict[str, Any]], reviewed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reviews = rows_by_candidate(reviewed_rows)
    output: list[dict[str, Any]] = []
    for row in anchor_rows:
        enriched = dict(row)
        review = reviews.get(str(row.get("candidate_id") or ""))
        enriched["marker_fp_review_status"] = None if review is None else review.get("review_status")
        enriched["marker_fp_false_positive_reason"] = None if review is None else review.get("false_positive_reason")
        enriched["marker_fp_review_tags"] = None if review is None else review.get("review_tags")
        enriched["marker_fp_reviewed_at"] = None if review is None else review.get("reviewed_at")
        output.append(enriched)
    return output


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Marker Anchor Suppression",
        "",
        f"Marker anchors: `{summary['marker_anchor_manifest']}`",
        f"Marker-FP reviews: `{summary['marker_fp_reviewed_manifest']}`",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Rule",
        "",
        f"- reviewed marker-FP `false_positive` rows are suppressed",
        f"- reviewed `accept`/`partial` rows are protected",
        f"- unreviewed original candidates suppress only when bucket is `no_near_matching_marker` and confidence < `{summary['params']['confidence_threshold']:.2f}`",
        "",
        "## Totals",
        "",
        f"- input candidates: `{summary['input_candidates']}`",
        f"- retained candidates: `{summary['retained_candidates']}`",
        f"- suppressed candidates: `{summary['suppressed_candidates']}`",
        f"- reviewed suppressions: `{summary['reviewed_suppressions']}`",
        f"- rule suppressions: `{summary['rule_suppressions']}`",
        "",
        "## Suppression Reasons",
        "",
        "| Reason | Count |",
        "| --- | ---: |",
    ]
    for reason, count in sorted(summary["suppression_reasons"].items()):
        lines.append(f"| `{reason}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `candidates_with_marker_anchor_suppression.jsonl`: all candidates with suppression decision fields",
            "- `marker_anchor_suppressed_candidates.jsonl`: candidates removed by reviewed or calibrated marker-anchor suppression",
            "- `marker_anchor_retained_candidates.jsonl`: candidates retained after suppression",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize(
    rows: list[dict[str, Any]],
    marker_anchor_manifest: Path,
    marker_fp_reviewed_manifest: Path,
    output_dir: Path,
    confidence_threshold: float,
) -> dict[str, Any]:
    suppressed = [row for row in rows if row.get("marker_anchor_suppressed")]
    return {
        "schema": "cloudhammer.marker_anchor_suppression.v1",
        "marker_anchor_manifest": str(marker_anchor_manifest),
        "marker_fp_reviewed_manifest": str(marker_fp_reviewed_manifest),
        "output_dir": str(output_dir),
        "params": {"confidence_threshold": confidence_threshold},
        "input_candidates": len(rows),
        "retained_candidates": len(rows) - len(suppressed),
        "suppressed_candidates": len(suppressed),
        "reviewed_suppressions": sum(1 for row in suppressed if row.get("marker_anchor_suppression_reviewed")),
        "rule_suppressions": sum(1 for row in suppressed if not row.get("marker_anchor_suppression_reviewed")),
        "suppression_reasons": dict(Counter(str(row.get("marker_anchor_suppression_reason")) for row in suppressed)),
        "suppressed_by_false_positive_reason": dict(
            Counter(str(row.get("marker_fp_false_positive_reason") or "unreviewed_rule") for row in suppressed)
        ),
        "suppressed_by_marker_anchor_bucket": dict(Counter(str(row.get("marker_anchor_bucket")) for row in suppressed)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply calibrated marker-anchor suppression to corrected candidates.")
    parser.add_argument("--marker-anchors", type=Path, default=DEFAULT_MARKER_ANCHORS)
    parser.add_argument("--marker-fp-reviewed", type=Path, default=DEFAULT_MARKER_FP_REVIEWED)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--confidence-threshold", type=float, default=0.45)
    args = parser.parse_args()

    marker_anchor_manifest = args.marker_anchors.resolve()
    marker_fp_reviewed_manifest = args.marker_fp_reviewed.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    anchor_rows = list(read_jsonl(marker_anchor_manifest))
    reviewed_rows = list(read_jsonl(marker_fp_reviewed_manifest))
    rows = []
    for row in merge_reviews(anchor_rows, reviewed_rows):
        enriched = dict(row)
        enriched.update(suppression_decision(enriched, args.confidence_threshold))
        rows.append(enriched)
    suppressed = [row for row in rows if row.get("marker_anchor_suppressed")]
    retained = [row for row in rows if not row.get("marker_anchor_suppressed")]

    write_jsonl(output_dir / "candidates_with_marker_anchor_suppression.jsonl", rows)
    write_jsonl(output_dir / "marker_anchor_suppressed_candidates.jsonl", suppressed)
    write_jsonl(output_dir / "marker_anchor_retained_candidates.jsonl", retained)
    summary = summarize(rows, marker_anchor_manifest, marker_fp_reviewed_manifest, output_dir, args.confidence_threshold)
    write_json(output_dir / "marker_anchor_suppression_summary.json", summary)
    write_markdown(summary, output_dir / "marker_anchor_suppression_summary.md")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
