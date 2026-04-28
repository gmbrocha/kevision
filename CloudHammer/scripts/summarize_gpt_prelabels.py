from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.prelabel.gpt_review_queue import read_jsonl, summarize_predictions


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize GPT prelabel predictions without modifying them.")
    parser.add_argument("predictions", type=Path, help="Path to predictions.jsonl")
    parser.add_argument("--manifest", type=Path, default=None, help="Optional source queue manifest for completeness checks")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON summary output path")
    args = parser.parse_args()

    predictions = read_jsonl(args.predictions)
    manifest = read_jsonl(args.manifest) if args.manifest is not None else None
    summary = summarize_predictions(predictions, manifest)
    text = json.dumps(summary, indent=2, sort_keys=True)
    print(text)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
