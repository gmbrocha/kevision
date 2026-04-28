from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2

from cloudhammer.contracts.detections import CloudDetection, DetectionPage, clip_xywh, xywh_to_xyxy, xyxy_to_xywh
from cloudhammer.manifests import write_jsonl
from cloudhammer.page_catalog import stable_page_key


XYXY = tuple[float, float, float, float]


@dataclass(frozen=True)
class WholeCloudExportParams:
    crop_margin_ratio: float = 0.12
    min_crop_margin: float = 48.0
    max_crop_margin: float = 650.0
    min_candidate_confidence: float = 0.0
    min_box_side: float = 20.0
    small_max_side: float = 800.0
    medium_max_side: float = 2200.0
    large_max_side: float = 5200.0


def area_xyxy(box: XYXY) -> float:
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def iou_xyxy(left: XYXY, right: XYXY) -> float:
    lx1, ly1, lx2, ly2 = left
    rx1, ry1, rx2, ry2 = right
    intersection = area_xyxy((max(lx1, rx1), max(ly1, ry1), min(lx2, rx2), min(ly2, ry2)))
    union = area_xyxy(left) + area_xyxy(right) - intersection
    return 0.0 if union <= 0 else intersection / union


def containment_xyxy(inner: XYXY, outer: XYXY) -> float:
    intersection = area_xyxy(
        (max(inner[0], outer[0]), max(inner[1], outer[1]), min(inner[2], outer[2]), min(inner[3], outer[3]))
    )
    inner_area = area_xyxy(inner)
    return 0.0 if inner_area <= 0 else intersection / inner_area


def round_box(box: XYXY | list[float], digits: int = 3) -> list[float]:
    return [round(float(value), digits) for value in box]


def size_bucket_for_box(box_xywh: list[float], params: WholeCloudExportParams) -> str:
    _, _, width, height = box_xywh
    side = max(width, height)
    if side < params.small_max_side:
        return "small"
    if side < params.medium_max_side:
        return "medium"
    if side < params.large_max_side:
        return "large"
    return "xlarge"


def crop_box_for_candidate(
    bbox_page: list[float],
    image_width: int,
    image_height: int,
    params: WholeCloudExportParams,
) -> list[float]:
    x, y, width, height = bbox_page
    side = max(width, height)
    margin = max(params.min_crop_margin, min(params.max_crop_margin, side * params.crop_margin_ratio))
    return clip_xywh([x - margin, y - margin, width + 2 * margin, height + 2 * margin], image_width, image_height)


def whole_cloud_confidence(group: CloudDetection, image_width: int, image_height: int) -> float:
    member_confidences = [float(value) for value in group.metadata.get("member_confidences", [])]
    if not member_confidences:
        member_confidences = [float(group.confidence)]
    member_count = max(1, int(group.metadata.get("member_count", len(member_confidences))))
    max_confidence = max(member_confidences)
    mean_confidence = sum(member_confidences) / len(member_confidences)
    member_bonus = min(0.12, math.log2(member_count + 1) * 0.035)
    page_area = max(1.0, float(image_width * image_height))
    box_area_ratio = area_xyxy(xywh_to_xyxy(group.bbox_page)) / page_area
    page_span_penalty = 0.0
    if box_area_ratio > 0.35:
        page_span_penalty += 0.08
    if member_count == 1:
        member_bonus *= 0.35
    return max(0.0, min(1.0, 0.62 * max_confidence + 0.38 * mean_confidence + member_bonus - page_span_penalty))


def crop_id_for_page(page: DetectionPage, index: int) -> str:
    if page.render_path:
        return f"{Path(page.render_path).stem}_whole_{index:03d}"
    return f"{stable_page_key(Path(page.pdf), page.page - 1)}_whole_{index:03d}"


def export_candidate_crop(image, crop_xywh: list[float], output_path: Path) -> None:
    height, width = image.shape[:2]
    x, y, w, h = [int(round(value)) for value in crop_xywh]
    x0 = max(0, min(width, x))
    y0 = max(0, min(height, y))
    x1 = max(0, min(width, x + w))
    y1 = max(0, min(height, y + h))
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"Invalid crop box for {output_path}: {crop_xywh}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), image[y0:y1, x0:x1])


def candidate_row(
    page: DetectionPage,
    candidate: CloudDetection,
    index: int,
    image_width: int,
    image_height: int,
    crop_xywh: list[float],
    crop_path: Path,
    params: WholeCloudExportParams,
) -> dict[str, Any]:
    bbox_xyxy = xywh_to_xyxy(candidate.bbox_page)
    crop_xyxy = xywh_to_xyxy(crop_xywh)
    width = float(candidate.bbox_page[2])
    height = float(candidate.bbox_page[3])
    crop_width = float(crop_xywh[2])
    crop_height = float(crop_xywh[3])
    member_count = int(candidate.metadata.get("member_count", 1))
    whole_confidence = float(candidate.metadata.get("whole_cloud_confidence", candidate.confidence))
    return {
        "schema": "cloudhammer.whole_cloud_candidate.v1",
        "candidate_id": crop_id_for_page(page, index),
        "pdf_path": page.pdf,
        "pdf_stem": Path(page.pdf).stem,
        "page_number": int(page.page),
        "render_path": page.render_path,
        "crop_image_path": str(crop_path),
        "source_mode": candidate.source_mode,
        "confidence": round(float(candidate.confidence), 6),
        "whole_cloud_confidence": round(whole_confidence, 6),
        "confidence_tier": confidence_tier(whole_confidence),
        "size_bucket": size_bucket_for_box(candidate.bbox_page, params),
        "bbox_page_xywh": round_box(candidate.bbox_page),
        "bbox_page_xyxy": round_box(bbox_xyxy),
        "crop_box_page_xywh": round_box(crop_xywh),
        "crop_box_page_xyxy": round_box(crop_xyxy),
        "bbox_width": round(width, 3),
        "bbox_height": round(height, 3),
        "bbox_area": round(width * height, 3),
        "crop_width": round(crop_width, 3),
        "crop_height": round(crop_height, 3),
        "crop_area": round(crop_width * crop_height, 3),
        "page_width": image_width,
        "page_height": image_height,
        "member_count": member_count,
        "member_confidences": candidate.metadata.get("member_confidences", []),
        "member_boxes_page_xyxy": candidate.metadata.get("member_boxes_page", []),
        "group_fill_ratio": candidate.metadata.get("fill_ratio"),
    }


def confidence_tier(confidence: float) -> str:
    if confidence >= 0.82:
        return "high"
    if confidence >= 0.65:
        return "medium"
    return "low"


def build_whole_cloud_candidates_for_page(
    page: DetectionPage,
    image_width: int,
    image_height: int,
    params: WholeCloudExportParams,
) -> list[CloudDetection]:
    candidates: list[CloudDetection] = []
    for group in page.detections:
        _, _, width, height = group.bbox_page
        if max(width, height) < params.min_box_side:
            continue
        confidence = whole_cloud_confidence(group, image_width, image_height)
        if confidence < params.min_candidate_confidence:
            continue
        metadata = dict(group.metadata)
        crop_xywh = crop_box_for_candidate(group.bbox_page, image_width, image_height, params)
        metadata.update(
            {
                "source_group_mode": group.source_mode,
                "model_confidence": float(group.confidence),
                "whole_cloud_confidence": confidence,
                "confidence_tier": confidence_tier(confidence),
                "size_bucket": size_bucket_for_box(group.bbox_page, params),
                "crop_box_page": crop_xywh,
            }
        )
        candidates.append(
            CloudDetection(
                confidence=confidence,
                bbox_page=[float(value) for value in group.bbox_page],
                crop_path=None,
                source_mode="whole_cloud_candidate",
                metadata=metadata,
            )
        )
    return candidates


def export_whole_cloud_page(
    page: DetectionPage,
    crop_dir: Path,
    params: WholeCloudExportParams,
) -> tuple[DetectionPage | None, list[dict[str, Any]]]:
    if not page.render_path:
        return None, []
    image = cv2.imread(page.render_path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None, []
    image_height, image_width = image.shape[:2]
    candidates = build_whole_cloud_candidates_for_page(page, image_width, image_height, params)
    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        crop_xywh = candidate.metadata["crop_box_page"]
        candidate_id = crop_id_for_page(page, index)
        crop_path = crop_dir / f"{candidate_id}_{candidate.metadata['size_bucket']}.png"
        export_candidate_crop(image, crop_xywh, crop_path)
        candidate.crop_path = str(crop_path)
        rows.append(candidate_row(page, candidate, index, image_width, image_height, crop_xywh, crop_path, params))
    return (
        DetectionPage(pdf=page.pdf, page=page.page, detections=candidates, render_path=page.render_path),
        rows,
    )


def write_candidate_manifest(path: Path, rows: list[dict[str, Any]]) -> int:
    return write_jsonl(path, rows)

