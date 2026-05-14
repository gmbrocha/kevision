from __future__ import annotations

import csv
import html
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import fitz

from .pre_review import PRE_REVIEW_2, PRE_REVIEW_KEY
from .review_queue import is_superseded
from .revision_state.models import ChangeItem, SheetVersion
from .utils import choose_best_sheet_id, clean_display_text, normalize_text, stable_id
from .workspace import WorkspaceStore


KEYNOTE_REGISTRY_SCHEMA = "scopeledger.keynote_registry.v1"
KEYNOTE_EXPANSION_SCHEMA = "scopeledger.keynote_expansion.v1"
KEYNOTE_REGISTRY_EXTRACTOR_VERSION = 1
HEADER_SEARCH_TERMS = (
    "KEYED NOTES",
    "KEYED NOTE",
    "KEYEDNOTES",
    "KEYEDNOTE",
    "KEY NOTES",
    "KEY NOTE",
    "KEYNOTES",
    "KEYNOTE",
)
TOKEN_RE = re.compile(r"^[A-Z](?:\.\d{1,3})?$|^[A-Z]{1,3}\d{1,3}$|^\d{1,3}$", re.IGNORECASE)
CSV_FIELDS = [
    "sheet_key",
    "sheet_id",
    "pdf",
    "page_number",
    "header_text",
    "token",
    "description",
    "marker_bbox",
    "label_bbox",
    "description_bbox",
    "shape_line_count",
    "shape_bbox",
    "source_pattern",
]
KEYNOTE_CUE_RE = re.compile(r"\b(key\s*notes?|keyed\s*notes?|keynotes?|hex(?:agon)?|tag|note)\b", re.IGNORECASE)


@dataclass(frozen=True)
class HeaderRegion:
    pdf_path: str
    page_number: int
    sheet_key: str
    sheet_id: str
    header_text: str
    header_bbox: list[float]
    search_bbox: list[float]
    orientation: str
    row_count: int = 0


@dataclass(frozen=True)
class MarkerShape:
    bbox: list[float]
    line_count: int


@dataclass(frozen=True)
class KeynoteRow:
    sheet_key: str
    sheet_id: str
    pdf_path: str
    page_number: int
    header_text: str
    token: str
    description: str
    marker_bbox: list[float]
    label_bbox: list[float]
    description_bbox: list[float]
    shape_line_count: int
    shape_bbox: list[float]
    source_pattern: str = "marker-label"


@dataclass(frozen=True)
class KeynoteRegistrySummary:
    scanned_sheet_count: int = 0
    sheet_count_with_keynotes: int = 0
    definition_count: int = 0
    cache_hit_count: int = 0

    def to_status(self) -> dict[str, int]:
        return {
            "keynote_registry_scanned_sheet_count": self.scanned_sheet_count,
            "keynote_registry_sheet_count": self.sheet_count_with_keynotes,
            "keynote_registry_definition_count": self.definition_count,
            "keynote_registry_cache_hits": self.cache_hit_count,
        }


@dataclass(frozen=True)
class KeynoteExpansionSummary:
    item_count: int = 0
    reference_count: int = 0

    def to_status(self) -> dict[str, int]:
        return {
            "keynote_expanded_item_count": self.item_count,
            "keynote_resolved_reference_count": self.reference_count,
        }


def scan_keynote_legends(input_dir: Path) -> tuple[list[HeaderRegion], list[KeynoteRow]]:
    pdf_paths = sorted(input_dir.rglob("*.pdf"))
    if not pdf_paths:
        raise FileNotFoundError(f"No PDFs found under input directory: {input_dir}")

    all_regions: list[HeaderRegion] = []
    all_rows: list[KeynoteRow] = []
    for pdf_path in pdf_paths:
        document = fitz.open(pdf_path)
        try:
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                page_number = page_index + 1
                sheet_id = extract_sheet_id(page, pdf_path)
                sheet_key = sheet_id or f"{pdf_path.stem} p{page_number:04d}"
                regions = find_header_regions(
                    page,
                    pdf_path=pdf_path,
                    page_number=page_number,
                    sheet_key=sheet_key,
                    sheet_id=sheet_id,
                )
                if not regions:
                    continue
                page_drawings = page.get_drawings()
                page_words = list(page.get_text("words") or [])
                for region in regions:
                    rows = extract_keynote_rows(page_words, page_drawings, region=region)
                    all_rows.extend(rows)
                    all_regions.append(HeaderRegion(**{**asdict(region), "row_count": len(rows)}))
        finally:
            document.close()
    return all_regions, dedupe_rows(all_rows)


def build_workspace_keynote_registry(store: WorkspaceStore) -> KeynoteRegistrySummary:
    document_cache: dict[str, fitz.Document] = {}
    previous_registry = store.data.keynote_registry if isinstance(store.data.keynote_registry, dict) else {}
    previous_sheets = previous_registry.get("sheets") if isinstance(previous_registry.get("sheets"), dict) else {}
    registry_sheets: dict[str, dict[str, Any]] = {}
    scanned_count = 0
    cache_hit_count = 0
    definition_count = 0
    try:
        for sheet in store.data.sheets:
            if not sheet.source_pdf or sheet.page_number < 1:
                continue
            source_pdf = str(store.resolve_path(sheet.source_pdf).resolve())
            source_fingerprint = _sheet_source_fingerprint(Path(source_pdf), sheet.page_number)
            previous_entry = previous_sheets.get(sheet.id)
            if _registry_entry_usable(previous_entry, sheet, source_pdf, source_fingerprint):
                entry = dict(previous_entry)
                registry_sheets[sheet.id] = entry
                scanned_count += 1
                cache_hit_count += 1
                definition_count += len(entry.get("definitions") or [])
                continue
            if source_pdf not in document_cache:
                document_cache[source_pdf] = fitz.open(source_pdf)
            document = document_cache[source_pdf]
            if sheet.page_number > document.page_count:
                continue
            scanned_count += 1
            page = document.load_page(sheet.page_number - 1)
            rows = extract_keynote_rows_for_sheet(page, sheet, source_pdf)
            definitions = [_row_to_registry_definition(row) for row in rows]
            registry_sheets[sheet.id] = {
                "schema": KEYNOTE_REGISTRY_SCHEMA,
                "extractor_version": KEYNOTE_REGISTRY_EXTRACTOR_VERSION,
                "sheet_version_id": sheet.id,
                "sheet_id": sheet.sheet_id,
                "revision_set_id": sheet.revision_set_id,
                "source_pdf": source_pdf,
                "source_fingerprint": source_fingerprint,
                "page_number": sheet.page_number,
                "has_keynotes": bool(definitions),
                "definitions": definitions,
            }
            definition_count += len(definitions)
    finally:
        for document in document_cache.values():
            document.close()

    store.data.keynote_registry = {
        "schema": KEYNOTE_REGISTRY_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sheets": registry_sheets,
    }
    store.save()
    return KeynoteRegistrySummary(
        scanned_sheet_count=scanned_count,
        sheet_count_with_keynotes=sum(1 for entry in registry_sheets.values() if entry.get("definitions")),
        definition_count=definition_count,
        cache_hit_count=cache_hit_count,
    )


def extract_keynote_rows_for_sheet(page: fitz.Page, sheet: SheetVersion, source_pdf: str | Path) -> list[KeynoteRow]:
    pdf_path = Path(source_pdf)
    regions = find_header_regions(
        page,
        pdf_path=pdf_path,
        page_number=sheet.page_number,
        sheet_key=sheet.sheet_id or sheet.id,
        sheet_id=sheet.sheet_id,
    )
    if not regions:
        return []
    rows: list[KeynoteRow] = []
    page_drawings = page.get_drawings()
    page_words = list(page.get_text("words") or [])
    for region in regions:
        rows.extend(extract_keynote_rows(page_words, page_drawings, region=region))
    return dedupe_rows(rows)


def apply_pre_review_keynote_expansions(store: WorkspaceStore) -> KeynoteExpansionSummary:
    registry = store.data.keynote_registry if isinstance(store.data.keynote_registry, dict) else {}
    registry_sheets = registry.get("sheets") if isinstance(registry.get("sheets"), dict) else {}
    if not registry_sheets:
        return KeynoteExpansionSummary()

    updated_items: list[ChangeItem] = []
    changed = False
    expanded_item_count = 0
    reference_count = 0
    definitions_by_sheet: dict[str, dict[str, dict[str, Any]]] = {}
    for item in store.data.change_items:
        updated = item
        if is_superseded(item) or item.provenance.get("source") != "visual-region":
            updated_items.append(updated)
            continue
        payload = item.provenance.get(PRE_REVIEW_KEY)
        if not isinstance(payload, dict):
            updated_items.append(updated)
            continue
        pre_review_2 = payload.get(PRE_REVIEW_2)
        if not isinstance(pre_review_2, dict) or not pre_review_2.get("available"):
            updated_items.append(updated)
            continue
        sheet_registry = registry_sheets.get(item.sheet_version_id)
        if item.sheet_version_id not in definitions_by_sheet:
            definitions_by_sheet[item.sheet_version_id] = _unique_definitions(sheet_registry)
        definitions = definitions_by_sheet[item.sheet_version_id]
        if not definitions:
            updated_items.append(updated)
            continue

        previous_expansion = pre_review_2.get("keynote_expansion") if isinstance(pre_review_2.get("keynote_expansion"), dict) else {}
        source_text = clean_display_text(str(previous_expansion.get("original_text") or pre_review_2.get("text") or ""))
        expanded_text, references = expand_keynote_text(source_text, definitions)
        next_pre_review_2 = dict(pre_review_2)
        if references:
            next_pre_review_2["text"] = expanded_text
            next_pre_review_2["keynote_expansion"] = {
                "schema": KEYNOTE_EXPANSION_SCHEMA,
                "original_text": source_text,
                "expanded_text": expanded_text,
                "references": references,
            }
            expanded_item_count += 1
            reference_count += len(references)
        else:
            next_pre_review_2["text"] = source_text
            next_pre_review_2.pop("keynote_expansion", None)
        next_payload = {**payload, PRE_REVIEW_2: next_pre_review_2}
        next_reviewer_text = item.reviewer_text
        if payload.get("selected") == PRE_REVIEW_2 and _reviewer_text_is_pre_review_owned(item.reviewer_text, pre_review_2, source_text):
            next_reviewer_text = next_pre_review_2.get("text", source_text)
        updated = replace(
            item,
            provenance={**item.provenance, PRE_REVIEW_KEY: next_payload},
            reviewer_text=next_reviewer_text,
        )
        if updated != item:
            changed = True
        updated_items.append(updated)

    if changed:
        store.data.change_items = updated_items
        store.save()
    return KeynoteExpansionSummary(item_count=expanded_item_count, reference_count=reference_count)


def _sheet_source_fingerprint(source_pdf: Path, page_number: int) -> str:
    if not source_pdf.exists():
        return ""
    stat = source_pdf.stat()
    return stable_id(
        "keynote-registry-sheet",
        source_pdf.resolve(),
        stat.st_size,
        stat.st_mtime_ns,
        page_number,
        KEYNOTE_REGISTRY_EXTRACTOR_VERSION,
    )


def _registry_entry_usable(entry: Any, sheet: SheetVersion, source_pdf: str, source_fingerprint: str) -> bool:
    if not isinstance(entry, dict):
        return False
    return (
        entry.get("schema") == KEYNOTE_REGISTRY_SCHEMA
        and entry.get("extractor_version") == KEYNOTE_REGISTRY_EXTRACTOR_VERSION
        and entry.get("sheet_version_id") == sheet.id
        and entry.get("sheet_id") == sheet.sheet_id
        and entry.get("revision_set_id") == sheet.revision_set_id
        and entry.get("source_pdf") == source_pdf
        and entry.get("source_fingerprint") == source_fingerprint
        and entry.get("page_number") == sheet.page_number
        and isinstance(entry.get("definitions"), list)
    )


def expand_keynote_text(text: str, definitions: dict[str, dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    clean = clean_display_text(text)
    if not clean:
        return "", []
    tokens = [token for token in sorted(definitions, key=len, reverse=True) if _token_should_expand(token, clean, definitions)]
    if not tokens:
        return clean, []
    by_upper = {token.upper(): definitions[token] for token in tokens}
    pattern = re.compile(r"(?<![A-Z0-9.])(" + "|".join(re.escape(token) for token in tokens) + r")(?![A-Z0-9.])", re.IGNORECASE)
    references: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()

    def replace_match(match: re.Match[str]) -> str:
        matched = normalize_token(match.group(1))
        definition = by_upper.get(matched.upper())
        if not definition:
            return match.group(0)
        if definition["token"] not in seen_tokens:
            seen_tokens.add(definition["token"])
            references.append(
                {
                    "token": definition["token"],
                    "description": definition["description"],
                    "source": "same_sheet_keynote_registry",
                    "source_pattern": definition.get("source_pattern", ""),
                }
            )
        return f"{definition['token']}: {definition['description']}"

    expanded = pattern.sub(replace_match, clean)
    return expanded, references


def keynote_expansion_payload(item: ChangeItem) -> dict[str, Any]:
    payload = item.provenance.get(PRE_REVIEW_KEY)
    if not isinstance(payload, dict):
        return {}
    pre_review_2 = payload.get(PRE_REVIEW_2)
    if not isinstance(pre_review_2, dict):
        return {}
    expansion = pre_review_2.get("keynote_expansion")
    return expansion if isinstance(expansion, dict) else {}


def _row_to_registry_definition(row: KeynoteRow) -> dict[str, Any]:
    return {
        "token": row.token,
        "description": row.description,
        "header_text": row.header_text,
        "source_pattern": row.source_pattern,
        "marker_bbox": row.marker_bbox,
        "label_bbox": row.label_bbox,
        "description_bbox": row.description_bbox,
        "shape_line_count": row.shape_line_count,
        "shape_bbox": row.shape_bbox,
    }


def _unique_definitions(sheet_registry: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(sheet_registry, dict):
        return {}
    rows = sheet_registry.get("definitions")
    if not isinstance(rows, list):
        return {}
    by_token: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        token = normalize_token(str(row.get("token") or ""))
        description = clean_display_text(str(row.get("description") or ""))
        if not token or not description:
            continue
        by_token.setdefault(token, []).append({**row, "token": token, "description": description})
    unique: dict[str, dict[str, Any]] = {}
    for token, token_rows in by_token.items():
        descriptions = {normalize_text(row["description"]) for row in token_rows}
        if len(descriptions) == 1:
            unique[token] = token_rows[0]
    return unique


def _token_should_expand(token: str, text: str, definitions: dict[str, dict[str, Any]]) -> bool:
    if not _token_in_text(token, text):
        return False
    if _specific_token(token):
        return True
    if KEYNOTE_CUE_RE.search(text):
        return True
    return _has_delimited_token_cluster(text, set(definitions))


def _token_in_text(token: str, text: str) -> bool:
    if not token or not text:
        return False
    return re.search(rf"(?<![A-Z0-9.]){re.escape(token)}(?![A-Z0-9.])", text, re.IGNORECASE) is not None


def _specific_token(token: str) -> bool:
    normalized = normalize_token(token)
    if "." in normalized:
        return True
    return len(normalized) > 1 and any(char.isalpha() for char in normalized) and any(char.isdigit() for char in normalized)


def _has_delimited_token_cluster(text: str, known_tokens: set[str]) -> bool:
    simple_known = {token for token in known_tokens if not _specific_token(token)}
    if len(simple_known) < 2:
        return False
    normalized = clean_display_text(text).upper()
    found: set[str] = set()
    for token in simple_known:
        if _token_in_text(token, normalized):
            found.add(token)
    if len(found) < 2:
        return False
    pattern = r"(?<![A-Z0-9.])(?:[A-Z]|\d{1,3})(?:\s*[,/&+]\s*(?:[A-Z]|\d{1,3})){1,}(?![A-Z0-9.])"
    return re.search(pattern, normalized) is not None


def _reviewer_text_is_pre_review_owned(reviewer_text: str, pre_review_2: dict[str, Any], source_text: str) -> bool:
    clean = normalize_text(reviewer_text)
    if not clean:
        return True
    candidates = {
        normalize_text(str(pre_review_2.get("text") or "")),
        normalize_text(source_text),
    }
    expansion = pre_review_2.get("keynote_expansion") if isinstance(pre_review_2.get("keynote_expansion"), dict) else {}
    candidates.add(normalize_text(str(expansion.get("expanded_text") or "")))
    candidates.add(normalize_text(str(expansion.get("original_text") or "")))
    return clean in {candidate for candidate in candidates if candidate}


def extract_sheet_id(page: fitz.Page, pdf_path: Path) -> str:
    text = page.get_text("text") or ""
    title_block_words = [
        str(word[4])
        for word in page.get_text("words")
        if float(word[0]) >= page.rect.width * 0.64 and float(word[1]) >= page.rect.height * 0.72
    ]
    title_block_text = " ".join(title_block_words)
    return choose_best_sheet_id(title_block_text) or choose_best_sheet_id(text) or ""


def find_header_regions(
    page: fitz.Page,
    *,
    pdf_path: Path,
    page_number: int,
    sheet_key: str,
    sheet_id: str,
) -> list[HeaderRegion]:
    raw_hits: list[tuple[str, fitz.Rect]] = []
    for term in HEADER_SEARCH_TERMS:
        for rect in page.search_for(term):
            raw_hits.append((term, rect))
    deduped = dedupe_header_hits(raw_hits)
    regions: list[HeaderRegion] = []
    words = list(page.get_text("words") or [])
    for term, rect in deduped:
        orientation = "horizontal" if rect.width >= rect.height else "vertical"
        right_boundary = neighboring_notes_boundary(words, rect, page.rect)
        header_text = header_line_text(words, rect, right_boundary=right_boundary) or term
        if not is_supported_header_text(header_text):
            continue
        if orientation != "horizontal":
            search = vertical_search_box(page.rect, rect)
            header_text = clean_vertical_header_text(header_text, fallback=term)
            regions.append(
                HeaderRegion(
                    pdf_path=str(pdf_path.resolve()),
                    page_number=page_number,
                    sheet_key=sheet_key,
                    sheet_id=sheet_id,
                    header_text=header_text,
                    header_bbox=rect_to_list(rect),
                    search_bbox=rect_to_list(search),
                    orientation=orientation,
                )
            )
            continue
        search = horizontal_search_box(page.rect, rect, right_boundary=right_boundary)
        regions.append(
            HeaderRegion(
                pdf_path=str(pdf_path.resolve()),
                page_number=page_number,
                sheet_key=sheet_key,
                sheet_id=sheet_id,
                header_text=header_text,
                header_bbox=rect_to_list(rect),
                search_bbox=rect_to_list(search),
                orientation=orientation,
            )
        )
    return regions


def is_supported_header_text(value: str) -> bool:
    text = " ".join(str(value or "").upper().split())
    if text.startswith("NOTE: NOT ALL"):
        return False
    symbol_legend_noise = ("NORTH ARROW", "GRAPHIC SCALE", "CENTER LINE")
    if any(term in text for term in symbol_legend_noise):
        return False
    strong_terms = ("KEY NOTES", "KEYNOTES", "KEYED NOTE", "KEYED NOTES", "KEYEDNOTE", "KEYEDNOTES")
    if any(term in text for term in strong_terms):
        return True
    if "KEYNOTE" in text and any(term in text for term in ("PLAN", "SHEET", "LEGEND", "NOTES", "DEMOLITION", "ATTIC", "ROOF", "FLOOR")):
        return True
    return False


def dedupe_header_hits(hits: list[tuple[str, fitz.Rect]]) -> list[tuple[str, fitz.Rect]]:
    ordered = sorted(hits, key=lambda item: (item[1].y0, item[1].x0, -len(item[0])))
    kept: list[tuple[str, fitz.Rect]] = []
    for term, rect in ordered:
        if any(rect_overlap_area(rect_to_list(rect), rect_to_list(existing_rect)) > rect.get_area() * 0.6 for _, existing_rect in kept):
            continue
        kept.append((term, rect))
    return kept


def neighboring_notes_boundary(words: list[tuple], header_rect: fitz.Rect, page_rect: fitz.Rect) -> float:
    line_rect = fitz.Rect(header_rect.x1 + 40, header_rect.y0 - 8, page_rect.x1, header_rect.y1 + 8)
    line_words = sorted([word for word in words if line_rect.intersects(fitz.Rect(word[:4]))], key=lambda word: word[0])
    for index, word in enumerate(line_words):
        text = str(word[4]).upper()
        next_text = str(line_words[index + 1][4]).upper() if index + 1 < len(line_words) else ""
        if text == "GENERAL" and next_text == "NOTES":
            boundary_word = word
            if index >= 2 and str(line_words[index - 1][4]).upper() == "PLAN":
                boundary_word = line_words[index - 2]
            return max(header_rect.x1 + 80, float(boundary_word[0]) - 18)
        if text in {"SHEET", "FLOOR", "PLAN"} and next_text == "NOTES":
            return max(header_rect.x1 + 80, float(word[0]) - 18)
        if text == "NOTES" and float(word[0]) - header_rect.x1 > 140:
            return max(header_rect.x1 + 80, float(word[0]) - 18)
    return page_rect.x1


def header_line_text(words: list[tuple], header_rect: fitz.Rect, *, right_boundary: float) -> str:
    expanded = fitz.Rect(max(0, header_rect.x0 - 180), header_rect.y0 - 8, min(right_boundary, header_rect.x1 + 240), header_rect.y1 + 8)
    line_words = [word for word in words if expanded.intersects(fitz.Rect(word[:4]))]
    if not line_words:
        return ""
    line_words.sort(key=lambda word: word[0])
    return " ".join(str(word[4]) for word in line_words)


def clean_vertical_header_text(value: str, *, fallback: str) -> str:
    text = " ".join(str(value or "").upper().split())
    match = re.search(r"\b(KEYED\s*NOTES?|KEY\s*NOTES?|KEYEDNOTES?|KEYNOTES?)\b:?", text)
    if not match:
        return fallback
    label = " ".join(match.group(1).replace("KEYEDNOTE", "KEYED NOTE").replace("KEYNOTE", "KEY NOTE").split())
    return f"{label}:"


def horizontal_search_box(page_rect: fitz.Rect, header_rect: fitz.Rect, *, right_boundary: float) -> fitz.Rect:
    return fitz.Rect(
        max(page_rect.x0, header_rect.x0 - 380),
        min(page_rect.y1, header_rect.y1 + 2),
        min(page_rect.x1, right_boundary, header_rect.x1 + 850),
        min(page_rect.y1, header_rect.y1 + 980),
    )


def vertical_search_box(page_rect: fitz.Rect, header_rect: fitz.Rect) -> fitz.Rect:
    return fitz.Rect(
        max(page_rect.x0, header_rect.x0 - 70),
        max(page_rect.y0, header_rect.y0 - 190),
        min(page_rect.x1, header_rect.x1 + 760),
        min(page_rect.y1, header_rect.y1 + 980),
    )


def extract_keynote_rows(words: list[tuple], drawings: list[dict[str, Any]], *, region: HeaderRegion) -> list[KeynoteRow]:
    if not region.search_bbox:
        return []
    search_rect = fitz.Rect(region.search_bbox)
    region_words = [word for word in words if search_rect.intersects(fitz.Rect(word[:4]))]
    if not region_words:
        return []
    header_rect = fitz.Rect(region.header_bbox)
    drawing_rect = fitz.Rect(
        min(header_rect.x0 - 28, search_rect.x0),
        min(header_rect.y0 - 30, search_rect.y0),
        max(header_rect.x1 + 120, search_rect.x1),
        search_rect.y1,
    )
    small_drawings = small_drawings_in_region(drawings, drawing_rect)
    if region.orientation == "vertical":
        return extract_numbered_list_rows(region_words, small_drawings, region=region)
    marker_rows = extract_marker_label_rows(region_words, small_drawings, region=region)
    if marker_rows:
        return marker_rows
    return extract_numbered_list_rows(region_words, small_drawings, region=region)


def extract_marker_label_rows(
    region_words: list[tuple],
    small_drawings: list[dict[str, Any]],
    *,
    region: HeaderRegion,
) -> list[KeynoteRow]:
    candidates = marker_label_candidates(region_words, small_drawings)
    if len(candidates) < 2:
        return []

    rows: list[KeynoteRow] = []
    for index, (token, label_bbox, shape) in enumerate(candidates):
        next_top = next_marker_boundary(candidates, index, region.search_bbox[3])
        description_words = words_for_description(region_words, marker_bbox=shape.bbox, label_bbox=label_bbox, next_marker_top=next_top)
        description = clean_description(" ".join(str(word[4]) for word in description_words))
        if not description:
            continue
        rows.append(
            KeynoteRow(
                sheet_key=region.sheet_key,
                sheet_id=region.sheet_id,
                pdf_path=region.pdf_path,
                page_number=region.page_number,
                header_text=region.header_text,
                token=token,
                description=description,
                marker_bbox=shape.bbox,
                label_bbox=label_bbox,
                description_bbox=union_words_bbox(description_words),
                shape_line_count=shape.line_count,
                shape_bbox=shape.bbox,
                source_pattern="marker-label",
            )
        )
    return rows


def marker_label_candidates(region_words: list[tuple], small_drawings: list[dict[str, Any]]) -> list[tuple[str, list[float], MarkerShape]]:
    candidates = []
    for word in region_words:
        token = normalize_token(str(word[4]))
        if not is_keynote_token(token):
            continue
        label_bbox = rect_to_list(fitz.Rect(word[:4]))
        shape = marker_shape_near_label(label_bbox, small_drawings)
        if not shape:
            continue
        candidates.append((token, label_bbox, shape))
    candidates = dedupe_marker_candidates(candidates)
    candidates = filter_to_dominant_marker_columns(candidates)
    candidates.sort(key=lambda item: (item[1][1], item[1][0], item[0]))
    return candidates


def extract_numbered_list_rows(
    region_words: list[tuple],
    small_drawings: list[dict[str, Any]],
    *,
    region: HeaderRegion,
) -> list[KeynoteRow]:
    if region.orientation == "vertical":
        return extract_vertical_numbered_list_rows(region_words, small_drawings, region=region)
    return extract_horizontal_numbered_list_rows(region_words, small_drawings, region=region)


def extract_horizontal_numbered_list_rows(
    region_words: list[tuple],
    small_drawings: list[dict[str, Any]],
    *,
    region: HeaderRegion,
) -> list[KeynoteRow]:
    candidates = numbered_list_candidates(region_words)
    candidates = filter_to_dominant_number_column(candidates)
    header_marker = marker_shape_near_header(region, small_drawings)
    if len(candidates) < 2 and not header_marker and not is_numbered_legend_header(region.header_text):
        return []
    candidates.sort(key=lambda item: (item[1][1], item[1][0], int(item[0])))
    rows: list[KeynoteRow] = []
    for index, (token, label_bbox) in enumerate(candidates):
        next_top = candidates[index + 1][1][1] if index + 1 < len(candidates) else region.search_bbox[3]
        description_words = horizontal_numbered_description_words(
            region_words,
            label_bbox=label_bbox,
            next_marker_top=next_top,
        )
        description = clean_description(" ".join(str(word[4]) for word in description_words))
        if not description:
            continue
        rows.append(make_numbered_row(region, token, label_bbox, description_words, header_marker))
    return rows


def extract_vertical_numbered_list_rows(
    region_words: list[tuple],
    small_drawings: list[dict[str, Any]],
    *,
    region: HeaderRegion,
) -> list[KeynoteRow]:
    candidates = numbered_list_candidates(region_words)
    candidates = filter_vertical_numbered_candidates(candidates, region)
    header_marker = marker_shape_near_header(region, small_drawings)
    if len(candidates) < 2 and not header_marker and not is_numbered_legend_header(region.header_text):
        return []
    candidates.sort(key=lambda item: (item[1][0], item[1][1], int(item[0])))
    rows: list[KeynoteRow] = []
    for index, (token, label_bbox) in enumerate(candidates):
        next_x = candidates[index + 1][1][0] if index + 1 < len(candidates) else region.search_bbox[2]
        description_words = vertical_numbered_description_words(
            region_words,
            label_bbox=label_bbox,
            next_marker_x=next_x,
        )
        description = clean_description(" ".join(str(word[4]) for word in description_words))
        if not description:
            continue
        rows.append(make_numbered_row(region, token, label_bbox, description_words, header_marker))
    return rows


def numbered_list_candidates(region_words: list[tuple]) -> list[tuple[str, list[float]]]:
    candidates: list[tuple[str, list[float]]] = []
    for word in region_words:
        raw = str(word[4] or "").strip()
        if not re.fullmatch(r"\d{1,3}\.", raw):
            continue
        token = normalize_token(raw)
        candidates.append((token, rect_to_list(fitz.Rect(word[:4]))))
    return dedupe_numbered_candidates(candidates)


def is_numbered_legend_header(value: str) -> bool:
    text = " ".join(str(value or "").upper().split())
    return any(term in text for term in ("KEY NOTES", "KEYNOTES", "KEYED NOTES", "KEYEDNOTES"))


def make_numbered_row(
    region: HeaderRegion,
    token: str,
    label_bbox: list[float],
    description_words: list[tuple],
    header_marker: MarkerShape | None,
) -> KeynoteRow:
    marker_bbox = header_marker.bbox if header_marker else []
    line_count = header_marker.line_count if header_marker else 0
    return KeynoteRow(
        sheet_key=region.sheet_key,
        sheet_id=region.sheet_id,
        pdf_path=region.pdf_path,
        page_number=region.page_number,
        header_text=region.header_text,
        token=token,
        description=clean_description(" ".join(str(word[4]) for word in description_words)),
        marker_bbox=marker_bbox,
        label_bbox=label_bbox,
        description_bbox=union_words_bbox(description_words),
        shape_line_count=line_count,
        shape_bbox=marker_bbox,
        source_pattern="numbered-list",
    )


def small_drawings_in_region(drawings: list[dict[str, Any]], region: fitz.Rect) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None or not region.intersects(rect):
            continue
        width = float(rect.width)
        height = float(rect.height)
        if width <= 0 or height <= 0:
            continue
        if width > 80 or height > 80:
            continue
        selected.append(drawing)
    return selected


def marker_shape_near_label(label_bbox: list[float], drawings: list[dict[str, Any]]) -> MarkerShape | None:
    label_rect = fitz.Rect(label_bbox)
    expanded = fitz.Rect(label_rect.x0 - 10, label_rect.y0 - 10, label_rect.x1 + 10, label_rect.y1 + 10)
    nearby_rects = []
    line_count = 0
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None or not expanded.intersects(rect):
            continue
        nearby_rects.append(rect_to_list(rect))
        for item in drawing.get("items") or []:
            if item and item[0] == "l":
                line_count += 1
    if line_count < 4 or not nearby_rects:
        return None
    bbox = union_bboxes(nearby_rects)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if width < 8 or height < 8 or width > 42 or height > 42:
        return None
    aspect = width / height if height else 0
    if aspect < 0.45 or aspect > 2.2:
        return None
    if not fitz.Rect(bbox).contains(label_rect):
        return None
    return MarkerShape(bbox=bbox, line_count=line_count)


def marker_shape_near_header(region: HeaderRegion, drawings: list[dict[str, Any]]) -> MarkerShape | None:
    header_rect = fitz.Rect(region.header_bbox)
    if region.orientation == "horizontal":
        search = fitz.Rect(header_rect.x0 - 20, header_rect.y0 - 24, header_rect.x1 + 90, header_rect.y1 + 34)
    else:
        search = fitz.Rect(header_rect.x0 - 28, header_rect.y0 - 28, header_rect.x1 + 44, header_rect.y1 + 60)
    nearby_rects = []
    line_count = 0
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None or not search.intersects(rect):
            continue
        width = float(rect.width)
        height = float(rect.height)
        if width > 54 or height > 54:
            continue
        nearby_rects.append(rect_to_list(rect))
        for item in drawing.get("items") or []:
            if item and item[0] == "l":
                line_count += 1
    if line_count < 4 or not nearby_rects:
        return None
    bbox = union_bboxes(nearby_rects)
    return MarkerShape(bbox=bbox, line_count=line_count)


def words_for_description(
    words: list[tuple],
    *,
    marker_bbox: list[float],
    label_bbox: list[float],
    next_marker_top: float,
) -> list[tuple]:
    x_min = max(marker_bbox[2], label_bbox[2]) + 8
    y_min = min(marker_bbox[1], label_bbox[1]) - 4
    y_max = max(y_min + 16, next_marker_top - 3)
    same_entry = [
        word
        for word in words
        if float(word[0]) >= x_min
        and float(word[1]) >= y_min
        and float(word[1]) <= y_max
        and is_description_word(str(word[4]))
    ]
    same_entry.sort(key=lambda word: (round(float(word[1]) / 4) * 4, float(word[0])))
    return same_entry


def horizontal_numbered_description_words(
    words: list[tuple],
    *,
    label_bbox: list[float],
    next_marker_top: float,
) -> list[tuple]:
    x_min = label_bbox[2] + 10
    y_min = label_bbox[1] - 4
    y_max = max(y_min + 18, next_marker_top - 3)
    selected = [
        word
        for word in words
        if float(word[0]) >= x_min
        and float(word[1]) >= y_min
        and float(word[1]) <= y_max
        and is_description_word(str(word[4]))
    ]
    selected.sort(key=lambda word: (round(float(word[1]) / 4) * 4, float(word[0])))
    return selected


def vertical_numbered_description_words(
    words: list[tuple],
    *,
    label_bbox: list[float],
    next_marker_x: float,
) -> list[tuple]:
    x_min = label_bbox[0] - 5
    x_max = max(label_bbox[2] + 12, next_marker_x - 4)
    y_max = label_bbox[3] + 2
    selected = [
        word
        for word in words
        if float(word[0]) >= x_min
        and float(word[0]) <= x_max
        and float(word[3]) <= y_max
        and not re.fullmatch(r"\d{1,3}\.", str(word[4] or "").strip())
        and is_description_word(str(word[4]))
    ]
    selected.sort(key=lambda word: (float(word[0]), -float(word[1])))
    return selected


def next_marker_boundary(candidates: list[tuple[str, list[float], MarkerShape]], index: int, fallback: float) -> float:
    current_x = candidates[index][2].bbox[0]
    for next_index in range(index + 1, len(candidates)):
        if abs(candidates[next_index][2].bbox[0] - current_x) <= 38:
            return candidates[next_index][1][1]
    return fallback


def dedupe_marker_candidates(candidates: list[tuple[str, list[float], MarkerShape]]) -> list[tuple[str, list[float], MarkerShape]]:
    kept: list[tuple[str, list[float], MarkerShape]] = []
    seen: set[tuple[str, int, int]] = set()
    for token, label_bbox, shape in sorted(candidates, key=lambda item: (item[2].bbox[1], item[2].bbox[0])):
        key = (token, int(round(shape.bbox[0])), int(round(shape.bbox[1])))
        if key in seen:
            continue
        seen.add(key)
        kept.append((token, label_bbox, shape))
    return kept


def dedupe_numbered_candidates(candidates: list[tuple[str, list[float]]]) -> list[tuple[str, list[float]]]:
    kept: list[tuple[str, list[float]]] = []
    seen: set[tuple[str, int, int]] = set()
    for token, bbox in sorted(candidates, key=lambda item: (item[1][1], item[1][0])):
        key = (token, int(round(bbox[0])), int(round(bbox[1])))
        if key in seen:
            continue
        seen.add(key)
        kept.append((token, bbox))
    return kept


def filter_to_dominant_number_column(candidates: list[tuple[str, list[float]]]) -> list[tuple[str, list[float]]]:
    if len(candidates) < 4:
        return candidates
    clusters: list[list[tuple[str, list[float]]]] = []
    for candidate in sorted(candidates, key=lambda item: item[1][0]):
        x = candidate[1][0]
        for cluster in clusters:
            cluster_x = sum(item[1][0] for item in cluster) / len(cluster)
            if abs(x - cluster_x) <= 28:
                cluster.append(candidate)
                break
        else:
            clusters.append([candidate])
    largest = max(clusters, key=len)
    return largest if len(largest) >= 2 else candidates


def filter_to_dominant_number_row(candidates: list[tuple[str, list[float]]]) -> list[tuple[str, list[float]]]:
    if len(candidates) < 4:
        return candidates
    clusters: list[list[tuple[str, list[float]]]] = []
    for candidate in sorted(candidates, key=lambda item: item[1][1]):
        y = candidate[1][1]
        for cluster in clusters:
            cluster_y = sum(item[1][1] for item in cluster) / len(cluster)
            if abs(y - cluster_y) <= 18:
                cluster.append(candidate)
                break
        else:
            clusters.append([candidate])
    largest = max(clusters, key=len)
    return largest if len(largest) >= 2 else candidates


def filter_vertical_numbered_candidates(
    candidates: list[tuple[str, list[float]]],
    region: HeaderRegion,
) -> list[tuple[str, list[float]]]:
    if not candidates:
        return []
    header_rect = fitz.Rect(region.header_bbox)
    near_header_row = [
        candidate
        for candidate in candidates
        if abs(((candidate[1][1] + candidate[1][3]) / 2) - header_rect.y1) <= 70
    ]
    row_candidates = near_header_row or filter_to_dominant_number_row(candidates)
    right_of_header = [candidate for candidate in row_candidates if candidate[1][0] >= header_rect.x1 - 8]
    if not right_of_header:
        return row_candidates
    ordered = sorted(right_of_header, key=lambda item: item[1][0])
    clusters: list[list[tuple[str, list[float]]]] = []
    for candidate in ordered:
        if clusters and candidate[1][0] - clusters[-1][-1][1][0] <= 46:
            clusters[-1].append(candidate)
        else:
            clusters.append([candidate])
    return clusters[0] if clusters else ordered


def filter_to_dominant_marker_columns(
    candidates: list[tuple[str, list[float], MarkerShape]]
) -> list[tuple[str, list[float], MarkerShape]]:
    if len(candidates) < 4:
        return candidates
    clusters: list[list[tuple[str, list[float], MarkerShape]]] = []
    for candidate in sorted(candidates, key=lambda item: item[2].bbox[0]):
        marker_x = candidate[2].bbox[0]
        for cluster in clusters:
            cluster_x = sum(item[2].bbox[0] for item in cluster) / len(cluster)
            if abs(marker_x - cluster_x) <= 28:
                cluster.append(candidate)
                break
        else:
            clusters.append([candidate])
    largest = max(len(cluster) for cluster in clusters)
    minimum_keep = max(2, int(largest * 0.35))
    kept = [candidate for cluster in clusters if len(cluster) >= minimum_keep for candidate in cluster]
    return kept or candidates


def dedupe_rows(rows: list[KeynoteRow]) -> list[KeynoteRow]:
    seen: set[tuple[str, int, str, int, int]] = set()
    deduped: list[KeynoteRow] = []
    for row in rows:
        anchor_bbox = row.marker_bbox or row.label_bbox
        key = (
            row.pdf_path,
            row.page_number,
            row.token,
            int(round(anchor_bbox[0])),
            int(round(anchor_bbox[1])),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def normalize_token(value: str) -> str:
    token = " ".join(str(value or "").upper().strip().split())
    token = re.sub(r"\s+", "", token)
    token = token.strip(".,;:()[]{}")
    return token


def is_keynote_token(token: str) -> bool:
    if not token:
        return False
    if token in {"I", "O"}:
        return False
    return bool(TOKEN_RE.match(token))


def is_description_word(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if re.fullmatch(r"[-.,;:()]+", text):
        return False
    return True


def clean_description(value: str) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    text = re.split(r"\bNOTE:\s+NOT\s+ALL\s+THE\s+KEYNOTES\b", text, flags=re.IGNORECASE)[0]
    text = re.split(r"\bGENERAL\s+SHEET\b", text, flags=re.IGNORECASE)[0]
    text = re.split(r"\bSHEET\s+NOTES:?\b", text, flags=re.IGNORECASE)[0]
    text = re.split(r"\bCONFORMED\s+SET\b", text, flags=re.IGNORECASE)[0]
    text = re.split(r"\bCONFORMED\s+FOR\b", text, flags=re.IGNORECASE)[0]
    text = re.split(r"\bPROJECT\s+TITLE\b", text, flags=re.IGNORECASE)[0]
    text = re.split(r"\bPROJECT\s+RENOVATE\b", text, flags=re.IGNORECASE)[0]
    text = re.split(r"\bLOCATION\s+ISSUE\b", text, flags=re.IGNORECASE)[0]
    text = text.strip(" -:.;")
    if len(text) < 6:
        return ""
    return text


def union_words_bbox(words: list[tuple]) -> list[float]:
    if not words:
        return []
    return [
        min(float(word[0]) for word in words),
        min(float(word[1]) for word in words),
        max(float(word[2]) for word in words),
        max(float(word[3]) for word in words),
    ]


def union_bboxes(boxes: Iterable[list[float]]) -> list[float]:
    values = list(boxes)
    return [
        min(box[0] for box in values),
        min(box[1] for box in values),
        max(box[2] for box in values),
        max(box[3] for box in values),
    ]


def rect_to_list(rect: fitz.Rect) -> list[float]:
    return [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]


def rect_overlap_area(left: list[float], right: list[float]) -> float:
    x_overlap = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    y_overlap = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    return x_overlap * y_overlap


def write_outputs(*, output_dir: Path, input_dir: Path, regions: list[HeaderRegion], rows: list[KeynoteRow]) -> dict[str, Path]:
    rows_jsonl = output_dir / "keynote_legend_rows.jsonl"
    rows_csv = output_dir / "keynote_legend_rows.csv"
    regions_jsonl = output_dir / "keynote_legend_regions.jsonl"
    by_sheet_json = output_dir / "keynotes_by_sheet.json"
    summary_json = output_dir / "summary.json"
    viewer_html = output_dir / "keynote_legend_viewer.html"

    write_jsonl(rows_jsonl, [asdict(row) for row in rows])
    write_jsonl(regions_jsonl, [asdict(region) for region in regions])
    write_rows_csv(rows_csv, rows)
    by_sheet_json.write_text(json.dumps(keynotes_by_sheet(rows), indent=2, ensure_ascii=True), encoding="utf-8")
    summary = {
        "schema": "scopeledger.keynote_legend_finder.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(input_dir),
        "header_region_count": len(regions),
        "horizontal_header_region_count": sum(1 for region in regions if region.orientation == "horizontal"),
        "vertical_header_region_count": sum(1 for region in regions if region.orientation == "vertical"),
        "keynote_row_count": len(rows),
        "sheet_count_with_keynotes": len({row.sheet_key for row in rows}),
        "outputs": {
            "summary": str(summary_json),
            "keynote_legend_rows_jsonl": str(rows_jsonl),
            "keynote_legend_rows_csv": str(rows_csv),
            "keynote_legend_regions_jsonl": str(regions_jsonl),
            "keynotes_by_sheet_json": str(by_sheet_json),
            "keynote_legend_viewer_html": str(viewer_html),
        },
    }
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    viewer_html.write_text(build_viewer_html(summary, rows), encoding="utf-8")
    return {
        "summary": summary_json,
        "rows_csv": rows_csv,
        "rows_jsonl": rows_jsonl,
        "regions_jsonl": regions_jsonl,
        "keynotes_by_sheet": by_sheet_json,
        "viewer": viewer_html,
    }


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def write_rows_csv(path: Path, rows: list[KeynoteRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "sheet_key": row.sheet_key,
                    "sheet_id": row.sheet_id,
                    "pdf": row.pdf_path,
                    "page_number": row.page_number,
                    "header_text": row.header_text,
                    "token": row.token,
                    "description": row.description,
                    "marker_bbox": json.dumps(row.marker_bbox),
                    "label_bbox": json.dumps(row.label_bbox),
                    "description_bbox": json.dumps(row.description_bbox),
                    "shape_line_count": row.shape_line_count,
                    "shape_bbox": json.dumps(row.shape_bbox),
                    "source_pattern": row.source_pattern,
                }
            )


def keynotes_by_sheet(rows: list[KeynoteRow]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = grouped.setdefault(
            row.sheet_key,
            {
                "sheet_id": row.sheet_id,
                "pdf": row.pdf_path,
                "page_number": row.page_number,
                "keynotes": {},
            },
        )
        entry["keynotes"][row.token] = row.description
    return grouped


def build_viewer_html(summary: dict[str, Any], rows: list[KeynoteRow]) -> str:
    row_html = "\n".join(
        "<tr>"
        f"<td>{html.escape(row.sheet_key)}</td>"
        f"<td>{row.page_number}</td>"
        f"<td>{html.escape(row.header_text)}</td>"
        f"<td><strong>{html.escape(row.token)}</strong></td>"
        f"<td>{html.escape(row.description)}</td>"
        f"<td>{html.escape(row.source_pattern)}</td>"
        f"<td>{row.shape_line_count}</td>"
        "</tr>"
        for row in rows
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Keynote Legend Finder</title>
  <style>
    body {{ font-family: Arial, Helvetica, sans-serif; margin: 24px; color: #111827; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d1d5db; padding: 7px 9px; vertical-align: top; font-size: 13px; }}
    th {{ background: #f3f4f6; text-align: left; position: sticky; top: 0; }}
    .stats {{ display: flex; gap: 18px; margin-bottom: 18px; flex-wrap: wrap; }}
    .stats div {{ background: #f9fafb; border: 1px solid #d1d5db; padding: 8px 10px; border-radius: 6px; }}
  </style>
</head>
<body>
  <h1>Keynote Legend Finder</h1>
  <div class="stats">
    <div>Header regions: {summary["header_region_count"]}</div>
    <div>Keynote rows: {summary["keynote_row_count"]}</div>
    <div>Sheets with keynotes: {summary["sheet_count_with_keynotes"]}</div>
    <div>Vertical headers: {summary["vertical_header_region_count"]}</div>
  </div>
  <table>
    <thead>
      <tr><th>Sheet</th><th>Page</th><th>Header</th><th>Token</th><th>Description</th><th>Source</th><th>Shape lines</th></tr>
    </thead>
    <tbody>
      {row_html}
    </tbody>
  </table>
</body>
</html>
"""
