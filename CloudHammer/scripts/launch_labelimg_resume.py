from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def natural_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def is_reviewed(label_path: Path, raw_label_path: Path, tolerance_seconds: float = 1.0) -> bool:
    if not label_path.exists() or not raw_label_path.exists():
        return False
    return label_path.stat().st_mtime > raw_label_path.stat().st_mtime + tolerance_seconds


def find_resume_image(image_dir: Path, raw_label_dir: Path, reviewed_label_dir: Path) -> tuple[Path | None, int, int]:
    images = sorted(
        [path for path in image_dir.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}],
        key=lambda path: natural_key(str(path.resolve()).lower()),
    )
    reviewed_count = 0
    for image in images:
        raw_label = raw_label_dir / f"{image.stem}.txt"
        reviewed_label = reviewed_label_dir / f"{image.stem}.txt"
        if is_reviewed(reviewed_label, raw_label):
            reviewed_count += 1
            continue
        return image, reviewed_count, len(images)
    return None, reviewed_count, len(images)


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch LabelImg at the first unsaved reviewed-label image.")
    parser.add_argument("--image-dir", type=Path, default=ROOT / "data" / "cloud_roi_images")
    parser.add_argument("--raw-label-dir", type=Path, default=ROOT / "data" / "api_cloud_labels_unreviewed")
    parser.add_argument("--reviewed-label-dir", type=Path, default=ROOT / "data" / "cloud_labels_reviewed")
    parser.add_argument("--class-file", type=Path, default=ROOT / "configs" / "cloud_classes.txt")
    parser.add_argument("--labelimg", type=Path, default=ROOT.parent / ".venv" / "Scripts" / "labelImg.exe")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    image, reviewed_count, total = find_resume_image(
        args.image_dir.resolve(),
        args.raw_label_dir.resolve(),
        args.reviewed_label_dir.resolve(),
    )
    if image is None:
        print(f"All images appear reviewed: {reviewed_count}/{total}")
        return 0

    print(f"Resuming LabelImg at {reviewed_count + 1}/{total}: {image.name}")
    if args.dry_run:
        return 0

    env = os.environ.copy()
    env["LABELIMG_START_IMAGE"] = str(image.resolve())
    subprocess.Popen(
        [
            str(args.labelimg.resolve()),
            str(args.image_dir.resolve()),
            str(args.class_file.resolve()),
            str(args.reviewed_label_dir.resolve()),
        ],
        cwd=str(ROOT),
        env=env,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
