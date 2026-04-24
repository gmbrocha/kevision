from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.contracts.detections import load_detection_manifest
from cloudhammer.infer.visualize import draw_overlay


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild overlays from a CloudHammer detection JSON.")
    parser.add_argument("detections_json", type=Path)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    out_dir = args.out_dir or args.detections_json.parent / "overlays"
    count = 0
    for page in load_detection_manifest(args.detections_json):
        if not page.render_path:
            continue
        image = cv2.imread(page.render_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            continue
        output_path = out_dir / f"{Path(page.pdf).stem}_p{page.page:04d}_clouds.png"
        draw_overlay(image, page.detections, output_path)
        count += 1
    print(f"wrote {count} overlays")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
