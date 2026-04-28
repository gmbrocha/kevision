from __future__ import annotations

import csv
import json
import random
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


WEIRD_VISUAL_TYPES = {"faint", "thin", "partial", "intersected", "unknown"}


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def row_id(row: dict[str, Any]) -> str:
    return str(row.get("cloud_roi_id") or Path(str(row.get("source_image_path") or "")).stem)


def manifest_row(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("manifest_row")
    return value if isinstance(value, dict) else row


def revision_name(row: dict[str, Any]) -> str:
    data = manifest_row(row)
    pdf_path = str(data.get("pdf_path") or row.get("pdf_path") or "")
    for part in Path(pdf_path).parts:
        if part.startswith("Revision #"):
            return part
    return "unknown"


def candidate_source(row: dict[str, Any]) -> str:
    data = manifest_row(row)
    return str(data.get("candidate_source") or row.get("candidate_source") or "unknown")


def max_confidence(row: dict[str, Any]) -> float | None:
    values = [
        float(box.get("confidence", 0.0))
        for box in row.get("accepted_boxes", [])
        if isinstance(box, dict)
    ]
    return max(values) if values else None


def visual_types(row: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for box in row.get("accepted_boxes", []):
        if isinstance(box, dict):
            out.add(str(box.get("visual_type") or "unknown"))
    return out


def accepted_box_count(row: dict[str, Any]) -> int:
    try:
        return int(row.get("accepted_box_count") or 0)
    except (TypeError, ValueError):
        return 0


def parsed_box_count(row: dict[str, Any]) -> int:
    parsed = row.get("parsed_response")
    if not isinstance(parsed, dict):
        return 0
    boxes = parsed.get("boxes")
    return len(boxes) if isinstance(boxes, list) else 0


def has_cloud(row: dict[str, Any]) -> bool:
    return bool(row.get("has_cloud"))


def confidence_bucket(confidence: float | None) -> str:
    if confidence is None:
        return "none"
    if confidence >= 0.95:
        return ">=0.95"
    if confidence >= 0.90:
        return "0.90-0.94"
    if confidence >= 0.80:
        return "0.80-0.89"
    if confidence >= 0.70:
        return "0.70-0.79"
    return "<0.70"


def classify_for_review(row: dict[str, Any]) -> str:
    if row.get("status") != "ok":
        return "failed"

    count = accepted_box_count(row)
    if count == 0:
        if has_cloud(row) or parsed_box_count(row) > 0:
            return "ambiguous_positive"
        if candidate_source(row) == "target_marker_neighborhood":
            return "hard_negative_marker_no_cloud"
        return "gpt_negative_spotcheck"

    if visual_types(row) & WEIRD_VISUAL_TYPES or count >= 3:
        return "weird_multi_faint_partial"
    if (max_confidence(row) or 0.0) >= 0.90:
        return "high_conf_positive"
    return "ambiguous_positive"


def summarize_predictions(predictions: list[dict[str, Any]], manifest: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    ids = {row_id(row) for row in predictions}
    expected_ids = {row_id(row) for row in manifest} if manifest is not None else set()

    summary: dict[str, Any] = {
        "prediction_rows": len(predictions),
        "expected_rows": len(expected_ids) if manifest is not None else None,
        "missing_predictions": sorted(expected_ids - ids) if manifest is not None else [],
        "extra_predictions": sorted(ids - expected_ids) if manifest is not None else [],
        "status": dict(Counter(str(row.get("status")) for row in predictions)),
        "has_cloud": dict(Counter(str(has_cloud(row)) for row in predictions if row.get("status") == "ok")),
        "accepted_box_count": dict(Counter(str(accepted_box_count(row)) for row in predictions if row.get("status") == "ok")),
        "confidence_bucket": dict(Counter(confidence_bucket(max_confidence(row)) for row in predictions if row.get("status") == "ok")),
        "review_bucket": dict(Counter(classify_for_review(row) for row in predictions)),
        "candidate_source": dict(Counter(candidate_source(row) for row in predictions)),
        "revision": {},
        "box_visual_type": {},
    }

    by_revision: dict[str, Counter[str]] = defaultdict(Counter)
    visual_counter: Counter[str] = Counter()
    for row in predictions:
        rev = revision_name(row)
        by_revision[rev]["rows"] += 1
        by_revision[rev][f"status:{row.get('status')}"] += 1
        by_revision[rev][f"source:{candidate_source(row)}"] += 1
        by_revision[rev][f"review:{classify_for_review(row)}"] += 1
        if row.get("status") == "ok":
            by_revision[rev]["accepted_boxes"] += accepted_box_count(row)
            by_revision[rev]["has_cloud" if has_cloud(row) else "no_cloud"] += 1
        for visual_type in visual_types(row):
            visual_counter[visual_type] += 1

    summary["revision"] = {key: dict(value) for key, value in sorted(by_revision.items())}
    summary["box_visual_type"] = dict(visual_counter)
    return summary


def _sort_key(row: dict[str, Any]) -> tuple[object, ...]:
    confidence = max_confidence(row)
    confidence_sort = -confidence if confidence is not None else 0.0
    return (
        revision_name(row),
        candidate_source(row),
        -accepted_box_count(row),
        confidence_sort,
        row_id(row),
    )


def select_balanced(rows: list[dict[str, Any]], limit: int, seed: int) -> list[dict[str, Any]]:
    if limit <= 0 or len(rows) <= limit:
        return sorted(rows, key=_sort_key)

    rng = random.Random(seed)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(revision_name(row), candidate_source(row))].append(row)
    for group_rows in groups.values():
        group_rows.sort(key=_sort_key)

    keys = sorted(groups)
    rng.shuffle(keys)
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    while len(selected) < limit and keys:
        progressed = False
        for key in list(keys):
            bucket = groups[key]
            while bucket and row_id(bucket[0]) in seen:
                bucket.pop(0)
            if not bucket:
                keys.remove(key)
                continue
            item = bucket.pop(0)
            selected.append(item)
            seen.add(row_id(item))
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def source_image_path(row: dict[str, Any]) -> Path:
    data = manifest_row(row)
    raw = row.get("source_image_path") or data.get("roi_image_path") or data.get("image_path")
    return Path(str(raw))


def gpt_label_path(row: dict[str, Any]) -> Path:
    raw = row.get("label_path")
    return Path(str(raw)) if raw else Path("")


def gpt_review_path(row: dict[str, Any]) -> Path:
    raw = row.get("review_image_path")
    return Path(str(raw)) if raw else Path("")


def queue_row(row: dict[str, Any], local_image: Path, local_label: Path, local_overlay: Path | None) -> dict[str, Any]:
    data = manifest_row(row)
    return {
        "cloud_roi_id": row_id(row),
        "review_bucket": classify_for_review(row),
        "revision": revision_name(row),
        "candidate_source": candidate_source(row),
        "source_image_path": str(source_image_path(row)),
        "local_image_path": str(local_image),
        "gpt_label_path": str(gpt_label_path(row)) if str(gpt_label_path(row)) else "",
        "local_label_path": str(local_label),
        "gpt_overlay_path": str(gpt_review_path(row)) if str(gpt_review_path(row)) else "",
        "local_overlay_path": str(local_overlay) if local_overlay is not None else "",
        "pdf_path": str(data.get("pdf_path") or ""),
        "page_index": data.get("page_index", ""),
        "page_number": data.get("page_number", ""),
        "sheet_id": data.get("sheet_id", ""),
        "sheet_title": data.get("sheet_title", ""),
        "accepted_box_count": accepted_box_count(row),
        "max_confidence": "" if max_confidence(row) is None else f"{max_confidence(row):.4f}",
        "visual_types": ",".join(sorted(visual_types(row))),
        "human_quick_label": "",
        "human_notes": "",
    }


@dataclass(frozen=True)
class QueueWriteResult:
    name: str
    count: int
    images_copied: int
    labels_copied: int
    overlays_copied: int
    missing_images: int


def write_review_queue(root: Path, name: str, rows: list[dict[str, Any]]) -> QueueWriteResult:
    queue_dir = root / name
    image_dir = queue_dir / "images"
    label_dir = queue_dir / "labels"
    overlay_dir = queue_dir / "gpt_overlays"
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)

    output_rows: list[dict[str, Any]] = []
    images_copied = labels_copied = overlays_copied = missing_images = 0
    image_list: list[str] = []

    for row in rows:
        roi_id = row_id(row)
        src_image = source_image_path(row)
        if not src_image.exists():
            missing_images += 1
            continue
        image_out = image_dir / f"{roi_id}{src_image.suffix.lower() or '.png'}"
        shutil.copy2(src_image, image_out)
        images_copied += 1
        image_list.append(str(image_out.resolve()))

        label_src = gpt_label_path(row)
        label_out = label_dir / f"{roi_id}.txt"
        if label_src.exists():
            shutil.copy2(label_src, label_out)
            labels_copied += 1
        else:
            label_out.write_text("", encoding="utf-8")

        overlay_src = gpt_review_path(row)
        overlay_out: Path | None = None
        if overlay_src.exists():
            overlay_out = overlay_dir / f"{roi_id}{overlay_src.suffix.lower() or '.jpg'}"
            shutil.copy2(overlay_src, overlay_out)
            overlays_copied += 1

        output_rows.append(queue_row(row, image_out.resolve(), label_out.resolve(), overlay_out.resolve() if overlay_out else None))

    write_jsonl(queue_dir / "manifest.jsonl", output_rows)
    (queue_dir / "images.txt").write_text("\n".join(image_list) + ("\n" if image_list else ""), encoding="utf-8")
    (label_dir / "classes.txt").write_text("cloud_motif\n", encoding="utf-8")

    csv_path = queue_dir / "review_queue.csv"
    fieldnames = list(output_rows[0].keys()) if output_rows else ["cloud_roi_id"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    return QueueWriteResult(
        name=name,
        count=len(output_rows),
        images_copied=images_copied,
        labels_copied=labels_copied,
        overlays_copied=overlays_copied,
        missing_images=missing_images,
    )
