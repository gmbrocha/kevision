from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from build_postprocessed_crop_inspection_viewer import (
    DEFAULT_CROP_REGEN_DIR,
    DEFAULT_MANIFEST,
    INSPECTION_FIELDNAMES,
    inspection_item_id,
    project_path,
    read_csv_by_id,
    write_csv,
)
from build_postprocessing_dry_run_plan import read_jsonl, write_jsonl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_INSPECTION_DIR = DEFAULT_CROP_REGEN_DIR / "crop_inspection_20260508"
DECISION_OPTIONS = [
    "accept_crop",
    "needs_human_review",
    "reject_no_visible_cloud",
    "reject_bad_crop",
    "reject_multiple_clouds_or_overmerge",
    "needs_expand_or_context",
    "unclear",
]
NEXT_STEP_OPTIONS = [
    "use_for_crop_inspection_or_export",
    "human_review_before_use",
    "route_to_postprocessing_followup",
    "exclude_from_crop_consumption",
    "no_action",
]
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "gpt_status",
        "gpt_decision",
        "confidence",
        "gpt_tags",
        "recommended_next_step",
        "gpt_notes",
    ],
    "properties": {
        "gpt_status": {"type": "string", "enum": ["gpt_prefilled", "needs_followup", "not_actionable"]},
        "gpt_decision": {"type": "string", "enum": DECISION_OPTIONS},
        "confidence": {"type": "number"},
        "gpt_tags": {"type": "array", "items": {"type": "string"}},
        "recommended_next_step": {"type": "string", "enum": NEXT_STEP_OPTIONS},
        "gpt_notes": {"type": "string"},
    },
}


PROMPT = """You are pre-checking CloudHammer postprocessed revision-cloud crop candidates before a human sees the inspection queue.

Each image is a crop from a non-frozen derived candidate manifest. The red solid rectangle is the candidate bbox projected into the crop.

Your task is to decide whether the crop is suitable for downstream crop-based inspection/export.

Decisions:
- accept_crop: one reasonably complete visible revision-clouded area is inside the red bbox, and the crop has enough surrounding context.
- needs_human_review: likely usable but visual evidence is ambiguous or borderline.
- reject_no_visible_cloud: no visible revision cloud is present in or near the red bbox.
- reject_bad_crop: crop is blank, corrupted, clipped, wrong page area, or the red bbox is badly misaligned.
- reject_multiple_clouds_or_overmerge: red bbox appears to combine multiple separate clouds/groups.
- needs_expand_or_context: bbox/crop appears to clip or under-cover the visible cloud, or context is insufficient.
- unclear: evidence is insufficient.

Policy:
- Be conservative. If unsure, use needs_human_review or unclear.
- Do not infer a revision cloud from text, arrows, revision triangles, leaders, or dense linework alone.
- Do not accept a crop when the red box is clearly a broad overmerge across separate clouds.
- This is provisional metadata only; it is not ground truth and must not be treated as training/eval labels.

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


def read_prediction_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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
    x1 = max(box[0], clip[0])
    y1 = max(box[1], clip[1])
    x2 = min(box[2], clip[2])
    y2 = min(box[3], clip[3])
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def to_crop_rect(box: list[float], crop_box: list[float], image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    clipped = intersect_box(box, crop_box)
    if clipped is None:
        return None
    crop_width = crop_box[2] - crop_box[0]
    crop_height = crop_box[3] - crop_box[1]
    if crop_width <= 0 or crop_height <= 0:
        return None
    image_width, image_height = image_size
    left = round(((clipped[0] - crop_box[0]) / crop_width) * image_width)
    top = round(((clipped[1] - crop_box[1]) / crop_height) * image_height)
    right = round(((clipped[2] - crop_box[0]) / crop_width) * image_width)
    bottom = round(((clipped[3] - crop_box[1]) / crop_height) * image_height)
    return (left, top, right, bottom)


def label_box(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], label: str, color: str) -> None:
    x1, y1, _, _ = rect
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    width = bbox[2] - bbox[0] + 8
    height = bbox[3] - bbox[1] + 6
    label_y = max(0, y1 - height)
    draw.rectangle((x1, label_y, x1 + width, label_y + height), fill=color)
    draw.text((x1 + 4, label_y + 3), label, fill="white", font=font)


def safe_stem(value: str, *, max_len: int = 96) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value).strip("_")
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("._-")
    return f"{cleaned}_{digest}" if cleaned else digest


def prepare_overlay_image(row: dict[str, Any], row_number: int, output_dir: Path, max_dim: int, image_format: str) -> Path | None:
    crop_path = project_path(row.get("crop_image_path"))
    crop_box = row.get("crop_box_page_xyxy")
    bbox = row.get("bbox_page_xyxy")
    if crop_path is None or not crop_path.exists() or not valid_box(crop_box) or not valid_box(bbox):
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(crop_path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    rect = to_crop_rect(normalize_box(bbox), normalize_box(crop_box), image.size)
    if rect is not None:
        draw.rectangle(rect, outline="#e11d48", width=6)
        label_box(draw, rect, "candidate bbox", "#e11d48")
    image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    extension = "jpg" if image_format == "jpeg" else image_format
    output_path = output_dir / f"row_{row_number:03d}_{safe_stem(str(row.get('candidate_id') or ''), max_len=72)}.{extension}"
    image.save(output_path, format="JPEG" if image_format == "jpeg" else image_format.upper(), quality=90)
    return output_path


def build_prompt_context(row: dict[str, Any], row_number: int) -> str:
    return json.dumps(
        {
            "row_number": row_number,
            "candidate_id": row.get("candidate_id"),
            "source_page_key": row.get("source_page_key"),
            "postprocessing_action": row.get("postprocessing_action"),
            "postprocessing_label": row.get("postprocessing_label"),
            "crop_status": row.get("crop_status"),
            "confidence": row.get("whole_cloud_confidence") or row.get("confidence"),
            "confidence_tier": row.get("confidence_tier"),
            "size_bucket": row.get("size_bucket"),
            "bbox_page_xyxy": row.get("bbox_page_xyxy"),
            "crop_box_page_xyxy": row.get("crop_box_page_xyxy"),
            "source_candidate_ids": row.get("source_candidate_ids", []),
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
    image_path: Path,
    image_format: str,
    max_retries: int,
    retry_initial_delay: float,
) -> str:
    try:
        from openai import OpenAI  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("openai is not installed. Install requirements.txt before API prefilling.") from exc

    client = OpenAI()
    image_part: dict[str, Any] = {"type": "input_image", "image_url": image_to_data_url(image_path, image_format)}
    if detail != "auto":
        image_part["detail"] = detail
    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": PROMPT + "\n\nCandidate context JSON:\n" + prompt_context},
        image_part,
    ]
    attempt = 0
    while True:
        try:
            response = client.responses.create(
                model=model,
                input=[{"role": "user", "content": content}],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "postprocessed_crop_inspection_prefill",
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


def normalize_prediction(payload: dict[str, Any]) -> dict[str, Any]:
    decision = str(payload.get("gpt_decision") or "unclear")
    if decision not in DECISION_OPTIONS:
        decision = "unclear"
    status = str(payload.get("gpt_status") or "needs_followup")
    if status not in {"gpt_prefilled", "needs_followup", "not_actionable"}:
        status = "needs_followup"
    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    tags = payload.get("gpt_tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(tag).strip() for tag in tags if str(tag).strip()]
    next_step = str(payload.get("recommended_next_step") or "")
    if next_step not in NEXT_STEP_OPTIONS:
        next_step = "human_review_before_use"
    if decision in {"unclear", "needs_human_review"} or confidence < 0.45:
        status = "needs_followup"
        next_step = "human_review_before_use"
    if decision.startswith("reject_") and confidence >= 0.65:
        status = "not_actionable"
        next_step = "exclude_from_crop_consumption"
    if decision == "needs_expand_or_context":
        status = "needs_followup"
        next_step = "route_to_postprocessing_followup"
    if decision == "accept_crop" and confidence >= 0.45:
        status = "gpt_prefilled"
        next_step = "use_for_crop_inspection_or_export"
    notes = str(payload.get("gpt_notes") or "").strip()
    if not notes:
        notes = f"GPT crop precheck decision: {decision}."
    notes = f"GPT-5.5 crop precheck, confidence {confidence:.2f}: {notes}"
    return {
        "gpt_status": status,
        "gpt_decision": decision,
        "gpt_confidence": f"{confidence:.3f}",
        "gpt_tags": " | ".join(tags),
        "recommended_next_step": next_step,
        "gpt_notes": notes,
    }


def build_output_row(row: dict[str, Any], row_number: int, prediction: dict[str, Any] | None) -> dict[str, Any]:
    output = {
        "inspection_item_id": inspection_item_id(row),
        "row_number": row_number,
        "candidate_id": row.get("candidate_id") or "",
        "source_page_key": row.get("source_page_key") or "",
        "postprocessing_action": row.get("postprocessing_action") or "",
        "crop_status": row.get("crop_status") or "",
        "gpt_status": "unreviewed",
        "gpt_decision": "",
        "gpt_confidence": "",
        "gpt_tags": "",
        "recommended_next_step": "",
        "gpt_notes": "",
    }
    if prediction:
        output.update(prediction)
    return output


def summarize(rows: list[dict[str, Any]], prediction_rows: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_decision: dict[str, int] = {}
    by_action: dict[str, int] = {}
    by_next_step: dict[str, int] = {}
    for row in rows:
        by_status[str(row.get("gpt_status") or "unreviewed")] = by_status.get(str(row.get("gpt_status") or "unreviewed"), 0) + 1
        by_action[str(row.get("postprocessing_action") or "")] = by_action.get(str(row.get("postprocessing_action") or ""), 0) + 1
        decision = str(row.get("gpt_decision") or "")
        if decision:
            by_decision[decision] = by_decision.get(decision, 0) + 1
        next_step = str(row.get("recommended_next_step") or "")
        if next_step:
            by_next_step[next_step] = by_next_step.get(next_step, 0) + 1
    return {
        "schema": "cloudhammer_v2.postprocessed_crop_inspection_gpt_prefill_summary.v1",
        "dry_run": dry_run,
        "rows": len(rows),
        "api_predictions": len(prediction_rows),
        "by_postprocessing_action": dict(sorted(by_action.items())),
        "by_gpt_status": dict(sorted(by_status.items())),
        "by_gpt_decision": dict(sorted(by_decision.items())),
        "by_recommended_next_step": dict(sorted(by_next_step.items())),
        "guardrails": [
            "provisional_inspection_metadata_only",
            "non_frozen_derived_manifest_only",
            "no_source_candidate_manifest_edits",
            "no_truth_label_edits",
            "no_eval_manifest_edits",
            "no_prediction_file_edits",
            "no_model_file_edits",
            "no_dataset_or_training_data_writes",
            "not_threshold_tuning",
        ],
    }


def markdown_summary(
    summary: dict[str, Any],
    output_csv: Path,
    predictions_jsonl: Path,
    api_input_dir: Path,
    rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# GPT-5.5 Postprocessed Crop Inspection Prefill",
        "",
        "This is provisional inspection metadata only. It does not modify source manifests, labels, eval truth, predictions, datasets, model files, training data, or threshold-tuning inputs.",
        "",
        f"- Dry run: `{summary['dry_run']}`",
        f"- Rows: `{summary['rows']}`",
        f"- API predictions: `{summary['api_predictions']}`",
        f"- Prefill CSV: `{output_csv}`",
        f"- Prediction JSONL: `{predictions_jsonl}`",
        f"- API overlay inputs: `{api_input_dir}`",
        "",
        "## By GPT Status",
        "",
    ]
    for key, value in summary["by_gpt_status"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## By GPT Decision", ""])
    if summary["by_gpt_decision"]:
        for key, value in summary["by_gpt_decision"].items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- No decisions written.")
    lines.extend(["", "## By Recommended Next Step", ""])
    if summary["by_recommended_next_step"]:
        for key, value in summary["by_recommended_next_step"].items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- No next steps written.")
    focus_rows = [row for row in rows if row.get("gpt_decision") and row.get("gpt_decision") != "accept_crop"]
    lines.extend(["", "## Non-Accepted Rows", ""])
    if focus_rows:
        lines.append("| Row | Decision | Next step | Candidate | Notes |")
        lines.append("| ---: | --- | --- | --- | --- |")
        for row in focus_rows:
            notes = str(row.get("gpt_notes") or "").replace("|", "\\|").replace("\n", " ")
            candidate = str(row.get("candidate_id") or "").replace("|", "\\|")
            lines.append(
                f"| {row.get('row_number')} | `{row.get('gpt_decision')}` | "
                f"`{row.get('recommended_next_step')}` | `{candidate}` | {notes} |"
            )
    else:
        lines.append("- None.")
    lines.extend(["", "All GPT decisions remain provisional until accepted by the review/apply workflow.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Use GPT-5.5 to prefill regenerated postprocessed crop inspection metadata.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--inspection-dir", type=Path, default=DEFAULT_INSPECTION_DIR)
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

    rows = read_jsonl(args.manifest)
    if args.limit is not None:
        rows = rows[: args.limit]

    output_csv = args.output_csv or args.inspection_dir / "postprocessed_crop_inspection.gpt55_prefill.csv"
    prefill_dir = args.inspection_dir / "gpt55_crop_inspection_prefill"
    predictions_jsonl = args.predictions_jsonl or prefill_dir / "predictions.jsonl"
    api_input_dir = args.api_input_dir or prefill_dir / "api_inputs"

    existing_predictions = read_csv_by_id(output_csv) if output_csv.exists() and not args.overwrite else {}
    prediction_rows = read_prediction_rows(predictions_jsonl) if predictions_jsonl.exists() and not args.overwrite else []
    predictions_by_id = {
        str(row.get("inspection_item_id")): row
        for row in prediction_rows
        if row.get("inspection_item_id") and row.get("prediction")
    }

    load_env_file(args.env_file)
    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(f"OPENAI_API_KEY is not set. Checked environment and {args.env_file}.")

    output_rows: list[dict[str, Any]] = []
    new_prediction_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        item_id = inspection_item_id(row)
        row_api_dir = api_input_dir / f"row_{index:03d}"
        image_path = prepare_overlay_image(row, index, row_api_dir, args.max_dim, args.image_format)
        prediction: dict[str, Any] | None = None
        if item_id in existing_predictions:
            saved = existing_predictions[item_id]
            prediction = {
                "gpt_status": saved.get("gpt_status", "unreviewed"),
                "gpt_decision": saved.get("gpt_decision", ""),
                "gpt_confidence": saved.get("gpt_confidence", ""),
                "gpt_tags": saved.get("gpt_tags", ""),
                "recommended_next_step": saved.get("recommended_next_step", ""),
                "gpt_notes": saved.get("gpt_notes", ""),
            }
        elif item_id in predictions_by_id:
            prediction = normalize_prediction(predictions_by_id[item_id]["prediction"])
        elif image_path is None:
            prediction = {
                "gpt_status": "needs_followup",
                "gpt_decision": "reject_bad_crop",
                "gpt_confidence": "0.000",
                "gpt_tags": "missing_or_invalid_crop_input",
                "recommended_next_step": "human_review_before_use",
                "gpt_notes": "GPT-5.5 crop precheck was not called because the crop image, crop box, or bbox was missing/invalid.",
            }
        elif not args.dry_run:
            print(f"gpt crop inspection prefill {index}/{len(rows)}: {item_id}", flush=True)
            response_text = call_openai(
                args.model,
                args.detail,
                build_prompt_context(row, index),
                image_path,
                args.image_format,
                args.max_retries,
                args.retry_initial_delay,
            )
            parsed = json.loads(response_text)
            if not isinstance(parsed, dict):
                raise ValueError("GPT response must be a JSON object")
            prediction = normalize_prediction(parsed)
            new_prediction_rows.append(
                {
                    "schema": "cloudhammer_v2.postprocessed_crop_inspection_gpt_prefill.v1",
                    "inspection_item_id": item_id,
                    "row_number": index,
                    "model": args.model,
                    "candidate_id": row.get("candidate_id"),
                    "source_page_key": row.get("source_page_key"),
                    "postprocessing_action": row.get("postprocessing_action"),
                    "crop_status": row.get("crop_status"),
                    "api_input_path": str(image_path),
                    "prediction": parsed,
                    "normalized_prediction": prediction,
                }
            )
            if args.request_delay:
                time.sleep(args.request_delay)
        output_rows.append(build_output_row(row, index, prediction))

    all_prediction_rows = prediction_rows + new_prediction_rows if not args.overwrite else new_prediction_rows
    write_csv(output_csv, output_rows)
    if all_prediction_rows:
        write_jsonl(predictions_jsonl, all_prediction_rows)
    summary = summarize(output_rows, all_prediction_rows, args.dry_run)
    summary_json = output_csv.with_suffix(".summary.json")
    summary_md = output_csv.with_suffix(".summary.md")
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_md.write_text(markdown_summary(summary, output_csv, predictions_jsonl, api_input_dir, output_rows), encoding="utf-8")

    print("GPT-5.5 postprocessed crop inspection prefill")
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
