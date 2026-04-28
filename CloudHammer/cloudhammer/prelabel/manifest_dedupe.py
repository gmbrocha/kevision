from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


XYXY = tuple[float, float, float, float]


@dataclass(frozen=True)
class DedupeDecision:
    row: dict[str, Any]
    kept: bool
    reason: str
    duplicate_of: str
    iou: float
    overlap_smaller: float


def row_id(row: dict[str, Any]) -> str:
    return str(row.get("cloud_roi_id") or row.get("random_crop_id") or Path(str(row.get("image_path") or "")).stem)


def candidate_source(row: dict[str, Any]) -> str:
    return str(row.get("candidate_source") or row.get("source") or "unknown")


def revision_name(row: dict[str, Any]) -> str:
    raw = str(row.get("revision") or "")
    if raw:
        return raw
    pdf_path = str(row.get("pdf_path") or "")
    marker = "revision_sets"
    parts = Path(pdf_path).parts
    lowered = [part.lower() for part in parts]
    if marker in lowered:
        index = lowered.index(marker)
        if index + 1 < len(parts):
            return parts[index + 1]
    return "unknown"


def page_key(row: dict[str, Any]) -> tuple[str, str]:
    pdf_path = str(row.get("pdf_path") or row.get("render_path") or "").lower()
    page_index = str(row.get("page_index") if row.get("page_index") is not None else row.get("page_number") or "")
    return pdf_path, page_index


def _xywh_to_xyxy(values: list[Any] | tuple[Any, ...]) -> XYXY:
    x, y, w, h = [float(value) for value in values[:4]]
    return x, y, x + w, y + h


def _xyxy(values: list[Any] | tuple[Any, ...]) -> XYXY:
    x1, y1, x2, y2 = [float(value) for value in values[:4]]
    return x1, y1, x2, y2


def crop_box_xyxy(row: dict[str, Any]) -> XYXY | None:
    for key in ("roi_bbox_page", "bbox_on_page"):
        values = row.get(key)
        if isinstance(values, (list, tuple)) and len(values) >= 4:
            return _xywh_to_xyxy(values)
    values = row.get("crop_box_page")
    if isinstance(values, (list, tuple)) and len(values) >= 4:
        return _xyxy(values)
    return None


def area(box: XYXY) -> float:
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def overlap_metrics(a: XYXY, b: XYXY) -> tuple[float, float]:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if intersection <= 0:
        return 0.0, 0.0
    a_area = area(a)
    b_area = area(b)
    union = a_area + b_area - intersection
    iou = intersection / union if union > 0 else 0.0
    smaller = min(a_area, b_area)
    overlap_smaller = intersection / smaller if smaller > 0 else 0.0
    return iou, overlap_smaller


def _source_priority(row: dict[str, Any]) -> int:
    source = candidate_source(row)
    if source == "target_marker_neighborhood":
        return 0
    if source in {"marker_neighborhood", "all_marker_neighborhood"}:
        return 1
    if source == "random_standard_drawing_crop":
        return 2
    return 3


def _float_value(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def sort_key(row_with_index: tuple[int, dict[str, Any]]) -> tuple[Any, ...]:
    index, row = row_with_index
    box = crop_box_xyxy(row)
    box_area = area(box) if box else 0.0
    crop_offset = str(row.get("crop_offset") or "")
    center_bonus = 0 if crop_offset.startswith("center") else 1
    return (
        page_key(row),
        _source_priority(row),
        center_bonus,
        -_float_value(row, "cloud_likeness"),
        -_float_value(row, "cloud_candidate_score"),
        -_float_value(row, "ink_ratio"),
        -box_area,
        index,
    )


def dedupe_manifest_rows(
    rows: list[dict[str, Any]],
    *,
    iou_threshold: float = 0.30,
    overlap_smaller_threshold: float = 0.65,
) -> list[DedupeDecision]:
    if not 0.0 <= iou_threshold <= 1.0:
        raise ValueError("iou_threshold must be between 0 and 1")
    if not 0.0 <= overlap_smaller_threshold <= 1.0:
        raise ValueError("overlap_smaller_threshold must be between 0 and 1")

    decisions_by_id: dict[int, DedupeDecision] = {}
    kept_by_page: dict[tuple[str, str], list[tuple[dict[str, Any], XYXY]]] = defaultdict(list)

    for original_index, row in sorted(enumerate(rows), key=sort_key):
        box = crop_box_xyxy(row)
        if box is None:
            decisions_by_id[original_index] = DedupeDecision(
                row=row,
                kept=True,
                reason="keep_no_crop_box",
                duplicate_of="",
                iou=0.0,
                overlap_smaller=0.0,
            )
            continue

        duplicate_of = ""
        best_iou = 0.0
        best_overlap = 0.0
        for kept_row, kept_box in kept_by_page[page_key(row)]:
            iou, overlap = overlap_metrics(box, kept_box)
            if iou > best_iou or overlap > best_overlap:
                best_iou = max(best_iou, iou)
                best_overlap = max(best_overlap, overlap)
                duplicate_of = row_id(kept_row)
            if iou >= iou_threshold or overlap >= overlap_smaller_threshold:
                decisions_by_id[original_index] = DedupeDecision(
                    row=row,
                    kept=False,
                    reason="same_page_overlapping_crop",
                    duplicate_of=row_id(kept_row),
                    iou=round(iou, 6),
                    overlap_smaller=round(overlap, 6),
                )
                break
        else:
            kept_by_page[page_key(row)].append((row, box))
            decisions_by_id[original_index] = DedupeDecision(
                row=row,
                kept=True,
                reason="keep",
                duplicate_of="",
                iou=round(best_iou, 6),
                overlap_smaller=round(best_overlap, 6),
            )

    return [decisions_by_id[index] for index in range(len(rows))]


def summarize_dedupe(decisions: list[DedupeDecision]) -> dict[str, Any]:
    kept = [decision for decision in decisions if decision.kept]
    rejected = [decision for decision in decisions if not decision.kept]
    summary: dict[str, Any] = {
        "input_rows": len(decisions),
        "kept_rows": len(kept),
        "excluded_rows": len(rejected),
        "excluded_by_reason": dict(Counter(decision.reason for decision in rejected)),
        "kept_by_source": dict(Counter(candidate_source(decision.row) for decision in kept)),
        "excluded_by_source": dict(Counter(candidate_source(decision.row) for decision in rejected)),
        "kept_by_revision": dict(Counter(revision_name(decision.row) for decision in kept)),
        "excluded_by_revision": dict(Counter(revision_name(decision.row) for decision in rejected)),
    }
    return summary


def exclusion_row(decision: DedupeDecision) -> dict[str, Any]:
    row = dict(decision.row)
    row["dedupe_excluded"] = True
    row["dedupe_reason"] = decision.reason
    row["dedupe_duplicate_of"] = decision.duplicate_of
    row["dedupe_iou"] = decision.iou
    row["dedupe_overlap_smaller"] = decision.overlap_smaller
    return row
