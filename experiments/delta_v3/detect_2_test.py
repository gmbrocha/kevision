"""detect_2_test.py — Bottom-up geometric Δ detection with canonical model.

Two independent detectors fused at the end:

  Pipeline A (line-based, fast hypothesis generator):
    Canny -> morph close -> HoughLinesP -> spatial-hashed collinear merge
    -> spatially-pruned (horiz, +60°, -60°) triplet enumeration ->
    equilateral + upward validation -> centroid NMS

  Calibration:
    Pull median side length from line-based hits (preferring those with
    target-digit attribution). All real Δs are identical size, so this is
    a hard size lock not a tolerance window.

  Canonical-snap + ink-coverage post-filter:
    Each Pipeline-A candidate is replaced with a perfect canonical upward
    equilateral at side = CANONICAL_SIDE. The centroid is refined by a
    small local search maximising ink coverage along the canonical
    outline. Candidates with low ink coverage are dropped.

  Pipeline B (canonical template scan, ground-truth check):
    Build a binary outline of the canonical Δ at locked side length, run
    cv2.matchTemplate over the whole binary page, threshold + NMS.

  Reconcile:
    Detections from A and B within a small centroid distance are fused.
    Each final detection records which detectors backed it.

  Overlay:
    Snapped canonical Δs (always perfect equilaterals), color-coded by
    detector agreement and digit attribution.

Usage:
  python experiments/delta_v3/detect_2_test.py
  python experiments/delta_v3/detect_2_test.py --canonical-side 100
  python experiments/delta_v3/detect_2_test.py --no-template
  python experiments/delta_v3/detect_2_test.py --input <denoised.png>
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DETECTOR_DIR = REPO_ROOT / "experiments" / "2026_04_delta_marker_detector"
OUT_DIR = Path(__file__).parent

sys.path.insert(0, str(DETECTOR_DIR))
import detect_deltas  # noqa: E402

sys.path.insert(0, str(OUT_DIR))
from denoise_2 import output_path as denoise_2_output_path  # noqa: E402

DEFAULT_PDF = REPO_ROOT / "revision_sets" / "Revision #1 - Drawing Changes" / "Revision #1 - Drawing Changes.pdf"
DEFAULT_PAGE = 17
DEFAULT_TARGET_DIGIT = "1"

# --------------------------------------------------------------------------
# Tunables (px at 300 DPI). Calibrated against AE122 / Revision #1 page 17.
# --------------------------------------------------------------------------

# Canny + close
CANNY_LOW = 50
CANNY_HIGH = 150
CLOSE_KERNEL = 3

# Hough — lenient on purpose (we'll merge fragments later)
HOUGH_VOTE_THRESHOLD = 25
HOUGH_MIN_LINE_LENGTH = 12
HOUGH_MAX_LINE_GAP = 8
HOUGH_RHO = 1
HOUGH_THETA = np.pi / 180

# Collinear merging tolerances
MERGE_ANGLE_TOL_DEG = 4.0
MERGE_RHO_TOL_PX = 4.0

# Permissive Δ-side window for Pipeline A's hypothesis generator. The
# size-lock filter (CANONICAL_SIDE_TOL) tightens this dramatically once
# we know the canonical side length.
SIDE_LEN_MIN = 25
SIDE_LEN_MAX = 160

# Angle buckets for upward equilateral
HORIZ_ANGLE_TOL = 12.0
SLANT_POS_CENTER = 60.0
SLANT_NEG_CENTER = 120.0
SLANT_ANGLE_TOL = 12.0

# Pipeline A geometric validation
EQUILATERAL_TOL = 0.18
INTERIOR_ANGLE_TOL_DEG = 14.0
APEX_HEIGHT_TOL = 0.25
BASE_HORIZ_TOL_DEG = 12.0

TRIPLET_MAX_VERTEX_DIST = 200

# Size lock + canonical snap
CANONICAL_SIDE_TOL = 0.12              # ±12% of canonical, hard cut after calibration
CANONICAL_SNAP_SEARCH_PX = 6           # local search radius for centroid refine
CANONICAL_SNAP_STEP_PX = 1             # grid step within search

# Ink coverage + interior emptiness (binarized)
INK_BINARIZE_THRESHOLD = 150
INK_COVERAGE_SAMPLES_PER_SIDE = 25
INK_CORRIDOR_PX = 2
INK_COVERAGE_MIN = 0.50                # outline coverage post-filter (both pipelines)
INTERIOR_EXCLUDE_FRAC = 0.18           # ignore region within this fraction of side around centroid (digit zone)
INTERIOR_CORRIDOR_PX = 1               # ink within this many px counts as "not empty"
INTERIOR_EMPTINESS_MIN = 0.65          # fraction of interior samples that must be ink-free

# Tighter NMS applied AFTER canonical snap, to merge near-duplicate snapped dets
POST_SNAP_NMS_RADIUS_FRAC = 0.35

# Template scan (Pipeline B). We compute outline-coverage at every position
# directly via filter2D (correlation against the canonical outline) instead of
# matchTemplate, because TM_CCOEFF_NORMED gives misleading scores on sparse
# binary inputs. Threshold here is intentionally permissive — the snap+filter
# step will re-evaluate each peak with the same coverage+emptiness gates as
# Pipeline A.
TEMPLATE_OUTLINE_THICKNESS = 2
TEMPLATE_DILATE_PX = 2                 # widen image ink before correlation (matches INK_CORRIDOR_PX)
TEMPLATE_COVERAGE_THRESHOLD = 0.40     # peak threshold; final filter is INK_COVERAGE_MIN
TEMPLATE_NMS_RADIUS_FRAC = 0.6         # of canonical side

# Reconciliation
RECONCILE_RADIUS_FRAC = 0.45           # match A and B detections within this * side


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------


@dataclass
class MergedLine:
    p1: tuple[float, float]
    p2: tuple[float, float]
    angle_deg: float
    rho: float
    length: float = field(init=False)

    def __post_init__(self) -> None:
        dx = self.p2[0] - self.p1[0]
        dy = self.p2[1] - self.p1[1]
        self.length = float(np.hypot(dx, dy))


@dataclass
class RawTriangle:
    """Pipeline-A raw geometric triangle (three line intersections)."""
    vertices: np.ndarray
    side_lengths: tuple[float, float, float]
    angles_deg: tuple[float, float, float]
    centroid: tuple[float, float]
    digit: str | None = None
    digit_position: tuple[float, float] | None = None


@dataclass
class Detection:
    """Final canonical detection (perfect equilateral at locked side)."""
    centroid: tuple[float, float]
    side: float
    sources: set[str]                          # {"line"}, {"template"}, both
    ink_coverage: float                        # outline ink coverage [0..1]
    interior_emptiness: float                  # fraction of interior samples ink-free [0..1]
    digit: str | None = None
    digit_position: tuple[float, float] | None = None
    template_score: float | None = None        # if matched by Pipeline B

    def vertices(self) -> np.ndarray:
        return canonical_triangle(self.centroid[0], self.centroid[1], self.side)


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------


def normalize_angle(deg: float) -> float:
    a = deg % 180.0
    if a < 0:
        a += 180.0
    return a


def angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def line_rho(p1: tuple[float, float], p2: tuple[float, float], angle_deg: float) -> float:
    theta = np.radians(angle_deg + 90.0)
    return float(p1[0] * np.cos(theta) + p1[1] * np.sin(theta))


def line_intersection(
    p1: tuple[float, float], p2: tuple[float, float],
    q1: tuple[float, float], q2: tuple[float, float],
) -> tuple[float, float] | None:
    x1, y1 = p1; x2, y2 = p2
    x3, y3 = q1; x4, y4 = q2
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None
    t_num = (x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)
    t = t_num / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def triangle_is_upward(verts: np.ndarray, side_len: float) -> bool:
    sorted_v = verts[np.argsort(verts[:, 1])]
    apex = sorted_v[0]
    base = sorted_v[1:]
    bx0, by0 = base[0]
    bx1, by1 = base[1]
    base_angle = abs(np.degrees(np.arctan2(by1 - by0, bx1 - bx0)))
    base_angle = min(base_angle, 180.0 - base_angle)
    if base_angle > BASE_HORIZ_TOL_DEG:
        return False
    base_avg_y = (by0 + by1) / 2.0
    apex_height = base_avg_y - apex[1]
    expected = side_len * np.sqrt(3.0) / 2.0
    if apex_height <= 0:
        return False
    if abs(apex_height - expected) > APEX_HEIGHT_TOL * expected:
        return False
    return True


def canonical_triangle(cx: float, cy: float, side: float) -> np.ndarray:
    """Perfect upward equilateral centered at (cx, cy). Centroid is 1/3 of
    the height up from the base, so:
      apex   = (cx, cy - side * sqrt(3)/3)
      bot-L  = (cx - side/2, cy + side * sqrt(3)/6)
      bot-R  = (cx + side/2, cy + side * sqrt(3)/6)
    Returned in apex, bot-L, bot-R order.
    """
    s3 = float(np.sqrt(3.0))
    apex = (cx, cy - side * s3 / 3.0)
    bl = (cx - side / 2.0, cy + side * s3 / 6.0)
    br = (cx + side / 2.0, cy + side * s3 / 6.0)
    return np.array([apex, bl, br], dtype=np.float64)


def _side_lengths(verts: np.ndarray) -> tuple[float, float, float]:
    a = float(np.linalg.norm(verts[1] - verts[0]))
    b = float(np.linalg.norm(verts[2] - verts[1]))
    c = float(np.linalg.norm(verts[0] - verts[2]))
    return (a, b, c)


def _interior_angles_deg(verts: np.ndarray) -> tuple[float, float, float]:
    angles: list[float] = []
    for i in range(3):
        prev_pt = verts[(i - 1) % 3]
        curr = verts[i]
        nxt = verts[(i + 1) % 3]
        v1 = prev_pt - curr
        v2 = nxt - curr
        denom = (np.linalg.norm(v1) * np.linalg.norm(v2)) or 1e-9
        cos_a = float(np.clip(np.dot(v1, v2) / denom, -1.0, 1.0))
        angles.append(float(np.degrees(np.arccos(cos_a))))
    return (angles[0], angles[1], angles[2])


def _is_equilateral(side_lens: tuple[float, float, float], angles: tuple[float, float, float]) -> bool:
    longest = max(side_lens)
    shortest = min(side_lens)
    if shortest <= 0:
        return False
    if (longest - shortest) / longest > EQUILATERAL_TOL:
        return False
    for ang in angles:
        if abs(ang - 60.0) > INTERIOR_ANGLE_TOL_DEG:
            return False
    return True


# --------------------------------------------------------------------------
# Pipeline A: line-based hypothesis generator
# --------------------------------------------------------------------------


def stage_edges_and_close(gray: np.ndarray) -> np.ndarray:
    edges = cv2.Canny(gray, CANNY_LOW, CANNY_HIGH)
    if CLOSE_KERNEL > 0:
        k = np.ones((CLOSE_KERNEL, CLOSE_KERNEL), np.uint8)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k)
    return edges


def stage_hough(edges: np.ndarray) -> np.ndarray:
    lines = cv2.HoughLinesP(
        edges, rho=HOUGH_RHO, theta=HOUGH_THETA,
        threshold=HOUGH_VOTE_THRESHOLD,
        minLineLength=HOUGH_MIN_LINE_LENGTH,
        maxLineGap=HOUGH_MAX_LINE_GAP,
    )
    if lines is None:
        return np.empty((0, 4), dtype=np.float32)
    return lines.reshape(-1, 4).astype(np.float32)


def stage_merge_collinear(segments: np.ndarray) -> list[MergedLine]:
    """Spatial-hash + union-find collinear merge. O(n) expected."""
    n = len(segments)
    if n == 0:
        return []

    x1 = segments[:, 0]; y1 = segments[:, 1]
    x2 = segments[:, 2]; y2 = segments[:, 3]
    raw = np.degrees(np.arctan2(y2 - y1, x2 - x1)).astype(np.float32)
    angles = np.mod(raw, 180.0)
    theta_perp = np.radians(angles + 90.0)
    rhos = (x1 * np.cos(theta_perp) + y1 * np.sin(theta_perp)).astype(np.float32)

    a_step = MERGE_ANGLE_TOL_DEG
    r_step = MERGE_RHO_TOL_PX
    n_ab = int(np.ceil(180.0 / a_step))
    ab = (angles // a_step).astype(np.int32) % n_ab
    rb = (rhos // r_step).astype(np.int32)

    grid: dict[tuple[int, int], list[int]] = {}
    for i in range(n):
        grid.setdefault((int(ab[i]), int(rb[i])), []).append(i)

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb_ = find(a), find(b)
        if ra != rb_:
            parent[rb_] = ra

    for i in range(n):
        ab_i = int(ab[i]); rb_i = int(rb[i])
        ang_i = float(angles[i]); rho_i = float(rhos[i])
        for dab in (-1, 0, 1):
            ab_j = (ab_i + dab) % n_ab
            for drb in (-1, 0, 1):
                key = (ab_j, rb_i + drb)
                bucket = grid.get(key)
                if bucket is None:
                    continue
                for j in bucket:
                    if j <= i:
                        continue
                    if abs(rho_i - float(rhos[j])) > MERGE_RHO_TOL_PX:
                        continue
                    if angle_diff(ang_i, float(angles[j])) > MERGE_ANGLE_TOL_DEG:
                        continue
                    union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    merged: list[MergedLine] = []
    for idxs_list in groups.values():
        idxs = np.array(idxs_list, dtype=np.int64)
        ang_rad = np.radians(angles[idxs] * 2.0)
        avg_ang = normalize_angle(
            float(np.degrees(np.arctan2(np.sin(ang_rad).mean(),
                                        np.cos(ang_rad).mean()))) / 2.0
        )
        ux = float(np.cos(np.radians(avg_ang)))
        uy = float(np.sin(np.radians(avg_ang)))
        xs = np.concatenate([segments[idxs, 0], segments[idxs, 2]])
        ys = np.concatenate([segments[idxs, 1], segments[idxs, 3]])
        ts = xs * ux + ys * uy
        cx, cy = float(xs.mean()), float(ys.mean())
        c_proj = cx * ux + cy * uy
        t_lo = float(ts.min()) - c_proj
        t_hi = float(ts.max()) - c_proj
        p1 = (cx + t_lo * ux, cy + t_lo * uy)
        p2 = (cx + t_hi * ux, cy + t_hi * uy)
        merged.append(MergedLine(
            p1=p1, p2=p2, angle_deg=avg_ang, rho=line_rho(p1, p2, avg_ang),
        ))
    return merged


def _midpoint(L: MergedLine) -> tuple[float, float]:
    return ((L.p1[0] + L.p2[0]) * 0.5, (L.p1[1] + L.p2[1]) * 0.5)


def stage_triplet_to_triangles(lines: list[MergedLine]) -> list[RawTriangle]:
    """Spatially-pruned (horiz, +60°, -60°) triplet enumeration."""
    horiz: list[MergedLine] = []
    pos: list[MergedLine] = []
    neg: list[MergedLine] = []
    for L in lines:
        if L.length > SIDE_LEN_MAX * 4:
            continue
        a = L.angle_deg
        if a <= HORIZ_ANGLE_TOL or a >= 180.0 - HORIZ_ANGLE_TOL:
            horiz.append(L)
        elif abs(a - SLANT_POS_CENTER) <= SLANT_ANGLE_TOL:
            pos.append(L)
        elif abs(a - SLANT_NEG_CENTER) <= SLANT_ANGLE_TOL:
            neg.append(L)

    cell = float(SIDE_LEN_MAX)
    pos_grid: dict[tuple[int, int], list[MergedLine]] = {}
    neg_grid: dict[tuple[int, int], list[MergedLine]] = {}
    for L in pos:
        mx, my = _midpoint(L)
        pos_grid.setdefault((int(mx // cell), int(my // cell)), []).append(L)
    for L in neg:
        mx, my = _midpoint(L)
        neg_grid.setdefault((int(mx // cell), int(my // cell)), []).append(L)

    triangles: list[RawTriangle] = []
    for H in horiz:
        hx, hy = _midpoint(H)
        bx, by = int(hx // cell), int(hy // cell)
        cand_pos: list[MergedLine] = []
        cand_neg: list[MergedLine] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                key = (bx + dx, by + dy)
                if key in pos_grid:
                    cand_pos.extend(pos_grid[key])
                if key in neg_grid:
                    cand_neg.extend(neg_grid[key])
        if not cand_pos or not cand_neg:
            continue
        for P, N in product(cand_pos, cand_neg):
            v_hp = line_intersection(H.p1, H.p2, P.p1, P.p2)
            v_hn = line_intersection(H.p1, H.p2, N.p1, N.p2)
            v_pn = line_intersection(P.p1, P.p2, N.p1, N.p2)
            if v_hp is None or v_hn is None or v_pn is None:
                continue
            verts = np.array([v_hp, v_hn, v_pn], dtype=np.float64)
            sides = _side_lengths(verts)
            if min(sides) < SIDE_LEN_MIN or max(sides) > SIDE_LEN_MAX:
                continue
            if max(sides) > TRIPLET_MAX_VERTEX_DIST:
                continue
            angles = _interior_angles_deg(verts)
            if not _is_equilateral(sides, angles):
                continue
            side_avg = float(np.mean(sides))
            if not triangle_is_upward(verts, side_avg):
                continue
            cx = float(verts[:, 0].mean())
            cy = float(verts[:, 1].mean())
            triangles.append(RawTriangle(
                vertices=verts, side_lengths=sides,
                angles_deg=angles, centroid=(cx, cy),
            ))
    return triangles


def stage_dedupe_raw(triangles: list[RawTriangle], radius: float) -> list[RawTriangle]:
    keep: list[RawTriangle] = []
    for t in sorted(triangles, key=lambda x: -float(np.mean(x.side_lengths))):
        too_close = False
        for k in keep:
            d = np.hypot(t.centroid[0] - k.centroid[0], t.centroid[1] - k.centroid[1])
            if d < radius:
                too_close = True
                break
        if not too_close:
            keep.append(t)
    return keep


def stage_assign_digits_raw(triangles: list[RawTriangle], digit_words: list[dict]) -> None:
    used: set[int] = set()
    for t in triangles:
        poly = t.vertices.astype(np.float32)
        for i, w in enumerate(digit_words):
            if i in used:
                continue
            if cv2.pointPolygonTest(poly, w["centroid"], False) >= 0:
                t.digit = w["text"]
                t.digit_position = w["centroid"]
                used.add(i)
                break


# --------------------------------------------------------------------------
# Calibration: lock canonical side length
# --------------------------------------------------------------------------


def calibrate_canonical_side(triangles: list[RawTriangle], target_digit: str | None) -> float | None:
    """Median side length of the highest-confidence Pipeline-A hits.

    Preference order:
      1. Triangles where the attributed digit == target_digit (likeliest
         to be true Δs of the current revision).
      2. All triangles with any digit attribution.
      3. None — caller must specify --canonical-side.
    """
    if target_digit is not None:
        with_target = [t for t in triangles if t.digit == target_digit]
        if len(with_target) >= 3:
            sides = [float(np.mean(t.side_lengths)) for t in with_target]
            return float(np.median(sides))
    with_digit = [t for t in triangles if t.digit is not None]
    if len(with_digit) >= 3:
        sides = [float(np.mean(t.side_lengths)) for t in with_digit]
        return float(np.median(sides))
    return None


# --------------------------------------------------------------------------
# Canonical-snap + ink coverage
# --------------------------------------------------------------------------


def _make_outline_sample_offsets(side: float) -> np.ndarray:
    """Sample points along a canonical Δ outline as offsets from the centroid.

    Returns shape (N, 2) of (dx, dy) offsets, sampling `INK_COVERAGE_SAMPLES_PER_SIDE`
    points along each of the 3 sides.
    """
    verts = canonical_triangle(0.0, 0.0, side)
    pts: list[tuple[float, float]] = []
    for i in range(3):
        p1 = verts[i]
        p2 = verts[(i + 1) % 3]
        for t in np.linspace(0.0, 1.0, INK_COVERAGE_SAMPLES_PER_SIDE, endpoint=False):
            pts.append((p1[0] + t * (p2[0] - p1[0]),
                        p1[1] + t * (p2[1] - p1[1])))
    return np.asarray(pts, dtype=np.float32)


def ink_coverage(binary: np.ndarray, cx: float, cy: float,
                 sample_offsets: np.ndarray, corridor: int = INK_CORRIDOR_PX) -> float:
    """Fraction of outline samples that have an ink pixel within `corridor` px.

    `binary` is INV-binarized: ink == 255, background == 0.
    """
    h, w = binary.shape
    xs = (sample_offsets[:, 0] + cx).round().astype(np.int32)
    ys = (sample_offsets[:, 1] + cy).round().astype(np.int32)

    valid = (xs >= corridor) & (xs < w - corridor) & (ys >= corridor) & (ys < h - corridor)
    if not valid.any():
        return 0.0
    xs = xs[valid]
    ys = ys[valid]

    hits = 0
    c = corridor
    for x, y in zip(xs, ys):
        if (binary[y - c:y + c + 1, x - c:x + c + 1] > 0).any():
            hits += 1
    return hits / float(len(xs))


def canonical_snap(binary: np.ndarray, init_centroid: tuple[float, float],
                   side: float, sample_offsets: np.ndarray,
                   search_radius: int = CANONICAL_SNAP_SEARCH_PX,
                   step: int = CANONICAL_SNAP_STEP_PX) -> tuple[float, float, float]:
    """Refine (cx, cy) within ±search_radius to maximise ink coverage of the
    canonical outline. Returns (best_cx, best_cy, best_coverage).
    """
    cx0, cy0 = init_centroid
    best_cov = -1.0
    best = (cx0, cy0)
    for dy in range(-search_radius, search_radius + 1, step):
        for dx in range(-search_radius, search_radius + 1, step):
            cx = cx0 + dx
            cy = cy0 + dy
            cov = ink_coverage(binary, cx, cy, sample_offsets)
            if cov > best_cov:
                best_cov = cov
                best = (cx, cy)
    return (best[0], best[1], best_cov)


def _make_interior_sample_offsets(side: float,
                                  exclude_radius_frac: float = INTERIOR_EXCLUDE_FRAC,
                                  density: int = 8) -> np.ndarray:
    """Sample points strictly inside the canonical Δ, excluding the central
    digit zone. Uses a barycentric grid for deterministic, even coverage.
    """
    verts = canonical_triangle(0.0, 0.0, side)
    exclude_r2 = (side * exclude_radius_frac) ** 2
    pts: list[tuple[float, float]] = []
    for i in range(1, density):
        for j in range(1, density - i):
            k = density - i - j
            if k < 1:
                continue
            a = i / density
            b = j / density
            c = k / density
            x = a * verts[0, 0] + b * verts[1, 0] + c * verts[2, 0]
            y = a * verts[0, 1] + b * verts[1, 1] + c * verts[2, 1]
            if x * x + y * y < exclude_r2:
                continue
            pts.append((x, y))
    return np.asarray(pts, dtype=np.float32)


def interior_emptiness(binary: np.ndarray, cx: float, cy: float,
                       sample_offsets: np.ndarray,
                       corridor: int = INTERIOR_CORRIDOR_PX) -> float:
    """Fraction of interior sample points with NO ink within `corridor` px.
    A real Δ is hollow except for the digit, so this should be high for true
    Δs (≥~0.7) and low for ink-rich blob false positives.
    """
    h, w = binary.shape
    xs = (sample_offsets[:, 0] + cx).round().astype(np.int32)
    ys = (sample_offsets[:, 1] + cy).round().astype(np.int32)
    valid = (xs >= corridor) & (xs < w - corridor) & (ys >= corridor) & (ys < h - corridor)
    if not valid.any():
        return 0.0
    xs = xs[valid]
    ys = ys[valid]
    empty = 0
    c = corridor
    for x, y in zip(xs, ys):
        if not (binary[y - c:y + c + 1, x - c:x + c + 1] > 0).any():
            empty += 1
    return empty / float(len(xs))


def evaluate_detection(binary: np.ndarray, init_centroid: tuple[float, float],
                       side: float, outline_offsets: np.ndarray,
                       interior_offsets: np.ndarray,
                       source: str, do_snap: bool = True) -> Detection:
    """Snap an init centroid to canonical model, score outline + interior,
    return a Detection. Used uniformly by both Pipeline A and Pipeline B.
    """
    if do_snap:
        cx, cy, cov = canonical_snap(binary, init_centroid, side, outline_offsets)
    else:
        cx, cy = init_centroid
        cov = ink_coverage(binary, cx, cy, outline_offsets)
    emp = interior_emptiness(binary, cx, cy, interior_offsets)
    return Detection(
        centroid=(cx, cy), side=side, sources={source},
        ink_coverage=cov, interior_emptiness=emp,
    )


def passes_quality(d: Detection) -> bool:
    return d.ink_coverage >= INK_COVERAGE_MIN and d.interior_emptiness >= INTERIOR_EMPTINESS_MIN


def _detection_score(d: Detection) -> float:
    """Higher = better. Used for NMS preference."""
    return d.ink_coverage + d.interior_emptiness + 0.5 * (d.template_score or 0.0)


def nms_detections(dets: list[Detection], radius: float,
                   merge_sources: bool = False) -> list[Detection]:
    """Greedy NMS over Detections. Higher-score wins; if `merge_sources`,
    suppressed detections donate their `sources` and template_score to the
    surviving neighbour (useful in the cross-pipeline reconcile step).
    """
    r2 = radius * radius
    keep: list[Detection] = []
    for d in sorted(dets, key=lambda x: -_detection_score(x)):
        absorbed = False
        for k in keep:
            if (d.centroid[0] - k.centroid[0]) ** 2 + (d.centroid[1] - k.centroid[1]) ** 2 < r2:
                if merge_sources:
                    k.sources |= d.sources
                    if k.template_score is None:
                        k.template_score = d.template_score
                absorbed = True
                break
        if not absorbed:
            keep.append(d)
    return keep


# --------------------------------------------------------------------------
# Pipeline B: canonical template scan
# --------------------------------------------------------------------------


def build_canonical_template(side: int, thickness: int = TEMPLATE_OUTLINE_THICKNESS) -> np.ndarray:
    """Binary outline of an upward equilateral with given side, drawn white
    on black. Same color convention as the inverted-binary input image
    (ink = white = 255).
    """
    h = int(np.ceil(side * np.sqrt(3.0) / 2.0))
    pad = thickness + 1
    W = side + 2 * pad
    H = h + 2 * pad
    img = np.zeros((H, W), dtype=np.uint8)
    apex = (W // 2, pad)
    bl = (pad, pad + h)
    br = (pad + side, pad + h)
    cv2.line(img, apex, bl, 255, thickness, cv2.LINE_AA)
    cv2.line(img, apex, br, 255, thickness, cv2.LINE_AA)
    cv2.line(img, bl, br, 255, thickness, cv2.LINE_AA)
    return img


def _peak_nms(response: np.ndarray, threshold: float, radius: int) -> list[tuple[int, int, float]]:
    """Greedy non-maximum suppression over a 2D response map."""
    ys, xs = np.where(response >= threshold)
    if len(xs) == 0:
        return []
    scores = response[ys, xs]
    order = np.argsort(-scores)
    kept_y: list[int] = []
    kept_x: list[int] = []
    kept_s: list[float] = []
    r2 = radius * radius
    for i in order:
        y = int(ys[i]); x = int(xs[i]); s = float(scores[i])
        ok = True
        for ky, kx in zip(kept_y, kept_x):
            if (ky - y) ** 2 + (kx - x) ** 2 < r2:
                ok = False
                break
        if ok:
            kept_y.append(y); kept_x.append(x); kept_s.append(s)
    return list(zip(kept_x, kept_y, kept_s))


def stage_template_scan(binary: np.ndarray, side: float) -> list[tuple[float, float, float]]:
    """Direct outline-coverage scan via convolution.

    For every pixel position, computes the fraction of canonical-outline
    samples that hit ink (within an INK_CORRIDOR_PX corridor). Returns
    (centroid_x, centroid_y, coverage) peaks above TEMPLATE_COVERAGE_THRESHOLD.
    """
    side_int = int(round(side))
    template = build_canonical_template(side_int)
    th, tw = template.shape

    # Kernel = canonical outline as 0/1 floats
    kernel = (template > 0).astype(np.float32)
    kernel_sum = float(kernel.sum())
    if kernel_sum <= 0:
        return []

    # Dilate the binary image so a near-miss within INK_CORRIDOR_PX still
    # counts (matches the per-position ink_coverage corridor behaviour).
    if TEMPLATE_DILATE_PX > 0:
        d = TEMPLATE_DILATE_PX
        dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * d + 1, 2 * d + 1))
        binary_d = cv2.dilate(binary, dilate_kernel)
    else:
        binary_d = binary
    binary_f = (binary_d > 0).astype(np.float32)

    # Anchor the kernel at the canonical centroid so response[y, x] is the
    # outline coverage when the canonical centroid sits at (x, y).
    pad = TEMPLATE_OUTLINE_THICKNESS + 1
    h_tri = int(np.ceil(side * np.sqrt(3.0) / 2.0))
    anchor_x = tw // 2
    anchor_y = pad + int(round(h_tri * 2.0 / 3.0))

    response = cv2.filter2D(
        binary_f, -1, kernel,
        anchor=(anchor_x, anchor_y),
        borderType=cv2.BORDER_CONSTANT,
    )
    coverage_map = response / kernel_sum

    peaks = _peak_nms(
        coverage_map,
        threshold=TEMPLATE_COVERAGE_THRESHOLD,
        radius=int(round(side * TEMPLATE_NMS_RADIUS_FRAC)),
    )
    # _peak_nms returns (x, y, score); since we anchored at centroid, x/y
    # are already centroid coords.
    return [(float(px), float(py), float(score)) for (px, py, score) in peaks]


# --------------------------------------------------------------------------
# Visualization
# --------------------------------------------------------------------------


def _detection_color(d: Detection, target_digit: str | None) -> tuple[tuple[int, int, int], str]:
    """Return (BGR color, label) for a detection."""
    both = "line" in d.sources and "template" in d.sources
    digit_label = d.digit if d.digit is not None else "?"

    if both:
        if target_digit is not None and d.digit == target_digit:
            return ((0, 200, 0), digit_label)        # green
        if d.digit is not None:
            return ((200, 200, 0), digit_label)      # cyan: both, other digit
        return ((180, 0, 200), digit_label)          # magenta: both, no digit
    if "line" in d.sources:
        return ((0, 165, 255), digit_label)          # orange: line-only
    return ((255, 100, 0), digit_label)              # blue: template-only


def overlay(gray: np.ndarray, detections: list[Detection],
            target_digit: str | None) -> np.ndarray:
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for d in detections:
        color, label = _detection_color(d, target_digit)
        verts = d.vertices().astype(np.int32)
        cv2.polylines(bgr, [verts], isClosed=True, color=color, thickness=4)
        cx, cy = int(d.centroid[0]), int(d.centroid[1])
        cv2.putText(bgr, label, (cx - 12, cy + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, color, 4)
    return bgr


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None,
                        help="Pre-denoised greyscale PNG. Defaults to denoise_2 output.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--page", type=int, default=DEFAULT_PAGE)
    parser.add_argument("--target-digit", type=str, default=DEFAULT_TARGET_DIGIT)
    parser.add_argument("--canonical-side", type=float, default=None,
                        help="Lock canonical Δ side length (px). Auto-calibrated if omitted.")
    parser.add_argument("--no-snap", action="store_true",
                        help="Skip canonical-snap / ink-coverage post-filter.")
    parser.add_argument("--no-template", action="store_true",
                        help="Skip Pipeline B (canonical template scan).")
    parser.add_argument("--out", type=str, default="detection_test_3",
                        help="Output filename stem (written to experiments/delta_v3/<out>.png).")
    args = parser.parse_args()

    pdf_path = args.pdf if args.pdf.is_absolute() else (Path.cwd() / args.pdf).resolve()
    in_path = args.input or denoise_2_output_path(pdf_path, args.page)
    if not in_path.exists():
        print(f"ERROR: input not found: {in_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Input: {in_path.name}")
    gray = cv2.imread(str(in_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        print(f"ERROR: could not read {in_path}", file=sys.stderr)
        sys.exit(1)
    print(f"  {gray.shape[1]}x{gray.shape[0]}")

    binary = cv2.threshold(gray, INK_BINARIZE_THRESHOLD, 255, cv2.THRESH_BINARY_INV)[1]

    # ----- Pipeline A: line-based -----
    t0 = time.time()
    edges = stage_edges_and_close(gray)
    print(f"  [A.1+2] Canny + close: {time.time() - t0:.2f}s")

    t0 = time.time()
    segments = stage_hough(edges)
    print(f"  [A.3]   Hough: {len(segments)} raw segments in {time.time() - t0:.2f}s")

    t0 = time.time()
    merged = stage_merge_collinear(segments)
    print(f"  [A.4]   merged into {len(merged)} lines in {time.time() - t0:.2f}s")

    t0 = time.time()
    raw_triangles = stage_triplet_to_triangles(merged)
    print(f"  [A.5-8] {len(raw_triangles)} valid upward equilateral triangles "
          f"in {time.time() - t0:.2f}s")

    # ----- Calibration -----
    digit_words = detect_deltas.extract_digit_words_in_pixels(pdf_path, args.page)
    stage_assign_digits_raw(raw_triangles, digit_words)

    canonical_side = args.canonical_side or calibrate_canonical_side(raw_triangles, args.target_digit)
    if canonical_side is None:
        print("ERROR: could not auto-calibrate canonical side length "
              "(too few digit-attributed line-based hits). Pass --canonical-side N.",
              file=sys.stderr)
        sys.exit(2)
    print(f"  [CAL]   canonical side = {canonical_side:.1f} px"
          + (f"  (auto from {sum(1 for t in raw_triangles if t.digit == args.target_digit)} "
             f"target-digit hits)" if args.canonical_side is None else "  (manual)"))

    # ----- Size-lock filter on Pipeline A -----
    side_lo = canonical_side * (1.0 - CANONICAL_SIDE_TOL)
    side_hi = canonical_side * (1.0 + CANONICAL_SIDE_TOL)
    locked = [t for t in raw_triangles
              if side_lo <= float(np.mean(t.side_lengths)) <= side_hi]
    print(f"  [LOCK]  {len(locked)} of {len(raw_triangles)} triangles within "
          f"±{CANONICAL_SIDE_TOL:.0%} of canonical")

    # NMS at canonical scale
    locked = stage_dedupe_raw(locked, radius=canonical_side * 0.4)
    print(f"  [NMS]   {len(locked)} after centroid NMS")

    # ----- Canonical-snap + outline coverage + interior emptiness (Pipeline A) -----
    outline_offsets = _make_outline_sample_offsets(canonical_side)
    interior_offsets = _make_interior_sample_offsets(canonical_side)
    do_snap = not args.no_snap

    t0 = time.time()
    line_evaluated: list[Detection] = []
    for t in locked:
        d = evaluate_detection(
            binary, t.centroid, canonical_side, outline_offsets,
            interior_offsets, source="line", do_snap=do_snap,
        )
        d.digit = t.digit
        d.digit_position = t.digit_position
        line_evaluated.append(d)
    line_passed = [d for d in line_evaluated if passes_quality(d)]
    print(f"  [A.S]   snap+filter: {len(line_passed)} of {len(line_evaluated)} "
          f"pass coverage>={INK_COVERAGE_MIN:.0%} AND emptiness>={INTERIOR_EMPTINESS_MIN:.0%} "
          f"in {time.time() - t0:.2f}s")

    # Re-NMS AFTER snap to merge near-duplicates that drifted apart during snap
    line_dets = nms_detections(line_passed, radius=canonical_side * POST_SNAP_NMS_RADIUS_FRAC)
    print(f"  [A.NMS] {len(line_dets)} after post-snap NMS "
          f"(radius {canonical_side * POST_SNAP_NMS_RADIUS_FRAC:.0f} px)")

    # ----- Pipeline B: template scan + same snap+filter -----
    template_dets: list[Detection] = []
    if not args.no_template:
        t0 = time.time()
        peaks = stage_template_scan(binary, canonical_side)
        template_evaluated: list[Detection] = []
        for px, py, score in peaks:
            d = evaluate_detection(
                binary, (px, py), canonical_side, outline_offsets,
                interior_offsets, source="template", do_snap=do_snap,
            )
            d.template_score = score
            template_evaluated.append(d)
        template_passed = [d for d in template_evaluated if passes_quality(d)]
        template_dets = nms_detections(
            template_passed, radius=canonical_side * POST_SNAP_NMS_RADIUS_FRAC,
        )
        print(f"  [B]     template scan: {len(peaks)} peaks -> "
              f"{len(template_passed)} pass filters -> {len(template_dets)} after NMS "
              f"in {time.time() - t0:.2f}s")

    # ----- Cross-pipeline reconcile + final NMS -----
    fused = nms_detections(
        line_dets + template_dets,
        radius=canonical_side * RECONCILE_RADIUS_FRAC,
        merge_sources=True,
    )
    final = fused

    # ----- Digit attribution for any det that doesn't already have one -----
    used_digits = {tuple(d.digit_position) for d in final
                   if d.digit_position is not None}
    for d in final:
        if d.digit is not None:
            continue
        poly = d.vertices().astype(np.float32)
        for w in digit_words:
            wc = w["centroid"]
            if wc in used_digits:
                continue
            if cv2.pointPolygonTest(poly, wc, False) >= 0:
                d.digit = w["text"]
                d.digit_position = wc
                used_digits.add(tuple(wc))
                break

    # ----- Report -----
    n_both = sum(1 for d in final if "line" in d.sources and "template" in d.sources)
    n_line_only = sum(1 for d in final if d.sources == {"line"})
    n_template_only = sum(1 for d in final if d.sources == {"template"})
    n_target = sum(1 for d in final if d.digit == args.target_digit)
    print(f"\n  FINAL: {len(final)} detections "
          f"(both={n_both}, line-only={n_line_only}, template-only={n_template_only}, "
          f"with digit '{args.target_digit}'={n_target})")

    out_img = overlay(gray, final, args.target_digit)
    out_path = OUT_DIR / f"{args.out}.png"
    cv2.imwrite(str(out_path), out_img)
    print(f"\nOverlay -> {out_path.name}")
    print("  Color legend:")
    print("    green   = both detectors, target digit")
    print("    cyan    = both detectors, other digit")
    print("    magenta = both detectors, no digit (destroyed)")
    print("    orange  = line-based only")
    print("    blue    = template-only (line missed)")


if __name__ == "__main__":
    main()
