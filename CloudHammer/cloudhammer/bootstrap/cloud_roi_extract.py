from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from cloudhammer.config import CloudHammerConfig
from cloudhammer.data.splits import assign_split
from cloudhammer.manifests import read_json, read_jsonl, write_jsonl
from cloudhammer.page_filter import classify_roi_source_page_with_pdf_text, count_page_filter_results


DEFAULT_CROP_SIZE = 1536
DEFAULT_CROP_SIZE_LARGE = 2048
DEFAULT_DEDUPE_IOU = 0.82
DEFAULT_BLANK_INK_RATIO = 0.002
DELTA_ID_RE = re.compile(r"_d(?P<idx>\d{3,})$")
REVISION_DIGIT_RE = re.compile(
    r"\b(?:revision|rev)[\s_#-]*(?:set[\s_#-]*)?(?P<digit>\d+)(?!\d)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MarkerSeed:
    pdf_path: str
    page_index: int
    seed_id: str
    marker_digit: str | None
    center_x: float
    center_y: float
    marker_bbox: list[int]
    marker_matches_target: bool | None = None
    target_revision_digit: str | None = None


@dataclass(frozen=True)
class CloudCrop:
    bbox: list[int]
    crop_offset: str
    marker: MarkerSeed
    cloud_likeness: float
    ink_ratio: float


def clip_bbox_xywh(bbox: list[int], page_width: int, page_height: int) -> list[int]:
    x, y, w, h = bbox
    w = max(1, min(int(w), page_width))
    h = max(1, min(int(h), page_height))
    x = max(0, min(page_width - w, int(x)))
    y = max(0, min(page_height - h, int(y)))
    return [x, y, w, h]


def bbox_iou(a: list[int], b: list[int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix0 = max(ax, bx)
    iy0 = max(ay, by)
    ix1 = min(ax + aw, bx + bw)
    iy1 = min(ay + ah, by + bh)
    iw = max(0, ix1 - ix0)
    ih = max(0, iy1 - iy0)
    intersection = iw * ih
    if intersection <= 0:
        return 0.0
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def marker_bbox_from_delta(delta: dict, fallback_center: tuple[float, float]) -> list[int]:
    points: list[tuple[float, float]] = []
    triangle = delta.get("triangle") or {}
    for key in ("apex", "left_base", "right_base"):
        point = triangle.get(key)
        if point:
            points.append((float(point["x"]), float(point["y"])))
    center = delta.get("center")
    if center:
        points.append((float(center["x"]), float(center["y"])))
    if not points:
        points.append(fallback_center)

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    pad = 40
    x0 = int(round(min(xs) - pad))
    y0 = int(round(min(ys) - pad))
    x1 = int(round(max(xs) + pad))
    y1 = int(round(max(ys) + pad))
    return [x0, y0, max(1, x1 - x0), max(1, y1 - y0)]


def _delta_index_from_id(delta_id: str) -> int | None:
    match = DELTA_ID_RE.search(delta_id)
    if not match:
        return None
    return int(match.group("idx")) - 1


def _delta_payload_path(delta_json_dir: Path, marker_row: dict) -> Path:
    stem = str(marker_row["delta_id"]).rsplit("_d", 1)[0]
    return delta_json_dir / f"{stem}.json"


def derive_target_revision_digit(row: dict) -> str | None:
    values = [
        str(row.get("pdf_stem") or ""),
        Path(str(row.get("pdf_path") or "")).stem,
    ]
    for value in values:
        match = REVISION_DIGIT_RE.search(value)
        if match:
            return match.group("digit")
    return None


def _load_marker_seed(marker_row: dict, delta_json_dir: Path, target_revision_digit: str | None) -> MarkerSeed:
    roi_bbox = [int(value) for value in marker_row["roi_bbox_page"]]
    center_x = float(roi_bbox[0] + roi_bbox[2] / 2)
    center_y = float(roi_bbox[1] + roi_bbox[3] / 2)
    marker_bbox = [int(round(center_x - 90)), int(round(center_y - 90)), 180, 180]
    marker_digit = None if marker_row.get("delta_digit") is None else str(marker_row.get("delta_digit"))

    delta_idx = _delta_index_from_id(str(marker_row.get("delta_id") or ""))
    if delta_idx is not None:
        try:
            payload = read_json(_delta_payload_path(delta_json_dir, marker_row))
            deltas = payload.get("active_deltas", [])
            if 0 <= delta_idx < len(deltas):
                delta = deltas[delta_idx]
                center = delta.get("center")
                if center:
                    center_x = float(center["x"])
                    center_y = float(center["y"])
                marker_digit = None if delta.get("digit") is None else str(delta.get("digit"))
                marker_bbox = marker_bbox_from_delta(delta, (center_x, center_y))
        except Exception:
            pass

    marker_matches_target = None if target_revision_digit is None or marker_digit is None else marker_digit == target_revision_digit
    return MarkerSeed(
        pdf_path=str(Path(marker_row["pdf_path"]).resolve()),
        page_index=int(marker_row["page_index"]),
        seed_id=str(marker_row.get("delta_id") or ""),
        marker_digit=marker_digit,
        center_x=center_x,
        center_y=center_y,
        marker_bbox=marker_bbox,
        marker_matches_target=marker_matches_target,
        target_revision_digit=target_revision_digit,
    )


def _load_marker_seeds(
    marker_manifest: Path,
    delta_json_dir: Path,
    page_lookup: dict[tuple[str, int], dict],
    target_revision_digit: str | None,
    target_revision_map: dict[str, str] | None = None,
) -> dict[tuple[str, int], list[MarkerSeed]]:
    seeds_by_page: dict[tuple[str, int], list[MarkerSeed]] = {}
    for row in read_jsonl(marker_manifest):
        if row.get("is_excluded"):
            continue
        try:
            pdf_path = str(Path(row["pdf_path"]).resolve())
            page_index = int(row["page_index"])
            page_row = page_lookup.get((pdf_path, page_index), row)
            target = resolve_target_revision_digit(page_row, target_revision_digit, target_revision_map)
            seed = _load_marker_seed(row, delta_json_dir, target)
        except KeyError:
            continue
        seeds_by_page.setdefault((seed.pdf_path, seed.page_index), []).append(seed)
    return seeds_by_page


def _load_target_revision_map(path: str | Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    mapping: dict[str, str] = {}
    map_path = Path(path)
    if map_path.suffix.lower() == ".json":
        raw = json.loads(map_path.read_text(encoding="utf-8"))
        items = raw.items() if isinstance(raw, dict) else enumerate(raw if isinstance(raw, list) else [])
        for key, value in items:
            if isinstance(value, dict):
                digit = value.get("target_revision_digit") or value.get("target_digit") or value.get("digit")
                for key_name in ("pdf_path", "pdf_stem", "source_file"):
                    source_value = value.get(key_name)
                    if digit is not None and source_value:
                        mapping[str(source_value).lower()] = str(digit)
            elif value is not None:
                mapping[str(key).lower()] = str(value)
        return mapping

    for row in read_jsonl(map_path):
        digit = row.get("target_revision_digit") or row.get("target_digit") or row.get("digit")
        if digit is None:
            continue
        for key_name in ("pdf_path", "pdf_stem", "source_file"):
            value = row.get(key_name)
            if value:
                mapping[str(value).lower()] = str(digit)
    return mapping


def resolve_target_revision_digit(
    row: dict,
    explicit_digit: str | None = None,
    target_revision_map: dict[str, str] | None = None,
) -> str | None:
    if explicit_digit is not None:
        return str(explicit_digit)
    if target_revision_map:
        pdf_path = str(Path(row.get("pdf_path") or "").resolve()).lower()
        pdf_stem = str(row.get("pdf_stem") or Path(str(row.get("pdf_path") or "")).stem).lower()
        for key in (pdf_path, pdf_stem):
            if key in target_revision_map:
                return str(target_revision_map[key])
    return derive_target_revision_digit(row)


def _offsets(include_diagonals: bool) -> list[tuple[str, float, float]]:
    offsets = [
        ("center", 0.0, 0.0),
        ("left", -0.55, 0.0),
        ("right", 0.55, 0.0),
        ("up", 0.0, -0.55),
        ("down", 0.0, 0.55),
    ]
    if include_diagonals:
        offsets.extend(
            [
                ("up_left", -0.45, -0.45),
                ("up_right", 0.45, -0.45),
                ("down_left", -0.45, 0.45),
                ("down_right", 0.45, 0.45),
            ]
        )
    return offsets


def _crop_bbox_for_marker(
    seed: MarkerSeed,
    crop_size: int,
    offset_name: str,
    offset_x: float,
    offset_y: float,
    page_width: int,
    page_height: int,
) -> tuple[str, list[int]]:
    cx = seed.center_x + offset_x * crop_size
    cy = seed.center_y + offset_y * crop_size
    bbox = [
        int(round(cx - crop_size / 2)),
        int(round(cy - crop_size / 2)),
        crop_size,
        crop_size,
    ]
    return offset_name, clip_bbox_xywh(bbox, page_width, page_height)


def ink_ratio(crop: np.ndarray) -> float:
    if crop.size == 0:
        return 0.0
    return float(np.count_nonzero(crop < 235)) / float(crop.size)


def cloud_likeness_score(crop: np.ndarray) -> float:
    if crop.size == 0:
        return 0.0
    scale = min(1.0, 720.0 / float(max(crop.shape[:2])))
    small = crop
    if scale < 1.0:
        small = cv2.resize(crop, (int(round(crop.shape[1] * scale)), int(round(crop.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    edges = cv2.Canny(cv2.GaussianBlur(small, (3, 3), 0), 70, 170)
    edge_pixels = int(np.count_nonzero(edges))
    if edge_pixels == 0:
        return 0.0

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    curved = 0
    short_fragments = 0
    for contour in contours:
        if len(contour) < 8:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        perimeter = float(cv2.arcLength(contour, False))
        if perimeter < 14:
            continue
        chord = float(np.linalg.norm(contour[0][0].astype(float) - contour[-1][0].astype(float)))
        bend = perimeter / max(chord, max(w, h), 1.0)
        aspect = max(w / max(1, h), h / max(1, w))
        if 18 <= perimeter <= 260 and bend >= 1.15 and aspect <= 6.0:
            curved += 1
        if 12 <= perimeter <= 180:
            short_fragments += 1

    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=55, minLineLength=90, maxLineGap=8)
    line_penalty = 0.0
    if lines is not None:
        length = 0.0
        for line in lines[:, 0, :]:
            x1, y1, x2, y2 = line
            length += float(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)
        line_penalty = min(0.45, length / max(edge_pixels * 2.2, 1.0))

    score = 0.62 * min(1.0, curved / 24.0) + 0.28 * min(1.0, short_fragments / 70.0) - line_penalty
    return round(max(0.0, min(1.0, score)), 4)


def _is_title_block_region(seed: MarkerSeed, page_width: int, page_height: int) -> bool:
    return seed.center_x >= page_width * 0.72 and seed.center_y >= page_height * 0.62


def generate_marker_neighborhood_crops(
    gray: np.ndarray,
    seeds: list[MarkerSeed],
    crop_size: int,
    crop_size_large: int,
    include_diagonals: bool,
    blank_ink_threshold: float,
    skip_title_block: bool,
) -> list[CloudCrop]:
    page_height, page_width = gray.shape[:2]
    crop_sizes = [crop_size]
    if crop_size_large and crop_size_large != crop_size:
        crop_sizes.append(crop_size_large)

    crops: list[CloudCrop] = []
    for seed in seeds:
        if skip_title_block and _is_title_block_region(seed, page_width, page_height):
            continue
        for size in crop_sizes:
            for offset_name, offset_x, offset_y in _offsets(include_diagonals):
                crop_offset, bbox = _crop_bbox_for_marker(seed, size, offset_name, offset_x, offset_y, page_width, page_height)
                x, y, w, h = bbox
                crop = gray[y : y + h, x : x + w]
                ratio = ink_ratio(crop)
                if ratio < blank_ink_threshold:
                    continue
                crops.append(
                    CloudCrop(
                        bbox=bbox,
                        crop_offset=f"{crop_offset}_{size}",
                        marker=seed,
                        cloud_likeness=cloud_likeness_score(crop),
                        ink_ratio=round(ratio, 6),
                    )
                )
    return crops


def marker_seed_counts(seeds_by_page: dict[tuple[str, int], list[MarkerSeed]]) -> dict[str, int]:
    counts = {
        "total_markers": 0,
        "matching_target_markers": 0,
        "old_nonmatching_markers": 0,
        "unknown_digit_markers": 0,
        "unknown_target_markers": 0,
    }
    for seeds in seeds_by_page.values():
        for seed in seeds:
            counts["total_markers"] += 1
            if seed.marker_digit is None:
                counts["unknown_digit_markers"] += 1
            if seed.target_revision_digit is None:
                counts["unknown_target_markers"] += 1
            if seed.marker_matches_target is True:
                counts["matching_target_markers"] += 1
            elif seed.marker_matches_target is False:
                counts["old_nonmatching_markers"] += 1
    return counts


def dedupe_crops(crops: list[CloudCrop], iou_threshold: float) -> list[CloudCrop]:
    ordered = sorted(crops, key=lambda item: (item.cloud_likeness, item.ink_ratio), reverse=True)
    kept: list[CloudCrop] = []
    for crop in ordered:
        if any(bbox_iou(crop.bbox, existing.bbox) >= iou_threshold for existing in kept):
            continue
        kept.append(crop)
    return kept


def _row_for_crop(
    row: dict,
    crop: CloudCrop,
    roi_id: str,
    image_path: Path,
    label_path: Path,
) -> dict:
    pdf_path = str(Path(row["pdf_path"]).resolve())
    page_index = int(row["page_index"])
    return {
        "pdf_path": pdf_path,
        "page_index": page_index,
        "cloud_roi_id": roi_id,
        "roi_type": "cloud_candidate" if crop.marker.marker_matches_target is True else "marker_context",
        "seed_type": "marker_neighborhood" if crop.marker.marker_matches_target is True else "old_marker_context",
        "contains_marker": True,
        "delta_digit": crop.marker.marker_digit,
        "marker_digit": crop.marker.marker_digit,
        "target_revision_digit": crop.marker.target_revision_digit,
        "marker_matches_target": crop.marker.marker_matches_target,
        "marker_seed_id": crop.marker.seed_id,
        "marker_bbox": crop.marker.marker_bbox,
        "seed_marker_page": [crop.marker.center_x, crop.marker.center_y],
        "crop_offset": crop.crop_offset,
        "bbox_on_page": crop.bbox,
        "roi_bbox_page": crop.bbox,
        "image_path": str(image_path),
        "roi_image_path": str(image_path),
        "label_path": str(label_path),
        "split": assign_split(pdf_path, page_index),
        "is_excluded": False,
        "exclude_reason": "none",
        "cloud_likeness": crop.cloud_likeness,
        "cloud_candidate_score": crop.cloud_likeness,
        "ink_ratio": crop.ink_ratio,
    }


def _clean_cloud_images(roi_dir: Path) -> None:
    if not roi_dir.exists():
        return
    for path in roi_dir.glob("*.png"):
        if path.is_file():
            path.unlink()


def extract_cloud_rois(
    cfg: CloudHammerConfig,
    pages_manifest: str | Path | None = None,
    marker_manifest: str | Path | None = None,
    target_revision_digit: str | None = None,
    target_revision_map: str | Path | None = None,
    include_nonmatching_markers: bool = False,
    delta_json_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    limit: int | None = None,
    crop_size: int = DEFAULT_CROP_SIZE,
    crop_size_large: int = DEFAULT_CROP_SIZE_LARGE,
    include_diagonals: bool = False,
    dedupe_iou: float = DEFAULT_DEDUPE_IOU,
    blank_ink_threshold: float = DEFAULT_BLANK_INK_RATIO,
    skip_title_block: bool = True,
    overwrite: bool = False,
) -> int:
    cfg.ensure_directories()
    page_manifest_path = Path(pages_manifest) if pages_manifest is not None else cfg.path("manifests") / "pages.jsonl"
    marker_manifest_path = Path(marker_manifest) if marker_manifest is not None else cfg.path("manifests") / "roi_manifest.jsonl"
    delta_dir = Path(delta_json_dir) if delta_json_dir is not None else cfg.path("delta_json")
    roi_dir = Path(output_dir) if output_dir is not None else cfg.path("cloud_roi_images")
    cloud_manifest_path = (
        Path(manifest_path) if manifest_path is not None else cfg.path("manifests") / "cloud_roi_manifest.jsonl"
    )
    label_dir = cfg.path("cloud_labels")
    roi_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    if overwrite:
        _clean_cloud_images(roi_dir)

    page_rows = [row for row in read_jsonl(page_manifest_path) if row.get("page_kind") == "drawing"]
    page_lookup = {
        (str(Path(row["pdf_path"]).resolve()), int(row["page_index"])): row
        for row in page_rows
    }
    page_counts = count_page_filter_results(page_rows, inspect_pdf_text=True)
    print(
        "page filter: "
        f"total={page_counts['total_pages']} "
        f"included={page_counts['included_pages']} "
        f"excluded_index_cover={page_counts['excluded_index_cover_pages']}"
    )

    target_map = _load_target_revision_map(target_revision_map)
    seeds_by_page = _load_marker_seeds(
        marker_manifest_path,
        delta_dir,
        page_lookup=page_lookup,
        target_revision_digit=target_revision_digit,
        target_revision_map=target_map,
    )
    counts = marker_seed_counts(seeds_by_page)
    derived_targets = sorted(
        {
            seed.target_revision_digit
            for seeds in seeds_by_page.values()
            for seed in seeds
            if seed.target_revision_digit is not None
        }
    )
    print(
        "target revision digits: "
        f"{', '.join(derived_targets) if derived_targets else 'none'}"
        + (" (explicit)" if target_revision_digit is not None else " (derived/mapped)")
    )
    print(
        "marker filter: "
        f"total={counts['total_markers']} "
        f"matching_target={counts['matching_target_markers']} "
        f"old_nonmatching_skipped={counts['old_nonmatching_markers'] if not include_nonmatching_markers else 0} "
        f"old_nonmatching_context={counts['old_nonmatching_markers'] if include_nonmatching_markers else 0} "
        f"unknown_digit={counts['unknown_digit_markers']} "
        f"unknown_target={counts['unknown_target_markers']}"
    )
    rows: list[dict] = []
    included_pages = 0
    skipped_pages_without_markers = 0
    skipped_title_block_markers = 0

    for page_row in page_rows:
        filter_result = classify_roi_source_page_with_pdf_text(page_row)
        if filter_result.is_excluded:
            continue
        if limit is not None and included_pages >= limit:
            break

        pdf_path = str(Path(page_row["pdf_path"]).resolve())
        page_index = int(page_row["page_index"])
        seeds = seeds_by_page.get((pdf_path, page_index), [])
        if include_nonmatching_markers:
            seeds = [seed for seed in seeds if seed.marker_matches_target is True or seed.marker_matches_target is False]
        else:
            seeds = [seed for seed in seeds if seed.marker_matches_target is True]
        if not seeds:
            skipped_pages_without_markers += 1
            continue

        render_path = page_row.get("render_path")
        if not render_path or not Path(render_path).exists():
            continue
        gray = cv2.imread(str(render_path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            continue

        crops = generate_marker_neighborhood_crops(
            gray,
            seeds,
            crop_size=crop_size,
            crop_size_large=crop_size_large,
            include_diagonals=include_diagonals,
            blank_ink_threshold=blank_ink_threshold,
            skip_title_block=skip_title_block,
        )
        if skip_title_block:
            page_height, page_width = gray.shape[:2]
            skipped_title_block_markers += sum(1 for seed in seeds if _is_title_block_region(seed, page_width, page_height))
        crops = dedupe_crops(crops, dedupe_iou)
        if not crops:
            continue

        included_pages += 1
        page_key = str(crops[0].marker.seed_id).rsplit("_d", 1)[0]
        for idx, crop in enumerate(crops, start=1):
            roi_id = f"{page_key}_m{idx:03d}"
            roi_path = roi_dir / f"{roi_id}.png"
            label_path = label_dir / f"{roi_id}.txt"
            if overwrite or not roi_path.exists():
                x, y, w, h = crop.bbox
                cv2.imwrite(str(roi_path), gray[y : y + h, x : x + w])
            rows.append(_row_for_crop(page_row, crop, roi_id, roi_path, label_path))

    write_count = write_jsonl(cloud_manifest_path, rows)
    print(
        "marker seeds: "
        f"pages_with_markers={len(seeds_by_page)} "
        f"processed_pages={included_pages} "
        f"skipped_pages_without_markers={skipped_pages_without_markers} "
        f"skipped_title_block_markers={skipped_title_block_markers}"
    )
    return write_count
