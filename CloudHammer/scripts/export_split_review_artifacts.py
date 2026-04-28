from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANALYSIS_DIR = (
    ROOT
    / "runs"
    / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428"
    / "split_review_analysis"
)
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "runs"
    / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428"
    / "split_review_artifacts"
)


def safe_path_part(value: str, max_length: int = 96) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = "unknown"
    return cleaned[:max_length].rstrip(" .")


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


def clip_xyxy(box: tuple[float, float, float, float], width: int, height: int) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    return (
        max(0.0, min(float(width), x1)),
        max(0.0, min(float(height), y1)),
        max(0.0, min(float(width), x2)),
        max(0.0, min(float(height), y2)),
    )


def crop_box_for_bbox(
    bbox_xyxy: tuple[float, float, float, float],
    width: int,
    height: int,
    min_margin: float,
    max_margin: float,
    margin_ratio: float,
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox_xyxy
    side = max(x2 - x1, y2 - y1)
    margin = max(min_margin, min(max_margin, side * margin_ratio))
    return clip_xyxy((x1 - margin, y1 - margin, x2 + margin, y2 + margin), width, height)


def export_crop(image, crop_xyxy: tuple[float, float, float, float], output_path: Path) -> None:
    height, width = image.shape[:2]
    x1, y1, x2, y2 = [int(round(value)) for value in crop_xyxy]
    x1 = max(0, min(width, x1))
    x2 = max(0, min(width, x2))
    y1 = max(0, min(height, y1))
    y2 = max(0, min(height, y2))
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"Invalid crop for {output_path}: {crop_xyxy}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), image[y1:y2, x1:x2])


def artifact_row_from_bbox(
    row: dict[str, Any],
    artifact_id: str,
    source_type: str,
    bbox_xyxy: tuple[float, float, float, float],
    image,
    output_dir: Path,
    min_margin: float,
    max_margin: float,
    margin_ratio: float,
) -> dict[str, Any]:
    image_height, image_width = image.shape[:2]
    crop_xyxy = crop_box_for_bbox(bbox_xyxy, image_width, image_height, min_margin, max_margin, margin_ratio)
    pdf_stem = safe_path_part(str(row.get("pdf_stem") or Path(str(row.get("pdf_path") or "unknown")).stem))
    artifact_path = output_dir / "crops" / pdf_stem / f"{safe_path_part(artifact_id)}.png"
    export_crop(image, crop_xyxy, artifact_path)
    return {
        "schema": "cloudhammer.split_review_artifact.v1",
        "artifact_id": artifact_id,
        "source_type": source_type,
        "artifact_crop_path": str(artifact_path),
        "pdf_path": row.get("pdf_path"),
        "pdf_stem": row.get("pdf_stem"),
        "page_number": row.get("page_number"),
        "render_path": row.get("render_path"),
        "bbox_page_xyxy": [round(float(value), 3) for value in bbox_xyxy],
        "bbox_page_xywh": bbox_xywh_from_xyxy(bbox_xyxy),
        "crop_box_page_xyxy": [round(float(value), 3) for value in crop_xyxy],
    }


def bbox_xywh_from_xyxy(box: tuple[float, float, float, float]) -> list[float]:
    x1, y1, x2, y2 = box
    return [round(float(x1), 3), round(float(y1), 3), round(float(x2 - x1), 3), round(float(y2 - y1), 3)]


def load_image_cache(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cache: dict[str, Any] = {}
    for row in rows:
        render_path_text = str(row.get("render_path") or "")
        if not render_path_text or render_path_text in cache:
            continue
        render_path = resolve_cloudhammer_path(render_path_text)
        image = cv2.imread(str(render_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(f"Could not load render image: {render_path}")
        cache[render_path_text] = image
    return cache


def selected_split_artifacts(
    selected_groups: list[dict[str, Any]],
    output_dir: Path,
    min_margin: float,
    max_margin: float,
    margin_ratio: float,
) -> list[dict[str, Any]]:
    images = load_image_cache(selected_groups)
    output: list[dict[str, Any]] = []
    for row in selected_groups:
        bbox = tuple(float(value) for value in row["bbox_page_xyxy"])
        image = images[str(row["render_path"])]
        artifact = artifact_row_from_bbox(
            row,
            artifact_id=str(row["split_group_id"]),
            source_type="selected_split_group",
            bbox_xyxy=bbox,
            image=image,
            output_dir=output_dir,
            min_margin=min_margin,
            max_margin=max_margin,
            margin_ratio=margin_ratio,
        )
        artifact.update(
            {
                "bbox_page_xywh": bbox_xywh_from_xyxy(bbox),
                "parent_candidate_id": row.get("parent_candidate_id"),
                "split_variant_name": row.get("split_variant_name"),
                "split_variant_index": row.get("split_variant_index"),
                "split_group_index": row.get("split_group_index"),
                "member_count": row.get("member_count"),
                "member_indexes": row.get("member_indexes"),
                "confidence": row.get("confidence"),
                "group_fill_ratio": row.get("group_fill_ratio"),
            }
        )
        output.append(artifact)
    return output


def current_ok_artifacts(
    current_ok_rows: list[dict[str, Any]],
    output_dir: Path,
    min_margin: float,
    max_margin: float,
    margin_ratio: float,
) -> list[dict[str, Any]]:
    images = load_image_cache(current_ok_rows)
    output: list[dict[str, Any]] = []
    for row in current_ok_rows:
        bbox = tuple(float(value) for value in row["bbox_page_xyxy"])
        image = images[str(row["render_path"])]
        artifact = artifact_row_from_bbox(
            row,
            artifact_id=f"{row['candidate_id']}_current_ok",
            source_type="current_ok_candidate",
            bbox_xyxy=bbox,
            image=image,
            output_dir=output_dir,
            min_margin=min_margin,
            max_margin=max_margin,
            margin_ratio=margin_ratio,
        )
        artifact.update(
            {
                "bbox_page_xywh": bbox_xywh_from_xyxy(bbox),
                "parent_candidate_id": row.get("candidate_id"),
                "member_count": row.get("member_count"),
                "confidence": row.get("whole_cloud_confidence"),
                "group_fill_ratio": row.get("group_fill_ratio"),
            }
        )
        output.append(artifact)
    return output


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Split Review Artifacts",
        "",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Totals",
        "",
        f"- selected split group crops: `{summary['selected_split_group_crops']}`",
        f"- current-ok crops: `{summary['current_ok_crops']}`",
        f"- total resolved crops: `{summary['total_resolved_crops']}`",
        "",
        "## By Source Type",
        "",
        "| Source Type | Count |",
        "| --- | ---: |",
    ]
    for source_type, count in sorted(summary["by_source_type"].items()):
        lines.append(f"| `{source_type}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `resolved_split_artifacts.jsonl`: selected split groups plus current-ok candidates",
            "- `selected_split_group_artifacts.jsonl`: one crop per selected split group",
            "- `current_ok_artifacts.jsonl`: current groups that were marked good as-is",
            "- `crops/`: rendered crop images for inspection",
            "- `contact_sheets/resolved_split_artifacts.png`: quick visual scan of resolved crops",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def thumbnail_for_row(row: dict[str, Any], thumb_size: int) -> np.ndarray | None:
    image = cv2.imread(str(row["artifact_crop_path"]), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    height, width = image.shape[:2]
    scale = min(thumb_size / max(1, width), thumb_size / max(1, height))
    resized = cv2.resize(image, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA)
    canvas = np.full((thumb_size + 52, thumb_size, 3), 255, dtype=np.uint8)
    y = (thumb_size - resized.shape[0]) // 2
    x = (thumb_size - resized.shape[1]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)
    label = f"{str(row.get('source_type', ''))[:13]} n={row.get('member_count', '')}"
    cv2.putText(canvas, label, (5, thumb_size + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(
        canvas,
        str(row.get("artifact_id", ""))[-34:],
        (5, thumb_size + 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.36,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )
    return canvas


def write_contact_sheet(rows: list[dict[str, Any]], output_path: Path, thumb_size: int = 260, cols: int = 5) -> None:
    thumbs = [thumb for row in rows if (thumb := thumbnail_for_row(row, thumb_size)) is not None]
    if not thumbs:
        return
    row_count = int(np.ceil(len(thumbs) / cols))
    cell_height, cell_width = thumbs[0].shape[:2]
    sheet = np.full((row_count * cell_height, cols * cell_width, 3), 245, dtype=np.uint8)
    for index, thumb in enumerate(thumbs):
        row = index // cols
        col = index % cols
        sheet[row * cell_height : (row + 1) * cell_height, col * cell_width : (col + 1) * cell_width] = thumb
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), sheet)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export crop artifacts from accepted split-review proposals.")
    parser.add_argument("--analysis-dir", type=Path, default=DEFAULT_ANALYSIS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-margin", type=float, default=90.0)
    parser.add_argument("--max-margin", type=float, default=450.0)
    parser.add_argument("--margin-ratio", type=float, default=0.12)
    args = parser.parse_args()

    analysis_dir = args.analysis_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_groups = list(read_jsonl(analysis_dir / "selected_split_groups.jsonl"))
    current_ok_rows = list(read_jsonl(analysis_dir / "current_ok_candidates.jsonl"))
    selected_artifacts = selected_split_artifacts(
        selected_groups,
        output_dir,
        min_margin=args.min_margin,
        max_margin=args.max_margin,
        margin_ratio=args.margin_ratio,
    )
    current_ok = current_ok_artifacts(
        current_ok_rows,
        output_dir,
        min_margin=args.min_margin,
        max_margin=args.max_margin,
        margin_ratio=args.margin_ratio,
    )
    resolved = selected_artifacts + current_ok

    write_jsonl(output_dir / "selected_split_group_artifacts.jsonl", selected_artifacts)
    write_jsonl(output_dir / "current_ok_artifacts.jsonl", current_ok)
    write_jsonl(output_dir / "resolved_split_artifacts.jsonl", resolved)
    write_contact_sheet(resolved, output_dir / "contact_sheets" / "resolved_split_artifacts.png")

    summary = {
        "schema": "cloudhammer.split_review_artifacts.v1",
        "analysis_dir": str(analysis_dir),
        "output_dir": str(output_dir),
        "params": {
            "min_margin": args.min_margin,
            "max_margin": args.max_margin,
            "margin_ratio": args.margin_ratio,
        },
        "selected_split_group_crops": len(selected_artifacts),
        "current_ok_crops": len(current_ok),
        "total_resolved_crops": len(resolved),
        "by_source_type": dict(Counter(str(row.get("source_type")) for row in resolved)),
    }
    write_json(output_dir / "split_review_artifacts_summary.json", summary)
    write_markdown(summary, output_dir / "split_review_artifacts_summary.md")

    print(f"wrote {output_dir / 'split_review_artifacts_summary.md'}")
    print(
        json.dumps(
            {
                "selected_split_group_crops": len(selected_artifacts),
                "current_ok_crops": len(current_ok),
                "total_resolved_crops": len(resolved),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
