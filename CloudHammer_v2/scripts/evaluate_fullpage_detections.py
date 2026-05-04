from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
LEGACY_ROOT = PROJECT_ROOT / "CloudHammer"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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
        if len(parts) != 5:
            continue
        cls, xc, yc, bw, bh = parts
        if cls != "0":
            continue
        x_center = float(xc) * width
        y_center = float(yc) * height
        box_w = float(bw) * width
        box_h = float(bh) * height
        boxes.append(
            {
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


def match_predictions_to_labels(
    labels: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    iou_threshold: float,
) -> tuple[int, int, int, list[dict[str, Any]]]:
    pairs: list[tuple[float, int, int]] = []
    for label_index, label in enumerate(labels):
        for pred_index, pred in enumerate(predictions):
            pairs.append((iou_xyxy(label["box_xyxy"], pred["box_xyxy"]), label_index, pred_index))
    pairs.sort(reverse=True)
    used_labels: set[int] = set()
    used_predictions: set[int] = set()
    matches: list[dict[str, Any]] = []
    for iou, label_index, pred_index in pairs:
        if iou < iou_threshold:
            break
        if label_index in used_labels or pred_index in used_predictions:
            continue
        used_labels.add(label_index)
        used_predictions.add(pred_index)
        matches.append(
            {
                "label_index": labels[label_index]["label_index"],
                "prediction_index": predictions[pred_index]["prediction_index"],
                "prediction_confidence": predictions[pred_index]["confidence"],
                "iou": round(iou, 6),
            }
        )
    tp = len(matches)
    fp = len(predictions) - len(used_predictions)
    fn = len(labels) - len(used_labels)
    return tp, fp, fn, matches


def metrics_for_counts(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"# Full-Page Eval - {summary['run_name']}",
        "",
        f"Eval subset: `{summary['eval_subset']}`",
        f"Label status: `{summary['label_status']}`",
        f"Prediction source: `{summary['prediction_source']}`",
        f"Pages: `{summary['pages']}`",
        f"Labels: `{summary['labels']}`",
        f"Predictions: `{summary['predictions']}`",
        f"False positives per page @ IoU 0.25: `{summary['iou_25']['false_positives_per_page']:.3f}`",
        "",
        "## Metrics",
        "",
        "| IoU | TP | FP | FN | Precision | Recall | F1 |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in ("iou_25", "iou_50"):
        item = summary[key]
        lines.append(
            f"| `{item['threshold']:.2f}` | `{item['tp']}` | `{item['fp']}` | `{item['fn']}` | "
            f"`{item['precision']:.3f}` | `{item['recall']:.3f}` | `{item['f1']:.3f}` |"
        )
    lines.extend(["", "## Confidence Buckets", ""])
    for bucket, count in summary["confidence_buckets"].items():
        lines.append(f"- `{bucket}`: `{count}`")
    lines.extend(["", "This report uses provisional labels unless label_status says otherwise."])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate full-page CloudHammer detections against frozen YOLO labels.")
    parser.add_argument(
        "--eval-manifest",
        type=Path,
        default=V2_ROOT / "eval" / "page_disjoint_real" / "page_disjoint_real_manifest.gpt_provisional.jsonl",
    )
    parser.add_argument("--detections-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-name", type=str, required=True)
    parser.add_argument("--prediction-source", type=str, required=True)
    args = parser.parse_args()

    eval_rows = read_jsonl(args.eval_manifest)
    detection_pages = load_detection_pages(args.detections_dir)
    pages_by_key: dict[str, dict[str, Any]] = {}
    for page in detection_pages:
        for key in detection_match_keys(page):
            pages_by_key[key] = page

    per_page_rows: list[dict[str, Any]] = []
    match_rows: list[dict[str, Any]] = []
    totals = {
        "labels": 0,
        "predictions": 0,
        "iou_25": Counter(),
        "iou_50": Counter(),
    }
    confidence_buckets: Counter[str] = Counter()

    for row in eval_rows:
        source_key = str(row.get("source_page_key") or Path(str(row.get("render_path") or "")).stem)
        width = int(row.get("width_px") or 0)
        height = int(row.get("height_px") or 0)
        label_path = Path(str(row.get("label_path") or ""))
        labels = yolo_labels_to_boxes(label_path, width, height)
        detection_page = None
        for key in eval_row_match_keys(row):
            detection_page = pages_by_key.get(key)
            if detection_page is not None:
                break
        detections = detection_page.get("detections", []) if detection_page else []
        predictions = [
            {
                "prediction_index": index,
                "box_xyxy": xywh_to_xyxy(det["bbox_page"]),
                "confidence": float(det.get("confidence") or 0.0),
                "source_mode": det.get("source_mode"),
            }
            for index, det in enumerate(detections, start=1)
        ]
        for pred in predictions:
            conf = pred["confidence"]
            if conf >= 0.75:
                confidence_buckets["high_0.75_plus"] += 1
            elif conf >= 0.50:
                confidence_buckets["medium_0.50_0.75"] += 1
            else:
                confidence_buckets["low_below_0.50"] += 1

        totals["labels"] += len(labels)
        totals["predictions"] += len(predictions)
        page_payload = {
            "source_page_key": source_key,
            "label_count": len(labels),
            "prediction_count": len(predictions),
            "matched_detection_page": detection_page is not None,
            "detection_manifest_path": None if detection_page is None else detection_page.get("_detection_manifest_path"),
        }
        for threshold, key in ((0.25, "iou_25"), (0.50, "iou_50")):
            tp, fp, fn, matches = match_predictions_to_labels(labels, predictions, threshold)
            totals[key].update({"tp": tp, "fp": fp, "fn": fn})
            page_payload[f"{key}_tp"] = tp
            page_payload[f"{key}_fp"] = fp
            page_payload[f"{key}_fn"] = fn
            for match in matches:
                match_rows.append({"source_page_key": source_key, "threshold": threshold, **match})
        per_page_rows.append(page_payload)

    def threshold_summary(name: str, threshold: float) -> dict[str, Any]:
        counts = totals[name]
        metrics = metrics_for_counts(counts["tp"], counts["fp"], counts["fn"])
        return {
            "threshold": threshold,
            "tp": counts["tp"],
            "fp": counts["fp"],
            "fn": counts["fn"],
            "false_positives_per_page": counts["fp"] / len(eval_rows) if eval_rows else 0.0,
            **metrics,
        }

    summary = {
        "schema": "cloudhammer_v2.fullpage_eval_summary.v1",
        "run_name": args.run_name,
        "eval_subset": "page_disjoint_real",
        "label_status": str(eval_rows[0].get("label_status") if eval_rows else "unknown"),
        "prediction_source": args.prediction_source,
        "eval_manifest": str(args.eval_manifest),
        "detections_dir": str(args.detections_dir),
        "pages": len(eval_rows),
        "pages_with_labels": sum(1 for row in per_page_rows if row["label_count"] > 0),
        "pages_with_predictions": sum(1 for row in per_page_rows if row["prediction_count"] > 0),
        "labels": totals["labels"],
        "predictions": totals["predictions"],
        "unmatched_detection_pages": sum(1 for row in per_page_rows if not row["matched_detection_page"]),
        "iou_25": threshold_summary("iou_25", 0.25),
        "iou_50": threshold_summary("iou_50", 0.50),
        "confidence_buckets": dict(confidence_buckets),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "eval_summary.json", summary)
    write_jsonl(args.output_dir / "per_page_eval.jsonl", per_page_rows)
    write_jsonl(args.output_dir / "prediction_matches.jsonl", match_rows)
    (args.output_dir / "eval_summary.md").write_text(markdown_summary(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
