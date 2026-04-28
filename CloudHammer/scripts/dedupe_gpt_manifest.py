from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl, write_jsonl
from cloudhammer.prelabel.manifest_dedupe import dedupe_manifest_rows, exclusion_row, summarize_dedupe


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_output(path: Path | None, overwrite: bool) -> None:
    if path is not None and path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass --overwrite to replace it")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deduplicate a pre-GPT crop manifest by same-page crop geometry. "
            "This does not read human review or duplicate-skip markers."
        )
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-manifest", type=Path, help="Write kept rows here.")
    parser.add_argument("--excluded-manifest", type=Path, help="Write excluded duplicate rows here.")
    parser.add_argument("--summary-json", type=Path, help="Write summary JSON here.")
    parser.add_argument("--iou-threshold", type=float, default=0.30)
    parser.add_argument("--overlap-smaller-threshold", type=float, default=0.65)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    check_output(args.output_manifest, args.overwrite)
    check_output(args.excluded_manifest, args.overwrite)
    check_output(args.summary_json, args.overwrite)

    rows = list(read_jsonl(args.manifest))
    decisions = dedupe_manifest_rows(
        rows,
        iou_threshold=args.iou_threshold,
        overlap_smaller_threshold=args.overlap_smaller_threshold,
    )
    kept_rows = [decision.row for decision in decisions if decision.kept]
    excluded_rows = [exclusion_row(decision) for decision in decisions if not decision.kept]
    summary = summarize_dedupe(decisions)
    summary["manifest"] = str(args.manifest.resolve())
    summary["iou_threshold"] = args.iou_threshold
    summary["overlap_smaller_threshold"] = args.overlap_smaller_threshold
    if args.output_manifest:
        summary["output_manifest"] = str(args.output_manifest.resolve())
    if args.excluded_manifest:
        summary["excluded_manifest"] = str(args.excluded_manifest.resolve())

    if args.output_manifest:
        args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(args.output_manifest, kept_rows)
    if args.excluded_manifest:
        args.excluded_manifest.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(args.excluded_manifest, excluded_rows)
    if args.summary_json:
        write_json(args.summary_json, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
