from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VISUAL_PRIORITY = {"bold", "thin", "faint", "partial", "intersected", "unknown"}


@dataclass(frozen=True)
class BatchItem:
    cloud_roi_id: str
    image_path: Path
    api_label_path: Path
    reviewed_label_path: Path
    api_confidence: float | None
    visual_type: str
    has_cloud: bool
    accepted_box_count: int
    reason_for_selection: str
    source_batch: str
    cloud_likeness: float | None
    contains_marker: bool | None

    def jsonable(self) -> dict[str, Any]:
        return {
            "cloud_roi_id": self.cloud_roi_id,
            "image_path": str(self.image_path),
            "label_path": str(self.reviewed_label_path),
            "api_label_path": str(self.api_label_path),
            "api_confidence": self.api_confidence,
            "visual_type": self.visual_type,
            "has_cloud": self.has_cloud,
            "accepted_box_count": self.accepted_box_count,
            "reason_for_selection": self.reason_for_selection,
            "source_batch": self.source_batch,
            "cloud_likeness": self.cloud_likeness,
            "contains_marker": self.contains_marker,
        }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def resolve_predictions_path(path: Path | None) -> Path:
    candidates = []
    if path is not None:
        candidates.append(path)
    candidates.extend(
        [
            ROOT / "data" / "api_cloud_predictions_unreviewed" / "predictions.jsonl",
            ROOT / "data" / "api_cloud_predictions" / "predictions.jsonl",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError("No predictions.jsonl found in api_cloud_predictions_unreviewed or api_cloud_predictions")


def max_confidence(row: dict[str, Any]) -> float | None:
    values = [float(box.get("confidence", 0.0)) for box in row.get("accepted_boxes", []) if isinstance(box, dict)]
    return max(values) if values else None


def visual_types(row: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for box in row.get("accepted_boxes", []):
        if isinstance(box, dict):
            value = str(box.get("visual_type") or "unknown")
            out.add(value if value in VISUAL_PRIORITY else "unknown")
    return out


def primary_visual_type(types: set[str]) -> str:
    for value in ["faint", "thin", "intersected", "partial", "unknown", "bold"]:
        if value in types:
            return value
    return "none"


def image_path_for(row: dict[str, Any], image_dir: Path) -> Path:
    source = Path(str(row.get("source_image_path") or row.get("manifest_row", {}).get("roi_image_path") or ""))
    local = image_dir / source.name
    return local.resolve() if local.exists() else source.resolve()


def make_item(row: dict[str, Any], image_dir: Path, api_label_dir: Path, reviewed_label_dir: Path, reason: str) -> BatchItem:
    roi_id = str(row.get("cloud_roi_id") or Path(str(row.get("source_image_path"))).stem)
    image_path = image_path_for(row, image_dir)
    api_label_path = api_label_dir / f"{image_path.stem}.txt"
    reviewed_label_path = reviewed_label_dir / f"{image_path.stem}.txt"
    manifest_row = row.get("manifest_row") if isinstance(row.get("manifest_row"), dict) else {}
    types = visual_types(row)
    return BatchItem(
        cloud_roi_id=roi_id,
        image_path=image_path,
        api_label_path=api_label_path.resolve(),
        reviewed_label_path=reviewed_label_path.resolve(),
        api_confidence=max_confidence(row),
        visual_type=primary_visual_type(types),
        has_cloud=bool(row.get("has_cloud")),
        accepted_box_count=int(row.get("accepted_box_count") or 0),
        reason_for_selection=reason,
        source_batch="",
        cloud_likeness=float(manifest_row["cloud_likeness"]) if "cloud_likeness" in manifest_row else None,
        contains_marker=bool(manifest_row["contains_marker"]) if "contains_marker" in manifest_row else None,
    )


def score_row(row: dict[str, Any]) -> tuple[float, float, str]:
    confidence = max_confidence(row) or 0.0
    manifest_row = row.get("manifest_row") if isinstance(row.get("manifest_row"), dict) else {}
    cloud_likeness = float(manifest_row.get("cloud_likeness") or 0.0)
    return (-confidence, -cloud_likeness, str(row.get("cloud_roi_id") or ""))


def classify_rows(rows: list[dict[str, Any]], image_dir: Path, api_label_dir: Path, reviewed_label_dir: Path) -> dict[str, list[BatchItem]]:
    buckets: dict[str, list[BatchItem]] = {
        "bold_easy_positive": [],
        "thin_faint_positive": [],
        "weird_partial_intersected": [],
        "hard_negative_no_cloud": [],
        "common_false_positive_geometry": [],
        "later": [],
    }
    for row in sorted(rows, key=score_row):
        if row.get("status") != "ok":
            continue
        count = int(row.get("accepted_box_count") or 0)
        has_cloud = bool(row.get("has_cloud"))
        types = visual_types(row)
        parsed_boxes = row.get("parsed_response", {}).get("boxes", []) if isinstance(row.get("parsed_response"), dict) else []

        if count == 0 and not has_cloud:
            buckets["hard_negative_no_cloud"].append(
                make_item(row, image_dir, api_label_dir, reviewed_label_dir, "marker_neighborhood_negative_no_cloud")
            )
        elif count == 0 and (has_cloud or parsed_boxes):
            buckets["common_false_positive_geometry"].append(
                make_item(row, image_dir, api_label_dir, reviewed_label_dir, "model_reported_cloud_but_no_accepted_box")
            )
        elif types & {"thin", "faint"}:
            buckets["thin_faint_positive"].append(
                make_item(row, image_dir, api_label_dir, reviewed_label_dir, "thin_or_faint_positive")
            )
        elif types & {"partial", "intersected", "unknown"} or count >= 3:
            buckets["weird_partial_intersected"].append(
                make_item(row, image_dir, api_label_dir, reviewed_label_dir, "partial_intersected_or_multi_cloud_positive")
            )
        elif "bold" in types and (max_confidence(row) or 0.0) >= 0.80:
            buckets["bold_easy_positive"].append(
                make_item(row, image_dir, api_label_dir, reviewed_label_dir, "bold_easy_high_confidence_positive")
            )
        else:
            buckets["later"].append(make_item(row, image_dir, api_label_dir, reviewed_label_dir, "lower_priority_remaining"))
    return buckets


def take_unique(
    selected: list[BatchItem],
    seen: set[str],
    candidates: list[BatchItem],
    limit: int,
    batch_name: str,
) -> None:
    for item in candidates:
        if len([x for x in selected if x.reason_for_selection == item.reason_for_selection]) >= limit:
            break
        if item.cloud_roi_id in seen:
            continue
        selected.append(
            BatchItem(
                **{
                    **item.__dict__,
                    "source_batch": batch_name,
                }
            )
        )
        seen.add(item.cloud_roi_id)


def build_priority_batch(buckets: dict[str, list[BatchItem]], target_count: int) -> list[BatchItem]:
    quotas = {
        "bold_easy_positive": round(target_count * 0.28),
        "thin_faint_positive": round(target_count * 0.20),
        "weird_partial_intersected": round(target_count * 0.22),
        "hard_negative_no_cloud": round(target_count * 0.22),
        "common_false_positive_geometry": round(target_count * 0.08),
    }
    selected: list[BatchItem] = []
    seen: set[str] = set()
    for bucket_name, quota in quotas.items():
        take_unique(selected, seen, buckets[bucket_name], quota, "batch_001_priority_train")

    remaining = []
    for name in ["bold_easy_positive", "thin_faint_positive", "weird_partial_intersected", "hard_negative_no_cloud", "common_false_positive_geometry", "later"]:
        remaining.extend(buckets[name])
    for item in remaining:
        if len(selected) >= target_count:
            break
        if item.cloud_roi_id in seen:
            continue
        selected.append(BatchItem(**{**item.__dict__, "source_batch": "batch_001_priority_train"}))
        seen.add(item.cloud_roi_id)
    return selected


def write_batch(batch_dir: Path, items: list[BatchItem]) -> None:
    batch_dir.mkdir(parents=True, exist_ok=True)
    rows = [item.jsonable() for item in items]
    write_jsonl(batch_dir / "manifest.jsonl", rows)
    with (batch_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["cloud_roi_id"])
        writer.writeheader()
        writer.writerows(rows)
    (batch_dir / "images.txt").write_text(
        "\n".join(str(item.image_path) for item in items) + ("\n" if items else ""),
        encoding="utf-8",
    )


def seed_reviewed_labels(items: list[BatchItem], overwrite: bool) -> tuple[int, int, int]:
    copied = 0
    skipped = 0
    missing = 0
    for item in items:
        if not item.api_label_path.exists():
            missing += 1
            continue
        item.reviewed_label_path.parent.mkdir(parents=True, exist_ok=True)
        if item.reviewed_label_path.exists() and not overwrite:
            skipped += 1
            continue
        shutil.copy2(item.api_label_path, item.reviewed_label_path)
        copied += 1
    return copied, skipped, missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Create prioritized review batches from API cloud prelabels.")
    parser.add_argument("--image-dir", type=Path, default=ROOT / "data" / "cloud_roi_images")
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--api-label-dir", type=Path, default=ROOT / "data" / "api_cloud_labels_unreviewed")
    parser.add_argument("--reviewed-label-dir", type=Path, default=ROOT / "data" / "cloud_labels_reviewed")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "review_batches")
    parser.add_argument("--target-count", type=int, default=500)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--seed-all-batches", action="store_true")
    args = parser.parse_args()

    if not 300 <= args.target_count <= 600:
        parser.error("--target-count must be between 300 and 600")

    predictions_path = resolve_predictions_path(args.predictions)
    rows = read_jsonl(predictions_path)
    buckets = classify_rows(rows, args.image_dir.resolve(), args.api_label_dir.resolve(), args.reviewed_label_dir.resolve())
    priority = build_priority_batch(buckets, args.target_count)
    priority_ids = {item.cloud_roi_id for item in priority}

    output_batches = {
        "batch_001_priority_train": priority,
        "batch_002_thin_faint": [item for item in buckets["thin_faint_positive"] if item.cloud_roi_id not in priority_ids],
        "batch_003_weird_partial": [item for item in buckets["weird_partial_intersected"] if item.cloud_roi_id not in priority_ids],
        "batch_004_hard_negatives": [
            item
            for item in (buckets["hard_negative_no_cloud"] + buckets["common_false_positive_geometry"])
            if item.cloud_roi_id not in priority_ids
        ],
        "batch_later": [
            item
            for item in (buckets["bold_easy_positive"] + buckets["later"])
            if item.cloud_roi_id not in priority_ids
        ],
    }

    for name, items in output_batches.items():
        write_batch(args.output_dir / name, [BatchItem(**{**item.__dict__, "source_batch": name}) for item in items])

    labels_to_seed = priority
    if args.seed_all_batches:
        labels_to_seed = [item for items in output_batches.values() for item in items]
    copied, skipped, missing = seed_reviewed_labels(labels_to_seed, overwrite=args.overwrite)

    print(f"predictions={predictions_path}")
    for name, items in output_batches.items():
        print(f"{name}: {len(items)}")
    print(f"seeded reviewed labels: copied={copied} skipped={skipped} missing_api_labels={missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
