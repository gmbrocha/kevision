from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from build_postprocessing_geometry_reviewer import (
    DEFAULT_DRY_RUN_DIR,
    GEOMETRY_FIELDNAMES,
    build_geometry_items,
    load_candidates,
    project_path,
    read_csv_by_id,
    read_json,
    read_jsonl,
    write_csv,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "gpt-5.5"
DECISION_OPTIONS = {
    "merge_component_geometry": ["component_bbox", "component_needs_split", "component_not_actionable", "unclear"],
    "expand_geometry": ["corrected_bbox", "merge_with_component", "not_actionable", "unclear"],
    "tighten_adjust_geometry": ["corrected_bbox", "not_actionable", "unclear"],
    "split_geometry": ["child_bboxes", "split_by_existing_candidates", "not_actionable", "unclear"],
}
ALL_DECISIONS = sorted({value for values in DECISION_OPTIONS.values() for value in values})
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "review_status",
        "geometry_decision",
        "corrected_bbox_xyxy",
        "child_bboxes",
        "target_candidate_ids",
        "review_notes",
        "confidence",
    ],
    "properties": {
        "review_status": {"type": "string", "enum": ["reviewed", "needs_followup", "not_actionable"]},
        "geometry_decision": {"type": "string", "enum": ALL_DECISIONS},
        "corrected_bbox_xyxy": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 0,
            "maxItems": 4,
        },
        "child_bboxes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "bbox_xyxy", "source_candidate_ids"],
                "properties": {
                    "label": {"type": "string"},
                    "bbox_xyxy": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "source_candidate_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "target_candidate_ids": {"type": "array", "items": {"type": "string"}},
        "review_notes": {"type": "string"},
        "confidence": {"type": "number"},
    },
}


PROMPT = """You are pre-filling a human geometry review log for CloudHammer revision-cloud postprocessing.

The task is to propose provisional geometry only. The human reviewer will confirm or change it.

Images show candidate crops with overlays:
- red solid box: the active/source candidate bbox in page coordinates projected onto the crop
- blue/green/purple dashed boxes: other source candidates in the same geometry item, when present
- amber dashed boxes: member detector boxes inside a candidate

Coordinate system:
- All bbox values you return must be page-coordinate [x1, y1, x2, y2] values.
- Prefer conservative boxes that cover the complete visible revision cloud outline.
- Do not make boxes tight to text, revision triangles, or leader lines; box the revision-cloud outline.
- If the image/context is insufficient for exact geometry, use review_status "needs_followup" and decision "unclear".

Allowed geometry decisions:
- component_bbox: source candidates are same-cloud fragments; corrected_bbox_xyxy is the full-cloud bbox for the merged component.
- component_needs_split: component row still appears to mix separate clouds; use child_bboxes if you can identify child boxes.
- component_not_actionable: component should not become geometry.
- corrected_bbox: one source candidate needs a corrected full-cloud bbox.
- merge_with_component: the source candidate should be handled by the listed merge component rather than standalone geometry.
- child_bboxes: split one candidate into explicit child cloud boxes.
- split_by_existing_candidates: split is already adequately represented by existing candidate IDs; put those IDs in target_candidate_ids.
- not_actionable: no geometry action should be taken.
- unclear: visual evidence is insufficient.

Important policy:
- GPT geometry is provisional, never ground truth.
- For expand_geometry, prefer merge_with_component when the source candidate is already part of a merge_component item shown in the context.
- For tighten_adjust_geometry, use corrected_bbox only if you can see the full cloud and the corrected bbox is obvious.
- For split_geometry, use child_bboxes only if you can identify distinct complete child clouds; otherwise use needs_followup/unclear.
- If returning corrected_bbox_xyxy or child_bboxes, include coordinates that cover the full visible cloud outline, not just detected members.

Return JSON only.
"""


def load_env_file(path: Path | None) -> bool:
    if path is None or not path.exists():
        return False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)
    return True


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def image_to_data_url(path: Path, image_format: str) -> str:
    mime = "image/jpeg" if image_format == "jpeg" else f"image/{image_format}"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
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


def valid_box(box: Any) -> bool:
    return isinstance(box, list) and len(box) == 4 and all(isinstance(value, (int, float)) for value in box)


def normalize_box(box: list[Any]) -> list[float]:
    x1, y1, x2, y2 = [float(value) for value in box]
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def intersect_box(box: list[float], clip: list[float]) -> list[float] | None:
    x1 = max(float(box[0]), float(clip[0]))
    y1 = max(float(box[1]), float(clip[1]))
    x2 = min(float(box[2]), float(clip[2]))
    y2 = min(float(box[3]), float(clip[3]))
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def to_crop_rect(box: list[float], crop_box: list[float], image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    clipped = intersect_box(box, crop_box)
    if clipped is None:
        return None
    crop_width = float(crop_box[2]) - float(crop_box[0])
    crop_height = float(crop_box[3]) - float(crop_box[1])
    if crop_width <= 0 or crop_height <= 0:
        return None
    image_width, image_height = image_size
    left = round(((clipped[0] - float(crop_box[0])) / crop_width) * image_width)
    top = round(((clipped[1] - float(crop_box[1])) / crop_height) * image_height)
    right = round(((clipped[2] - float(crop_box[0])) / crop_width) * image_width)
    bottom = round(((clipped[3] - float(crop_box[1])) / crop_height) * image_height)
    return (left, top, right, bottom)


def draw_dashed_rectangle(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], color: str, width: int = 5) -> None:
    x1, y1, x2, y2 = rect
    dash = 22
    gap = 12
    for x in range(x1, x2, dash + gap):
        draw.line((x, y1, min(x + dash, x2), y1), fill=color, width=width)
        draw.line((x, y2, min(x + dash, x2), y2), fill=color, width=width)
    for y in range(y1, y2, dash + gap):
        draw.line((x1, y, x1, min(y + dash, y2)), fill=color, width=width)
        draw.line((x2, y, x2, min(y + dash, y2)), fill=color, width=width)


def label_box(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], label: str, color: str) -> None:
    x1, y1, _, _ = rect
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    width = bbox[2] - bbox[0] + 8
    height = bbox[3] - bbox[1] + 6
    label_y = max(0, y1 - height)
    draw.rectangle((x1, label_y, x1 + width, label_y + height), fill=color)
    draw.text((x1 + 4, label_y + 3), label, fill="white", font=font)


def prepare_overlay_images(item: dict[str, Any], output_dir: Path, max_dim: int, image_format: str) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []
    source_ids = [str(value) for value in item.get("source_candidate_ids", [])]
    candidates = item.get("candidates") or []
    palette = ["#e11d48", "#2563eb", "#16a34a", "#7c3aed", "#0891b2"]
    for candidate_index, candidate in enumerate(candidates, start=1):
        crop_path = project_path(candidate.get("crop_image_path"))
        if crop_path is None or not crop_path.exists():
            crop_href = str(candidate.get("crop_href") or "")
            crop_path = project_path(crop_href) if crop_href else None
        if crop_path is None or not crop_path.exists():
            continue
        crop_box = candidate.get("crop_box_page_xyxy")
        if not valid_box(crop_box):
            continue
        with Image.open(crop_path) as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image, "RGBA")
        for other_index, other in enumerate(candidates):
            bbox = other.get("bbox_page_xyxy")
            if not valid_box(bbox):
                continue
            rect = to_crop_rect(normalize_box(bbox), normalize_box(crop_box), image.size)
            if rect is None:
                continue
            is_active = other.get("candidate_id") == candidate.get("candidate_id")
            color = palette[0] if is_active else palette[(other_index % (len(palette) - 1)) + 1]
            if is_active:
                draw.rectangle(rect, outline=color, width=6)
            else:
                draw_dashed_rectangle(draw, rect, color=color, width=5)
            label = "active" if is_active else str(other.get("short_id") or other.get("candidate_id") or "")
            label_box(draw, rect, label, color)
        for member_box in candidate.get("member_boxes_page_xyxy", []) or []:
            if not valid_box(member_box):
                continue
            rect = to_crop_rect(normalize_box(member_box), normalize_box(crop_box), image.size)
            if rect is not None:
                draw_dashed_rectangle(draw, rect, "#f59e0b", width=3)
        image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        extension = "jpg" if image_format == "jpeg" else image_format
        output_path = output_dir / f"{item['geometry_item_id']}_candidate_{candidate_index:02d}.{extension}"
        image.save(output_path, format="JPEG" if image_format == "jpeg" else image_format.upper(), quality=90)
        output_paths.append(output_path)
    return output_paths


def build_prompt_context(item: dict[str, Any], related_components: dict[str, list[str]]) -> str:
    return json.dumps(
        {
            "geometry_item_id": item.get("geometry_item_id"),
            "item_type": item.get("item_type"),
            "allowed_decisions": DECISION_OPTIONS.get(str(item.get("item_type")), ["unclear"]),
            "source_row_numbers": item.get("source_row_numbers"),
            "source_candidate_ids": item.get("source_candidate_ids"),
            "target_candidate_ids": item.get("target_candidate_ids"),
            "dry_run_notes": item.get("dry_run_notes"),
            "blocked_reason": item.get("blocked_reason"),
            "geometry_status": item.get("geometry_status"),
            "review_decision": item.get("review_decision"),
            "proposed_bbox_xyxy": item.get("proposed_bbox_xyxy"),
            "related_merge_components_by_candidate": related_components,
            "candidates": [
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "bbox_page_xyxy": candidate.get("bbox_page_xyxy"),
                    "crop_box_page_xyxy": candidate.get("crop_box_page_xyxy"),
                    "crop_image_path": candidate.get("crop_image_path"),
                    "member_boxes_page_xyxy": candidate.get("member_boxes_page_xyxy"),
                    "confidence": candidate.get("confidence"),
                    "size_bucket": candidate.get("size_bucket"),
                    "member_count": candidate.get("member_count"),
                    "group_fill_ratio": candidate.get("group_fill_ratio"),
                }
                for candidate in item.get("candidates", [])
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _error_status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
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


def call_openai(
    model: str,
    detail: str,
    prompt_context: str,
    image_paths: list[Path],
    image_format: str,
    max_retries: int,
    retry_initial_delay: float,
) -> str:
    try:
        from openai import OpenAI  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("openai is not installed. Install requirements.txt before API prefilling.") from exc

    client = OpenAI()
    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": PROMPT + "\n\nGeometry item context JSON:\n" + prompt_context}
    ]
    for image_path in image_paths:
        image_part: dict[str, Any] = {
            "type": "input_image",
            "image_url": image_to_data_url(image_path, image_format),
        }
        if detail != "auto":
            image_part["detail"] = detail
        content.append(image_part)
    attempt = 0
    while True:
        try:
            response = client.responses.create(
                model=model,
                input=[{"role": "user", "content": content}],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "postprocessing_geometry_prefill",
                        "schema": RESPONSE_SCHEMA,
                        "strict": True,
                    }
                },
            )
            return extract_response_text(response)
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


def normalize_prediction(payload: dict[str, Any], item_type: str) -> dict[str, Any]:
    allowed = DECISION_OPTIONS.get(item_type, ["unclear"])
    decision = str(payload.get("geometry_decision") or "unclear")
    if decision not in allowed:
        decision = "unclear" if "unclear" in allowed else allowed[-1]
    status = str(payload.get("review_status") or "needs_followup")
    if status not in {"reviewed", "needs_followup", "not_actionable"}:
        status = "needs_followup"
    if status == "reviewed":
        status = "gpt_prefilled"
    confidence = float(payload.get("confidence") or 0.0)
    bbox = payload.get("corrected_bbox_xyxy") or []
    if not (isinstance(bbox, list) and len(bbox) in {0, 4}):
        bbox = []
    child_bboxes = payload.get("child_bboxes") or []
    if not isinstance(child_bboxes, list):
        child_bboxes = []
    target_candidate_ids = payload.get("target_candidate_ids") or []
    if not isinstance(target_candidate_ids, list):
        target_candidate_ids = []
    if decision == "unclear" or confidence < 0.45:
        status = "needs_followup"
    if decision in {"corrected_bbox", "component_bbox"} and not bbox:
        status = "needs_followup"
    if decision == "child_bboxes" and not child_bboxes:
        status = "needs_followup"
    notes = str(payload.get("review_notes") or "").strip()
    if not notes:
        notes = f"GPT geometry prefill decision: {decision}."
    notes = f"GPT-5.5 geometry prefill, confidence {confidence:.2f}: {notes}"
    return {
        "review_status": status,
        "geometry_decision": decision,
        "corrected_bbox_xyxy": json.dumps(bbox, ensure_ascii=False) if bbox else "",
        "child_bboxes_json": json.dumps(child_bboxes, ensure_ascii=False) if child_bboxes else "",
        "target_candidate_ids": " | ".join(str(value) for value in target_candidate_ids),
        "review_notes": notes,
        "gpt_confidence": confidence,
    }


def build_prefill_row(item: dict[str, Any], prediction: dict[str, Any] | None) -> dict[str, Any]:
    row = {
        "geometry_item_id": item["geometry_item_id"],
        "item_type": item["item_type"],
        "source_row_numbers": " | ".join(str(value) for value in item.get("source_row_numbers", [])),
        "source_candidate_ids": " | ".join(str(value) for value in item.get("source_candidate_ids", [])),
        "review_status": "unreviewed",
        "geometry_decision": "",
        "corrected_bbox_xyxy": "",
        "child_bboxes_json": "",
        "target_candidate_ids": item.get("target_candidate_ids", ""),
        "review_notes": "",
    }
    if prediction:
        row.update(
            {
                "review_status": prediction["review_status"],
                "geometry_decision": prediction["geometry_decision"],
                "corrected_bbox_xyxy": prediction["corrected_bbox_xyxy"],
                "child_bboxes_json": prediction["child_bboxes_json"],
                "target_candidate_ids": prediction["target_candidate_ids"] or item.get("target_candidate_ids", ""),
                "review_notes": prediction["review_notes"],
            }
        )
    return row


def related_components(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for item in items:
        if item.get("item_type") != "merge_component_geometry":
            continue
        component_id = str(item.get("geometry_item_id"))
        for candidate_id in item.get("source_candidate_ids", []):
            mapping.setdefault(str(candidate_id), []).append(component_id)
    return mapping


def summarize(rows: list[dict[str, Any]], prediction_rows: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_decision: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for row in rows:
        by_status[str(row.get("review_status") or "unreviewed")] = by_status.get(str(row.get("review_status") or "unreviewed"), 0) + 1
        by_type[str(row.get("item_type") or "")] = by_type.get(str(row.get("item_type") or ""), 0) + 1
        decision = str(row.get("geometry_decision") or "")
        if decision:
            by_decision[decision] = by_decision.get(decision, 0) + 1
    return {
        "schema": "cloudhammer_v2.postprocessing_geometry_gpt_prefill_summary.v1",
        "dry_run": dry_run,
        "rows": len(rows),
        "api_predictions": len(prediction_rows),
        "by_item_type": by_type,
        "by_review_status": by_status,
        "by_geometry_decision": by_decision,
        "guardrails": [
            "provisional_geometry_only",
            "no_source_candidate_manifest_edits",
            "no_truth_label_edits",
            "no_eval_manifest_edits",
            "no_prediction_file_edits",
            "no_model_file_edits",
            "no_dataset_or_training_data_writes",
            "not_threshold_tuning",
        ],
    }


def markdown_summary(summary: dict[str, Any], output_csv: Path, predictions_jsonl: Path, api_input_dir: Path) -> str:
    lines = [
        "# GPT-5.5 Blocked Geometry Prefill",
        "",
        "This is provisional geometry metadata only. It does not modify labels, eval manifests, predictions, source candidate manifests, datasets, model files, or training data.",
        "",
        f"- Dry run: `{summary['dry_run']}`",
        f"- Rows: `{summary['rows']}`",
        f"- API predictions: `{summary['api_predictions']}`",
        f"- Prefill CSV: `{output_csv}`",
        f"- Prediction JSONL: `{predictions_jsonl}`",
        f"- API overlay inputs: `{api_input_dir}`",
        "",
        "## By Item Type",
        "",
    ]
    for key, value in sorted(summary["by_item_type"].items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## By Review Status", ""])
    for key, value in sorted(summary["by_review_status"].items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## By Geometry Decision", ""])
    if summary["by_geometry_decision"]:
        for key, value in sorted(summary["by_geometry_decision"].items()):
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- No decisions written.")
    lines.extend(["", "All geometry must be human-confirmed before any apply step.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Use GPT-5.5 to prefill blocked postprocessing geometry review metadata.")
    parser.add_argument("--dry-run-dir", type=Path, default=DEFAULT_DRY_RUN_DIR)
    parser.add_argument("--geometry-review-dir", type=Path, default=None)
    parser.add_argument("--output-csv", type=Path, default=None)
    parser.add_argument("--predictions-jsonl", type=Path, default=None)
    parser.add_argument("--api-input-dir", type=Path, default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--detail", choices=["low", "auto", "high"], default="high")
    parser.add_argument("--max-dim", type=int, default=1400)
    parser.add_argument("--image-format", choices=["jpeg", "png", "webp"], default="jpeg")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / "CloudHammer" / ".env")
    parser.add_argument("--request-delay", type=float, default=0.25)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-initial-delay", type=float, default=2.0)
    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.max_dim < 512:
        parser.error("--max-dim must be at least 512")
    if args.request_delay < 0:
        parser.error("--request-delay must be non-negative")
    if args.max_retries < 0:
        parser.error("--max-retries must be non-negative")

    geometry_review_dir = args.geometry_review_dir or args.dry_run_dir / "blocked_geometry_review"
    geometry_log = geometry_review_dir / "postprocessing_geometry_review.csv"
    diagnostic_summary = read_json(args.dry_run_dir.parent / "postprocessing_diagnostic_summary.json")
    candidate_manifest = project_path(diagnostic_summary.get("source_candidate_manifest"))
    if candidate_manifest is None or not candidate_manifest.exists():
        raise FileNotFoundError(f"Candidate manifest not found: {diagnostic_summary.get('source_candidate_manifest')}")
    candidates = load_candidates(candidate_manifest)
    plan_rows = read_jsonl(args.dry_run_dir / "postprocessing_dry_run_plan.jsonl")
    items = build_geometry_items(
        plan_rows,
        candidates,
        read_csv_by_id(geometry_log),
        geometry_review_dir / "postprocessing_geometry_reviewer.html",
    )
    if args.limit is not None:
        items = items[: args.limit]

    output_csv = args.output_csv or geometry_review_dir / "postprocessing_geometry_review.gpt55_prefill.csv"
    prefill_dir = geometry_review_dir / "gpt55_geometry_prefill"
    predictions_jsonl = args.predictions_jsonl or prefill_dir / "predictions.jsonl"
    api_input_dir = args.api_input_dir or prefill_dir / "api_inputs"
    existing_predictions = read_csv_by_id(output_csv) if output_csv.exists() and not args.overwrite else {}
    prediction_rows = read_jsonl(predictions_jsonl) if predictions_jsonl.exists() and not args.overwrite else []
    predictions_by_id = {
        str(row.get("geometry_item_id")): row
        for row in prediction_rows
        if row.get("geometry_item_id") and row.get("prediction")
    }
    component_map = related_components(items)

    load_env_file(args.env_file)
    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(f"OPENAI_API_KEY is not set. Checked environment and {args.env_file}.")

    output_rows: list[dict[str, Any]] = []
    new_prediction_rows: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        item_id = str(item["geometry_item_id"])
        row_api_dir = api_input_dir / f"item_{index:03d}_{item_id}"
        image_paths = prepare_overlay_images(item, row_api_dir, args.max_dim, args.image_format)
        prediction: dict[str, Any] | None = None
        if item_id in existing_predictions:
            saved = existing_predictions[item_id]
            prediction = {
                "review_status": saved.get("review_status", "unreviewed"),
                "geometry_decision": saved.get("geometry_decision", ""),
                "corrected_bbox_xyxy": saved.get("corrected_bbox_xyxy", ""),
                "child_bboxes_json": saved.get("child_bboxes_json", ""),
                "target_candidate_ids": saved.get("target_candidate_ids", ""),
                "review_notes": saved.get("review_notes", ""),
            }
        elif item_id in predictions_by_id:
            prediction = normalize_prediction(predictions_by_id[item_id]["prediction"], str(item.get("item_type") or ""))
        elif not args.dry_run:
            print(f"gpt geometry prefill {index}/{len(items)}: {item_id}", flush=True)
            related = {cid: component_map.get(cid, []) for cid in item.get("source_candidate_ids", [])}
            response_text = call_openai(
                args.model,
                args.detail,
                build_prompt_context(item, related),
                image_paths,
                args.image_format,
                args.max_retries,
                args.retry_initial_delay,
            )
            parsed = json.loads(response_text)
            if not isinstance(parsed, dict):
                raise ValueError("GPT response must be a JSON object")
            prediction = normalize_prediction(parsed, str(item.get("item_type") or ""))
            new_prediction_rows.append(
                {
                    "schema": "cloudhammer_v2.postprocessing_geometry_gpt_prefill.v1",
                    "geometry_item_id": item_id,
                    "item_index": index,
                    "model": args.model,
                    "item_type": item.get("item_type"),
                    "source_row_numbers": item.get("source_row_numbers"),
                    "source_candidate_ids": item.get("source_candidate_ids"),
                    "api_input_paths": [str(path) for path in image_paths],
                    "prediction": parsed,
                    "normalized_prediction": prediction,
                }
            )
            if args.request_delay:
                time.sleep(args.request_delay)
        output_rows.append(build_prefill_row(item, prediction))

    all_prediction_rows = prediction_rows + new_prediction_rows if not args.overwrite else new_prediction_rows
    write_csv(output_csv, output_rows)
    if all_prediction_rows:
        write_jsonl(predictions_jsonl, all_prediction_rows)
    summary = summarize(output_rows, all_prediction_rows, args.dry_run)
    summary_json = output_csv.with_suffix(".summary.json")
    summary_md = output_csv.with_suffix(".summary.md")
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_md.write_text(markdown_summary(summary, output_csv, predictions_jsonl, api_input_dir), encoding="utf-8")

    print("GPT-5.5 blocked geometry prefill")
    print(f"- dry_run: {args.dry_run}")
    print(f"- rows: {len(output_rows)}")
    print(f"- api_predictions: {len(all_prediction_rows)}")
    print(f"- output_csv: {output_csv}")
    print(f"- predictions_jsonl: {predictions_jsonl}")
    print(f"- summary: {summary_md}")
    print(f"- api_input_dir: {api_input_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
