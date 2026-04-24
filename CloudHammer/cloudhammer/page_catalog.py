from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

import fitz

from .config import CloudHammerConfig
from .manifests import write_jsonl
from .rasterize import rendered_pixel_size, save_page_png


SHEET_PREFIXES = (
    "GI",
    "AE",
    "AD",
    "AF",
    "AG",
    "AR",
    "AS",
    "AV",
    "AX",
    "CE",
    "CG",
    "CS",
    "ED",
    "EL",
    "EP",
    "ES",
    "ET",
    "FA",
    "FP",
    "FS",
    "ID",
    "LD",
    "LS",
    "MD",
    "ME",
    "MH",
    "MP",
    "MS",
    "PD",
    "PH",
    "PL",
    "PM",
    "SF",
    "TA",
    "TC",
    "TY",
    "A",
    "C",
    "E",
    "G",
    "I",
    "M",
    "P",
    "S",
    "T",
)
SHEET_ID_RE = re.compile(
    rf"\b(?:{'|'.join(SHEET_PREFIXES)})[- ]?\d{{2,4}}(?:\.\d+)?(?:[A-Z])?\b",
    re.IGNORECASE,
)


def slugify(value: str, max_length: int = 120) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return value[:max_length] or "item"


def stable_page_key(pdf_path: Path, page_index: int, base: Path | None = None) -> str:
    try:
        rel = pdf_path.resolve().relative_to(base.resolve()) if base is not None else pdf_path.resolve()
    except ValueError:
        rel = pdf_path.resolve()
    digest = hashlib.sha1(str(rel).encode("utf-8")).hexdigest()[:8]
    return f"{slugify(pdf_path.stem)}_{digest}_p{page_index:04d}"


def classify_pdf_from_path(pdf_path: Path) -> str | None:
    lower = str(pdf_path).lower()
    if "narrative" in lower:
        return "narrative"
    if "specification" in lower or "specifications" in lower or re.search(r"\bspecs?\b", lower):
        return "spec"
    return None


def extract_sheet_id(text: str) -> str | None:
    matches = [m.group(0).replace(" ", "").upper() for m in SHEET_ID_RE.finditer(text)]
    if not matches:
        return None
    counts: dict[str, int] = {}
    for match in matches:
        counts[match] = counts.get(match, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], len(item[0]), item[0]))[0][0]


def extract_sheet_title(text: str, sheet_id: str | None) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    if sheet_id:
        normalized_id = sheet_id.replace("-", "").upper()
        for idx, line in enumerate(lines):
            normalized_line = line.replace("-", "").replace(" ", "").upper()
            if normalized_id in normalized_line:
                for candidate in lines[idx + 1 : idx + 5]:
                    if 3 <= len(candidate) <= 90 and not SHEET_ID_RE.search(candidate):
                        return candidate
    title_words = ("plan", "details", "elevation", "section", "schedule", "demolition")
    for line in reversed(lines[-40:]):
        lower = line.lower()
        if any(word in lower for word in title_words) and 3 <= len(line) <= 90:
            return line
    return None


def classify_page_kind(pdf_path: Path, text: str, sheet_id: str | None) -> str:
    path_kind = classify_pdf_from_path(pdf_path)
    if path_kind is not None:
        return path_kind

    lower = text.lower()
    if sheet_id is not None:
        return "drawing"
    if "specification" in lower[:3000] or "section 0" in lower[:3000]:
        return "spec"
    if "narrative" in lower[:3000] and sheet_id is None:
        return "narrative"
    if text.strip():
        return "drawing"
    return "unknown"


def find_pdfs(revision_sets_dir: Path) -> list[Path]:
    return sorted(p for p in revision_sets_dir.rglob("*.pdf") if p.is_file())


def iter_page_rows(
    revision_sets_dir: Path,
    cfg: CloudHammerConfig,
    render: bool = True,
    overwrite: bool = False,
    limit: int | None = None,
    only_pdf: str | None = None,
    only_page_index: int | None = None,
) -> Iterable[dict]:
    rendered_count = 0
    pdfs = find_pdfs(revision_sets_dir)
    if only_pdf:
        needle = only_pdf.lower()
        pdfs = [path for path in pdfs if needle in str(path).lower()]

    for pdf_path in pdfs:
        doc = fitz.open(pdf_path)
        try:
            for page_index in range(doc.page_count):
                if only_page_index is not None and page_index != only_page_index:
                    continue
                if limit is not None and rendered_count >= limit:
                    return
                page = doc[page_index]
                text = page.get_text("text") or ""
                sheet_id = extract_sheet_id(text)
                page_kind = classify_page_kind(pdf_path, text, sheet_id)
                width_px, height_px = rendered_pixel_size(page, cfg.dpi)
                key = stable_page_key(pdf_path, page_index)
                render_path: str | None = None
                if page_kind == "drawing":
                    out_path = cfg.path("rasterized_pages") / f"{key}.png"
                    render_path = str(out_path)
                    if render and (overwrite or not out_path.exists()):
                        width_px, height_px = save_page_png(pdf_path, page_index, out_path, cfg.dpi)
                    rendered_count += 1

                yield {
                    "pdf_path": str(pdf_path.resolve()),
                    "pdf_stem": pdf_path.stem,
                    "page_index": page_index,
                    "page_number": page_index + 1,
                    "page_kind": page_kind,
                    "width_px": width_px,
                    "height_px": height_px,
                    "render_path": render_path,
                    "sheet_id": sheet_id,
                    "sheet_title": extract_sheet_title(text, sheet_id),
                }
        finally:
            doc.close()


def catalog_pages(
    revision_sets_dir: Path,
    cfg: CloudHammerConfig,
    render: bool = True,
    overwrite: bool = False,
    limit: int | None = None,
    only_pdf: str | None = None,
    only_page_index: int | None = None,
    manifest_path: Path | None = None,
) -> int:
    cfg.ensure_directories()
    manifest = manifest_path or (cfg.path("manifests") / "pages.jsonl")
    rows = iter_page_rows(
        revision_sets_dir,
        cfg,
        render=render,
        overwrite=overwrite,
        limit=limit,
        only_pdf=only_pdf,
        only_page_index=only_page_index,
    )
    return write_jsonl(manifest, rows)
