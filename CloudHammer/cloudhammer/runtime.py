from __future__ import annotations

import os
from pathlib import Path

from .config import CloudHammerConfig


def configure_local_artifact_cache(cfg: CloudHammerConfig) -> None:
    """Keep large ML/temp artifacts inside the CloudHammer project tree."""
    cache_root = cfg.path("models") / "cache"
    tmp_root = cfg.path("runs") / "tmp"
    paths = {
        "TORCH_HOME": cache_root / "torch",
        "HF_HOME": cache_root / "huggingface",
        "XDG_CACHE_HOME": cache_root / "xdg",
        "YOLO_CONFIG_DIR": cache_root / "ultralytics",
        "ULTRALYTICS_CONFIG_DIR": cache_root / "ultralytics",
        "MPLCONFIGDIR": cache_root / "matplotlib",
        "TMP": tmp_root,
        "TEMP": tmp_root,
    }
    for path in paths.values():
        Path(path).mkdir(parents=True, exist_ok=True)
    for key, path in paths.items():
        os.environ.setdefault(key, str(path))
