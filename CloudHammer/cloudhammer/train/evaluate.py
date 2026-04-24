from __future__ import annotations

from pathlib import Path


def evaluate_model(model_path: str | Path, data_yaml: str | Path):
    try:
        from ultralytics import YOLO  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("ultralytics is not installed. Install requirements-train.txt to evaluate.") from exc
    model = YOLO(str(model_path))
    return model.val(data=str(data_yaml))
