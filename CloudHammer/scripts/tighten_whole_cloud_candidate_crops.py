from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.infer.crop_tightening import (
    CropTighteningParams,
    box_from_row,
    crop_metrics,
    round_box,
    tightened_crop_box_for_bbox,
)
from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs" / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428"
DEFAULT_MANIFEST = DEFAULT_RUN / "audit_queue_080" / "manifest.jsonl"
DEFAULT_REVIEW_LOG = (
    ROOT
    / "data"
    / "whole_cloud_candidate_reviews"
    / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428.audit80.review.jsonl"
)
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "audit_queue_080" / "tightened_crops_v1"


XYXY = tuple[float, float, float, float]


def resolve_cloudhammer_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.exists():
        return path.resolve()
    parts = path.parts
    for index, part in enumerate(parts):
        if part.lower() == "cloudhammer":
            relocated = ROOT.joinpath(*parts[index + 1 :])
            if relocated.exists():
                return relocated.resolve()
    return path


def safe_path_part(value: str, max_length: int = 96) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = "unknown"
    return cleaned[:max_length].rstrip(" .")


def latest_reviews(path: Path) -> dict[str, dict[str, Any]]:
    reviews: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return reviews
    for row in read_jsonl(path):
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id:
            reviews[candidate_id] = row
    return reviews


def selected_rows(manifest_path: Path, review_log_path: Path | None, review_status: str) -> list[dict[str, Any]]:
    reviews = latest_reviews(review_log_path) if review_log_path is not None else {}
    rows: list[dict[str, Any]] = []
    for row in read_jsonl(manifest_path):
        candidate_id = str(row.get("candidate_id") or "")
        review = reviews.get(candidate_id)
        merged = dict(row)
        if review is not None:
            merged["review_status"] = review.get("status")
            merged["reviewed_at"] = review.get("reviewed_at")
            merged["reviewer"] = review.get("reviewer")
        elif review_log_path is not None:
            merged["review_status"] = None
        if review_status != "all" and merged.get("review_status") != review_status:
            continue
        rows.append(merged)
    return rows


def crop_image(image: np.ndarray, box: XYXY) -> np.ndarray:
    height, width = image.shape[:2]
    x1, y1, x2, y2 = box
    left = max(0, min(width, int(math.floor(x1))))
    top = max(0, min(height, int(math.floor(y1))))
    right = max(0, min(width, int(math.ceil(x2))))
    bottom = max(0, min(height, int(math.ceil(y2))))
    if right <= left or bottom <= top:
        raise ValueError(f"Invalid crop box: {box}")
    return image[top:bottom, left:right]


def fit_image(image: np.ndarray, width: int, height: int) -> np.ndarray:
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    image_height, image_width = image.shape[:2]
    scale = min(width / max(1, image_width), height / max(1, image_height))
    resized = cv2.resize(
        image,
        (max(1, int(image_width * scale)), max(1, int(image_height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    y = (height - resized.shape[0]) // 2
    x = (width - resized.shape[1]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


def draw_page_box_on_crop(
    image: np.ndarray,
    page_box: XYXY,
    crop_box: XYXY,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    crop_x1, crop_y1, _, _ = crop_box
    x1, y1, x2, y2 = page_box
    cv2.rectangle(
        image,
        (int(round(x1 - crop_x1)), int(round(y1 - crop_y1))),
        (int(round(x2 - crop_x1)), int(round(y2 - crop_y1))),
        color,
        thickness,
    )


def comparison_tile(row: dict[str, Any], tile_width: int = 360, tile_height: int = 300) -> np.ndarray | None:
    source = cv2.imread(str(resolve_cloudhammer_path(str(row["source_crop_image_path"]))), cv2.IMREAD_GRAYSCALE)
    tight = cv2.imread(str(resolve_cloudhammer_path(str(row["tight_crop_image_path"]))), cv2.IMREAD_GRAYSCALE)
    if source is None or tight is None:
        return None

    source_bgr = cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
    tight_bgr = cv2.cvtColor(tight, cv2.COLOR_GRAY2BGR)
    bbox = tuple(float(value) for value in row["bbox_page_xyxy"])
    original_crop = tuple(float(value) for value in row["original_crop_box_page_xyxy"])
    tight_crop = tuple(float(value) for value in row["tight_crop_box_page_xyxy"])
    draw_page_box_on_crop(source_bgr, tight_crop, original_crop, (0, 190, 0), 5)
    draw_page_box_on_crop(source_bgr, bbox, original_crop, (220, 100, 0), 4)
    draw_page_box_on_crop(tight_bgr, bbox, tight_crop, (220, 100, 0), 4)

    left = fit_image(source_bgr, tile_width, tile_height)
    right = fit_image(tight_bgr, tile_width, tile_height)
    label_height = 56
    tile = np.full((tile_height + label_height, tile_width * 2, 3), 245, dtype=np.uint8)
    tile[:tile_height, :tile_width] = left
    tile[:tile_height, tile_width:] = right
    cv2.line(tile, (tile_width, 0), (tile_width, tile_height), (30, 30, 30), 2)
    label = (
        f"{str(row['candidate_id'])[-24:]}  "
        f"{row.get('size_bucket')}  n={row.get('member_count')}  "
        f"area {float(row['area_ratio_vs_original']):.2f}x"
    )
    cv2.putText(tile, "original + tight box", (8, tile_height + 21), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(tile, "tight crop", (tile_width + 8, tile_height + 21), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(tile, label, (8, tile_height + 45), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    return tile


def write_contact_sheet(rows: list[dict[str, Any]], output_path: Path, cols: int = 2) -> None:
    tiles = [tile for row in rows if (tile := comparison_tile(row)) is not None]
    if not tiles:
        return
    rows_count = int(math.ceil(len(tiles) / cols))
    cell_height, cell_width = tiles[0].shape[:2]
    sheet = np.full((rows_count * cell_height, cols * cell_width, 3), 245, dtype=np.uint8)
    for index, tile in enumerate(tiles):
        row = index // cols
        col = index % cols
        sheet[row * cell_height : (row + 1) * cell_height, col * cell_width : (col + 1) * cell_width] = tile
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), sheet)


def tighten_row(row: dict[str, Any], output_dir: Path, params: CropTighteningParams) -> dict[str, Any]:
    render_path = resolve_cloudhammer_path(str(row["render_path"]))
    image = cv2.imread(str(render_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"Could not read render image: {render_path}")
    page_height, page_width = image.shape[:2]

    bbox = box_from_row(row, "bbox_page_xyxy")
    original_crop = box_from_row(row, "crop_box_page_xyxy")
    tight_crop = tightened_crop_box_for_bbox(bbox, page_width, page_height, params)
    tight_image = crop_image(image, tight_crop)

    pdf_stem = safe_path_part(str(row.get("pdf_stem") or Path(str(row.get("pdf_path") or "unknown")).stem))
    candidate_id = safe_path_part(str(row["candidate_id"]))
    tight_path = output_dir / "tight_crops" / pdf_stem / f"{candidate_id}_tight.png"
    tight_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(tight_path), tight_image)

    output = dict(row)
    output.update(
        {
            "schema": "cloudhammer.tightened_whole_cloud_candidate.v1",
            "source_candidate_id": row["candidate_id"],
            "source_crop_image_path": str(resolve_cloudhammer_path(str(row["crop_image_path"]))),
            "tight_crop_image_path": str(tight_path),
            "original_crop_box_page_xyxy": round_box(original_crop),
            "tight_crop_box_page_xyxy": round_box(tight_crop),
            "tight_crop_width": int(tight_image.shape[1]),
            "tight_crop_height": int(tight_image.shape[0]),
            "tightening_margin_ratio": params.margin_ratio,
            "tightening_min_margin": params.min_margin,
            "tightening_max_margin": params.max_margin,
            "tightening_min_crop_side": params.min_crop_side,
        }
    )
    output.update(crop_metrics(original_crop, tight_crop, bbox))
    return output


def summarize(rows: list[dict[str, Any]], output_dir: Path, manifest_path: Path, review_log_path: Path | None) -> dict[str, Any]:
    ratios = [float(row["area_ratio_vs_original"]) for row in rows]
    reductions = [float(row["area_reduction_pct"]) for row in rows]
    return {
        "schema": "cloudhammer.tightened_whole_cloud_candidates.v1",
        "output_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "review_log_path": None if review_log_path is None else str(review_log_path),
        "tightened_candidates": len(rows),
        "by_review_status": dict(Counter(str(row.get("review_status") or "unreviewed") for row in rows)),
        "by_size_bucket": dict(Counter(str(row.get("size_bucket") or "unknown") for row in rows)),
        "by_policy_bucket": dict(Counter(str(row.get("policy_bucket") or "unknown") for row in rows)),
        "median_area_ratio_vs_original": 0.0 if not ratios else round(float(np.median(ratios)), 6),
        "median_area_reduction_pct": 0.0 if not reductions else round(float(np.median(reductions)), 2),
        "min_area_ratio_vs_original": 0.0 if not ratios else round(min(ratios), 6),
        "max_area_ratio_vs_original": 0.0 if not ratios else round(max(ratios), 6),
    }


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Tightened Whole Cloud Crops",
        "",
        f"Output dir: `{summary['output_dir']}`",
        f"Manifest: `{summary['manifest_path']}`",
        f"Review log: `{summary['review_log_path']}`",
        "",
        "## Totals",
        "",
        f"- tightened candidates: `{summary['tightened_candidates']}`",
        f"- median area ratio vs original crop: `{summary['median_area_ratio_vs_original']}`",
        f"- median area reduction: `{summary['median_area_reduction_pct']}%`",
        f"- min/max area ratio: `{summary['min_area_ratio_vs_original']}` / `{summary['max_area_ratio_vs_original']}`",
        "",
        "## Size Buckets",
        "",
        "| Bucket | Count |",
        "| --- | ---: |",
    ]
    for bucket, count in sorted(summary["by_size_bucket"].items()):
        lines.append(f"| `{bucket}` | `{count}` |")
    lines.extend(["", "## Policy Buckets", "", "| Bucket | Count |", "| --- | ---: |"])
    for bucket, count in sorted(summary["by_policy_bucket"].items()):
        lines.append(f"| `{bucket}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `tightened_candidates_manifest.jsonl`: accepted candidate rows with tight crop paths and crop metrics",
            "- `tight_crops/`: tightened crop images",
            "- `contact_sheets/before_after.png`: original crop vs tightened crop comparison",
            "- blue box: detected whole-cloud bbox",
            "- green box on original: tightened crop extent",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create tighter crop artifacts from whole-cloud candidate rows.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--review-log", type=Path, default=DEFAULT_REVIEW_LOG)
    parser.add_argument("--review-status", default="accept", help="Review status to export, or 'all'.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--margin-ratio", type=float, default=0.07)
    parser.add_argument("--min-margin", type=float, default=90.0)
    parser.add_argument("--max-margin", type=float, default=375.0)
    parser.add_argument("--min-crop-side", type=float, default=160.0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    review_log_path = args.review_log.resolve() if args.review_log else None
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = selected_rows(manifest_path, review_log_path, args.review_status)
    if args.limit > 0:
        rows = rows[: args.limit]

    params = CropTighteningParams(
        margin_ratio=args.margin_ratio,
        min_margin=args.min_margin,
        max_margin=args.max_margin,
        min_crop_side=args.min_crop_side,
    )
    tightened = [tighten_row(row, output_dir, params) for row in rows]
    write_jsonl(output_dir / "tightened_candidates_manifest.jsonl", tightened)
    if tightened:
        contact_rows = sorted(tightened, key=lambda row: (float(row["area_ratio_vs_original"]), -float(row["bbox_area"])))[:80]
        write_contact_sheet(contact_rows, output_dir / "contact_sheets" / "before_after.png")

    summary = summarize(tightened, output_dir, manifest_path, review_log_path)
    summary["params"] = params.__dict__
    write_json(output_dir / "tightened_candidates_summary.json", summary)
    write_markdown(summary, output_dir / "tightened_candidates_summary.md")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
