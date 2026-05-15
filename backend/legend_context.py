from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Iterable

from .revision_state.models import ChangeItem, CloudCandidate, SheetVersion
from .review_queue import is_superseded
from .utils import clean_display_text, normalize_text
from .workspace import WorkspaceStore


LEGEND_CONTEXT_KEY = "scopeledger.legend_context.v1"
LEGEND_CONTEXT_SCHEMA = "scopeledger.legend_context.v1"

LEGEND_HEADER_TERMS = (
    "legend",
    "keynote",
    "keynotes",
    "symbol",
    "symbols",
    "abbreviation",
    "abbreviations",
)
LEGEND_SUPPORT_TERMS = (
    "not all keynotes",
    "not all symbols",
    "existing to remain",
    "to be removed",
    "photolog",
)
SYMBOL_TOKEN_RE = re.compile(
    r"^(?P<token>"
    r"[A-Z]\.\d{1,3}(?:\.\d{1,3})?|"
    r"[A-Z]{1,3}\d{1,4}(?:\.\d+)?|"
    r"\d{1,3}[A-Z]?|"
    r"[A-Z]"
    r")[\s.)\]-]+(?P<description>[A-Z][A-Z0-9 /,.;:'\"()\-]{5,})$",
    re.IGNORECASE,
)
INLINE_SYMBOL_RE = re.compile(
    r"\b(?P<token>"
    r"[A-Z]\.\d{1,3}(?:\.\d{1,3})?|"
    r"[A-Z]{1,3}\d{1,4}(?:\.\d+)?|"
    r"\d{1,3}[A-Z]?|"
    r"[A-Z]"
    r")\b\s*[-:.)]?\s+(?P<description>[A-Z][A-Z0-9 /,.;'\"()\-]{6,120})",
    re.IGNORECASE,
)
SHEET_ID_RE = re.compile(r"^(?:GI|AD|AE|IN|PL|EL|EP|MP|MH|ME|E|M|S|SF|CS)\d{2,4}(?:\.\d+)?$", re.IGNORECASE)
TOKEN_IN_TEXT_RE_TEMPLATE = r"(?<![A-Z0-9.]){token}(?![A-Z0-9.])"  # nosec B105


@dataclass(frozen=True)
class LegendClassification:
    probable: bool
    confidence: float
    reason: str
    definitions: list[dict[str, str]]


def legend_context_payload(item: ChangeItem) -> dict[str, Any]:
    payload = (item.provenance or {}).get(LEGEND_CONTEXT_KEY)
    return dict(payload) if isinstance(payload, dict) else {}


def is_probable_legend_context(item: ChangeItem) -> bool:
    return bool(legend_context_payload(item).get("probable"))


def is_confirmed_legend_context(item: ChangeItem) -> bool:
    return bool(legend_context_payload(item).get("confirmed")) or item.superseded_reason == "legend_context"


def legend_context_text(item: ChangeItem) -> str:
    payload = legend_context_payload(item)
    references = payload.get("resolved_references")
    if isinstance(references, list) and references:
        lines = []
        for reference in references:
            if not isinstance(reference, dict):
                continue
            token = clean_display_text(str(reference.get("token") or ""))
            description = clean_display_text(str(reference.get("description") or ""))
            if token and description:
                lines.append(f"{token}: {description}")
        return "\n".join(lines)
    definitions = payload.get("symbol_definitions")
    if payload.get("probable") and isinstance(definitions, list) and definitions:
        lines = []
        for definition in definitions:
            if not isinstance(definition, dict):
                continue
            token = clean_display_text(str(definition.get("token") or ""))
            description = clean_display_text(str(definition.get("description") or ""))
            if token and description:
                lines.append(f"{token}: {description}")
        return "\n".join(lines)
    return ""


def extract_symbol_definitions(text: str) -> list[dict[str, str]]:
    normalized = _normalize_legend_text(text)
    if not normalized:
        return []

    definitions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for line in _candidate_lines(text):
        match = SYMBOL_TOKEN_RE.match(line)
        if not match:
            continue
        _append_definition(definitions, seen, match.group("token"), match.group("description"))

    if not definitions and any(term in normalized.lower() for term in LEGEND_HEADER_TERMS + LEGEND_SUPPORT_TERMS):
        for match in INLINE_SYMBOL_RE.finditer(normalized):
            token = match.group("token")
            if not _symbol_token_is_specific(token):
                continue
            _append_definition(definitions, seen, token, match.group("description"))
            if len(definitions) >= 24:
                break

    return definitions[:24]


def classify_legend_context(text: str) -> LegendClassification:
    clean = _normalize_legend_text(text)
    lower = clean.lower()
    definitions = extract_symbol_definitions(text)
    has_header = any(term in lower for term in LEGEND_HEADER_TERMS)
    has_support = any(term in lower for term in LEGEND_SUPPORT_TERMS)

    if has_header and definitions:
        confidence = min(0.94, 0.72 + len(definitions) * 0.04)
        return LegendClassification(True, round(confidence, 3), "legend-like text with symbol definitions", definitions)
    if has_support and len(definitions) >= 2:
        return LegendClassification(True, 0.72, "table-like legend context with repeated definitions", definitions)
    if len(definitions) >= 3 and (has_header or has_support):
        return LegendClassification(True, 0.68, "multiple symbol definitions in a legend-like region", definitions)
    return LegendClassification(False, 0.0, "", definitions)


def enrich_workspace_legend_context(store: WorkspaceStore) -> int:
    sheets_by_id = {sheet.id: sheet for sheet in store.data.sheets}
    clouds_by_id = {cloud.id: cloud for cloud in store.data.clouds}
    revision_by_sheet_id = {sheet.id: sheet.revision_set_id for sheet in store.data.sheets}
    updated_items = list(store.data.change_items)
    changed_ids: set[str] = set()
    definition_rows: list[dict[str, Any]] = []

    for index, item in enumerate(store.data.change_items):
        if item.provenance.get("source") != "visual-region":
            continue
        existing = legend_context_payload(item)
        if existing.get("confirmed"):
            if existing.get("symbol_definitions"):
                definition_rows.extend(
                    _definition_rows(
                        item,
                        sheets_by_id.get(item.sheet_version_id),
                        existing.get("symbol_definitions") or [],
                    )
                )
            continue
        if is_superseded(item):
            continue
        cloud = clouds_by_id.get(item.cloud_candidate_id or "")
        sheet = sheets_by_id.get(item.sheet_version_id)
        text = _candidate_text(item, cloud)
        classification = classify_legend_context(text)
        if not classification.probable and not existing.get("probable"):
            continue

        payload = {
            **existing,
            "schema": LEGEND_CONTEXT_SCHEMA,
            "probable": classification.probable,
            "confirmed": bool(existing.get("confirmed", False)),
            "confidence": classification.confidence,
            "reason": classification.reason,
            "symbol_definitions": classification.definitions,
            "resolved_references": existing.get("resolved_references", []),
        }
        updated = _with_legend_payload(item, payload)
        if updated != updated_items[index]:
            updated_items[index] = updated
            changed_ids.add(item.id)
        definition_rows.extend(_definition_rows(updated, sheet, classification.definitions))

    if definition_rows:
        by_id = {item.id: index for index, item in enumerate(updated_items)}
        for item in list(updated_items):
            if item.provenance.get("source") != "visual-region" or is_superseded(item):
                continue
            payload = legend_context_payload(item)
            if payload.get("probable") or payload.get("confirmed"):
                continue
            cloud = clouds_by_id.get(item.cloud_candidate_id or "")
            sheet = sheets_by_id.get(item.sheet_version_id)
            if not sheet:
                continue
            references = _resolve_references(
                _candidate_text(item, cloud),
                definition_rows,
                sheet=sheet,
                revision_set_id=revision_by_sheet_id.get(sheet.id, ""),
            )
            if not references:
                if payload.get("resolved_references"):
                    payload = {**payload, "resolved_references": []}
                else:
                    continue
            else:
                payload = {
                    **payload,
                    "schema": LEGEND_CONTEXT_SCHEMA,
                    "probable": False,
                    "confirmed": False,
                    "resolved_references": references,
                }
            updated = _with_legend_payload(item, payload)
            index = by_id[item.id]
            if updated != updated_items[index]:
                updated_items[index] = updated
                changed_ids.add(item.id)

    if not changed_ids:
        return 0
    store.data.change_items = updated_items
    store.save()
    return len(changed_ids)


def confirm_legend_context_item(
    item: ChangeItem,
    *,
    reviewer_id: str | None,
    review_session_id: str | None,
    confirmed_at: str,
    manual: bool = False,
) -> ChangeItem:
    payload = legend_context_payload(item)
    if not manual and not payload.get("probable") and not payload.get("confirmed"):
        raise ValueError("This review item is not marked as probable legend context.")
    payload = {
        **payload,
        "schema": LEGEND_CONTEXT_SCHEMA,
        "probable": bool(payload.get("probable")),
        "confirmed": True,
        "confirmed_at": confirmed_at,
        "confirmed_by": reviewer_id,
        "review_session_id": review_session_id,
    }
    if manual:
        payload["manual"] = True
        payload.setdefault("reason", "reviewer-marked-legend")
    return replace(
        item,
        provenance={**item.provenance, LEGEND_CONTEXT_KEY: payload},
        superseded_reason="legend_context",
        superseded_at=confirmed_at,
    )


def legend_context_human_result(item: ChangeItem) -> dict[str, Any]:
    payload = legend_context_payload(item)
    return {
        "final_label": "legend_context",
        "legend_context": payload,
        "follow_up_status": False,
    }


def _candidate_text(item: ChangeItem, cloud: CloudCandidate | None) -> str:
    parts = [
        item.raw_text,
        item.reviewer_text,
        cloud.scope_text if cloud else "",
        cloud.nearby_text if cloud else "",
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for part in parts:
        clean = str(part or "").strip()
        key = normalize_text(clean)
        if clean and key and key not in seen:
            unique.append(clean)
            seen.add(key)
    return "\n".join(unique)


def _normalize_legend_text(text: str) -> str:
    return clean_display_text(str(text or "").replace("\r", "\n"))


def _candidate_lines(text: str) -> list[str]:
    raw = str(text or "").replace("\r", "\n")
    lines = [clean_display_text(line) for line in raw.split("\n")]
    return [line for line in lines if line]


def _append_definition(definitions: list[dict[str, str]], seen: set[tuple[str, str]], token: str, description: str) -> None:
    normalized_token = _normalize_token(token)
    normalized_description = _clean_definition(description)
    if not normalized_token or not normalized_description:
        return
    if SHEET_ID_RE.match(normalized_token):
        return
    key = (normalized_token, normalize_text(normalized_description))
    if key in seen:
        return
    seen.add(key)
    definitions.append({"token": normalized_token, "description": normalized_description})


def _clean_definition(description: str) -> str:
    clean = clean_display_text(description)
    clean = re.sub(r"\s+", " ", clean).strip(" -:;,.")
    if len(clean) < 6:
        return ""
    return clean[:220]


def _normalize_token(token: str) -> str:
    return clean_display_text(token).upper().strip(" .:-[]()")


def _symbol_token_is_specific(token: str) -> bool:
    normalized = _normalize_token(token)
    if not normalized:
        return False
    if len(normalized) == 1:
        return True
    return any(char.isdigit() for char in normalized) or "." in normalized


def _definition_rows(item: ChangeItem, sheet: SheetVersion | None, definitions: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
    if not sheet:
        return []
    rows = []
    for definition in definitions:
        token = _normalize_token(str(definition.get("token") or ""))
        description = _clean_definition(str(definition.get("description") or ""))
        if not token or not description:
            continue
        rows.append(
            {
                "token": token,
                "description": description,
                "legend_item_id": item.id,
                "sheet_version_id": sheet.id,
                "sheet_id": sheet.sheet_id,
                "revision_set_id": sheet.revision_set_id,
                "discipline": _discipline_key(sheet.sheet_id),
            }
        )
    return rows


def _resolve_references(
    text: str,
    definition_rows: list[dict[str, Any]],
    *,
    sheet: SheetVersion,
    revision_set_id: str,
) -> list[dict[str, Any]]:
    clean = clean_display_text(text)
    references: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    tokens = sorted({row["token"] for row in definition_rows if _token_is_safe_for_reference(row["token"])}, key=len, reverse=True)
    for token in tokens:
        if token in seen_tokens or not _token_in_text(token, clean):
            continue
        same_sheet = [row for row in definition_rows if row["token"] == token and row["sheet_version_id"] == sheet.id]
        selected = _unique_definition(same_sheet)
        source = "same_sheet"
        if selected is None:
            fallback = [
                row
                for row in definition_rows
                if row["token"] == token
                and row["revision_set_id"] == revision_set_id
                and row["discipline"] == _discipline_key(sheet.sheet_id)
            ]
            selected = _unique_definition(fallback)
            source = "same_package_discipline"
        if selected is None:
            continue
        references.append(
            {
                "token": selected["token"],
                "description": selected["description"],
                "legend_item_id": selected["legend_item_id"],
                "source": source,
            }
        )
        seen_tokens.add(token)
        if len(references) >= 12:
            break
    return references


def _unique_definition(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        unique[(row["token"], normalize_text(row["description"]))] = row
    if len(unique) != 1:
        return None
    return next(iter(unique.values()))


def _token_in_text(token: str, text: str) -> bool:
    if not token or not text:
        return False
    escaped = re.escape(token.upper())
    return re.search(TOKEN_IN_TEXT_RE_TEMPLATE.format(token=escaped), text.upper()) is not None


def _token_is_safe_for_reference(token: str) -> bool:
    normalized = _normalize_token(token)
    if len(normalized) == 1 and normalized in {"A", "I", "O"}:
        return False
    return True


def _discipline_key(sheet_id: str) -> str:
    return "".join(ch for ch in str(sheet_id or "").upper() if ch.isalpha()) or "DRAWING"


def _with_legend_payload(item: ChangeItem, payload: dict[str, Any]) -> ChangeItem:
    return replace(item, provenance={**item.provenance, LEGEND_CONTEXT_KEY: payload})
