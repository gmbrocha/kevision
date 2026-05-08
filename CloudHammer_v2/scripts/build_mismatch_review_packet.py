from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
LEGACY_ROOT = PROJECT_ROOT / "CloudHammer"

APPROVED_ERROR_BUCKETS = [
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
]

REVIEW_STATUSES = [
    "unreviewed",
    "resolved",
    "truth_followup",
    "tooling_or_matching_artifact",
    "not_actionable",
]

CSV_FIELDNAMES = [
    "review_item_id",
    "source_page_key",
    "eval_mode",
    "mismatch_type",
    "truth_id",
    "prediction_id",
    "confidence",
    "iou_25",
    "best_iou",
    "nearest_truth_iou",
    "nearest_truth_id",
    "nearest_prediction_id",
    "nearest_prediction_iou",
    "matched_elsewhere",
    "matched_elsewhere_prediction_id",
    "matched_elsewhere_truth_id",
    "possible_duplicate_prediction",
    "mismatch_reason_raw",
    "human_error_bucket",
    "human_review_status",
    "human_notes",
    "overlay_path",
    "crop_path",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_csv_by_id(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["review_item_id"]: row for row in csv.DictReader(handle)}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_project_path(value: str | Path | None) -> Path:
    if value is None or str(value) == "":
        return Path("")
    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve()
    parts = candidate.parts
    for anchor, root in (("CloudHammer", LEGACY_ROOT), ("revision_sets", PROJECT_ROOT / "revision_sets")):
        for index, part in enumerate(parts):
            if part.lower() == anchor.lower():
                relocated = root.joinpath(*parts[index + 1 :])
                if relocated.exists():
                    return relocated.resolve()
    return candidate


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.replace(":", "_")).strip("_")


def xywh_to_xyxy(box: list[float]) -> list[float]:
    x, y, w, h = [float(value) for value in box]
    return [x, y, x + w, y + h]


def iou_xyxy(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    denom = area_a + area_b - inter
    return 0.0 if denom <= 0 else inter / denom


def yolo_labels_to_boxes(path: Path, width: int, height: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    boxes: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5 or parts[0] != "0":
            continue
        _, xc, yc, bw, bh = parts
        x_center = float(xc) * width
        y_center = float(yc) * height
        box_w = float(bw) * width
        box_h = float(bh) * height
        boxes.append(
            {
                "truth_id": f"truth_{index:03d}",
                "label_index": index,
                "box_xyxy": [
                    x_center - box_w / 2.0,
                    y_center - box_h / 2.0,
                    x_center + box_w / 2.0,
                    y_center + box_h / 2.0,
                ],
            }
        )
    return boxes


def load_detection_pages(detections_dir: Path) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for path in sorted(detections_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for page in payload.get("pages", []):
            page["_detection_manifest_path"] = str(path)
            pages.append(page)
    return pages


def detection_match_keys(page: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    render_path = page.get("render_path")
    if render_path:
        keys.add(f"render:{Path(str(render_path)).stem}")
    pdf = page.get("pdf")
    if pdf and page.get("page") not in (None, ""):
        keys.add(f"pdfpage:{Path(str(pdf)).stem}:pagenum:{int(page['page'])}")
    return keys


def eval_row_match_keys(row: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    render_path = row.get("render_path")
    if render_path:
        keys.add(f"render:{Path(str(render_path)).stem}")
        keys.add(f"render:{resolve_project_path(render_path).stem}")
    if row.get("pdf_path") and row.get("page_number") not in (None, ""):
        keys.add(f"pdfpage:{Path(str(row['pdf_path'])).stem}:pagenum:{int(row['page_number'])}")
    return keys


def build_pages_by_key(detections_dir: Path) -> dict[str, dict[str, Any]]:
    pages_by_key: dict[str, dict[str, Any]] = {}
    for page in load_detection_pages(detections_dir):
        for key in detection_match_keys(page):
            pages_by_key[key] = page
    return pages_by_key


def match_at_threshold(
    labels: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    threshold: float,
) -> tuple[dict[int, int], dict[int, int], dict[tuple[int, int], float]]:
    pairs: list[tuple[float, int, int]] = []
    all_ious: dict[tuple[int, int], float] = {}
    for label_index, label in enumerate(labels):
        for pred_index, pred in enumerate(predictions):
            iou = iou_xyxy(label["box_xyxy"], pred["box_xyxy"])
            all_ious[(label_index, pred_index)] = iou
            pairs.append((iou, label_index, pred_index))
    pairs.sort(reverse=True)
    label_to_pred: dict[int, int] = {}
    pred_to_label: dict[int, int] = {}
    for iou, label_index, pred_index in pairs:
        if iou < threshold:
            break
        if label_index in label_to_pred or pred_index in pred_to_label:
            continue
        label_to_pred[label_index] = pred_index
        pred_to_label[pred_index] = label_index
    return label_to_pred, pred_to_label, all_ious


def best_label_for_prediction(
    pred_index: int,
    labels: list[dict[str, Any]],
    all_ious: dict[tuple[int, int], float],
) -> tuple[int | None, float]:
    best_index: int | None = None
    best_iou = 0.0
    for label_index, _ in enumerate(labels):
        iou = all_ious.get((label_index, pred_index), 0.0)
        if iou > best_iou:
            best_index = label_index
            best_iou = iou
    return best_index, best_iou


def best_prediction_for_label(
    label_index: int,
    predictions: list[dict[str, Any]],
    all_ious: dict[tuple[int, int], float],
) -> tuple[int | None, float]:
    best_index: int | None = None
    best_iou = 0.0
    for pred_index, _ in enumerate(predictions):
        iou = all_ious.get((label_index, pred_index), 0.0)
        if iou > best_iou:
            best_index = pred_index
            best_iou = iou
    return best_index, best_iou


def rounded_iou(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def build_truth_context(
    labels: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    label_to_pred_25: dict[int, int],
    all_ious: dict[tuple[int, int], float],
) -> list[dict[str, Any]]:
    truth_boxes: list[dict[str, Any]] = []
    for label_index, label in enumerate(labels):
        pred_index = label_to_pred_25.get(label_index)
        match_iou = None if pred_index is None else all_ious.get((label_index, pred_index), 0.0)
        truth_boxes.append(
            {
                "truth_id": label["truth_id"],
                "box_xyxy": label["box_xyxy"],
                "matched_prediction_id": None if pred_index is None else predictions[pred_index]["prediction_id"],
                "match_iou_25": rounded_iou(match_iou),
            }
        )
    return truth_boxes


def build_prediction_context(
    labels: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    pred_to_label_25: dict[int, int],
    all_ious: dict[tuple[int, int], float],
) -> list[dict[str, Any]]:
    prediction_boxes: list[dict[str, Any]] = []
    for pred_index, pred in enumerate(predictions):
        matched_label_index = pred_to_label_25.get(pred_index)
        match_iou = None if matched_label_index is None else all_ious.get((matched_label_index, pred_index), 0.0)
        nearest_label_index, nearest_iou = best_label_for_prediction(pred_index, labels, all_ious)
        prediction_boxes.append(
            {
                "prediction_id": pred["prediction_id"],
                "box_xyxy": pred["box_xyxy"],
                "confidence": round(pred["confidence"], 6),
                "source_mode": pred.get("source_mode"),
                "member_count": pred.get("member_count"),
                "size_bucket": pred.get("size_bucket"),
                "confidence_tier": pred.get("confidence_tier"),
                "matched_truth_id": None if matched_label_index is None else labels[matched_label_index]["truth_id"],
                "match_iou_25": rounded_iou(match_iou),
                "nearest_truth_id": None if nearest_label_index is None else labels[nearest_label_index]["truth_id"],
                "nearest_truth_iou": rounded_iou(nearest_iou),
            }
        )
    return prediction_boxes


def describe_prediction_mismatch(
    mismatch_type: str,
    pred: dict[str, Any],
    truth: dict[str, Any] | None,
    best_iou: float,
    match_iou: float,
    localization_iou: float,
    matched_elsewhere_prediction_id: str | None,
) -> str:
    pred_id = pred["prediction_id"]
    truth_id = None if truth is None else truth["truth_id"]
    if mismatch_type == "localization_low_iou":
        return (
            f"{pred_id} was matched to {truth_id} at IoU {best_iou:.3f}, so it counts as a TP at "
            f"IoU {match_iou:.2f}. It is queued because localization is below IoU {localization_iou:.2f}."
        )
    if matched_elsewhere_prediction_id:
        return (
            f"{pred_id} was not assigned the IoU {match_iou:.2f} scoring match. Its nearest truth is "
            f"{truth_id} at IoU {best_iou:.3f}, but that truth was already matched to "
            f"{matched_elsewhere_prediction_id}. This may be a duplicate/fragment scoring artifact."
        )
    if truth_id:
        return (
            f"{pred_id} was not assigned a scoring match because its nearest truth is {truth_id} at "
            f"IoU {best_iou:.3f}, below the IoU {match_iou:.2f} threshold."
        )
    return f"{pred_id} was not assigned a scoring match and no truth box overlaps it on this page."


def describe_truth_mismatch(
    label: dict[str, Any],
    best_pred: dict[str, Any] | None,
    best_iou: float,
    match_iou: float,
    matched_elsewhere_truth_id: str | None,
) -> str:
    truth_id = label["truth_id"]
    if best_pred is None:
        return f"{truth_id} did not receive an IoU {match_iou:.2f} scoring match; there are no predictions on this page."
    pred_id = best_pred["prediction_id"]
    if matched_elsewhere_truth_id:
        return (
            f"{truth_id} did not receive an IoU {match_iou:.2f} scoring match. The nearest prediction is "
            f"{pred_id} at IoU {best_iou:.3f}, but that prediction was matched to {matched_elsewhere_truth_id}."
        )
    return (
        f"{truth_id} did not receive an IoU {match_iou:.2f} scoring match. The nearest prediction is "
        f"{pred_id} at IoU {best_iou:.3f}."
    )


def load_predictions_for_row(row: dict[str, Any], pages_by_key: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    detection_page = None
    for key in eval_row_match_keys(row):
        detection_page = pages_by_key.get(key)
        if detection_page is not None:
            break
    detections = detection_page.get("detections", []) if detection_page else []
    predictions = []
    for index, det in enumerate(detections, start=1):
        metadata = det.get("metadata") or {}
        predictions.append(
            {
                "prediction_id": f"pred_{index:03d}",
                "prediction_index": index,
                "box_xyxy": xywh_to_xyxy(det["bbox_page"]),
                "bbox_page_xywh": det["bbox_page"],
                "confidence": float(det.get("confidence") or 0.0),
                "crop_path": det.get("crop_path"),
                "source_mode": det.get("source_mode"),
                "member_count": metadata.get("member_count"),
                "size_bucket": metadata.get("size_bucket"),
                "confidence_tier": metadata.get("confidence_tier"),
            }
        )
    return predictions, None if detection_page is None else detection_page.get("_detection_manifest_path")


def scaled_box(box: list[float], scale: float) -> tuple[int, int, int, int]:
    return tuple(int(round(value * scale)) for value in box)  # type: ignore[return-value]


def draw_box(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], color: str, width: int, text: str) -> None:
    draw.rectangle(box, outline=color, width=width)
    x1, y1, _, _ = box
    text_origin = (x1 + 3, max(0, y1 - 16))
    draw.rectangle(
        (text_origin[0] - 2, text_origin[1] - 1, text_origin[0] + 8 * max(1, len(text)), text_origin[1] + 13),
        fill="white",
    )
    draw.text(text_origin, text, fill=color)


def make_overlay(
    row: dict[str, Any],
    mode: str,
    labels: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    pred_to_label_25: dict[int, int],
    label_to_pred_25: dict[int, int],
    all_ious: dict[tuple[int, int], float],
    output_path: Path,
    max_dim: int,
) -> None:
    image_path = resolve_project_path(row.get("render_path"))
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        scale = min(max_dim / max(image.size), 1.0)
        if scale < 1.0:
            image = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(image)
        line_width = max(2, int(round(5 * scale)))
        for label_index, label in enumerate(labels):
            matched = label_index in label_to_pred_25
            color = "lime" if matched else "orange"
            text = f"T{label_index + 1}"
            if not matched:
                text += " FN"
            draw_box(draw, scaled_box(label["box_xyxy"], scale), color, line_width + (1 if not matched else 0), text)
        for pred_index, pred in enumerate(predictions):
            box = scaled_box(pred["box_xyxy"], scale)
            confidence = pred["confidence"]
            if pred_index in pred_to_label_25:
                label_index = pred_to_label_25[pred_index]
                iou = all_ious.get((label_index, pred_index), 0.0)
                color = "dodgerblue" if iou >= 0.50 else "purple"
                text = f"P{pred_index + 1} {confidence:.2f} IoU {iou:.2f}"
            else:
                color = "red"
                text = f"P{pred_index + 1} FP {confidence:.2f}"
            draw_box(draw, box, color, line_width, text)
        title = f"{mode} | {row.get('source_page_key')} | green truth, orange FN, red FP, blue/purple matched"
        draw.rectangle((0, 0, min(image.width, 8 * len(title) + 16), 24), fill="white")
        draw.text((8, 6), title, fill="black")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, quality=92)


def make_contact_sheet(
    overlay_pairs: list[dict[str, Any]],
    output_path: Path,
    thumb_width: int,
) -> None:
    thumbs: list[tuple[str, Image.Image, Image.Image]] = []
    for item in overlay_pairs:
        with Image.open(item["model_overlay"]) as model_image, Image.open(item["pipeline_overlay"]) as pipeline_image:
            model = model_image.convert("RGB")
            pipeline = pipeline_image.convert("RGB")
            model_scale = thumb_width / model.width
            pipeline_scale = thumb_width / pipeline.width
            model_thumb = model.resize((thumb_width, int(model.height * model_scale)), Image.Resampling.LANCZOS)
            pipeline_thumb = pipeline.resize((thumb_width, int(pipeline.height * pipeline_scale)), Image.Resampling.LANCZOS)
            thumbs.append((item["source_page_key"], model_thumb, pipeline_thumb))
    if not thumbs:
        return
    header_h = 28
    gap = 12
    row_heights = [header_h + max(model.height, pipeline.height) for _, model, pipeline in thumbs]
    sheet_w = thumb_width * 2 + gap
    sheet_h = sum(row_heights) + gap * (len(thumbs) - 1)
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)
    y = 0
    for source_page_key, model, pipeline in thumbs:
        draw.text((4, y + 6), f"{source_page_key} | left: model_only_tiled | right: pipeline_full", fill="black")
        y_image = y + header_h
        sheet.paste(model, (0, y_image))
        sheet.paste(pipeline, (thumb_width + gap, y_image))
        y += header_h + max(model.height, pipeline.height) + gap
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=92)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    fieldnames = fieldnames or CSV_FIELDNAMES
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_instructions(path: Path, summary: dict[str, Any]) -> None:
    bucket_lines = "\n".join(f"- `{bucket}`" for bucket in APPROVED_ERROR_BUCKETS)
    status_lines = "\n".join(f"- `{status}`" for status in REVIEW_STATUSES)
    text = f"""# Mismatch Review Packet

Status: error-analysis packet for already-reviewed `page_disjoint_real` pages.

This is not a truth-labeling pass. Do not open LabelImg for this packet. Do not
modify truth labels, eval manifests, prediction files, model files, datasets, or
training data. The mismatch review log is intentionally editable for
error-analysis metadata only.

## What To Review

- HTML reviewer: `{summary['reviewer_html']}`
- Crisp PNG review crops: `{summary['reviewer_crops_dir']}`
- Contact sheet: `{summary['contact_sheet']}`
- Mismatch JSONL: `{summary['mismatch_manifest_jsonl']}`
- Mismatch CSV: `{summary['mismatch_manifest_csv']}`
- Blank/template review log: `{summary['review_log_csv']}`
- Individual overlays: `{summary['overlays_dir']}`

The HTML reviewer is the primary review surface. The contact sheet is retained
only as a quick overview and should not be the main review tool.

## Review Fatigue Guardrail

Queue size: `{summary['mismatch_rows']}` rows.

Before asking Michael to manually review this packet, report the queue size and
estimated burden, then ask whether GPT-5.5 should prefill provisional decisions
first. For `10-50` rows, usually recommend GPT-5.5 sample or full prefill. For
more than `50` rows, recommend staged GPT-5.5 prefill unless explicitly told
otherwise. GPT prefill remains provisional until human accepted.

## Human Authority Rule

The human cloud/not-cloud judgment is authoritative when the displayed context
is adequate. If the display does not make the case understandable, mark the row
as `tooling_or_matching_artifact` or `not_actionable`; do not treat that as
human uncertainty.

`truth_followup` creates a separate frozen-truth correction/recheck task. It
does not change truth automatically.

`tooling_or_matching_artifact` means the row may reflect IoU matching, duplicate
predictions, crop context, overlay/scoring behavior, or reviewer display limits
rather than a meaningful model error.

Overlay colors:

- Green: human-audited truth box matched at IoU 0.25
- Orange: human-audited truth box missed at IoU 0.25
- Red: prediction false positive at IoU 0.25
- Blue: prediction matched with IoU at least 0.50
- Purple: prediction matched at IoU 0.25 but below IoU 0.50

## HTML Reviewer Workflow

Open `mismatch_reviewer.html` through a local server from the repo root:

```powershell
python -m http.server 8766 --bind 127.0.0.1
```

Then browse to:

```text
http://127.0.0.1:8766/CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_reviewer.html
```

After any approved prefill step, use the browser UI to confirm/correct review
metadata and click `Export Reviewed CSV`.
Save the export as `mismatch_review_log.reviewed.csv` in this packet directory,
then run:

```powershell
.\\.venv\\Scripts\\python.exe CloudHammer_v2\\scripts\\summarize_mismatch_review.py --review-log CloudHammer_v2\\outputs\\baseline_human_audited_mismatch_review_20260504\\overlay_packet\\mismatch_review_log.reviewed.csv
```

## Review Fields

Editable fields:

- `human_error_bucket`
- `human_review_status`
- `human_notes`

Read-only explanation/scoring fields include:

- `nearest_truth_iou`
- `nearest_truth_id`
- `nearest_prediction_id`
- `nearest_prediction_iou`
- `matched_elsewhere`
- `possible_duplicate_prediction`
- `mismatch_reason_raw`

## Review Status Values

{status_lines}

## Approved Error Buckets

{bucket_lines}

## Packet Summary

- Pages with mismatch rows: `{summary['pages_with_mismatches']}`
- Mismatch rows: `{summary['mismatch_rows']}`
- By mode: `{summary['by_mode']}`
- By mismatch type: `{summary['by_mismatch_type']}`
"""
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build read-only mismatch overlays and review manifests.")
    parser.add_argument(
        "--eval-manifest",
        type=Path,
        default=V2_ROOT / "eval" / "page_disjoint_real" / "page_disjoint_real_manifest.human_audited.jsonl",
    )
    parser.add_argument(
        "--model-detections-dir",
        type=Path,
        default=V2_ROOT / "outputs" / "baseline_model_only_tiled_page_disjoint_real_20260502" / "detections",
    )
    parser.add_argument(
        "--pipeline-detections-dir",
        type=Path,
        default=V2_ROOT
        / "outputs"
        / "baseline_pipeline_full_page_disjoint_real_20260502"
        / "whole_cloud_candidates"
        / "detections_whole",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=V2_ROOT / "outputs" / "baseline_human_audited_mismatch_review_20260504" / "overlay_packet",
    )
    parser.add_argument("--match-iou", type=float, default=0.25)
    parser.add_argument("--localization-iou", type=float, default=0.50)
    parser.add_argument("--max-overlay-dim", type=int, default=1800)
    parser.add_argument("--contact-thumb-width", type=int, default=850)
    args = parser.parse_args()

    eval_rows = read_jsonl(args.eval_manifest)
    model_pages = build_pages_by_key(args.model_detections_dir)
    pipeline_pages = build_pages_by_key(args.pipeline_detections_dir)
    mode_configs = {
        "model_only_tiled": model_pages,
        "pipeline_full": pipeline_pages,
    }

    output_dir = args.output_dir
    overlays_dir = output_dir / "overlays"
    review_log_csv = output_dir / "mismatch_review_log.csv"
    existing_review_rows = read_csv_by_id(review_log_csv)
    mismatch_rows: list[dict[str, Any]] = []
    overlay_pairs: dict[str, dict[str, Any]] = {}

    for row in eval_rows:
        source_page_key = str(row.get("source_page_key") or Path(str(row.get("render_path") or "")).stem)
        width = int(row.get("width_px") or 0)
        height = int(row.get("height_px") or 0)
        label_path = Path(str(row.get("label_path") or ""))
        labels = yolo_labels_to_boxes(label_path, width, height)
        page_stem = safe_stem(source_page_key)
        overlay_pairs[source_page_key] = {"source_page_key": source_page_key}

        for eval_mode, pages_by_key in mode_configs.items():
            predictions, detection_manifest_path = load_predictions_for_row(row, pages_by_key)
            label_to_pred_25, pred_to_label_25, all_ious = match_at_threshold(labels, predictions, args.match_iou)
            overlay_path = overlays_dir / eval_mode / f"{page_stem}_{eval_mode}_truth_vs_predictions.jpg"
            make_overlay(
                row,
                eval_mode,
                labels,
                predictions,
                pred_to_label_25,
                label_to_pred_25,
                all_ious,
                overlay_path,
                args.max_overlay_dim,
            )
            overlay_pairs[source_page_key][f"{'model' if eval_mode == 'model_only_tiled' else 'pipeline'}_overlay"] = overlay_path
            page_truth_boxes = build_truth_context(labels, predictions, label_to_pred_25, all_ious)
            page_prediction_boxes = build_prediction_context(labels, predictions, pred_to_label_25, all_ious)

            for pred_index, pred in enumerate(predictions):
                if pred_index in pred_to_label_25:
                    label_index = pred_to_label_25[pred_index]
                    iou = all_ious.get((label_index, pred_index), 0.0)
                    if iou >= args.localization_iou:
                        continue
                    mismatch_type = "localization_low_iou"
                    truth = labels[label_index]
                    best_iou = iou
                else:
                    label_index, best_iou = best_label_for_prediction(pred_index, labels, all_ious)
                    truth = labels[label_index] if label_index is not None else None
                    mismatch_type = "false_positive"
                matched_elsewhere_prediction_id = None
                matched_elsewhere_prediction_iou = None
                if label_index is not None:
                    matched_pred_index = label_to_pred_25.get(label_index)
                    if matched_pred_index is not None and matched_pred_index != pred_index:
                        matched_elsewhere_prediction_id = predictions[matched_pred_index]["prediction_id"]
                        matched_elsewhere_prediction_iou = all_ious.get((label_index, matched_pred_index), 0.0)
                matched_elsewhere = matched_elsewhere_prediction_id is not None
                possible_duplicate_prediction = bool(
                    mismatch_type == "false_positive" and matched_elsewhere and best_iou > 0.0
                )
                nearest_truth_id = None if truth is None else truth["truth_id"]
                nearest_prediction_id = matched_elsewhere_prediction_id or pred["prediction_id"]
                nearest_prediction_iou = (
                    matched_elsewhere_prediction_iou if matched_elsewhere_prediction_iou is not None else best_iou
                )
                mismatch_rows.append(
                    {
                        "schema": "cloudhammer_v2.mismatch_review_item.v1",
                        "review_item_id": f"{page_stem}:{eval_mode}:pred:{pred['prediction_id']}",
                        "source_page_key": source_page_key,
                        "eval_subset": "page_disjoint_real",
                        "label_status": row.get("label_status"),
                        "eval_mode": eval_mode,
                        "mismatch_type": mismatch_type,
                        "truth_id": None if truth is None else truth["truth_id"],
                        "prediction_id": pred["prediction_id"],
                        "confidence": round(pred["confidence"], 6),
                        "iou_25": round(best_iou, 6),
                        "best_iou": round(best_iou, 6),
                        "nearest_truth_iou": round(best_iou, 6),
                        "nearest_truth_id": nearest_truth_id,
                        "nearest_prediction_id": nearest_prediction_id,
                        "nearest_prediction_iou": round(nearest_prediction_iou, 6),
                        "matched_elsewhere": matched_elsewhere,
                        "matched_elsewhere_prediction_id": matched_elsewhere_prediction_id,
                        "matched_elsewhere_truth_id": None,
                        "possible_duplicate_prediction": possible_duplicate_prediction,
                        "mismatch_reason_raw": describe_prediction_mismatch(
                            mismatch_type,
                            pred,
                            truth,
                            best_iou,
                            args.match_iou,
                            args.localization_iou,
                            matched_elsewhere_prediction_id,
                        ),
                        "bbox_xyxy": pred["box_xyxy"],
                        "truth_bbox_xyxy": None if truth is None else truth["box_xyxy"],
                        "page_truth_boxes": page_truth_boxes,
                        "page_predictions": page_prediction_boxes,
                        "crop_path": pred.get("crop_path"),
                        "prediction_source_mode": pred.get("source_mode"),
                        "member_count": pred.get("member_count"),
                        "size_bucket": pred.get("size_bucket"),
                        "confidence_tier": pred.get("confidence_tier"),
                        "detection_manifest_path": detection_manifest_path,
                        "render_path": row.get("render_path"),
                        "overlay_path": str(overlay_path),
                        "human_error_bucket": "",
                        "human_review_status": "unreviewed",
                        "human_notes": "",
                    }
                )

            for label_index, label in enumerate(labels):
                if label_index in label_to_pred_25:
                    continue
                pred_index, best_iou = best_prediction_for_label(label_index, predictions, all_ious)
                best_pred = predictions[pred_index] if pred_index is not None else None
                matched_elsewhere_truth_id = None
                if pred_index is not None:
                    matched_label_index = pred_to_label_25.get(pred_index)
                    if matched_label_index is not None and matched_label_index != label_index:
                        matched_elsewhere_truth_id = labels[matched_label_index]["truth_id"]
                matched_elsewhere = matched_elsewhere_truth_id is not None
                mismatch_rows.append(
                    {
                        "schema": "cloudhammer_v2.mismatch_review_item.v1",
                        "review_item_id": f"{page_stem}:{eval_mode}:truth:{label['truth_id']}",
                        "source_page_key": source_page_key,
                        "eval_subset": "page_disjoint_real",
                        "label_status": row.get("label_status"),
                        "eval_mode": eval_mode,
                        "mismatch_type": "false_negative",
                        "truth_id": label["truth_id"],
                        "prediction_id": None if best_pred is None else best_pred["prediction_id"],
                        "confidence": None if best_pred is None else round(best_pred["confidence"], 6),
                        "iou_25": round(best_iou, 6),
                        "best_iou": round(best_iou, 6),
                        "nearest_truth_iou": round(best_iou, 6),
                        "nearest_truth_id": label["truth_id"],
                        "nearest_prediction_id": None if best_pred is None else best_pred["prediction_id"],
                        "nearest_prediction_iou": round(best_iou, 6),
                        "matched_elsewhere": matched_elsewhere,
                        "matched_elsewhere_prediction_id": None,
                        "matched_elsewhere_truth_id": matched_elsewhere_truth_id,
                        "possible_duplicate_prediction": False,
                        "mismatch_reason_raw": describe_truth_mismatch(
                            label,
                            best_pred,
                            best_iou,
                            args.match_iou,
                            matched_elsewhere_truth_id,
                        ),
                        "bbox_xyxy": label["box_xyxy"],
                        "truth_bbox_xyxy": label["box_xyxy"],
                        "page_truth_boxes": page_truth_boxes,
                        "page_predictions": page_prediction_boxes,
                        "crop_path": None if best_pred is None else best_pred.get("crop_path"),
                        "prediction_source_mode": None if best_pred is None else best_pred.get("source_mode"),
                        "member_count": None if best_pred is None else best_pred.get("member_count"),
                        "size_bucket": None if best_pred is None else best_pred.get("size_bucket"),
                        "confidence_tier": None if best_pred is None else best_pred.get("confidence_tier"),
                        "detection_manifest_path": detection_manifest_path,
                        "render_path": row.get("render_path"),
                        "overlay_path": str(overlay_path),
                        "human_error_bucket": "",
                        "human_review_status": "unreviewed",
                        "human_notes": "",
                    }
                )

    priority_keys = []
    queue_path = output_dir.parent / "mismatch_review_queue.jsonl"
    if queue_path.exists():
        priority_keys = [str(row["source_page_key"]) for row in read_jsonl(queue_path)]
    ordered_pairs = []
    seen: set[str] = set()
    for key in priority_keys + sorted(overlay_pairs):
        if key in seen or key not in overlay_pairs:
            continue
        item = overlay_pairs[key]
        if "model_overlay" in item and "pipeline_overlay" in item:
            ordered_pairs.append(item)
            seen.add(key)

    contact_sheet = output_dir / "contact_sheets" / "mismatch_truth_vs_predictions_contact_sheet.jpg"
    make_contact_sheet(ordered_pairs, contact_sheet, args.contact_thumb_width)

    manifest_jsonl = output_dir / "mismatch_manifest.jsonl"
    manifest_csv = output_dir / "mismatch_manifest.csv"
    write_jsonl(manifest_jsonl, mismatch_rows)
    write_csv(manifest_csv, mismatch_rows)
    review_rows: list[dict[str, Any]] = []
    for row in mismatch_rows:
        saved = existing_review_rows.get(str(row["review_item_id"]), {})
        review_row = {**row}
        review_row["human_error_bucket"] = saved.get("human_error_bucket", row.get("human_error_bucket", ""))
        review_row["human_review_status"] = saved.get(
            "human_review_status", row.get("human_review_status", "unreviewed")
        )
        review_row["human_notes"] = saved.get("human_notes", row.get("human_notes", ""))
        review_rows.append(review_row)
    write_csv(review_log_csv, review_rows)

    summary = {
        "schema": "cloudhammer_v2.mismatch_review_packet_summary.v1",
        "eval_subset": "page_disjoint_real",
        "label_status": "human_audited",
        "eval_manifest": str(args.eval_manifest),
        "model_detections_dir": str(args.model_detections_dir),
        "pipeline_detections_dir": str(args.pipeline_detections_dir),
        "mismatch_manifest_jsonl": str(manifest_jsonl),
        "mismatch_manifest_csv": str(manifest_csv),
        "review_log_csv": str(review_log_csv),
        "reviewer_html": str(output_dir / "mismatch_reviewer.html"),
        "reviewer_crops_dir": str(output_dir / "reviewer_crops"),
        "contact_sheet": str(contact_sheet),
        "overlays_dir": str(overlays_dir),
        "pages": len(eval_rows),
        "pages_with_mismatches": len({row["source_page_key"] for row in mismatch_rows}),
        "mismatch_rows": len(mismatch_rows),
        "by_mode": dict(Counter(str(row["eval_mode"]) for row in mismatch_rows)),
        "by_mismatch_type": dict(Counter(str(row["mismatch_type"]) for row in mismatch_rows)),
        "approved_error_buckets": APPROVED_ERROR_BUCKETS,
        "review_statuses": REVIEW_STATUSES,
    }
    write_json(output_dir / "mismatch_packet_summary.json", summary)
    write_instructions(output_dir / "README.md", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
