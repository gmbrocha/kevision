from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from cloudhammer.config import CloudHammerConfig
from cloudhammer.manifests import read_jsonl, write_jsonl


VISUAL_TYPES = {"bold", "thin", "faint", "partial", "intersected", "unknown"}
DEFAULT_MODEL = "gpt-5.4"
PROMPT = """You are labeling construction drawing crops for object detection.

Task:
Find revision cloud motifs only. A revision cloud is a scalloped, bubbly, repeated-arc boundary drawn around a changed note or drawing area.

Use one box per visible cloud. Box the full visible scalloped cloud boundary when possible, including partial clouds cut off by the crop edge.

Ignore:
- revision triangle markers
- digits inside/near triangles
- normal text
- room labels
- doors/walls/fixtures
- dotted path lines
- tables/title blocks
- straight boxes/arrows
- random blueprint linework

Return JSON only:
{
  "has_cloud": true/false,
  "boxes": [
    {
      "x1": 0,
      "y1": 0,
      "x2": 0,
      "y2": 0,
      "confidence": 0.0,
      "visual_type": "bold|thin|faint|partial|intersected|unknown"
    }
  ]
}

Coordinates must be integer pixels relative to this image.
If uncertain, prefer no box over a bad box."""


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["has_cloud", "boxes"],
    "properties": {
        "has_cloud": {"type": "boolean"},
        "boxes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["x1", "y1", "x2", "y2", "confidence", "visual_type"],
                "properties": {
                    "x1": {"type": "integer"},
                    "y1": {"type": "integer"},
                    "x2": {"type": "integer"},
                    "y2": {"type": "integer"},
                    "confidence": {"type": "number"},
                    "visual_type": {
                        "type": "string",
                        "enum": sorted(VISUAL_TYPES),
                    },
                },
            },
        },
    },
}


@dataclass(frozen=True)
class PreparedImage:
    source_path: Path
    api_path: Path
    original_width: int
    original_height: int
    compressed_width: int
    compressed_height: int
    image_format: str


def _strip_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def load_env_file(path: str | Path) -> bool:
    env_path = Path(path)
    if not env_path.exists():
        return False
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_env_value(value)
    return True


def load_openai_env(cfg: CloudHammerConfig, env_file: str | Path | None = None) -> Path | None:
    candidates = [Path(env_file)] if env_file is not None else [cfg.root / ".env", Path.cwd() / ".env"]
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if load_env_file(resolved):
            return resolved
    return None


def prepare_api_image(
    source_path: str | Path,
    output_dir: str | Path,
    max_dim: int = 1024,
    image_format: str = "png",
) -> PreparedImage:
    source = Path(source_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    image_format = image_format.lower()
    if image_format not in {"png", "jpeg", "jpg", "webp"}:
        raise ValueError(f"Unsupported image format: {image_format}")
    suffix = ".jpg" if image_format in {"jpeg", "jpg"} else f".{image_format}"
    api_path = out_dir / f"{source.stem}{suffix}"

    with Image.open(source) as image:
        image = image.convert("RGB")
        original_width, original_height = image.size
        scale = min(1.0, float(max_dim) / float(max(original_width, original_height)))
        if scale < 1.0:
            resized = image.resize(
                (max(1, int(round(original_width * scale))), max(1, int(round(original_height * scale)))),
                Image.Resampling.LANCZOS,
            )
        else:
            resized = image.copy()
        compressed_width, compressed_height = resized.size
        if suffix == ".png":
            resized.save(api_path, format="PNG", optimize=True)
        elif suffix == ".webp":
            resized.save(api_path, format="WEBP", quality=95, method=6)
        else:
            resized.save(api_path, format="JPEG", quality=95, subsampling=0, optimize=True)

    return PreparedImage(
        source_path=source,
        api_path=api_path,
        original_width=original_width,
        original_height=original_height,
        compressed_width=compressed_width,
        compressed_height=compressed_height,
        image_format="jpeg" if suffix == ".jpg" else image_format,
    )


def image_to_data_url(path: str | Path, image_format: str) -> str:
    mime = {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "webp": "image/webp",
    }[image_format.lower()]
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def extract_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return str(text)
    output = getattr(response, "output", None)
    if output:
        chunks: list[str] = []
        for item in output:
            for content in getattr(item, "content", []) or []:
                value = getattr(content, "text", None)
                if value:
                    chunks.append(str(value))
        if chunks:
            return "".join(chunks)
    return str(response)


def parse_model_json(text: str) -> dict:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Model response JSON must be an object")
    if not isinstance(payload.get("has_cloud"), bool):
        raise ValueError("Model response missing boolean has_cloud")
    boxes = payload.get("boxes")
    if not isinstance(boxes, list):
        raise ValueError("Model response missing boxes array")
    return payload


def clamp_box(box: dict, width: int, height: int) -> dict:
    x1 = max(0.0, min(float(width), float(box["x1"])))
    y1 = max(0.0, min(float(height), float(box["y1"])))
    x2 = max(0.0, min(float(width), float(box["x2"])))
    y2 = max(0.0, min(float(height), float(box["y2"])))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "confidence": float(box.get("confidence", 0.0)),
        "visual_type": str(box.get("visual_type") or "unknown"),
    }


def scale_box(box: dict, x_scale: float, y_scale: float) -> dict:
    return {
        **box,
        "x1": box["x1"] * x_scale,
        "y1": box["y1"] * y_scale,
        "x2": box["x2"] * x_scale,
        "y2": box["y2"] * y_scale,
    }


def validate_boxes(
    payload: dict,
    compressed_width: int,
    compressed_height: int,
    original_width: int,
    original_height: int,
    min_confidence: float,
) -> list[dict]:
    accepted: list[dict] = []
    image_area = float(compressed_width * compressed_height)
    x_scale = float(original_width) / float(compressed_width)
    y_scale = float(original_height) / float(compressed_height)
    for raw_box in payload.get("boxes", []):
        if not isinstance(raw_box, dict):
            continue
        try:
            box = clamp_box(raw_box, compressed_width, compressed_height)
        except (KeyError, TypeError, ValueError):
            continue
        box_width = box["x2"] - box["x1"]
        box_height = box["y2"] - box["y1"]
        box_area = box_width * box_height
        if box["confidence"] < min_confidence:
            continue
        if box["visual_type"] not in VISUAL_TYPES:
            box["visual_type"] = "unknown"
        if box_width < 12 or box_height < 12 or box_area < 144:
            continue
        if box_area > image_area * 0.85:
            continue
        original_box = scale_box(box, x_scale, y_scale)
        accepted.append(
            {
                "compressed_box": box,
                "original_box": original_box,
                "confidence": box["confidence"],
                "visual_type": box["visual_type"],
            }
        )
    return accepted


def yolo_line(box: dict, width: int, height: int) -> str:
    x1 = max(0.0, min(float(width), float(box["x1"])))
    y1 = max(0.0, min(float(height), float(box["y1"])))
    x2 = max(0.0, min(float(width), float(box["x2"])))
    y2 = max(0.0, min(float(height), float(box["y2"])))
    cx = ((x1 + x2) / 2.0) / float(width)
    cy = ((y1 + y2) / 2.0) / float(height)
    bw = max(0.0, x2 - x1) / float(width)
    bh = max(0.0, y2 - y1) / float(height)
    return f"0 {cx:.8f} {cy:.8f} {bw:.8f} {bh:.8f}"


def write_yolo_label(label_path: Path, boxes: list[dict], width: int, height: int) -> None:
    label_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [yolo_line(item["original_box"], width, height) for item in boxes]
    label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def draw_review_overlay(source_path: Path, review_path: Path, boxes: list[dict]) -> None:
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        image = image.convert("RGB")
        draw = ImageDraw.Draw(image)
        for item in boxes:
            box = item["original_box"]
            color = (220, 20, 60)
            draw.rectangle((box["x1"], box["y1"], box["x2"], box["y2"]), outline=color, width=5)
            label = f"{item['confidence']:.2f} {item['visual_type']}"
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
            draw.text((box["x1"] + 4, max(0, box["y1"] - 16)), label, fill=color, font=font)
        if not boxes:
            draw.text((12, 12), "no accepted cloud_motif", fill=(80, 80, 80))
        image.save(review_path, format="JPEG", quality=92)


def response_to_jsonable(response: Any) -> dict | str:
    if hasattr(response, "model_dump"):
        try:
            return response.model_dump(mode="json")
        except TypeError:
            return response.model_dump()
    return str(response)


def _error_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        value = headers.get("retry-after") or headers.get("Retry-After")
    except AttributeError:
        return None
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _is_retryable_openai_error(exc: Exception) -> bool:
    status_code = _error_status_code(exc)
    if status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True
    text = str(exc).lower()
    return "rate limit" in text or "temporarily unavailable" in text or "timeout" in text


def call_openai_vision(
    api_image: PreparedImage,
    model: str,
    detail: str,
    max_retries: int = 3,
    retry_initial_delay: float = 2.0,
) -> tuple[str, Any]:
    try:
        from openai import OpenAI  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("openai is not installed. Install requirements.txt before API prelabeling.") from exc

    client = OpenAI()
    image_part = {
        "type": "input_image",
        "image_url": image_to_data_url(api_image.api_path, api_image.image_format),
    }
    if detail != "auto":
        image_part["detail"] = detail
    attempt = 0
    while True:
        try:
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": PROMPT},
                            image_part,
                        ],
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "cloud_motif_detection",
                        "schema": RESPONSE_SCHEMA,
                        "strict": True,
                    }
                },
            )
            break
        except Exception as exc:
            if attempt >= max_retries or not _is_retryable_openai_error(exc):
                raise
            attempt += 1
            retry_after = _retry_after_seconds(exc)
            delay = retry_after if retry_after is not None else retry_initial_delay * (2 ** (attempt - 1))
            delay = min(max(0.0, delay), 60.0)
            status = _error_status_code(exc)
            status_text = f" status={status}" if status else ""
            print(
                f"OpenAI request retry {attempt}/{max_retries} after {delay:.1f}s"
                f"{status_text} ({type(exc).__name__})",
                flush=True,
            )
            time.sleep(delay)
    return extract_response_text(response), response


def _load_existing_predictions(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    for row in read_jsonl(path):
        roi_id = row.get("cloud_roi_id")
        if roi_id:
            out[str(roi_id)] = row
    return out


def _prediction_paths(cfg: CloudHammerConfig) -> tuple[Path, Path, Path, Path]:
    return (
        cfg.path("api_cloud_inputs"),
        cfg.path("api_cloud_predictions") / "predictions.jsonl",
        cfg.path("api_cloud_labels"),
        cfg.path("api_cloud_review"),
    )


def prelabel_cloud_rois(
    cfg: CloudHammerConfig,
    manifest_path: str | Path | None = None,
    limit: int | None = None,
    overwrite: bool = False,
    model: str = DEFAULT_MODEL,
    detail: str = "auto",
    max_dim: int = 1024,
    min_confidence: float = 0.60,
    dry_run: bool = False,
    image_format: str = "png",
    env_file: str | Path | None = None,
    request_delay: float = 0.5,
    max_retries: int = 3,
    retry_initial_delay: float = 2.0,
) -> int:
    if detail not in {"low", "auto", "high"}:
        raise ValueError("detail must be one of: low, auto, high")
    if max_dim < 256:
        raise ValueError("max_dim must be at least 256")
    if request_delay < 0:
        raise ValueError("request_delay must be non-negative")
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    if retry_initial_delay < 0:
        raise ValueError("retry_initial_delay must be non-negative")

    cfg.ensure_directories()
    roi_manifest = Path(manifest_path) if manifest_path is not None else cfg.path("manifests") / "cloud_roi_manifest.jsonl"
    input_dir, predictions_path, label_dir, review_dir = _prediction_paths(cfg)
    input_dir.mkdir(parents=True, exist_ok=True)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)

    rows = list(read_jsonl(roi_manifest))
    if limit is not None:
        rows = rows[:limit]

    existing = {} if overwrite else _load_existing_predictions(predictions_path)
    predictions: dict[str, dict] = dict(existing)
    processed = 0
    skipped = 0
    failed = 0

    loaded_env = load_openai_env(cfg, env_file)
    if not dry_run and not os.environ.get("OPENAI_API_KEY"):
        searched = Path(env_file).resolve() if env_file is not None else cfg.root / ".env"
        raise RuntimeError(
            f"OPENAI_API_KEY is not set. Checked environment and {searched}. "
            "Use --dry-run to test compression without API calls."
        )

    total = len(rows)
    for index, row in enumerate(rows, start=1):
        roi_id = str(row.get("cloud_roi_id") or Path(row["roi_image_path"]).stem)
        if not overwrite and roi_id in existing:
            skipped += 1
            continue
        source_path = Path(row.get("roi_image_path") or row.get("image_path"))
        if not source_path.exists():
            failed += 1
            predictions[roi_id] = {
                "cloud_roi_id": roi_id,
                "status": "failed",
                "error": f"ROI image not found: {source_path}",
                "row": row,
            }
            continue

        api_image = prepare_api_image(source_path, input_dir, max_dim=max_dim, image_format=image_format)
        if dry_run:
            processed += 1
            continue

        label_path = label_dir / f"{source_path.stem}.txt"
        review_path = review_dir / f"{source_path.stem}.jpg"
        try:
            print(f"api prelabel {index}/{total}: {source_path.name}", flush=True)
            raw_text, raw_response = call_openai_vision(
                api_image,
                model=model,
                detail=detail,
                max_retries=max_retries,
                retry_initial_delay=retry_initial_delay,
            )
            parsed = parse_model_json(raw_text)
            accepted_boxes = validate_boxes(
                parsed,
                api_image.compressed_width,
                api_image.compressed_height,
                api_image.original_width,
                api_image.original_height,
                min_confidence=min_confidence,
            )
            write_yolo_label(label_path, accepted_boxes, api_image.original_width, api_image.original_height)
            draw_review_overlay(source_path, review_path, accepted_boxes)
            predictions[roi_id] = {
                "cloud_roi_id": roi_id,
                "source_image_path": str(source_path),
                "api_image_path": str(api_image.api_path),
                "label_path": str(label_path),
                "review_image_path": str(review_path),
                "original_width": api_image.original_width,
                "original_height": api_image.original_height,
                "compressed_width": api_image.compressed_width,
                "compressed_height": api_image.compressed_height,
                "model": model,
                "detail": detail,
                "min_confidence": min_confidence,
                "env_file_loaded": str(loaded_env) if loaded_env else None,
                "status": "ok",
                "has_cloud": bool(parsed.get("has_cloud")),
                "raw_response_text": raw_text,
                "raw_response": response_to_jsonable(raw_response),
                "parsed_response": parsed,
                "accepted_boxes": accepted_boxes,
                "accepted_box_count": len(accepted_boxes),
                "manifest_row": row,
            }
            processed += 1
        except Exception as exc:
            failed += 1
            predictions[roi_id] = {
                "cloud_roi_id": roi_id,
                "source_image_path": str(source_path),
                "api_image_path": str(api_image.api_path),
                "model": model,
                "detail": detail,
                "env_file_loaded": str(loaded_env) if loaded_env else None,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "manifest_row": row,
            }
        if request_delay > 0 and index < total:
            time.sleep(request_delay)

    if not dry_run:
        ordered_predictions = [predictions[key] for key in sorted(predictions)]
        write_jsonl(predictions_path, ordered_predictions)

    print(
        f"api prelabel: processed={processed} skipped={skipped} failed={failed} "
        f"dry_run={dry_run} inputs={input_dir}"
    )
    if not dry_run:
        print(f"wrote predictions={predictions_path} labels={label_dir} review={review_dir}")
    return processed
