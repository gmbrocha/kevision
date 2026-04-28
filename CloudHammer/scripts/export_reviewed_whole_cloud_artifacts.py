from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs" / "whole_cloud_candidates_broad_deduped_lowconf_context_20260428"
DEFAULT_REVIEW_ANALYSIS = DEFAULT_RUN / "review_analysis"
DEFAULT_ACCEPTED_MANIFEST = DEFAULT_REVIEW_ANALYSIS / "accepted_candidates.jsonl"
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "reviewed_artifacts"


def safe_path_part(value: str, max_length: int = 96) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = "unknown"
    return cleaned[:max_length].rstrip(" .")


def resolve_cloudhammer_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.exists():
        return path.resolve()
    parts = path.parts
    for index, part in enumerate(parts):
        if part.lower() == "cloudhammer":
            relocated = ROOT.joinpath(*parts[index + 1 :])
            if relocated.exists():
                return relocated.resolve()
    return path


def copy_candidate_crop(row: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    source = resolve_cloudhammer_path(str(row["crop_image_path"]))
    if not source.exists():
        raise FileNotFoundError(f"Missing candidate crop: {source}")

    pdf_stem = safe_path_part(str(row.get("pdf_stem") or Path(str(row.get("pdf_path") or "unknown")).stem))
    suffix = source.suffix.lower() or ".png"
    destination = output_dir / "accepted_crops" / pdf_stem / f"{safe_path_part(str(row['candidate_id']))}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

    artifact_row = dict(row)
    artifact_row["artifact_crop_path"] = str(destination)
    artifact_row["source_crop_image_path"] = str(source)
    return artifact_row


def summarize(rows: list[dict[str, Any]], output_dir: Path, copied_count: int) -> dict[str, Any]:
    return {
        "schema": "cloudhammer.reviewed_whole_cloud_artifacts.v1",
        "output_dir": str(output_dir),
        "accepted_candidates": len(rows),
        "copied_crops": copied_count,
        "by_size_bucket": dict(Counter(str(row.get("size_bucket") or "unknown") for row in rows)),
        "by_confidence_tier": dict(Counter(str(row.get("confidence_tier") or "unknown") for row in rows)),
        "by_pdf_stem": dict(Counter(str(row.get("pdf_stem") or "unknown") for row in rows)),
    }


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Reviewed Whole Cloud Artifacts",
        "",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Totals",
        "",
        f"- accepted candidates: `{summary['accepted_candidates']}`",
        f"- copied crops: `{summary['copied_crops']}`",
        "",
        "## Size Buckets",
        "",
        "| Bucket | Count |",
        "| --- | ---: |",
    ]
    for bucket, count in sorted(summary["by_size_bucket"].items()):
        lines.append(f"| `{bucket}` | `{count}` |")

    lines.extend(["", "## Confidence Tiers", "", "| Tier | Count |", "| --- | ---: |"])
    for tier, count in sorted(summary["by_confidence_tier"].items()):
        lines.append(f"| `{tier}` | `{count}` |")

    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `accepted_crops/`: reviewed crop images safe to treat as real whole-cloud candidates",
            "- `accepted_whole_cloud_candidates.jsonl`: accepted candidates with copied artifact paths",
            "- `feedback_false_positive_candidates.jsonl`: reviewed false positives",
            "- `feedback_overmerged_candidates.jsonl`: reviewed overmerged candidates",
            "- `feedback_partial_candidates.jsonl`: reviewed partial candidates",
            "- `feedback_issue_candidates.jsonl`: all reviewed non-accept candidates",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_feedback_manifest(review_analysis_dir: Path, output_dir: Path, name: str) -> int:
    source = review_analysis_dir / name
    if not source.exists():
        return 0
    rows = list(read_jsonl(source))
    write_jsonl(output_dir / f"feedback_{name}", rows)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export reviewed accepted whole-cloud crops and feedback manifests.")
    parser.add_argument("--accepted-manifest", type=Path, default=DEFAULT_ACCEPTED_MANIFEST)
    parser.add_argument("--review-analysis-dir", type=Path, default=DEFAULT_REVIEW_ANALYSIS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    accepted_manifest = args.accepted_manifest.resolve()
    review_analysis_dir = args.review_analysis_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    accepted_rows = list(read_jsonl(accepted_manifest))
    artifact_rows = [copy_candidate_crop(row, output_dir) for row in accepted_rows]
    write_jsonl(output_dir / "accepted_whole_cloud_candidates.jsonl", artifact_rows)

    feedback_counts = {
        name: copy_feedback_manifest(review_analysis_dir, output_dir, name)
        for name in [
            "false_positive_candidates.jsonl",
            "overmerged_candidates.jsonl",
            "partial_candidates.jsonl",
            "issue_candidates.jsonl",
        ]
    }
    summary = summarize(artifact_rows, output_dir, copied_count=len(artifact_rows))
    summary["accepted_manifest"] = str(accepted_manifest)
    summary["review_analysis_dir"] = str(review_analysis_dir)
    summary["feedback_counts"] = feedback_counts

    write_json(output_dir / "reviewed_artifact_summary.json", summary)
    write_markdown(summary, output_dir / "reviewed_artifact_summary.md")

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "accepted_candidates": len(artifact_rows),
                "feedback_counts": feedback_counts,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
