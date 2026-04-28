from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.contracts.detections import xywh_to_xyxy, xyxy_to_xywh
from cloudhammer.infer.whole_clouds import WholeCloudExportParams, confidence_tier, size_bucket_for_box
from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs" / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428"
DEFAULT_POLICY_INPUT = DEFAULT_RUN / "policy_v1" / "candidates_with_policy.jsonl"
DEFAULT_SPLIT_ANALYSIS_DIR = DEFAULT_RUN / "split_review_analysis"
DEFAULT_SPLIT_ARTIFACTS = DEFAULT_RUN / "split_review_artifacts" / "resolved_split_artifacts.jsonl"
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "corrected_candidates_v1"


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


def image_shape(path_text: str) -> tuple[int, int]:
    image = cv2.imread(str(resolve_cloudhammer_path(path_text)), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {path_text}")
    height, width = image.shape[:2]
    return int(width), int(height)


def round_box(box: list[float] | tuple[float, float, float, float], digits: int = 3) -> list[float]:
    return [round(float(value), digits) for value in box]


def normalize_original_candidate(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["correction_source"] = "original_candidate"
    normalized["corrected_candidate_id"] = row["candidate_id"]
    normalized["is_split_replacement"] = False
    normalized["is_unresolved_split_parent"] = False
    return normalized


def normalize_split_artifact(row: dict[str, Any], params: WholeCloudExportParams) -> dict[str, Any]:
    crop_path = str(row["artifact_crop_path"])
    render_path = str(row["render_path"])
    crop_width, crop_height = image_shape(crop_path)
    page_width, page_height = image_shape(render_path)
    bbox_xyxy = tuple(float(value) for value in row["bbox_page_xyxy"])
    bbox_xywh = row.get("bbox_page_xywh")
    if not isinstance(bbox_xywh, list) or len(bbox_xywh) != 4:
        bbox_xywh = xyxy_to_xywh(bbox_xyxy)
    crop_xyxy = tuple(float(value) for value in row["crop_box_page_xyxy"])
    crop_xywh = xyxy_to_xywh(crop_xyxy)
    width = float(bbox_xywh[2])
    height = float(bbox_xywh[3])
    whole_confidence = float(row.get("confidence") or 0.0)
    candidate_id = str(row["artifact_id"])
    return {
        "schema": "cloudhammer.whole_cloud_candidate.corrected.v1",
        "candidate_id": candidate_id,
        "corrected_candidate_id": candidate_id,
        "parent_candidate_id": row.get("parent_candidate_id"),
        "correction_source": row.get("source_type"),
        "is_split_replacement": True,
        "is_unresolved_split_parent": False,
        "pdf_path": row.get("pdf_path"),
        "pdf_stem": row.get("pdf_stem"),
        "page_number": row.get("page_number"),
        "render_path": render_path,
        "crop_image_path": crop_path,
        "source_mode": row.get("source_type"),
        "confidence": round(whole_confidence, 6),
        "whole_cloud_confidence": round(whole_confidence, 6),
        "confidence_tier": confidence_tier(whole_confidence),
        "size_bucket": size_bucket_for_box([float(value) for value in bbox_xywh], params),
        "bbox_page_xywh": round_box(bbox_xywh),
        "bbox_page_xyxy": round_box(bbox_xyxy),
        "crop_box_page_xywh": round_box(crop_xywh),
        "crop_box_page_xyxy": round_box(crop_xyxy),
        "bbox_width": round(width, 3),
        "bbox_height": round(height, 3),
        "bbox_area": round(width * height, 3),
        "crop_width": crop_width,
        "crop_height": crop_height,
        "crop_area": crop_width * crop_height,
        "page_width": page_width,
        "page_height": page_height,
        "member_count": int(row.get("member_count") or 1),
        "member_indexes": row.get("member_indexes"),
        "member_confidences": [],
        "member_boxes_page_xyxy": [],
        "group_fill_ratio": row.get("group_fill_ratio"),
        "review_status": "accept",
        "review_source": "split_review",
        "split_variant_name": row.get("split_variant_name"),
        "split_variant_index": row.get("split_variant_index"),
        "split_group_index": row.get("split_group_index"),
        "parent_whole_cloud_confidence": row.get("parent_whole_cloud_confidence"),
    }


def build_corrected_rows(
    policy_rows: list[dict[str, Any]],
    split_artifact_rows: list[dict[str, Any]],
    unresolved_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    split_parent_ids = {str(row.get("parent_candidate_id")) for row in split_artifact_rows if row.get("parent_candidate_id")}
    split_parent_ids.update(str(row.get("candidate_id")) for row in unresolved_rows if row.get("candidate_id"))
    kept_original = [
        normalize_original_candidate(row)
        for row in policy_rows
        if str(row.get("candidate_id")) not in split_parent_ids
    ]
    params = WholeCloudExportParams()
    replacements = [normalize_split_artifact(row, params) for row in split_artifact_rows]
    unresolved = [dict(row, is_unresolved_split_parent=True, correction_source="still_overmerged") for row in unresolved_rows]
    corrected = sorted(
        kept_original + replacements,
        key=lambda row: (str(row.get("pdf_stem")), int(row.get("page_number") or 0), str(row.get("candidate_id"))),
    )
    return corrected, kept_original, unresolved


def summarize(
    corrected: list[dict[str, Any]],
    kept_original: list[dict[str, Any]],
    replacements: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    accepted_corrected: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    by_source = Counter(str(row.get("correction_source")) for row in corrected)
    by_size = Counter(str(row.get("size_bucket")) for row in corrected)
    by_tier = Counter(str(row.get("confidence_tier")) for row in corrected)
    return {
        "schema": "cloudhammer.corrected_whole_cloud_candidates.v1",
        "output_dir": str(output_dir),
        "corrected_candidates": len(corrected),
        "kept_original_candidates": len(kept_original),
        "split_replacement_candidates": len(replacements),
        "unresolved_split_parents": len(unresolved),
        "human_accepted_corrected_candidates": len(accepted_corrected),
        "by_correction_source": dict(by_source),
        "by_size_bucket": dict(by_size),
        "by_confidence_tier": dict(by_tier),
    }


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Corrected Whole Cloud Candidates v1",
        "",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Totals",
        "",
        f"- corrected candidates: `{summary['corrected_candidates']}`",
        f"- kept original candidates: `{summary['kept_original_candidates']}`",
        f"- split replacement candidates: `{summary['split_replacement_candidates']}`",
        f"- unresolved split parents quarantined: `{summary['unresolved_split_parents']}`",
        f"- human-accepted corrected candidates: `{summary['human_accepted_corrected_candidates']}`",
        "",
        "## By Correction Source",
        "",
        "| Source | Count |",
        "| --- | ---: |",
    ]
    for source, count in sorted(summary["by_correction_source"].items()):
        lines.append(f"| `{source}` | `{count}` |")
    lines.extend(["", "## By Size Bucket", "", "| Bucket | Count |", "| --- | ---: |"])
    for bucket, count in sorted(summary["by_size_bucket"].items()):
        lines.append(f"| `{bucket}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `corrected_whole_cloud_candidates.jsonl`: original candidates with solved split-risk parents replaced",
            "- `kept_original_candidates.jsonl`: candidates retained from the prior run",
            "- `split_replacement_candidates.jsonl`: selected split/current-ok replacement candidates",
            "- `unresolved_split_parent_candidates.jsonl`: still-overmerged parents excluded from corrected candidates",
            "- `human_accepted_corrected_candidates.jsonl`: accepted original candidates plus selected split replacements",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build corrected whole-cloud candidate manifest after split review.")
    parser.add_argument("--policy-input", type=Path, default=DEFAULT_POLICY_INPUT)
    parser.add_argument("--split-artifacts", type=Path, default=DEFAULT_SPLIT_ARTIFACTS)
    parser.add_argument("--split-analysis-dir", type=Path, default=DEFAULT_SPLIT_ANALYSIS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    policy_input = args.policy_input.resolve()
    split_artifacts = args.split_artifacts.resolve()
    split_analysis_dir = args.split_analysis_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    policy_rows = list(read_jsonl(policy_input))
    split_artifact_rows = list(read_jsonl(split_artifacts))
    unresolved_rows = list(read_jsonl(split_analysis_dir / "still_overmerged_candidates.jsonl"))
    corrected, kept_original, unresolved = build_corrected_rows(policy_rows, split_artifact_rows, unresolved_rows)
    replacements = [row for row in corrected if row.get("is_split_replacement")]
    accepted_corrected = [
        row
        for row in corrected
        if row.get("is_split_replacement") or row.get("review_status") == "accept"
    ]

    write_jsonl(output_dir / "corrected_whole_cloud_candidates.jsonl", corrected)
    write_jsonl(output_dir / "kept_original_candidates.jsonl", kept_original)
    write_jsonl(output_dir / "split_replacement_candidates.jsonl", replacements)
    write_jsonl(output_dir / "unresolved_split_parent_candidates.jsonl", unresolved)
    write_jsonl(output_dir / "human_accepted_corrected_candidates.jsonl", accepted_corrected)
    summary = summarize(corrected, kept_original, replacements, unresolved, accepted_corrected, output_dir)
    summary["policy_input"] = str(policy_input)
    summary["split_artifacts"] = str(split_artifacts)
    summary["split_analysis_dir"] = str(split_analysis_dir)
    write_json(output_dir / "corrected_whole_cloud_candidates_summary.json", summary)
    write_markdown(summary, output_dir / "corrected_whole_cloud_candidates_summary.md")

    print(f"wrote {output_dir / 'corrected_whole_cloud_candidates_summary.md'}")
    print(
        json.dumps(
            {
                "corrected_candidates": len(corrected),
                "kept_original_candidates": len(kept_original),
                "split_replacement_candidates": len(replacements),
                "unresolved_split_parents": len(unresolved),
                "human_accepted_corrected_candidates": len(accepted_corrected),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
