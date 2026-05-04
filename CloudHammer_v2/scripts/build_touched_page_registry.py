from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
LEGACY_ROOT = PROJECT_ROOT / "CloudHammer"

DEFAULT_PAGE_MANIFEST = LEGACY_ROOT / "data" / "manifests" / "pages.jsonl"
DEFAULT_ELIGIBLE_PAGE_MANIFEST = (
    LEGACY_ROOT / "data" / "manifests" / "pages_standard_drawings_no_index_20260427.jsonl"
)
DEFAULT_TOUCHED_MANIFESTS = (
    LEGACY_ROOT
    / "data"
    / "manifests"
    / "reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl",
    LEGACY_ROOT / "data" / "manifests" / "source_controlled_small_corpus_20260502.jsonl",
    LEGACY_ROOT / "data" / "manifests" / "source_controlled_small_corpus_20260502.quasi_holdout.jsonl",
    LEGACY_ROOT / "data" / "manifests" / "fullpage_eval_sample_broad_deduped_20260428.jsonl",
)

REVISION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Revision[_ #.-]*1|Drawing[_ -]*Changes", re.IGNORECASE), "Revision #1 - Drawing Changes"),
    (re.compile(r"260309|Drawing[_ -]*Rev2|Rev[_ -]*2", re.IGNORECASE), "Revision #2 - Mod 5 grab bar supports"),
    (re.compile(r"260313|Rev[_ -]*3", re.IGNORECASE), "Revision #3 - EHRM Drawings"),
    (re.compile(r"260219|Rev[_ -]*4", re.IGNORECASE), "Revision #4 - Dental Air"),
    (re.compile(r"260303|Rev[_ -]*5|RFI[_ -]*126", re.IGNORECASE), "Revision #5 - RFI 126 - Concrete Repairs"),
    (re.compile(r"Revision[_ -]*Set[_ -]*7|Rev[_ -]*7|RFI[_ -]*141", re.IGNORECASE), "Revision #7 - RFI 141 - Deteriorated Attic Wood"),
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown_source"


def strip_hash_suffix(value: str) -> str:
    return re.sub(r"_[0-9a-fA-F]{8}$", "", value)


def resolve_project_path(value: str | Path | None) -> Path:
    if value is None or str(value) == "":
        return Path("")
    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve()
    parts = candidate.parts
    for anchor, root in (("CloudHammer", LEGACY_ROOT), ("revision_sets", PROJECT_ROOT / "revision_sets")):
        for index, part in enumerate(parts):
            if part.lower() == anchor.lower():
                relocated = root.joinpath(*parts[index + 1 :])
                if relocated.exists():
                    return relocated.resolve()
    return candidate


def row_id(row: dict[str, Any]) -> str:
    for key in ("cloud_roi_id", "candidate_id", "marker_seed_id"):
        if row.get(key):
            return str(row[key])
    for key in ("roi_image_path", "source_image_path", "image_path", "render_path", "page_image_path"):
        value = row.get(key)
        if value:
            return Path(str(value)).stem
    return "unknown"


def page_index_for_row(row: dict[str, Any]) -> int | None:
    for key in ("source_page_index", "page_index"):
        value = row.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                pass

    text = " ".join(
        str(row.get(key) or "")
        for key in ("cloud_roi_id", "roi_image_path", "source_image_path", "image_path", "render_path", "page_image_path")
    )
    match = re.search(r"_p(\d{4})(?:_|\.|$)", text)
    return int(match.group(1)) if match else None


def source_id_for_row(row: dict[str, Any]) -> str:
    if row.get("source_id"):
        return strip_hash_suffix(slug(str(row["source_id"])))

    pdf_path = row.get("pdf_path") or row.get("source_pdf_path")
    if pdf_path:
        return strip_hash_suffix(slug(Path(str(pdf_path)).stem))

    for key in ("pdf_stem", "source_pdf_stem"):
        if row.get(key):
            return strip_hash_suffix(slug(str(row[key])))

    text = row_id(row)
    match = re.match(r"(?P<source>.+?)_p\d{4}(?:_|$)", text)
    if match:
        return strip_hash_suffix(slug(match.group("source")))

    for key in ("roi_image_path", "source_image_path", "image_path", "render_path", "page_image_path"):
        value = row.get(key)
        if not value:
            continue
        stem = Path(str(value)).stem
        match = re.match(r"(?P<source>.+?)_p\d{4}(?:_|$)", stem)
        if match:
            return strip_hash_suffix(slug(match.group("source")))
        return strip_hash_suffix(slug(stem))

    return "unknown_source"


def revision_group_for_row(row: dict[str, Any]) -> str:
    for key in ("revision_group", "revision"):
        value = row.get(key)
        if isinstance(value, str) and value.startswith("Revision #"):
            return value

    pdf_path = str(row.get("pdf_path") or row.get("source_pdf_path") or "")
    for part in re.split(r"[\\/]+", pdf_path):
        if part.startswith("Revision #"):
            return part

    text = " ".join(
        str(value)
        for value in (
            pdf_path,
            row.get("pdf_stem"),
            row.get("source_pdf_stem"),
            row.get("source_id"),
            row_id(row),
        )
        if value
    )
    for pattern, revision in REVISION_PATTERNS:
        if pattern.search(text):
            return revision
    return "unknown"


def source_page_key_for_row(row: dict[str, Any]) -> str | None:
    page_index = page_index_for_row(row)
    if page_index is None:
        return None
    return f"{source_id_for_row(row)}:p{page_index:04d}"


def role_for_manifest(path: Path) -> str:
    name = path.name.lower()
    if "quasi_holdout" in name:
        return "quasi_holdout"
    if "source_controlled" in name:
        return "source_controlled_train_val"
    if "fullpage_eval" in name:
        return "debug_eval"
    if "reviewed_plus" in name:
        return "continuity_training"
    return path.stem


def build_touch_index(paths: list[Path]) -> tuple[dict[str, Counter[str]], list[dict[str, Any]]]:
    touches: dict[str, Counter[str]] = defaultdict(Counter)
    unknown_rows: list[dict[str, Any]] = []
    for path in paths:
        role = role_for_manifest(path)
        for row in read_jsonl(path):
            key = source_page_key_for_row(row)
            if key is None:
                unknown_rows.append({"manifest": str(path), "role": role, "row_id": row_id(row)})
                continue
            touches[key][role] += 1
    return touches, unknown_rows


def page_registry_row(row: dict[str, Any], eligible_keys: set[str], touches: dict[str, Counter[str]]) -> dict[str, Any]:
    key = source_page_key_for_row(row)
    render_path = resolve_project_path(row.get("render_path"))
    pdf_path = resolve_project_path(row.get("pdf_path"))
    guards: list[str] = []
    if key is None:
        guards.append("missing_source_page_key")
    if key not in eligible_keys:
        guards.append("not_eligible_standard_drawing")
    if key and touches.get(key):
        guards.append("already_touched_by_training_or_eval")
    if not render_path.exists():
        guards.append("missing_render_path")
    if row.get("page_kind") != "drawing":
        guards.append("not_drawing_page")

    page_index = page_index_for_row(row)
    return {
        "schema": "cloudhammer_v2.touched_page_registry.row.v1",
        "source_page_key": key,
        "source_id": source_id_for_row(row),
        "revision_group": revision_group_for_row(row),
        "pdf_stem": row.get("pdf_stem") or Path(str(row.get("pdf_path") or "")).stem,
        "pdf_path": str(pdf_path),
        "render_path": str(render_path),
        "page_index": page_index,
        "page_number": row.get("page_number"),
        "page_kind": row.get("page_kind"),
        "sheet_id": row.get("sheet_id") or "",
        "sheet_title": row.get("sheet_title") or "",
        "width_px": row.get("width_px"),
        "height_px": row.get("height_px"),
        "eligible_standard_drawing": key in eligible_keys if key else False,
        "render_exists": render_path.exists(),
        "touch_roles": dict(touches.get(key, Counter())) if key else {},
        "touched": bool(key and touches.get(key)),
        "freeze_guard_reasons": guards,
        "eligible_for_page_disjoint_real": not guards,
    }


def select_page_disjoint_rows(candidates: list[dict[str, Any]], max_pages: int) -> list[dict[str, Any]]:
    ordered = sorted(
        candidates,
        key=lambda row: (
            str(row.get("revision_group") or ""),
            str(row.get("source_id") or ""),
            int(row.get("page_index") or 0),
        ),
    )
    if max_pages <= 0 or len(ordered) <= max_pages:
        return ordered

    by_revision: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        by_revision[str(row.get("revision_group") or "unknown")].append(row)

    selected: list[dict[str, Any]] = []
    revisions = sorted(by_revision)
    while len(selected) < max_pages and any(by_revision.values()):
        for revision in revisions:
            bucket = by_revision[revision]
            if not bucket:
                continue
            selected.append(bucket.pop(0))
            if len(selected) >= max_pages:
                break
    return selected


def eval_manifest_row(row: dict[str, Any]) -> dict[str, Any]:
    output = {
        **row,
        "eval_subset": "page_disjoint_real",
        "frozen_at": str(date.today()),
        "freeze_policy": "page_disjoint_real_v1",
        "label_status": "unlabeled",
        "label_path": "",
        "gpt_label_metadata_path": "",
        "gpt_review_overlay_path": "",
    }
    return output


def markdown_summary(summary: dict[str, Any], frozen_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Touched Page Registry Dry Run",
        "",
        f"Generated: `{summary['generated_at']}`",
        f"Pages in registry: `{summary['registry_pages']}`",
        f"Eligible standard drawing pages: `{summary['eligible_standard_drawing_pages']}`",
        f"Touched eligible pages: `{summary['touched_eligible_pages']}`",
        f"Page-disjoint candidates: `{summary['page_disjoint_candidate_pages']}`",
        f"Frozen page_disjoint_real pages: `{summary['frozen_page_disjoint_real_pages']}`",
        "",
        "## Frozen Pages",
        "",
        "| Source Page | Revision | Sheet | Title | Render |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in frozen_rows:
        lines.append(
            f"| `{row['source_page_key']}` | `{row['revision_group']}` | `{row.get('sheet_id') or ''}` | "
            f"{row.get('sheet_title') or ''} | `{Path(str(row['render_path'])).name}` |"
        )
    lines.extend(["", "## Touch Roles", ""])
    for role, count in summary["touch_role_counts"].items():
        lines.append(f"- `{role}`: `{count}` rows")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build CloudHammer_v2 touched-page registry and page_disjoint_real manifest.")
    parser.add_argument("--page-manifest", type=Path, default=DEFAULT_PAGE_MANIFEST)
    parser.add_argument("--eligible-page-manifest", type=Path, default=DEFAULT_ELIGIBLE_PAGE_MANIFEST)
    parser.add_argument("--touched-manifest", type=Path, action="append", default=[])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=V2_ROOT / "outputs" / "touched_page_registry_20260502",
    )
    parser.add_argument(
        "--eval-dir",
        type=Path,
        default=V2_ROOT / "eval" / "page_disjoint_real",
    )
    parser.add_argument(
        "--max-frozen-pages",
        type=int,
        default=0,
        help="0 means freeze all page-disjoint candidates.",
    )
    args = parser.parse_args()

    touched_paths = args.touched_manifest or list(DEFAULT_TOUCHED_MANIFESTS)
    eligible_rows = read_jsonl(args.eligible_page_manifest)
    eligible_keys = {key for row in eligible_rows if (key := source_page_key_for_row(row))}
    touches, unknown_touches = build_touch_index(touched_paths)

    registry_rows = [
        page_registry_row(row, eligible_keys, touches)
        for row in read_jsonl(args.page_manifest)
    ]
    registry_rows = sorted(
        registry_rows,
        key=lambda row: (
            str(row.get("revision_group") or ""),
            str(row.get("source_id") or ""),
            int(row.get("page_index") or 0),
        ),
    )
    candidates = [row for row in registry_rows if row["eligible_for_page_disjoint_real"]]
    frozen_rows = select_page_disjoint_rows(candidates, args.max_frozen_pages)
    eval_rows = [eval_manifest_row(row) for row in frozen_rows]

    touch_role_counts: Counter[str] = Counter()
    for counter in touches.values():
        touch_role_counts.update(counter)
    touched_eligible = sum(1 for row in registry_rows if row["eligible_standard_drawing"] and row["touched"])
    summary = {
        "schema": "cloudhammer_v2.touched_page_registry.summary.v1",
        "generated_at": str(date.today()),
        "page_manifest": str(args.page_manifest),
        "eligible_page_manifest": str(args.eligible_page_manifest),
        "touched_manifests": [str(path) for path in touched_paths],
        "registry_pages": len(registry_rows),
        "eligible_standard_drawing_pages": len(eligible_keys),
        "touched_source_pages": len(touches),
        "touched_eligible_pages": touched_eligible,
        "page_disjoint_candidate_pages": len(candidates),
        "frozen_page_disjoint_real_pages": len(frozen_rows),
        "touch_role_counts": dict(touch_role_counts),
        "candidate_revision_counts": dict(Counter(row["revision_group"] for row in candidates)),
        "frozen_revision_counts": dict(Counter(row["revision_group"] for row in frozen_rows)),
        "unknown_touch_rows": len(unknown_touches),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.eval_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "touched_page_registry.jsonl", registry_rows)
    write_json(args.output_dir / "touched_page_registry_summary.json", summary)
    write_jsonl(args.output_dir / "unknown_touch_rows.jsonl", unknown_touches)
    (args.output_dir / "touched_page_registry_summary.md").write_text(
        markdown_summary(summary, frozen_rows),
        encoding="utf-8",
    )

    write_jsonl(args.eval_dir / "page_disjoint_real_candidates.jsonl", candidates)
    write_jsonl(args.eval_dir / "page_disjoint_real_manifest.jsonl", eval_rows)
    write_json(args.eval_dir / "page_disjoint_real_selection_summary.json", summary)
    (args.eval_dir / "page_disjoint_real_selection_summary.md").write_text(
        markdown_summary(summary, frozen_rows),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "registry_pages": summary["registry_pages"],
                "eligible_standard_drawing_pages": summary["eligible_standard_drawing_pages"],
                "page_disjoint_candidate_pages": summary["page_disjoint_candidate_pages"],
                "frozen_page_disjoint_real_pages": summary["frozen_page_disjoint_real_pages"],
                "frozen_revision_counts": summary["frozen_revision_counts"],
            },
            indent=2,
        )
    )
    print(f"wrote {args.output_dir / 'touched_page_registry_summary.md'}")
    print(f"wrote {args.eval_dir / 'page_disjoint_real_manifest.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
