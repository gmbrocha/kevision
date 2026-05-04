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

REVIEW_STATUSES = {"unreviewed", "bucketed", "needs_second_look", "truth_needs_recheck", "not_actionable"}


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
        lines.append("- No bucketed rows yet.")
    lines.extend(["", "## By Mode And Bucket", ""])
    if summary["by_mode_and_bucket"]:
        for mode, buckets in summary["by_mode_and_bucket"].items():
            lines.append(f"### `{mode}`")
            for bucket, count in buckets.items():
                lines.append(f"- `{bucket}`: `{count}`")
            lines.append("")
    else:
        lines.append("- No bucketed rows yet.")
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
            "Use this summary only after the review log is human-bucketed. Do not use",
            "frozen eval-page crops as training data, hard negatives, threshold-tuning",
            "inputs, GPT relabel inputs, or synthetic backgrounds.",
        ]
    )
    return "\n".join(lines) + "\n"


def summarize(rows: list[dict[str, str]], review_log: Path) -> dict[str, Any]:
    by_status: Counter[str] = Counter()
    by_bucket: Counter[str] = Counter()
    by_mode_and_bucket: dict[str, Counter[str]] = defaultdict(Counter)
    invalid_rows: list[dict[str, str]] = []
    reviewed_rows = 0

    for row in rows:
        status = (row.get("human_review_status") or "unreviewed").strip()
        bucket = (row.get("human_error_bucket") or "").strip()
        mode = (row.get("eval_mode") or "unknown").strip()
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
                by_bucket[bucket] += 1
                by_mode_and_bucket[mode][bucket] += 1

    return {
        "schema": "cloudhammer_v2.mismatch_review_summary.v1",
        "review_log": str(review_log),
        "rows": len(rows),
        "reviewed_rows": reviewed_rows,
        "unreviewed_rows": len(rows) - reviewed_rows,
        "by_status": compact_counter(by_status),
        "by_human_error_bucket": compact_counter(by_bucket),
        "by_mode_and_bucket": {
            mode: compact_counter(counter) for mode, counter in sorted(by_mode_and_bucket.items())
        },
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize and summarize a human mismatch review log.")
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
        help="Editable human review log CSV.",
    )
    parser.add_argument(
        "--summary-dir",
        type=Path,
        default=DEFAULT_PACKET_DIR,
        help="Directory for mismatch_review_summary.json/md.",
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
    write_json(args.summary_dir / "mismatch_review_summary.json", summary)
    (args.summary_dir / "mismatch_review_summary.md").write_text(markdown(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
