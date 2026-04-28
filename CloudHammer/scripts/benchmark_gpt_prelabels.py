from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl, write_json


ROOT = Path(__file__).resolve().parents[1]
IOU_THRESHOLDS = (0.25, 0.40, 0.50)
CONFIDENCE_CUTOFFS = (0.0, 0.80, 0.90, 0.95)


def yolo_to_xyxy(values: list[float]) -> tuple[float, float, float, float]:
    cx, cy, width, height = values
    return (
        max(0.0, cx - width / 2.0),
        max(0.0, cy - height / 2.0),
        min(1.0, cx + width / 2.0),
        min(1.0, cy + height / 2.0),
    )


def read_yolo_boxes(path: Path) -> list[tuple[float, float, float, float]]:
    if not path.exists():
        return []
    boxes = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid YOLO label line {line_number} in {path}: {line}")
        boxes.append(yolo_to_xyxy([float(value) for value in parts[1:]]))
    return boxes


def gpt_box_records(
    roi_id: str,
    api_label_dir: Path,
    prediction_metadata: dict[str, dict],
) -> list[dict]:
    boxes = read_yolo_boxes(api_label_dir / f"{roi_id}.txt")
    metadata_boxes = (prediction_metadata.get(roi_id) or {}).get("accepted_boxes") or []
    records = []
    for index, box in enumerate(boxes):
        metadata = metadata_boxes[index] if index < len(metadata_boxes) else {}
        records.append(
            {
                "box": box,
                "confidence": float(metadata.get("confidence", 0.0)),
                "visual_type": str(metadata.get("visual_type") or "unknown"),
            }
        )
    return records


def box_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def greedy_match(
    predicted: list[dict],
    truth: list[tuple[float, float, float, float]],
    threshold: float,
) -> tuple[int, int, int, list[tuple[float, int]], list[int]]:
    candidates = []
    for pred_index, pred_box in enumerate(predicted):
        for truth_index, truth_box in enumerate(truth):
            iou = box_iou(pred_box["box"], truth_box)
            if iou >= threshold:
                candidates.append((iou, pred_index, truth_index))
    candidates.sort(reverse=True)

    matched_pred = set()
    matched_truth = set()
    matched_ious = []
    for iou, pred_index, truth_index in candidates:
        if pred_index in matched_pred or truth_index in matched_truth:
            continue
        matched_pred.add(pred_index)
        matched_truth.add(truth_index)
        matched_ious.append((iou, pred_index))

    tp = len(matched_pred)
    fp = len(predicted) - tp
    fn = len(truth) - tp
    unmatched_pred = [index for index in range(len(predicted)) if index not in matched_pred]
    return tp, fp, fn, matched_ious, unmatched_pred


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def load_prediction_metadata(path: Path) -> dict[str, dict]:
    by_id = {}
    for row in read_jsonl(path):
        roi_id = row.get("cloud_roi_id")
        if roi_id:
            by_id[roi_id] = row
    return by_id


def prediction_stats(row: dict | None) -> float | None:
    if not row:
        return None
    boxes = row.get("accepted_boxes") or []
    confidences = [float(box.get("confidence", 0.0)) for box in boxes]
    return max(confidences) if confidences else None


def summarize_box_counts(counts: dict[str, int | float]) -> dict[str, float | int]:
    tp = int(counts["tp"])
    fp = int(counts["fp"])
    fn = int(counts["fn"])
    precision = safe_rate(tp, tp + fp)
    recall = safe_rate(tp, tp + fn)
    f1 = safe_rate(2 * precision * recall, precision + recall)
    mean_iou = safe_rate(float(counts.get("iou_sum", 0.0)), tp)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "mean_matched_iou": mean_iou,
    }


def confidence_bucket(max_confidence: float | None) -> str:
    if max_confidence is None:
        return "no_gpt_boxes"
    if max_confidence >= 0.95:
        return ">=0.95"
    if max_confidence >= 0.90:
        return "0.90-0.95"
    if max_confidence >= 0.80:
        return "0.80-0.90"
    return "<0.80"


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark GPT cloud prelabels against human-reviewed labels.")
    parser.add_argument(
        "--reviewed-manifest",
        type=Path,
        default=ROOT / "data" / "manifests" / "reviewed_batch_001_priority_train.jsonl",
    )
    parser.add_argument(
        "--api-label-dir",
        type=Path,
        default=ROOT / "data" / "api_cloud_labels_unreviewed",
    )
    parser.add_argument(
        "--predictions-jsonl",
        type=Path,
        default=ROOT / "data" / "api_cloud_predictions_unreviewed" / "predictions.jsonl",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "gpt_prelabel_benchmark")
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    prediction_metadata = load_prediction_metadata(args.predictions_jsonl)

    image_counts = Counter()
    box_counts = {threshold: Counter() for threshold in IOU_THRESHOLDS}
    cutoff_counts = {
        threshold: {cutoff: Counter() for cutoff in CONFIDENCE_CUTOFFS} for threshold in IOU_THRESHOLDS
    }
    cutoff_image_counts = {cutoff: Counter() for cutoff in CONFIDENCE_CUTOFFS}
    visual_type_counts = {threshold: defaultdict(Counter) for threshold in IOU_THRESHOLDS}
    rows_out = []

    for row in read_jsonl(args.reviewed_manifest):
        roi_id = row["cloud_roi_id"]
        truth_label = Path(row["label_path"])
        truth_boxes = read_yolo_boxes(truth_label)
        gpt_boxes = gpt_box_records(roi_id, args.api_label_dir, prediction_metadata)
        max_confidence = prediction_stats(prediction_metadata.get(roi_id))
        bucket = confidence_bucket(max_confidence)

        truth_has = bool(truth_boxes)
        gpt_has = bool(gpt_boxes)
        if truth_has and gpt_has:
            image_result = "tp_cloud"
        elif not truth_has and not gpt_has:
            image_result = "tn_no_cloud"
        elif not truth_has and gpt_has:
            image_result = "fp_cloud"
        else:
            image_result = "fn_cloud"
        image_counts[image_result] += 1

        per_threshold = {}
        for threshold in IOU_THRESHOLDS:
            tp, fp, fn, matched_ious, unmatched_pred = greedy_match(gpt_boxes, truth_boxes, threshold)
            box_counts[threshold].update(
                {"tp": tp, "fp": fp, "fn": fn, "iou_sum": sum(iou for iou, _ in matched_ious)}
            )
            for _, pred_index in matched_ious:
                visual_type_counts[threshold][gpt_boxes[pred_index]["visual_type"]].update({"tp": 1})
            for pred_index in unmatched_pred:
                visual_type_counts[threshold][gpt_boxes[pred_index]["visual_type"]].update({"fp": 1})
            visual_type_counts[threshold]["unattributed_truth_misses"].update({"fn": fn})
            per_threshold[str(threshold)] = {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "mean_matched_iou": sum(iou for iou, _ in matched_ious) / len(matched_ious) if matched_ious else 0.0,
            }

            for cutoff in CONFIDENCE_CUTOFFS:
                filtered = [record for record in gpt_boxes if record["confidence"] >= cutoff]
                c_tp, c_fp, c_fn, c_ious, _ = greedy_match(filtered, truth_boxes, threshold)
                cutoff_counts[threshold][cutoff].update(
                    {"tp": c_tp, "fp": c_fp, "fn": c_fn, "iou_sum": sum(iou for iou, _ in c_ious)}
                )

        for cutoff in CONFIDENCE_CUTOFFS:
            filtered_has = any(record["confidence"] >= cutoff for record in gpt_boxes)
            if truth_has and filtered_has:
                cutoff_image_counts[cutoff]["tp_cloud"] += 1
            elif not truth_has and not filtered_has:
                cutoff_image_counts[cutoff]["tn_no_cloud"] += 1
            elif not truth_has and filtered_has:
                cutoff_image_counts[cutoff]["fp_cloud"] += 1
            else:
                cutoff_image_counts[cutoff]["fn_cloud"] += 1

        rows_out.append(
            {
                "cloud_roi_id": roi_id,
                "split": row.get("split", ""),
                "visual_type": row.get("visual_type", ""),
                "reason_for_selection": row.get("reason_for_selection", ""),
                "truth_box_count": len(truth_boxes),
                "gpt_box_count": len(gpt_boxes),
                "gpt_max_confidence": "" if max_confidence is None else f"{max_confidence:.4f}",
                "confidence_bucket": bucket,
                "image_result": image_result,
                "iou_025_tp": per_threshold["0.25"]["tp"],
                "iou_025_fp": per_threshold["0.25"]["fp"],
                "iou_025_fn": per_threshold["0.25"]["fn"],
                "iou_040_tp": per_threshold["0.4"]["tp"],
                "iou_040_fp": per_threshold["0.4"]["fp"],
                "iou_040_fn": per_threshold["0.4"]["fn"],
                "iou_050_tp": per_threshold["0.5"]["tp"],
                "iou_050_fp": per_threshold["0.5"]["fp"],
                "iou_050_fn": per_threshold["0.5"]["fn"],
            }
        )

    total_images = sum(image_counts.values())
    image_tp = image_counts["tp_cloud"]
    image_tn = image_counts["tn_no_cloud"]
    image_fp = image_counts["fp_cloud"]
    image_fn = image_counts["fn_cloud"]
    image_summary = {
        "total": total_images,
        "tp_cloud": image_tp,
        "tn_no_cloud": image_tn,
        "fp_cloud": image_fp,
        "fn_cloud": image_fn,
        "accuracy": safe_rate(image_tp + image_tn, total_images),
        "precision": safe_rate(image_tp, image_tp + image_fp),
        "recall": safe_rate(image_tp, image_tp + image_fn),
    }

    summary = {
        "reviewed_manifest": str(args.reviewed_manifest),
        "api_label_dir": str(args.api_label_dir),
        "predictions_jsonl": str(args.predictions_jsonl),
        "image_level": image_summary,
        "box_level": {str(k): summarize_box_counts(v) for k, v in box_counts.items()},
        "box_level_by_confidence_cutoff": {
            str(threshold): {str(cutoff): summarize_box_counts(counts) for cutoff, counts in cutoffs.items()}
            for threshold, cutoffs in cutoff_counts.items()
        },
        "image_level_by_confidence_cutoff": {
            str(cutoff): {
                "total": sum(counts.values()),
                "tp_cloud": counts["tp_cloud"],
                "tn_no_cloud": counts["tn_no_cloud"],
                "fp_cloud": counts["fp_cloud"],
                "fn_cloud": counts["fn_cloud"],
                "accuracy": safe_rate(counts["tp_cloud"] + counts["tn_no_cloud"], sum(counts.values())),
                "precision": safe_rate(counts["tp_cloud"], counts["tp_cloud"] + counts["fp_cloud"]),
                "recall": safe_rate(counts["tp_cloud"], counts["tp_cloud"] + counts["fn_cloud"]),
            }
            for cutoff, counts in cutoff_image_counts.items()
        },
        "by_gpt_visual_type": {
            str(threshold): {visual_type: summarize_box_counts(counts) for visual_type, counts in counts_by_type.items()}
            for threshold, counts_by_type in visual_type_counts.items()
        },
    }

    write_json(output_dir / "summary.json", summary)
    csv_path = output_dir / "per_image.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_out[0].keys()) if rows_out else [])
        writer.writeheader()
        writer.writerows(rows_out)

    md_lines = [
        "# GPT Prelabel Benchmark",
        "",
        "Compared raw GPT prelabels against the human-reviewed 204-image truth set.",
        "",
        "## Image Level",
        "",
        f"- Images: `{image_summary['total']}`",
        f"- Accuracy: `{image_summary['accuracy']:.3f}`",
        f"- Cloud precision: `{image_summary['precision']:.3f}`",
        f"- Cloud recall: `{image_summary['recall']:.3f}`",
        f"- False cloud images: `{image_summary['fp_cloud']}`",
        f"- Missed cloud images: `{image_summary['fn_cloud']}`",
        "",
        "## Box Level",
        "",
    ]
    for threshold in IOU_THRESHOLDS:
        metrics = summary["box_level"][str(threshold)]
        md_lines.extend(
            [
                f"### IoU {threshold:.2f}",
                "",
                f"- TP boxes: `{metrics['tp']}`",
                f"- FP boxes: `{metrics['fp']}`",
                f"- FN boxes: `{metrics['fn']}`",
                f"- Precision: `{metrics['precision']:.3f}`",
                f"- Recall: `{metrics['recall']:.3f}`",
                f"- F1: `{metrics['f1']:.3f}`",
                f"- Mean matched IoU: `{metrics['mean_matched_iou']:.3f}`",
                "",
            ]
        )
    md_lines.extend(["## Confidence Cutoffs", ""])
    for cutoff in CONFIDENCE_CUTOFFS:
        image_metrics = summary["image_level_by_confidence_cutoff"][str(cutoff)]
        box_metrics = summary["box_level_by_confidence_cutoff"]["0.4"][str(cutoff)]
        label = "all GPT boxes" if cutoff == 0.0 else f"GPT boxes >= {cutoff:.2f}"
        md_lines.extend(
            [
                f"### {label}",
                "",
                f"- Image precision: `{image_metrics['precision']:.3f}`",
                f"- Image recall: `{image_metrics['recall']:.3f}`",
                f"- Box precision at IoU 0.40: `{box_metrics['precision']:.3f}`",
                f"- Box recall at IoU 0.40: `{box_metrics['recall']:.3f}`",
                f"- Box F1 at IoU 0.40: `{box_metrics['f1']:.3f}`",
                "",
            ]
        )
    md_lines.extend(
        [
            "## Files",
            "",
            "- `summary.json`",
            "- `per_image.csv`",
            "",
        ]
    )
    (output_dir / "README.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(json.dumps(summary["image_level"], indent=2))
    print(json.dumps(summary["box_level"], indent=2))
    print(f"Wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
