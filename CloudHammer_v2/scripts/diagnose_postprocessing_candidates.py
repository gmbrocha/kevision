from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
LEGACY_ROOT = PROJECT_ROOT / "CloudHammer"

DEFAULT_CANDIDATE_MANIFEST = (
    LEGACY_ROOT / "runs" / "whole_cloud_eval_symbol_text_fp_hn_20260502" / "whole_cloud_candidates_manifest.jsonl"
)
DEFAULT_OUTPUT_DIR = V2_ROOT / "outputs" / "postprocessing_diagnostic_non_frozen_20260504"
DEFAULT_FROZEN_MANIFEST = (
    V2_ROOT / "eval" / "page_disjoint_real" / "page_disjoint_real_manifest.human_audited.jsonl"
)
DEFAULT_REVIEW_SUMMARY = (
    V2_ROOT
    / "outputs"
    / "baseline_human_audited_mismatch_review_20260504"
    / "overlay_packet"
    / "mismatch_review_log.reviewed_summary.json"
)

DIAGNOSTIC_FAMILIES = [
    "fragment_merge_candidate",
    "duplicate_suppression_candidate",
    "overmerge_split_candidate",
    "loose_localization_candidate",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def page_index_from_render_path(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"_p(\d{4})$", Path(value).stem)
    return int(match.group(1)) if match else None


def page_identity(row: dict[str, Any]) -> dict[str, Any]:
    render_path = str(row.get("render_path") or row.get("image_path") or "")
    pdf_path = str(row.get("pdf_path") or "")
    pdf_stem = str(row.get("pdf_stem") or (Path(pdf_path).stem if pdf_path else "unknown_pdf"))
    page_index = page_index_from_render_path(render_path)
    page_number = row.get("page_number")
    if page_index is None and page_number not in (None, ""):
        try:
            page_index = int(page_number) - 1
        except ValueError:
            page_index = None
    page_token = f"p{page_index:04d}" if page_index is not None else f"page_{page_number or 'unknown'}"
    render_stem = Path(render_path).stem if render_path else ""
    return {
        "source_page_key": f"{safe_stem(pdf_stem)}:{page_token}",
        "render_stem": render_stem,
        "pdf_stem": pdf_stem,
        "page_index": page_index,
        "page_number": page_number,
        "render_path": render_path,
        "pdf_path": pdf_path,
    }


def frozen_page_keys(manifest_path: Path) -> set[str]:
    keys: set[str] = set()
    if not manifest_path.exists():
        return keys
    for row in read_jsonl(manifest_path):
        identity = page_identity(row)
        keys.add(str(row.get("source_page_key") or ""))
        keys.add(identity["source_page_key"])
        if identity["render_stem"]:
            keys.add(f"render:{identity['render_stem']}")
        if identity["pdf_stem"] and identity["page_index"] is not None:
            keys.add(f"pdf:{identity['pdf_stem']}:p{identity['page_index']:04d}")
    return {key for key in keys if key}


def is_frozen_page(row: dict[str, Any], frozen_keys: set[str]) -> bool:
    identity = page_identity(row)
    candidates = {
        str(row.get("source_page_key") or ""),
        identity["source_page_key"],
        f"render:{identity['render_stem']}",
    }
    if identity["pdf_stem"] and identity["page_index"] is not None:
        candidates.add(f"pdf:{identity['pdf_stem']}:p{identity['page_index']:04d}")
    return any(key in frozen_keys for key in candidates if key)


def xywh_to_xyxy(box: list[float]) -> list[float]:
    x, y, w, h = [float(value) for value in box]
    return [x, y, x + w, y + h]


def normalize_xyxy(box: list[float]) -> list[float]:
    x1, y1, x2, y2 = [float(value) for value in box]
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def box_xyxy(row: dict[str, Any]) -> list[float]:
    if isinstance(row.get("bbox_page_xyxy"), list):
        return normalize_xyxy(row["bbox_page_xyxy"])
    if isinstance(row.get("bbox_page_xywh"), list):
        return xywh_to_xyxy(row["bbox_page_xywh"])
    if isinstance(row.get("bbox_page"), list):
        return xywh_to_xyxy(row["bbox_page"])
    raise ValueError(f"Row has no supported bbox field: {row.get('candidate_id')}")


def area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def iou(a: list[float], b: list[float]) -> float:
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    inter = area([ix1, iy1, ix2, iy2])
    denom = area(a) + area(b) - inter
    return 0.0 if denom <= 0 else inter / denom


def intersection_over_min_area(a: list[float], b: list[float]) -> float:
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    inter = area([ix1, iy1, ix2, iy2])
    denom = min(area(a), area(b))
    return 0.0 if denom <= 0 else inter / denom


def union_box(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def center_gap(a: list[float], b: list[float]) -> float:
    ax = (a[0] + a[2]) / 2.0
    ay = (a[1] + a[3]) / 2.0
    bx = (b[0] + b[2]) / 2.0
    by = (b[1] + b[3]) / 2.0
    return math.hypot(ax - bx, ay - by)


def edge_gap(a: list[float], b: list[float]) -> float:
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def axis_overlap_ratio(a: list[float], b: list[float], axis: str) -> float:
    if axis == "x":
        inter = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
        denom = min(max(0.0, a[2] - a[0]), max(0.0, b[2] - b[0]))
    else:
        inter = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
        denom = min(max(0.0, a[3] - a[1]), max(0.0, b[3] - b[1]))
    return 0.0 if denom <= 0 else inter / denom


def relation_for_merge(a: list[float], b: list[float], max_gap_px: float) -> tuple[bool, dict[str, float]]:
    pair_iou = iou(a, b)
    containment = intersection_over_min_area(a, b)
    gap = edge_gap(a, b)
    x_overlap = axis_overlap_ratio(a, b, "x")
    y_overlap = axis_overlap_ratio(a, b, "y")
    adjacent = gap <= max_gap_px and max(x_overlap, y_overlap) >= 0.20
    should_merge_review = pair_iou >= 0.02 or containment >= 0.35 or adjacent
    return should_merge_review, {
        "iou": round(pair_iou, 6),
        "containment": round(containment, 6),
        "edge_gap_px": round(gap, 3),
        "center_gap_px": round(center_gap(a, b), 3),
        "x_overlap_ratio": round(x_overlap, 6),
        "y_overlap_ratio": round(y_overlap, 6),
    }


def connected_components(indexes: list[int], edges: dict[int, set[int]]) -> list[list[int]]:
    remaining = set(indexes)
    components: list[list[int]] = []
    while remaining:
        start = remaining.pop()
        stack = [start]
        component = {start}
        while stack:
            item = stack.pop()
            for neighbor in edges.get(item, set()):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda values: (len(values), values), reverse=True)


def candidate_id(row: dict[str, Any], fallback: int) -> str:
    return str(row.get("candidate_id") or f"candidate_{fallback:04d}")


def confidence(row: dict[str, Any]) -> float:
    return float(row.get("whole_cloud_confidence") or row.get("confidence") or 0.0)


def member_boxes(row: dict[str, Any]) -> list[list[float]]:
    boxes = row.get("member_boxes_page_xyxy")
    if not isinstance(boxes, list):
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        boxes = metadata.get("member_boxes_page")
    if not isinstance(boxes, list):
        return []
    normalized = []
    for box in boxes:
        if isinstance(box, list) and len(box) == 4:
            normalized.append(normalize_xyxy(box))
    return normalized


def group_fill_ratio(row: dict[str, Any], bbox: list[float], members: list[list[float]]) -> float | None:
    explicit = row.get("group_fill_ratio")
    if explicit is None and isinstance(row.get("metadata"), dict):
        explicit = row["metadata"].get("fill_ratio")
    if explicit is not None:
        try:
            return float(explicit)
        except (TypeError, ValueError):
            pass
    if not members or area(bbox) <= 0:
        return None
    return sum(area(member) for member in members) / area(bbox)


def diagnostic_row(
    family: str,
    source_page: dict[str, Any],
    candidate_ids: list[str],
    metrics: dict[str, Any],
    reason: str,
    suggested_review_focus: str,
) -> dict[str, Any]:
    stable = safe_stem(f"{source_page['source_page_key']}:{family}:{':'.join(candidate_ids)}")
    return {
        "diagnostic_id": stable,
        "diagnostic_family": family,
        "source_page_key": source_page["source_page_key"],
        "render_stem": source_page["render_stem"],
        "pdf_stem": source_page["pdf_stem"],
        "page_index": source_page["page_index"],
        "page_number": source_page["page_number"],
        "candidate_ids": candidate_ids,
        "metrics": metrics,
        "reason": reason,
        "suggested_review_focus": suggested_review_focus,
        "render_path": source_page["render_path"],
        "pdf_path": source_page["pdf_path"],
        "source": "postprocessing_geometry_diagnostic_report_only",
    }


def analyze_page(rows: list[dict[str, Any]], max_gap_ratio: float, max_gap_px: float) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        bbox = box_xyxy(row)
        identity = page_identity(row)
        members = member_boxes(row)
        normalized_rows.append(
            {
                "row": row,
                "candidate_id": candidate_id(row, index),
                "bbox": bbox,
                "members": members,
                "fill_ratio": group_fill_ratio(row, bbox, members),
                "confidence": confidence(row),
                "identity": identity,
            }
        )

    page_width = max((float(row["row"].get("page_width") or 0) for row in normalized_rows), default=0.0)
    page_height = max((float(row["row"].get("page_height") or 0) for row in normalized_rows), default=0.0)
    page_max_gap = max(max_gap_px, max(page_width, page_height) * max_gap_ratio)
    source_page = normalized_rows[0]["identity"]
    output_rows: list[dict[str, Any]] = []

    for left_index, left in enumerate(normalized_rows):
        for right in normalized_rows[left_index + 1 :]:
            merge_relation, metrics = relation_for_merge(left["bbox"], right["bbox"], page_max_gap)
            containment = metrics["containment"]
            pair_iou = metrics["iou"]
            if pair_iou >= 0.65 or containment >= 0.85:
                output_rows.append(
                    diagnostic_row(
                        "duplicate_suppression_candidate",
                        source_page,
                        [left["candidate_id"], right["candidate_id"]],
                        {
                            **metrics,
                            "left_confidence": round(left["confidence"], 6),
                            "right_confidence": round(right["confidence"], 6),
                        },
                        "Candidate boxes substantially overlap or contain each other.",
                        "Review whether the lower-quality duplicate should be suppressed before export.",
                    )
                )
            elif merge_relation:
                output_rows.append(
                    diagnostic_row(
                        "fragment_merge_candidate",
                        source_page,
                        [left["candidate_id"], right["candidate_id"]],
                        {
                            **metrics,
                            "left_confidence": round(left["confidence"], 6),
                            "right_confidence": round(right["confidence"], 6),
                        },
                        "Candidate boxes are adjacent or weakly overlapping and may be fragments of one cloud.",
                        "Review whether these should merge into one whole-cloud candidate.",
                    )
                )

    for item in normalized_rows:
        bbox = item["bbox"]
        members = item["members"]
        fill_ratio = item["fill_ratio"]
        if members:
            edges: dict[int, set[int]] = defaultdict(set)
            for left_index, left in enumerate(members):
                for right_index, right in enumerate(members[left_index + 1 :], start=left_index + 1):
                    related, _ = relation_for_merge(left, right, page_max_gap)
                    if related:
                        edges[left_index].add(right_index)
                        edges[right_index].add(left_index)
            components = connected_components(list(range(len(members))), edges)
            tight = union_box(members)
            tight_area = area(tight)
            bbox_area = area(bbox)
            loose_area_ratio = bbox_area / tight_area if tight_area > 0 else None
        else:
            components = []
            tight = None
            loose_area_ratio = None

        if len(components) >= 2 and (fill_ratio is None or fill_ratio <= 0.35):
            output_rows.append(
                diagnostic_row(
                    "overmerge_split_candidate",
                    source_page,
                    [item["candidate_id"]],
                    {
                        "candidate_confidence": round(item["confidence"], 6),
                        "member_count": len(members),
                        "member_component_count": len(components),
                        "component_sizes": [len(component) for component in components],
                        "group_fill_ratio": None if fill_ratio is None else round(fill_ratio, 6),
                        "bbox_xyxy": [round(value, 3) for value in bbox],
                    },
                    "One candidate contains multiple separated member-box components.",
                    "Review whether this is one large cloud or an overmerge that should split into separate candidates.",
                )
            )

        if loose_area_ratio is not None and loose_area_ratio >= 1.45:
            output_rows.append(
                diagnostic_row(
                    "loose_localization_candidate",
                    source_page,
                    [item["candidate_id"]],
                    {
                        "candidate_confidence": round(item["confidence"], 6),
                        "member_count": len(members),
                        "bbox_area": round(area(bbox), 3),
                        "tight_member_area": round(area(tight), 3) if tight else None,
                        "bbox_to_tight_member_area_ratio": round(loose_area_ratio, 6),
                        "group_fill_ratio": None if fill_ratio is None else round(fill_ratio, 6),
                        "bbox_xyxy": [round(value, 3) for value in bbox],
                        "tight_member_bbox_xyxy": [round(value, 3) for value in tight] if tight else None,
                    },
                    "Candidate bbox is materially larger than the tight box around its member detections.",
                    "Review whether crop tightening/localization should shrink this candidate before export.",
                )
            )

    return output_rows


def load_review_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def markdown_summary(summary: dict[str, Any], top_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Non-Frozen Postprocessing Diagnostic",
        "",
        "This report is a read-only geometry diagnostic. It does not modify labels,",
        "eval manifests, prediction files, model files, datasets, or training data.",
        "",
        f"Source candidate manifest: `{summary['source_candidate_manifest']}`",
        f"Output rows: `{summary['diagnostic_rows']}`",
        f"Input candidates: `{summary['input_candidates']}`",
        f"Analyzed candidates: `{summary['analyzed_candidates']}`",
        f"Excluded frozen-page candidates: `{summary['excluded_frozen_candidates']}`",
        "",
        "## Diagnostic Families",
        "",
    ]
    for family, count in summary["by_diagnostic_family"].items():
        lines.append(f"- `{family}`: `{count}`")
    lines.extend(
        [
            "",
            "## Baseline Mismatch Context",
            "",
            f"- Reviewed mismatch rows: `{summary['reviewed_mismatch_context'].get('reviewed_rows', 'unknown')}`",
            "- Dominant reviewed buckets are fragments, duplicates, overmerges, split fragments, and localization.",
            f"- `crossing_line_x_patterns`: `{summary['reviewed_mismatch_context'].get('crossing_line_x_patterns', 0)}` "
            "(tracked for later hard-negative/training-family review, not the primary blocker).",
            "",
            "## Interpretation",
            "",
            "- `fragment_merge_candidate`: nearby or weakly overlapping candidates that may need merge review.",
            "- `duplicate_suppression_candidate`: overlapping/contained candidates that may need duplicate suppression.",
            "- `overmerge_split_candidate`: one candidate with separated member components that may need split review.",
            "- `loose_localization_candidate`: one candidate whose box is materially looser than its member detections.",
            "",
            "These are candidate rows for postprocessing diagnosis only. Do not treat them as truth labels.",
            "",
            "Review fatigue guardrail: report this queue size before asking for manual review. For 10-50",
            "repetitive diagnostic rows, usually recommend GPT-5.5 sample or full provisional prefill first.",
            "For more than 50 rows, recommend staged GPT-5.5 prefill unless explicitly declined.",
            "",
            "## Top Rows",
            "",
        ]
    )
    for row in top_rows[:20]:
        lines.append(
            f"- `{row['diagnostic_family']}` `{', '.join(row['candidate_ids'])}` "
            f"on `{row['source_page_key']}`: {row['reason']}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a read-only non-frozen postprocessing diagnostic from whole-cloud candidate geometry."
    )
    parser.add_argument("--candidate-manifest", type=Path, default=DEFAULT_CANDIDATE_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--frozen-manifest", type=Path, default=DEFAULT_FROZEN_MANIFEST)
    parser.add_argument("--review-summary", type=Path, default=DEFAULT_REVIEW_SUMMARY)
    parser.add_argument("--max-gap-ratio", type=float, default=0.02)
    parser.add_argument("--max-gap-px", type=float, default=250.0)
    args = parser.parse_args()

    candidates = read_jsonl(args.candidate_manifest)
    frozen_keys = frozen_page_keys(args.frozen_manifest)
    review_summary = load_review_summary(args.review_summary)

    analyzed: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        identity = page_identity(row)
        if is_frozen_page(row, frozen_keys):
            excluded.append(
                {
                    "candidate_id": row.get("candidate_id"),
                    "source_page_key": identity["source_page_key"],
                    "render_stem": identity["render_stem"],
                    "reason": "excluded_by_frozen_page_disjoint_real_guard",
                }
            )
            continue
        by_page[identity["source_page_key"]].append(row)
        analyzed.append(row)

    diagnostic_rows: list[dict[str, Any]] = []
    for rows in by_page.values():
        diagnostic_rows.extend(analyze_page(rows, args.max_gap_ratio, args.max_gap_px))

    by_family = Counter(row["diagnostic_family"] for row in diagnostic_rows)
    by_family_complete = {family: by_family.get(family, 0) for family in DIAGNOSTIC_FAMILIES}
    reviewed_buckets = review_summary.get("by_human_error_bucket", {}) if isinstance(review_summary, dict) else {}
    reviewed_context = {
        "reviewed_rows": review_summary.get("reviewed_rows") if isinstance(review_summary, dict) else None,
        "matching_or_scoring_artifact": (review_summary.get("by_bucket_category", {}) or {}).get(
            "matching_or_scoring_artifact"
        )
        if isinstance(review_summary, dict)
        else None,
        "true_model_error_or_visual_family": (review_summary.get("by_bucket_category", {}) or {}).get(
            "true_model_error_or_visual_family"
        )
        if isinstance(review_summary, dict)
        else None,
        "crossing_line_x_patterns": reviewed_buckets.get("crossing_line_x_patterns", 0),
    }
    summary = {
        "schema": "cloudhammer_v2.postprocessing_diagnostic.v1",
        "source_candidate_manifest": str(args.candidate_manifest),
        "frozen_manifest_guard": str(args.frozen_manifest),
        "review_summary_context": str(args.review_summary),
        "output_dir": str(args.output_dir),
        "input_candidates": len(candidates),
        "analyzed_candidates": len(analyzed),
        "excluded_frozen_candidates": len(excluded),
        "pages_analyzed": len(by_page),
        "diagnostic_rows": len(diagnostic_rows),
        "by_diagnostic_family": by_family_complete,
        "reviewed_mismatch_context": reviewed_context,
        "guardrails": [
            "report_only",
            "excluded_page_disjoint_real_frozen_pages",
            "no_truth_label_edits",
            "no_eval_manifest_edits",
            "no_prediction_file_edits",
            "no_model_file_edits",
            "no_dataset_or_training_data_writes",
            "not_threshold_tuning",
        ],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "postprocessing_diagnostic_candidates.jsonl", diagnostic_rows)
    write_jsonl(args.output_dir / "excluded_frozen_candidates.jsonl", excluded)
    write_json(args.output_dir / "postprocessing_diagnostic_summary.json", summary)
    (args.output_dir / "postprocessing_diagnostic_summary.md").write_text(
        markdown_summary(summary, diagnostic_rows), encoding="utf-8"
    )

    print("Postprocessing diagnostic summary")
    print(f"- source_candidate_manifest: {args.candidate_manifest}")
    print(f"- input_candidates: {len(candidates)}")
    print(f"- analyzed_candidates: {len(analyzed)}")
    print(f"- excluded_frozen_candidates: {len(excluded)}")
    print(f"- diagnostic_rows: {len(diagnostic_rows)}")
    print(f"- by_diagnostic_family: {by_family_complete}")
    print(f"- output_dir: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
