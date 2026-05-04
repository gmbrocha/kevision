from __future__ import annotations

import argparse
import base64
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
LEGACY_ROOT = PROJECT_ROOT / "CloudHammer"
Image.MAX_IMAGE_PIXELS = None

DEFAULT_MODEL = "gpt-5.4"

PROMPT = """You are labeling full-page construction drawings for object detection.

Task:
Find visible revision cloud motifs only. A revision cloud is a repeated scalloped, bubbly boundary drawn around changed notes or drawing areas.

Use one box per visible cloud. Box the full visible scalloped cloud boundary when possible, including partial clouds clipped by the page edge.

Ignore:
- revision triangle markers
- digits inside or near triangles
- normal text and title blocks
- room labels, schedules, tables, symbols, fixture circles, and equipment outlines
- dotted paths, doors, walls, stairs, and other normal blueprint linework
- isolated curved arcs that are not a repeated scalloped boundary
- straight rectangles, arrows, delta markers, and index/table X marks

Do not label a symbol, fixture, glyph, or decorative arc just because it is curved. A valid revision cloud should read as an intentional repeated scalloped boundary around a revision area.

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
      "visual_type": "bold|thin|faint|partial|intersected|large|unknown"
    }
  ]
}

Coordinates must be integer pixels relative to the image you see, not the original full-resolution page.
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
                        "enum": ["bold", "thin", "faint", "partial", "intersected", "large", "unknown"],
                    },
                },
            },
        },
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def strip_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> bool:
    if not path.exists():
        return False
    loaded = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = strip_env_value(value)
            loaded = True
    return loaded


def resolve_project_path(value: str | Path | None) -> Path:
    if value is None or str(value) == "":
        return Path("")
    candidate = Path(value)
    if candidate.exists():
        return candidate.resolve()
    parts = candidate.parts
    for anchor, root in (("CloudHammer", LEGACY_ROOT), ("revision_sets", PROJECT_ROOT / "revision_sets")):
        for index, part in enumerate(parts):
            if part.lower() == anchor.lower():
                relocated = root.joinpath(*parts[index + 1 :])
                if relocated.exists():
                    return relocated.resolve()
    return candidate


def prepare_api_image(source_path: Path, output_dir: Path, max_dim: int, image_format: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".jpg" if image_format in {"jpeg", "jpg"} else f".{image_format}"
    api_path = output_dir / f"{source_path.stem}{suffix}"
    with Image.open(source_path) as image:
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
        if suffix == ".jpg":
            resized.save(api_path, format="JPEG", quality=92, subsampling=0, optimize=True)
        else:
            resized.save(api_path, format=image_format.upper(), optimize=True)
    return {
        "source_path": str(source_path),
        "api_path": str(api_path),
        "original_width": original_width,
        "original_height": original_height,
        "compressed_width": compressed_width,
        "compressed_height": compressed_height,
        "image_format": "jpeg" if suffix == ".jpg" else image_format,
    }


def image_to_data_url(path: Path, image_format: str) -> str:
    mime = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "webp": "image/webp"}[image_format]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


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


def parse_json_response(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("GPT response must be a JSON object")
    if not isinstance(payload.get("has_cloud"), bool):
        raise ValueError("GPT response missing has_cloud boolean")
    if not isinstance(payload.get("boxes"), list):
        raise ValueError("GPT response missing boxes list")
    return payload


def call_openai(api_image: dict[str, Any], model: str, detail: str, max_retries: int, retry_initial_delay: float) -> str:
    from openai import OpenAI

    client = OpenAI()
    image_part = {
        "type": "input_image",
        "image_url": image_to_data_url(Path(api_image["api_path"]), str(api_image["image_format"])),
        "detail": detail,
    }
    page_note = (
        f"\nDisplayed image size: {api_image['compressed_width']}x{api_image['compressed_height']} pixels. "
        f"Original page size: {api_image['original_width']}x{api_image['original_height']} pixels."
    )
    attempt = 0
    while True:
        try:
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": PROMPT + page_note},
                            image_part,
                        ],
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "fullpage_cloud_motif_detection",
                        "schema": RESPONSE_SCHEMA,
                        "strict": True,
                    }
                },
            )
            return extract_response_text(response)
        except Exception:
            if attempt >= max_retries:
                raise
            attempt += 1
            time.sleep(min(60.0, retry_initial_delay * (2 ** (attempt - 1))))


def clamp_and_scale_boxes(payload: dict[str, Any], api_image: dict[str, Any], min_confidence: float) -> list[dict[str, Any]]:
    width = int(api_image["compressed_width"])
    height = int(api_image["compressed_height"])
    x_scale = float(api_image["original_width"]) / max(1.0, float(width))
    y_scale = float(api_image["original_height"]) / max(1.0, float(height))
    accepted: list[dict[str, Any]] = []
    for raw in payload.get("boxes", []):
        confidence = float(raw.get("confidence") or 0.0)
        if confidence < min_confidence:
            continue
        x1 = max(0.0, min(float(width), float(raw["x1"])))
        y1 = max(0.0, min(float(height), float(raw["y1"])))
        x2 = max(0.0, min(float(width), float(raw["x2"])))
        y2 = max(0.0, min(float(height), float(raw["y2"])))
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        if (x2 - x1) < 4 or (y2 - y1) < 4:
            continue
        accepted.append(
            {
                "x1": round(x1 * x_scale, 3),
                "y1": round(y1 * y_scale, 3),
                "x2": round(x2 * x_scale, 3),
                "y2": round(y2 * y_scale, 3),
                "confidence": confidence,
                "visual_type": str(raw.get("visual_type") or "unknown"),
                "api_box_xyxy": [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))],
            }
        )
    return accepted


def write_yolo_label(path: Path, boxes: list[dict[str, Any]], width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for box in boxes:
        x1, y1, x2, y2 = [float(box[key]) for key in ("x1", "y1", "x2", "y2")]
        xc = ((x1 + x2) / 2.0) / width
        yc = ((y1 + y2) / 2.0) / height
        bw = (x2 - x1) / width
        bh = (y2 - y1) / height
        lines.append(f"0 {xc:.8f} {yc:.8f} {bw:.8f} {bh:.8f}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def draw_overlay(source_path: Path, output_path: Path, boxes: list[dict[str, Any]], max_dim: int = 2200) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        image = image.convert("RGB")
        scale = min(1.0, float(max_dim) / float(max(image.size)))
        if scale < 1.0:
            image = image.resize(
                (max(1, int(round(image.size[0] * scale))), max(1, int(round(image.size[1] * scale)))),
                Image.Resampling.LANCZOS,
            )
        draw = ImageDraw.Draw(image)
        for index, box in enumerate(boxes, start=1):
            xy = [box["x1"] * scale, box["y1"] * scale, box["x2"] * scale, box["y2"] * scale]
            draw.rectangle(xy, outline=(255, 64, 0), width=4)
            draw.text((xy[0], max(0, xy[1] - 18)), f"C{index} {box['confidence']:.2f}", fill=(255, 64, 0))
        image.save(output_path, format="JPEG", quality=92)


def write_contact_sheet(image_paths: list[Path], output_path: Path, thumb_width: int = 620, cols: int = 2) -> None:
    existing = [path for path in image_paths if path.exists()]
    if not existing:
        return
    thumbs: list[Image.Image] = []
    for path in existing:
        with Image.open(path) as image:
            image = image.convert("RGB")
            scale = thumb_width / max(1, image.size[0])
            thumb = image.resize(
                (thumb_width, max(1, int(round(image.size[1] * scale)))),
                Image.Resampling.LANCZOS,
            )
            thumbs.append(thumb)
    cell_height = max(thumb.size[1] for thumb in thumbs)
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_width, rows * cell_height), "white")
    for index, thumb in enumerate(thumbs):
        x = (index % cols) * thumb_width
        y = (index // cols) * cell_height
        sheet.paste(thumb, (x, y))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="JPEG", quality=90)


def markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# GPT-Provisional Full-Page Labels",
        "",
        f"Eval subset: `{summary['eval_subset']}`",
        f"Model: `{summary['model']}`",
        f"Label status: `{summary['label_status']}`",
        f"Pages: `{summary['pages']}`",
        f"Processed: `{summary['processed']}`",
        f"Skipped: `{summary['skipped']}`",
        f"Failed: `{summary['failed']}`",
        f"Pages with accepted boxes: `{summary['pages_with_boxes']}`",
        f"Accepted boxes: `{summary['accepted_boxes']}`",
        "",
        "These labels are provisional and must not be treated as human-audited truth.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate GPT-provisional full-page YOLO labels for frozen eval pages.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=V2_ROOT / "eval" / "page_disjoint_real" / "page_disjoint_real_manifest.jsonl",
    )
    parser.add_argument("--output-dir", type=Path, default=V2_ROOT / "eval" / "page_disjoint_real")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--detail", choices=["low", "auto", "high"], default="high")
    parser.add_argument("--max-dim", type=int, default=3000)
    parser.add_argument("--min-confidence", type=float, default=0.40)
    parser.add_argument("--image-format", choices=["jpeg", "png", "webp"], default="jpeg")
    parser.add_argument("--env-file", type=Path, default=LEGACY_ROOT / ".env")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--request-delay", type=float, default=0.25)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-initial-delay", type=float, default=2.0)
    args = parser.parse_args()

    if not args.dry_run:
        load_env_file(args.env_file)
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(f"OPENAI_API_KEY is not set. Checked {args.env_file}.")

    input_dir = args.output_dir / "api_inputs"
    label_dir = args.output_dir / "labels_gpt_provisional"
    metadata_dir = args.output_dir / "label_metadata"
    overlay_dir = args.output_dir / "overlays_gpt_provisional"
    prediction_path = args.output_dir / "gpt_fullpage_predictions.jsonl"
    updated_manifest_path = args.output_dir / "page_disjoint_real_manifest.gpt_provisional.jsonl"

    rows = read_jsonl(args.manifest)
    predictions: list[dict[str, Any]] = []
    updated_rows: list[dict[str, Any]] = []
    processed = skipped = failed = 0
    accepted_boxes_total = 0
    pages_with_boxes = 0

    for index, row in enumerate(rows, start=1):
        source_key = str(row.get("source_page_key") or Path(str(row.get("render_path") or "")).stem)
        render_path = resolve_project_path(row.get("render_path"))
        label_path = label_dir / f"{source_key.replace(':', '_')}.txt"
        metadata_path = metadata_dir / f"{source_key.replace(':', '_')}.json"
        overlay_path = overlay_dir / f"{source_key.replace(':', '_')}.jpg"

        updated = dict(row)
        updated.update(
            {
                "label_status": "gpt_provisional",
                "label_path": str(label_path),
                "gpt_label_metadata_path": str(metadata_path),
                "gpt_review_overlay_path": str(overlay_path),
            }
        )

        if not render_path.exists():
            failed += 1
            prediction = {
                "source_page_key": source_key,
                "status": "failed",
                "error": f"render_path not found: {render_path}",
                "manifest_row": row,
            }
            predictions.append(prediction)
            updated_rows.append(updated)
            continue

        if label_path.exists() and metadata_path.exists() and not args.overwrite:
            skipped += 1
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            accepted_boxes_total += int(metadata.get("accepted_box_count") or 0)
            pages_with_boxes += 1 if int(metadata.get("accepted_box_count") or 0) > 0 else 0
            predictions.append(metadata)
            updated_rows.append(updated)
            continue

        api_image = prepare_api_image(render_path, input_dir, args.max_dim, args.image_format)
        if args.dry_run:
            processed += 1
            prediction = {
                "source_page_key": source_key,
                "status": "dry_run",
                "api_image": api_image,
                "manifest_row": row,
            }
            predictions.append(prediction)
            updated_rows.append(updated)
            continue

        try:
            print(f"gpt full-page label {index}/{len(rows)}: {source_key}", flush=True)
            raw_text = call_openai(api_image, args.model, args.detail, args.max_retries, args.retry_initial_delay)
            parsed = parse_json_response(raw_text)
            boxes = clamp_and_scale_boxes(parsed, api_image, args.min_confidence)
            write_yolo_label(label_path, boxes, int(api_image["original_width"]), int(api_image["original_height"]))
            draw_overlay(render_path, overlay_path, boxes)
            metadata = {
                "schema": "cloudhammer_v2.fullpage_gpt_label.v1",
                "source_page_key": source_key,
                "status": "ok",
                "label_status": "gpt_provisional",
                "model": args.model,
                "detail": args.detail,
                "min_confidence": args.min_confidence,
                "label_path": str(label_path),
                "review_overlay_path": str(overlay_path),
                "api_image": api_image,
                "raw_response_text": raw_text,
                "parsed_response": parsed,
                "accepted_boxes": boxes,
                "accepted_box_count": len(boxes),
                "manifest_row": row,
            }
            write_json(metadata_path, metadata)
            predictions.append(metadata)
            processed += 1
            accepted_boxes_total += len(boxes)
            pages_with_boxes += 1 if boxes else 0
        except Exception as exc:
            failed += 1
            metadata = {
                "schema": "cloudhammer_v2.fullpage_gpt_label.v1",
                "source_page_key": source_key,
                "status": "failed",
                "label_status": "gpt_provisional",
                "model": args.model,
                "detail": args.detail,
                "error": f"{type(exc).__name__}: {exc}",
                "api_image": api_image,
                "manifest_row": row,
            }
            write_json(metadata_path, metadata)
            predictions.append(metadata)
        updated_rows.append(updated)
        if args.request_delay > 0 and index < len(rows):
            time.sleep(args.request_delay)

    write_jsonl(prediction_path, predictions)
    write_jsonl(updated_manifest_path, updated_rows)
    contact_sheet_path = args.output_dir / "gpt_fullpage_overlay_contact_sheet.jpg"
    write_contact_sheet([Path(row["gpt_review_overlay_path"]) for row in updated_rows], contact_sheet_path)
    summary = {
        "schema": "cloudhammer_v2.fullpage_gpt_label_summary.v1",
        "eval_subset": "page_disjoint_real",
        "model": args.model,
        "label_status": "gpt_provisional",
        "pages": len(rows),
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "pages_with_boxes": pages_with_boxes,
        "accepted_boxes": accepted_boxes_total,
        "visual_type_counts": dict(
            Counter(
                box.get("visual_type", "unknown")
                for prediction in predictions
                for box in prediction.get("accepted_boxes", [])
            )
        ),
        "manifest": str(args.manifest),
        "updated_manifest": str(updated_manifest_path),
        "predictions": str(prediction_path),
        "overlay_contact_sheet": str(contact_sheet_path),
    }
    write_json(args.output_dir / "gpt_fullpage_label_summary.json", summary)
    (args.output_dir / "gpt_fullpage_label_summary.md").write_text(markdown_summary(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
