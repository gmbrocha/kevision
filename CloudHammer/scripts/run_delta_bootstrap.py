from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.bootstrap.delta_stack import run_bootstrap_from_manifest
from cloudhammer.config import CloudHammerConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the wrapped legacy delta stack for drawing pages.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--pages-manifest", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--target-digit", type=str, default=None)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    cfg = CloudHammerConfig.load(args.config)
    count = run_bootstrap_from_manifest(
        cfg,
        pages_manifest=args.pages_manifest,
        limit=args.limit,
        target_digit=args.target_digit,
        workers=args.workers,
        overwrite=args.overwrite,
    )
    print(f"manifest contains {count} delta pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
