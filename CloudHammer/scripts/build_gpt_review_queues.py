from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.prelabel.gpt_review_queue import (
    classify_for_review,
    read_jsonl,
    row_id,
    select_balanced,
    summarize_predictions,
    write_review_queue,
)


DEFAULT_QUEUE_NAMES = [
    "high_conf_positive",
    "ambiguous_positive",
    "weird_multi_faint_partial",
    "hard_negative_marker_no_cloud",
    "gpt_negative_spotcheck",
]


def validate_complete(predictions: list[dict], manifest: list[dict], allow_partial: bool) -> None:
    prediction_ids = {row_id(row) for row in predictions}
    manifest_ids = {row_id(row) for row in manifest}
    missing = manifest_ids - prediction_ids
    extra = prediction_ids - manifest_ids
    if (missing or extra) and not allow_partial:
        raise RuntimeError(
            "Predictions do not match the manifest. "
            f"missing={len(missing)} extra={len(extra)}. "
            "Wait for the API run to finish, or pass --allow-partial intentionally."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build isolated LabelImg review queues from GPT prelabel predictions. "
            "This never writes to cloud_labels_reviewed."
        )
    )
    parser.add_argument("--predictions", type=Path, required=True, help="Path to completed predictions.jsonl")
    parser.add_argument("--manifest", type=Path, required=True, help="Source queue manifest used for the GPT run")
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory to receive review queues")
    parser.add_argument("--max-per-queue", type=int, default=80)
    parser.add_argument("--seed", type=int, default=20260427)
    parser.add_argument("--allow-partial", action="store_true", help="Allow building from incomplete predictions")
    parser.add_argument(
        "--filter-to-manifest",
        action="store_true",
        help="Only include predictions whose IDs appear in --manifest. Use this for deduped or subset manifests.",
    )
    args = parser.parse_args()

    if args.max_per_queue < 1:
        parser.error("--max-per-queue must be at least 1")
    if args.output_dir.exists():
        parser.error(f"--output-dir already exists: {args.output_dir}")

    predictions = read_jsonl(args.predictions)
    manifest = read_jsonl(args.manifest)
    if args.filter_to_manifest:
        manifest_ids = {row_id(row) for row in manifest}
        predictions = [row for row in predictions if row_id(row) in manifest_ids]
    validate_complete(predictions, manifest, args.allow_partial)

    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in predictions:
        bucket = classify_for_review(row)
        if bucket == "failed":
            continue
        buckets[bucket].append(row)

    args.output_dir.mkdir(parents=True)
    queue_results = []
    for queue_name in DEFAULT_QUEUE_NAMES:
        selected = select_balanced(buckets.get(queue_name, []), args.max_per_queue, args.seed)
        result = write_review_queue(args.output_dir, queue_name, selected)
        queue_results.append(result.__dict__)

    summary = {
        "predictions": str(args.predictions.resolve()),
        "manifest": str(args.manifest.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "allow_partial": args.allow_partial,
        "filter_to_manifest": args.filter_to_manifest,
        "max_per_queue": args.max_per_queue,
        "seed": args.seed,
        "prediction_summary": summarize_predictions(predictions, manifest),
        "queues": queue_results,
    }
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
