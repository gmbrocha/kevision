from __future__ import annotations

from dataclasses import dataclass

from cloudhammer.contracts.detections import CloudDetection, clip_xywh, xywh_to_xyxy, xyxy_to_xywh


XYXY = tuple[float, float, float, float]


@dataclass(frozen=True)
class GroupingParams:
    expansion_ratio: float = 0.55
    min_padding: float = 120.0
    max_padding: float = 850.0
    group_margin_ratio: float = 0.08
    min_group_margin: float = 25.0
    max_group_margin: float = 350.0
    split_min_members: int = 7
    split_min_partition_members: int = 3
    split_gap_ratio: float = 0.16
    split_min_gap: float = 550.0
    split_max_fill_ratio: float = 0.28


def _area(box: XYXY) -> float:
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _intersects(a: XYXY, b: XYXY) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return min(ax2, bx2) > max(ax1, bx1) and min(ay2, by2) > max(ay1, by1)


def _union_xyxy(boxes: list[XYXY]) -> XYXY:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _expand(box: XYXY, params: GroupingParams) -> XYXY:
    x1, y1, x2, y2 = box
    side = max(x2 - x1, y2 - y1)
    padding = max(params.min_padding, min(params.max_padding, side * params.expansion_ratio))
    return (x1 - padding, y1 - padding, x2 + padding, y2 + padding)


def _add_group_margin(box: XYXY, params: GroupingParams) -> XYXY:
    x1, y1, x2, y2 = box
    side = max(x2 - x1, y2 - y1)
    margin = max(params.min_group_margin, min(params.max_group_margin, side * params.group_margin_ratio))
    return (x1 - margin, y1 - margin, x2 + margin, y2 + margin)


def _center(box: XYXY) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _fill_ratio_for_indexes(indexes: list[int], boxes: list[XYXY]) -> float:
    if not indexes:
        return 0.0
    member_area = sum(_area(boxes[index]) for index in indexes)
    group_area = _area(_union_xyxy([boxes[index] for index in indexes]))
    return 0.0 if group_area <= 0 else member_area / group_area


def _best_center_gap_split(
    indexes: list[int],
    boxes: list[XYXY],
    params: GroupingParams,
) -> tuple[list[int], list[int]] | None:
    group_box = _union_xyxy([boxes[index] for index in indexes])
    x_span = max(1.0, group_box[2] - group_box[0])
    y_span = max(1.0, group_box[3] - group_box[1])
    candidates: list[tuple[float, list[int], list[int]]] = []

    for axis in (0, 1):
        ordered = sorted(indexes, key=lambda index: _center(boxes[index])[axis])
        centers = [_center(boxes[index])[axis] for index in ordered]
        span = x_span if axis == 0 else y_span
        for split_at in range(1, len(ordered)):
            left = ordered[:split_at]
            right = ordered[split_at:]
            if len(left) < params.split_min_partition_members or len(right) < params.split_min_partition_members:
                continue
            gap = centers[split_at] - centers[split_at - 1]
            required_gap = max(params.split_min_gap, span * params.split_gap_ratio)
            if gap < required_gap:
                continue
            before = _fill_ratio_for_indexes(indexes, boxes)
            after = (
                _fill_ratio_for_indexes(left, boxes) * len(left)
                + _fill_ratio_for_indexes(right, boxes) * len(right)
            ) / len(indexes)
            candidates.append((after - before, left, right))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    improvement, left, right = candidates[0]
    if improvement <= 0:
        return None
    return left, right


def _split_large_component(
    indexes: list[int],
    boxes: list[XYXY],
    params: GroupingParams,
) -> list[list[int]]:
    if len(indexes) < params.split_min_members:
        return [indexes]
    if _fill_ratio_for_indexes(indexes, boxes) > params.split_max_fill_ratio:
        return [indexes]
    split = _best_center_gap_split(indexes, boxes, params)
    if split is None:
        return [indexes]
    left, right = split
    return _split_large_component(left, boxes, params) + _split_large_component(right, boxes, params)


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def group_fragment_detections(
    detections: list[CloudDetection],
    image_width: int,
    image_height: int,
    params: GroupingParams | None = None,
) -> list[CloudDetection]:
    """Group nearby motif-fragment detections into whole-cloud candidates.

    This is intentionally geometry-only. It treats the detector outputs as cloud
    edge/motif proposals, expands each box, connects intersecting expanded
    boxes, then emits one enclosing candidate per connected component.
    """
    params = params or GroupingParams()
    if not detections:
        return []

    boxes = [xywh_to_xyxy(det.bbox_page) for det in detections]
    expanded = [_expand(box, params) for box in boxes]
    uf = UnionFind(len(detections))

    for i in range(len(detections)):
        for j in range(i + 1, len(detections)):
            if _intersects(expanded[i], expanded[j]):
                uf.union(i, j)

    components: dict[int, list[int]] = {}
    for index in range(len(detections)):
        components.setdefault(uf.find(index), []).append(index)

    grouped: list[CloudDetection] = []
    for member_indexes in components.values():
        for split_indexes in _split_large_component(member_indexes, boxes, params):
            grouped.append(_group_from_indexes(split_indexes, detections, boxes, image_width, image_height, params))

    return sorted(grouped, key=lambda det: (-len(det.metadata.get("member_indexes", [])), -det.confidence))


def _group_from_indexes(
    member_indexes: list[int],
    detections: list[CloudDetection],
    boxes: list[XYXY],
    image_width: int,
    image_height: int,
    params: GroupingParams,
) -> CloudDetection:
    member_boxes = [boxes[index] for index in member_indexes]
    group_xyxy = _add_group_margin(_union_xyxy(member_boxes), params)
    group_xywh = clip_xywh(xyxy_to_xywh(group_xyxy), image_width, image_height)
    member_confidences = [float(detections[index].confidence) for index in member_indexes]
    member_area = sum(_area(boxes[index]) for index in member_indexes)
    group_area = _area(xywh_to_xyxy(group_xywh))
    return CloudDetection(
        confidence=max(member_confidences),
        bbox_page=group_xywh,
        crop_path=None,
        source_mode="fragment_group",
        metadata={
            "member_count": len(member_indexes),
            "member_indexes": [index + 1 for index in member_indexes],
            "member_confidences": member_confidences,
            "member_boxes_page": [list(boxes[index]) for index in member_indexes],
            "member_area_sum": member_area,
            "group_area": group_area,
            "fill_ratio": 0.0 if group_area <= 0 else member_area / group_area,
        },
    )


def grouping_summary(original: list[CloudDetection], grouped: list[CloudDetection]) -> dict:
    member_counts = [int(det.metadata.get("member_count", 1)) for det in grouped]
    multi = [count for count in member_counts if count > 1]
    return {
        "fragment_count": len(original),
        "group_count": len(grouped),
        "multi_fragment_group_count": len(multi),
        "singleton_group_count": len(grouped) - len(multi),
        "largest_group_member_count": max(member_counts, default=0),
    }
