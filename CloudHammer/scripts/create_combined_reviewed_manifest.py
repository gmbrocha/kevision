from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.data.splits import assign_split
from cloudhammer.manifests import read_jsonl, write_jsonl


ROOT = Path(__file__).resolve().parents[1]


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate.resolve()
    parts = candidate.parts
    for index, part in enumerate(parts):
        if part.lower() == "cloudhammer":
            relocated = ROOT.joinpath(*parts[index + 1 :])
            if relocated.exists():
                return relocated.resolve()
    return candidate


def label_box_count(label_path: Path) -> int:
    if not label_path.exists():
        return 0
    return sum(1 for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip())


def has_review_marker(label_path: Path) -> bool:
    return label_path.with_suffix(".review.json").exists()


def reviewed_newer_than_raw(label_path: Path, raw_label_path: Path, tolerance_seconds: float = 1.0) -> bool:
    if not label_path.exists() or not raw_label_path.exists():
        return False
    return label_path.stat().st_mtime > raw_label_path.stat().st_mtime + tolerance_seconds


def base_training_row(row: dict[str, Any], source_manifest: Path) -> dict[str, Any] | None:
    image_path = resolve_path(row.get("roi_image_path") or row.get("image_path") or "")
    label_path = resolve_path(row.get("label_path") or "")
    if not image_path.exists() or not label_path.exists():
        return None
    out = dict(row)
    out["cloud_roi_id"] = str(row.get("cloud_roi_id") or image_path.stem)
    out["roi_image_path"] = str(image_path)
    out["label_path"] = str(label_path)
    out["is_excluded"] = bool(row.get("is_excluded", False))
    out["split"] = row.get("split") if row.get("split") in {"train", "val", "test"} else "train"
    out.setdefault("source_batch", source_manifest.stem)
    out.setdefault("training_source", "base_manifest")
    out["reviewed_box_count"] = label_box_count(label_path)
    out["has_cloud"] = out["reviewed_box_count"] > 0
    return out


def queue_training_row(row: dict[str, Any], queue_dir: Path, val_fraction: float) -> dict[str, Any] | None:
    image_path = resolve_path(row.get("local_image_path") or "")
    label_path = resolve_path(row.get("local_label_path") or "")
    if not image_path.exists() or not label_path.exists():
        return None
    raw_label_path = resolve_path(row.get("api_label_path") or "")
    if not has_review_marker(label_path) and not reviewed_newer_than_raw(label_path, raw_label_path):
        return None

    try:
        page_index = int(row.get("page_index") or 0)
    except (TypeError, ValueError):
        page_index = 0
    pdf_path = str(row.get("pdf_path") or "")
    split = assign_split(pdf_path, page_index, val_fraction=val_fraction, test_fraction=0.0)
    box_count = label_box_count(label_path)

    return {
        "cloud_roi_id": str(row.get("cloud_roi_id") or image_path.stem),
        "roi_image_path": str(image_path),
        "label_path": str(label_path),
        "is_excluded": False,
        "split": split,
        "source_batch": queue_dir.parent.name,
        "source_queue": queue_dir.name,
        "training_source": "review_queue",
        "reason_for_selection": row.get("review_bucket", ""),
        "review_bucket": row.get("review_bucket", ""),
        "accept_reason": row.get("accept_reason", ""),
        "accept_reason_label": row.get("accept_reason_label", ""),
        "review_tags": row.get("review_tags", ""),
        "requires_precise_label": row.get("requires_precise_label", False),
        "candidate_source": row.get("candidate_source", ""),
        "revision": row.get("revision", ""),
        "pdf_path": pdf_path,
        "page_index": row.get("page_index", ""),
        "page_number": row.get("page_number", ""),
        "sheet_id": row.get("sheet_id", ""),
        "sheet_title": row.get("sheet_title", ""),
        "visual_type": row.get("visual_types", ""),
        "api_confidence": row.get("max_confidence", ""),
        "reviewed_box_count": box_count,
        "has_cloud": box_count > 0,
    }


def reviewed_rows_from_queue_root(queue_root: Path, val_fraction: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    queue_dirs = [queue_root] if (queue_root / "manifest.jsonl").exists() else sorted(path for path in queue_root.iterdir() if path.is_dir())
    for queue_dir in queue_dirs:
        manifest = queue_dir / "manifest.jsonl"
        if not manifest.exists():
            continue
        for row in read_jsonl(manifest):
            training_row = queue_training_row(row, queue_dir, val_fraction)
            if training_row is not None:
                rows.append(training_row)
    return rows


def summarize(rows: list[dict[str, Any]], skipped_duplicate_ids: int) -> dict[str, Any]:
    return {
        "total_rows": len(rows),
        "splits": dict(Counter(str(row.get("split")) for row in rows)),
        "training_source": dict(Counter(str(row.get("training_source")) for row in rows)),
        "source_queue": dict(Counter(str(row.get("source_queue") or "") for row in rows if row.get("source_queue"))),
        "has_cloud": dict(Counter(str(bool(row.get("has_cloud"))) for row in rows)),
        "box_count": dict(Counter(str(row.get("reviewed_box_count", 0)) for row in rows)),
        "skipped_duplicate_ids": skipped_duplicate_ids,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Combine an existing reviewed training manifest with reviewed labels from isolated review queues."
    )
    parser.add_argument("--base-manifest", type=Path, action="append", default=[])
    parser.add_argument("--queue-root", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not 0.0 <= args.val_fraction < 1.0:
        parser.error("--val-fraction must be at least 0 and less than 1")
    if args.output.exists() and not args.overwrite:
        raise FileExistsError(f"{args.output} already exists; pass --overwrite to replace it")
    if args.summary_json and args.summary_json.exists() and not args.overwrite:
        raise FileExistsError(f"{args.summary_json} already exists; pass --overwrite to replace it")

    rows_by_id: dict[str, dict[str, Any]] = {}
    skipped_duplicate_ids = 0

    for manifest in args.base_manifest:
        for row in read_jsonl(manifest):
            training_row = base_training_row(row, manifest)
            if training_row is None:
                continue
            row_id = str(training_row["cloud_roi_id"])
            if row_id in rows_by_id:
                skipped_duplicate_ids += 1
                continue
            rows_by_id[row_id] = training_row

    for queue_root in args.queue_root:
        for training_row in reviewed_rows_from_queue_root(queue_root, args.val_fraction):
            row_id = str(training_row["cloud_roi_id"])
            if row_id in rows_by_id:
                skipped_duplicate_ids += 1
                continue
            rows_by_id[row_id] = training_row

    rows = sorted(rows_by_id.values(), key=lambda item: (str(item.get("split")), str(item.get("source_queue", "")), str(item["cloud_roi_id"])))
    write_jsonl(args.output, rows)
    summary = summarize(rows, skipped_duplicate_ids)
    summary["output"] = str(args.output.resolve())
    summary["base_manifests"] = [str(path.resolve()) for path in args.base_manifest]
    summary["queue_roots"] = [str(path.resolve()) for path in args.queue_root]
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
