from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.keynote_legends import scan_keynote_legends, write_outputs  # noqa: E402


DEFAULT_INPUT_DIR = PROJECT_ROOT / "revision_sets" / "Revision #1 - Drawing Changes"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "test_tmp" / "keynote_legend_finder"


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = (args.output_dir or default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    regions, rows = scan_keynote_legends(input_dir)
    output_files = write_outputs(output_dir=output_dir, input_dir=input_dir, regions=regions, rows=rows)
    print(f"Keynote legend finder complete: {output_dir}")
    for label, path in output_files.items():
        print(f"- {label}: {path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find same-sheet keynote legend rows by locating KEYNOTE headers, "
            "marker labels, and KEYED NOTES numbered-list definitions."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def default_output_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return DEFAULT_OUTPUT_ROOT / stamp


if __name__ == "__main__":
    raise SystemExit(main())
