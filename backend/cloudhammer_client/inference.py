from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any
from typing import Protocol

import fitz

from ..revision_state.models import SheetVersion
from .schemas import CloudDetection


MIN_SHEET_BBOX_SIZE = 4
NEGATIVE_RELEASE_ACTIONS = {"reject", "rejected", "discard", "drop", "skip", "exclude", "excluded", "quarantine"}
NEGATIVE_REVIEW_STATUSES = {"reject", "rejected", "false_positive", "false-positive", "discarded", "excluded"}
NEGATIVE_POLICY_MARKERS = ("false_positive", "false-positive", "reject", "rejected", "quarantine", "discard", "noise")


class CloudInferenceClient(Protocol):
    """Boundary between backend orchestration and CloudHammer inference."""

    def detect(self, *, page: fitz.Page, sheet: SheetVersion) -> list[CloudDetection]:
        ...


class NullCloudInferenceClient:
    """Default placeholder until the local CloudHammer model is wired in."""

    name = "disabled"
    cache_key = "disabled"

    def detect(self, *, page: fitz.Page, sheet: SheetVersion) -> list[CloudDetection]:
        return []


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _resolve_existing_path(path_text: str, *, manifest_path: Path) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    candidates = [path]
    if not path.is_absolute():
        candidates.append(manifest_path.parent / path)
        candidates.append(Path.cwd() / path)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    return path_text


def _row_crop_path(row: dict[str, Any], manifest_path: Path) -> str:
    for key in ("tight_crop_image_path", "artifact_crop_path", "crop_image_path"):
        value = str(row.get(key) or "")
        if value:
            return _resolve_existing_path(value, manifest_path=manifest_path)
    return ""


def _as_finite_float_list(values: Any) -> list[float] | None:
    if not isinstance(values, list) or len(values) != 4:
        return None
    try:
        numbers = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in numbers):
        return None
    return numbers


def _row_bbox_xywh(row: dict[str, Any]) -> list[float] | None:
    xywh = row.get("bbox_page_xywh")
    values = _as_finite_float_list(xywh)
    if values:
        return values
    xyxy = row.get("bbox_page_xyxy")
    values = _as_finite_float_list(xyxy)
    if values:
        x1, y1, x2, y2 = values
        return [x1, y1, x2 - x1, y2 - y1]
    return None


def _positive_dimension(value: Any, fallback: int) -> float:
    try:
        number = float(value or fallback or 1)
    except (TypeError, ValueError):
        return float(fallback or 1)
    return number if math.isfinite(number) and number > 0 else float(fallback or 1)


def _float_or_zero(value: Any) -> float:
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _scale_bbox_to_sheet(row: dict[str, Any], sheet: SheetVersion) -> tuple[list[int] | None, str | None]:
    raw_bbox = _row_bbox_xywh(row)
    if not raw_bbox:
        return None, "invalid_bbox"
    x, y, width, height = raw_bbox
    if width <= 0 or height <= 0:
        return None, "invalid_bbox"
    source_width = _positive_dimension(row.get("page_width"), sheet.width)
    source_height = _positive_dimension(row.get("page_height"), sheet.height)
    x1 = max(0.0, min(source_width, x))
    y1 = max(0.0, min(source_height, y))
    x2 = max(0.0, min(source_width, x + width))
    y2 = max(0.0, min(source_height, y + height))
    if x2 <= x1 or y2 <= y1:
        return None, "invalid_bbox"
    width = x2 - x1
    height = y2 - y1
    scale_x = float(sheet.width or source_width) / source_width if source_width else 1.0
    scale_y = float(sheet.height or source_height) / source_height if source_height else 1.0
    scaled = [
        max(0, int(round(x1 * scale_x))),
        max(0, int(round(y1 * scale_y))),
        max(1, int(round(width * scale_x))),
        max(1, int(round(height * scale_y))),
    ]
    if scaled[2] < MIN_SHEET_BBOX_SIZE or scaled[3] < MIN_SHEET_BBOX_SIZE:
        return None, "tiny_bbox"
    return scaled, None


def _row_bbox_skip_reason(row: dict[str, Any]) -> str | None:
    raw_bbox = _row_bbox_xywh(row)
    if not raw_bbox:
        return "invalid_bbox"
    _, _, width, height = raw_bbox
    if width <= 0 or height <= 0:
        return "invalid_bbox"
    return None


def _nearby_text(row: dict[str, Any]) -> str:
    candidate_id = str(row.get("candidate_id") or row.get("source_candidate_id") or "unknown")
    policy = str(row.get("policy_bucket") or "unbucketed")
    review = str(row.get("review_status") or "unreviewed")
    confidence = row.get("whole_cloud_confidence", row.get("confidence", ""))
    return (
        "Cloud Only - CloudHammer detected revision cloud. "
        "OCR/scope extraction is not wired yet. "
        f"candidate={candidate_id}; policy={policy}; review={review}; confidence={confidence}"
    )


def _policy_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _row_rejection_reason(row: dict[str, Any]) -> str | None:
    release_action = _policy_text(row.get("release_action"))
    review_status = _policy_text(row.get("review_status"))
    policy_bucket = _policy_text(row.get("policy_bucket"))
    if release_action in NEGATIVE_RELEASE_ACTIONS:
        return "release_action"
    if review_status in NEGATIVE_REVIEW_STATUSES:
        return "review_status"
    if any(marker in policy_bucket for marker in NEGATIVE_POLICY_MARKERS):
        return "policy_bucket"
    return None


class ManifestCloudInferenceClient:
    """CloudHammer integration that serves detections from a candidate manifest.

    This is the bridge between the current CloudHammer artifact pipeline and the
    existing backend scanner/exporter. It does not run the model; it lets a
    precomputed CloudHammer release manifest participate in the normal scan path.
    """

    name = "cloudhammer_manifest"

    def __init__(self, manifest_path: Path | str):
        self.manifest_path = Path(manifest_path).resolve()
        stat = self.manifest_path.stat()
        self.cache_key = f"{self.name}:{self.manifest_path}:{stat.st_size}:{stat.st_mtime_ns}"
        self.rows = _read_jsonl(self.manifest_path)
        self._by_pdf_page: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        self.stats: dict[str, int] = {
            "total_rows": len(self.rows),
            "indexed_rows": 0,
            "skipped_missing_pdf_page": 0,
            "skipped_policy": 0,
            "skipped_invalid_bbox": 0,
            "skipped_tiny_bbox": 0,
            "missing_crop_count": 0,
        }
        for row in self.rows:
            pdf_path = str(row.get("pdf_path") or "")
            try:
                page_number = int(row.get("page_number") or 0)
            except (TypeError, ValueError):
                page_number = 0
            if not pdf_path or not page_number:
                self.stats["skipped_missing_pdf_page"] += 1
                continue
            if _row_rejection_reason(row):
                self.stats["skipped_policy"] += 1
                continue
            skip_reason = _row_bbox_skip_reason(row)
            if skip_reason:
                self.stats[f"skipped_{skip_reason}"] += 1
                continue
            resolved = str(Path(pdf_path).resolve()).lower()
            self._by_pdf_page[(resolved, page_number)].append(row)
            self.stats["indexed_rows"] += 1
            if _row_crop_path(row, self.manifest_path) and not Path(_row_crop_path(row, self.manifest_path)).exists():
                self.stats["missing_crop_count"] += 1

    def detect(self, *, page: fitz.Page, sheet: SheetVersion) -> list[CloudDetection]:
        key = (str(Path(sheet.source_pdf).resolve()).lower(), int(sheet.page_number))
        rows = self._by_pdf_page.get(key, [])
        detections: list[CloudDetection] = []
        for row in rows:
            bbox, skip_reason = _scale_bbox_to_sheet(row, sheet)
            if not bbox:
                self.stats[f"skipped_{skip_reason}"] += 1
                continue
            confidence = _float_or_zero(row.get("whole_cloud_confidence", row.get("confidence")))
            crop_path = _row_crop_path(row, self.manifest_path)
            detections.append(
                CloudDetection(
                    bbox=bbox,
                    confidence=confidence,
                    image_path=crop_path,
                    page_image_path=sheet.render_path,
                    extraction_method=self.name,
                    nearby_text=_nearby_text(row),
                    detail_ref=None,
                    metadata={
                        "cloudhammer_candidate_id": row.get("candidate_id"),
                        "policy_bucket": row.get("policy_bucket"),
                        "release_action": row.get("release_action"),
                        "release_reason": row.get("release_reason"),
                        "review_status": row.get("review_status"),
                        "cloudhammer_quality_policy": "included",
                        "cloudhammer_crop_missing": bool(crop_path and not Path(crop_path).exists()),
                        "manifest_path": str(self.manifest_path),
                    },
                )
            )
        return detections
