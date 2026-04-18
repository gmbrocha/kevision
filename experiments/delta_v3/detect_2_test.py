"""detect_2_test.py — Bottom-up geometric Δ detection.

Replaces the contour-based Tier 1 + outline-density Tier 2 detector with
a pipeline that constructs triangles from independent line segments.
This is robust to outline fragmentation and doesn't require the digit to
be present.

Pipeline:
  1. Canny edge detection on the denoised image.
  2. Morphological closing (small kernel) to bridge sub-pixel gaps in
     broken edges before line detection.
  3. cv2.HoughLinesP with lenient parameters (low vote threshold, small
     minLineLength, generous maxLineGap) to catch fragmented Δ sides.
  4. Collinear merging: cluster Hough segments by (angle, rho) and merge
     each cluster into a single line spanning its extreme endpoints.
  5. Triplet enumeration: for an UPWARD equilateral the three sides have
     normalized angles ~0° (base), ~60°, and ~120°. Bucket lines by
     angle and try every (horizontal, +60°, -60°) triplet.
  6. Line intersection -> 3 candidate vertices.
  7. Equilateral validation: all three sides equal within ~15%.
  8. Orientation filter: UPWARD-pointing only (apex Y < base Y, base near
     horizontal). NO downward triangles allowed.
  9. Deduplication: NMS by centroid distance.
 10. Digit lookup via PyMuPDF text layer (digit is OPTIONAL — destroyed
     digits still leave a valid triangle).
 11. Color overlay:
       green - Δ with target digit (default "1") inside
       cyan  - Δ with other digit inside (older revision)
       red   - Δ with no digit inside (geometric only; digit destroyed
               or never present)

Usage:
  python experiments/delta_v3/detect_2_test.py --out detection_test_2
  python experiments/delta_v3/detect_2_test.py --input path/to/denoised.png

Defaults: AE122 (Revision #1, page 17), input = denoise_2 output.
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
# Tunables (px at 300 DPI). Tuned for AE122 first; will likely generalize.
# --------------------------------------------------------------------------

# Canny + close
CANNY_LOW = 50
CANNY_HIGH = 150
CLOSE_KERNEL = 3                 # 3x3 morphological close to bridge sub-pixel gaps

# Hough — lenient on purpose (we'll merge fragments later)
HOUGH_VOTE_THRESHOLD = 25
HOUGH_MIN_LINE_LENGTH = 12
HOUGH_MAX_LINE_GAP = 8
HOUGH_RHO = 1
HOUGH_THETA = np.pi / 180

# Collinear merging tolerances
MERGE_ANGLE_TOL_DEG = 4.0        # two segments are "same line" if angles within this
MERGE_RHO_TOL_PX = 4.0           # AND perpendicular distance from origin within this

# Δ-side length window (filter merged lines before triplet enumeration)
SIDE_LEN_MIN = 25                # Δ sides observed ~30-130 px
SIDE_LEN_MAX = 160

# Angle buckets for upward equilateral
HORIZ_ANGLE_TOL = 12.0           # base: angle in [0°-tol, 0°+tol] OR [180°-tol, 180°]
SLANT_POS_CENTER = 60.0          # one slant
SLANT_NEG_CENTER = 120.0         # other slant
SLANT_ANGLE_TOL = 12.0

# Triangle validation
EQUILATERAL_TOL = 0.18           # (max-min)/max <= this
INTERIOR_ANGLE_TOL_DEG = 14.0    # each angle within this of 60°
APEX_HEIGHT_TOL = 0.25           # apex height vs expected = side*sqrt(3)/2; relative tol
BASE_HORIZ_TOL_DEG = 12.0        # base segment angle from horizontal

# Deduplication
DEDUPE_RADIUS_PX = 25

# Spatial pruning for triplet enumeration: a triangle's 3 lines must all
# pass within this distance of each other (or rather: every pair of the
# three lines must intersect within plausible Δ-side bounds).
TRIPLET_MAX_VERTEX_DIST = 200    # if any vertex pair is farther than this, skip


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------


@dataclass
class MergedLine:
    p1: tuple[float, float]      # endpoint 1 (x, y)
    p2: tuple[float, float]      # endpoint 2 (x, y)
    angle_deg: float             # normalized to [0, 180)
    rho: float                   # perpendicular distance from origin
    length: float = field(init=False)

    def __post_init__(self) -> None:
        dx = self.p2[0] - self.p1[0]
        dy = self.p2[1] - self.p1[1]
        self.length = float(np.hypot(dx, dy))


@dataclass
class Triangle:
    vertices: np.ndarray         # (3, 2) float
    side_lengths: tuple[float, float, float]
    angles_deg: tuple[float, float, float]
    centroid: tuple[float, float]
    digit: str | None = None
    digit_position: tuple[float, float] | None = None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def normalize_angle(deg: float) -> float:
    """Wrap to [0, 180) — line direction is sign-agnostic."""
    a = deg % 180.0
    if a < 0:
        a += 180.0
    return a


def angle_diff(a: float, b: float) -> float:
    """Smallest difference between two normalized angles in [0, 180)."""
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def line_rho(p1: tuple[float, float], p2: tuple[float, float], angle_deg: float) -> float:
    """Perpendicular distance from origin to the infinite line through p1, p2.

    rho = x * cos(theta) + y * sin(theta), where theta is the angle of the
    perpendicular to the line. For a line at angle `angle_deg`, the
    perpendicular angle is `angle_deg + 90`.
    """
    theta = np.radians(angle_deg + 90.0)
    return float(p1[0] * np.cos(theta) + p1[1] * np.sin(theta))


def line_intersection(
    p1: tuple[float, float], p2: tuple[float, float],
    q1: tuple[float, float], q2: tuple[float, float],
) -> tuple[float, float] | None:
    """Intersection of two infinite lines defined by (p1,p2) and (q1,q2).

    Returns None if parallel.
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = q1
    x4, y4 = q2
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None
    t_num = (x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)
    t = t_num / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def triangle_is_upward(verts: np.ndarray, side_len: float) -> bool:
    """Apex at top (smallest y), base near horizontal at bottom."""
    sorted_v = verts[np.argsort(verts[:, 1])]
    apex = sorted_v[0]
    base = sorted_v[1:]
    # Base should be roughly horizontal
    bx0, by0 = base[0]
    bx1, by1 = base[1]
    base_angle = abs(np.degrees(np.arctan2(by1 - by0, bx1 - bx0)))
    base_angle = min(base_angle, 180.0 - base_angle)
    if base_angle > BASE_HORIZ_TOL_DEG:
        return False
    # Apex must sit above base by approximately side * sqrt(3) / 2
    base_avg_y = (by0 + by1) / 2.0
    apex_height = base_avg_y - apex[1]
    expected = side_len * np.sqrt(3.0) / 2.0
    if apex_height <= 0:
        return False  # apex isn't actually above base -> downward
    if abs(apex_height - expected) > APEX_HEIGHT_TOL * expected:
        return False
    return True


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
# Pipeline stages
# --------------------------------------------------------------------------


def stage_edges_and_close(gray: np.ndarray) -> np.ndarray:
    edges = cv2.Canny(gray, CANNY_LOW, CANNY_HIGH)
    if CLOSE_KERNEL > 0:
        k = np.ones((CLOSE_KERNEL, CLOSE_KERNEL), np.uint8)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k)
    return edges


def stage_hough(edges: np.ndarray) -> np.ndarray:
    lines = cv2.HoughLinesP(
        edges,
        rho=HOUGH_RHO,
        theta=HOUGH_THETA,
        threshold=HOUGH_VOTE_THRESHOLD,
        minLineLength=HOUGH_MIN_LINE_LENGTH,
        maxLineGap=HOUGH_MAX_LINE_GAP,
    )
    if lines is None:
        return np.empty((0, 4), dtype=np.float32)
    return lines.reshape(-1, 4).astype(np.float32)


def stage_merge_collinear(segments: np.ndarray) -> list[MergedLine]:
    """Cluster segments by (angle, rho) and merge each cluster into one line.

    Uses a (angle_bucket, rho_bucket) hash grid + union-find so each segment
    only checks its own bucket and the 8 neighbours instead of every other
    segment. O(n) expected vs. O(n^2) for the naive double loop.

    The merged line spans the extreme projections of its members onto the
    cluster's average direction.
    """
    n = len(segments)
    if n == 0:
        return []

    # Vectorized (angle, rho) per segment
    x1 = segments[:, 0]; y1 = segments[:, 1]
    x2 = segments[:, 2]; y2 = segments[:, 3]
    raw = np.degrees(np.arctan2(y2 - y1, x2 - x1)).astype(np.float32)
    angles = np.mod(raw, 180.0)
    # rho = perpendicular distance from origin = x*cos(theta+90) + y*sin(theta+90)
    theta_perp = np.radians(angles + 90.0)
    rhos = (x1 * np.cos(theta_perp) + y1 * np.sin(theta_perp)).astype(np.float32)

    # Spatial hash by quantized (angle, rho). Bucket size = tolerance, so
    # collinear segments are guaranteed to land in the same OR an adjacent
    # bucket.
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
        ab_i = int(ab[i])
        rb_i = int(rb[i])
        ang_i = float(angles[i])
        rho_i = float(rhos[i])
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

    # Group by root
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    merged: list[MergedLine] = []
    for idxs_list in groups.values():
        idxs = np.array(idxs_list, dtype=np.int64)
        ang_rad = np.radians(angles[idxs] * 2.0)  # double-angle to handle wrap
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


def stage_triplet_to_triangles(lines: list[MergedLine]) -> list[Triangle]:
    """Build upward equilaterals from (horizontal, +60°, -60°) triplets.

    Spatial-bucket optimization: every Δ side fits in a SIDE_LEN_MAX-wide
    box, so the three sides' midpoints are all within ~SIDE_LEN_MAX of each
    other. We bucket the +60°/-60° lines by midpoint into a grid of cell
    size SIDE_LEN_MAX, and for each horizontal base only consider slants
    in its cell ± 1 neighbour. Drops the cost from O(h*p*n) to roughly
    O(h * k_p * k_n) where k_p, k_n are average lines per neighbourhood.
    """
    horiz: list[MergedLine] = []
    pos: list[MergedLine] = []
    neg: list[MergedLine] = []
    for L in lines:
        if L.length > SIDE_LEN_MAX * 4:
            # Walls / dimension lines, never a Δ side
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

    triangles: list[Triangle] = []
    for H in horiz:
        hx, hy = _midpoint(H)
        bx, by = int(hx // cell), int(hy // cell)
        # Gather slants in the 3x3 neighbourhood of the base midpoint
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
            triangles.append(Triangle(
                vertices=verts,
                side_lengths=sides,
                angles_deg=angles,
                centroid=(cx, cy),
            ))
    return triangles


def stage_dedupe(triangles: list[Triangle]) -> list[Triangle]:
    """Greedy NMS on centroid distance; keep largest first."""
    keep: list[Triangle] = []
    for t in sorted(triangles, key=lambda x: -float(np.mean(x.side_lengths))):
        too_close = False
        for k in keep:
            d = np.hypot(t.centroid[0] - k.centroid[0], t.centroid[1] - k.centroid[1])
            if d < DEDUPE_RADIUS_PX:
                too_close = True
                break
        if not too_close:
            keep.append(t)
    return keep


def stage_assign_digits(triangles: list[Triangle], digit_words: list[dict]) -> None:
    """Look up any digit whose centroid sits inside each triangle. Mutates in place.

    Digit is OPTIONAL — destroyed digits leave triangle.digit = None.
    """
    used = set()
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
# Visualization
# --------------------------------------------------------------------------


def overlay(gray: np.ndarray, triangles: list[Triangle], target_digit: str | None) -> np.ndarray:
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for t in triangles:
        if t.digit is None:
            color = (60, 60, 200)        # red
            label = "?"
        elif target_digit is not None and t.digit == target_digit:
            color = (0, 200, 0)           # green
            label = t.digit
        else:
            color = (200, 200, 0)         # cyan
            label = t.digit
        cv2.polylines(bgr, [t.vertices.astype(np.int32)], isClosed=True,
                      color=color, thickness=4)
        cx, cy = int(t.centroid[0]), int(t.centroid[1])
        cv2.putText(bgr, label, (cx - 12, cy + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, color, 4)
    return bgr


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path, default=None,
        help="Pre-denoised greyscale PNG. Defaults to denoise_2 output for the given pdf+page.",
    )
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--page", type=int, default=DEFAULT_PAGE)
    parser.add_argument("--target-digit", type=str, default=DEFAULT_TARGET_DIGIT)
    parser.add_argument("--out", type=str, default="detection_test_2",
                        help="Output filename stem. Written to experiments/delta_v3/<out>.png")
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

    t0 = time.time()
    edges = stage_edges_and_close(gray)
    print(f"  [1+2] Canny + close: {time.time() - t0:.2f}s")

    t0 = time.time()
    segments = stage_hough(edges)
    print(f"  [3]   Hough: {len(segments)} raw segments in {time.time() - t0:.2f}s")

    t0 = time.time()
    merged = stage_merge_collinear(segments)
    print(f"  [4]   merged into {len(merged)} lines in {time.time() - t0:.2f}s")

    # Quick angle-bucket diagnostic
    horiz = sum(1 for L in merged if L.angle_deg <= HORIZ_ANGLE_TOL or L.angle_deg >= 180.0 - HORIZ_ANGLE_TOL)
    pos = sum(1 for L in merged if abs(L.angle_deg - SLANT_POS_CENTER) <= SLANT_ANGLE_TOL)
    neg = sum(1 for L in merged if abs(L.angle_deg - SLANT_NEG_CENTER) <= SLANT_ANGLE_TOL)
    print(f"        angle buckets: horizontal={horiz}, +60°={pos}, -60°={neg} "
          f"(spatial-pruned triplet enumeration)")

    t0 = time.time()
    triangles = stage_triplet_to_triangles(merged)
    print(f"  [5-8] {len(triangles)} valid upward equilateral triangles in {time.time() - t0:.2f}s")

    triangles = stage_dedupe(triangles)
    print(f"  [9]   {len(triangles)} after centroid NMS")

    digit_words = detect_deltas.extract_digit_words_in_pixels(pdf_path, args.page)
    stage_assign_digits(triangles, digit_words)
    n_with = sum(1 for t in triangles if t.digit is not None)
    n_target = sum(1 for t in triangles if t.digit == args.target_digit)
    n_no = len(triangles) - n_with
    print(f"  [10]  digit attribution: {n_with} with digit ({n_target} == '{args.target_digit}'), "
          f"{n_no} without digit")

    out_img = overlay(gray, triangles, args.target_digit)
    out_path = OUT_DIR / f"{args.out}.png"
    cv2.imwrite(str(out_path), out_img)
    print(f"\nOverlay -> {out_path.name}")


if __name__ == "__main__":
    main()
