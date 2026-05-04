from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.data.source_control import (
    DEFAULT_QUASI_HOLDOUT_REVISIONS,
    dedupe_rows_by_id,
    row_id,
    source_control_fields,
    source_key_for_row,
)
from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_QUOTAS = {
    "normal_hard_negative": 75,
    "symbol_text_false_positive": 60,
    "weird_positive": 60,
    "high_conf_positive": 60,
    "large_dense_context": 45,
}

WEIRD_VISUAL_TYPES = {"faint", "thin", "partial", "intersected", "unknown"}


def _read_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(read_jsonl(path))
    return rows


def resolve_cloudhammer_path(raw: str | Path) -> Path:
    path = Path(str(raw))
    if path.exists():
        return path.resolve()
    if not path.is_absolute():
        candidate = ROOT / path
        if candidate.exists():
            return candidate.resolve()
    parts = list(path.parts)
    lowered = [part.lower() for part in parts]
    if "cloudhammer" in lowered:
        index = lowered.index("cloudhammer")
        relocated = ROOT.joinpath(*parts[index + 1 :])
        if relocated.exists():
            return relocated.resolve()
    return path


def source_image_for_row(row: dict[str, Any]) -> Path:
    nested = row.get("manifest_row") if isinstance(row.get("manifest_row"), dict) else {}
    for key in ("roi_image_path", "source_image_path", "image_path", "local_image_path", "crop_image_path"):
        raw = row.get(key) or nested.get(key)
        if raw:
            return resolve_cloudhammer_path(raw)
    return Path("")


def _float(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _int(row: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return 0


def expansion_bucket(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get(key) or "") for key in ("review_bucket", "review_group", "candidate_source", "reason_for_selection", "policy_bucket", "source_mode", "visual_types", "gpt_visual_types")).lower()
    if any(token in text for token in ("symbol", "glyph", "fixture", "text", "false_positive", "likely_false_positive")):
        return "symbol_text_false_positive"
    if str(row.get("size_bucket") or "").lower() in {"large", "xlarge"} or _int(row, "member_count") >= 6:
        return "large_dense_context"
    if str(row.get("source_mode") or "").lower() == "whole_cloud_candidate":
        return "large_dense_context"

    visual_text = str(row.get("visual_types") or row.get("gpt_visual_types") or row.get("visual_type") or "").lower()
    if any(visual in visual_text for visual in WEIRD_VISUAL_TYPES):
        return "weird_positive"
    if _float(row, "api_confidence", "max_confidence", "whole_cloud_confidence", "confidence", "cloud_candidate_score") >= 0.9:
        return "high_conf_positive"
    if "negative" in text or row.get("has_cloud") is False:
        return "normal_hard_negative"
    if (row.get("random_crop_id") or "_random_" in row_id(row)) and not (row.get("gpt_has_cloud") or row.get("review_group")):
        return "normal_hard_negative"
    return "weird_positive"


def _selection_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    key = source_key_for_row(row)
    confidence = _float(row, "api_confidence", "max_confidence", "whole_cloud_confidence", "confidence", "cloud_candidate_score")
    member_count = _int(row, "member_count")
    return (
        key.revision_group,
        key.source_id,
        key.page_index if key.page_index is not None else 999999,
        -member_count,
        -confidence,
        row_id(row),
    )


def balanced_bucket_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = source_key_for_row(row)
        groups[(key.revision_group, key.source_id)].append(row)
    for group_rows in groups.values():
        group_rows.sort(key=_selection_sort_key)

    ordered: list[dict[str, Any]] = []
    keys = sorted(groups)
    while keys:
        next_keys: list[tuple[str, str]] = []
        for key in keys:
            group_rows = groups[key]
            if group_rows:
                ordered.append(group_rows.pop(0))
            if group_rows:
                next_keys.append(key)
        keys = next_keys
    return ordered


def select_balanced_expansion(
    candidates: list[dict[str, Any]],
    *,
    existing_ids: set[str],
    api_labeled_ids: set[str] | None = None,
    target_count: int,
    quotas: dict[str, int],
    max_rows_per_source: int,
    max_rows_per_source_page: int,
    excluded_revisions: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped = Counter()
    seen: set[str] = set()
    api_labeled = api_labeled_ids or set()
    for row in dedupe_rows_by_id(candidates):
        rid = row_id(row)
        if rid in existing_ids:
            skipped["existing_reviewed"] += 1
            continue
        if rid in api_labeled:
            skipped["existing_api_label"] += 1
            continue
        image_path = source_image_for_row(row)
        if not image_path.exists():
            skipped["missing_image"] += 1
            continue
        key = source_key_for_row(row)
        if key.revision_group in excluded_revisions:
            skipped["quasi_holdout_excluded"] += 1
            continue
        if rid in seen:
            skipped["duplicate"] += 1
            continue
        seen.add(rid)
        buckets[expansion_bucket(row)].append(row)

    for bucket_rows in buckets.values():
        bucket_rows.sort(key=_selection_sort_key)

    source_counts: Counter[str] = Counter()
    page_counts: Counter[str] = Counter()
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    def try_take(row: dict[str, Any]) -> bool:
        rid = row_id(row)
        if rid in selected_ids:
            return False
        key = source_key_for_row(row)
        if source_counts[key.source_id] >= max_rows_per_source:
            return False
        if page_counts[key.page_key] >= max_rows_per_source_page:
            return False
        source_counts[key.source_id] += 1
        page_counts[key.page_key] += 1
        selected_ids.add(rid)
        selected.append(row)
        return True

    for bucket_name, quota in quotas.items():
        taken = 0
        for row in balanced_bucket_order(buckets.get(bucket_name, [])):
            if taken >= quota or len(selected) >= target_count:
                break
            if try_take(row):
                taken += 1

    if len(selected) < target_count:
        leftovers = [row for rows in buckets.values() for row in rows if row_id(row) not in selected_ids]
        for row in balanced_bucket_order(leftovers):
            if len(selected) >= target_count:
                break
            try_take(row)

    summary = {
        "available_by_bucket": {bucket: len(rows) for bucket, rows in sorted(buckets.items())},
        "selected_by_bucket": dict(Counter(expansion_bucket(row) for row in selected)),
        "selected_by_revision": dict(Counter(source_key_for_row(row).revision_group for row in selected)),
        "selected_by_source": Counter(source_key_for_row(row).source_id for row in selected).most_common(20),
        "skipped": dict(skipped),
    }
    return selected, summary


def write_review_batch(output_dir: Path, rows: list[dict[str, Any]], *, overwrite: bool) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise RuntimeError(f"{output_dir} exists and is not empty; pass --overwrite to replace generated files")
    if output_dir.exists() and overwrite:
        shutil.rmtree(output_dir)
    image_dir = output_dir / "images"
    label_dir = output_dir / "labels"
    api_label_dir = ROOT / "data" / "api_cloud_labels_unreviewed"
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    api_label_dir.mkdir(parents=True, exist_ok=True)

    output_rows: list[dict[str, Any]] = []
    image_list: list[str] = []
    copied = 0
    for row in rows:
        rid = row_id(row)
        src_image = source_image_for_row(row)
        suffix = src_image.suffix.lower() or ".png"
        local_image = (image_dir / f"{rid}{suffix}").resolve()
        local_label = (label_dir / f"{rid}.txt").resolve()
        api_label = (api_label_dir / f"{rid}.txt").resolve()
        shutil.copy2(src_image, local_image)
        copied += 1
        image_list.append(str(local_image))
        output_rows.append(
            {
                **row,
                **source_control_fields(row),
                "cloud_roi_id": rid,
                "image_path": str(local_image),
                "roi_image_path": str(local_image),
                "label_path": str(local_label),
                "api_label_path": str(api_label),
                "source_image_path": str(src_image),
                "source_batch": output_dir.name,
                "expansion_bucket": expansion_bucket(row),
                "human_quick_label": "",
                "human_notes": "",
            }
        )

    write_jsonl(output_dir / "manifest.jsonl", output_rows)
    write_jsonl(output_dir / "prelabel_manifest.jsonl", output_rows)
    (output_dir / "images.txt").write_text("\n".join(image_list) + ("\n" if image_list else ""), encoding="utf-8")
    (label_dir / "classes.txt").write_text("cloud_motif\n", encoding="utf-8")

    fieldnames = list(output_rows[0].keys()) if output_rows else ["cloud_roi_id"]
    with (output_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)
    return {"rows": len(output_rows), "images_copied": copied}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a balanced CloudHammer V2 expansion review batch from sets 1-7.")
    parser.add_argument("--candidate-manifest", type=Path, action="append", default=[])
    parser.add_argument(
        "--existing-reviewed-manifest",
        type=Path,
        action="append",
        default=[],
        help="Reviewed manifests whose ROI IDs should not be selected again.",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "review_batches" / "small_corpus_expansion_20260502")
    parser.add_argument("--target-count", type=int, default=300)
    parser.add_argument("--max-rows-per-source", type=int, default=70)
    parser.add_argument("--max-rows-per-source-page", type=int, default=10)
    parser.add_argument("--include-quasi-holdout", action="store_true")
    parser.add_argument(
        "--exclude-api-labeled",
        action="store_true",
        help="Exclude candidates that already have a global API prelabel txt.",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    candidate_paths = args.candidate_manifest or [
        ROOT / "data" / "manifests" / "cloud_roi_broad_allmarkers_20260427.jsonl",
        ROOT / "data" / "manifests" / "cloud_roi_broad_candidates_20260427.jsonl",
        ROOT / "runs" / "whole_cloud_eval_symbol_text_fp_hn_20260502" / "whole_cloud_candidates_manifest.jsonl",
        ROOT / "data" / "temp_random_gpt_review_queue" / "manifest.jsonl",
    ]
    reviewed_paths = args.existing_reviewed_manifest or [
        ROOT / "data" / "manifests" / "reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl"
    ]
    candidates = _read_rows([path for path in candidate_paths if path.exists()])
    existing_ids = {row_id(row) for row in _read_rows([path for path in reviewed_paths if path.exists()])}
    api_labeled_ids = set()
    if args.exclude_api_labeled:
        api_label_dir = ROOT / "data" / "api_cloud_labels_unreviewed"
        api_labeled_ids = {path.stem for path in api_label_dir.glob("*.txt")}
    excluded = set() if args.include_quasi_holdout else set(DEFAULT_QUASI_HOLDOUT_REVISIONS)
    selected, selection_summary = select_balanced_expansion(
        candidates,
        existing_ids=existing_ids,
        api_labeled_ids=api_labeled_ids,
        target_count=args.target_count,
        quotas=DEFAULT_QUOTAS,
        max_rows_per_source=args.max_rows_per_source,
        max_rows_per_source_page=args.max_rows_per_source_page,
        excluded_revisions=excluded,
    )
    write_summary = write_review_batch(args.output_dir, selected, overwrite=args.overwrite)
    summary = {
        "schema": "cloudhammer.small_corpus_expansion_review_batch.v1",
        "candidate_manifests": [str(path) for path in candidate_paths if path.exists()],
        "existing_reviewed_manifests": [str(path) for path in reviewed_paths if path.exists()],
        "target_count": args.target_count,
        "quotas": DEFAULT_QUOTAS,
        "source_caps": {
            "max_rows_per_source": args.max_rows_per_source,
            "max_rows_per_source_page": args.max_rows_per_source_page,
        },
        "excluded_revisions": sorted(excluded),
        **selection_summary,
        **write_summary,
    }
    write_json(args.output_dir / "summary.json", summary)
    print(json.dumps({key: summary[key] for key in ("rows", "selected_by_bucket", "selected_by_revision", "skipped")}, indent=2))
    print(f"wrote {args.output_dir / 'manifest.jsonl'}")
    print(f"wrote {args.output_dir / 'prelabel_manifest.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
