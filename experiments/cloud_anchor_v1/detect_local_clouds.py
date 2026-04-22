"""delta-anchored local cloud crop proposals.

This is a pragmatic reboot of the cloud stage:

- The delta detector gives us `active_deltas` for the current revision.
- For each active delta, we only search a local ROI around that anchor.
- Inside that ROI, we reuse the cloud experiment's text mask, line mask, and
  scallop matcher, but we do NOT try to solve the whole page at once.
- We propose a crop box on the raw render, not a perfect cloud polygon.

The output is intended as a handoff for the next iteration: overlays, raw crops,
and a JSON summary of the proposed cloud regions.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
CLOUD_V2_DIR = REPO_ROOT / "experiments" / "2026_04_cloud_detector_v2"
DEFAULT_DELTA_JSON = (
    REPO_ROOT
    / "experiments"
    / "delta_v4"
    / "output"
    / "Revision #1 - Drawing Changes_p17_denoise_2_delta_v4_overlay_results.json"
)
OUTPUT_DIR = Path(__file__).parent / "output"

sys.path.insert(0, str(CLOUD_V2_DIR))
from common import get_text_word_rects, render_page_gray  # noqa: E402
from stages.detect_scallops import ORIENTATION_COLORS, Scallop, detect_scallops  # noqa: E402
from stages.mask_lines import mask_lines  # noqa: E402
from stages.mask_text import mask_text  # noqa: E402

ROI_HALF_SIZE = 700
SCALLOP_THRESHOLD = 0.48
SCALLOP_RADII_TO_TRY = (180, 240, 320, 420)
MIN_SELECTED_HITS = 4
SCALLOP_BBOX_PAD = 120
TRIANGLE_BBOX_PAD = 40
FALLBACK_DELTA_CROP_HALF_SIZE = 260
MIN_COMPONENT_AREA = 80
COMPONENT_TOUCH_PAD = 80
COMPONENT_LINK_DISTANCE = 120
COMPONENT_BBOX_PAD = 60
LOOP_CLOSE_KERNELS = (3, 5, 7, 9)
LOOP_MIN_AREA = 150
LOOP_MIN_PERIMETER = 120
LOOP_MAX_BBOX_FRACTION = 0.75
LOOP_TRIANGLE_ERASE_KERNEL = 9
LOOP_CONTOUR_HIT_PAD = 25
LOOP_BBOX_HIT_PAD = 15
LOOP_SCORE_MIN = 12.0


@dataclass(frozen=True)
class LocalROI:
    image: np.ndarray
    x0: int
    y0: int
    x1: int
    y1: int


@dataclass(frozen=True)
class CloudProposal:
    delta_idx: int
    delta_digit: str | None
    delta_status: str
    selection_mode: str
    mask_mode: str
    scallop_hits_total: int
    scallop_hits_selected: int
    scallop_selection_radius: int | None
    confidence: float
    roi_bbox_page: tuple[int, int, int, int]
    crop_bbox_page: tuple[int, int, int, int]
    loop_close_kernel: int | None
    loop_triangle_erased: bool | None
    loop_score: float | None
    loop_bbox_page: tuple[int, int, int, int] | None
    loop_contour_hits: int
    loop_bbox_hits: int


@dataclass(frozen=True)
class LoopCandidate:
    close_kernel: int
    triangle_erased: bool
    score: float
    contour_hits: int
    bbox_hits: int
    area: float
    perimeter: float
    bbox: tuple[int, int, int, int]
    bump_area: float
    bump_per: float
    contour: np.ndarray


def load_delta_results(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def crop_around_center(gray: np.ndarray, center_x: float, center_y: float, half_size: int = ROI_HALF_SIZE) -> LocalROI:
    cx = int(round(center_x))
    cy = int(round(center_y))
    x0 = max(0, cx - half_size)
    y0 = max(0, cy - half_size)
    x1 = min(gray.shape[1], cx + half_size)
    y1 = min(gray.shape[0], cy + half_size)
    return LocalROI(gray[y0:y1, x0:x1].copy(), x0, y0, x1, y1)


def local_triangle_points(delta_record: dict, roi: LocalROI) -> list[tuple[float, float]]:
    tri = delta_record["triangle"]
    return [
        (float(tri["apex"]["x"]) - roi.x0, float(tri["apex"]["y"]) - roi.y0),
        (float(tri["left_base"]["x"]) - roi.x0, float(tri["left_base"]["y"]) - roi.y0),
        (float(tri["right_base"]["x"]) - roi.x0, float(tri["right_base"]["y"]) - roi.y0),
    ]


def triangle_bbox(points: list[tuple[float, float]], pad: int = TRIANGLE_BBOX_PAD) -> tuple[int, int, int, int]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (
        int(np.floor(min(xs) - pad)),
        int(np.floor(min(ys) - pad)),
        int(np.ceil(max(xs) + pad)),
        int(np.ceil(max(ys) + pad)),
    )


def clamp_bbox(bbox: tuple[int, int, int, int], shape: tuple[int, int]) -> tuple[int, int, int, int]:
    h, w = shape[:2]
    x0, y0, x1, y1 = bbox
    x0 = max(0, min(w, x0))
    y0 = max(0, min(h, y0))
    x1 = max(0, min(w, x1))
    y1 = max(0, min(h, y1))
    if x1 <= x0:
        x1 = min(w, x0 + 1)
    if y1 <= y0:
        y1 = min(h, y0 + 1)
    return (x0, y0, x1, y1)


def union_bbox(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def bbox_distance(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    dx = max(0, max(b[0] - a[2], a[0] - b[2]))
    dy = max(0, max(b[1] - a[3], a[1] - b[3]))
    return max(dx, dy)


def component_boxes(binary: np.ndarray, min_area: int = MIN_COMPONENT_AREA) -> list[tuple[int, tuple[int, int, int, int]]]:
    n_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    out: list[tuple[int, tuple[int, int, int, int]]] = []
    for idx in range(1, n_labels):
        x, y, w, h, area = stats[idx]
        if int(area) < min_area:
            continue
        out.append((int(area), (int(x), int(y), int(x + w), int(y + h))))
    return out


def select_component_cloud_bbox(
    line_masked_roi: np.ndarray,
    delta_box: tuple[int, int, int, int],
) -> tuple[tuple[int, int, int, int] | None, str]:
    binary = cv2.threshold(line_masked_roi, 200, 255, cv2.THRESH_BINARY_INV)[1]
    comps = component_boxes(binary)
    if not comps:
        return None, "no_component_seed"

    touch_box = (
        delta_box[0] - COMPONENT_TOUCH_PAD,
        delta_box[1] - COMPONENT_TOUCH_PAD,
        delta_box[2] + COMPONENT_TOUCH_PAD,
        delta_box[3] + COMPONENT_TOUCH_PAD,
    )
    seeds = [comp for comp in comps if bbox_distance(comp[1], touch_box) == 0]
    if not seeds:
        return None, "no_component_seed"

    seed = max(seeds, key=lambda comp: comp[0])
    selected = [comp for comp in comps if bbox_distance(comp[1], seed[1]) <= COMPONENT_LINK_DISTANCE]
    union = seed[1]
    for _area, bbox in selected:
        union = union_bbox(union, bbox)
    padded = (
        union[0] - COMPONENT_BBOX_PAD,
        union[1] - COMPONENT_BBOX_PAD,
        union[2] + COMPONENT_BBOX_PAD,
        union[3] + COMPONENT_BBOX_PAD,
    )
    return padded, "component_seed_neighborhood"


def selected_hits_near_delta(
    hits: list[Scallop],
    delta_local_center: tuple[float, float],
) -> tuple[list[Scallop], int | None, str]:
    cx, cy = delta_local_center
    if not hits:
        return [], None, "no_scallops"

    by_radius: dict[int, list[Scallop]] = {}
    for radius in SCALLOP_RADII_TO_TRY:
        chosen = [h for h in hits if ((h.x - cx) ** 2 + (h.y - cy) ** 2) ** 0.5 <= radius]
        by_radius[radius] = chosen
        if len(chosen) >= MIN_SELECTED_HITS:
            return chosen, radius, "delta_neighborhood"

    fallback_radius = max(SCALLOP_RADII_TO_TRY)
    fallback = by_radius[fallback_radius]
    if fallback:
        return fallback, fallback_radius, "delta_neighborhood_weak"
    return [], None, "no_scallops"


def bbox_from_hits(hits: list[Scallop]) -> tuple[int, int, int, int]:
    xs = [h.x for h in hits]
    ys = [h.y for h in hits]
    pad = max((h.radius for h in hits), default=18) * 2 + SCALLOP_BBOX_PAD
    return (
        int(np.floor(min(xs) - pad)),
        int(np.floor(min(ys) - pad)),
        int(np.ceil(max(xs) + pad)),
        int(np.ceil(max(ys) + pad)),
    )


def hits_inside_bbox(hits: list[Scallop], bbox: tuple[int, int, int, int], pad: int = 20) -> list[Scallop]:
    x0, y0, x1, y1 = bbox
    return [h for h in hits if x0 - pad <= h.x <= x1 + pad and y0 - pad <= h.y <= y1 + pad]


def shift_points(points: list[tuple[float, float]], dx: int, dy: int) -> list[tuple[float, float]]:
    return [(p[0] - dx, p[1] - dy) for p in points]


def triangle_erase_mask(shape: tuple[int, int], triangle_points: list[tuple[float, float]]) -> np.ndarray:
    mask = np.zeros(shape[:2], dtype=np.uint8)
    poly = np.array(triangle_points, dtype=np.int32).reshape((-1, 1, 2))
    cv2.fillPoly(mask, [poly], 255)
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (LOOP_TRIANGLE_ERASE_KERNEL, LOOP_TRIANGLE_ERASE_KERNEL),
    )
    return cv2.dilate(mask, kernel, iterations=1)


def scallop_hits_near_contour(hits: list[Scallop], contour: np.ndarray) -> tuple[int, int]:
    x, y, w, h = cv2.boundingRect(contour)
    bbox_hits = sum(
        1
        for hit in hits
        if x - LOOP_BBOX_HIT_PAD <= hit.x <= x + w + LOOP_BBOX_HIT_PAD
        and y - LOOP_BBOX_HIT_PAD <= hit.y <= y + h + LOOP_BBOX_HIT_PAD
    )
    contour_hits = sum(
        1
        for hit in hits
        if abs(cv2.pointPolygonTest(contour, (float(hit.x), float(hit.y)), True)) <= LOOP_CONTOUR_HIT_PAD
    )
    return contour_hits, bbox_hits


def compactness(area: float, perimeter: float) -> float:
    if perimeter <= 1e-6:
        return 1.0
    return float((4.0 * np.pi * area) / (perimeter * perimeter))


def select_loop_candidate(
    line_masked_crop: np.ndarray,
    triangle_points_crop: list[tuple[float, float]],
    crop_hits: list[Scallop],
) -> LoopCandidate | None:
    best: LoopCandidate | None = None
    base_binary = cv2.threshold(line_masked_crop, 200, 255, cv2.THRESH_BINARY_INV)[1]
    crop_area = float(base_binary.shape[0] * base_binary.shape[1])

    for triangle_erased in (False, True):
        binary = base_binary.copy()
        if triangle_erased:
            tri_mask = triangle_erase_mask(binary.shape, triangle_points_crop)
            binary[tri_mask > 0] = 0

        for kernel_size in LOOP_CLOSE_KERNELS:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
            closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
            contours, _hier = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
            for contour in contours:
                area = float(cv2.contourArea(contour))
                if area < LOOP_MIN_AREA:
                    continue
                perimeter = float(cv2.arcLength(contour, True))
                if perimeter < LOOP_MIN_PERIMETER:
                    continue
                x, y, w, h = cv2.boundingRect(contour)
                if crop_area > 0 and ((w * h) / crop_area) > LOOP_MAX_BBOX_FRACTION:
                    continue

                hull = cv2.convexHull(contour)
                hull_area = max(float(cv2.contourArea(hull)), 1.0)
                hull_per = max(float(cv2.arcLength(hull, True)), 1.0)
                bump_area = 1.0 - (area / hull_area)
                bump_per = perimeter / hull_per
                contour_hits, bbox_hits = scallop_hits_near_contour(crop_hits, contour)
                verts = len(cv2.approxPolyDP(contour, 0.01 * perimeter, True))
                score = (
                    3.0 * contour_hits
                    + 1.0 * bbox_hits
                    + 2.4 * bump_per
                    + 1.6 * bump_area
                    + 0.03 * min(verts, 30)
                    - 3.0 * compactness(area, perimeter)
                )

                candidate = LoopCandidate(
                    close_kernel=kernel_size,
                    triangle_erased=triangle_erased,
                    score=score,
                    contour_hits=contour_hits,
                    bbox_hits=bbox_hits,
                    area=area,
                    perimeter=perimeter,
                    bbox=(x, y, x + w, y + h),
                    bump_area=bump_area,
                    bump_per=bump_per,
                    contour=contour.copy(),
                )
                if best is None or candidate.score > best.score:
                    best = candidate

    if best is None or best.score < LOOP_SCORE_MIN:
        return None
    return best


def loop_confidence(candidate: LoopCandidate) -> float:
    base = 0.20
    base += min(0.45, candidate.contour_hits * 0.08)
    base += min(0.20, max(0.0, candidate.bump_per - 1.0) * 0.20)
    base += min(0.15, max(0.0, candidate.bump_area) * 0.20)
    return max(0.0, min(1.0, base))


def fallback_delta_bbox(delta_points: list[tuple[float, float]]) -> tuple[int, int, int, int]:
    xs = [p[0] for p in delta_points]
    ys = [p[1] for p in delta_points]
    cx = int(round(sum(xs) / len(xs)))
    cy = int(round(sum(ys) / len(ys)))
    return (
        cx - FALLBACK_DELTA_CROP_HALF_SIZE,
        cy - FALLBACK_DELTA_CROP_HALF_SIZE,
        cx + FALLBACK_DELTA_CROP_HALF_SIZE,
        cy + FALLBACK_DELTA_CROP_HALF_SIZE,
    )


def bbox_to_page_coords(bbox: tuple[int, int, int, int], roi: LocalROI) -> tuple[int, int, int, int]:
    return (bbox[0] + roi.x0, bbox[1] + roi.y0, bbox[2] + roi.x0, bbox[3] + roi.y0)


def confidence_from_selection(selected_hits: list[Scallop], selection_mode: str) -> float:
    if selection_mode == "component_seed_neighborhood":
        return max(0.55, min(1.0, 0.25 + len(selected_hits) / 8.0))
    if not selected_hits:
        return 0.0
    base = min(1.0, len(selected_hits) / 8.0)
    if selection_mode == "delta_neighborhood":
        return min(1.0, base + 0.15)
    if selection_mode == "delta_neighborhood_weak":
        return max(0.2, base * 0.65)
    return base * 0.3


def draw_triangle(bgr: np.ndarray, points: list[tuple[float, float]], color: tuple[int, int, int]) -> None:
    poly = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(bgr, [poly], isClosed=True, color=color, thickness=3)


def draw_bbox(bgr: np.ndarray, bbox: tuple[int, int, int, int], color: tuple[int, int, int]) -> None:
    x0, y0, x1, y1 = bbox
    cv2.rectangle(bgr, (x0, y0), (x1, y1), color, 3)


def draw_selected_hits(bgr: np.ndarray, hits: list[Scallop]) -> None:
    for hit in hits:
        color = ORIENTATION_COLORS[hit.orientation]
        cv2.circle(bgr, (hit.x, hit.y), max(4, hit.radius // 3), color, 2)


def process_delta(
    delta_idx: int,
    delta_record: dict,
    raw_gray: np.ndarray,
    line_masked_gray: np.ndarray,
    out_dir: Path,
    page_stem: str,
) -> CloudProposal:
    delta_center = delta_record["center"]
    roi_raw = crop_around_center(raw_gray, delta_center["x"], delta_center["y"])
    roi_line = crop_around_center(line_masked_gray, delta_center["x"], delta_center["y"])
    delta_points = local_triangle_points(delta_record, roi_raw)
    delta_box = triangle_bbox(delta_points)
    delta_box = clamp_bbox(delta_box, roi_raw.image.shape)

    hits = detect_scallops(roi_line.image, threshold=SCALLOP_THRESHOLD)
    component_box, selection_mode = select_component_cloud_bbox(roi_line.image, delta_box)

    if component_box is not None:
        component_box = clamp_bbox(component_box, roi_raw.image.shape)
        selected_hits = hits_inside_bbox(hits, component_box)
        chosen_radius = None
        scallop_box = component_box
        crop_box = union_bbox(component_box, delta_box)
    else:
        local_center = (
            float(delta_center["x"]) - roi_raw.x0,
            float(delta_center["y"]) - roi_raw.y0,
        )
        selected_hits, chosen_radius, selection_mode = selected_hits_near_delta(hits, local_center)
        if selected_hits:
            scallop_box = clamp_bbox(bbox_from_hits(selected_hits), roi_raw.image.shape)
            crop_box = union_bbox(scallop_box, delta_box)
        else:
            scallop_box = None
            chosen_radius = None
            selection_mode = "delta_fallback_box"
            selected_hits = []
            crop_box = clamp_bbox(fallback_delta_bbox(delta_points), roi_raw.image.shape)

    crop_box = clamp_bbox(crop_box, roi_raw.image.shape)
    crop_page = bbox_to_page_coords(crop_box, roi_raw)

    crop = roi_raw.image[crop_box[1]:crop_box[3], crop_box[0]:crop_box[2]]
    crop_line = roi_line.image[crop_box[1]:crop_box[3], crop_box[0]:crop_box[2]]
    crop_triangle_points = shift_points(delta_points, crop_box[0], crop_box[1])
    crop_hits = [
        Scallop(
            x=int(hit.x - crop_box[0]),
            y=int(hit.y - crop_box[1]),
            radius=hit.radius,
            orientation=hit.orientation,
            confidence=hit.confidence,
        )
        for hit in hits
        if crop_box[0] <= hit.x < crop_box[2] and crop_box[1] <= hit.y < crop_box[3]
    ]
    loop_candidate = select_loop_candidate(crop_line, crop_triangle_points, crop_hits)
    loop_bbox_page: tuple[int, int, int, int] | None = None
    loop_close_kernel: int | None = None
    loop_triangle_erased: bool | None = None
    loop_score: float | None = None
    loop_contour_hits = 0
    loop_bbox_hits = 0
    mask_mode = "bbox_crop"

    overlay = cv2.cvtColor(roi_raw.image, cv2.COLOR_GRAY2BGR)
    draw_triangle(overlay, delta_points, (0, 220, 0))
    if scallop_box is not None:
        draw_bbox(overlay, scallop_box, (255, 0, 255))
    draw_bbox(overlay, crop_box, (0, 0, 220))
    draw_selected_hits(overlay, selected_hits)
    cv2.putText(
        overlay,
        f"delta {delta_idx}  {selection_mode}  hits={len(selected_hits)}/{len(hits)}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )

    base_name = f"{page_stem}_delta{delta_idx:02d}"
    cv2.imwrite(str(out_dir / f"{base_name}_roi_raw.png"), roi_raw.image)
    cv2.imwrite(str(out_dir / f"{base_name}_roi_line_masked.png"), roi_line.image)
    cv2.imwrite(str(out_dir / f"{base_name}_overlay.png"), overlay)
    cv2.imwrite(str(out_dir / f"{base_name}_crop.png"), crop)

    if loop_candidate is not None:
        mask_mode = "loop_mask"
        loop_close_kernel = loop_candidate.close_kernel
        loop_triangle_erased = loop_candidate.triangle_erased
        loop_score = loop_candidate.score
        loop_contour_hits = loop_candidate.contour_hits
        loop_bbox_hits = loop_candidate.bbox_hits
        loop_bbox_page = (
            loop_candidate.bbox[0] + roi_raw.x0 + crop_box[0],
            loop_candidate.bbox[1] + roi_raw.y0 + crop_box[1],
            loop_candidate.bbox[2] + roi_raw.x0 + crop_box[0],
            loop_candidate.bbox[3] + roi_raw.y0 + crop_box[1],
        )

        loop_overlay = cv2.cvtColor(crop.copy(), cv2.COLOR_GRAY2BGR)
        loop_mask = np.zeros(crop.shape[:2], dtype=np.uint8)
        cv2.drawContours(loop_mask, [loop_candidate.contour], -1, 255, -1)
        loop_masked = crop.copy()
        loop_masked[loop_mask == 0] = 255

        draw_triangle(loop_overlay, crop_triangle_points, (0, 220, 0))
        cv2.drawContours(loop_overlay, [loop_candidate.contour], -1, (255, 0, 255), 3)
        draw_bbox(loop_overlay, loop_candidate.bbox, (0, 0, 220))
        draw_selected_hits(loop_overlay, crop_hits)
        cv2.putText(
            loop_overlay,
            f"loop k={loop_candidate.close_kernel} erase={int(loop_candidate.triangle_erased)} score={loop_candidate.score:.2f} hits={loop_candidate.contour_hits}/{loop_candidate.bbox_hits}",
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.imwrite(str(out_dir / f"{base_name}_loop_overlay.png"), loop_overlay)
        cv2.imwrite(str(out_dir / f"{base_name}_loop_mask.png"), loop_mask)
        cv2.imwrite(str(out_dir / f"{base_name}_loop_masked.png"), loop_masked)

    return CloudProposal(
        delta_idx=delta_idx,
        delta_digit=delta_record.get("digit"),
        delta_status=delta_record.get("status", "unknown"),
        selection_mode=selection_mode,
        mask_mode=mask_mode,
        scallop_hits_total=len(hits),
        scallop_hits_selected=len(selected_hits),
        scallop_selection_radius=chosen_radius,
        confidence=loop_confidence(loop_candidate) if loop_candidate is not None else confidence_from_selection(selected_hits, selection_mode),
        roi_bbox_page=(roi_raw.x0, roi_raw.y0, roi_raw.x1, roi_raw.y1),
        crop_bbox_page=crop_page,
        loop_close_kernel=loop_close_kernel,
        loop_triangle_erased=loop_triangle_erased,
        loop_score=loop_score,
        loop_bbox_page=loop_bbox_page,
        loop_contour_hits=loop_contour_hits,
        loop_bbox_hits=loop_bbox_hits,
    )


def page_stem_from_json(delta_results: dict) -> str:
    image_path = Path(delta_results["image_path"])
    return image_path.stem.replace("_denoise_2", "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delta-json", type=Path, default=DEFAULT_DELTA_JSON)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    delta_json_path = args.delta_json if args.delta_json.is_absolute() else (Path.cwd() / args.delta_json).resolve()
    if not delta_json_path.exists():
        print(f"Delta JSON not found: {delta_json_path}")
        return 1

    delta_results = load_delta_results(delta_json_path)
    pdf_path_str = delta_results.get("pdf_path")
    if not pdf_path_str:
        print("Delta JSON is missing pdf_path.")
        return 1
    pdf_path = Path(pdf_path_str)
    page_index = int(delta_results["page_index"])
    active_deltas = delta_results.get("active_deltas", [])
    if not active_deltas:
        print("No active deltas found in the input JSON.")
        return 0

    page_stem = page_stem_from_json(delta_results)
    out_dir = args.out_dir
    if out_dir is None:
        out_dir = OUTPUT_DIR / page_stem
    out_dir = out_dir if out_dir.is_absolute() else (Path.cwd() / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Rendering {pdf_path.name} page {page_index} ...")
    raw_gray, zoom = render_page_gray(pdf_path, page_index)
    text_rects = get_text_word_rects(pdf_path, page_index, zoom)
    text_masked = mask_text(raw_gray, text_rects)
    line_masked, _line_mask, stats = mask_lines(text_masked, page_kind="drawing")
    print(
        f"Masked page: text_rects={len(text_rects)} "
        f"line_mask_coverage={stats['line_mask_coverage_pct']:.2f}%"
    )

    proposals: list[CloudProposal] = []
    for idx, delta_record in enumerate(active_deltas, start=1):
        proposal = process_delta(idx, delta_record, raw_gray, line_masked, out_dir, page_stem)
        proposals.append(proposal)
        print(
            f"delta {idx:02d}: digit={proposal.delta_digit} mode={proposal.selection_mode} "
            f"mask={proposal.mask_mode} "
            f"hits={proposal.scallop_hits_selected}/{proposal.scallop_hits_total} "
            f"radius={proposal.scallop_selection_radius} "
            f"confidence={proposal.confidence:.2f}"
            + (
                f" loop_k={proposal.loop_close_kernel} erase={int(bool(proposal.loop_triangle_erased))} loop_score={proposal.loop_score:.2f}"
                if proposal.loop_score is not None
                else ""
            )
        )

    summary = {
        "delta_json": str(delta_json_path),
        "pdf_path": str(pdf_path),
        "page_index": page_index,
        "target_digit": delta_results.get("target_digit"),
        "active_delta_count": len(active_deltas),
        "proposals": [
            {
                "delta_idx": p.delta_idx,
                "delta_digit": p.delta_digit,
                "delta_status": p.delta_status,
                "selection_mode": p.selection_mode,
                "mask_mode": p.mask_mode,
                "scallop_hits_total": p.scallop_hits_total,
                "scallop_hits_selected": p.scallop_hits_selected,
                "scallop_selection_radius": p.scallop_selection_radius,
                "confidence": p.confidence,
                "roi_bbox_page": {
                    "x0": p.roi_bbox_page[0],
                    "y0": p.roi_bbox_page[1],
                    "x1": p.roi_bbox_page[2],
                    "y1": p.roi_bbox_page[3],
                },
                "crop_bbox_page": {
                    "x0": p.crop_bbox_page[0],
                    "y0": p.crop_bbox_page[1],
                    "x1": p.crop_bbox_page[2],
                    "y1": p.crop_bbox_page[3],
                },
                "loop_close_kernel": p.loop_close_kernel,
                "loop_triangle_erased": p.loop_triangle_erased,
                "loop_score": p.loop_score,
                "loop_contour_hits": p.loop_contour_hits,
                "loop_bbox_hits": p.loop_bbox_hits,
                "loop_bbox_page": (
                    {
                        "x0": p.loop_bbox_page[0],
                        "y0": p.loop_bbox_page[1],
                        "x1": p.loop_bbox_page[2],
                        "y1": p.loop_bbox_page[3],
                    }
                    if p.loop_bbox_page is not None
                    else None
                ),
            }
            for p in proposals
        ],
    }
    summary_path = out_dir / f"{page_stem}_cloud_proposals.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"summary -> {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
