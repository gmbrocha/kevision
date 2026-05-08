from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from apply_postprocessing_non_frozen import DEFAULT_OUTPUT_DIR as DEFAULT_APPLY_DIR
from build_postprocessing_dry_run_plan import (
    DEFAULT_FROZEN_MANIFEST,
    box_area,
    box_from_candidate,
    candidate_page_keys,
    frozen_page_keys,
    project_path,
    read_jsonl,
    round_box,
    write_json,
    write_jsonl,
    xyxy_to_xywh,
)


DEFAULT_INPUT_MANIFEST = DEFAULT_APPLY_DIR / "postprocessed_non_frozen_candidates_manifest.jsonl"
DEFAULT_OUTPUT_DIR = DEFAULT_APPLY_DIR / "crop_regeneration_20260508"
REGENERATE_STATUS = "needs_regeneration_for_postprocessed_bbox"
REGENERATED_STATUS = "postprocessed_crop_regenerated"
PRESERVED_STATUS = "source_crop_preserved"

# Rasterized drawing pages are expected to exceed Pillow's default web-image
# safety threshold; these are local project artifacts, not untrusted uploads.
Image.MAX_IMAGE_PIXELS = None


def safe_stem(value: str, *, max_len: int = 96) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value).strip("_")
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("._-")
    return f"{cleaned}_{digest}" if cleaned else digest


def size_bucket_for_box(box_xywh: list[float]) -> str:
    side = max(float(box_xywh[2]), float(box_xywh[3]))
    if side < 800.0:
        return "small"
    if side < 2200.0:
        return "medium"
    if side < 5200.0:
        return "large"
    return "xlarge"


def crop_box_for_bbox(
    bbox_xyxy: list[float],
    page_width: int,
    page_height: int,
    *,
    crop_margin_ratio: float,
    min_crop_margin: float,
    max_crop_margin: float,
) -> list[float]:
    width = bbox_xyxy[2] - bbox_xyxy[0]
    height = bbox_xyxy[3] - bbox_xyxy[1]
    side = max(width, height)
    margin = max(min_crop_margin, min(max_crop_margin, side * crop_margin_ratio))
    return [
        max(0.0, bbox_xyxy[0] - margin),
        max(0.0, bbox_xyxy[1] - margin),
        min(float(page_width), bbox_xyxy[2] + margin),
        min(float(page_height), bbox_xyxy[3] + margin),
    ]


def pixel_crop_box(crop_xyxy: list[float], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    image_width, image_height = image_size
    left = max(0, min(image_width, int(round(crop_xyxy[0]))))
    top = max(0, min(image_height, int(round(crop_xyxy[1]))))
    right = max(0, min(image_width, int(round(crop_xyxy[2]))))
    bottom = max(0, min(image_height, int(round(crop_xyxy[3]))))
    if right <= left or bottom <= top:
        raise ValueError(f"Invalid pixel crop box: {crop_xyxy} -> {(left, top, right, bottom)}")
    return (left, top, right, bottom)


def image_stats(image: Image.Image) -> dict[str, Any]:
    gray = image.convert("L")
    stat = ImageStat.Stat(gray)
    extrema = stat.extrema[0]
    return {
        "pixel_width": image.width,
        "pixel_height": image.height,
        "grayscale_min": int(extrema[0]),
        "grayscale_max": int(extrema[1]),
        "grayscale_mean": round(float(stat.mean[0]), 3),
        "grayscale_stddev": round(float(stat.stddev[0]), 3),
    }


def validate_input_rows(rows: list[dict[str, Any]], frozen_manifest: Path) -> None:
    errors: list[str] = []
    candidate_ids = [str(row.get("candidate_id") or "") for row in rows]
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("input manifest contains duplicate candidate_id values")
    frozen_keys = frozen_page_keys(frozen_manifest)
    frozen_violations = [
        str(row.get("candidate_id"))
        for row in rows
        if candidate_page_keys(row) & frozen_keys
    ]
    if frozen_violations:
        errors.append(f"frozen page guard violation: {frozen_violations[:20]}")
    for row in rows:
        candidate_id = row.get("candidate_id")
        try:
            box = box_from_candidate(row)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if box[2] <= box[0] or box[3] <= box[1]:
            errors.append(f"{candidate_id}: non-positive bbox")
    if errors:
        raise ValueError("Invalid crop regeneration input:\n" + "\n".join(errors[:30]))


def load_image_sizes(render_paths: list[Path]) -> tuple[dict[str, tuple[int, int]], list[str]]:
    sizes: dict[str, tuple[int, int]] = {}
    warnings: list[str] = []
    for render_path in sorted(set(render_paths)):
        if not render_path.exists():
            raise FileNotFoundError(f"Render image not found: {render_path}")
        with Image.open(render_path) as image:
            sizes[str(render_path)] = image.size
            if image.width <= 0 or image.height <= 0:
                warnings.append(f"render image has invalid size: {render_path}")
    return sizes, warnings


def build_crop_plan(
    rows: list[dict[str, Any]],
    *,
    output_dir: Path,
    crop_margin_ratio: float,
    min_crop_margin: float,
    max_crop_margin: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    target_rows = [row for row in rows if row.get("crop_status") == REGENERATE_STATUS]
    render_paths: list[Path] = []
    for row in target_rows:
        render_path = project_path(row.get("render_path"))
        if render_path is None:
            raise FileNotFoundError(f"{row.get('candidate_id')}: missing render_path")
        render_paths.append(render_path)
    image_sizes, warnings = load_image_sizes(render_paths)

    crop_paths: set[str] = set()
    plan_rows: list[dict[str, Any]] = []
    for index, row in enumerate(target_rows, start=1):
        candidate_id = str(row["candidate_id"])
        render_path = project_path(row.get("render_path"))
        if render_path is None:
            raise FileNotFoundError(f"{candidate_id}: missing render_path")
        image_size = image_sizes[str(render_path)]
        row_width = row.get("page_width")
        row_height = row.get("page_height")
        if row_width not in (None, "") and row_height not in (None, ""):
            if int(row_width) != image_size[0] or int(row_height) != image_size[1]:
                warnings.append(
                    f"{candidate_id}: manifest page size {row_width}x{row_height} "
                    f"does not match render {image_size[0]}x{image_size[1]}"
                )
        bbox_xyxy = box_from_candidate(row)
        bbox_xywh = xyxy_to_xywh(bbox_xyxy)
        size_bucket = size_bucket_for_box(bbox_xywh)
        crop_xyxy = crop_box_for_bbox(
            bbox_xyxy,
            image_size[0],
            image_size[1],
            crop_margin_ratio=crop_margin_ratio,
            min_crop_margin=min_crop_margin,
            max_crop_margin=max_crop_margin,
        )
        crop_xywh = xyxy_to_xywh(crop_xyxy)
        crop_pixel_box = pixel_crop_box(crop_xyxy, image_size)
        page_dir = output_dir / "crops" / safe_stem(str(row.get("source_page_key") or Path(str(render_path)).stem), max_len=72)
        crop_path = page_dir / f"{index:03d}_{safe_stem(candidate_id, max_len=92)}_{size_bucket}.png"
        crop_path_key = str(crop_path)
        if crop_path_key in crop_paths:
            raise ValueError(f"Duplicate planned crop path: {crop_path}")
        crop_paths.add(crop_path_key)
        plan_rows.append(
            {
                "schema": "cloudhammer_v2.postprocessed_crop_regeneration_plan.v1",
                "candidate_id": candidate_id,
                "source_page_key": row.get("source_page_key") or "",
                "postprocessing_action": row.get("postprocessing_action") or "",
                "input_crop_status": row.get("crop_status") or "",
                "output_crop_status": REGENERATED_STATUS,
                "render_path": str(render_path),
                "crop_image_path": str(crop_path.resolve()),
                "size_bucket": size_bucket,
                "bbox_page_xyxy": round_box(bbox_xyxy),
                "bbox_page_xywh": round_box(bbox_xywh),
                "crop_box_page_xyxy": round_box(crop_xyxy),
                "crop_box_page_xywh": round_box(crop_xywh),
                "crop_width": round(float(crop_xywh[2]), 3),
                "crop_height": round(float(crop_xywh[3]), 3),
                "crop_area": round(float(crop_xywh[2]) * float(crop_xywh[3]), 3),
                "page_width": image_size[0],
                "page_height": image_size[1],
                "pixel_crop_box": list(crop_pixel_box),
            }
        )
    return plan_rows, warnings


def apply_crop_plan(
    rows: list[dict[str, Any]],
    plan_rows: list[dict[str, Any]],
    *,
    overwrite: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    plan_by_id = {str(row["candidate_id"]): row for row in plan_rows}
    records_by_render: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for plan in plan_rows:
        crop_path = Path(str(plan["crop_image_path"]))
        if crop_path.exists() and not overwrite:
            raise FileExistsError(f"Crop already exists; pass --overwrite to replace: {crop_path}")
        records_by_render[str(plan["render_path"])].append(plan)

    for render_path_value, records in records_by_render.items():
        with Image.open(render_path_value) as page_image:
            for record in records:
                crop_path = Path(str(record["crop_image_path"]))
                pixel_box = tuple(int(value) for value in record["pixel_crop_box"])
                crop = page_image.crop(pixel_box)
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                crop.save(crop_path)
                stats = image_stats(crop)
                record.update(stats)
                if stats["grayscale_min"] == stats["grayscale_max"]:
                    warnings.append(f"{record['candidate_id']}: regenerated crop has flat pixel values")

    output_rows: list[dict[str, Any]] = []
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        output = dict(row)
        bbox_xyxy = box_from_candidate(output)
        bbox_xywh = xyxy_to_xywh(bbox_xyxy)
        output.setdefault("size_bucket", size_bucket_for_box(bbox_xywh))
        if candidate_id in plan_by_id:
            plan = plan_by_id[candidate_id]
            output.update(
                {
                    "crop_status": REGENERATED_STATUS,
                    "crop_image_path": plan["crop_image_path"],
                    "crop_box_page_xyxy": plan["crop_box_page_xyxy"],
                    "crop_box_page_xywh": plan["crop_box_page_xywh"],
                    "crop_width": plan["crop_width"],
                    "crop_height": plan["crop_height"],
                    "crop_area": plan["crop_area"],
                    "size_bucket": plan["size_bucket"],
                    "crop_regeneration_provenance": {
                        "script": "CloudHammer_v2/scripts/regenerate_postprocessed_non_frozen_crops.py",
                        "plan_schema": plan["schema"],
                        "generated_date": "2026-05-08",
                        "input_crop_status": plan["input_crop_status"],
                    },
                }
            )
        elif output.get("crop_status") == PRESERVED_STATUS:
            crop_path = project_path(output.get("crop_image_path"))
            if crop_path is None or not crop_path.exists():
                warnings.append(f"{candidate_id}: preserved source crop is missing: {output.get('crop_image_path')}")
        output_rows.append(output)
    return output_rows, plan_rows, warnings


def build_summary(
    *,
    input_manifest: Path,
    output_dir: Path,
    rows: list[dict[str, Any]],
    plan_rows: list[dict[str, Any]],
    output_rows: list[dict[str, Any]] | None,
    warnings: list[str],
    dry_run: bool,
    crop_margin_ratio: float,
    min_crop_margin: float,
    max_crop_margin: float,
) -> dict[str, Any]:
    output_crop_status = Counter(str(row.get("crop_status") or "") for row in (output_rows or rows))
    summary: dict[str, Any] = {
        "schema": "cloudhammer_v2.postprocessed_crop_regeneration_summary.v1",
        "status": "dry_run_only" if dry_run else "regenerated_crop_manifest_written",
        "input_manifest": str(input_manifest),
        "output_dir": str(output_dir),
        "crop_dir": str(output_dir / "crops"),
        "output_manifest": None
        if dry_run
        else str(output_dir / "postprocessed_non_frozen_candidates_manifest.regenerated_crops.jsonl"),
        "candidate_count": len(rows),
        "regeneration_targets": len(plan_rows),
        "preserved_source_crops": sum(1 for row in rows if row.get("crop_status") == PRESERVED_STATUS),
        "input_crop_status": dict(sorted(Counter(str(row.get("crop_status") or "") for row in rows).items())),
        "output_crop_status": dict(sorted(output_crop_status.items())),
        "targets_by_postprocessing_action": dict(
            sorted(Counter(str(row.get("postprocessing_action") or "") for row in plan_rows).items())
        ),
        "targets_by_size_bucket": dict(sorted(Counter(str(row.get("size_bucket") or "") for row in plan_rows).items())),
        "crop_params": {
            "crop_margin_ratio": crop_margin_ratio,
            "min_crop_margin": min_crop_margin,
            "max_crop_margin": max_crop_margin,
        },
        "warnings": warnings,
        "guardrails": [
            "derived_crop_manifest_only",
            "non_frozen_postprocessed_manifest_only",
            "no_source_candidate_manifest_edits",
            "no_truth_label_edits",
            "no_eval_manifest_edits",
            "no_prediction_file_edits",
            "no_model_file_edits",
            "no_dataset_or_training_data_writes",
            "not_threshold_tuning",
            "excluded_page_disjoint_real_frozen_pages",
        ],
    }
    if output_rows:
        summary["regenerated_crops_written"] = sum(
            1 for row in output_rows if row.get("crop_status") == REGENERATED_STATUS
        )
    else:
        summary["regenerated_crops_written"] = 0
    return summary


def markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# Postprocessed Non-Frozen Crop Regeneration",
        "",
        f"Status: `{summary['status']}`",
        "",
        "Purpose: regenerate crop images for postprocessed non-frozen candidates whose boxes changed after reviewed postprocessing.",
        "",
        "Safety: this writes derived crop artifacts only. It does not edit source candidate manifests, labels, eval manifests, predictions, model files, datasets, training data, or threshold-tuning inputs.",
        "",
        "## Counts",
        "",
        f"- candidates in input manifest: `{summary['candidate_count']}`",
        f"- regeneration targets: `{summary['regeneration_targets']}`",
        f"- regenerated crops written: `{summary['regenerated_crops_written']}`",
        f"- preserved source crops: `{summary['preserved_source_crops']}`",
        "",
        "## Input Crop Status",
        "",
    ]
    for key, value in summary["input_crop_status"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Output Crop Status", ""])
    for key, value in summary["output_crop_status"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Target Actions", ""])
    for key, value in summary["targets_by_postprocessing_action"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Artifacts", ""])
    lines.append(f"- `{Path(summary['output_dir']) / 'postprocessed_non_frozen_crop_regeneration_plan.jsonl'}`")
    if summary["output_manifest"]:
        lines.append(f"- `{summary['output_manifest']}`")
        lines.append(f"- `{Path(summary['output_dir']) / 'postprocessed_non_frozen_crop_regeneration_records.jsonl'}`")
        lines.append(f"- `{summary['crop_dir']}`")
    lines.append(f"- `{Path(summary['output_dir']) / 'postprocessed_non_frozen_crop_regeneration_summary.json'}`")
    lines.append(f"- `{Path(summary['output_dir']) / 'postprocessed_non_frozen_crop_regeneration_summary.md'}`")
    lines.extend(["", "## Warnings", ""])
    if summary["warnings"]:
        for warning in summary["warnings"]:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "Next step: use the crop-ready regenerated manifest for any crop-based inspection or export wiring.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate crops for derived non-frozen postprocessed candidates."
    )
    parser.add_argument("--input-manifest", type=Path, default=DEFAULT_INPUT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--frozen-manifest", type=Path, default=DEFAULT_FROZEN_MANIFEST)
    parser.add_argument("--crop-margin-ratio", type=float, default=0.16)
    parser.add_argument("--min-crop-margin", type=float, default=550.0)
    parser.add_argument("--max-crop-margin", type=float, default=950.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    input_manifest = args.input_manifest
    output_dir = args.output_dir
    rows = read_jsonl(input_manifest)
    validate_input_rows(rows, args.frozen_manifest)
    plan_rows, warnings = build_crop_plan(
        rows,
        output_dir=output_dir,
        crop_margin_ratio=args.crop_margin_ratio,
        min_crop_margin=args.min_crop_margin,
        max_crop_margin=args.max_crop_margin,
    )
    output_rows: list[dict[str, Any]] | None = None
    if not args.dry_run:
        output_rows, record_rows, apply_warnings = apply_crop_plan(
            rows,
            plan_rows,
            overwrite=args.overwrite,
        )
        warnings.extend(apply_warnings)
    else:
        record_rows = plan_rows

    summary = build_summary(
        input_manifest=input_manifest,
        output_dir=output_dir,
        rows=rows,
        plan_rows=plan_rows,
        output_rows=output_rows,
        warnings=warnings,
        dry_run=args.dry_run,
        crop_margin_ratio=args.crop_margin_ratio,
        min_crop_margin=args.min_crop_margin,
        max_crop_margin=args.max_crop_margin,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "postprocessed_non_frozen_crop_regeneration_plan.jsonl", plan_rows)
    if output_rows is not None:
        write_jsonl(
            output_dir / "postprocessed_non_frozen_candidates_manifest.regenerated_crops.jsonl",
            output_rows,
        )
        write_jsonl(output_dir / "postprocessed_non_frozen_crop_regeneration_records.jsonl", record_rows)
    write_json(output_dir / "postprocessed_non_frozen_crop_regeneration_summary.json", summary)
    (output_dir / "postprocessed_non_frozen_crop_regeneration_summary.md").write_text(
        markdown_summary(summary), encoding="utf-8"
    )

    print("Postprocessed non-frozen crop regeneration")
    print(f"- status: {summary['status']}")
    print(f"- candidates: {summary['candidate_count']}")
    print(f"- regeneration_targets: {summary['regeneration_targets']}")
    print(f"- regenerated_crops_written: {summary['regenerated_crops_written']}")
    print(f"- output_dir: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
