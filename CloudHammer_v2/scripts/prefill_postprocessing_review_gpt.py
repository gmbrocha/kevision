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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
DEFAULT_DIAGNOSTIC_DIR = V2_ROOT / "outputs" / "postprocessing_diagnostic_non_frozen_20260504"
DEFAULT_MODEL = "gpt-5.5"
REVIEW_FIELDNAMES = [
    "review_item_id",
    "row_number",
    "diagnostic_id",
    "diagnostic_family",
    "source_page_key",
    "candidate_ids",
    "review_status",
    "review_decision",
    "target_candidate_ids",
    "corrected_bbox_xyxy",
    "review_notes",
]
DECISION_OPTIONS = {
    "fragment_merge_candidate": ["merge", "reject_merge", "split", "tighten", "ignore", "unclear"],
    "duplicate_suppression_candidate": ["suppress_duplicate", "reject_suppress", "ignore", "unclear"],
    "overmerge_split_candidate": ["split", "reject_split", "tighten", "tighten_adjust", "expand", "ignore", "unclear"],
    "loose_localization_candidate": ["tighten", "tighten_adjust", "reject_tighten", "expand", "split", "ignore", "unclear"],
}
ALL_DECISIONS = sorted({value for values in DECISION_OPTIONS.values() for value in values})
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "review_status",
        "review_decision",
        "target_candidate_ids",
        "corrected_bbox_xyxy",
        "review_notes",
        "confidence",
    ],
    "properties": {
        "review_status": {"type": "string", "enum": ["reviewed", "needs_followup", "not_actionable"]},
        "review_decision": {"type": "string", "enum": ALL_DECISIONS},
        "target_candidate_ids": {"type": "array", "items": {"type": "string"}},
        "corrected_bbox_xyxy": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 0,
            "maxItems": 4,
        },
        "review_notes": {"type": "string"},
        "confidence": {"type": "number"},
    },
}


PROMPT = """You are pre-filling a human review log for CloudHammer revision-cloud postprocessing diagnostics.

The images are diagnostic crop panels with overlays:
- red solid box: the candidate box for that panel
- blue/green dashed boxes: other candidate boxes in the same diagnostic row
- amber dashed box: tight member bbox for loose-localization rows, if present

Choose a review decision for the row. The human reviewer will confirm or change it.

Allowed decisions:
- merge: candidate boxes are true fragments of one whole revision cloud and should become one candidate.
- reject_merge: candidate boxes are separate clouds, separate groups, or one/both boxes are loose/overmerged.
- suppress_duplicate: one candidate is a duplicate of another and should be suppressed.
- reject_suppress: candidates are not duplicates.
- split: one candidate appears to contain multiple separate clouds/groups and should split.
- reject_split: the candidate is one valid group and should not split.
- tighten: candidate is valid but bbox is materially too loose.
- tighten_adjust: candidate is valid and should tighten, but the displayed tight-member bbox is also wrong or clips the cloud; corrected geometry needs manual adjustment.
- reject_tighten: bbox is acceptable for export.
- expand: candidate is a fragment or under-covers the visible cloud and should be expanded or merged into a larger full-cloud extent.
- ignore: diagnostic row is not actionable for postprocessing.
- unclear: visual evidence is insufficient.

Important review policy:
- Be conservative. Do not merge just because boxes are close in one axis.
- If a candidate box contains multiple separated clouds, prefer split or reject_merge over merge.
- If the diagnostic is a fragment_merge_candidate and either candidate is a broad overmerge, use reject_merge.
- If a loose-localization row has a clear amber tight-member box that better matches visible cloud geometry, use tighten.
- If the candidate box is too loose but the amber tight-member box clips the cloud or is still too loose in one axis, use tighten_adjust.
- If a loose-localization row under-covers the visible cloud, use expand instead of tighten.
- Do not infer truth from revision triangles or text alone.

Return JSON only. corrected_bbox_xyxy should be [] unless the row should tighten or tighten_adjust and a corrected page-coordinate bbox is obvious from provided metrics.
"""


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_csv_by_id(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["review_item_id"]: row for row in csv.DictReader(handle) if row.get("review_item_id")}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def project_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    candidate = Path(str(value))
    if candidate.exists():
        return candidate.resolve()
    parts = candidate.parts
    for anchor, root in (("CloudHammer", PROJECT_ROOT / "CloudHammer"), ("CloudHammer_v2", V2_ROOT)):
        for index, part in enumerate(parts):
            if part.lower() == anchor.lower():
                relocated = root.joinpath(*parts[index + 1 :])
                if relocated.exists():
                    return relocated.resolve()
    return candidate


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


def review_item_id(row: dict[str, Any], row_number: int) -> str:
    diagnostic_id = str(row.get("diagnostic_id") or "")
    if diagnostic_id:
        return diagnostic_id
    family = str(row.get("diagnostic_family") or "diagnostic")
    source_page_key = str(row.get("source_page_key") or "unknown_page")
    candidate_ids = "|".join(str(value) for value in row.get("candidate_ids", []))
    return f"{row_number}:{family}:{source_page_key}:{candidate_ids}"


def load_candidates(manifest_path: Path) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(manifest_path):
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id:
            by_id[candidate_id] = row
    return by_id


def valid_box(box: Any) -> bool:
    return isinstance(box, list) and len(box) == 4 and all(isinstance(value, (int, float)) for value in box)


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


def short_candidate_id(candidate_id: str) -> str:
    marker = "_whole_"
    index = candidate_id.find(marker)
    return candidate_id[index + 1 :] if index >= 0 else candidate_id[-24:]


def prepare_overlay_images(
    row: dict[str, Any],
    row_number: int,
    candidates: list[dict[str, Any]],
    output_dir: Path,
    max_dim: int,
    image_format: str,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []
    palette = ["#e11d48", "#2563eb", "#16a34a", "#7c3aed"]
    tight_box = row.get("metrics", {}).get("tight_member_bbox_xyxy")
    for candidate_index, candidate in enumerate(candidates, start=1):
        crop_path = project_path(candidate.get("crop_image_path"))
        crop_box = candidate.get("crop_box_page_xyxy")
        if crop_path is None or not crop_path.exists() or not valid_box(crop_box):
            continue
        with Image.open(crop_path) as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image, "RGBA")
        for other_index, other in enumerate(candidates):
            bbox = other.get("bbox_page_xyxy")
            if not valid_box(bbox):
                continue
            rect = to_crop_rect([float(v) for v in bbox], [float(v) for v in crop_box], image.size)
            if rect is None:
                continue
            is_active = other.get("candidate_id") == candidate.get("candidate_id")
            color = palette[0] if is_active else palette[(other_index % (len(palette) - 1)) + 1]
            if is_active:
                draw.rectangle(rect, outline=color, width=6)
            else:
                draw_dashed_rectangle(draw, rect, color=color, width=5)
            label_box(draw, rect, short_candidate_id(str(other.get("candidate_id") or "")), color)
        if valid_box(tight_box):
            rect = to_crop_rect([float(v) for v in tight_box], [float(v) for v in crop_box], image.size)
            if rect is not None:
                draw_dashed_rectangle(draw, rect, color="#f59e0b", width=5)
                label_box(draw, rect, "tight_member_bbox", "#f59e0b")
        image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        extension = "jpg" if image_format == "jpeg" else image_format
        output_path = output_dir / f"row_{row_number:03d}_candidate_{candidate_index:02d}.{extension}"
        image.save(output_path, format="JPEG" if image_format == "jpeg" else image_format.upper(), quality=90)
        output_paths.append(output_path)
    return output_paths


def build_prompt_context(row: dict[str, Any], row_number: int, candidates: list[dict[str, Any]]) -> str:
    family = str(row.get("diagnostic_family") or "")
    return json.dumps(
        {
            "row_number": row_number,
            "diagnostic_id": row.get("diagnostic_id"),
            "diagnostic_family": family,
            "allowed_decisions_for_family": DECISION_OPTIONS.get(family, ["ignore", "unclear"]),
            "source_page_key": row.get("source_page_key"),
            "candidate_ids": row.get("candidate_ids", []),
            "reason": row.get("reason"),
            "suggested_review_focus": row.get("suggested_review_focus"),
            "metrics": row.get("metrics", {}),
            "candidates": [
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "confidence": candidate.get("whole_cloud_confidence") or candidate.get("confidence"),
                    "confidence_tier": candidate.get("confidence_tier"),
                    "size_bucket": candidate.get("size_bucket"),
                    "member_count": candidate.get("member_count"),
                    "group_fill_ratio": candidate.get("group_fill_ratio"),
                    "bbox_page_xyxy": candidate.get("bbox_page_xyxy"),
                    "crop_box_page_xyxy": candidate.get("crop_box_page_xyxy"),
                    "member_boxes_page_xyxy": candidate.get("member_boxes_page_xyxy", []),
                }
                for candidate in candidates
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
        {"type": "input_text", "text": PROMPT + "\n\nDiagnostic row context JSON:\n" + prompt_context}
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
                        "name": "postprocessing_review_prefill",
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


def parse_prediction(text: str) -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("GPT response must be a JSON object")
    return payload


def normalize_prediction(payload: dict[str, Any], family: str) -> dict[str, Any]:
    allowed = DECISION_OPTIONS.get(family, ["ignore", "unclear"])
    decision = str(payload.get("review_decision") or "unclear")
    if decision not in allowed:
        decision = "unclear" if "unclear" in allowed else allowed[-1]
    status = str(payload.get("review_status") or "needs_followup")
    if status not in {"reviewed", "needs_followup", "not_actionable"}:
        status = "needs_followup"
    confidence = float(payload.get("confidence") or 0.0)
    if decision == "unclear" or confidence < 0.45:
        status = "needs_followup"
    target_candidate_ids = payload.get("target_candidate_ids") or []
    if not isinstance(target_candidate_ids, list):
        target_candidate_ids = []
    corrected_bbox = payload.get("corrected_bbox_xyxy") or []
    if not (isinstance(corrected_bbox, list) and len(corrected_bbox) in {0, 4}):
        corrected_bbox = []
    notes = str(payload.get("review_notes") or "").strip()
    if not notes:
        notes = f"GPT prefill decision: {decision}."
    notes = f"GPT-5.5 prefill, confidence {confidence:.2f}: {notes}"
    return {
        "review_status": status,
        "review_decision": decision,
        "target_candidate_ids": " | ".join(str(value) for value in target_candidate_ids),
        "corrected_bbox_xyxy": json.dumps(corrected_bbox, ensure_ascii=False) if corrected_bbox else "",
        "review_notes": notes,
        "gpt_confidence": confidence,
    }


def build_review_row(
    row: dict[str, Any],
    row_number: int,
    prediction: dict[str, Any] | None,
) -> dict[str, Any]:
    family = str(row.get("diagnostic_family") or "")
    candidate_ids = [str(value) for value in row.get("candidate_ids", [])]
    output = {
        "review_item_id": review_item_id(row, row_number),
        "row_number": row_number,
        "diagnostic_id": row.get("diagnostic_id") or "",
        "diagnostic_family": family,
        "source_page_key": row.get("source_page_key") or "",
        "candidate_ids": " | ".join(candidate_ids),
        "review_status": "unreviewed",
        "review_decision": "",
        "target_candidate_ids": "",
        "corrected_bbox_xyxy": "",
        "review_notes": "",
    }
    if prediction:
        output.update(
            {
                "review_status": prediction["review_status"],
                "review_decision": prediction["review_decision"],
                "target_candidate_ids": prediction["target_candidate_ids"],
                "corrected_bbox_xyxy": prediction["corrected_bbox_xyxy"],
                "review_notes": prediction["review_notes"],
            }
        )
    return output


def summarize(review_rows: list[dict[str, Any]], prediction_rows: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_decision: dict[str, int] = {}
    for row in review_rows:
        by_status[str(row.get("review_status") or "unreviewed")] = by_status.get(str(row.get("review_status") or "unreviewed"), 0) + 1
        decision = str(row.get("review_decision") or "")
        if decision:
            by_decision[decision] = by_decision.get(decision, 0) + 1
    return {
        "schema": "cloudhammer_v2.postprocessing_review_gpt_prefill_summary.v1",
        "dry_run": dry_run,
        "rows": len(review_rows),
        "api_predictions": len(prediction_rows),
        "by_review_status": by_status,
        "by_review_decision": by_decision,
    }


def markdown_summary(summary: dict[str, Any], output_csv: Path, predictions_jsonl: Path, api_input_dir: Path) -> str:
    lines = [
        "# GPT-5.5 Postprocessing Review Prefill",
        "",
        "This is review metadata only. It does not modify labels, eval manifests, predictions, datasets, model files, or training data.",
        "",
        f"- Dry run: `{summary['dry_run']}`",
        f"- Rows: `{summary['rows']}`",
        f"- API predictions: `{summary['api_predictions']}`",
        f"- Prefill CSV: `{output_csv}`",
        f"- Prediction JSONL: `{predictions_jsonl}`",
        f"- API overlay inputs: `{api_input_dir}`",
        "",
        "## By Review Status",
        "",
    ]
    for key, value in sorted(summary["by_review_status"].items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## By Review Decision", ""])
    if summary["by_review_decision"]:
        for key, value in sorted(summary["by_review_decision"].items()):
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- No decisions written.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Use GPT-5.5 to prefill postprocessing diagnostic review metadata.")
    parser.add_argument("--diagnostic-dir", type=Path, default=DEFAULT_DIAGNOSTIC_DIR)
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

    diagnostic_dir = args.diagnostic_dir
    summary = read_json(diagnostic_dir / "postprocessing_diagnostic_summary.json")
    diagnostic_rows = read_jsonl(diagnostic_dir / "postprocessing_diagnostic_candidates.jsonl")
    if args.limit is not None:
        diagnostic_rows = diagnostic_rows[: args.limit]
    candidate_manifest = project_path(summary.get("source_candidate_manifest"))
    if candidate_manifest is None or not candidate_manifest.exists():
        raise FileNotFoundError(f"Candidate manifest not found: {summary.get('source_candidate_manifest')}")
    candidates_by_id = load_candidates(candidate_manifest)

    output_csv = args.output_csv or diagnostic_dir / "postprocessing_diagnostic_review_log.gpt55_prefill.csv"
    prefill_dir = diagnostic_dir / "gpt55_review_prefill"
    predictions_jsonl = args.predictions_jsonl or prefill_dir / "predictions.jsonl"
    api_input_dir = args.api_input_dir or prefill_dir / "api_inputs"
    existing_predictions = read_csv_by_id(output_csv) if output_csv.exists() and not args.overwrite else {}
    prediction_rows = read_jsonl(predictions_jsonl) if predictions_jsonl.exists() and not args.overwrite else []
    predictions_by_id = {
        str(row.get("review_item_id")): row
        for row in prediction_rows
        if row.get("review_item_id") and row.get("prediction")
    }

    load_env_file(args.env_file)
    if not args.dry_run and not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(f"OPENAI_API_KEY is not set. Checked environment and {args.env_file}.")

    review_rows: list[dict[str, Any]] = []
    new_prediction_rows: list[dict[str, Any]] = []
    for index, row in enumerate(diagnostic_rows, start=1):
        item_id = review_item_id(row, index)
        candidate_ids = [str(value) for value in row.get("candidate_ids", [])]
        candidates = [candidates_by_id[candidate_id] for candidate_id in candidate_ids if candidate_id in candidates_by_id]
        row_api_dir = api_input_dir / f"row_{index:03d}"
        image_paths = prepare_overlay_images(row, index, candidates, row_api_dir, args.max_dim, args.image_format)
        prediction: dict[str, Any] | None = None
        if item_id in existing_predictions:
            saved = existing_predictions[item_id]
            prediction = {
                "review_status": saved.get("review_status", "unreviewed"),
                "review_decision": saved.get("review_decision", ""),
                "target_candidate_ids": saved.get("target_candidate_ids", ""),
                "corrected_bbox_xyxy": saved.get("corrected_bbox_xyxy", ""),
                "review_notes": saved.get("review_notes", ""),
            }
        elif item_id in predictions_by_id:
            prediction = normalize_prediction(predictions_by_id[item_id]["prediction"], str(row.get("diagnostic_family") or ""))
        elif not args.dry_run:
            print(f"gpt prefill {index}/{len(diagnostic_rows)}: {item_id}", flush=True)
            prompt_context = build_prompt_context(row, index, candidates)
            response_text = call_openai(
                args.model,
                args.detail,
                prompt_context,
                image_paths,
                args.image_format,
                args.max_retries,
                args.retry_initial_delay,
            )
            parsed = parse_prediction(response_text)
            prediction = normalize_prediction(parsed, str(row.get("diagnostic_family") or ""))
            new_prediction_rows.append(
                {
                    "schema": "cloudhammer_v2.postprocessing_review_gpt_prefill.v1",
                    "review_item_id": item_id,
                    "row_number": index,
                    "model": args.model,
                    "diagnostic_family": row.get("diagnostic_family"),
                    "source_page_key": row.get("source_page_key"),
                    "candidate_ids": candidate_ids,
                    "api_input_paths": [str(path) for path in image_paths],
                    "prediction": parsed,
                    "normalized_prediction": prediction,
                }
            )
            if args.request_delay:
                time.sleep(args.request_delay)
        review_rows.append(build_review_row(row, index, prediction))

    all_prediction_rows = prediction_rows + new_prediction_rows if not args.overwrite else new_prediction_rows
    write_csv(output_csv, review_rows, REVIEW_FIELDNAMES)
    if all_prediction_rows:
        write_jsonl(predictions_jsonl, all_prediction_rows)
    summary_payload = summarize(review_rows, all_prediction_rows, args.dry_run)
    summary_json = output_csv.with_suffix(".summary.json")
    summary_md = output_csv.with_suffix(".summary.md")
    summary_json.write_text(json.dumps(summary_payload, indent=2, sort_keys=True), encoding="utf-8")
    summary_md.write_text(markdown_summary(summary_payload, output_csv, predictions_jsonl, api_input_dir), encoding="utf-8")

    print("GPT-5.5 postprocessing review prefill")
    print(f"- dry_run: {args.dry_run}")
    print(f"- rows: {len(review_rows)}")
    print(f"- api_predictions: {len(all_prediction_rows)}")
    print(f"- output_csv: {output_csv}")
    print(f"- predictions_jsonl: {predictions_jsonl}")
    print(f"- summary: {summary_md}")
    print(f"- api_input_dir: {api_input_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
