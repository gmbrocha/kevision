from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


WINDOW_NAME = "measure_arc_ratio"
OUTPUT_DIR = Path(__file__).parent / "measurements"
POINT_RADIUS = 4


@dataclass(frozen=True)
class CircleFit:
    cx: float
    cy: float
    radius: float


def fit_circle(points: list[tuple[float, float]]) -> CircleFit | None:
    if len(points) < 3:
        return None
    pts = np.asarray(points, dtype=np.float64)
    x = pts[:, 0]
    y = pts[:, 1]
    a = np.column_stack((2 * x, 2 * y, np.ones(len(pts))))
    b = x * x + y * y
    try:
        sol, *_ = np.linalg.lstsq(a, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cx, cy, c = sol.tolist()
    radius_sq = c + cx * cx + cy * cy
    if radius_sq <= 0:
        return None
    return CircleFit(cx=float(cx), cy=float(cy), radius=float(math.sqrt(radius_sq)))


def scaled_image(image: np.ndarray) -> tuple[np.ndarray, int]:
    h, w = image.shape[:2]
    max_dim = max(h, w)
    if max_dim <= 300:
        scale = 4
    elif max_dim <= 700:
        scale = 2
    else:
        scale = 1
    if scale == 1:
        return image.copy(), scale
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST), scale


def draw_scene(
    gray: np.ndarray,
    points_big: list[tuple[float, float]],
    points_small: list[tuple[float, float]],
    active_set: int,
) -> tuple[np.ndarray, int]:
    base = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    display, scale = scaled_image(base)

    def draw_points(points: list[tuple[float, float]], color: tuple[int, int, int]) -> None:
        for x, y in points:
            cv2.circle(display, (int(round(x * scale)), int(round(y * scale))), POINT_RADIUS * scale, color, -1)

    def draw_circle(points: list[tuple[float, float]], color: tuple[int, int, int]) -> None:
        fit = fit_circle(points)
        if fit is None:
            return
        cv2.circle(
            display,
            (int(round(fit.cx * scale)), int(round(fit.cy * scale))),
            int(round(fit.radius * scale)),
            color,
            max(1, scale),
        )

    draw_points(points_big, (0, 180, 0))
    draw_points(points_small, (220, 0, 0))
    draw_circle(points_big, (0, 220, 0))
    draw_circle(points_small, (255, 0, 0))

    active_label = "BIG arc" if active_set == 0 else "SMALL arc"
    info_lines = [
        "Left click: add point",
        "Space: switch to small arc",
        "Z / Backspace: undo last point",
        "R: reset all",
        "Enter: fit and save",
        f"Active set: {active_label}",
        f"BIG points: {len(points_big)}  SMALL points: {len(points_small)}",
    ]
    y = 24
    for line in info_lines:
        cv2.putText(display, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6 * scale, (0, 0, 0), max(1, scale), cv2.LINE_AA)
        y += int(22 * scale)
    return display, scale


def save_outputs(
    image_path: Path,
    gray: np.ndarray,
    points_big: list[tuple[float, float]],
    points_small: list[tuple[float, float]],
) -> None:
    fit_big = fit_circle(points_big)
    fit_small = fit_circle(points_small)
    if fit_big is None or fit_small is None:
        raise RuntimeError("Need at least 3 valid points for each arc.")

    ratio = fit_big.radius / fit_small.radius if fit_small.radius > 1e-9 else float("inf")
    center_distance = math.hypot(fit_big.cx - fit_small.cx, fit_big.cy - fit_small.cy)

    annotated = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for x, y in points_big:
        cv2.circle(annotated, (int(round(x)), int(round(y))), 4, (0, 180, 0), -1)
    for x, y in points_small:
        cv2.circle(annotated, (int(round(x)), int(round(y))), 4, (220, 0, 0), -1)
    cv2.circle(annotated, (int(round(fit_big.cx)), int(round(fit_big.cy))), int(round(fit_big.radius)), (0, 220, 0), 2)
    cv2.circle(annotated, (int(round(fit_small.cx)), int(round(fit_small.cy))), int(round(fit_small.radius)), (255, 0, 0), 2)
    cv2.putText(
        annotated,
        f"big={fit_big.radius:.2f}px small={fit_small.radius:.2f}px ratio={ratio:.3f} center_dist={center_distance:.2f}px",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = image_path.stem
    png_path = OUTPUT_DIR / f"{stem}_measured.png"
    json_path = OUTPUT_DIR / f"{stem}_measured.json"
    cv2.imwrite(str(png_path), annotated)
    payload = {
        "image_path": str(image_path),
        "big_arc": {
            "points": [{"x": float(x), "y": float(y)} for x, y in points_big],
            "center": {"x": fit_big.cx, "y": fit_big.cy},
            "radius_px": fit_big.radius,
        },
        "small_arc": {
            "points": [{"x": float(x), "y": float(y)} for x, y in points_small],
            "center": {"x": fit_small.cx, "y": fit_small.cy},
            "radius_px": fit_small.radius,
        },
        "radius_ratio_big_over_small": ratio,
        "center_distance_px": center_distance,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved annotated image -> {png_path}")
    print(f"Saved measurements JSON -> {json_path}")
    print(
        f"big radius = {fit_big.radius:.2f}px, "
        f"small radius = {fit_small.radius:.2f}px, "
        f"ratio = {ratio:.3f}, center distance = {center_distance:.2f}px"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True, help="Path to an image containing one big/small scallop pair.")
    args = parser.parse_args()

    image_path = args.image if args.image.is_absolute() else (Path.cwd() / args.image).resolve()
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        print(f"Could not read image: {image_path}")
        return 1

    state = {
        "big": [],
        "small": [],
        "active": 0,
        "display_scale": 1,
    }

    def redraw() -> None:
        display, scale = draw_scene(gray, state["big"], state["small"], state["active"])
        state["display_scale"] = scale
        cv2.imshow(WINDOW_NAME, display)

    def on_mouse(event: int, x: int, y: int, _flags: int, _userdata: object) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        scale = max(1, int(state["display_scale"]))
        px = x / scale
        py = y / scale
        key = "big" if state["active"] == 0 else "small"
        state[key].append((px, py))
        redraw()

    try:
        cv2.destroyWindow(WINDOW_NAME)
    except cv2.error:
        pass
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW_NAME, on_mouse)
    redraw()
    print("Click points along the BIG arc, press Space, click points along the SMALL arc, then press Enter.")

    while True:
        key = cv2.waitKey(20) & 0xFF
        if key == 27:  # ESC
            cv2.destroyAllWindows()
            print("Cancelled.")
            return 0
        if key == ord(" "):
            state["active"] = 1
            redraw()
        elif key in (ord("z"), 8):
            current = "big" if state["active"] == 0 else "small"
            if state[current]:
                state[current].pop()
                redraw()
        elif key == ord("r"):
            state["big"].clear()
            state["small"].clear()
            state["active"] = 0
            redraw()
        elif key in (13, 10):
            if len(state["big"]) >= 3 and len(state["small"]) >= 3:
                save_outputs(image_path, gray, state["big"], state["small"])
                cv2.destroyAllWindows()
                return 0
            print("Need at least 3 points on each arc before pressing Enter.")


if __name__ == "__main__":
    raise SystemExit(main())
