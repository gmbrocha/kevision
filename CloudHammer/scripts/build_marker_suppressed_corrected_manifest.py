from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs" / "whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428"
DEFAULT_SUPPRESSION_DIR = DEFAULT_RUN / "marker_anchor_suppression_v1"
DEFAULT_OUTPUT_DIR = DEFAULT_RUN / "corrected_candidates_with_rescue_marker_suppressed_v1"


def summarize(
    retained: list[dict[str, Any]],
    suppressed: list[dict[str, Any]],
    suppression_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    return {
        "schema": "cloudhammer.marker_suppressed_corrected_candidates.v1",
        "suppression_dir": str(suppression_dir),
        "output_dir": str(output_dir),
        "corrected_candidates": len(retained),
        "marker_anchor_suppressed_candidates": len(suppressed),
        "by_correction_source": dict(Counter(str(row.get("correction_source")) for row in retained)),
        "by_size_bucket": dict(Counter(str(row.get("size_bucket")) for row in retained)),
        "by_confidence_tier": dict(Counter(str(row.get("confidence_tier")) for row in retained)),
        "suppressed_by_reason": dict(Counter(str(row.get("marker_anchor_suppression_reason")) for row in suppressed)),
        "suppressed_by_false_positive_reason": dict(
            Counter(str(row.get("marker_fp_false_positive_reason") or "generic_false_positive") for row in suppressed)
        ),
    }


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Marker-Suppressed Corrected Whole Cloud Candidates",
        "",
        f"Suppression dir: `{summary['suppression_dir']}`",
        f"Output dir: `{summary['output_dir']}`",
        "",
        "## Totals",
        "",
        f"- corrected candidates retained: `{summary['corrected_candidates']}`",
        f"- marker-anchor suppressed candidates: `{summary['marker_anchor_suppressed_candidates']}`",
        "",
        "## Retained By Source",
        "",
        "| Source | Count |",
        "| --- | ---: |",
    ]
    for source, count in sorted(summary["by_correction_source"].items()):
        lines.append(f"| `{source}` | `{count}` |")
    lines.extend(["", "## Suppressed By False-Positive Reason", "", "| Reason | Count |", "| --- | ---: |"])
    for reason, count in sorted(summary["suppressed_by_false_positive_reason"].items()):
        lines.append(f"| `{reason}` | `{count}` |")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `corrected_whole_cloud_candidates.jsonl`: retained corrected candidates after marker-anchor suppression",
            "- `marker_anchor_suppressed_quarantine.jsonl`: reviewed/calibrated marker-anchor suppressions",
            "- `marker_suppressed_corrected_summary.json`: machine-readable summary",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build final corrected candidate manifest after marker-anchor suppression.")
    parser.add_argument("--suppression-dir", type=Path, default=DEFAULT_SUPPRESSION_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    suppression_dir = args.suppression_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    retained = list(read_jsonl(suppression_dir / "marker_anchor_retained_candidates.jsonl"))
    suppressed = list(read_jsonl(suppression_dir / "marker_anchor_suppressed_candidates.jsonl"))

    write_jsonl(output_dir / "corrected_whole_cloud_candidates.jsonl", retained)
    write_jsonl(output_dir / "marker_anchor_suppressed_quarantine.jsonl", suppressed)
    summary = summarize(retained, suppressed, suppression_dir, output_dir)
    write_json(output_dir / "marker_suppressed_corrected_summary.json", summary)
    write_markdown(summary, output_dir / "marker_suppressed_corrected_summary.md")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
