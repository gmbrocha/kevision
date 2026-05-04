from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.data.source_control import audit_sources
from cloudhammer.manifests import read_jsonl, write_json


ROOT = Path(__file__).resolve().parents[1]


def _read_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(read_jsonl(path))
    return rows


def _table_pairs(items: list[list[Any]] | list[tuple[Any, Any]], *, limit: int = 20) -> str:
    lines = ["| Key | Rows |", "| --- | ---: |"]
    for key, count in items[:limit]:
        lines.append(f"| `{key}` | {count} |")
    return "\n".join(lines)


def _markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# CloudHammer Source Audit",
        "",
        f"- Rows: {summary['rows']}",
        f"- Source families: {summary['source_count']}",
        f"- Source pages: {summary['source_page_count']}",
        f"- Mixed train/val/test source families: {len(summary['mixed_split_sources'])}",
        f"- Mixed train/val/test source pages: {len(summary['mixed_split_source_pages'])}",
    ]
    if "eval_rows" in summary:
        lines.extend(
            [
                f"- Eval rows: {summary['eval_rows']}",
                f"- Eval source-family overlap with training rows: {summary['eval_source_overlap_count']}",
                f"- Eval source-page overlap with training rows: {summary['eval_source_page_overlap_count']}",
            ]
        )
    lines.extend(["", "## Revision Concentration", ""])
    lines.append(_table_pairs(list(summary["revision_groups"].items())))
    lines.extend(["", "## Top Source Families", ""])
    lines.append(_table_pairs(summary["top_sources"]))
    lines.extend(["", "## Top Source Pages", ""])
    lines.append(_table_pairs(summary["top_source_pages"]))
    if summary["mixed_split_sources"]:
        lines.extend(["", "## Split Leakage: Source Families", ""])
        for source, split_counts in list(summary["mixed_split_sources"].items())[:50]:
            lines.append(f"- `{source}`: {split_counts}")
    if summary["mixed_split_source_pages"]:
        lines.extend(["", "## Split Leakage: Source Pages", ""])
        for page, split_counts in list(summary["mixed_split_source_pages"].items())[:50]:
            lines.append(f"- `{page}`: {split_counts}")
    if summary.get("eval_source_page_overlap"):
        lines.extend(["", "## Eval Source-Page Overlap", ""])
        for page in summary["eval_source_page_overlap"][:50]:
            lines.append(f"- `{page}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit CloudHammer manifest source/page-family concentration and leakage.")
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        default=[],
        help="Training/reviewed manifest to audit. Can be repeated.",
    )
    parser.add_argument(
        "--eval-manifest",
        type=Path,
        action="append",
        default=[],
        help="Eval/debug manifest to compare for source/page overlap. Can be repeated.",
    )
    parser.add_argument("--output-json", type=Path, default=ROOT / "runs" / "source_audit" / "source_audit_summary.json")
    parser.add_argument("--output-md", type=Path, default=ROOT / "runs" / "source_audit" / "source_audit_summary.md")
    args = parser.parse_args()

    manifest_paths = args.manifest or [
        ROOT / "data" / "manifests" / "reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl"
    ]
    rows = _read_rows(manifest_paths)
    eval_rows = _read_rows(args.eval_manifest) if args.eval_manifest else None
    summary = audit_sources(rows, eval_rows)
    summary["manifests"] = [str(path) for path in manifest_paths]
    summary["eval_manifests"] = [str(path) for path in args.eval_manifest]

    write_json(args.output_json, summary)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(_markdown(summary), encoding="utf-8")

    print(json.dumps({key: summary[key] for key in ("rows", "source_count", "source_page_count")}, indent=2))
    if "eval_source_page_overlap_count" in summary:
        print(f"eval source-page overlap: {summary['eval_source_page_overlap_count']} / {summary['eval_rows']}")
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
