from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.data.splits import stable_fraction
from cloudhammer.data.source_control import (
    DEFAULT_QUASI_HOLDOUT_REVISIONS,
    audit_sources,
    dedupe_rows_by_id,
    source_capped_rows,
    source_control_fields,
    source_key_for_row,
)
from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]


def _read_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(read_jsonl(path))
    return rows


def _assign_source_disjoint_splits(
    rows: list[dict[str, Any]],
    *,
    val_fraction: float,
    quasi_holdout_revisions: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    holdout: list[dict[str, Any]] = []
    usable: list[dict[str, Any]] = []
    for row in rows:
        key = source_key_for_row(row)
        if key.revision_group in quasi_holdout_revisions:
            holdout.append(row)
        else:
            usable.append(row)

    sources = sorted({source_key_for_row(row).source_id for row in usable})
    val_count = max(1, round(len(sources) * val_fraction)) if sources else 0
    val_sources = set(sorted(sources, key=stable_fraction)[:val_count])

    assigned: list[dict[str, Any]] = []
    for row in usable:
        key = source_key_for_row(row)
        split = "val" if key.source_id in val_sources else "train"
        assigned.append(
            {
                **row,
                **source_control_fields(row),
                "split": split,
                "source_control_split": split,
                "source_control_policy": "source_disjoint_v1",
            }
        )

    holdout_rows = [
        {
            **row,
            **source_control_fields(row),
            "split": "quasi_holdout",
            "source_control_split": "quasi_holdout",
            "source_control_policy": "source_disjoint_v1",
        }
        for row in holdout
    ]
    return assigned, holdout_rows


def _summary(rows: list[dict[str, Any]], holdout: list[dict[str, Any]], dropped_by_cap: int) -> dict[str, Any]:
    audit = audit_sources(rows)
    split_counts = Counter(str(row.get("split") or "unknown") for row in rows)
    source_counts = Counter(str(row.get("source_id") or "unknown") for row in rows)
    revision_counts = Counter(str(row.get("revision_group") or "unknown") for row in rows)
    return {
        "schema": "cloudhammer.source_controlled_split_summary.v1",
        "training_rows": len(rows),
        "quasi_holdout_rows": len(holdout),
        "dropped_by_source_caps": dropped_by_cap,
        "split_counts": dict(split_counts),
        "revision_counts": dict(revision_counts),
        "top_sources": source_counts.most_common(20),
        "mixed_split_sources": audit["mixed_split_sources"],
        "mixed_split_source_pages": audit["mixed_split_source_pages"],
        "leakage_failures": len(audit["mixed_split_sources"]) + len(audit["mixed_split_source_pages"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rewrite reviewed CloudHammer training manifests with source-controlled splits.")
    parser.add_argument(
        "--base-manifest",
        type=Path,
        action="append",
        default=[],
        help="Reviewed training manifest. Can be repeated.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "manifests" / "source_controlled_small_corpus_20260502.jsonl",
    )
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument("--quasi-output", type=Path, default=None)
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--max-rows-per-source", type=int, default=150)
    parser.add_argument("--max-rows-per-source-page", type=int, default=15)
    parser.add_argument("--quasi-holdout-revision", action="append", default=[])
    parser.add_argument("--include-quasi-holdout", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.output.exists() and not args.overwrite:
        raise RuntimeError(f"{args.output} exists; pass --overwrite to replace")
    if not 0.0 < args.val_fraction < 1.0:
        parser.error("--val-fraction must be between 0 and 1")

    base_paths = args.base_manifest or [
        ROOT / "data" / "manifests" / "reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl"
    ]
    rows = dedupe_rows_by_id(_read_rows(base_paths))
    holdout_revisions = set(args.quasi_holdout_revision) if args.quasi_holdout_revision else set(DEFAULT_QUASI_HOLDOUT_REVISIONS)
    assigned, holdout = _assign_source_disjoint_splits(
        rows,
        val_fraction=args.val_fraction,
        quasi_holdout_revisions=holdout_revisions,
    )
    capped = source_capped_rows(
        assigned,
        max_rows_per_source=args.max_rows_per_source,
        max_rows_per_source_page=args.max_rows_per_source_page,
    )
    dropped_by_cap = len(assigned) - len(capped)
    output_rows = capped + (holdout if args.include_quasi_holdout else [])
    write_jsonl(args.output, sorted(output_rows, key=lambda item: (str(item.get("split")), str(item.get("source_id")), str(item.get("cloud_roi_id")))))

    quasi_output = args.quasi_output or args.output.with_suffix(".quasi_holdout.jsonl")
    write_jsonl(quasi_output, sorted(holdout, key=lambda item: (str(item.get("revision_group")), str(item.get("cloud_roi_id")))))

    summary_path = args.summary_json or args.output.with_suffix(".summary.json")
    summary = _summary(capped, holdout, dropped_by_cap)
    summary["base_manifests"] = [str(path) for path in base_paths]
    summary["output"] = str(args.output)
    summary["quasi_output"] = str(quasi_output)
    summary["source_caps"] = {
        "max_rows_per_source": args.max_rows_per_source,
        "max_rows_per_source_page": args.max_rows_per_source_page,
    }
    write_json(summary_path, summary)

    if summary["leakage_failures"]:
        raise RuntimeError(f"source leakage remains after split rewrite: {summary['leakage_failures']} failures")
    print(json.dumps({key: summary[key] for key in ("training_rows", "quasi_holdout_rows", "split_counts", "dropped_by_source_caps")}, indent=2))
    print(f"wrote {args.output}")
    print(f"wrote {quasi_output}")
    print(f"wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
