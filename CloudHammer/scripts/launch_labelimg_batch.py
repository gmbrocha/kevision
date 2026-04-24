from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_manifest(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def reviewed_newer_than_raw(row: dict, tolerance_seconds: float = 1.0) -> bool:
    label_path = Path(row["label_path"])
    api_label_path = Path(row["api_label_path"])
    if not label_path.exists() or not api_label_path.exists():
        return False
    return label_path.stat().st_mtime > api_label_path.stat().st_mtime + tolerance_seconds


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch LabelImg for one review batch in manifest order.")
    parser.add_argument("batch", nargs="?", default="batch_001_priority_train")
    parser.add_argument("--batch-root", type=Path, default=ROOT / "data" / "review_batches")
    parser.add_argument("--reviewed-label-dir", type=Path, default=ROOT / "data" / "cloud_labels_reviewed")
    parser.add_argument("--class-file", type=Path, default=ROOT / "configs" / "cloud_classes.txt")
    parser.add_argument("--labelimg", type=Path, default=ROOT.parent / ".venv" / "Scripts" / "labelImg.exe")
    parser.add_argument("--start-first", action="store_true", help="Open the first batch image instead of resuming.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    batch_dir = (args.batch_root / args.batch).resolve()
    manifest_path = batch_dir / "manifest.jsonl"
    image_list_path = batch_dir / "images.txt"
    rows = read_manifest(manifest_path)
    if not rows:
        raise RuntimeError(f"No rows found in {manifest_path}")

    start_row = rows[0]
    if not args.start_first:
        for row in rows:
            if not reviewed_newer_than_raw(row):
                start_row = row
                break

    start_image = Path(start_row["image_path"]).resolve()
    print(f"Launching LabelImg for {args.batch}: {len(rows)} images")
    print(f"Start image: {start_image.name}")
    if args.dry_run:
        return 0

    env = os.environ.copy()
    env["LABELIMG_IMAGE_LIST"] = str(image_list_path.resolve())
    env["LABELIMG_START_IMAGE"] = str(start_image)
    subprocess.Popen(
        [
            str(args.labelimg.resolve()),
            str(Path(rows[0]["image_path"]).resolve().parent),
            str(args.class_file.resolve()),
            str(args.reviewed_label_dir.resolve()),
        ],
        cwd=str(ROOT),
        env=env,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
