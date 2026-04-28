from __future__ import annotations

from pathlib import Path

from cloudhammer.config import CloudHammerConfig
from cloudhammer.data.yolo import build_yolo_dataset
from cloudhammer.runtime import configure_local_artifact_cache


def train_roi_detector(
    cfg: CloudHammerConfig,
    roi_manifest_path: str | Path | None = None,
    model_name: str | None = None,
    imgsz: int | None = None,
    epochs: int | None = None,
    batch: int | None = None,
    dataset_dir: str | Path | None = None,
    run_name: str = "cloudhammer_roi",
):
    configure_local_artifact_cache(cfg)
    try:
        from ultralytics import YOLO  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("ultralytics is not installed. Install requirements-train.txt to train.") from exc

    manifest = (
        Path(roi_manifest_path)
        if roi_manifest_path is not None
        else cfg.path("manifests") / "cloud_roi_manifest.jsonl"
    )
    if not manifest.exists():
        raise FileNotFoundError(f"ROI manifest not found: {manifest}")
    dataset_yaml = build_yolo_dataset(manifest, dataset_dir or cfg.root / "data" / "yolo")
    model = YOLO(model_name or str(cfg.data["training"]["model"]))
    return model.train(
        data=str(dataset_yaml),
        imgsz=imgsz or int(cfg.data["training"]["imgsz"]),
        epochs=epochs or int(cfg.data["training"]["epochs"]),
        batch=batch or int(cfg.data["training"]["batch"]),
        project=str(cfg.path("runs")),
        name=run_name,
    )
