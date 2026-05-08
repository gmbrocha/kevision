from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
DEFAULT_PACKET_DIR = (
    V2_ROOT / "outputs" / "baseline_human_audited_mismatch_review_20260504" / "overlay_packet"
)

APPROVED_ERROR_BUCKETS = {
    "actual_false_positive",
    "duplicate_prediction_on_real_cloud",
    "localization_matching_issue",
    "truth_box_needs_recheck",
    "truth_box_too_tight",
    "truth_box_too_loose",
    "prediction_fragment_on_real_cloud",
    "not_actionable_matching_artifact",
    "marker_neighborhood_no_cloud_regions",
    "historical_or_nonmatching_revision_marker_context",
    "isolated_arcs_and_scallop_fragments",
    "fixture_circles_and_symbol_circles",
    "glyph_text_arcs",
    "crossing_line_x_patterns",
    "index_table_x_marks",
    "dense_linework_near_valid_clouds",
    "thick_dark_cloud_false_positive_context",
    "thin_light_cloud_low_contrast_miss",
    "no_cloud_dense_dark_linework",
    "no_cloud_door_swing_arc_false_positive_trap",
    "mixed_cloud_with_dense_false_positive_regions",
    "overmerged_grouping",
    "split_fragment",
    "localization_too_loose",
    "localization_too_tight",
    "truth_needs_recheck",
    "other",
}

REVIEW_STATUSES = {
    "unreviewed",
    "resolved",
    "truth_followup",
    "tooling_or_matching_artifact",
    "not_actionable",
}

LEGACY_STATUS_MAP = {
    "bucketed": "resolved",
    "truth_needs_recheck": "truth_followup",
    "needs_second_look": "tooling_or_matching_artifact",
}

MATCHING_ARTIFACT_BUCKETS = {
    "duplicate_prediction_on_real_cloud",
    "localization_matching_issue",
    "truth_box_needs_recheck",
    "truth_box_too_tight",
    "truth_box_too_loose",
    "prediction_fragment_on_real_cloud",
    "not_actionable_matching_artifact",
    "truth_needs_recheck",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def compact_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Mismatch Review Summary",
        "",
        f"Review log: `{summary['review_log']}`",
        f"Rows: `{summary['rows']}`",
        f"Reviewed rows: `{summary['reviewed_rows']}`",
        f"Unreviewed rows: `{summary['unreviewed_rows']}`",
        "",
        "## By Status",
        "",
    ]
    for key, count in summary["by_status"].items():
        lines.append(f"- `{key}`: `{count}`")
    lines.extend(["", "## By Human Error Bucket", ""])
    if summary["by_human_error_bucket"]:
        for key, count in summary["by_human_error_bucket"].items():
            lines.append(f"- `{key}`: `{count}`")
    else:
        lines.append("- No reviewed rows with buckets yet.")
    lines.extend(["", "## By Bucket Category", ""])
    if summary["by_bucket_category"]:
        for key, count in summary["by_bucket_category"].items():
            lines.append(f"- `{key}`: `{count}`")
    else:
        lines.append("- No reviewed rows with buckets yet.")
    lines.extend(["", "## By Mode And Bucket", ""])
    if summary["by_mode_and_bucket"]:
        for mode, buckets in summary["by_mode_and_bucket"].items():
            lines.append(f"### `{mode}`")
            for bucket, count in buckets.items():
                lines.append(f"- `{bucket}`: `{count}`")
            lines.append("")
    else:
        lines.append("- No reviewed rows with buckets yet.")
        lines.append("")
    lines.extend(["## By Mismatch Type And Bucket Category", ""])
    if summary["by_mismatch_type_and_bucket_category"]:
        for mismatch_type, buckets in summary["by_mismatch_type_and_bucket_category"].items():
            lines.append(f"### `{mismatch_type}`")
            for bucket, count in buckets.items():
                lines.append(f"- `{bucket}`: `{count}`")
            lines.append("")
    else:
        lines.append("- No reviewed rows with buckets yet.")
        lines.append("")
    if summary["deprecated_status_rows"]:
        lines.extend(["## Deprecated Status Rows", ""])
        for item in summary["deprecated_status_rows"]:
            lines.append(
                f"- `{item['review_item_id']}`: `{item['raw_status']}` mapped to `{item['mapped_status']}`"
            )
        lines.append("")
    if summary["invalid_rows"]:
        lines.extend(["## Invalid Rows", ""])
        for item in summary["invalid_rows"]:
            lines.append(
                f"- `{item['review_item_id']}`: {item['reason']} "
                f"(bucket=`{item.get('human_error_bucket', '')}`, status=`{item.get('human_review_status', '')}`)"
            )
        lines.append("")
    lines.extend(
        [
            "## Next Action",
            "",
            "Use this summary only after the review log has human error buckets. Do not use",
            "frozen eval-page crops as training data, hard negatives, threshold-tuning",
            "inputs, GPT relabel inputs, or synthetic backgrounds.",
        ]
    )
    return "\n".join(lines) + "\n"


def summarize(rows: list[dict[str, str]], review_log: Path) -> dict[str, Any]:
    by_status: Counter[str] = Counter()
    by_bucket: Counter[str] = Counter()
    by_bucket_category: Counter[str] = Counter()
    by_mode_and_bucket: dict[str, Counter[str]] = defaultdict(Counter)
    by_mismatch_type_and_bucket_category: dict[str, Counter[str]] = defaultdict(Counter)
    invalid_rows: list[dict[str, str]] = []
    deprecated_status_rows: list[dict[str, str]] = []
    reviewed_rows = 0

    for row in rows:
        raw_status = (row.get("human_review_status") or "unreviewed").strip()
        status = LEGACY_STATUS_MAP.get(raw_status, raw_status)
        bucket = (row.get("human_error_bucket") or "").strip()
        mode = (row.get("eval_mode") or "unknown").strip()
        mismatch_type = (row.get("mismatch_type") or "unknown").strip()
        if raw_status != status:
            deprecated_status_rows.append(
                {**row, "raw_status": raw_status, "mapped_status": status}
            )
        by_status[status] += 1
        if status not in REVIEW_STATUSES:
            invalid_rows.append({**row, "reason": "unknown human_review_status"})
        if status != "unreviewed":
            reviewed_rows += 1
            if not bucket:
                invalid_rows.append({**row, "reason": "reviewed row missing human_error_bucket"})
            elif bucket not in APPROVED_ERROR_BUCKETS:
                invalid_rows.append({**row, "reason": "unknown human_error_bucket"})
            else:
                category = "matching_or_scoring_artifact" if bucket in MATCHING_ARTIFACT_BUCKETS else "true_model_error_or_visual_family"
                by_bucket[bucket] += 1
                by_mode_and_bucket[mode][bucket] += 1
                by_bucket_category[category] += 1
                by_mismatch_type_and_bucket_category[mismatch_type][category] += 1

    return {
        "schema": "cloudhammer_v2.mismatch_review_summary.v1",
        "review_log": str(review_log),
        "rows": len(rows),
        "reviewed_rows": reviewed_rows,
        "unreviewed_rows": len(rows) - reviewed_rows,
        "by_status": compact_counter(by_status),
        "by_human_error_bucket": compact_counter(by_bucket),
        "by_bucket_category": compact_counter(by_bucket_category),
        "by_mode_and_bucket": {
            mode: compact_counter(counter) for mode, counter in sorted(by_mode_and_bucket.items())
        },
        "by_mismatch_type_and_bucket_category": {
            mismatch_type: compact_counter(counter)
            for mismatch_type, counter in sorted(by_mismatch_type_and_bucket_category.items())
        },
        "deprecated_status_rows": [
            {
                "review_item_id": row.get("review_item_id", ""),
                "raw_status": row.get("raw_status", ""),
                "mapped_status": row.get("mapped_status", ""),
            }
            for row in deprecated_status_rows
        ],
        "invalid_rows": [
            {
                "review_item_id": row.get("review_item_id", ""),
                "reason": row.get("reason", ""),
                "human_error_bucket": row.get("human_error_bucket", ""),
                "human_review_status": row.get("human_review_status", ""),
            }
            for row in invalid_rows
        ],
    }


def console_summary(summary: dict[str, Any]) -> str:
    lines = [
        "Mismatch review summary",
        f"- review_log: {summary['review_log']}",
        f"- rows: {summary['rows']}",
        f"- reviewed_rows: {summary['reviewed_rows']}",
        f"- unreviewed_rows: {summary['unreviewed_rows']}",
        f"- by_status: {summary['by_status']}",
        f"- by_bucket_category: {summary['by_bucket_category']}",
        f"- invalid_rows: {len(summary['invalid_rows'])}",
        f"- deprecated_status_rows: {len(summary['deprecated_status_rows'])}",
    ]
    if summary.get("markdown_summary"):
        lines.append(f"- markdown_summary: {summary['markdown_summary']}")
    if summary.get("json_summary"):
        lines.append(f"- json_summary: {summary['json_summary']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize and summarize a mismatch review log.")
    parser.add_argument(
        "--manifest-csv",
        type=Path,
        default=DEFAULT_PACKET_DIR / "mismatch_manifest.csv",
        help="Read-only packet CSV generated by build_mismatch_review_packet.py.",
    )
    parser.add_argument(
        "--review-log",
        type=Path,
        default=DEFAULT_PACKET_DIR / "mismatch_review_log.csv",
        help="Editable review log CSV.",
    )
    parser.add_argument(
        "--summary-dir",
        type=Path,
        default=None,
        help="Directory for summary JSON/Markdown. Defaults to the review log directory.",
    )
    parser.add_argument("--init-review-log", action="store_true")
    args = parser.parse_args()

    if args.init_review_log:
        if args.review_log.exists():
            raise SystemExit(f"review log already exists: {args.review_log}")
        source_rows = read_csv(args.manifest_csv)
        fieldnames = list(source_rows[0].keys()) if source_rows else []
        write_csv(args.review_log, source_rows, fieldnames)

    rows = read_csv(args.review_log)
    summary = summarize(rows, args.review_log)
    summary_dir = args.summary_dir or args.review_log.parent
    summary_stem = (
        "mismatch_review_summary"
        if args.review_log.name == "mismatch_review_log.csv"
        else f"{args.review_log.stem}_summary"
    )
    summary_json = summary_dir / f"{summary_stem}.json"
    summary_md = summary_dir / f"{summary_stem}.md"
    summary["json_summary"] = str(summary_json)
    summary["markdown_summary"] = str(summary_md)
    write_json(summary_json, summary)
    summary_md.write_text(markdown(summary), encoding="utf-8")
    print(console_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
