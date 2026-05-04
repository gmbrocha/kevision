from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEWED_LABEL_DIR = ROOT / "data" / "cloud_labels_reviewed"


def resolve_cloudhammer_path(path: Path) -> Path:
    if path.exists():
        return path.resolve()
    parts = path.parts
    for index, part in enumerate(parts):
        if part.lower() == "cloudhammer":
            relocated = ROOT.joinpath(*parts[index + 1 :])
            if relocated.exists():
                return relocated.resolve()
    return path


def read_manifest(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def reviewed_newer_than_raw(row: dict, tolerance_seconds: float = 1.0) -> bool:
    label_path = resolve_cloudhammer_path(Path(row["label_path"]))
    api_label_path = resolve_cloudhammer_path(Path(row["api_label_path"]))
    if not label_path.exists() or not api_label_path.exists():
        return False
    return label_path.stat().st_mtime > api_label_path.stat().st_mtime + tolerance_seconds


def has_review_marker(row: dict) -> bool:
    label_path = resolve_cloudhammer_path(Path(row["label_path"]))
    marker_path = label_path.with_suffix(".review.json")
    return marker_path.exists()


def is_reviewed(row: dict) -> bool:
    return reviewed_newer_than_raw(row) or has_review_marker(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch LabelImg for one review batch in manifest order.")
    parser.add_argument("batch", nargs="?", default="batch_001_priority_train")
    parser.add_argument("--batch-root", type=Path, default=ROOT / "data" / "review_batches")
    parser.add_argument("--reviewed-label-dir", type=Path, default=DEFAULT_REVIEWED_LABEL_DIR)
    parser.add_argument("--class-file", type=Path, default=ROOT / "configs" / "cloud_classes.txt")
    parser.add_argument("--labelimg", type=Path, default=ROOT.parent / ".venv" / "Scripts" / "labelImg.exe")
    parser.add_argument("--start-first", action="store_true", help="Open the first batch image instead of resuming.")
    parser.add_argument("--start-index", type=int, help="Open a 1-based item number from the batch manifest.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    batch_dir = (args.batch_root / args.batch).resolve()
    manifest_path = batch_dir / "manifest.jsonl"
    rows = read_manifest(manifest_path)
    if not rows:
        raise RuntimeError(f"No rows found in {manifest_path}")

    label_dirs = {resolve_cloudhammer_path(Path(row["label_path"])).parent for row in rows if row.get("label_path")}
    reviewed_label_dir = args.reviewed_label_dir.resolve()
    if args.reviewed_label_dir == DEFAULT_REVIEWED_LABEL_DIR and len(label_dirs) == 1:
        reviewed_label_dir = next(iter(label_dirs)).resolve()

    resolved_images = [resolve_cloudhammer_path(Path(row["image_path"])) for row in rows]
    marker_mode = any(has_review_marker(row) for row in rows)

    start_index = 0
    start_row = rows[0]
    if args.start_index is not None:
        if args.start_index < 1 or args.start_index > len(rows):
            raise RuntimeError(f"--start-index must be between 1 and {len(rows)}")
        start_index = args.start_index - 1
        start_row = rows[start_index]
    elif not args.start_first:
        for row in rows:
            reviewed = has_review_marker(row) if marker_mode else is_reviewed(row)
            if not reviewed:
                start_index = rows.index(row)
                start_row = row
                break

    if args.start_index is not None:
        image_list_path = batch_dir / f"images_from_{start_index + 1:03d}.txt"
        launch_images = resolved_images[start_index:]
    else:
        image_list_path = batch_dir / "images_resolved.txt"
        launch_images = resolved_images
    image_list_path.write_text("\n".join(str(path) for path in launch_images) + "\n", encoding="utf-8")

    start_image = resolve_cloudhammer_path(Path(start_row["image_path"]))
    print(f"Launching LabelImg for {args.batch}: {len(rows)} images")
    print(f"Start item: {start_index + 1}")
    print(f"Start image: {start_image.name}")
    print(f"Label dir: {reviewed_label_dir}")
    if args.start_index is not None:
        print(f"Sliced review list: {len(launch_images)} images")
    if args.dry_run:
        return 0

    env = os.environ.copy()
    env["LABELIMG_IMAGE_LIST"] = str(image_list_path.resolve())
    env["LABELIMG_START_IMAGE"] = str(start_image)
    subprocess.Popen(
        [
            str(args.labelimg.resolve()),
            str(launch_images[0].parent),
            str(args.class_file.resolve()),
            str(reviewed_label_dir),
        ],
        cwd=str(ROOT),
        env=env,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
