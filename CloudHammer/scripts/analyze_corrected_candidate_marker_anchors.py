from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs" / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428"
DEFAULT_INPUT = DEFAULT_RUN / "corrected_candidates_with_rescue_v1" / "corrected_whole_cloud_candidates.jsonl"
DEFAULT_DELTA_MANIFEST = ROOT / "data" / "manifests" / "delta_manifest.jsonl"
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "marker_anchor_analysis_v1"


def pdf_stem_key(path_text: str) -> str:
    return Path(path_text).stem.casefold()


def infer_page_index(row: dict[str, Any]) -> int | None:
    value = row.get("page_index")
    if value is not None and value != "":
        return int(value)
    page_number = row.get("page_number")
    if page_number is None or page_number == "":
        return None
    return int(page_number) - 1


def infer_target_digit(row: dict[str, Any]) -> str | None:
    text = " ".join(str(row.get(key) or "") for key in ("pdf_path", "pdf_stem", "revision", "candidate_id"))
    match = re.search(r"Revision\s*#\s*(\d+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\bRev(?:ision)?\s*[_#-]?\s*(\d+)\b", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def box_from_row(row: dict[str, Any], key: str) -> tuple[float, float, float, float] | None:
    value = row.get(key)
    if not isinstance(value, list) or len(value) != 4:
        return None
    return tuple(float(item) for item in value)


def box_area(box: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def box_distance(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    lx1, ly1, lx2, ly2 = left
    rx1, ry1, rx2, ry2 = right
    dx = max(rx1 - lx2, lx1 - rx2, 0.0)
    dy = max(ry1 - ly2, ly1 - ry2, 0.0)
    return math.hypot(dx, dy)


def point_to_box_distance(point: dict[str, float], box: tuple[float, float, float, float]) -> float:
    x = float(point["x"])
    y = float(point["y"])
    x1, y1, x2, y2 = box
    dx = max(x1 - x, 0.0, x - x2)
    dy = max(y1 - y, 0.0, y - y2)
    return math.hypot(dx, dy)


def marker_box(marker: dict[str, Any]) -> tuple[float, float, float, float]:
    points: list[dict[str, Any]] = []
    triangle = marker.get("triangle") or {}
    for key in ("apex", "left_base", "right_base"):
        point = triangle.get(key)
        if isinstance(point, dict) and "x" in point and "y" in point:
            points.append(point)
    if not points:
        center = marker["center"]
        x = float(center["x"])
        y = float(center["y"])
        return (x, y, x, y)
    xs = [float(point["x"]) for point in points]
    ys = [float(point["y"]) for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def markers_near_box(
    markers: list[dict[str, Any]],
    box: tuple[float, float, float, float] | None,
    margin: float,
) -> list[dict[str, Any]]:
    if box is None:
        return []
    x1, y1, x2, y2 = box
    return [
        marker
        for marker in markers
        if x1 - margin <= float(marker["center"]["x"]) <= x2 + margin
        and y1 - margin <= float(marker["center"]["y"]) <= y2 + margin
    ]


def load_delta_marker_index(path: Path) -> dict[tuple[str, int], list[dict[str, Any]]]:
    index: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in read_jsonl(path):
        page_index = int(row.get("page_index") or 0)
        key = (pdf_stem_key(str(row.get("pdf_path") or row.get("pdf_stem") or "")), page_index)
        markers: list[dict[str, Any]] = []
        for marker in row.get("active_deltas") or []:
            center = marker.get("center") or {}
            if "x" not in center or "y" not in center:
                continue
            markers.append(
                {
                    "digit": None if marker.get("digit") is None else str(marker.get("digit")),
                    "center": {"x": float(center["x"]), "y": float(center["y"])},
                    "triangle": marker.get("triangle") or {},
                    "score": float(marker.get("score") or 0.0),
                    "side_support": float(marker.get("side_support") or 0.0),
                    "base_support": float(marker.get("base_support") or 0.0),
                    "geometry_score": float(marker.get("geometry_score") or 0.0),
                }
            )
        index.setdefault(key, []).extend(markers)
    return index


def markers_for_row(row: dict[str, Any], marker_index: dict[tuple[str, int], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    page_index = infer_page_index(row)
    if page_index is None:
        return []
    markers = marker_index.get((pdf_stem_key(str(row.get("pdf_path") or row.get("pdf_stem") or "")), page_index), [])
    if not markers and row.get("pdf_stem"):
        markers = marker_index.get((pdf_stem_key(str(row.get("pdf_stem"))), page_index), [])
    return markers


def nearest_marker_metrics(
    markers: list[dict[str, Any]],
    bbox: tuple[float, float, float, float] | None,
) -> dict[str, Any]:
    if bbox is None or not markers:
        return {
            "nearest_marker_bbox_distance": None,
            "nearest_marker_center_distance": None,
            "nearest_marker_digit": None,
            "nearest_marker_score": None,
        }
    best: dict[str, Any] | None = None
    for marker in markers:
        bbox_distance = box_distance(bbox, marker_box(marker))
        center_distance = point_to_box_distance(marker["center"], bbox)
        metric = {
            "nearest_marker_bbox_distance": bbox_distance,
            "nearest_marker_center_distance": center_distance,
            "nearest_marker_digit": marker.get("digit"),
            "nearest_marker_score": marker.get("score"),
        }
        if best is None or bbox_distance < best["nearest_marker_bbox_distance"]:
            best = metric
    return best or {}


def marker_anchor_bucket(enriched: dict[str, Any]) -> str:
    if enriched.get("target_digit") is None:
        return "no_target_digit"
    if int(enriched.get("matching_page_marker_count") or 0) == 0:
        return "no_matching_page_markers"
    nearest_bbox = enriched.get("nearest_matching_marker_bbox_distance")
    nearest_center = enriched.get("nearest_matching_marker_center_distance")
    if nearest_bbox is not None and float(nearest_bbox) <= 40.0:
        return "marker_touches_candidate"
    if int(enriched.get("matching_markers_in_crop") or 0) > 0:
        return "marker_in_crop_not_touching"
    if nearest_center is not None and float(nearest_center) <= 350.0:
        return "marker_near_candidate"
    return "no_near_matching_marker"


def likely_marker_false_positive(row: dict[str, Any]) -> bool:
    if row.get("marker_anchor_bucket") != "no_near_matching_marker":
        return False
    if row.get("review_status") == "accept":
        return False
    if row.get("is_split_replacement"):
        return False
    confidence = float(row.get("whole_cloud_confidence") or row.get("confidence") or 0.0)
    member_count = int(row.get("member_count") or 0)
    return confidence < 0.75 or member_count <= 1


def enrich_candidate(row: dict[str, Any], marker_index: dict[tuple[str, int], list[dict[str, Any]]]) -> dict[str, Any]:
    enriched = dict(row)
    target_digit = infer_target_digit(row)
    all_markers = markers_for_row(row, marker_index)
    matching_markers = [
        marker
        for marker in all_markers
        if target_digit is None or marker.get("digit") == target_digit
    ]
    bbox = box_from_row(row, "bbox_page_xyxy")
    crop_box = box_from_row(row, "crop_box_page_xyxy")
    crop_margin = 0.0
    matching_crop_markers = markers_near_box(matching_markers, crop_box, crop_margin)
    all_crop_markers = markers_near_box(all_markers, crop_box, crop_margin)
    metrics = nearest_marker_metrics(matching_markers, bbox)
    enriched.update(
        {
            "target_digit": target_digit,
            "page_marker_count": len(all_markers),
            "matching_page_marker_count": len(matching_markers),
            "markers_in_crop": len(all_crop_markers),
            "matching_markers_in_crop": len(matching_crop_markers),
            "bbox_area_page": None if bbox is None else box_area(bbox),
            "marker_anchor_schema": "cloudhammer.marker_anchor_analysis.v1",
            "nearest_matching_marker_bbox_distance": metrics.get("nearest_marker_bbox_distance"),
            "nearest_matching_marker_center_distance": metrics.get("nearest_marker_center_distance"),
            "nearest_matching_marker_digit": metrics.get("nearest_marker_digit"),
            "nearest_matching_marker_score": metrics.get("nearest_marker_score"),
        }
    )
    enriched["marker_anchor_bucket"] = marker_anchor_bucket(enriched)
    enriched["marker_false_positive_candidate"] = likely_marker_false_positive(enriched)
    return enriched


def summarize(rows: list[dict[str, Any]], output_dir: Path, input_path: Path) -> dict[str, Any]:
    return {
        "schema": "cloudhammer.marker_anchor_analysis.v1",
        "input_manifest": str(input_path),
        "output_dir": str(output_dir),
        "total_candidates": len(rows),
        "by_marker_anchor_bucket": dict(Counter(str(row.get("marker_anchor_bucket")) for row in rows)),
        "by_correction_source": dict(Counter(str(row.get("correction_source")) for row in rows)),
        "marker_false_positive_candidates": sum(1 for row in rows if row.get("marker_false_positive_candidate")),
    }


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Corrected Candidate Marker Anchor Analysis",
        "",
        f"Input manifest: `{summary['input_manifest']}`",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Totals",
        "",
        f"- total candidates: `{summary['total_candidates']}`",
        f"- marker false-positive candidates: `{summary['marker_false_positive_candidates']}`",
        "",
        "## Marker Anchor Buckets",
        "",
        "| Bucket | Count |",
        "| --- | ---: |",
    ]
    for bucket, count in sorted(summary["by_marker_anchor_bucket"].items()):
        lines.append(f"| `{bucket}` | `{count}` |")
    lines.extend(["", "## Files", "", "- `candidates_with_marker_anchors.jsonl`: every row with marker context attached"])
    lines.append("- `marker_false_positive_candidates.jsonl`: conservative candidates lacking matching marker support")
    lines.append("- `marker_false_positive_review_queue.jsonl`: same rows sorted by confidence ascending")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze corrected whole-cloud candidates against revision marker anchors.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--delta-manifest", type=Path, default=DEFAULT_DELTA_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    marker_index = load_delta_marker_index(args.delta_manifest.resolve())
    rows = [enrich_candidate(row, marker_index) for row in read_jsonl(input_path)]
    marker_fp_rows = [row for row in rows if row.get("marker_false_positive_candidate")]
    marker_fp_review_queue = sorted(
        marker_fp_rows,
        key=lambda row: (
            float(row.get("whole_cloud_confidence") or row.get("confidence") or 0.0),
            int(row.get("member_count") or 0),
            str(row.get("candidate_id")),
        ),
    )
    write_jsonl(output_dir / "candidates_with_marker_anchors.jsonl", rows)
    write_jsonl(output_dir / "marker_false_positive_candidates.jsonl", marker_fp_rows)
    write_jsonl(output_dir / "marker_false_positive_review_queue.jsonl", marker_fp_review_queue)
    summary = summarize(rows, output_dir, input_path)
    write_json(output_dir / "marker_anchor_summary.json", summary)
    write_markdown(summary, output_dir / "marker_anchor_summary.md")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
