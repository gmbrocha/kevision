from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.config import CloudHammerConfig
from cloudhammer.train.trainer import train_roi_detector


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the ROI cloud detector.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--roi-manifest", type=Path, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--imgsz", type=int, default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch", type=int, default=None)
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--name", type=str, default="cloudhammer_roi")
    args = parser.parse_args()

    cfg = CloudHammerConfig.load(args.config)
    train_roi_detector(
        cfg,
        roi_manifest_path=args.roi_manifest,
        model_name=args.model,
        imgsz=args.imgsz,
        epochs=args.epochs,
        batch=args.batch,
        dataset_dir=args.dataset_dir,
        run_name=args.name,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
