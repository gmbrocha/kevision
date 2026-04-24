from __future__ import annotations

from pathlib import Path

import cv2

from cloudhammer.config import CloudHammerConfig
from cloudhammer.data.splits import assign_split
from cloudhammer.manifests import read_json, read_jsonl, write_jsonl
from cloudhammer.page_catalog import stable_page_key
from cloudhammer.page_filter import classify_roi_source_page, count_page_filter_results


def clip_square_roi(cx: float, cy: float, size: int, page_width: int, page_height: int) -> list[int]:
    if size <= 0:
        raise ValueError("ROI size must be positive")
    width = min(size, page_width)
    height = min(size, page_height)
    x0 = int(round(cx - width / 2))
    y0 = int(round(cy - height / 2))
    x0 = max(0, min(page_width - width, x0))
    y0 = max(0, min(page_height - height, y0))
    return [x0, y0, width, height]


def _iter_delta_payloads(delta_json_dir: Path):
    for path in sorted(delta_json_dir.glob("*.json")):
        yield path, read_json(path)


def extract_rois(
    cfg: CloudHammerConfig,
    pages_manifest: str | Path | None = None,
    delta_json_dir: str | Path | None = None,
    limit: int | None = None,
) -> int:
    cfg.ensure_directories()
    page_manifest_path = Path(pages_manifest) if pages_manifest is not None else cfg.path("manifests") / "pages.jsonl"
    delta_dir = Path(delta_json_dir) if delta_json_dir is not None else cfg.path("delta_json")
    page_rows = list(read_jsonl(page_manifest_path))
    counts = count_page_filter_results([row for row in page_rows if row.get("page_kind") == "drawing"])
    print(
        "page filter: "
        f"total={counts['total_pages']} "
        f"included={counts['included_pages']} "
        f"excluded_index_cover={counts['excluded_index_cover_pages']}"
    )
    pages = {
        (str(Path(row["pdf_path"]).resolve()), int(row["page_index"])): row
        for row in page_rows
    }
    rows: list[dict] = []
    count = 0

    for delta_path, payload in _iter_delta_payloads(delta_dir):
        pdf_path = str(Path(payload["pdf_path"]).resolve())
        page_index = int(payload["page_index"])
        page = pages.get((pdf_path, page_index))
        if page is None:
            continue
        filter_result = classify_roi_source_page(page)
        if filter_result.is_excluded:
            continue
        render_path = page.get("render_path")
        if not render_path or not Path(render_path).exists():
            continue
        image = cv2.imread(str(render_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            continue
        page_h, page_w = image.shape[:2]
        for delta_idx, delta in enumerate(payload.get("active_deltas", []), start=1):
            if limit is not None and count >= limit:
                write_jsonl(cfg.path("manifests") / "roi_manifest.jsonl", rows)
                return count
            center = delta.get("center")
            if not center:
                continue
            bbox = clip_square_roi(float(center["x"]), float(center["y"]), cfg.roi_size, page_w, page_h)
            x, y, w, h = bbox
            roi = image[y : y + h, x : x + w]
            key = stable_page_key(Path(pdf_path), page_index)
            delta_digit = delta.get("digit")
            delta_id = f"{key}_d{delta_idx:03d}"
            roi_path = cfg.path("roi_images") / f"{delta_id}.png"
            label_path = cfg.path("labels") / f"{delta_id}.txt"
            cv2.imwrite(str(roi_path), roi)
            rows.append(
                {
                    "pdf_path": pdf_path,
                    "page_index": page_index,
                    "delta_id": delta_id,
                    "delta_digit": delta_digit,
                    "roi_bbox_page": bbox,
                    "roi_image_path": str(roi_path),
                    "split": assign_split(pdf_path, page_index),
                    "label_path": str(label_path),
                    "is_excluded": False,
                    "exclude_reason": "none",
                }
            )
            count += 1
    write_jsonl(cfg.path("manifests") / "roi_manifest.jsonl", rows)
    return count
