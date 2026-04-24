"""
Step 2 of the stamp-finder pipeline.

Load a circles JSON dump from find_circles.py, optionally NMS-collapse
near-duplicate circles (HoughCircles tends to fire several times on one true
arc), then enumerate all ordered (big, small) pairs and filter by the two
stamp invariants:

    r_big / r_small             target ~1.77   (tol --ratio-tol)
    || c_big - c_small || / r_big   target ~1.281 (tol --dist-tol)

Dump matched pairs as JSON + overlay PNG. No chain assembly here -- that's
step 3 (`find_chains.py`).
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np


OUTPUT_DIR = Path(__file__).parent / "output"

# Stamp invariants measured from manual scallop fits (see README.md).
DEFAULT_RATIO = 1.77
DEFAULT_RATIO_TOL = 0.05
DEFAULT_DIST_OVER_RBIG = 1.281
DEFAULT_DIST_TOL = 0.03


def load_circles_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def reconstruct_input_image(payload: dict) -> np.ndarray:
    """Re-read the source image and re-apply the crop the circles were detected on."""
    image_path = Path(payload["image_path"])
    full = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if full is None:
        raise FileNotFoundError(f"could not re-read source image: {image_path}")
    off_x, off_y = payload["crop_offset"]
    h, w = payload["image_shape"]
    return full[off_y : off_y + h, off_x : off_x + w].copy()


def circles_to_array(payload: dict) -> np.ndarray:
    """Return (N, 3) float32 array of (cx_local, cy_local, r) — coords already in crop-local space."""
    rows = payload.get("circles", [])
    if not rows:
        return np.zeros((0, 3), dtype=np.float32)
    return np.asarray(
        [(c["cx_local"], c["cy_local"], c["r"]) for c in rows],
        dtype=np.float32,
    )


def compute_edge_distance_transform(
    gray: np.ndarray, *, canny_high: int
) -> np.ndarray:
    """Canny edges then distance transform of the *non-edge* pixels.

    Returned array has 0 on edge pixels and increasing distance to the nearest edge
    elsewhere. Used by `edge_support_scores` to ask "is this point near an edge?"
    in O(1) per query.
    """
    canny_low = max(1, canny_high // 2)
    edges = cv2.Canny(gray, canny_low, canny_high)
    # distanceTransform expects "distance to nearest zero". We want distance to nearest
    # edge, so invert: edges (255) -> 0, non-edges (0) -> 255.
    inv = cv2.bitwise_not(edges)
    return cv2.distanceTransform(inv, cv2.DIST_L2, 3)


def edge_support_scores(
    circles: np.ndarray,
    edge_dt: np.ndarray,
    *,
    tol_px: float = 1.5,
    samples_per_px: float = 1.0,
) -> np.ndarray:
    """For each circle return fraction-of-perimeter that sits within `tol_px` of a Canny edge.

    Score in [0, 1]. Higher = the circle's perimeter actually traces real edge pixels.
    """
    h, w = edge_dt.shape
    n = len(circles)
    scores = np.zeros(n, dtype=np.float32)
    for k in range(n):
        cx, cy, r = float(circles[k, 0]), float(circles[k, 1]), float(circles[k, 2])
        n_samples = max(32, int(round(2.0 * math.pi * r * samples_per_px)))
        thetas = np.linspace(0.0, 2.0 * math.pi, n_samples, endpoint=False)
        xs = np.rint(cx + r * np.cos(thetas)).astype(np.int32)
        ys = np.rint(cy + r * np.sin(thetas)).astype(np.int32)
        mask = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        if not np.any(mask):
            scores[k] = 0.0
            continue
        sampled = edge_dt[ys[mask], xs[mask]]
        # Count out-of-image samples as "not on edge" (don't reward circles that fall off-page)
        scores[k] = float(np.sum(sampled <= tol_px)) / float(n_samples)
    return scores


def nms_collapse_by_score(
    circles: np.ndarray,
    scores: np.ndarray,
    *,
    center_frac: float = 0.5,
    radius_frac: float = 0.30,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Greedy single-link cluster of near-duplicate circles, keep max-score representative.

    Two circles are clustered if their center distance is within `center_frac * min(r_i, r_j)`
    AND their radii agree to within `radius_frac` (relative). Cluster rep is the member
    with the highest edge-support score (NOT the median geometry — median drifts the radius
    when a true arc fit gets averaged with concentric phantom fits).

    Returns (kept_circles (M,3), kept_scores (M,), cluster_sizes list of length M).
    """
    n = len(circles)
    if n == 0:
        return circles, scores, []
    # Sort by score desc so the seed of each greedy cluster is the strongest member.
    order = np.argsort(-scores)
    used = np.zeros(n, dtype=bool)
    kept_circles: list[list[float]] = []
    kept_scores: list[float] = []
    sizes: list[int] = []
    for idx in order:
        if used[idx]:
            continue
        cx_i, cy_i, r_i = circles[idx]
        cluster_size = 1
        used[idx] = True
        # Sweep all remaining unused for cluster membership; the seed wins automatically
        # because it has the highest score and we take it as representative.
        for j in range(n):
            if used[j] or j == idx:
                continue
            cx_j, cy_j, r_j = circles[j]
            min_r = float(min(r_i, r_j))
            max_r = float(max(r_i, r_j))
            if max_r <= 0:
                continue
            if math.hypot(float(cx_i - cx_j), float(cy_i - cy_j)) > center_frac * min_r:
                continue
            if (max_r - min_r) / max_r > radius_frac:
                continue
            used[j] = True
            cluster_size += 1
        kept_circles.append([float(cx_i), float(cy_i), float(r_i)])
        kept_scores.append(float(scores[idx]))
        sizes.append(cluster_size)
    return (
        np.asarray(kept_circles, dtype=np.float32),
        np.asarray(kept_scores, dtype=np.float32),
        sizes,
    )


def mutually_exclusive_pairs(pairs: list[dict]) -> list[dict]:
    """Force one-best-partner-per-circle before pair-NMS runs.

    The invariant filter alone happily emits multiple pairs that share a big
    (one big can sit at the right ratio + spacing relative to several smalls)
    or share a small. Pair-NMS then has to mop those up by midpoint clustering,
    which is fragile when the duplicates are spread far apart.

    Mutual-exclusion does it earlier and more cleanly:

      - For each big circle, pick the candidate small with the highest
        ``edge_support_small`` among all invariant-passing pairs that big
        participates in.
      - For each small circle, pick the candidate big with the highest
        ``edge_support_big`` symmetrically.
      - Keep pair (b, s) iff b chose s AND s chose b (mutual best-match).

    A circle whose preferred partner preferred someone else drops out — that's
    intentional. The losing pair was almost certainly a duplicate of the
    winning pair on the same physical motif (or a true non-match) and will
    not survive pair-NMS anyway.

    Pairs without ``edge_support_*`` keys (i.e. scores were not computed
    upstream) are returned unchanged: this stage is a no-op without scores.
    """
    if not pairs:
        return []
    if not all("edge_support_small" in p and "edge_support_big" in p for p in pairs):
        return list(pairs)

    def big_key(p: dict) -> tuple[float, float, float]:
        b = p["big"]
        return (b["cx"], b["cy"], b["r"])

    def small_key(p: dict) -> tuple[float, float, float]:
        s = p["small"]
        return (s["cx"], s["cy"], s["r"])

    # Per-big: index of the pair whose small has the highest edge_support_small.
    # Per-small: index of the pair whose big has the highest edge_support_big.
    # Ties go to the earlier index (stable, deterministic given input order).
    best_small_for_big: dict[tuple[float, float, float], tuple[int, float]] = {}
    best_big_for_small: dict[tuple[float, float, float], tuple[int, float]] = {}
    for idx, p in enumerate(pairs):
        bk = big_key(p)
        sk = small_key(p)
        es_small = float(p["edge_support_small"])
        es_big = float(p["edge_support_big"])
        prev = best_small_for_big.get(bk)
        if prev is None or es_small > prev[1]:
            best_small_for_big[bk] = (idx, es_small)
        prev = best_big_for_small.get(sk)
        if prev is None or es_big > prev[1]:
            best_big_for_small[sk] = (idx, es_big)

    kept: list[dict] = []
    for idx, p in enumerate(pairs):
        if (
            best_small_for_big[big_key(p)][0] == idx
            and best_big_for_small[small_key(p)][0] == idx
        ):
            kept.append(p)
    return kept


def _pair_midpoint(p: dict) -> tuple[float, float]:
    bx, by = p["big"]["cx"], p["big"]["cy"]
    sx, sy = p["small"]["cx"], p["small"]["cy"]
    return (0.5 * (bx + sx), 0.5 * (by + sy))


def nms_pairs(
    pairs: list[dict],
    *,
    center_tol_frac: float = 0.50,
    radius_tol_frac: float = 0.30,
) -> list[dict]:
    """Collapse near-duplicate pairs that describe the same physical motif.

    Cluster criterion: pair midpoints agree within `center_tol_frac * r_big` AND r_big
    values agree within `radius_tol_frac`. Midpoint is used (not big-center alone) because
    both arc fits jitter independently — a stable single-motif anchor needs both endpoints.

    Per cluster, keep the pair with the highest summed edge-support score.
    """
    if not pairs:
        return []
    used = [False] * len(pairs)
    kept: list[dict] = []
    midpoints = [_pair_midpoint(p) for p in pairs]
    order = sorted(
        range(len(pairs)),
        key=lambda i: -(pairs[i].get("edge_support_total", 0.0)),
    )
    for idx in order:
        if used[idx]:
            continue
        seed = pairs[idx]
        used[idx] = True
        r_big_seed = float(seed["big"]["r"])
        mx_seed, my_seed = midpoints[idx]
        cluster_count = 1
        for j in range(len(pairs)):
            if used[j] or j == idx:
                continue
            other = pairs[j]
            r_big_other = float(other["big"]["r"])
            if abs(r_big_other - r_big_seed) / max(r_big_seed, 1e-6) > radius_tol_frac:
                continue
            mx_other, my_other = midpoints[j]
            if math.hypot(mx_other - mx_seed, my_other - my_seed) > center_tol_frac * r_big_seed:
                continue
            used[j] = True
            cluster_count += 1
        out = dict(seed)
        out["pair_cluster_size"] = cluster_count
        kept.append(out)
    return kept


def find_pairs(
    circles: np.ndarray,
    *,
    target_ratio: float,
    ratio_tol: float,
    target_dist_over_rbig: float,
    dist_tol: float,
    scores: np.ndarray | None = None,
) -> list[dict]:
    """Enumerate ordered (big, small) pairs and keep those passing both stamp invariants.

    If `scores` is provided (one per circle, same indexing as `circles`), each emitted
    pair carries `edge_support_big`, `edge_support_small`, `edge_support_total`.
    O(n^2). Acceptable per the experiment's design notes.
    """
    pairs: list[dict] = []
    n = len(circles)
    for i in range(n):
        cx_i, cy_i, r_i = circles[i]
        for j in range(n):
            if i == j:
                continue
            cx_j, cy_j, r_j = circles[j]
            if r_j >= r_i:
                continue  # require strict r_big > r_small to avoid emitting both orderings
            ratio = float(r_i / r_j)
            if abs(ratio - target_ratio) > ratio_tol:
                continue
            dist = math.hypot(float(cx_i - cx_j), float(cy_i - cy_j))
            dist_over_rbig = dist / float(r_i)
            if abs(dist_over_rbig - target_dist_over_rbig) > dist_tol:
                continue
            rec: dict = {
                "big": {"cx": float(cx_i), "cy": float(cy_i), "r": float(r_i)},
                "small": {"cx": float(cx_j), "cy": float(cy_j), "r": float(r_j)},
                "ratio": ratio,
                "dist": float(dist),
                "dist_over_rbig": float(dist_over_rbig),
                "scale_rbig": float(r_i),
            }
            if scores is not None:
                rec["edge_support_big"] = float(scores[i])
                rec["edge_support_small"] = float(scores[j])
                rec["edge_support_total"] = float(scores[i] + scores[j])
            pairs.append(rec)
    return pairs


def draw_pair_overlay(
    gray: np.ndarray,
    candidate_circles: np.ndarray,
    pairs: list[dict],
    *,
    show_candidates: bool = True,
) -> np.ndarray:
    overlay = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    if show_candidates:
        # Faded view of every candidate circle (post-NMS) so we can see what got rejected.
        for cx, cy, r in candidate_circles:
            cv2.circle(
                overlay,
                (int(round(float(cx))), int(round(float(cy)))),
                int(round(float(r))),
                (180, 180, 180),
                1,
            )
    # Matched pairs: big = green, small = red, connecting line = orange.
    for p in pairs:
        bx, by, br = p["big"]["cx"], p["big"]["cy"], p["big"]["r"]
        sx, sy, sr = p["small"]["cx"], p["small"]["cy"], p["small"]["r"]
        cv2.circle(overlay, (int(round(bx)), int(round(by))), int(round(br)), (0, 200, 0), 2)
        cv2.circle(overlay, (int(round(sx)), int(round(sy))), int(round(sr)), (0, 0, 220), 2)
        cv2.line(
            overlay,
            (int(round(bx)), int(round(by))),
            (int(round(sx)), int(round(sy))),
            (255, 120, 0),
            1,
        )
    return overlay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--circles",
        type=Path,
        required=True,
        help="Path to a circles JSON dumped by find_circles.py.",
    )
    parser.add_argument("--ratio", type=float, default=DEFAULT_RATIO, help="Target r_big / r_small.")
    parser.add_argument(
        "--ratio-tol", type=float, default=DEFAULT_RATIO_TOL, help="Absolute tolerance on radius ratio."
    )
    parser.add_argument(
        "--dist-ratio",
        type=float,
        default=DEFAULT_DIST_OVER_RBIG,
        help="Target center_distance / r_big.",
    )
    parser.add_argument(
        "--dist-tol", type=float, default=DEFAULT_DIST_TOL, help="Absolute tolerance on dist/r_big."
    )
    parser.add_argument("--no-nms", action="store_true", help="Skip circle-level NMS collapse.")
    parser.add_argument(
        "--nms-center-frac",
        type=float,
        default=0.5,
        help="Circle NMS: merge centers within this fraction of min(r_i, r_j).",
    )
    parser.add_argument(
        "--nms-radius-frac",
        type=float,
        default=0.30,
        help="Circle NMS: merge radii within this relative tolerance.",
    )
    parser.add_argument(
        "--no-mutex-pairs",
        action="store_true",
        help="Skip mutually-exclusive pair selection (one best partner per big and per small) before pair-NMS.",
    )
    parser.add_argument(
        "--no-pair-nms",
        action="store_true",
        help="Skip pair-level NMS that collapses duplicate pairs describing the same motif.",
    )
    parser.add_argument(
        "--pair-nms-center-frac",
        type=float,
        default=0.50,
        help="Pair NMS: collapse pairs whose midpoints agree within frac * r_big.",
    )
    parser.add_argument(
        "--pair-nms-radius-frac",
        type=float,
        default=0.30,
        help="Pair NMS: collapse pairs whose r_big values agree within this relative tolerance.",
    )
    parser.add_argument(
        "--canny-high",
        type=int,
        default=None,
        help="Canny upper threshold for edge-support scoring. Defaults to circles JSON's hough_params.param1.",
    )
    parser.add_argument(
        "--edge-tol-px",
        type=float,
        default=1.5,
        help="Perimeter sample is 'on edge' if within this many pixels of a Canny edge.",
    )
    parser.add_argument(
        "--no-candidate-overlay",
        action="store_true",
        help="Suppress the faded gray candidate circles in the output overlay.",
    )
    parser.add_argument(
        "--out-stem",
        type=str,
        default=None,
        help="Override output stem; defaults to circles JSON stem with __pairs suffix.",
    )
    args = parser.parse_args()

    circles_path = args.circles if args.circles.is_absolute() else (Path.cwd() / args.circles).resolve()
    payload = load_circles_payload(circles_path)
    raw_circles = circles_to_array(payload)
    print(f"Input: {circles_path.name}  raw circles = {len(raw_circles)}")

    gray = reconstruct_input_image(payload)
    canny_high = args.canny_high
    if canny_high is None:
        canny_high = int(payload.get("hough_params", {}).get("param1", 120))
    t0 = time.time()
    edge_dt = compute_edge_distance_transform(gray, canny_high=canny_high)
    raw_scores = (
        edge_support_scores(raw_circles, edge_dt, tol_px=args.edge_tol_px)
        if len(raw_circles)
        else np.zeros(0, dtype=np.float32)
    )
    print(
        f"Edge support: canny_high={canny_high}  tol={args.edge_tol_px}px  "
        f"computed in {time.time() - t0:.2f}s  "
        f"(median={float(np.median(raw_scores)) if len(raw_scores) else 0.0:.3f}, "
        f"max={float(np.max(raw_scores)) if len(raw_scores) else 0.0:.3f})"
    )

    if args.no_nms or len(raw_circles) == 0:
        nms_circles = raw_circles
        nms_scores = raw_scores
        cluster_sizes: list[int] = [1] * len(raw_circles)
    else:
        t0 = time.time()
        nms_circles, nms_scores, cluster_sizes = nms_collapse_by_score(
            raw_circles,
            raw_scores,
            center_frac=args.nms_center_frac,
            radius_frac=args.nms_radius_frac,
        )
        print(
            f"Circle NMS (edge-fit pick): {len(raw_circles)} -> {len(nms_circles)} circles "
            f"in {time.time() - t0:.2f}s  (largest cluster = {max(cluster_sizes) if cluster_sizes else 0})"
        )

    print(
        f"Pair filter: ratio={args.ratio:.3f} +/- {args.ratio_tol:.3f}  "
        f"dist/r_big={args.dist_ratio:.3f} +/- {args.dist_tol:.3f}"
    )
    t0 = time.time()
    pairs_raw = find_pairs(
        nms_circles,
        target_ratio=args.ratio,
        ratio_tol=args.ratio_tol,
        target_dist_over_rbig=args.dist_ratio,
        dist_tol=args.dist_tol,
        scores=nms_scores,
    )
    print(f"Pairs (post invariant filter): {len(pairs_raw)} in {time.time() - t0:.2f}s")

    if args.no_mutex_pairs:
        pairs_mutex = pairs_raw
    else:
        t0 = time.time()
        pairs_mutex = mutually_exclusive_pairs(pairs_raw)
        print(
            f"Pairs (post mutex selection): {len(pairs_raw)} -> {len(pairs_mutex)} "
            f"in {time.time() - t0:.2f}s"
        )

    if args.no_pair_nms:
        pairs = pairs_mutex
    else:
        t0 = time.time()
        pairs = nms_pairs(
            pairs_mutex,
            center_tol_frac=args.pair_nms_center_frac,
            radius_tol_frac=args.pair_nms_radius_frac,
        )
        print(f"Pairs (post pair-NMS): {len(pairs)} in {time.time() - t0:.2f}s")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = args.out_stem or (circles_path.stem.replace("__circles", "") + "__pairs")
    overlay_path = OUTPUT_DIR / f"{stem}.png"
    json_path = OUTPUT_DIR / f"{stem}.json"

    overlay = draw_pair_overlay(
        gray, nms_circles, pairs, show_candidates=not args.no_candidate_overlay
    )
    cv2.imwrite(str(overlay_path), overlay)

    off_x, off_y = payload["crop_offset"]
    out_payload = {
        "source_circles_json": str(circles_path),
        "image_path": payload["image_path"],
        "image_shape": payload["image_shape"],
        "crop_offset": payload["crop_offset"],
        "filter": {
            "target_ratio": args.ratio,
            "ratio_tol": args.ratio_tol,
            "target_dist_over_rbig": args.dist_ratio,
            "dist_tol": args.dist_tol,
        },
        "edge_support": {
            "canny_high": canny_high,
            "tol_px": args.edge_tol_px,
        },
        "nms": {
            "applied": not args.no_nms,
            "center_frac": args.nms_center_frac,
            "radius_frac": args.nms_radius_frac,
            "raw_circles": int(len(raw_circles)),
            "post_nms_circles": int(len(nms_circles)),
        },
        "mutex_pairs": {
            "applied": not args.no_mutex_pairs,
            "pairs_pre": int(len(pairs_raw)),
            "pairs_post": int(len(pairs_mutex)),
        },
        "pair_nms": {
            "applied": not args.no_pair_nms,
            "center_tol_frac": args.pair_nms_center_frac,
            "radius_tol_frac": args.pair_nms_radius_frac,
            "pairs_pre": int(len(pairs_mutex)),
            "pairs_post": int(len(pairs)),
        },
        "pairs": [
            {
                **p,
                "big_full": {
                    "cx": p["big"]["cx"] + off_x,
                    "cy": p["big"]["cy"] + off_y,
                    "r": p["big"]["r"],
                },
                "small_full": {
                    "cx": p["small"]["cx"] + off_x,
                    "cy": p["small"]["cy"] + off_y,
                    "r": p["small"]["r"],
                },
            }
            for p in pairs
        ],
    }
    json_path.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")

    print(f"Overlay -> {overlay_path}")
    print(f"JSON    -> {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
