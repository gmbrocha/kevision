from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cloudhammer.contracts.detections import xyxy_to_xywh


XYXY = tuple[float, float, float, float]


@dataclass(frozen=True)
class CropTighteningParams:
    margin_ratio: float = 0.07
    min_margin: float = 90.0
    max_margin: float = 375.0
    min_crop_side: float = 160.0


def area_xyxy(box: XYXY) -> float:
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def clip_xyxy(box: XYXY, page_width: int, page_height: int) -> XYXY:
    x1, y1, x2, y2 = box
    clipped = (
        max(0.0, min(float(page_width), float(x1))),
        max(0.0, min(float(page_height), float(y1))),
        max(0.0, min(float(page_width), float(x2))),
        max(0.0, min(float(page_height), float(y2))),
    )
    if clipped[2] < clipped[0]:
        clipped = (clipped[2], clipped[1], clipped[0], clipped[3])
    if clipped[3] < clipped[1]:
        clipped = (clipped[0], clipped[3], clipped[2], clipped[1])
    return clipped


def margin_for_box(box: XYXY, params: CropTighteningParams) -> float:
    x1, y1, x2, y2 = box
    side = max(0.0, x2 - x1, y2 - y1)
    return max(params.min_margin, min(params.max_margin, side * params.margin_ratio))


def expand_to_min_side(box: XYXY, min_side: float) -> XYXY:
    x1, y1, x2, y2 = box
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    if width >= min_side and height >= min_side:
        return box
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    half_width = max(width, min_side) / 2.0
    half_height = max(height, min_side) / 2.0
    return (cx - half_width, cy - half_height, cx + half_width, cy + half_height)


def tightened_crop_box_for_bbox(
    bbox_xyxy: XYXY,
    page_width: int,
    page_height: int,
    params: CropTighteningParams | None = None,
) -> XYXY:
    params = params or CropTighteningParams()
    x1, y1, x2, y2 = bbox_xyxy
    margin = margin_for_box(bbox_xyxy, params)
    expanded = expand_to_min_side((x1 - margin, y1 - margin, x2 + margin, y2 + margin), params.min_crop_side)
    return clip_xyxy(expanded, page_width, page_height)


def box_from_row(row: dict[str, Any], field: str) -> XYXY:
    raw = row.get(field)
    if not isinstance(raw, list) or len(raw) != 4:
        raise ValueError(f"Missing {field} on candidate {row.get('candidate_id')}")
    return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))


def round_box(box: XYXY, digits: int = 3) -> list[float]:
    return [round(float(value), digits) for value in box]


def crop_metrics(original_crop_xyxy: XYXY, tightened_crop_xyxy: XYXY, bbox_xyxy: XYXY) -> dict[str, Any]:
    original_area = area_xyxy(original_crop_xyxy)
    tightened_area = area_xyxy(tightened_crop_xyxy)
    bbox_area = area_xyxy(bbox_xyxy)
    return {
        "original_crop_area": round(original_area, 3),
        "tightened_crop_area": round(tightened_area, 3),
        "bbox_area": round(bbox_area, 3),
        "area_ratio_vs_original": 0.0 if original_area <= 0 else round(tightened_area / original_area, 6),
        "area_reduction_pct": 0.0 if original_area <= 0 else round((1.0 - tightened_area / original_area) * 100.0, 2),
        "tightened_crop_box_page_xywh": round_box(tuple(xyxy_to_xywh(tightened_crop_xyxy))),
    }
