from __future__ import annotations

from cloudhammer.contracts.detections import CloudDetection, xywh_to_xyxy


def bbox_iou_xywh(a: list[float], b: list[float]) -> float:
    ax0, ay0, ax1, ay1 = xywh_to_xyxy(a)
    bx0, by0, bx1, by1 = xywh_to_xyxy(b)
    inter_x0 = max(ax0, bx0)
    inter_y0 = max(ay0, by0)
    inter_x1 = min(ax1, bx1)
    inter_y1 = min(ay1, by1)
    inter_w = max(0.0, inter_x1 - inter_x0)
    inter_h = max(0.0, inter_y1 - inter_y0)
    inter_area = inter_w * inter_h
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    denom = area_a + area_b - inter_area
    return 0.0 if denom <= 0 else inter_area / denom


def nms_detections(detections: list[CloudDetection], iou_threshold: float) -> list[CloudDetection]:
    ordered = sorted(detections, key=lambda det: det.confidence, reverse=True)
    kept: list[CloudDetection] = []
    for det in ordered:
        if all(bbox_iou_xywh(det.bbox_page, keep.bbox_page) <= iou_threshold for keep in kept):
            kept.append(det)
    return kept
