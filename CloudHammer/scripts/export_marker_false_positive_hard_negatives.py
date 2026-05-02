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
DEFAULT_REVIEW_ANALYSIS = DEFAULT_RUN / "marker_fp_review_analysis"
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "hard_negatives_v1"


def hard_negative_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "cloudhammer.whole_cloud_hard_negative.v1",
        "candidate_id": row.get("candidate_id"),
        "hard_negative_source": "marker_fp_review",
        "false_positive_reason": row.get("false_positive_reason") or "generic_false_positive",
        "false_positive_reason_label": row.get("false_positive_reason_label") or "False Positive",
        "review_tags": row.get("review_tags") or ["hard_negative", "generic_false_positive"],
        "crop_image_path": row.get("crop_image_path"),
        "pdf_path": row.get("pdf_path"),
        "pdf_stem": row.get("pdf_stem"),
        "page_number": row.get("page_number"),
        "bbox_page_xyxy": row.get("bbox_page_xyxy"),
        "crop_box_page_xyxy": row.get("crop_box_page_xyxy"),
        "whole_cloud_confidence": row.get("whole_cloud_confidence"),
        "member_count": row.get("member_count"),
        "marker_anchor_bucket": row.get("marker_anchor_bucket"),
        "target_digit": row.get("target_digit"),
        "matching_page_marker_count": row.get("matching_page_marker_count"),
        "matching_markers_in_crop": row.get("matching_markers_in_crop"),
        "nearest_matching_marker_bbox_distance": row.get("nearest_matching_marker_bbox_distance"),
        "nearest_matching_marker_center_distance": row.get("nearest_matching_marker_center_distance"),
        "reviewed_at": row.get("reviewed_at"),
        "reviewer": row.get("reviewer"),
    }


def summarize(rows: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    return {
        "schema": "cloudhammer.whole_cloud_hard_negatives.v1",
        "output_dir": str(output_dir),
        "hard_negatives": len(rows),
        "by_false_positive_reason": dict(Counter(str(row.get("false_positive_reason")) for row in rows)),
        "by_marker_anchor_bucket": dict(Counter(str(row.get("marker_anchor_bucket")) for row in rows)),
        "by_pdf_stem": dict(Counter(str(row.get("pdf_stem")) for row in rows)),
    }


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Marker False-Positive Hard Negatives",
        "",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Totals",
        "",
        f"- hard negatives: `{summary['hard_negatives']}`",
        "",
        "## By Reason",
        "",
        "| Reason | Count |",
        "| --- | ---: |",
    ]
    for reason, count in sorted(summary["by_false_positive_reason"].items()):
        lines.append(f"| `{reason}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `hard_negative_candidates.jsonl`: reviewed marker-FP false positives normalized for training/filter work",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export reviewed marker false positives as hard negatives.")
    parser.add_argument("--review-analysis-dir", type=Path, default=DEFAULT_REVIEW_ANALYSIS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    review_analysis_dir = args.review_analysis_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    false_positive_rows = list(read_jsonl(review_analysis_dir / "false_positive_candidates.jsonl"))
    hard_negatives = [hard_negative_row(row) for row in false_positive_rows]
    write_jsonl(output_dir / "hard_negative_candidates.jsonl", hard_negatives)
    summary = summarize(hard_negatives, output_dir)
    summary["review_analysis_dir"] = str(review_analysis_dir)
    write_json(output_dir / "hard_negative_summary.json", summary)
    write_markdown(summary, output_dir / "hard_negative_summary.md")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
