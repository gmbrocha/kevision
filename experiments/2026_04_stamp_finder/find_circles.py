"""
Step 1 of the stamp-finder pipeline.

Run cv2.HoughCircles on a cleaned page (or crop), dump every candidate circle
as JSON and overlay PNG. No filtering, no pairing, no scoring -- this script
exists so a human can eyeball whether the real scallops are even in the
candidate set before we build anything on top.

If real scallops do not appear here, HoughCircles is the wrong primitive and
we should drop to RANSAC arc fitting on Canny edges instead.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np


OUTPUT_DIR = Path(__file__).parent / "output"


def parse_crop(value: str | None) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("crop must be 'x,y,w,h'")
    x, y, w, h = (int(p.strip()) for p in parts)
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError("crop width and height must be positive")
    return x, y, w, h


def load_input(path: Path, crop: tuple[int, int, int, int] | None) -> tuple[np.ndarray, tuple[int, int]]:
    """Return (gray_image, (offset_x, offset_y)). Offset lets callers map back to full-page coords."""
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(f"could not read image: {path}")
    if crop is None:
        return gray, (0, 0)
    x, y, w, h = crop
    h_img, w_img = gray.shape
    if x < 0 or y < 0 or x + w > w_img or y + h > h_img:
        raise ValueError(
            f"crop {crop} falls outside image bounds {w_img}x{h_img}"
        )
    return gray[y : y + h, x : x + w].copy(), (x, y)


_MODE_LOOKUP = {
    "gradient": cv2.HOUGH_GRADIENT,
    "gradient_alt": cv2.HOUGH_GRADIENT_ALT,
}


def find_circles(
    gray: np.ndarray,
    *,
    rmin: int,
    rmax: int,
    param1: int,
    param2: float,
    min_dist: int,
    dp: float,
    mode: str = "gradient",
) -> np.ndarray:
    """Wrap cv2.HoughCircles. Returns (N, 3) array of (cx, cy, r) in image coords, possibly empty.

    mode='gradient'      -> classic; param2 = accumulator threshold (lower = more circles)
    mode='gradient_alt'  -> partial-arc-friendly; param2 = circle perfectness 0..1 (lower = more circles)
    """
    if mode not in _MODE_LOOKUP:
        raise ValueError(f"unknown mode {mode!r}; expected one of {list(_MODE_LOOKUP)}")
    blurred = cv2.medianBlur(gray, 3)
    raw = cv2.HoughCircles(
        blurred,
        _MODE_LOOKUP[mode],
        dp=dp,
        minDist=min_dist,
        param1=param1,
        param2=param2,
        minRadius=rmin,
        maxRadius=rmax,
    )
    if raw is None:
        return np.zeros((0, 3), dtype=np.float32)
    return raw[0]  # shape (N, 3) — (x, y, r)


def find_circles_multi_band(
    gray: np.ndarray,
    *,
    bands: list[tuple[int, int, float]],
    param1: int,
    min_dist: int,
    dp: float,
    mode: str,
) -> np.ndarray:
    """Run a separate Hough pass per (rmin, rmax, param2) band and concatenate results.

    Useful when big and small arcs of the same motif need different sensitivity (e.g. small/short
    companion arcs need a lower param2 floor than big main arcs).
    """
    parts: list[np.ndarray] = []
    for rmin, rmax, param2 in bands:
        circles = find_circles(
            gray,
            rmin=rmin,
            rmax=rmax,
            param1=param1,
            param2=param2,
            min_dist=min_dist,
            dp=dp,
            mode=mode,
        )
        if len(circles):
            parts.append(circles)
    if not parts:
        return np.zeros((0, 3), dtype=np.float32)
    return np.concatenate(parts, axis=0)


def draw_overlay(gray: np.ndarray, circles: np.ndarray) -> np.ndarray:
    overlay = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for cx, cy, r in circles:
        cv2.circle(overlay, (int(round(cx)), int(round(cy))), int(round(r)), (0, 200, 255), 2)
        cv2.circle(overlay, (int(round(cx)), int(round(cy))), 2, (0, 0, 255), -1)
    return overlay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--image", type=Path, required=True, help="Path to cleaned (or raw) page image.")
    parser.add_argument("--crop", type=parse_crop, default=None, help="Optional crop 'x,y,w,h' for fast iteration.")
    parser.add_argument("--rmin", type=int, default=10, help="HoughCircles minRadius in px.")
    parser.add_argument("--rmax", type=int, default=120, help="HoughCircles maxRadius in px.")
    parser.add_argument("--param1", type=int, default=120, help="HoughCircles param1 (Canny upper).")
    parser.add_argument(
        "--param2",
        type=float,
        default=20,
        help="HoughCircles param2. mode=gradient: accumulator threshold (lower=more); mode=gradient_alt: 'perfectness' 0..1 (lower=more).",
    )
    parser.add_argument("--min-dist", type=int, default=8, help="HoughCircles minDist between centers in px.")
    parser.add_argument("--dp", type=float, default=1.0, help="HoughCircles inverse accumulator resolution.")
    parser.add_argument(
        "--mode",
        choices=sorted(_MODE_LOOKUP.keys()),
        default="gradient",
        help="HoughCircles mode. 'gradient_alt' handles partial/short arcs better.",
    )
    parser.add_argument(
        "--bands",
        type=str,
        default=None,
        help=(
            "Optional multi-band sweep, format 'rmin:rmax:param2,rmin:rmax:param2,...'. "
            "Overrides --rmin/--rmax/--param2. E.g. '8:16:6,16:30:10' runs two passes."
        ),
    )
    parser.add_argument(
        "--out-stem",
        type=str,
        default=None,
        help="Override output stem; defaults to image filename stem (with crop suffix if cropped).",
    )
    args = parser.parse_args()

    image_path = args.image if args.image.is_absolute() else (Path.cwd() / args.image).resolve()
    gray, (off_x, off_y) = load_input(image_path, args.crop)
    print(f"Input: {image_path.name}  shape={gray.shape}  offset=({off_x},{off_y})")

    bands: list[tuple[int, int, float]] | None = None
    if args.bands:
        bands = []
        for chunk in args.bands.split(","):
            parts = chunk.strip().split(":")
            if len(parts) != 3:
                raise SystemExit(f"--bands chunk {chunk!r} must be 'rmin:rmax:param2'")
            bands.append((int(parts[0]), int(parts[1]), float(parts[2])))

    if bands:
        print(f"Mode: {args.mode}  bands: {bands}  minDist={args.min_dist}  dp={args.dp}")
    else:
        print(
            f"Mode: {args.mode}  r=[{args.rmin},{args.rmax}]  param1={args.param1}  "
            f"param2={args.param2}  minDist={args.min_dist}  dp={args.dp}"
        )

    t0 = time.time()
    if bands:
        circles = find_circles_multi_band(
            gray,
            bands=bands,
            param1=args.param1,
            min_dist=args.min_dist,
            dp=args.dp,
            mode=args.mode,
        )
    else:
        circles = find_circles(
            gray,
            rmin=args.rmin,
            rmax=args.rmax,
            param1=args.param1,
            param2=args.param2,
            min_dist=args.min_dist,
            dp=args.dp,
            mode=args.mode,
        )
    elapsed = time.time() - t0
    print(f"Found {len(circles)} candidate circles in {elapsed:.2f}s")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = args.out_stem or image_path.stem
    if args.crop is not None:
        cx, cy, cw, ch = args.crop
        stem = f"{stem}__crop_{cx}_{cy}_{cw}_{ch}"

    overlay = draw_overlay(gray, circles)
    overlay_path = OUTPUT_DIR / f"{stem}__circles.png"
    cv2.imwrite(str(overlay_path), overlay)

    payload = {
        "image_path": str(image_path),
        "image_shape": [int(gray.shape[0]), int(gray.shape[1])],
        "crop_offset": [off_x, off_y],
        "hough_params": {
            "mode": args.mode,
            "rmin": args.rmin,
            "rmax": args.rmax,
            "param1": args.param1,
            "param2": args.param2,
            "min_dist": args.min_dist,
            "dp": args.dp,
            "bands": bands,
        },
        "elapsed_s": elapsed,
        "circles": [
            {
                "cx_local": float(cx),
                "cy_local": float(cy),
                "cx_full": float(cx) + off_x,
                "cy_full": float(cy) + off_y,
                "r": float(r),
            }
            for cx, cy, r in circles
        ],
    }
    json_path = OUTPUT_DIR / f"{stem}__circles.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Overlay -> {overlay_path}")
    print(f"JSON    -> {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
