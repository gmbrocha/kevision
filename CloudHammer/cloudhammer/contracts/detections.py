from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from cloudhammer.manifests import read_json, write_json


SourceMode = Literal["roi_bootstrap", "page_tile", "fragment_group"]


def xyxy_to_xywh(box: tuple[float, float, float, float]) -> list[float]:
    x0, y0, x1, y1 = box
    return [float(x0), float(y0), float(max(0.0, x1 - x0)), float(max(0.0, y1 - y0))]


def xywh_to_xyxy(box: list[float] | tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x, y, w, h = box
    return (float(x), float(y), float(x + w), float(y + h))


def clip_xywh(box: list[float], width: int, height: int) -> list[float]:
    x0, y0, x1, y1 = xywh_to_xyxy(box)
    x0 = max(0.0, min(float(width), x0))
    y0 = max(0.0, min(float(height), y0))
    x1 = max(0.0, min(float(width), x1))
    y1 = max(0.0, min(float(height), y1))
    return xyxy_to_xywh((x0, y0, x1, y1))


@dataclass
class CloudDetection:
    confidence: float
    bbox_page: list[float]
    crop_path: str | None
    source_mode: SourceMode
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "confidence": float(self.confidence),
            "bbox_page": [float(v) for v in self.bbox_page],
            "crop_path": self.crop_path,
            "source_mode": self.source_mode,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "CloudDetection":
        source_mode = payload["source_mode"]
        if source_mode not in {"roi_bootstrap", "page_tile", "fragment_group"}:
            raise ValueError(f"Invalid source_mode: {source_mode}")
        return cls(
            confidence=float(payload["confidence"]),
            bbox_page=[float(v) for v in payload["bbox_page"]],
            crop_path=payload.get("crop_path"),
            source_mode=source_mode,
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass
class DetectionPage:
    pdf: str
    page: int
    detections: list[CloudDetection]
    render_path: str | None = None

    def to_dict(self) -> dict:
        payload = {
            "pdf": self.pdf,
            "page": int(self.page),
            "detections": [det.to_dict() for det in self.detections],
        }
        if self.render_path is not None:
            payload["render_path"] = self.render_path
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "DetectionPage":
        return cls(
            pdf=str(payload["pdf"]),
            page=int(payload["page"]),
            detections=[CloudDetection.from_dict(item) for item in payload.get("detections", [])],
            render_path=payload.get("render_path"),
        )


def write_detection_manifest(path: str | Path, pages: list[DetectionPage], model: str | None = None) -> None:
    payload = {
        "schema": "cloudhammer.detections.v1",
        "model": model,
        "pages": [page.to_dict() for page in pages],
    }
    write_json(path, payload)


def load_detection_manifest(path: str | Path) -> list[DetectionPage]:
    payload = read_json(path)
    return [DetectionPage.from_dict(page) for page in payload.get("pages", [])]
