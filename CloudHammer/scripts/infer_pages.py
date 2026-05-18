from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.config import CloudHammerConfig
from cloudhammer.infer.detect import infer_pages_from_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Run tiled full-page cloud inference.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--pages-manifest", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-pdf-stem", type=str, default=None)
    parser.add_argument("--no-crops", action="store_true", help="Skip fragment crop debug artifacts.")
    parser.add_argument("--no-overlays", action="store_true", help="Skip model detection overlay debug artifacts.")
    args = parser.parse_args()

    cfg = CloudHammerConfig.load(args.config)
    written = infer_pages_from_manifest(
        cfg,
        args.model,
        pages_manifest=args.pages_manifest,
        limit=args.limit,
        only_pdf_stem=args.only_pdf_stem,
        write_fragment_crops=not args.no_crops,
        write_overlays=not args.no_overlays,
    )
    for pdf_stem, output_path in written.items():
        print(f"{pdf_stem}: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
