from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "cloudhammer.yaml"


DEFAULT_CONFIG: dict[str, Any] = {
    "paths": {
        "raw_pdfs": "data/raw_pdfs",
        "rasterized_pages": "data/rasterized_pages",
        "delta_json": "data/delta_json",
        "roi_images": "data/roi_images",
        "cloud_roi_images": "data/cloud_roi_images",
        "api_cloud_inputs": "data/api_cloud_inputs",
        "api_cloud_predictions": "data/api_cloud_predictions",
        "api_cloud_labels_unreviewed": "data/api_cloud_labels_unreviewed",
        "api_cloud_review": "data/api_cloud_review",
        "labels": "data/labels",
        "cloud_labels": "data/cloud_labels",
        "cloud_labels_reviewed": "data/cloud_labels_reviewed",
        "manifests": "data/manifests",
        "models": "models",
        "runs": "runs",
        "outputs": "outputs",
    },
    "render": {"dpi": 300},
    "bootstrap": {"roi_size": 1400, "target_revision_digit": None},
    "training": {"model": "yolov8n.pt", "imgsz": 640, "epochs": 50, "batch": 16},
    "inference": {"confidence_threshold": 0.5, "tile_size": 1280, "tile_overlap": 192, "nms_iou": 0.5},
}


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"null", "Null", "NULL", "~"}:
        return None
    if value in {"true", "True", "TRUE"}:
        return True
    if value in {"false", "False", "FALSE"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _minimal_yaml_load(text: str) -> dict[str, Any]:
    """Parse the small two-level YAML shape used by the default config."""
    root: dict[str, Any] = {}
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0:
            key, _, value = stripped.partition(":")
            if value.strip():
                root[key] = _parse_scalar(value)
                current = None
            else:
                current = {}
                root[key] = current
            continue
        if indent == 2 and current is not None:
            key, _, value = stripped.partition(":")
            current[key] = _parse_scalar(value)
            continue
        raise ValueError(f"Unsupported YAML line: {raw_line!r}")
    return root


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Config root must be a mapping: {path}")
        return data
    except ModuleNotFoundError:
        return _minimal_yaml_load(text)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in base.items():
        out[key] = _deep_merge(value, {}) if isinstance(value, dict) else value
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass(frozen=True)
class CloudHammerConfig:
    root: Path
    data: dict[str, Any]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "CloudHammerConfig":
        config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
        config_path = config_path.resolve()
        if config_path.exists():
            data = _deep_merge(DEFAULT_CONFIG, load_yaml(config_path))
            root = config_path.parent.parent
        else:
            data = DEFAULT_CONFIG
            root = PROJECT_ROOT
        return cls(root=root.resolve(), data=data)

    def path(self, key: str) -> Path:
        raw = self.data["paths"][key]
        path = Path(raw)
        if not path.is_absolute():
            path = self.root / path
        return path.resolve()

    def ensure_directories(self) -> None:
        for key in self.data["paths"]:
            self.path(key).mkdir(parents=True, exist_ok=True)

    @property
    def dpi(self) -> int:
        return int(self.data["render"]["dpi"])

    @property
    def roi_size(self) -> int:
        return int(self.data["bootstrap"]["roi_size"])

    @property
    def target_revision_digit(self) -> str | None:
        value = self.data["bootstrap"].get("target_revision_digit")
        return None if value is None else str(value)
