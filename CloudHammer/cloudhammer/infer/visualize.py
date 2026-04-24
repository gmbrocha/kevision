from __future__ import annotations

from pathlib import Path

import cv2

from cloudhammer.contracts.detections import CloudDetection


def save_crops(
    image,
    detections: list[CloudDetection],
    crop_dir: str | Path,
    prefix: str,
) -> list[CloudDetection]:
    out_dir = Path(crop_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    height, width = image.shape[:2]
    for idx, det in enumerate(detections, start=1):
        x, y, w, h = [int(round(v)) for v in det.bbox_page]
        x0 = max(0, min(width, x))
        y0 = max(0, min(height, y))
        x1 = max(0, min(width, x + w))
        y1 = max(0, min(height, y + h))
        if x1 <= x0 or y1 <= y0:
            continue
        crop_path = out_dir / f"{prefix}_cloud_{idx:03d}.png"
        cv2.imwrite(str(crop_path), image[y0:y1, x0:x1])
        det.crop_path = str(crop_path)
    return detections


def draw_overlay(image, detections: list[CloudDetection], output_path: str | Path) -> None:
    if len(image.shape) == 2:
        overlay = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        overlay = image.copy()
    for det in detections:
        x, y, w, h = [int(round(v)) for v in det.bbox_page]
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 190, 0), 4)
        cv2.putText(
            overlay,
            f"{det.confidence:.2f}",
            (x, max(20, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 190, 0),
            2,
            cv2.LINE_AA,
        )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), overlay)
