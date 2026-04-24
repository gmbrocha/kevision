from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CloudDetection:
    """A normalized cloud-detection result returned by CloudHammer integration."""

    bbox: list[int]
    confidence: float = 0.0
    image_path: str = ""
    page_image_path: str = ""
    extraction_method: str = "cloudhammer"
    nearby_text: str = ""
    detail_ref: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
