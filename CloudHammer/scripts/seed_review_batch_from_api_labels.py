from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed a review batch's LabelImg labels from API labels without marking them human-reviewed."
    )
    parser.add_argument("batch", nargs="?", default="small_corpus_expansion_20260502")
    parser.add_argument("--batch-root", type=Path, default=ROOT / "data" / "review_batches")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    manifest_path = args.batch_root / args.batch / "manifest.jsonl"
    rows = list(read_jsonl(manifest_path))
    copied = skipped_existing = missing_api = 0
    for row in rows:
        api_label = Path(str(row.get("api_label_path") or ""))
        review_label = Path(str(row.get("label_path") or ""))
        if not api_label.exists():
            missing_api += 1
            continue
        if review_label.exists() and not args.overwrite:
            skipped_existing += 1
            continue
        review_label.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(api_label, review_label)
        copied += 1

    summary = {
        "batch": args.batch,
        "manifest": str(manifest_path),
        "rows": len(rows),
        "copied": copied,
        "skipped_existing": skipped_existing,
        "missing_api": missing_api,
        "timestamp_policy": "copy2_preserves_api_mtime_so_seed_labels_are_not_human_reviewed",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
