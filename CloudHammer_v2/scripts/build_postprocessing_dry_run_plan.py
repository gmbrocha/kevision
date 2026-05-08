from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
DEFAULT_DIAGNOSTIC_DIR = V2_ROOT / "outputs" / "postprocessing_diagnostic_non_frozen_20260504"
DEFAULT_FROZEN_MANIFEST = (
    V2_ROOT / "eval" / "page_disjoint_real" / "page_disjoint_real_manifest.human_audited.jsonl"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def project_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    candidate = Path(str(value))
    if candidate.exists():
        return candidate.resolve()
    parts = candidate.parts
    for anchor, root in (("CloudHammer", PROJECT_ROOT / "CloudHammer"), ("CloudHammer_v2", V2_ROOT)):
        for index, part in enumerate(parts):
            if part.lower() == anchor.lower():
                relocated = root.joinpath(*parts[index + 1 :])
                if relocated.exists():
                    return relocated.resolve()
    return candidate


def split_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]


def normalize_xyxy(values: list[Any]) -> list[float]:
    if len(values) != 4:
        raise ValueError(f"Expected 4 bbox values, got {values}")
    x1, y1, x2, y2 = [float(value) for value in values]
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def parse_bbox(value: str | None) -> list[float] | None:
    if not value or not str(value).strip():
        return None
    payload = json.loads(value)
    if not isinstance(payload, list) or len(payload) != 4:
        return None
    return normalize_xyxy(payload)


def box_from_candidate(row: dict[str, Any]) -> list[float]:
    if isinstance(row.get("bbox_page_xyxy"), list):
        return normalize_xyxy(row["bbox_page_xyxy"])
    if isinstance(row.get("bbox_page_xywh"), list) and len(row["bbox_page_xywh"]) == 4:
        x, y, w, h = [float(value) for value in row["bbox_page_xywh"]]
        return [x, y, x + w, y + h]
    raise ValueError(f"Candidate has no bbox: {row.get('candidate_id')}")


def xyxy_to_xywh(box: list[float]) -> list[float]:
    return [box[0], box[1], box[2] - box[0], box[3] - box[1]]


def box_area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def round_box(box: list[float]) -> list[float]:
    return [round(float(value), 3) for value in box]


def union_box(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def diagnostic_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("diagnostic_id") or ""): row for row in rows if row.get("diagnostic_id")}


def candidate_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("candidate_id") or ""): row for row in rows if row.get("candidate_id")}


def frozen_page_keys(manifest_path: Path) -> set[str]:
    if not manifest_path.exists():
        return set()
    keys: set[str] = set()
    for row in read_jsonl(manifest_path):
        source_page_key = str(row.get("source_page_key") or "")
        if source_page_key:
            keys.add(source_page_key)
        render_path = row.get("render_path") or row.get("image_path")
        if render_path:
            keys.add(f"render:{Path(str(render_path)).stem}")
    return keys


def candidate_page_keys(candidate: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    pdf_stem = str(candidate.get("pdf_stem") or "")
    page_number = candidate.get("page_number")
    if pdf_stem and page_number not in (None, ""):
        try:
            keys.add(f"{safe_stem(pdf_stem)}:p{int(page_number) - 1:04d}")
        except ValueError:
            pass
    render_path = candidate.get("render_path")
    if render_path:
        keys.add(f"render:{Path(str(render_path)).stem}")
    return keys


def safe_stem(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value).strip("_")


def connected_components(edges: list[tuple[str, str]]) -> list[list[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    nodes: set[str] = set()
    for left, right in edges:
        graph[left].add(right)
        graph[right].add(left)
        nodes.update([left, right])
    components: list[list[str]] = []
    while nodes:
        start = nodes.pop()
        stack = [start]
        component = {start}
        while stack:
            current = stack.pop()
            for neighbor in graph[current]:
                if neighbor in nodes:
                    nodes.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return sorted(components, key=lambda item: (item[0], len(item)))


def validate_reviews(rows: list[dict[str, str]], allow_incomplete: bool) -> list[str]:
    errors: list[str] = []
    for row in rows:
        row_number = row.get("row_number") or "?"
        if row.get("review_status") != "reviewed":
            errors.append(f"row {row_number}: review_status is {row.get('review_status')!r}")
        if not row.get("review_decision"):
            errors.append(f"row {row_number}: missing review_decision")
    if errors and not allow_incomplete:
        raise ValueError("Reviewed CSV is incomplete:\n" + "\n".join(errors[:20]))
    return errors


def tight_bbox_for_review(review: dict[str, str], diagnostic: dict[str, Any] | None) -> list[float] | None:
    explicit = parse_bbox(review.get("corrected_bbox_xyxy"))
    if explicit is not None:
        return explicit
    metrics = diagnostic.get("metrics") if diagnostic else None
    if isinstance(metrics, dict) and isinstance(metrics.get("tight_member_bbox_xyxy"), list):
        return normalize_xyxy(metrics["tight_member_bbox_xyxy"])
    return None


def make_candidate_update(candidate: dict[str, Any], proposed_box: list[float]) -> dict[str, Any]:
    original_box = box_from_candidate(candidate)
    original_area = box_area(original_box)
    proposed_area = box_area(proposed_box)
    return {
        "source_candidate_id": candidate.get("candidate_id"),
        "original_bbox_xyxy": round_box(original_box),
        "proposed_bbox_xyxy": round_box(proposed_box),
        "proposed_bbox_xywh": round_box(xyxy_to_xywh(proposed_box)),
        "original_area": round(original_area, 3),
        "proposed_area": round(proposed_area, 3),
        "area_ratio_vs_original": None if original_area <= 0 else round(proposed_area / original_area, 6),
    }


def build_plan(
    diagnostic_rows: list[dict[str, Any]],
    review_rows: list[dict[str, str]],
    candidates: dict[str, dict[str, Any]],
    frozen_keys: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    diagnostics = diagnostic_by_id(diagnostic_rows)
    row_actions: list[dict[str, Any]] = []
    merge_edges: list[tuple[str, str]] = []
    candidate_evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_decision: Counter[str] = Counter()
    by_action: Counter[str] = Counter()
    blocked_reasons: Counter[str] = Counter()

    for review in review_rows:
        decision = review.get("review_decision") or ""
        by_decision[decision] += 1
        candidate_ids = split_ids(review.get("target_candidate_ids")) or split_ids(review.get("candidate_ids"))
        diagnostic = diagnostics.get(review.get("diagnostic_id") or "")
        action = "no_change"
        geometry_status = "not_applicable"
        proposed_bbox = None
        blocked_reason = ""

        if decision == "merge":
            action = "merge_component_edge"
            geometry_status = "union_of_source_candidate_boxes"
            if len(candidate_ids) >= 2:
                merge_edges.append((candidate_ids[0], candidate_ids[1]))
            else:
                blocked_reason = "merge_decision_has_fewer_than_two_candidates"
        elif decision == "suppress_duplicate":
            action = "suppress_duplicate"
            geometry_status = "no_geometry_change"
        elif decision in {"tighten", "reject_tighten"}:
            if decision == "tighten" and len(candidate_ids) == 1 and candidate_ids[0] in candidates:
                proposed_bbox = tight_bbox_for_review(review, diagnostic)
                if proposed_bbox is None:
                    action = "manual_geometry_required"
                    geometry_status = "missing_tight_bbox"
                    blocked_reason = "tighten_without_corrected_or_tight_member_bbox"
                else:
                    action = "tighten_bbox"
                    geometry_status = "proposed_bbox_from_review"
            else:
                action = "no_change"
                geometry_status = "rejected_tighten"
        elif decision == "tighten_adjust":
            action = "manual_geometry_required"
            geometry_status = "tighten_adjust_requires_reviewed_corrected_bbox"
            blocked_reason = "tighten_adjust_not_safe_to_apply_from_tight_member_bbox"
        elif decision == "expand":
            action = "manual_geometry_required"
            geometry_status = "expand_requires_same_cloud_extent"
            blocked_reason = "expand_needs_reviewed_full_cloud_geometry_or_merge_component"
        elif decision == "split":
            action = "manual_split_required"
            geometry_status = "split_requires_child_geometry"
            blocked_reason = "split_needs_child_candidate_geometry"
        elif decision in {"reject_merge", "reject_suppress", "ignore", "unclear"}:
            action = "no_change"
            geometry_status = f"{decision}_reviewed"
        else:
            action = "manual_review_required"
            geometry_status = "unknown_decision"
            blocked_reason = f"unknown_decision:{decision}"

        frozen_candidate_ids = [
            candidate_id
            for candidate_id in candidate_ids
            if candidate_id in candidates and candidate_page_keys(candidates[candidate_id]) & frozen_keys
        ]
        if frozen_candidate_ids:
            action = "blocked_frozen_page_guard"
            blocked_reason = "candidate_on_frozen_page"

        if blocked_reason:
            blocked_reasons[blocked_reason] += 1
        by_action[action] += 1

        row_action = {
            "schema": "cloudhammer_v2.postprocessing_dry_run_row_action.v1",
            "row_number": int(review.get("row_number") or 0),
            "diagnostic_id": review.get("diagnostic_id"),
            "diagnostic_family": review.get("diagnostic_family"),
            "source_page_key": review.get("source_page_key"),
            "candidate_ids": candidate_ids,
            "review_decision": decision,
            "proposed_action": action,
            "geometry_status": geometry_status,
            "blocked_reason": blocked_reason,
            "proposed_bbox_xyxy": round_box(proposed_bbox) if proposed_bbox else [],
            "review_notes": review.get("review_notes") or "",
        }
        row_actions.append(row_action)

        for candidate_id in candidate_ids:
            candidate_evidence[candidate_id].append(row_action)

    component_actions: list[dict[str, Any]] = []
    for index, component_ids in enumerate(connected_components(merge_edges), start=1):
        known_candidates = [candidates[candidate_id] for candidate_id in component_ids if candidate_id in candidates]
        boxes = [box_from_candidate(candidate) for candidate in known_candidates]
        expand_rows = [
            evidence
            for candidate_id in component_ids
            for evidence in candidate_evidence.get(candidate_id, [])
            if evidence["review_decision"] == "expand"
        ]
        split_rows = [
            evidence
            for candidate_id in component_ids
            for evidence in candidate_evidence.get(candidate_id, [])
            if evidence["review_decision"] in {"split", "tighten_adjust"}
        ]
        proposed_box = union_box(boxes) if boxes else None
        component_actions.append(
            {
                "schema": "cloudhammer_v2.postprocessing_dry_run_component_action.v1",
                "component_id": f"merge_component_{index:03d}",
                "source_candidate_ids": component_ids,
                "source_candidate_count": len(component_ids),
                "proposed_action": "merge_candidates",
                "proposed_bbox_xyxy": round_box(proposed_box) if proposed_box else [],
                "geometry_status": "union_only_needs_expand_review" if expand_rows else "union_of_source_candidate_boxes",
                "requires_manual_geometry": bool(expand_rows or split_rows),
                "review_row_numbers": sorted(
                    {
                        evidence["row_number"]
                        for candidate_id in component_ids
                        for evidence in candidate_evidence.get(candidate_id, [])
                        if evidence["review_decision"] == "merge"
                    }
                ),
                "blocking_or_followup_row_numbers": sorted(
                    {
                        evidence["row_number"]
                        for evidence in [*expand_rows, *split_rows]
                    }
                ),
                "notes": (
                    "Merge edge is reviewed, but one or more source candidates also have expand/split/tighten_adjust "
                    "evidence. Do not apply as final geometry without a reviewed full-cloud bbox."
                    if expand_rows or split_rows
                    else "Reviewed merge component; proposed bbox is union of source candidate boxes."
                ),
            }
        )

    candidate_actions: list[dict[str, Any]] = []
    for candidate_id, evidence_rows in sorted(candidate_evidence.items()):
        decisions = sorted({row["review_decision"] for row in evidence_rows})
        actions = sorted({row["proposed_action"] for row in evidence_rows})
        candidate = candidates.get(candidate_id)
        proposed_updates = [
            row for row in evidence_rows if row["proposed_action"] == "tighten_bbox" and row["proposed_bbox_xyxy"]
        ]
        candidate_actions.append(
            {
                "schema": "cloudhammer_v2.postprocessing_dry_run_candidate_action.v1",
                "candidate_id": candidate_id,
                "source_page_key": candidate.get("source_page_key") if candidate else None,
                "review_row_numbers": [row["row_number"] for row in evidence_rows],
                "review_decisions": decisions,
                "proposed_actions": actions,
                "candidate_known": candidate is not None,
                "has_conflicting_manual_geometry": any(
                    row["proposed_action"] in {"manual_geometry_required", "manual_split_required"} for row in evidence_rows
                ),
                "tighten_update": (
                    make_candidate_update(candidate, proposed_updates[-1]["proposed_bbox_xyxy"])
                    if candidate and proposed_updates
                    else None
                ),
                "notes": "Candidate-level rollup only; row/component plans are authoritative for dry-run review.",
            }
        )

    outputs = {
        "row_actions": sorted(row_actions, key=lambda row: row["row_number"]),
        "component_actions": component_actions,
        "candidate_actions": candidate_actions,
    }
    summary = {
        "schema": "cloudhammer_v2.postprocessing_dry_run_summary.v1",
        "review_rows": len(review_rows),
        "row_actions": len(row_actions),
        "component_actions": len(component_actions),
        "candidate_actions": len(candidate_actions),
        "by_review_decision": dict(sorted(by_decision.items())),
        "by_proposed_action": dict(sorted(by_action.items())),
        "blocked_or_manual_reasons": dict(sorted(blocked_reasons.items())),
        "guardrails": [
            "dry_run_only",
            "no_source_candidate_manifest_edits",
            "no_truth_label_edits",
            "no_eval_manifest_edits",
            "no_prediction_file_edits",
            "no_model_file_edits",
            "no_dataset_or_training_data_writes",
            "not_threshold_tuning",
        ],
    }
    return [*outputs["component_actions"], *outputs["candidate_actions"], *outputs["row_actions"]], summary


def markdown_summary(summary: dict[str, Any], output_dir: Path) -> str:
    lines = [
        "# Postprocessing Dry-Run Plan",
        "",
        "Status: dry-run only. This report proposes postprocessing actions from the reviewed diagnostic CSV.",
        "",
        "Safety: no labels, eval manifests, prediction files, model files, source candidate manifests, datasets, or training data were edited.",
        "",
        "## Counts",
        "",
        f"- review rows: `{summary['review_rows']}`",
        f"- row actions: `{summary['row_actions']}`",
        f"- merge components: `{summary['component_actions']}`",
        f"- candidate rollups: `{summary['candidate_actions']}`",
        "",
        "## Decisions",
        "",
    ]
    for key, value in summary["by_review_decision"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Proposed Action Types", ""])
    for key, value in summary["by_proposed_action"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Manual Or Blocked Reasons", ""])
    if summary["blocked_or_manual_reasons"]:
        for key, value in summary["blocked_or_manual_reasons"].items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- `{output_dir / 'postprocessing_dry_run_plan.jsonl'}`",
            f"- `{output_dir / 'postprocessing_dry_run_summary.json'}`",
            "",
            "Next step: inspect this dry-run plan before writing any explicit apply script.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a dry-run postprocessing action plan from reviewed diagnostic rows.")
    parser.add_argument("--diagnostic-dir", type=Path, default=DEFAULT_DIAGNOSTIC_DIR)
    parser.add_argument("--review-log", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--frozen-manifest", type=Path, default=DEFAULT_FROZEN_MANIFEST)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()

    diagnostic_dir = args.diagnostic_dir
    review_log = args.review_log or diagnostic_dir / "postprocessing_diagnostic_review_log.reviewed.csv"
    output_dir = args.output_dir or diagnostic_dir / "dry_run_postprocessor_20260505"
    summary = read_json(diagnostic_dir / "postprocessing_diagnostic_summary.json")
    diagnostic_rows = read_jsonl(diagnostic_dir / "postprocessing_diagnostic_candidates.jsonl")
    review_rows = read_csv(review_log)
    validate_reviews(review_rows, args.allow_incomplete)

    candidate_manifest = project_path(summary.get("source_candidate_manifest"))
    if candidate_manifest is None or not candidate_manifest.exists():
        raise FileNotFoundError(f"Candidate manifest not found: {summary.get('source_candidate_manifest')}")
    candidates = candidate_by_id(read_jsonl(candidate_manifest))
    frozen_keys = frozen_page_keys(args.frozen_manifest)

    plan_rows, plan_summary = build_plan(diagnostic_rows, review_rows, candidates, frozen_keys)
    plan_summary.update(
        {
            "diagnostic_dir": str(diagnostic_dir),
            "review_log": str(review_log),
            "source_candidate_manifest": str(candidate_manifest),
            "output_dir": str(output_dir),
            "frozen_manifest_guard": str(args.frozen_manifest),
        }
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "postprocessing_dry_run_plan.jsonl", plan_rows)
    write_json(output_dir / "postprocessing_dry_run_summary.json", plan_summary)
    (output_dir / "postprocessing_dry_run_summary.md").write_text(markdown_summary(plan_summary, output_dir), encoding="utf-8")

    print("Postprocessing dry-run plan")
    print(f"- review_rows: {plan_summary['review_rows']}")
    print(f"- component_actions: {plan_summary['component_actions']}")
    print(f"- candidate_actions: {plan_summary['candidate_actions']}")
    print(f"- output_dir: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
