from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

SHEET_ID_PATTERN = re.compile(
    r"\b(?:GI|AD|AE|IN|PL|EL|EP|MP|MH|ME|E|M|S|SF|CS|RFP)\d{3}(?:\.\d+)?\b"
)
DATE_PATTERN = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
DETAIL_REF_PATTERN = re.compile(
    r"\b(?P<detail>\d{1,3})\s*/?\s*(?P<sheet>(?:GI|AD|AE|IN|PL|EL|EP|MP|MH|ME|E|M|S|SF|CS)\d{3}(?:\.\d+)?)\b"
)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "item"


def stable_id(*parts: object) -> str:
    digest = hashlib.sha1("::".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return digest[:16]


def clean_display_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    replacements = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00b7": "·",
        "â€“": "-",
        "â€”": "-",
        "â€˜": "'",
        "â€™": "'",
        "â€œ": '"',
        "â€�": '"',
        "Â·": "·",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    return cleaned


def normalize_text(value: str) -> str:
    return clean_display_text(value).lower()


def parse_mmddyyyy(value: str | None) -> tuple[int, int, int]:
    if not value:
        return (0, 0, 0)
    try:
        dt = datetime.strptime(value, "%m/%d/%Y")
        return (dt.year, dt.month, dt.day)
    except ValueError:
        return (0, 0, 0)


def json_dumps(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def choose_best_sheet_id(text: str) -> str | None:
    hits = SHEET_ID_PATTERN.findall(text or "")
    return hits[-1] if hits else None


def choose_dates(text: str) -> list[str]:
    return DATE_PATTERN.findall(text or "")


def parse_detail_ref(text: str, fallback_sheet_id: str | None = None) -> str | None:
    if not text:
        return None
    match = DETAIL_REF_PATTERN.search(text)
    if match:
        return f"{match.group('detail')}/{match.group('sheet')}"
    if fallback_sheet_id:
        bubble_match = re.search(r"\b(\d{1,3})\b", text)
        if bubble_match:
            return f"{bubble_match.group(1)}/{fallback_sheet_id}"
    return None


def relpath_str(path: Path, start: Path) -> str:
    return path.resolve().relative_to(start.resolve()).as_posix()


def sort_strings(values: Iterable[str]) -> list[str]:
    return sorted(values, key=lambda item: normalize_text(item))
