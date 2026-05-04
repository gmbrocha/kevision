from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
DEFAULT_PACKET_DIR = (
    V2_ROOT / "outputs" / "baseline_human_audited_mismatch_review_20260504" / "overlay_packet"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl_by_id(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[str(row["review_item_id"])] = row
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def parse_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_box(value: Any) -> list[float] | None:
    if isinstance(value, list) and len(value) == 4:
        return [float(item) for item in value]
    if not value:
        return None
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list) and len(parsed) == 4:
        return [float(item) for item in parsed]
    return None


def area(box: list[float] | None) -> float:
    if box is None:
        return 0.0
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def intersection(a: list[float] | None, b: list[float] | None) -> list[float] | None:
    if a is None or b is None:
        return None
    box = [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
    return box if box[2] > box[0] and box[3] > box[1] else None


def index_predictions(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    predictions = row.get("page_predictions")
    if isinstance(predictions, str):
        try:
            predictions = json.loads(predictions)
        except json.JSONDecodeError:
            predictions = []
    if not isinstance(predictions, list):
        return {}
    return {str(item.get("prediction_id") or ""): item for item in predictions if isinstance(item, dict)}


def box_for_prediction(row: dict[str, Any], prediction_id: str | None) -> list[float] | None:
    if not prediction_id:
        return None
    predictions = index_predictions(row)
    prediction = predictions.get(str(prediction_id))
    if prediction is None:
        return None
    return parse_box(prediction.get("box_xyxy"))


def current_adds_truth_coverage(row: dict[str, Any]) -> bool:
    truth_box = parse_box(row.get("truth_bbox_xyxy"))
    current_box = parse_box(row.get("bbox_xyxy"))
    matched_box = box_for_prediction(row, row.get("matched_elsewhere_prediction_id"))
    truth_area = area(truth_box)
    if truth_area <= 0.0 or current_box is None:
        return False
    current_truth = intersection(current_box, truth_box)
    if current_truth is None:
        return False
    already_covered = intersection(current_truth, matched_box)
    added_area = area(current_truth) - area(already_covered)
    return added_area / truth_area >= 0.04


def localization_bucket(row: dict[str, Any]) -> tuple[str, str]:
    pred_area = area(parse_box(row.get("bbox_xyxy")))
    truth_area = area(parse_box(row.get("truth_bbox_xyxy")))
    pred_box = parse_box(row.get("bbox_xyxy"))
    truth_box = parse_box(row.get("truth_bbox_xyxy"))
    width_ratio = 1.0
    height_ratio = 1.0
    if pred_box is not None and truth_box is not None:
        truth_w = max(1.0, truth_box[2] - truth_box[0])
        truth_h = max(1.0, truth_box[3] - truth_box[1])
        width_ratio = (pred_box[2] - pred_box[0]) / truth_w
        height_ratio = (pred_box[3] - pred_box[1]) / truth_h
    if pred_area > truth_area * 1.15 or width_ratio > 1.15 or height_ratio > 1.15:
        return (
            "localization_too_loose",
            "Prediction found the cloud but box is too loose and includes extra non-cloud area; review/tighten whole-cloud localization.",
        )
    if pred_area < truth_area * 0.85 or width_ratio < 0.85 or height_ratio < 0.85:
        return (
            "localization_too_tight",
            "Prediction found the cloud but covers only part of the truth; needs merge/whole-cloud coverage.",
        )
    return (
        "localization_matching_issue",
        "Prediction found the cloud but falls below the stricter localization review threshold; review box fit.",
    )


def suggest(row: dict[str, Any]) -> tuple[str, str, str, str]:
    mismatch_type = row.get("mismatch_type", "")
    nearest_iou = parse_float(row.get("nearest_truth_iou") or row.get("best_iou"))
    matched_elsewhere = parse_bool(row.get("matched_elsewhere"))

    if mismatch_type == "localization_low_iou":
        bucket, note = localization_bucket(row)
        return bucket, "resolved", note, "high"

    if mismatch_type == "false_negative":
        if matched_elsewhere:
            return (
                "overmerged_grouping",
                "resolved",
                "Truth cloud was missed because nearest prediction was matched to another truth; review as overmerge/grouping/localization issue.",
                "medium",
            )
        return (
            "split_fragment",
            "resolved",
            "Truth cloud exists but detections are split into fragments or poorly localized; no single whole-cloud prediction matched.",
            "high" if nearest_iou > 0.0 else "medium",
        )

    if mismatch_type == "false_positive":
        if matched_elsewhere:
            if current_adds_truth_coverage(row):
                return (
                    "prediction_fragment_on_real_cloud",
                    "resolved",
                    "Prediction is on a real cloud and appears to add useful coverage beyond the accepted prediction; review merge vs suppress.",
                    "medium",
                )
            return (
                "duplicate_prediction_on_real_cloud",
                "resolved",
                "Prediction is an extra box on a real cloud already claimed by another prediction; likely suppress/delete duplicate.",
                "medium",
            )
        if nearest_iou > 0.0:
            return (
                "prediction_fragment_on_real_cloud",
                "resolved",
                "Prediction overlaps a real truth cloud but was below scoring threshold; likely fragment/loose piece needing merge or better grouping.",
                "medium",
            )
        return (
            "actual_false_positive",
            "resolved",
            "Prediction has no nearby truth overlap; review visual FP family and adjust bucket if a more specific trap applies.",
            "low",
        )

    return "other", "resolved", "Unrecognized mismatch type; human review required.", "low"


def markdown(rows: list[dict[str, Any]], start_row: int, end_row: int, output_csv: Path) -> str:
    lines = [
        "# Mismatch Review Auto-Suggestions",
        "",
        f"Rows: `{start_row}`-`{end_row}`",
        f"Suggested CSV: `{output_csv}`",
        "",
        "These are review metadata suggestions only. They do not modify truth, eval manifests, predictions, model files, datasets, or training data.",
        "",
        "| row | mode | type | page | bucket | confidence | note |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if not row.get("auto_suggested"):
            continue
        note = str(row.get("auto_suggestion_note", "")).replace("|", "\\|")
        lines.append(
            f"| {row['review_row_number']} | `{row.get('eval_mode', '')}` | `{row.get('mismatch_type', '')}` | "
            f"`{row.get('source_page_key', '')}` | `{row.get('human_error_bucket', '')}` | "
            f"`{row.get('auto_suggestion_confidence', '')}` | {note} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest mismatch review metadata for a row range.")
    parser.add_argument("--review-log", type=Path, default=DEFAULT_PACKET_DIR / "mismatch_review_log.csv")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_PACKET_DIR / "mismatch_manifest.jsonl")
    parser.add_argument("--start-row", type=int, default=44)
    parser.add_argument("--end-row", type=int, default=77)
    parser.add_argument(
        "--output-review-log",
        type=Path,
        default=DEFAULT_PACKET_DIR / "mismatch_review_log.autosuggest_rows44_77.csv",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=DEFAULT_PACKET_DIR / "mismatch_review_autosuggest_rows44_77.md",
    )
    args = parser.parse_args()

    rows = read_csv(args.review_log)
    manifest_rows = read_jsonl_by_id(args.manifest)
    fieldnames = list(rows[0].keys()) if rows else []
    extra_fields = [
        "review_row_number",
        "auto_suggested",
        "auto_suggestion_confidence",
        "auto_suggestion_note",
    ]
    for field in extra_fields:
        if field not in fieldnames:
            fieldnames.append(field)

    suggested_count = 0
    for row_number, row in enumerate(rows, start=1):
        row["review_row_number"] = str(row_number)
        row["auto_suggested"] = ""
        row["auto_suggestion_confidence"] = ""
        row["auto_suggestion_note"] = ""
        if args.start_row <= row_number <= args.end_row:
            enriched_row = {**manifest_rows.get(str(row["review_item_id"]), {}), **row}
            bucket, status, note, confidence = suggest(enriched_row)
            row["human_error_bucket"] = bucket
            row["human_review_status"] = status
            row["human_notes"] = note
            row["auto_suggested"] = "yes"
            row["auto_suggestion_confidence"] = confidence
            row["auto_suggestion_note"] = note
            suggested_count += 1

    write_csv(args.output_review_log, rows, fieldnames)
    args.output_md.write_text(markdown(rows, args.start_row, args.end_row, args.output_review_log), encoding="utf-8")
    print(
        json.dumps(
            {
                "schema": "cloudhammer_v2.mismatch_review_autosuggest.v1",
                "review_log": str(args.review_log),
                "output_review_log": str(args.output_review_log),
                "output_md": str(args.output_md),
                "start_row": args.start_row,
                "end_row": args.end_row,
                "suggested_rows": suggested_count,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
