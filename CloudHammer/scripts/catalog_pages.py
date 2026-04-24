from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.config import CloudHammerConfig
from cloudhammer.page_catalog import catalog_pages


def main() -> int:
    parser = argparse.ArgumentParser(description="Catalog and optionally render drawing pages.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--revision-sets", type=Path, default=Path(__file__).resolve().parents[2] / "revision_sets")
    parser.add_argument("--manifest-out", type=Path, default=None)
    parser.add_argument("--no-render", action="store_true", help="Write page metadata without rendering PNGs.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing rendered page PNGs.")
    parser.add_argument("--limit", type=int, default=None, help="Limit drawing pages processed.")
    parser.add_argument("--only-pdf", type=str, default=None, help="Substring filter for source PDFs.")
    parser.add_argument("--page-index", type=int, default=None, help="Only catalog this zero-indexed page.")
    args = parser.parse_args()

    cfg = CloudHammerConfig.load(args.config)
    count = catalog_pages(
        revision_sets_dir=args.revision_sets.resolve(),
        cfg=cfg,
        render=not args.no_render,
        overwrite=args.overwrite,
        limit=args.limit,
        only_pdf=args.only_pdf,
        only_page_index=args.page_index,
        manifest_path=args.manifest_out,
    )
    print(f"wrote {count} page rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
