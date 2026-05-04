from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT
    / "runs"
    / "whole_cloud_eval_marker_fp_hn_20260502"
    / "review_analysis"
    / "tagged_accepted_candidates.jsonl"
)
DEFAULT_BATCH_DIR = ROOT / "data" / "review_batches" / "accept_contamination_precise_labels_20260502"
DEFAULT_RAW_LABEL_DIR = ROOT / "data" / "api_cloud_labels_accept_contamination_20260502"
DEFAULT_REVIEWED_LABEL_DIR = ROOT / "data" / "cloud_labels_reviewed_accept_contamination_20260502"


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


def write_empty_raw_label(path: Path, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8").strip() and not overwrite:
        raise FileExistsError(f"Refusing to replace non-empty raw label without --overwrite-labels: {path}")
    if overwrite or not path.exists():
        path.write_text("", encoding="utf-8")


def review_row(
    source_row: dict[str, Any],
    raw_label_dir: Path,
    reviewed_label_dir: Path,
    overwrite_labels: bool,
) -> dict[str, Any] | None:
    image_path = resolve_cloudhammer_path(source_row.get("crop_image_path"))
    if not image_path.exists():
        return None

    candidate_id = safe_id(source_row.get("candidate_id") or image_path.stem)
    cloud_roi_id = f"accept_contamination_{candidate_id}"
    raw_label_path = raw_label_dir / f"{image_path.stem}.txt"
    reviewed_label_path = reviewed_label_dir / f"{image_path.stem}.txt"
    write_empty_raw_label(raw_label_path, overwrite=overwrite_labels)
    reviewed_label_path.parent.mkdir(parents=True, exist_ok=True)

    page_index = page_index_for(source_row)
    return {
        "cloud_roi_id": cloud_roi_id,
        "image_path": str(image_path),
        "local_image_path": str(image_path),
        "label_path": str(reviewed_label_path.resolve()),
        "local_label_path": str(reviewed_label_path.resolve()),
        "api_label_path": str(raw_label_path.resolve()),
        "review_bucket": "accept_contamination_precise_label",
        "reason_for_selection": source_row.get("accept_reason") or "accepted_crop_with_non_cloud_contamination",
        "source_batch": "whole_cloud_eval_marker_fp_hn_20260502",
        "candidate_source": "tagged_accepted_candidate",
        "accept_reason": source_row.get("accept_reason"),
        "accept_reason_label": source_row.get("accept_reason_label"),
        "review_tags": source_row.get("review_tags") or [],
        "review_note": source_row.get("review_note"),
        "has_cloud": True,
        "accepted_box_count": "",
        "requires_precise_label": True,
        "training_instruction": (
            "Draw/save only true cloud_motif boxes. Leave door swing arcs, plan geometry arcs, "
            "fixture circles, text curves, seals, and other non-cloud geometry unlabeled."
        ),
        "candidate_id": source_row.get("candidate_id"),
        "pdf_path": source_row.get("pdf_path"),
        "pdf_stem": source_row.get("pdf_stem"),
        "page_index": page_index,
        "page_number": source_row.get("page_number"),
        "bbox_page_xyxy": source_row.get("bbox_page_xyxy"),
        "crop_box_page_xyxy": source_row.get("crop_box_page_xyxy"),
        "whole_cloud_confidence": source_row.get("whole_cloud_confidence"),
        "confidence_tier": source_row.get("confidence_tier"),
        "size_bucket": source_row.get("size_bucket"),
        "member_count": source_row.get("member_count"),
    }


def summarize(rows: list[dict[str, Any]], skipped_missing_images: int) -> dict[str, Any]:
    return {
        "schema": "cloudhammer.accept_contamination_precise_label_review_batch.v1",
        "total_rows": len(rows),
        "accept_reason": dict(Counter(str(row.get("accept_reason")) for row in rows)),
        "skipped_missing_images": skipped_missing_images,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a precise-label review batch from accepted crops tagged with non-cloud contamination."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    parser.add_argument("--raw-label-dir", type=Path, default=DEFAULT_RAW_LABEL_DIR)
    parser.add_argument("--reviewed-label-dir", type=Path, default=DEFAULT_REVIEWED_LABEL_DIR)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--overwrite-labels", action="store_true")
    args = parser.parse_args()

    input_path = args.input.resolve()
    batch_dir = args.batch_dir.resolve()
    manifest_path = batch_dir / "manifest.jsonl"
    summary_path = batch_dir / "summary.json"
    if manifest_path.exists() and not args.overwrite:
        raise FileExistsError(f"{manifest_path} already exists; pass --overwrite to replace it")
    if summary_path.exists() and not args.overwrite:
        raise FileExistsError(f"{summary_path} already exists; pass --overwrite to replace it")

    rows: list[dict[str, Any]] = []
    skipped_missing_images = 0
    for source_row in read_jsonl(input_path):
        row = review_row(
            source_row,
            args.raw_label_dir.resolve(),
            args.reviewed_label_dir.resolve(),
            args.overwrite_labels,
        )
        if row is None:
            skipped_missing_images += 1
            continue
        rows.append(row)

    rows.sort(key=lambda item: str(item["cloud_roi_id"]))
    write_jsonl(manifest_path, rows)
    summary = summarize(rows, skipped_missing_images)
    summary["input"] = str(input_path)
    summary["manifest"] = str(manifest_path)
    summary["raw_label_dir"] = str(args.raw_label_dir.resolve())
    summary["reviewed_label_dir"] = str(args.reviewed_label_dir.resolve())
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
