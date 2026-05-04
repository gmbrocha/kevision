from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudhammer.manifests import read_jsonl, write_json
from cloudhammer.runtime import configure_local_artifact_cache
from cloudhammer.config import CloudHammerConfig


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "manifests" / "marker_fp_hard_negatives_20260502.jsonl"


def resolve_cloudhammer_path(value: str | Path | None) -> Path:
    if value is None or str(value) == "":
        return Path("")
    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve()
    parts = candidate.parts
    for index, part in enumerate(parts):
        if part.lower() == "cloudhammer":
            relocated = ROOT.joinpath(*parts[index + 1 :])
            if relocated.exists():
                return relocated.resolve()
    return candidate


def image_path_for(row: dict[str, Any]) -> Path:
    return resolve_cloudhammer_path(row.get("roi_image_path") or row.get("crop_image_path"))


def model_name(path: Path) -> str:
    parts = path.parts
    if "runs" in [part.lower() for part in parts]:
        for index, part in enumerate(parts):
            if part.lower() == "runs" and index + 1 < len(parts):
                return parts[index + 1]
    return path.stem


def evaluate_model(model_path: Path, image_paths: list[str], thresholds: list[float], imgsz: int) -> dict[str, Any]:
    try:
        from ultralytics import YOLO  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("ultralytics is not installed. Use the project .venv or install requirements-train.txt.") from exc

    model = YOLO(str(model_path))
    results_by_threshold: dict[str, Any] = {}
    for threshold in thresholds:
        hit_images = 0
        total_boxes = 0
        max_confidence = 0.0
        for result in model.predict(image_paths, conf=threshold, imgsz=imgsz, verbose=False, stream=True):
            box_count = 0 if result.boxes is None else len(result.boxes)
            if box_count:
                hit_images += 1
                total_boxes += box_count
                max_confidence = max(max_confidence, float(result.boxes.conf.max().item()))
        results_by_threshold[f"{threshold:.2f}"] = {
            "hit_images": hit_images,
            "total_images": len(image_paths),
            "total_boxes": total_boxes,
            "max_confidence": round(max_confidence, 6),
            "hit_rate": round(hit_images / len(image_paths), 6) if image_paths else 0.0,
        }
    return {
        "model": str(model_path.resolve()),
        "model_name": model_name(model_path),
        "thresholds": results_by_threshold,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate model false hits on reviewed hard-negative crops.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--model", type=Path, action="append", required=True)
    parser.add_argument("--threshold", type=float, action="append", default=[])
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    cfg = CloudHammerConfig.load(args.config)
    configure_local_artifact_cache(cfg)

    rows = list(read_jsonl(args.manifest.resolve()))
    image_paths = [str(image_path_for(row)) for row in rows if image_path_for(row).exists()]
    missing_images = len(rows) - len(image_paths)
    thresholds = args.threshold or [0.1, 0.25, 0.5]
    output = {
        "schema": "cloudhammer.hard_negative_hit_eval.v1",
        "manifest": str(args.manifest.resolve()),
        "total_rows": len(rows),
        "total_images": len(image_paths),
        "missing_images": missing_images,
        "imgsz": args.imgsz,
        "models": [evaluate_model(model.resolve(), image_paths, thresholds, args.imgsz) for model in args.model],
    }
    if args.output:
        write_json(args.output, output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
