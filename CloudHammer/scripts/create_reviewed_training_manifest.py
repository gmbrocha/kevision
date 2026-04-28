from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl, write_jsonl


ROOT = Path(__file__).resolve().parents[1]


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


def is_reviewed_newer_than_raw(reviewed_label: Path, api_label: Path) -> bool:
    if not reviewed_label.exists() or not api_label.exists():
        return False
    return reviewed_label.stat().st_mtime > api_label.stat().st_mtime + 1.0


def has_review_marker(reviewed_label: Path) -> bool:
    return reviewed_label.with_suffix(".review.json").exists()


def is_reviewed(reviewed_label: Path, api_label: Path) -> bool:
    return is_reviewed_newer_than_raw(reviewed_label, api_label) or has_review_marker(reviewed_label)


def make_training_rows(batch_manifest: Path, val_fraction: float, seed: int) -> list[dict]:
    rows = []
    manifest_rows = list(read_jsonl(batch_manifest))
    marker_mode = any(has_review_marker(resolve_cloudhammer_path(Path(row["label_path"]))) for row in manifest_rows)
    for row in manifest_rows:
        image_path = resolve_cloudhammer_path(Path(row["image_path"]))
        label_path = resolve_cloudhammer_path(Path(row["label_path"]))
        api_label_path = resolve_cloudhammer_path(Path(row["api_label_path"]))
        if not image_path.exists():
            continue
        reviewed = has_review_marker(label_path) if marker_mode else is_reviewed(label_path, api_label_path)
        if not reviewed:
            continue
        rows.append(
            {
                "cloud_roi_id": row["cloud_roi_id"],
                "roi_image_path": str(image_path),
                "label_path": str(label_path),
                "is_excluded": False,
                "split": "train",
                "source_batch": row.get("source_batch", batch_manifest.parent.name),
                "reason_for_selection": row.get("reason_for_selection", ""),
                "visual_type": row.get("visual_type", ""),
                "api_confidence": row.get("api_confidence", ""),
                "has_cloud": row.get("has_cloud", ""),
            }
        )

    rng = random.Random(seed)
    rng.shuffle(rows)
    val_count = max(1, round(len(rows) * val_fraction)) if rows else 0
    for index, row in enumerate(rows):
        row["split"] = "val" if index < val_count else "train"
    rows.sort(key=lambda item: (item["split"], item["cloud_roi_id"]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a YOLO training manifest from reviewed batch labels.")
    parser.add_argument(
        "--batch-manifest",
        type=Path,
        default=ROOT / "data" / "review_batches" / "batch_001_priority_train" / "manifest.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "manifests" / "reviewed_batch_001_priority_train.jsonl",
    )
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=20260424)
    args = parser.parse_args()

    rows = make_training_rows(args.batch_manifest, args.val_fraction, args.seed)
    write_jsonl(args.output, rows)

    counts = {"train": 0, "val": 0, "test": 0}
    for row in rows:
        counts[row["split"]] = counts.get(row["split"], 0) + 1
    print(json.dumps({"output": str(args.output), "total": len(rows), "splits": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
