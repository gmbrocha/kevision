from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import fitz

from .revision_state.models import CloudCandidate, SheetVersion
from .utils import clean_display_text, normalize_text, parse_detail_ref
from .workspace import WorkspaceStore


SCOPE_TERMS = (
    "add",
    "adjust",
    "connect",
    "demo",
    "demolish",
    "extend",
    "furnish",
    "infill",
    "install",
    "modify",
    "patch",
    "provide",
    "relocate",
    "remove",
    "repair",
    "replace",
    "reroute",
)

INDEX_NOISE_TERMS = (
    "sheet index",
    "sheet no",
    "sheet name",
    "page no",
    "conformed set",
    "revision #",
)


@dataclass(frozen=True)
class ScopeExtractionResult:
    text: str
    reason: str
    signal: float
    method: str
    detail_ref: str | None = None
    word_count: int = 0
    context_bbox: list[int] | None = None

    def provenance(self) -> dict[str, Any]:
        return {
            "scope_text_reason": self.reason,
            "scope_text_method": self.method,
            "scope_text_signal": round(self.signal, 3),
            "scope_text_word_count": self.word_count,
            "scope_context_bbox": self.context_bbox or [],
        }


def extract_cloud_scope_text(page: fitz.Page, sheet: SheetVersion, bbox: list[int]) -> ScopeExtractionResult:
    context_rect, context_bbox = _expanded_context(page, sheet, bbox)
    words = _words_in_rect(page, context_rect)
    text = _line_text(words)
    method = "pdf-text-layer"
    word_count = len(words)
    if not text:
        text = _ocr_rect(page, context_rect)
        method = "tesseract-ocr" if text else method
        word_count = len(text.split())
    detail_ref = parse_detail_ref(text, sheet.sheet_id)
    if not text:
        return ScopeExtractionResult(
            text="Cloud Only - No readable scope text found near cloud. Review crop/source context.",
            reason="no-readable-text",
            signal=0.24,
            method=method,
            detail_ref=None,
            word_count=0,
            context_bbox=context_bbox,
        )

    reason, signal = _classify_text(text, detail_ref=detail_ref)
    if method == "tesseract-ocr" and reason == "text-layer-near-cloud":
        reason = "ocr-near-cloud"
        signal = min(signal, 0.7)
    display_text = _display_text(text, reason=reason, detail_ref=detail_ref)
    return ScopeExtractionResult(
        text=display_text,
        reason=reason,
        signal=signal,
        method=method,
        detail_ref=detail_ref,
        word_count=word_count,
        context_bbox=context_bbox,
    )


def _expanded_context(page: fitz.Page, sheet: SheetVersion, bbox: list[int]) -> tuple[fitz.Rect, list[int]]:
    x, y, width, height = [float(value) for value in bbox]
    sheet_width = float(sheet.width or page.rect.width)
    sheet_height = float(sheet.height or page.rect.height)
    pad = max(90.0, min(max(width, height) * 0.45, 360.0))
    left = max(0.0, x - pad)
    top = max(0.0, y - pad)
    right = min(sheet_width, x + width + pad)
    bottom = min(sheet_height, y + height + pad)
    scale_x = page.rect.width / sheet_width if sheet_width else 1.0
    scale_y = page.rect.height / sheet_height if sheet_height else 1.0
    return (
        fitz.Rect(left * scale_x, top * scale_y, right * scale_x, bottom * scale_y),
        [int(round(left)), int(round(top)), int(round(right - left)), int(round(bottom - top))],
    )


def _words_in_rect(page: fitz.Page, rect: fitz.Rect) -> list[tuple]:
    hits = []
    for word in page.get_text("words"):
        word_rect = fitz.Rect(word[:4])
        if rect.intersects(word_rect):
            hits.append(word)
    return sorted(hits, key=lambda item: (int(item[5]), int(item[6]), item[1], item[0]))


def _line_text(words: list[tuple]) -> str:
    lines: list[str] = []
    current_key: tuple[int, int] | None = None
    current_words: list[str] = []
    for word in words:
        key = (int(word[5]), int(word[6]))
        if current_key is not None and key != current_key:
            lines.append(" ".join(current_words))
            current_words = []
        current_key = key
        current_words.append(str(word[4]))
    if current_words:
        lines.append(" ".join(current_words))
    return clean_display_text(" ".join(lines))


def _ocr_rect(page: fitz.Page, rect: fitz.Rect) -> str:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return ""
    with tempfile.TemporaryDirectory(prefix="scopeledger_ocr_") as tmp:
        image_path = Path(tmp) / "crop.png"
        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=rect, alpha=False)
        pix.save(image_path)
        try:
            result = subprocess.run(
                [tesseract, str(image_path), "stdout", "--psm", "6"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
    if result.returncode != 0:
        return ""
    return clean_display_text(result.stdout)


def _classify_text(text: str, *, detail_ref: str | None) -> tuple[str, float]:
    normalized = text.lower()
    sheet_id_hits = len(re.findall(r"\b(?:GI|AD|AE|IN|PL|EL|EP|MP|MH|ME|E|M|S|SF|CS)\d{3}(?:\.\d+)?\b", text))
    if any(term in normalized for term in INDEX_NOISE_TERMS) or sheet_id_hits >= 5:
        return "index-or-title-noise", 0.22
    if detail_ref and len(text.split()) <= 12 and not any(term in normalized for term in SCOPE_TERMS):
        return "leader-or-callout-only", 0.42
    if len(text) > 520 or len(text.split()) > 85:
        return "needs-reviewer-rewrite", 0.38
    if any(term in normalized for term in SCOPE_TERMS):
        return "text-layer-near-cloud", 0.78
    return "needs-reviewer-rewrite", 0.48


def _display_text(text: str, *, reason: str, detail_ref: str | None) -> str:
    excerpt = text if len(text) <= 520 else f"{text[:517].rstrip()}..."
    if reason == "leader-or-callout-only":
        return f"Cloud Only - Detail reference {detail_ref}; review referenced detail for scope."
    if reason == "index-or-title-noise":
        return f"Cloud Only - Nearby text appears to be index/title-block noise: {excerpt}"
    if reason == "needs-reviewer-rewrite":
        return f"Cloud Only - Nearby text needs reviewer rewrite: {excerpt}"
    return f"Cloud Only - {excerpt}"


def enrich_workspace_scope_text(store: WorkspaceStore, *, force: bool = False) -> int:
    sheets_by_id = {sheet.id: sheet for sheet in store.data.sheets}
    updated_clouds: list[CloudCandidate] = []
    clouds_by_id: dict[str, CloudCandidate] = {}
    document_cache: dict[str, fitz.Document] = {}
    changed = 0
    try:
        for cloud in store.data.clouds:
            sheet = sheets_by_id.get(cloud.sheet_version_id)
            if not sheet or (cloud.scope_reason and not force):
                updated_clouds.append(cloud)
                clouds_by_id[cloud.id] = cloud
                continue
            source_pdf = str(store.resolve_path(sheet.source_pdf))
            if source_pdf not in document_cache:
                document_cache[source_pdf] = fitz.open(source_pdf)
            page = document_cache[source_pdf][sheet.page_number - 1]
            result = extract_cloud_scope_text(page, sheet, cloud.bbox)
            updated = replace(
                cloud,
                nearby_text=result.text or cloud.nearby_text,
                detail_ref=cloud.detail_ref or result.detail_ref,
                scope_text=result.text,
                scope_reason=result.reason,
                scope_signal=round(result.signal, 3),
                scope_method=result.method,
            )
            updated_clouds.append(updated)
            clouds_by_id[updated.id] = updated
            changed += 1
    finally:
        for document in document_cache.values():
            document.close()

    if not changed:
        return 0

    updated_items = []
    for item in store.data.change_items:
        cloud = clouds_by_id.get(item.cloud_candidate_id or "")
        if not cloud or item.provenance.get("source") != "visual-region":
            updated_items.append(item)
            continue
        raw_text = cloud.scope_text or item.raw_text
        previous_raw = item.raw_text
        reviewer_text = item.reviewer_text
        if reviewer_text and normalize_text(reviewer_text) == normalize_text(previous_raw):
            reviewer_text = raw_text
        updated_items.append(
            replace(
                item,
                detail_ref=item.detail_ref or cloud.detail_ref,
                raw_text=raw_text,
                normalized_text=normalize_text(raw_text),
                reviewer_text=reviewer_text,
                provenance={
                    **item.provenance,
                    "scope_text_reason": cloud.scope_reason,
                    "scope_text_method": cloud.scope_method,
                    "scope_text_signal": cloud.scope_signal,
                    "extraction_signal": cloud.scope_signal or item.provenance.get("extraction_signal"),
                    "cloud_confidence": cloud.confidence,
                    **cloud.metadata,
                },
            )
        )

    store.data.clouds = updated_clouds
    store.data.change_items = updated_items
    store.save()
    return changed
