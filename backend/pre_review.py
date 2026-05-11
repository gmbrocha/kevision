from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from PIL import Image, ImageDraw, ImageFont

from .revision_state.models import ChangeItem, CloudCandidate, SheetVersion
from .review_queue import is_superseded
from .utils import clean_display_text, json_dumps, normalize_text, stable_id
from .workspace import WorkspaceStore


PRE_REVIEW_KEY = "scopeledger.pre_review.v1"
PRE_REVIEW_SCHEMA = "scopeledger.pre_review.v1"
PROMPT_VERSION = "scopeledger_pre_review_prompt_v1"
BATCH_PROMPT_VERSION = "scopeledger_pre_review_batch_prompt_v1"
PRE_REVIEW_1 = "pre_review_1"
PRE_REVIEW_2 = "pre_review_2"
VALID_PRE_REVIEW_SOURCES = {PRE_REVIEW_1, PRE_REVIEW_2}
GEOMETRY_DECISIONS = {"same_box", "adjusted_box", "partial", "overmerged", "false_positive", "unclear"}
PRE_REVIEW_1_COLOR = "#0f766e"
PRE_REVIEW_2_COLOR = "#d97706"


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["geometry_decision", "boxes", "refined_text", "reason", "confidence", "tags"],
    "properties": {
        "geometry_decision": {"type": "string", "enum": sorted(GEOMETRY_DECISIONS)},
        "boxes": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 4,
                "maxItems": 4,
            },
        },
        "refined_text": {"type": "string"},
        "reason": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}

BATCH_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["item_id", "geometry_decision", "boxes", "refined_text", "reason", "confidence", "tags"],
                "properties": {
                    "item_id": {"type": "string"},
                    "geometry_decision": {"type": "string", "enum": sorted(GEOMETRY_DECISIONS)},
                    "boxes": RESPONSE_SCHEMA["properties"]["boxes"],
                    "refined_text": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}


PROMPT = """You are reviewing one detected drawing revision region before a human reviewer sees it.

You receive one large crop image. The colored rectangle on the image is Pre Review 1, the initial detected region. You also receive OCR text extracted near that region.

Tasks:
- Decide whether Pre Review 1 covers the whole visible revision cloud.
- Decide whether it appears to cover multiple separate clouds.
- Propose Pre Review 2 boxes when the region should be adjusted, split visually, or clarified.
- Refine the OCR text into the concise detail/scope text that should be presented to the reviewer.

Return crop-relative boxes as [x, y, width, height] in the image pixel coordinate system. If Pre Review 1 is already best, return the same box. If multiple boxes are appropriate, return multiple boxes, but they will remain one review item for now.

Policy:
- Do not auto-approve or auto-reject the item.
- Do not infer scope beyond visible evidence and OCR/context.
- Ignore random dimensions, standalone numbers, sheet index tables, title block noise, and broad unrelated text unless they are clearly part of the clouded scope.
- Treat your response as provisional pre-review metadata only; the human reviewer selection is final.

Return JSON only.
"""

BATCH_PROMPT = PROMPT.replace(
    "You receive one large crop image.",
    "You receive multiple large crop images, one per item_id.",
).replace(
    "Return JSON only.",
    "Return JSON only. Return one result per item_id in the provided Candidate contexts JSON.",
)


@dataclass(frozen=True)
class PreReviewContext:
    item: ChangeItem
    cloud: CloudCandidate
    sheet: SheetVersion
    crop_path: Path
    crop_size: tuple[int, int]
    pre_review_1: dict[str, Any]
    cache_dir: Path


@dataclass
class PreReviewRunSummary:
    total_count: int = 0
    pre_review_2_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    cache_hits: int = 0
    disabled_reason: str = ""
    batch_size: int = 1
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_input_tokens: int = 0

    def to_status(self) -> dict[str, object]:
        return {
            "pre_review_total_count": self.total_count,
            "pre_review_2_count": self.pre_review_2_count,
            "pre_review_skipped_count": self.skipped_count,
            "pre_review_failed_count": self.failed_count,
            "pre_review_cache_hits": self.cache_hits,
            "pre_review_disabled_reason": self.disabled_reason,
            "pre_review_batch_size": self.batch_size,
            "pre_review_request_count": self.request_count,
            "pre_review_input_tokens": self.input_tokens,
            "pre_review_output_tokens": self.output_tokens,
            "pre_review_total_tokens": self.total_tokens,
            "pre_review_cached_input_tokens": self.cached_input_tokens,
        }


class PreReviewProvider(Protocol):
    name: str
    enabled: bool
    disabled_reason: str

    def review(self, context: PreReviewContext) -> dict[str, Any] | None:
        ...

    def review_batch(self, contexts: list[PreReviewContext]) -> dict[str, dict[str, Any]]:
        ...


class DisabledPreReviewProvider:
    name = "disabled"
    enabled = False

    def __init__(self, reason: str = "disabled"):
        self.disabled_reason = reason

    def review(self, context: PreReviewContext) -> dict[str, Any] | None:
        return None

    def review_batch(self, contexts: list[PreReviewContext]) -> dict[str, dict[str, Any]]:
        return {}


class OpenAIPreReviewProvider:
    name = "pre_review_api"
    enabled = True
    disabled_reason = ""

    def __init__(
        self,
        *,
        model: str = "gpt-5.5",
        max_retries: int = 2,
        retry_initial_delay: float = 1.5,
        image_format: str = "png",
        batch_size: int = 5,
    ):
        self.model = model
        self.max_retries = max_retries
        self.retry_initial_delay = retry_initial_delay
        self.image_format = image_format
        self.batch_size = max(1, min(10, int(batch_size or 1)))

    def review(self, context: PreReviewContext) -> dict[str, Any] | None:
        cache_dir = context.cache_dir / "cache"
        api_input_dir = context.cache_dir / "api_inputs"
        cache_dir.mkdir(parents=True, exist_ok=True)
        api_input_dir.mkdir(parents=True, exist_ok=True)
        cache_key = _cache_key(self.model, context)
        cache_path = cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            result = dict(payload.get("result") or {})
            result["cache_hit"] = True
            result["usage"] = payload.get("usage") or result.get("usage") or {}
            return result

        input_image = _write_api_overlay(context, api_input_dir / f"{cache_key}.{self.image_format}")
        try:
            call = _coerce_call_result(self._call_openai(context, input_image))
        except Exception as exc:
            _append_usage_event(
                context.cache_dir,
                {
                    "event_type": "api_request_failed",
                    "prompt_version": PROMPT_VERSION,
                    "model": self.model,
                    "item_ids": [context.item.id],
                    "batch_size": 1,
                    "usage": {},
                    "request_meta": {},
                    "cache_hit": False,
                    "failure_reason": _compact_error(exc),
                },
            )
            raise
        raw_text = call["text"]
        try:
            payload = json.loads(raw_text)
            result = normalize_pre_review_2(payload, context)
        except Exception as exc:
            _append_usage_event(
                context.cache_dir,
                {
                    "event_type": "api_request_failed",
                    "prompt_version": PROMPT_VERSION,
                    "model": self.model,
                    "item_ids": [context.item.id],
                    "batch_size": 1,
                    "usage": call["usage"],
                    "request_meta": call["meta"],
                    "cache_hit": False,
                    "failure_reason": _compact_error(exc),
                },
            )
            raise
        result["cache_hit"] = False
        result["usage"] = call["usage"]
        result["request_meta"] = call["meta"]
        cache_path.write_text(
            json_dumps(
                {
                    "schema": "scopeledger.pre_review_cache.v1",
                    "prompt_version": PROMPT_VERSION,
                    "model": self.model,
                    "item_id": context.item.id,
                    "cloud_id": context.cloud.id,
                    "api_input_path": str(input_image),
                    "usage": call["usage"],
                    "request_meta": call["meta"],
                    "result": result,
                }
            ),
            encoding="utf-8",
        )
        _append_usage_event(
            context.cache_dir,
            {
                "event_type": "api_request",
                "prompt_version": PROMPT_VERSION,
                "model": self.model,
                "item_ids": [context.item.id],
                "batch_size": 1,
                "usage": call["usage"],
                "request_meta": call["meta"],
                "cache_hit": False,
            },
        )
        return result

    def review_batch(self, contexts: list[PreReviewContext]) -> dict[str, dict[str, Any]]:
        if not contexts:
            return {}
        cache_dir = contexts[0].cache_dir / "cache"
        api_input_dir = contexts[0].cache_dir / "api_inputs"
        cache_dir.mkdir(parents=True, exist_ok=True)
        api_input_dir.mkdir(parents=True, exist_ok=True)
        results: dict[str, dict[str, Any]] = {}
        pending: list[tuple[PreReviewContext, str, Path]] = []
        for context in contexts:
            cache_key = _cache_key(self.model, context, prompt_version=BATCH_PROMPT_VERSION)
            cache_path = cache_dir / f"{cache_key}.json"
            legacy_path = cache_dir / f"{_cache_key(self.model, context, prompt_version=PROMPT_VERSION)}.json"
            existing_path = cache_path if cache_path.exists() else legacy_path if legacy_path.exists() else None
            if existing_path is not None:
                payload = json.loads(existing_path.read_text(encoding="utf-8"))
                result = dict(payload.get("result") or {})
                result["cache_hit"] = True
                result["usage"] = payload.get("usage") or result.get("usage") or {}
                results[context.item.id] = result
                continue
            input_image = _write_api_overlay(context, api_input_dir / f"{cache_key}.{self.image_format}")
            pending.append((context, cache_key, input_image))

        if not pending:
            return results

        try:
            call = _coerce_call_result(self._call_openai_batch([item[0] for item in pending], [item[2] for item in pending]))
        except Exception as exc:
            _append_usage_event(
                contexts[0].cache_dir,
                {
                    "event_type": "api_batch_request_failed",
                    "prompt_version": BATCH_PROMPT_VERSION,
                    "model": self.model,
                    "item_ids": [item[0].item.id for item in pending],
                    "batch_size": len(pending),
                    "usage": {},
                    "request_meta": {},
                    "cache_hit": False,
                    "failure_reason": _compact_error(exc),
                },
            )
            raise
        try:
            raw_results = _batch_results_by_item_id(json.loads(call["text"]), [item[0].item.id for item in pending])
        except Exception as exc:
            _append_usage_event(
                contexts[0].cache_dir,
                {
                    "event_type": "api_batch_request_failed",
                    "prompt_version": BATCH_PROMPT_VERSION,
                    "model": self.model,
                    "item_ids": [item[0].item.id for item in pending],
                    "batch_size": len(pending),
                    "usage": call["usage"],
                    "request_meta": call["meta"],
                    "cache_hit": False,
                    "failure_reason": _compact_error(exc),
                },
            )
            raise
        allocations = _allocated_usage(call["usage"], len(pending))
        for index, (context, cache_key, input_image) in enumerate(pending):
            raw_result = raw_results.get(context.item.id)
            if raw_result is None:
                continue
            result = normalize_pre_review_2(raw_result, context)
            result["cache_hit"] = False
            result["usage"] = allocations[min(index, len(allocations) - 1)] if allocations else {}
            result["request_meta"] = call["meta"]
            cache_path = cache_dir / f"{cache_key}.json"
            cache_path.write_text(
                json_dumps(
                    {
                        "schema": "scopeledger.pre_review_cache.v1",
                        "prompt_version": BATCH_PROMPT_VERSION,
                        "model": self.model,
                        "item_id": context.item.id,
                        "cloud_id": context.cloud.id,
                        "api_input_path": str(input_image),
                        "usage": result["usage"],
                        "batch_usage": call["usage"],
                        "request_meta": call["meta"],
                        "result": result,
                    }
                ),
                encoding="utf-8",
            )
            results[context.item.id] = result

        _append_usage_event(
            contexts[0].cache_dir,
            {
                "event_type": "api_batch_request",
                "prompt_version": BATCH_PROMPT_VERSION,
                "model": self.model,
                "item_ids": [item[0].item.id for item in pending],
                "returned_item_ids": sorted(raw_results),
                "batch_size": len(pending),
                "usage": call["usage"],
                "request_meta": call["meta"],
                "cache_hit": False,
            },
        )
        return results

    def _call_openai(self, context: PreReviewContext, input_image: Path) -> dict[str, Any]:
        try:
            from openai import OpenAI  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("openai is not installed. Install requirements.txt before enabling pre-review.") from exc

        client = OpenAI()
        image_part: dict[str, Any] = {"type": "input_image", "image_url": _image_to_data_url(input_image)}
        prompt_context = json.dumps(
            {
                "prompt_version": PROMPT_VERSION,
                "sheet_id": context.sheet.sheet_id,
                "sheet_title": context.sheet.sheet_title,
                "page_number": context.sheet.page_number,
                "pre_review_1_crop_boxes": context.pre_review_1.get("crop_boxes", []),
                "pre_review_1_ocr_text": context.pre_review_1.get("text", ""),
                "pre_review_1_reason": context.pre_review_1.get("reason", ""),
                "confidence": context.cloud.confidence,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        content = [
            {"type": "input_text", "text": PROMPT + "\n\nCandidate context JSON:\n" + prompt_context},
            image_part,
        ]
        attempt = 0
        started_at = time.time()
        while True:
            try:
                response = client.responses.create(
                    model=self.model,
                    input=[{"role": "user", "content": content}],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "scopeledger_pre_review",
                            "schema": RESPONSE_SCHEMA,
                            "strict": True,
                        }
                    },
                )
                return {
                    "text": _extract_response_text(response),
                    "usage": _response_usage(response),
                    "meta": _request_meta(started_at, attempt),
                }
            except Exception as exc:
                if attempt >= self.max_retries or not _is_retryable_openai_error(exc):
                    raise
                attempt += 1
                retry_after = _retry_after_seconds(exc)
                delay = retry_after if retry_after is not None else self.retry_initial_delay * (2 ** (attempt - 1))
                time.sleep(min(max(0.0, delay), 30.0))

    def _call_openai_batch(self, contexts: list[PreReviewContext], input_images: list[Path]) -> dict[str, Any]:
        try:
            from openai import OpenAI  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("openai is not installed. Install requirements.txt before enabling pre-review.") from exc

        client = OpenAI()
        prompt_context = json.dumps(
            {
                "prompt_version": BATCH_PROMPT_VERSION,
                "items": [_prompt_context(context) for context in contexts],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        content: list[dict[str, Any]] = [{"type": "input_text", "text": BATCH_PROMPT + "\n\nCandidate contexts JSON:\n" + prompt_context}]
        for context, input_image in zip(contexts, input_images):
            content.append({"type": "input_text", "text": f"Image for item_id: {context.item.id}"})
            content.append({"type": "input_image", "image_url": _image_to_data_url(input_image)})

        attempt = 0
        started_at = time.time()
        while True:
            try:
                response = client.responses.create(
                    model=self.model,
                    input=[{"role": "user", "content": content}],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "scopeledger_pre_review_batch",
                            "schema": BATCH_RESPONSE_SCHEMA,
                            "strict": True,
                        }
                    },
                )
                return {
                    "text": _extract_response_text(response),
                    "usage": _response_usage(response),
                    "meta": _request_meta(started_at, attempt),
                }
            except Exception as exc:
                if attempt >= self.max_retries or not _is_retryable_openai_error(exc):
                    raise
                attempt += 1
                retry_after = _retry_after_seconds(exc)
                delay = retry_after if retry_after is not None else self.retry_initial_delay * (2 ** (attempt - 1))
                time.sleep(min(max(0.0, delay), 30.0))


def build_pre_review_provider_from_env() -> PreReviewProvider:
    if not _truthy(os.getenv("SCOPELEDGER_PREREVIEW_ENABLED", "")):
        return DisabledPreReviewProvider("disabled")
    if not os.getenv("OPENAI_API_KEY"):
        return DisabledPreReviewProvider("missing_api_key")
    return OpenAIPreReviewProvider(
        model=os.getenv("SCOPELEDGER_PREREVIEW_MODEL", "gpt-5.5"),
        batch_size=_configured_batch_size(os.getenv("SCOPELEDGER_PREREVIEW_BATCH_SIZE", "")),
    )


def ensure_workspace_pre_review(
    store: WorkspaceStore,
    provider: PreReviewProvider | None = None,
    *,
    force: bool = False,
    progress_callback: Callable[[PreReviewRunSummary], None] | None = None,
) -> PreReviewRunSummary:
    provider = provider or DisabledPreReviewProvider()
    sheets_by_id = {sheet.id: sheet for sheet in store.data.sheets}
    clouds_by_id = {cloud.id: cloud for cloud in store.data.clouds}
    updated_items: list[ChangeItem] = list(store.data.change_items)
    entries: list[dict[str, Any]] = []

    for index, item in enumerate(store.data.change_items):
        cloud = clouds_by_id.get(item.cloud_candidate_id or "")
        sheet = sheets_by_id.get(item.sheet_version_id)
        if is_superseded(item) or not cloud or not sheet or item.provenance.get("source") != "visual-region":
            continue
        entries.append(
            {
                "index": index,
                "item": item,
                "cloud": cloud,
                "sheet": sheet,
                "context": build_pre_review_context(store, item, cloud, sheet),
            }
        )

    summary = PreReviewRunSummary(
        total_count=len(entries),
        batch_size=_provider_batch_size(provider),
        disabled_reason="" if provider.enabled else provider.disabled_reason,
    )
    changed = False

    def emit() -> None:
        if progress_callback:
            progress_callback(summary)

    def apply_entry(entry: dict[str, Any], pre_review_2: dict[str, Any] | None, status: str, error: str = "") -> None:
        nonlocal changed
        item: ChangeItem = entry["item"]
        cloud: CloudCandidate = entry["cloud"]
        context: PreReviewContext | None = entry["context"]
        existing = pre_review_payload(item)
        selected = str(existing.get("selected") or PRE_REVIEW_1)
        if selected not in VALID_PRE_REVIEW_SOURCES or (selected == PRE_REVIEW_2 and not pre_review_2):
            selected = PRE_REVIEW_1
        pre_review_1 = context.pre_review_1 if context is not None else _fallback_pre_review_1(item, cloud)
        payload: dict[str, Any] = {
            "schema": PRE_REVIEW_SCHEMA,
            "selected": selected,
            "status": status,
            "provider": provider.name,
            PRE_REVIEW_1: pre_review_1,
            PRE_REVIEW_2: pre_review_2 or _empty_pre_review_2(),
        }
        if error:
            payload["error"] = error
        provenance = {**item.provenance, PRE_REVIEW_KEY: payload}
        reviewer_text = item.reviewer_text or selected_pre_review_text(payload) or item.raw_text
        updated = ChangeItem(
            id=item.id,
            sheet_version_id=item.sheet_version_id,
            cloud_candidate_id=item.cloud_candidate_id,
            sheet_id=item.sheet_id,
            detail_ref=item.detail_ref,
            raw_text=item.raw_text,
            normalized_text=item.normalized_text,
            provenance=provenance,
            status=item.status,
            reviewer_text=reviewer_text,
            reviewer_notes=item.reviewer_notes,
            queue_order=item.queue_order,
            parent_change_item_id=item.parent_change_item_id,
            superseded_by_change_item_ids=list(item.superseded_by_change_item_ids),
            superseded_reason=item.superseded_reason,
            superseded_at=item.superseded_at,
        )
        if updated != updated_items[entry["index"]]:
            changed = True
        updated_items[entry["index"]] = updated
        entry["item"] = updated

    pending_batch: list[dict[str, Any]] = []

    def flush_batch() -> None:
        nonlocal changed
        if not pending_batch:
            return
        contexts = [entry["context"] for entry in pending_batch if entry["context"] is not None]
        attempted_request = False
        try:
            if _provider_batch_size(provider) > 1 and hasattr(provider, "review_batch") and len(contexts) > 1:
                attempted_request = True
                results = provider.review_batch(contexts)  # type: ignore[attr-defined]
            else:
                results = {}
                for context in contexts:
                    attempted_request = True
                    result = provider.review(context)
                    if result:
                        results[context.item.id] = result
                        if not result.get("cache_hit"):
                            summary.request_count += 1
            if attempted_request and any(not (results.get(context.item.id) or {}).get("cache_hit") for context in contexts):
                summary.request_count += 1
            for entry in pending_batch:
                context = entry["context"]
                result = results.get(context.item.id) if context is not None else None
                if result:
                    apply_entry(entry, result, "complete")
                    summary.pre_review_2_count += 1
                    if result.get("cache_hit"):
                        summary.cache_hits += 1
                    else:
                        _add_usage_to_summary(summary, result.get("usage"))
                else:
                    apply_entry(entry, None, "failed", "Pre-review response was missing for this item.")
                    summary.failed_count += 1
        except Exception as exc:
            if attempted_request:
                summary.request_count += 1
            for entry in pending_batch:
                apply_entry(entry, None, "failed", _compact_error(exc))
                summary.failed_count += 1
        finally:
            if changed:
                store.data.change_items = updated_items
                store.save()
            emit()
            pending_batch.clear()

    for entry in entries:
        item: ChangeItem = entry["item"]
        context: PreReviewContext | None = entry["context"]
        existing = pre_review_payload(item)
        pre_review_2 = existing.get(PRE_REVIEW_2) if isinstance(existing.get(PRE_REVIEW_2), dict) else None
        if pre_review_2 and pre_review_2.get("available") and not force:
            summary.pre_review_2_count += 1
            continue
        if not provider.enabled:
            apply_entry(entry, None, "skipped")
            summary.skipped_count += 1
            continue
        if context is None:
            apply_entry(entry, None, "missing_crop")
            summary.skipped_count += 1
            continue
        pending_batch.append(entry)
        if len(pending_batch) >= _provider_batch_size(provider):
            flush_batch()

    flush_batch()
    if changed:
        store.data.change_items = updated_items
        store.save()
    emit()
    return summary


def build_pre_review_context(
    store: WorkspaceStore,
    item: ChangeItem,
    cloud: CloudCandidate,
    sheet: SheetVersion,
) -> PreReviewContext | None:
    crop_path = store.resolve_path(cloud.image_path)
    if not crop_path.exists():
        return None
    try:
        with Image.open(crop_path) as image:
            crop_size = image.size
    except Exception:
        return None
    pre_review_1 = _build_pre_review_1(item, cloud, sheet, crop_size)
    return PreReviewContext(
        item=item,
        cloud=cloud,
        sheet=sheet,
        crop_path=crop_path,
        crop_size=crop_size,
        pre_review_1=pre_review_1,
        cache_dir=store.output_dir / "pre_review",
    )


def pre_review_payload(item: ChangeItem) -> dict[str, Any]:
    value = item.provenance.get(PRE_REVIEW_KEY)
    return value if isinstance(value, dict) else {}


def selected_pre_review_text(payload: dict[str, Any]) -> str:
    selected = str(payload.get("selected") or PRE_REVIEW_1)
    entry = payload.get(selected)
    if isinstance(entry, dict):
        return str(entry.get("text") or "")
    return ""


def selected_pre_review_page_boxes(item: ChangeItem) -> list[list[float]]:
    payload = pre_review_payload(item)
    selected = str(payload.get("selected") or PRE_REVIEW_1)
    entry = payload.get(selected)
    if not isinstance(entry, dict):
        return []
    return _valid_boxes(entry.get("boxes"))


def select_pre_review_source(item: ChangeItem, source: str) -> ChangeItem:
    if source not in VALID_PRE_REVIEW_SOURCES:
        return item
    payload = pre_review_payload(item)
    if not payload:
        return item
    entry = payload.get(source)
    if not isinstance(entry, dict):
        return item
    if source == PRE_REVIEW_2 and not entry.get("available"):
        return item
    updated_payload = {**payload, "selected": source}
    text = str(entry.get("text") or item.raw_text)
    return ChangeItem(
        id=item.id,
        sheet_version_id=item.sheet_version_id,
        cloud_candidate_id=item.cloud_candidate_id,
        sheet_id=item.sheet_id,
        detail_ref=item.detail_ref,
        raw_text=item.raw_text,
        normalized_text=item.normalized_text,
        provenance={**item.provenance, PRE_REVIEW_KEY: updated_payload},
        status=item.status,
        reviewer_text=text,
        reviewer_notes=item.reviewer_notes,
    )


def build_pre_review_overlay_image(
    store: WorkspaceStore,
    item: ChangeItem,
    cloud: CloudCandidate,
    output_path: Path,
    *,
    include_all: bool,
) -> Path | None:
    crop_path = store.resolve_path(cloud.image_path)
    if not crop_path.exists():
        return None
    with Image.open(crop_path) as source:
        image = source.convert("RGB")
    payload = pre_review_payload(item)
    if not payload:
        payload = {
            "selected": PRE_REVIEW_1,
            PRE_REVIEW_1: _fallback_pre_review_1(item, cloud),
            PRE_REVIEW_2: _empty_pre_review_2(),
        }
    draw = ImageDraw.Draw(image)
    if include_all:
        _draw_entry_boxes(draw, image.size, payload.get(PRE_REVIEW_1), PRE_REVIEW_1_COLOR, "Pre Review 1")
        _draw_entry_boxes(draw, image.size, payload.get(PRE_REVIEW_2), PRE_REVIEW_2_COLOR, "Pre Review 2")
    else:
        selected = str(payload.get("selected") or PRE_REVIEW_1)
        color = PRE_REVIEW_2_COLOR if selected == PRE_REVIEW_2 else PRE_REVIEW_1_COLOR
        _draw_entry_boxes(draw, image.size, payload.get(selected), color, "Selected")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=True)
    return output_path


def normalize_pre_review_2(payload: dict[str, Any], context: PreReviewContext) -> dict[str, Any]:
    decision = str(payload.get("geometry_decision") or "unclear")
    if decision not in GEOMETRY_DECISIONS:
        decision = "unclear"
    crop_boxes = _normalize_crop_boxes(payload.get("boxes"), context.crop_size)
    if not crop_boxes:
        crop_boxes = _valid_boxes(context.pre_review_1.get("crop_boxes"))
    if not crop_boxes:
        crop_boxes = [[0.0, 0.0, float(context.crop_size[0]), float(context.crop_size[1])]]
    page_boxes = [_crop_box_to_sheet_box(box, context.cloud, context.sheet, context.crop_size) for box in crop_boxes]
    try:
        confidence = max(0.0, min(1.0, float(payload.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0
    tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
    return {
        "available": True,
        "source": PRE_REVIEW_2,
        "label": "Pre Review 2",
        "geometry_decision": decision,
        "boxes": page_boxes,
        "crop_boxes": crop_boxes,
        "text": clean_display_text(str(payload.get("refined_text") or context.pre_review_1.get("text") or "")),
        "reason": clean_display_text(str(payload.get("reason") or decision)),
        "confidence": round(confidence, 3),
        "tags": [clean_display_text(str(tag)) for tag in tags if clean_display_text(str(tag))],
    }


def _build_pre_review_1(
    item: ChangeItem,
    cloud: CloudCandidate,
    sheet: SheetVersion,
    crop_size: tuple[int, int],
) -> dict[str, Any]:
    crop_boxes = _pre_review_1_crop_boxes(cloud, sheet, crop_size)
    return {
        "available": True,
        "source": PRE_REVIEW_1,
        "label": "Pre Review 1",
        "geometry_decision": "same_box",
        "boxes": [[float(value) for value in cloud.bbox]],
        "crop_boxes": crop_boxes,
        "text": clean_display_text(item.raw_text or cloud.scope_text or cloud.nearby_text),
        "reason": clean_display_text(cloud.scope_reason or "initial detected region"),
        "confidence": round(float(cloud.confidence or 0.0), 3),
        "tags": [],
    }


def _fallback_pre_review_1(item: ChangeItem, cloud: CloudCandidate) -> dict[str, Any]:
    return {
        "available": True,
        "source": PRE_REVIEW_1,
        "label": "Pre Review 1",
        "geometry_decision": "same_box",
        "boxes": [[float(value) for value in cloud.bbox]],
        "crop_boxes": [],
        "text": clean_display_text(item.raw_text or cloud.scope_text or cloud.nearby_text),
        "reason": clean_display_text(cloud.scope_reason or "initial detected region"),
        "confidence": round(float(cloud.confidence or 0.0), 3),
        "tags": [],
    }


def _empty_pre_review_2() -> dict[str, Any]:
    return {
        "available": False,
        "source": PRE_REVIEW_2,
        "label": "Pre Review 2",
        "geometry_decision": "unclear",
        "boxes": [],
        "crop_boxes": [],
        "text": "",
        "reason": "",
        "confidence": 0.0,
        "tags": [],
    }


def _pre_review_1_crop_boxes(cloud: CloudCandidate, sheet: SheetVersion, crop_size: tuple[int, int]) -> list[list[float]]:
    metadata = cloud.metadata or {}
    raw_bbox = _xyxy_from_metadata(metadata.get("bbox_page_xyxy")) or _xyxy_from_xywh(metadata.get("bbox_page_xywh"))
    crop_box = _xyxy_from_metadata(metadata.get("crop_box_page_xyxy")) or _xyxy_from_xywh(metadata.get("crop_box_page_xywh"))
    if raw_bbox and crop_box:
        return [_raw_page_box_to_crop_box(raw_bbox, crop_box, crop_size)]
    sheet_box = _xyxy_from_xywh(cloud.bbox)
    crop_sheet_box = _crop_sheet_box_from_metadata(metadata, sheet) or sheet_box
    return [_raw_page_box_to_crop_box(sheet_box, crop_sheet_box, crop_size)]


def _crop_sheet_box_from_metadata(metadata: dict[str, Any], sheet: SheetVersion) -> list[float] | None:
    crop_box = _xyxy_from_metadata(metadata.get("crop_box_page_xyxy")) or _xyxy_from_xywh(metadata.get("crop_box_page_xywh"))
    if not crop_box:
        return None
    source_width = _positive_float(metadata.get("page_width"), sheet.width)
    source_height = _positive_float(metadata.get("page_height"), sheet.height)
    scale_x = float(sheet.width or source_width) / source_width if source_width else 1.0
    scale_y = float(sheet.height or source_height) / source_height if source_height else 1.0
    return [crop_box[0] * scale_x, crop_box[1] * scale_y, crop_box[2] * scale_x, crop_box[3] * scale_y]


def _crop_box_to_sheet_box(
    crop_box: list[float],
    cloud: CloudCandidate,
    sheet: SheetVersion,
    crop_size: tuple[int, int],
) -> list[float]:
    metadata = cloud.metadata or {}
    raw_crop = _xyxy_from_metadata(metadata.get("crop_box_page_xyxy")) or _xyxy_from_xywh(metadata.get("crop_box_page_xywh"))
    if not raw_crop:
        return [float(value) for value in cloud.bbox]
    crop_width, crop_height = crop_size
    x, y, width, height = crop_box
    raw_width = raw_crop[2] - raw_crop[0]
    raw_height = raw_crop[3] - raw_crop[1]
    raw_x1 = raw_crop[0] + (x / max(crop_width, 1)) * raw_width
    raw_y1 = raw_crop[1] + (y / max(crop_height, 1)) * raw_height
    raw_x2 = raw_crop[0] + ((x + width) / max(crop_width, 1)) * raw_width
    raw_y2 = raw_crop[1] + ((y + height) / max(crop_height, 1)) * raw_height
    source_width = _positive_float(metadata.get("page_width"), sheet.width)
    source_height = _positive_float(metadata.get("page_height"), sheet.height)
    scale_x = float(sheet.width or source_width) / source_width if source_width else 1.0
    scale_y = float(sheet.height or source_height) / source_height if source_height else 1.0
    return [
        round(raw_x1 * scale_x, 3),
        round(raw_y1 * scale_y, 3),
        round(max(1.0, raw_x2 - raw_x1) * scale_x, 3),
        round(max(1.0, raw_y2 - raw_y1) * scale_y, 3),
    ]


def _raw_page_box_to_crop_box(box_xyxy: list[float], crop_xyxy: list[float], crop_size: tuple[int, int]) -> list[float]:
    crop_width = max(1.0, crop_xyxy[2] - crop_xyxy[0])
    crop_height = max(1.0, crop_xyxy[3] - crop_xyxy[1])
    image_width, image_height = crop_size
    x1 = ((box_xyxy[0] - crop_xyxy[0]) / crop_width) * image_width
    y1 = ((box_xyxy[1] - crop_xyxy[1]) / crop_height) * image_height
    x2 = ((box_xyxy[2] - crop_xyxy[0]) / crop_width) * image_width
    y2 = ((box_xyxy[3] - crop_xyxy[1]) / crop_height) * image_height
    return _clip_crop_xywh([x1, y1, x2 - x1, y2 - y1], crop_size)


def _normalize_crop_boxes(boxes: Any, crop_size: tuple[int, int]) -> list[list[float]]:
    if not isinstance(boxes, list):
        return []
    normalized = []
    for value in boxes:
        if not isinstance(value, list) or len(value) != 4:
            continue
        try:
            box = [float(part) for part in value]
        except (TypeError, ValueError):
            continue
        clipped = _clip_crop_xywh(box, crop_size)
        if clipped[2] > 0 and clipped[3] > 0:
            normalized.append(clipped)
    return normalized[:8]


def _clip_crop_xywh(box: list[float], crop_size: tuple[int, int]) -> list[float]:
    image_width, image_height = crop_size
    x, y, width, height = box
    if width < 0:
        x += width
        width = abs(width)
    if height < 0:
        y += height
        height = abs(height)
    x1 = max(0.0, min(float(image_width), x))
    y1 = max(0.0, min(float(image_height), y))
    x2 = max(0.0, min(float(image_width), x + width))
    y2 = max(0.0, min(float(image_height), y + height))
    return [round(x1, 3), round(y1, 3), round(max(0.0, x2 - x1), 3), round(max(0.0, y2 - y1), 3)]


def _valid_boxes(value: Any) -> list[list[float]]:
    if not isinstance(value, list):
        return []
    boxes = []
    for item in value:
        if not isinstance(item, list) or len(item) != 4:
            continue
        try:
            box = [float(part) for part in item]
        except (TypeError, ValueError):
            continue
        if box[2] > 0 and box[3] > 0:
            boxes.append(box)
    return boxes


def _draw_entry_boxes(draw: ImageDraw.ImageDraw, image_size: tuple[int, int], entry: Any, color: str, label: str) -> None:
    if not isinstance(entry, dict) or not entry.get("available"):
        return
    boxes = _valid_boxes(entry.get("crop_boxes"))
    if not boxes:
        return
    line_width = max(4, round(max(image_size) / 180))
    font = ImageFont.load_default()
    for index, box in enumerate(boxes, start=1):
        x, y, width, height = box
        rect = (x, y, x + width, y + height)
        for offset in range(line_width):
            draw.rectangle(
                (rect[0] - offset, rect[1] - offset, rect[2] + offset, rect[3] + offset),
                outline=color,
            )
        text = label if len(boxes) == 1 else f"{label}.{index}"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        label_width = text_bbox[2] - text_bbox[0] + 8
        label_height = text_bbox[3] - text_bbox[1] + 6
        label_y = max(0, int(y) - label_height)
        draw.rectangle((int(x), label_y, int(x) + label_width, label_y + label_height), fill=color)
        draw.text((int(x) + 4, label_y + 3), text, fill="white", font=font)


def _write_api_overlay(context: PreReviewContext, output_path: Path) -> Path:
    with Image.open(context.crop_path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    _draw_entry_boxes(draw, image.size, context.pre_review_1, PRE_REVIEW_1_COLOR, "Pre Review 1")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=True)
    return output_path


def _xyxy_from_metadata(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(part) for part in value]
    except (TypeError, ValueError):
        return None
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def _xyxy_from_xywh(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, width, height = [float(part) for part in value]
    except (TypeError, ValueError):
        return None
    if width < 0:
        x += width
        width = abs(width)
    if height < 0:
        y += height
        height = abs(height)
    return [x, y, x + width, y + height]


def _positive_float(value: Any, fallback: Any) -> float:
    try:
        number = float(value or fallback or 1)
    except (TypeError, ValueError):
        number = float(fallback or 1)
    return number if number > 0 else 1.0


def _cache_key(model: str, context: PreReviewContext, *, prompt_version: str = PROMPT_VERSION) -> str:
    crop_hash = hashlib.sha256(context.crop_path.read_bytes()).hexdigest()
    return stable_id(
        prompt_version,
        model,
        context.item.id,
        context.cloud.id,
        crop_hash,
        context.pre_review_1.get("crop_boxes", []),
        normalize_text(str(context.pre_review_1.get("text") or "")),
    )


def _prompt_context(context: PreReviewContext) -> dict[str, Any]:
    return {
        "item_id": context.item.id,
        "sheet_id": context.sheet.sheet_id,
        "sheet_title": context.sheet.sheet_title,
        "page_number": context.sheet.page_number,
        "pre_review_1_crop_boxes": context.pre_review_1.get("crop_boxes", []),
        "pre_review_1_ocr_text": context.pre_review_1.get("text", ""),
        "pre_review_1_reason": context.pre_review_1.get("reason", ""),
        "confidence": context.cloud.confidence,
    }


def _image_to_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _extract_response_text(response: Any) -> str:
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


def _coerce_call_result(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "text": str(value.get("text") or ""),
            "usage": _usage_dict(value.get("usage")),
            "meta": value.get("meta") if isinstance(value.get("meta"), dict) else {},
        }
    return {"text": str(value), "usage": {}, "meta": {}}


def _response_usage(response: Any) -> dict[str, Any]:
    return _usage_dict(getattr(response, "usage", None))


def _usage_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(key): _usage_dict(item) if not isinstance(item, (str, int, float, bool, type(None))) else item for key, item in value.items()}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _usage_dict(model_dump())
        except Exception:
            pass
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _usage_dict(to_dict())
        except Exception:
            pass
    raw = getattr(value, "__dict__", None)
    if isinstance(raw, dict):
        return _usage_dict({key: item for key, item in raw.items() if not key.startswith("_")})
    return {}


def _request_meta(started_at: float, retry_count: int) -> dict[str, Any]:
    return {
        "started_at_unix": round(started_at, 3),
        "duration_seconds": round(max(0.0, time.time() - started_at), 3),
        "retry_count": retry_count,
    }


def _batch_results_by_item_id(payload: dict[str, Any], expected_ids: list[str]) -> dict[str, dict[str, Any]]:
    expected = set(expected_ids)
    mapped: dict[str, dict[str, Any]] = {}
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return mapped
    counts: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict):
            item_id = str(row.get("item_id") or "")
            counts[item_id] = counts.get(item_id, 0) + 1
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("item_id") or "")
        if item_id not in expected or counts.get(item_id, 0) != 1:
            continue
        mapped[item_id] = row
    return mapped


def _allocated_usage(usage: dict[str, Any], count: int) -> list[dict[str, Any]]:
    if not usage or count <= 0:
        return [{} for _ in range(max(0, count))]
    token_fields = {
        "input_tokens",
        "prompt_tokens",
        "output_tokens",
        "completion_tokens",
        "total_tokens",
    }
    nested_token_fields = {"cached_tokens", "reasoning_tokens"}
    allocations = []
    for _ in range(count):
        allocations.append({"allocation_method": "equal_per_item"})
    for key, value in usage.items():
        if key in token_fields and isinstance(value, int):
            parts = _split_int(value, count)
            for index, part in enumerate(parts):
                allocations[index][key] = part
        elif isinstance(value, dict):
            nested_allocations = _allocated_nested_usage(value, count, nested_token_fields)
            for index, nested in enumerate(nested_allocations):
                if nested:
                    allocations[index][key] = nested
        else:
            for allocation in allocations:
                allocation[key] = value
    return allocations


def _allocated_nested_usage(value: dict[str, Any], count: int, token_fields: set[str]) -> list[dict[str, Any]]:
    allocations = [{} for _ in range(count)]
    for key, item in value.items():
        if key in token_fields and isinstance(item, int):
            for index, part in enumerate(_split_int(item, count)):
                allocations[index][key] = part
        else:
            for allocation in allocations:
                allocation[key] = item
    return allocations


def _split_int(value: int, count: int) -> list[int]:
    if count <= 0:
        return []
    base = value // count
    remainder = value % count
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _append_usage_event(cache_dir: Path, payload: dict[str, Any]) -> None:
    usage_dir = cache_dir / "usage"
    usage_dir.mkdir(parents=True, exist_ok=True)
    event = {
        "created_at_unix": round(time.time(), 3),
        **payload,
    }
    with (usage_dir / "pre_review_usage.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def _add_usage_to_summary(summary: PreReviewRunSummary, usage: Any) -> None:
    payload = _usage_dict(usage)
    summary.input_tokens += _int_value(payload, "input_tokens") + _int_value(payload, "prompt_tokens")
    summary.output_tokens += _int_value(payload, "output_tokens") + _int_value(payload, "completion_tokens")
    summary.total_tokens += _int_value(payload, "total_tokens")
    input_details = payload.get("input_tokens_details") if isinstance(payload.get("input_tokens_details"), dict) else {}
    prompt_details = payload.get("prompt_tokens_details") if isinstance(payload.get("prompt_tokens_details"), dict) else {}
    summary.cached_input_tokens += _int_value(input_details, "cached_tokens") + _int_value(prompt_details, "cached_tokens")


def _int_value(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    return int(value) if isinstance(value, int) else 0


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


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _configured_batch_size(value: str) -> int:
    if not value.strip():
        return 5
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError("SCOPELEDGER_PREREVIEW_BATCH_SIZE must be an integer.") from exc
    return max(1, min(10, parsed))


def _provider_batch_size(provider: PreReviewProvider) -> int:
    value = getattr(provider, "batch_size", 1)
    try:
        return max(1, min(10, int(value)))
    except (TypeError, ValueError):
        return 1


def _compact_error(exc: Exception, limit: int = 600) -> str:
    text = " ".join(str(exc).split()) or exc.__class__.__name__
    if len(text) <= limit:
        return text
    return f"{text[:limit - 3].rstrip()}..."
