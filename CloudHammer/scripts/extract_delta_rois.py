from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.bootstrap.roi_extract import extract_rois
from cloudhammer.config import CloudHammerConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract legacy revision-marker context ROI images.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--pages-manifest", type=Path, default=None)
    parser.add_argument("--delta-json-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    cfg = CloudHammerConfig.load(args.config)
    count = extract_rois(
        cfg,
        pages_manifest=args.pages_manifest,
        delta_json_dir=args.delta_json_dir,
        limit=args.limit,
    )
    print(f"wrote {count} ROI rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
