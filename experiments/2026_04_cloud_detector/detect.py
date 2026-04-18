"""Cloud detection experiment via convex-hull defect analysis.

Throwaway script. See README.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import fitz
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_DIR = Path(__file__).parent
OUTPUT_DIR = EXPERIMENT_DIR / "output"

DEFAULT_DPI = 300
SCORE_THRESHOLD = 0.40

PAGES = [
    (
        "rev1_p00_index",
        "revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf",
        0,
        "Sheet index page (many small row-bracket clouds)",
    ),
    (
        "rev1_p01_GI104",
        "revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf",
        1,
        "5TH FLOOR CODE PLAN — FEC + exit light, 2 instances",
    ),
    (
        "rev1_p04_SF110",
        "revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf",
        4,
        "4TH FLOOR FRAMING PLAN — black square in wall (mystery)",
    ),
    (
        "rev1_p06_AD104",
        "revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf",
        6,
        "DEMO 4TH+5TH FLOOR — X-hexagon, multi-drawing page",
    ),
    (
        "rev2_AE107_1_R1",
        "revision_sets/Revision #2 - Mod 5 grab bar supports/Drawing Rev2- Steel Grab Bars R1 AE107.1.pdf",
        0,
        "Rev 2 grab bar — different style sanity check",
    ),
]


@dataclass
class CloudMetrics:
    n_defects: int
    depth_mean: float
    depth_std: float
    depth_cv: float
    spacing_mean: float
    spacing_std: float
    spacing_cv: float
    perimeter: float
    solidity: float
    arc_segment_fraction: float
    score: float


def _segment_arc_ratio(contour: np.ndarray, start_idx: int, end_idx: int) -> float | None:
    """Arc-length / chord-length ratio for the contour segment from start_idx to end_idx.

    Ratio ~1.0 = straight line. Half-circle = pi/2 ~ 1.57. Real cloud scallops typically 1.08-1.4.
    Returns None if the segment is too short to be meaningful.
    """
    n = len(contour)
    if n < 4 or start_idx == end_idx:
        return None
    if end_idx < start_idx:
        idx = list(range(start_idx, n)) + list(range(0, end_idx + 1))
    else:
        idx = list(range(start_idx, end_idx + 1))
    if len(idx) < 5:
        return None
    pts = contour[idx, 0, :].astype(np.float32)
    arc_len = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
    chord = float(np.linalg.norm(pts[-1] - pts[0]))
    if chord < 6.0 or arc_len < 6.0:
        return None
    return arc_len / chord


def render_page_gray(pdf_path: Path, page_index: int, dpi: int = DEFAULT_DPI) -> np.ndarray:
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        zoom = dpi / 72
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    finally:
        doc.close()
    return img


def find_candidate_contours(gray: np.ndarray) -> list[np.ndarray]:
    """Threshold + light morphological close + find every closed contour."""
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((3, 3), np.uint8)
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, _ = cv2.findContours(closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    return list(contours)


def score_cloud(contour: np.ndarray, page_perimeter_estimate: float) -> tuple[CloudMetrics | None, str]:
    """Return (metrics, reject_reason). reject_reason is empty string when accepted."""
    perimeter = float(cv2.arcLength(contour, closed=True))
    if perimeter < 400:
        return None, "too_small"
    if perimeter > page_perimeter_estimate * 0.8:
        return None, "too_large"
    if len(contour) < 12:
        return None, "few_points"

    contour_area = float(cv2.contourArea(contour))
    hull_pts = cv2.convexHull(contour, returnPoints=True)
    hull_area = float(cv2.contourArea(hull_pts))
    solidity = contour_area / hull_area if hull_area > 0 else 0.0
    if solidity < 0.40:
        return None, "low_solidity"
    if solidity > 0.95:
        return None, "high_solidity"

    try:
        hull = cv2.convexHull(contour, returnPoints=False)
    except cv2.error:
        return None, "hull_error"
    if hull is None or len(hull) < 4:
        return None, "tiny_hull"

    try:
        defects = cv2.convexityDefects(contour, hull)
    except cv2.error:
        return None, "defect_error"
    if defects is None or len(defects) < 3:
        return None, "too_few_raw_defects"

    depths_raw = defects[:, 0, 3].astype(np.float32) / 256.0
    far_indices = defects[:, 0, 2]

    sig_mask = depths_raw > 3.0
    sig_depths = depths_raw[sig_mask]
    sig_indices = far_indices[sig_mask]
    if len(sig_depths) < 4:
        return None, "few_sig_defects"

    depth_mean = float(sig_depths.mean())
    depth_std = float(sig_depths.std())
    depth_cv = depth_std / depth_mean if depth_mean > 0 else 1.0

    sorted_indices = np.sort(sig_indices)
    n = len(contour)
    spacings = np.diff(sorted_indices).astype(np.float32)
    spacings = np.append(spacings, float(n - sorted_indices[-1] + sorted_indices[0]))
    spacing_mean = float(spacings.mean())
    spacing_std = float(spacings.std())
    spacing_cv = spacing_std / spacing_mean if spacing_mean > 0 else 1.0

    arc_segment_count = 0
    measured_segments = 0
    for i in range(len(sorted_indices)):
        a = int(sorted_indices[i])
        b = int(sorted_indices[(i + 1) % len(sorted_indices)])
        ratio = _segment_arc_ratio(contour, a, b)
        if ratio is None:
            continue
        measured_segments += 1
        if 1.04 <= ratio <= 1.7:
            arc_segment_count += 1
    if measured_segments < 3:
        return None, "few_measurable_segments"
    arc_fraction = arc_segment_count / measured_segments
    if arc_fraction < 0.50:
        return None, "low_arc_fraction"

    n_defect_score = min(1.0, len(sig_depths) / 6.0)
    score = (
        0.40 * n_defect_score
        + 0.40 * arc_fraction
        - 0.20 * min(depth_cv, 1.0)
        - 0.15 * min(spacing_cv, 1.0)
    )

    metrics = CloudMetrics(
        n_defects=int(len(sig_depths)),
        depth_mean=depth_mean,
        depth_std=depth_std,
        depth_cv=depth_cv,
        spacing_mean=spacing_mean,
        spacing_std=spacing_std,
        spacing_cv=spacing_cv,
        perimeter=perimeter,
        solidity=float(solidity),
        arc_segment_fraction=float(arc_fraction),
        score=float(score),
    )
    return metrics, ""


def is_cloud(metrics: CloudMetrics | None, threshold: float = SCORE_THRESHOLD) -> bool:
    return metrics is not None and metrics.score >= threshold


REJECT_COLORS = {
    # color-code each reject reason so we can see what's getting filtered
    "too_small": None,                     # don't draw — way too noisy
    "too_large": None,                     # ditto (page boundary)
    "few_points": None,
    "low_solidity": (0, 100, 255),         # orange  — very concave (stars/combs)
    "high_solidity": (200, 100, 0),        # blue    — too convex (filled shapes)
    "tiny_hull": None,
    "hull_error": None,
    "defect_error": None,
    "too_few_raw_defects": None,
    "few_sig_defects": (0, 200, 200),      # yellow  — concave but not bumpy enough
    "few_measurable_segments": None,
    "low_arc_fraction": (180, 0, 180),     # magenta — bumpy but with straight edges (text/stars)
}


def render_overlay(
    gray: np.ndarray,
    scored: list[tuple[np.ndarray, CloudMetrics | None, str]],
    output_path: Path,
    threshold: float = SCORE_THRESHOLD,
) -> tuple[int, dict[str, int]]:
    rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    n_clouds = 0
    reject_counts: dict[str, int] = {}
    for contour, metrics, reason in scored:
        if metrics is not None and metrics.score >= threshold:
            n_clouds += 1
            cv2.drawContours(rgb, [contour], -1, (0, 200, 0), 10)
            x, y, _, _ = cv2.boundingRect(contour)
            label = f"{metrics.score:.2f}/{metrics.n_defects}/{metrics.arc_segment_fraction:.2f}"
            cv2.putText(
                rgb, label, (x, max(28, y - 12)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 200, 0), 4,
            )
            continue
        if metrics is not None:
            cv2.drawContours(rgb, [contour], -1, (90, 90, 220), 7)
            reject_counts["below_threshold"] = reject_counts.get("below_threshold", 0) + 1
            continue
        color = REJECT_COLORS.get(reason)
        reject_counts[reason] = reject_counts.get(reason, 0) + 1
        if color is not None:
            cv2.drawContours(rgb, [contour], -1, color, 5)
    cv2.imwrite(str(output_path), rgb)
    return n_clouds, reject_counts


def run(threshold: float = SCORE_THRESHOLD, dpi: int = DEFAULT_DPI) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"DPI={dpi}  cloud-score threshold={threshold:.2f}")
    summary: list[tuple[str, int, int]] = []

    for label, rel_pdf, page_index, desc in PAGES:
        pdf_path = REPO_ROOT / rel_pdf
        print(f"\n--- {label}: {desc}")
        gray = render_page_gray(pdf_path, page_index, dpi=dpi)
        h, w = gray.shape
        page_perim_est = float(2 * (h + w))
        print(f"  rendered {w}x{h}")

        contours = find_candidate_contours(gray)
        print(f"  found {len(contours)} candidate contours")

        scored: list[tuple[np.ndarray, CloudMetrics | None, str]] = [
            (c, *score_cloud(c, page_perim_est)) for c in contours
        ]
        out = OUTPUT_DIR / f"{label}.png"
        n_clouds, reject_counts = render_overlay(gray, scored, out, threshold=threshold)
        print(f"  classified {n_clouds} as clouds")

        # show why everything else was rejected
        relevant = {k: v for k, v in reject_counts.items() if k not in ("too_small", "too_large", "few_points", "tiny_hull", "too_few_raw_defects")}
        if relevant:
            print("  reject reasons (excluding trivial):")
            for reason, count in sorted(relevant.items(), key=lambda kv: -kv[1]):
                print(f"    {reason:<25} {count:>5}")

        ranked = sorted(
            ((m.score, m) for c, m, _ in scored if m is not None and m.score >= threshold),
            key=lambda kv: -kv[0],
        )[:5]
        if ranked:
            print("  top clouds:")
            for s, m in ranked:
                print(
                    f"    score={s:.2f} n={m.n_defects:>2} "
                    f"arc%={m.arc_segment_fraction:.2f} solid={m.solidity:.2f} "
                    f"depth_cv={m.depth_cv:.2f} spacing_cv={m.spacing_cv:.2f} perim={m.perimeter:.0f}"
                )

        # also show top BORDERLINE rejects so we can see what's just missing the bar
        below = sorted(
            ((m.score, m) for c, m, _ in scored if m is not None and m.score < threshold),
            key=lambda kv: -kv[0],
        )[:5]
        if below:
            print("  top below-threshold:")
            for s, m in below:
                print(
                    f"    score={s:.2f} n={m.n_defects:>2} "
                    f"arc%={m.arc_segment_fraction:.2f} solid={m.solidity:.2f} "
                    f"depth_cv={m.depth_cv:.2f} spacing_cv={m.spacing_cv:.2f} perim={m.perimeter:.0f}"
                )
        print(f"  -> {out}")
        summary.append((label, len(contours), n_clouds))

    print("\n=== SUMMARY ===")
    for label, total, clouds in summary:
        print(f"  {label}: {clouds:>3} clouds / {total:>5} contours")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
