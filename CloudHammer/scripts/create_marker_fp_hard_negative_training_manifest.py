from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.data.splits import assign_split
from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs" / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428"
DEFAULT_INPUT = DEFAULT_RUN / "hard_negatives_v1" / "hard_negative_candidates.jsonl"
DEFAULT_LABEL_DIR = ROOT / "data" / "cloud_labels_reviewed_marker_fp_hard_negatives"
DEFAULT_OUTPUT = ROOT / "data" / "manifests" / "marker_fp_hard_negatives_20260502.jsonl"
DEFAULT_SUMMARY = ROOT / "data" / "manifests" / "marker_fp_hard_negatives_20260502.summary.json"


def resolve_cloudhammer_path(value: str | Path | None) -> Path:
    if value is None or str(value) == "":
        return Path("")
    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve()
    parts = candidate.parts
    for index, part in enumerate(parts):
        if part.lower() == "cloudhammer":
            relocated = ROOT.joinpath(*parts[index + 1 :])
            if relocated.exists():
                return relocated.resolve()
    return candidate


def safe_id(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "unknown"


def page_index_for(row: dict[str, Any]) -> int:
    if row.get("page_index") not in {None, ""}:
        return int(row["page_index"])
    if row.get("page_number") not in {None, ""}:
        return max(0, int(row["page_number"]) - 1)
    return 0


def write_empty_label(label_path: Path, overwrite: bool, review_source: str) -> None:
    label_path.parent.mkdir(parents=True, exist_ok=True)
    if label_path.exists() and label_path.read_text(encoding="utf-8").strip() and not overwrite:
        raise FileExistsError(f"Refusing to replace non-empty label file without --overwrite-labels: {label_path}")
    label_path.write_text("", encoding="utf-8")
    marker_path = label_path.with_suffix(".review.json")
    if not marker_path.exists() or overwrite:
        marker_path.write_text(
            json.dumps(
                {
                    "reviewed": True,
                    "status": "false_positive",
                    "source": review_source,
                    "cloud_boxes": 0,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def training_row(
    row: dict[str, Any],
    label_dir: Path,
    val_fraction: float,
    overwrite_labels: bool,
    source_name: str,
    id_prefix: str,
    training_source: str,
    candidate_source: str,
) -> dict[str, Any] | None:
    image_path = resolve_cloudhammer_path(row.get("crop_image_path"))
    if not image_path.exists():
        return None

    candidate_id = safe_id(row.get("candidate_id") or image_path.stem)
    cloud_roi_id = f"{safe_id(id_prefix)}_{candidate_id}"
    label_path = label_dir / f"{cloud_roi_id}.txt"
    write_empty_label(label_path, overwrite=overwrite_labels, review_source=training_source)

    pdf_path = str(row.get("pdf_path") or "")
    page_index = page_index_for(row)
    split = assign_split(pdf_path, page_index, val_fraction=val_fraction, test_fraction=0.0)

    return {
        "cloud_roi_id": cloud_roi_id,
        "roi_image_path": str(image_path),
        "label_path": str(label_path.resolve()),
        "is_excluded": False,
        "split": split,
        "source_batch": source_name,
        "training_source": training_source,
        "reason_for_selection": row.get("false_positive_reason") or "generic_false_positive",
        "false_positive_reason": row.get("false_positive_reason") or "generic_false_positive",
        "false_positive_reason_label": row.get("false_positive_reason_label") or "False Positive",
        "review_tags": row.get("review_tags") or ["hard_negative", "generic_false_positive"],
        "has_cloud": False,
        "reviewed_box_count": 0,
        "candidate_id": row.get("candidate_id"),
        "candidate_source": row.get("hard_negative_source") or candidate_source,
        "pdf_path": pdf_path,
        "pdf_stem": row.get("pdf_stem"),
        "page_index": page_index,
        "page_number": row.get("page_number"),
        "whole_cloud_confidence": row.get("whole_cloud_confidence"),
        "marker_anchor_bucket": row.get("marker_anchor_bucket"),
        "target_digit": row.get("target_digit"),
        "matching_page_marker_count": row.get("matching_page_marker_count"),
        "matching_markers_in_crop": row.get("matching_markers_in_crop"),
        "nearest_matching_marker_bbox_distance": row.get("nearest_matching_marker_bbox_distance"),
        "nearest_matching_marker_center_distance": row.get("nearest_matching_marker_center_distance"),
    }


def summarize(rows: list[dict[str, Any]], skipped_missing_images: int, label_dir: Path) -> dict[str, Any]:
    return {
        "schema": "cloudhammer.false_positive_hard_negative_training_manifest.v1",
        "total_rows": len(rows),
        "splits": dict(Counter(str(row.get("split")) for row in rows)),
        "false_positive_reason": dict(Counter(str(row.get("false_positive_reason")) for row in rows)),
        "marker_anchor_bucket": dict(Counter(str(row.get("marker_anchor_bucket")) for row in rows)),
        "skipped_missing_images": skipped_missing_images,
        "label_dir": str(label_dir.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert reviewed marker-anchor false positives into empty-label hard-negative training rows."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--source-name", default="marker_fp_hard_negatives_20260502")
    parser.add_argument("--id-prefix", default="marker_fp_hn")
    parser.add_argument("--training-source", default="marker_fp_hard_negative")
    parser.add_argument("--candidate-source", default="marker_fp_review")
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--overwrite-labels", action="store_true")
    args = parser.parse_args()

    if not 0.0 <= args.val_fraction < 1.0:
        parser.error("--val-fraction must be at least 0 and less than 1")
    if args.output.exists() and not args.overwrite:
        raise FileExistsError(f"{args.output} already exists; pass --overwrite to replace it")
    if args.summary_json.exists() and not args.overwrite:
        raise FileExistsError(f"{args.summary_json} already exists; pass --overwrite to replace it")

    input_path = args.input.resolve()
    label_dir = args.label_dir.resolve()
    rows: list[dict[str, Any]] = []
    skipped_missing_images = 0
    for source_row in read_jsonl(input_path):
        row = training_row(
            source_row,
            label_dir,
            args.val_fraction,
            args.overwrite_labels,
            args.source_name,
            args.id_prefix,
            args.training_source,
            args.candidate_source,
        )
        if row is None:
            skipped_missing_images += 1
            continue
        rows.append(row)

    rows.sort(key=lambda item: (str(item.get("split")), str(item["cloud_roi_id"])))
    write_jsonl(args.output, rows)
    summary = summarize(rows, skipped_missing_images, label_dir)
    summary["input"] = str(input_path)
    summary["output"] = str(args.output.resolve())
    summary["source_name"] = args.source_name
    summary["id_prefix"] = args.id_prefix
    summary["training_source"] = args.training_source
    summary["candidate_source"] = args.candidate_source
    write_json(args.summary_json, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
