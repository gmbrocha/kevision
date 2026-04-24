from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.bootstrap.cloud_roi_extract import (
    DEFAULT_BLANK_INK_RATIO,
    DEFAULT_CROP_SIZE,
    DEFAULT_CROP_SIZE_LARGE,
    DEFAULT_DEDUPE_IOU,
    extract_cloud_rois,
)
from cloudhammer.config import CloudHammerConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract cloud/scallop candidate ROI images.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--pages-manifest", type=Path, default=None)
    parser.add_argument("--marker-manifest", type=Path, default=None)
    parser.add_argument("--delta-json-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--target-revision-digit", type=str, default=None)
    parser.add_argument("--target-revision-map", type=Path, default=None)
    parser.add_argument("--include-nonmatching-markers", action="store_true")
    parser.add_argument("--crop-size", type=int, default=DEFAULT_CROP_SIZE)
    parser.add_argument("--crop-size-large", type=int, default=DEFAULT_CROP_SIZE_LARGE)
    parser.add_argument("--include-diagonals", action="store_true")
    parser.add_argument("--dedupe-iou", type=float, default=DEFAULT_DEDUPE_IOU)
    parser.add_argument("--blank-ink-threshold", type=float, default=DEFAULT_BLANK_INK_RATIO)
    parser.add_argument("--include-title-block", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.crop_size < 800:
        parser.error("--crop-size must be at least 800")
    if args.crop_size_large and args.crop_size_large < args.crop_size:
        parser.error("--crop-size-large must be greater than or equal to --crop-size")
    if not 0.0 <= args.dedupe_iou <= 1.0:
        parser.error("--dedupe-iou must be between 0 and 1")

    cfg = CloudHammerConfig.load(args.config)
    count = extract_cloud_rois(
        cfg,
        pages_manifest=args.pages_manifest,
        marker_manifest=args.marker_manifest,
        target_revision_digit=args.target_revision_digit,
        target_revision_map=args.target_revision_map,
        include_nonmatching_markers=args.include_nonmatching_markers,
        delta_json_dir=args.delta_json_dir,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        limit=args.limit,
        crop_size=args.crop_size,
        crop_size_large=args.crop_size_large,
        include_diagonals=args.include_diagonals,
        dedupe_iou=args.dedupe_iou,
        blank_ink_threshold=args.blank_ink_threshold,
        skip_title_block=not args.include_title_block,
        overwrite=args.overwrite,
    )
    print(f"wrote {count} cloud ROI rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
