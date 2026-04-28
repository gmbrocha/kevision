from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_image_list(path: Path) -> list[Path]:
    images: list[Path] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            images.append(Path(line))
    return images


def review_marker(label_dir: Path, image_path: Path) -> Path:
    return label_dir / f"{image_path.stem}.review.json"


def duplicate_marker(label_dir: Path, image_path: Path) -> Path:
    return label_dir / f"{image_path.stem}.duplicate.json"


def is_queue_item_complete(label_dir: Path, image_path: Path, respect_duplicate_skips: bool = False) -> bool:
    if review_marker(label_dir, image_path).exists():
        return True
    return respect_duplicate_skips and duplicate_marker(label_dir, image_path).exists()


def first_unreviewed_index(images: list[Path], label_dir: Path, respect_duplicate_skips: bool = False) -> int | None:
    for index, image_path in enumerate(images):
        if not is_queue_item_complete(label_dir, image_path, respect_duplicate_skips):
            return index
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch LabelImg for the random GPT review queue.")
    parser.add_argument("--queue-dir", type=Path, default=ROOT / "data" / "temp_random_gpt_review_queue")
    parser.add_argument("--class-file", type=Path, default=ROOT / "configs" / "cloud_classes.txt")
    parser.add_argument("--labelimg", type=Path, default=ROOT.parent / ".venv" / "Scripts" / "labelImg.exe")
    parser.add_argument("--log-dir", type=Path, help="Directory for LabelImg stdout/stderr and launch metadata.")
    parser.add_argument("--start-first", action="store_true", help="Open the first queue image instead of resuming.")
    parser.add_argument("--start-index", type=int, help="Open a 1-based item number from images.txt.")
    parser.add_argument(
        "--respect-duplicate-skips",
        action="store_true",
        help="Treat .duplicate.json markers as completed items when resuming. Default is to ignore them.",
    )
    parser.add_argument("--qt-debug-plugins", action="store_true", help="Enable verbose Qt plugin diagnostics in stderr.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    queue_dir = args.queue_dir.resolve()
    image_dir = queue_dir / "images"
    label_dir = queue_dir / "labels"
    image_list = queue_dir / "images.txt"
    if not image_dir.exists():
        raise RuntimeError(f"Image directory not found: {image_dir}")
    if not label_dir.exists():
        raise RuntimeError(f"Label directory not found: {label_dir}")
    if not image_list.exists():
        raise RuntimeError(f"Image list not found: {image_list}")

    images = read_image_list(image_list)
    if not images:
        raise RuntimeError(f"No images found in {image_list}")

    start_index = 0
    if args.start_index is not None:
        if args.start_index < 1 or args.start_index > len(images):
            raise RuntimeError(f"--start-index must be between 1 and {len(images)}")
        start_index = args.start_index - 1
    elif not args.start_first:
        next_index = first_unreviewed_index(images, label_dir, args.respect_duplicate_skips)
        if next_index is None:
            print(f"All queue images appear reviewed: {len(images)}/{len(images)}")
            return 0
        start_index = next_index

    launch_images = images[start_index:]
    first_image = launch_images[0]
    launch_image_list = image_list
    if start_index:
        launch_image_list = queue_dir / f"images_from_{start_index + 1:03d}.txt"

    log_dir = (args.log_dir.resolve() if args.log_dir else queue_dir / "labelimg_logs")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stdout_path = log_dir / f"labelimg_{timestamp}.stdout.log"
    stderr_path = log_dir / f"labelimg_{timestamp}.stderr.log"
    metadata_path = log_dir / f"labelimg_{timestamp}.launch.json"

    print(f"Launching LabelImg queue: {queue_dir}")
    reviewed_count = sum(1 for image_path in images if review_marker(label_dir, image_path).exists())
    duplicate_count = sum(1 for image_path in images if duplicate_marker(label_dir, image_path).exists())
    print(f"Images: {len(images)}")
    print(f"Reviewed markers: {reviewed_count}")
    duplicate_mode = "respected" if args.respect_duplicate_skips else "ignored"
    print(f"Duplicate skip markers: {duplicate_count} ({duplicate_mode} for resume)")
    print(f"Start item: {start_index + 1}/{len(images)}")
    print(f"Start image: {Path(first_image).name}")
    print(f"Launch image list: {launch_image_list}")
    print(f"Saving labels to: {label_dir}")
    print(f"Logs: {log_dir}")
    if args.dry_run:
        return 0

    log_dir.mkdir(parents=True, exist_ok=True)
    if start_index:
        launch_image_list.write_text("\n".join(str(path) for path in launch_images) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env["LABELIMG_IMAGE_LIST"] = str(launch_image_list.resolve())
    env["LABELIMG_START_IMAGE"] = str(first_image)
    env["PYTHONFAULTHANDLER"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    if args.qt_debug_plugins:
        env["QT_DEBUG_PLUGINS"] = "1"

    command = [
        str(args.labelimg.resolve()),
        str(image_dir),
        str(args.class_file.resolve()),
        str(label_dir),
    ]
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
    )
    metadata = {
        "launched_at": datetime.now().isoformat(timespec="seconds"),
        "pid": process.pid,
        "queue_dir": str(queue_dir),
        "image_dir": str(image_dir),
        "label_dir": str(label_dir),
        "class_file": str(args.class_file.resolve()),
        "labelimg": str(args.labelimg.resolve()),
        "command": command,
        "cwd": str(ROOT),
        "total_images": len(images),
        "start_index": start_index + 1,
        "start_image": str(first_image),
        "launch_image_list": str(launch_image_list.resolve()),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "env": {
            "LABELIMG_IMAGE_LIST": env["LABELIMG_IMAGE_LIST"],
            "LABELIMG_START_IMAGE": env["LABELIMG_START_IMAGE"],
            "PYTHONFAULTHANDLER": env["PYTHONFAULTHANDLER"],
            "PYTHONUNBUFFERED": env["PYTHONUNBUFFERED"],
            "QT_DEBUG_PLUGINS": env.get("QT_DEBUG_PLUGINS", ""),
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"LabelImg PID: {process.pid}")
    print(f"Launch metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
