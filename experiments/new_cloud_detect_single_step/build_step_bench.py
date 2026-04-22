from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import sys

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
ROI_HALF_SIZE = 700
OUTPUT_DIR = Path(__file__).parent / "output"

CLOUD_V2_DIR = REPO_ROOT / "experiments" / "2026_04_cloud_detector_v2"
sys.path.insert(0, str(CLOUD_V2_DIR))
from common import get_text_word_rects, render_page_gray  # noqa: E402
from stages.detect_scallops import ORIENTATION_COLORS, detect_scallops  # noqa: E402
from stages.mask_lines import mask_lines  # noqa: E402
from stages.mask_text import mask_text  # noqa: E402

THICKNESS_CLIP_MAX_PX = 6.0
COMPONENT_MIN_AREA = 80
THICKNESS_COMPONENT_TOP_N = 25
THIN_KEEP_MEDIAN_MAX_PX = 2.2
THIN_KEEP_P90_MAX_PX = 4.2
THIN_KEEP_THICK_FRACTION_MAX = 0.18
THIN_THICK_PIXEL_THRESHOLD_PX = 3.0
HARD_THICK_KERNEL = 3
HARD_THIN_REPAIR_KERNEL = 3
PAIR_RATIO = 1.70
PAIR_SMALL_RADII = (8, 10, 12, 14, 16, 18, 20)
PAIR_SPANS_DEG = (80, 100, 120)
PAIR_THICKNESSES = (1, 2)
PAIR_MATCH_THRESHOLD = 0.62
PAIR_TOP_HITS = 25


@dataclass(frozen=True)
class StepBenchCase:
    case_id: str
    description: str
    delta_json: Path
    active_delta_index: int  # 1-based index within active_deltas


CASES: tuple[StepBenchCase, ...] = (
    StepBenchCase(
        case_id="rev1_p17_delta07",
        description="Canonical Rev1 p17 active delta #7",
        delta_json=(
            REPO_ROOT
            / "experiments"
            / "delta_v4"
            / "output"
            / "Revision #1 - Drawing Changes_p17_denoise_2_delta_v4_overlay_results.json"
        ),
        active_delta_index=7,
    ),
    StepBenchCase(
        case_id="rev2_main_p11_delta01",
        description="Ugly Rev2 main p11 active delta #1",
        delta_json=(
            REPO_ROOT
            / "experiments"
            / "delta_v4"
            / "output"
            / "260309 - Drawing Rev2- Steel Grab Bars_p11_denoise_2_delta_v4_overlay_results.json"
        ),
        active_delta_index=1,
    ),
)


def load_delta_record(path: Path, active_delta_index: int) -> tuple[dict, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    active = data["active_deltas"][active_delta_index - 1]
    return data, active


def crop_bbox_from_center(center: dict, image_shape: tuple[int, int], half_size: int = ROI_HALF_SIZE) -> tuple[int, int, int, int]:
    cx = int(round(center["x"]))
    cy = int(round(center["y"]))
    h, w = image_shape[:2]
    x0 = max(0, cx - half_size)
    y0 = max(0, cy - half_size)
    x1 = min(w, cx + half_size)
    y1 = min(h, cy + half_size)
    return (x0, y0, x1, y1)


def crop_image(gray: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = bbox
    return gray[y0:y1, x0:x1].copy()


def local_triangle_points(delta_record: dict, bbox: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, _x1, _y1 = bbox
    tri = delta_record["triangle"]
    return np.array(
        [
            [int(round(tri["apex"]["x"] - x0)), int(round(tri["apex"]["y"] - y0))],
            [int(round(tri["left_base"]["x"] - x0)), int(round(tri["left_base"]["y"] - y0))],
            [int(round(tri["right_base"]["x"] - x0)), int(round(tri["right_base"]["y"] - y0))],
        ],
        dtype=np.int32,
    )


def draw_triangle(gray: np.ndarray, triangle_pts: np.ndarray) -> np.ndarray:
    out = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    cv2.polylines(out, [triangle_pts.reshape((-1, 1, 2))], isClosed=True, color=(0, 220, 0), thickness=3)
    return out


def binary_view(gray: np.ndarray) -> np.ndarray:
    binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)[1]
    return 255 - binary


def local_thickness(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)[1]
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
    thickness = dist * 2.0
    return binary, thickness


def components_overlay(gray: np.ndarray) -> np.ndarray:
    binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)[1]
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    out = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    kept = 0
    for idx in range(1, n_labels):
        x, y, w, h, area = stats[idx]
        if int(area) < COMPONENT_MIN_AREA:
            continue
        kept += 1
        cv2.rectangle(out, (int(x), int(y)), (int(x + w), int(y + h)), (0, 0, 220), 2)
        cv2.putText(
            out,
            f"{int(area)}",
            (int(x), max(15, int(y) - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (220, 0, 0),
            1,
            cv2.LINE_AA,
        )
    cv2.putText(
        out,
        f"components >=80px: {kept}",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    return out


def thickness_heatmap(gray: np.ndarray) -> np.ndarray:
    binary, thickness = local_thickness(gray)
    clipped = np.clip(thickness, 0.0, THICKNESS_CLIP_MAX_PX)
    if THICKNESS_CLIP_MAX_PX > 0:
        scaled = (clipped / THICKNESS_CLIP_MAX_PX * 255.0).astype(np.uint8)
    else:
        scaled = np.zeros_like(clipped, dtype=np.uint8)
    color = cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)
    out = np.full((*gray.shape, 3), 255, dtype=np.uint8)
    out[binary > 0] = color[binary > 0]
    cv2.putText(
        out,
        f"local thickness map (clip {THICKNESS_CLIP_MAX_PX:.1f}px)",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    return out


def component_thickness_overlay(gray: np.ndarray) -> np.ndarray:
    binary, thickness = local_thickness(gray)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    out = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    rows: list[tuple[int, int, int, int, int, float, float]] = []
    for idx in range(1, n_labels):
        x, y, w, h, area = stats[idx]
        area = int(area)
        if area < COMPONENT_MIN_AREA:
            continue
        mask = labels == idx
        median_thickness = float(np.median(thickness[mask])) if np.any(mask) else 0.0
        max_thickness = float(np.max(thickness[mask])) if np.any(mask) else 0.0
        rows.append((area, int(x), int(y), int(w), int(h), median_thickness, max_thickness))

    rows.sort(reverse=True)
    shown = 0
    for area, x, y, w, h, median_thickness, max_thickness in rows[:THICKNESS_COMPONENT_TOP_N]:
        shown += 1
        color = (0, 180, 0)
        if median_thickness > 2.4 or max_thickness > 5.0:
            color = (0, 0, 220)
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
        cv2.putText(
            out,
            f"A{area} med{median_thickness:.1f} max{max_thickness:.1f}",
            (x, max(15, y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            color,
            1,
            cv2.LINE_AA,
        )

    cv2.putText(
        out,
        f"top {shown} components by area with thickness stats",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    return out


def thin_component_filter(gray: np.ndarray) -> np.ndarray:
    binary, thickness = local_thickness(gray)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    kept = np.zeros_like(binary)
    for idx in range(1, n_labels):
        x, y, w, h, area = stats[idx]
        area = int(area)
        if area < COMPONENT_MIN_AREA:
            continue
        mask = labels == idx
        values = thickness[mask]
        if values.size == 0:
            continue
        median_thickness = float(np.median(values))
        p90_thickness = float(np.percentile(values, 90))
        thick_fraction = float(np.mean(values >= THIN_THICK_PIXEL_THRESHOLD_PX))
        keep = (
            median_thickness <= THIN_KEEP_MEDIAN_MAX_PX
            and p90_thickness <= THIN_KEEP_P90_MAX_PX
            and thick_fraction <= THIN_KEEP_THICK_FRACTION_MAX
        )
        if keep:
            kept[mask] = 255
    return 255 - kept


def hard_thin_filter(gray: np.ndarray) -> np.ndarray:
    binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (HARD_THICK_KERNEL, HARD_THICK_KERNEL))
    thick_seed = cv2.erode(binary, kernel, iterations=1)
    thick_mask = cv2.dilate(thick_seed, kernel, iterations=1)
    thin = cv2.bitwise_and(binary, cv2.bitwise_not(thick_mask))
    repair_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (HARD_THIN_REPAIR_KERNEL, HARD_THIN_REPAIR_KERNEL),
    )
    repaired = cv2.morphologyEx(thin, cv2.MORPH_CLOSE, repair_kernel, iterations=1)
    return 255 - repaired


def close_view(gray: np.ndarray, kernel_size: int) -> np.ndarray:
    binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    return 255 - closed


def scallops_overlay(gray: np.ndarray) -> np.ndarray:
    out = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    hits = detect_scallops(gray, threshold=0.48)
    for hit in hits:
        color = ORIENTATION_COLORS[hit.orientation]
        cv2.circle(out, (int(hit.x), int(hit.y)), max(4, hit.radius // 3), color, 2)
    cv2.putText(
        out,
        f"scallop hits: {len(hits)}",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    return out


def make_pair_template(
    small_radius: int,
    ratio: float,
    orientation: str,
    order: str,
    span_deg: int,
    line_thickness: int,
    pad: int = 4,
) -> np.ndarray:
    large_radius = max(small_radius + 1, int(round(small_radius * ratio)))
    if order == "SL":
        r1, r2 = small_radius, large_radius
    else:
        r1, r2 = large_radius, small_radius

    if orientation in ("TOP", "BOTTOM"):
        h = max(r1, r2) + 2 * pad
        w = 2 * r1 + 2 * r2 + 2 * pad
    else:
        h = 2 * r1 + 2 * r2 + 2 * pad
        w = max(r1, r2) + 2 * pad
    img = np.full((h, w), 255, dtype=np.uint8)

    if orientation == "TOP":
        baseline = h - pad
        c1 = (pad + r1, baseline)
        c2 = (pad + 2 * r1 + r2, baseline)
        center_deg = 270.0
    elif orientation == "BOTTOM":
        baseline = pad
        c1 = (pad + r1, baseline)
        c2 = (pad + 2 * r1 + r2, baseline)
        center_deg = 90.0
    elif orientation == "LEFT":
        baseline = w - pad
        c1 = (baseline, pad + r1)
        c2 = (baseline, pad + 2 * r1 + r2)
        center_deg = 180.0
    elif orientation == "RIGHT":
        baseline = pad
        c1 = (baseline, pad + r1)
        c2 = (baseline, pad + 2 * r1 + r2)
        center_deg = 0.0
    else:
        raise ValueError(f"Unknown orientation: {orientation}")

    start = center_deg - span_deg / 2.0
    end = center_deg + span_deg / 2.0
    cv2.ellipse(img, tuple(map(int, c1)), (r1, r1), 0, start, end, color=0, thickness=line_thickness)
    cv2.ellipse(img, tuple(map(int, c2)), (r2, r2), 0, start, end, color=0, thickness=line_thickness)
    return img


def pair_motif_overlay(gray: np.ndarray) -> np.ndarray:
    out = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    candidates: list[tuple[float, int, int, int, str, str, int, int, int]] = []
    for orientation, color in (
        ("TOP", (0, 0, 220)),
        ("BOTTOM", (0, 180, 0)),
        ("LEFT", (220, 0, 0)),
        ("RIGHT", (0, 180, 180)),
    ):
        for order in ("SL", "LS"):
            for small_radius in PAIR_SMALL_RADII:
                for span_deg in PAIR_SPANS_DEG:
                    for line_thickness in PAIR_THICKNESSES:
                        template = make_pair_template(
                            small_radius=small_radius,
                            ratio=PAIR_RATIO,
                            orientation=orientation,
                            order=order,
                            span_deg=span_deg,
                            line_thickness=line_thickness,
                        )
                        if gray.shape[0] < template.shape[0] or gray.shape[1] < template.shape[1]:
                            continue
                        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                        ys, xs = np.where(result >= PAIR_MATCH_THRESHOLD)
                        for y, x in zip(ys.tolist(), xs.tolist()):
                            candidates.append(
                                (
                                    float(result[y, x]),
                                    x,
                                    y,
                                    template.shape[1],
                                    orientation,
                                    order,
                                    small_radius,
                                    span_deg,
                                    line_thickness,
                                )
                            )

    kept: list[tuple[float, int, int, int, str, str, int, int, int]] = []
    for cand in sorted(candidates, key=lambda row: row[0], reverse=True):
        score, x, y, width, orientation, order, small_radius, span_deg, line_thickness = cand
        cx = x + width / 2.0
        cy = y + width / 4.0
        suppress = False
        for prev in kept:
            _, px, py, pwidth, *_ = prev
            pcx = px + pwidth / 2.0
            pcy = py + pwidth / 4.0
            if math.hypot(cx - pcx, cy - pcy) < max(width, pwidth) * 0.6:
                suppress = True
                break
        if not suppress:
            kept.append(cand)
        if len(kept) >= PAIR_TOP_HITS:
            break

    for score, x, y, width, orientation, order, small_radius, span_deg, line_thickness in kept:
        large_radius = max(small_radius + 1, int(round(small_radius * PAIR_RATIO)))
        template = make_pair_template(
            small_radius=small_radius,
            ratio=PAIR_RATIO,
            orientation=orientation,
            order=order,
            span_deg=span_deg,
            line_thickness=line_thickness,
        )
        th, tw = template.shape[:2]
        color = {
            "TOP": (0, 0, 220),
            "BOTTOM": (0, 180, 0),
            "LEFT": (220, 0, 0),
            "RIGHT": (0, 180, 180),
        }[orientation]
        cv2.rectangle(out, (x, y), (x + tw, y + th), color, 2)
        cv2.putText(
            out,
            f"{orientation}-{order} s{small_radius} l{large_radius} {score:.2f}",
            (x, max(15, y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            color,
            1,
            cv2.LINE_AA,
        )

    cv2.putText(
        out,
        f"paired arc hits: {len(kept)} ratio={PAIR_RATIO:.2f}",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    return out


def save_step(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)


def labeled_tile(image_path: Path, label: str, width: int = 360, height: int = 360) -> np.ndarray:
    img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if img is None:
        tile = np.full((height, width, 3), 255, dtype=np.uint8)
        cv2.putText(tile, "missing", (20, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 220), 2, cv2.LINE_AA)
        return tile
    tile = cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)
    tile = cv2.copyMakeBorder(tile, 36, 12, 12, 12, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    cv2.putText(tile, label, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2, cv2.LINE_AA)
    return tile


def make_contact_sheet(variant_dir: Path) -> None:
    steps = [
        ("step_00_input.png", "00 input"),
        ("step_01_binary.png", "01 binary"),
        ("step_02_components_overlay.png", "02 components"),
        ("step_03_close_k3.png", "03 close k3"),
        ("step_04_close_k5.png", "04 close k5"),
        ("step_05_close_k7.png", "05 close k7"),
        ("step_06_close_k9.png", "06 close k9"),
        ("step_07_scallops_overlay.png", "07 scallops"),
        ("step_08_thickness_heatmap.png", "08 thickness heatmap"),
        ("step_09_component_thickness_overlay.png", "09 thickness comps"),
        ("step_10_thin_component_filter.png", "10 thin comp filter"),
        ("step_11_hard_thin_filter.png", "11 hard thin filter"),
        ("step_12_pair_motif_overlay.png", "12 pair motif"),
    ]
    tiles = [labeled_tile(variant_dir / filename, label) for filename, label in steps]
    rows = []
    for idx in range(0, len(tiles), 2):
        left = tiles[idx]
        right = tiles[idx + 1] if idx + 1 < len(tiles) else np.full_like(left, 255)
        rows.append(np.hstack([left, right]))
    sheet = np.vstack(rows)
    save_step(variant_dir / "contact_sheet.png", sheet)


def current_line_masked_image(delta_data: dict) -> np.ndarray:
    pdf_path = Path(delta_data["pdf_path"])
    page_index = int(delta_data["page_index"])
    raw_gray, zoom = render_page_gray(pdf_path, page_index)
    rects = get_text_word_rects(pdf_path, page_index, zoom)
    text_masked = mask_text(raw_gray, rects)
    line_masked, _line_mask, _stats = mask_lines(text_masked, page_kind="drawing")
    return line_masked


def sibling_variant_paths(image_path: Path) -> dict[str, Path]:
    stem = image_path.stem
    if not stem.endswith("_denoise_2"):
        raise ValueError(f"Expected denoise_2 image path, got {image_path}")
    base = stem[: -len("_denoise_2")]
    parent = image_path.parent
    return {
        "denoise_1": parent / f"{base}_denoise_1.png",
        "denoise_x": parent / f"{base}_denoise_x.png",
    }


def run_case(case: StepBenchCase) -> None:
    delta_data, delta_record = load_delta_record(case.delta_json, case.active_delta_index)
    image_path = Path(delta_data["image_path"])
    raw_page = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if raw_page is None:
        raise RuntimeError(f"Could not read case image from delta json: {image_path}")

    roi_bbox = crop_bbox_from_center(delta_record["center"], raw_page.shape)
    triangle_pts = local_triangle_points(delta_record, roi_bbox)

    current_line = current_line_masked_image(delta_data)
    variant_paths = sibling_variant_paths(image_path)
    variants: dict[str, np.ndarray] = {
        "current_line_masked": crop_image(current_line, roi_bbox),
    }
    for name, path in variant_paths.items():
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise RuntimeError(f"Missing variant image: {path}")
        variants[name] = crop_image(img, roi_bbox)

    run_dir = OUTPUT_DIR / case.case_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "case_id": case.case_id,
        "description": case.description,
        "delta_json": str(case.delta_json),
        "active_delta_index": case.active_delta_index,
        "delta_center_page": delta_record["center"],
        "roi_bbox_page": {
            "x0": roi_bbox[0],
            "y0": roi_bbox[1],
            "x1": roi_bbox[2],
            "y1": roi_bbox[3],
        },
        "variants": {},
        "note": "denoise_x is the output of denoise_1 -> denoise_x; there is no separate raw->x stage.",
    }

    for variant_name, crop in variants.items():
        variant_dir = run_dir / variant_name
        variant_dir.mkdir(parents=True, exist_ok=True)

        save_step(variant_dir / "step_00_input.png", draw_triangle(crop, triangle_pts))
        save_step(variant_dir / "step_01_binary.png", binary_view(crop))
        save_step(variant_dir / "step_02_components_overlay.png", components_overlay(crop))
        save_step(variant_dir / "step_03_close_k3.png", close_view(crop, 3))
        save_step(variant_dir / "step_04_close_k5.png", close_view(crop, 5))
        save_step(variant_dir / "step_05_close_k7.png", close_view(crop, 7))
        save_step(variant_dir / "step_06_close_k9.png", close_view(crop, 9))
        save_step(variant_dir / "step_07_scallops_overlay.png", scallops_overlay(crop))
        save_step(variant_dir / "step_08_thickness_heatmap.png", thickness_heatmap(crop))
        save_step(variant_dir / "step_09_component_thickness_overlay.png", component_thickness_overlay(crop))
        save_step(variant_dir / "step_10_thin_component_filter.png", thin_component_filter(crop))
        save_step(variant_dir / "step_11_hard_thin_filter.png", hard_thin_filter(crop))
        save_step(variant_dir / "step_12_pair_motif_overlay.png", pair_motif_overlay(crop))
        make_contact_sheet(variant_dir)

        manifest["variants"][variant_name] = {
            "shape": [int(crop.shape[1]), int(crop.shape[0])],
            "output_dir": str(variant_dir),
            "contact_sheet": str(variant_dir / "contact_sheet.png"),
        }

    (run_dir / "step_13_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote step bench -> {run_dir}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        type=str,
        default="all",
        help="Case id to build, or 'all'.",
    )
    args = parser.parse_args()

    selected = CASES
    if args.case != "all":
        selected = tuple(case for case in CASES if case.case_id == args.case)
        if not selected:
            print(
                "Unknown case. Available: "
                + ", ".join(case.case_id for case in CASES)
                + ", all"
            )
            return 1

    for case in selected:
        run_case(case)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
