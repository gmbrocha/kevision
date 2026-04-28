from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from typing import Protocol

import fitz

from ..revision_state.models import SheetVersion
from .schemas import CloudDetection


class CloudInferenceClient(Protocol):
    """Boundary between backend orchestration and CloudHammer inference."""

    def detect(self, *, page: fitz.Page, sheet: SheetVersion) -> list[CloudDetection]:
        ...


class NullCloudInferenceClient:
    """Default placeholder until the local CloudHammer model is wired in."""

    name = "disabled"

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


def _row_bbox_xywh(row: dict[str, Any]) -> list[float]:
    xywh = row.get("bbox_page_xywh")
    if isinstance(xywh, list) and len(xywh) == 4:
        return [float(value) for value in xywh]
    xyxy = row.get("bbox_page_xyxy")
    if isinstance(xyxy, list) and len(xyxy) == 4:
        x1, y1, x2, y2 = [float(value) for value in xyxy]
        return [x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)]
    return [0.0, 0.0, 1.0, 1.0]


def _scale_bbox_to_sheet(row: dict[str, Any], sheet: SheetVersion) -> list[int]:
    x, y, width, height = _row_bbox_xywh(row)
    source_width = float(row.get("page_width") or sheet.width or 1)
    source_height = float(row.get("page_height") or sheet.height or 1)
    scale_x = float(sheet.width or source_width) / source_width if source_width else 1.0
    scale_y = float(sheet.height or source_height) / source_height if source_height else 1.0
    return [
        int(round(x * scale_x)),
        int(round(y * scale_y)),
        max(1, int(round(width * scale_x))),
        max(1, int(round(height * scale_y))),
    ]


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


class ManifestCloudInferenceClient:
    """CloudHammer integration that serves detections from a candidate manifest.

    This is the bridge between the current CloudHammer artifact pipeline and the
    existing backend scanner/exporter. It does not run the model; it lets a
    precomputed CloudHammer release manifest participate in the normal scan path.
    """

    name = "cloudhammer_manifest"

    def __init__(self, manifest_path: Path | str):
        self.manifest_path = Path(manifest_path).resolve()
        self.rows = _read_jsonl(self.manifest_path)
        self._by_pdf_page: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for row in self.rows:
            pdf_path = str(row.get("pdf_path") or "")
            page_number = int(row.get("page_number") or 0)
            if not pdf_path or not page_number:
                continue
            resolved = str(Path(pdf_path).resolve()).lower()
            self._by_pdf_page[(resolved, page_number)].append(row)

    def detect(self, *, page: fitz.Page, sheet: SheetVersion) -> list[CloudDetection]:
        key = (str(Path(sheet.source_pdf).resolve()).lower(), int(sheet.page_number))
        rows = self._by_pdf_page.get(key, [])
        detections: list[CloudDetection] = []
        for row in rows:
            confidence = float(row.get("whole_cloud_confidence", row.get("confidence") or 0.0) or 0.0)
            detections.append(
                CloudDetection(
                    bbox=_scale_bbox_to_sheet(row, sheet),
                    confidence=confidence,
                    image_path=_row_crop_path(row, self.manifest_path),
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
                        "manifest_path": str(self.manifest_path),
                    },
                )
            )
        return detections
