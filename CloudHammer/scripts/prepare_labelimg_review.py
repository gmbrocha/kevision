from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.config import CloudHammerConfig
from cloudhammer.prelabel.review_prep import copy_unreviewed_labels_for_labelimg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy API YOLO prelabel txt files into the reviewed LabelImg save directory."
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--source-dir", type=Path, default=None)
    parser.add_argument("--reviewed-dir", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--class-name", default="cloud_motif")
    args = parser.parse_args()

    cfg = CloudHammerConfig.load(args.config)
    result = copy_unreviewed_labels_for_labelimg(
        cfg,
        source_dir=args.source_dir,
        reviewed_dir=args.reviewed_dir,
        overwrite=args.overwrite,
        class_name=args.class_name,
    )
    image_dir = cfg.path("cloud_roi_images")
    reviewed_dir = args.reviewed_dir.resolve() if args.reviewed_dir else cfg.path("cloud_labels_reviewed")
    print(
        "labelimg review prep: "
        f"copied={result['copied']} skipped={result['skipped']} "
        f"source_txt={result['source_count']} image_dir={image_dir} save_dir={reviewed_dir}"
    )
    print("LabelImg config: image dir=data/cloud_roi_images save dir=data/cloud_labels_reviewed format=YOLO")
    print("Wrote LabelImg YOLO class list: data/cloud_labels_reviewed/classes.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
