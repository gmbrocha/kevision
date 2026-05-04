from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from cloudhammer.data.splits import stable_fraction


REVISION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Revision[_ #.-]*1|Drawing[_ -]*Changes", re.IGNORECASE), "Revision #1 - Drawing Changes"),
    (re.compile(r"260309|Drawing[_ -]*Rev2|Rev[_ -]*2", re.IGNORECASE), "Revision #2 - Mod 5 grab bar supports"),
    (re.compile(r"260313|Rev[_ -]*3", re.IGNORECASE), "Revision #3 - EHRM Drawings"),
    (re.compile(r"260219|Rev[_ -]*4", re.IGNORECASE), "Revision #4 - Dental Air"),
    (re.compile(r"260303|Rev[_ -]*5|RFI[_ -]*126", re.IGNORECASE), "Revision #5 - RFI 126 - Concrete Repairs"),
    (re.compile(r"Revision[_ -]*Set[_ -]*7|Rev[_ -]*7|RFI[_ -]*141", re.IGNORECASE), "Revision #7 - RFI 141 - Deteriorated Attic Wood"),
)

HARD_NEGATIVE_PREFIXES = (
    "eval_symbol_text_fp_hn_",
    "marker_fp_hn_",
    "reviewed_fp_hn_",
    "hard_negative_",
)

DEFAULT_QUASI_HOLDOUT_REVISIONS = {
    "Revision #5 - RFI 126 - Concrete Repairs",
    "Revision #7 - RFI 141 - Deteriorated Attic Wood",
}


@dataclass(frozen=True)
class SourceKey:
    source_id: str
    page_index: int | None
    revision_group: str

    @property
    def page_key(self) -> str:
        page = "unknown" if self.page_index is None else f"{self.page_index:04d}"
        return f"{self.source_id}:p{page}"


def manifest_row(row: dict[str, Any]) -> dict[str, Any]:
    nested = row.get("manifest_row")
    return nested if isinstance(nested, dict) else row


def row_id(row: dict[str, Any]) -> str:
    data = manifest_row(row)
    for key in ("cloud_roi_id", "candidate_id", "marker_seed_id"):
        value = row.get(key) or data.get(key)
        if value:
            return str(value)
    for key in ("roi_image_path", "source_image_path", "image_path", "render_path", "page_image_path"):
        value = row.get(key) or data.get(key)
        if value:
            return Path(str(value)).stem
    return "unknown"


def _path_parts(value: str) -> list[str]:
    return [part for part in re.split(r"[\\/]+", value) if part]


def _first_nonempty(row: dict[str, Any], keys: Iterable[str]) -> str:
    data = manifest_row(row)
    for key in keys:
        value = row.get(key) or data.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def strip_training_prefix(value: str) -> str:
    current = value
    changed = True
    while changed:
        changed = False
        for prefix in HARD_NEGATIVE_PREFIXES:
            if current.startswith(prefix):
                current = current[len(prefix) :]
                changed = True
    return current


def page_index_for_row(row: dict[str, Any]) -> int | None:
    data = manifest_row(row)
    for key in ("source_page_index", "page_index", "page_number", "page"):
        value = row.get(key) if row.get(key) not in (None, "") else data.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            pass

    text = " ".join(
        filter(
            None,
            [
                row_id(row),
                _first_nonempty(row, ("roi_image_path", "source_image_path", "image_path", "render_path", "page_image_path")),
            ],
        )
    )
    match = re.search(r"_p(\d{4})(?:_|\.|$)", text)
    return int(match.group(1)) if match else None


def source_id_for_row(row: dict[str, Any]) -> str:
    data = manifest_row(row)
    explicit = row.get("source_id") or data.get("source_id")
    if explicit:
        return str(explicit)

    pdf_path = _first_nonempty(row, ("pdf_path", "source_pdf_path"))
    if pdf_path:
        stem = Path(pdf_path).stem
        if stem:
            return _slug(stem)

    for key in ("pdf_stem", "source_pdf_stem"):
        value = row.get(key) or data.get(key)
        if value:
            return _slug(str(value))

    text = strip_training_prefix(row_id(row))
    match = re.match(r"(?P<source>.+?)_p\d{4}(?:_|$)", text)
    if match:
        return _slug(match.group("source"))

    path_text = _first_nonempty(row, ("roi_image_path", "source_image_path", "image_path", "render_path", "page_image_path"))
    if path_text:
        stem = strip_training_prefix(Path(path_text).stem)
        match = re.match(r"(?P<source>.+?)_p\d{4}(?:_|$)", stem)
        if match:
            return _slug(match.group("source"))
        return _slug(Path(path_text).stem)

    return "unknown_source"


def revision_group_for_row(row: dict[str, Any]) -> str:
    data = manifest_row(row)
    for key in ("revision_group", "revision"):
        value = row.get(key) or data.get(key)
        if isinstance(value, str) and value.startswith("Revision #"):
            return value

    pdf_path = _first_nonempty(row, ("pdf_path", "source_pdf_path"))
    for part in _path_parts(pdf_path):
        if part.startswith("Revision #"):
            return part

    text = " ".join(
        filter(
            None,
            [
                pdf_path,
                _first_nonempty(row, ("pdf_stem", "source_pdf_stem")),
                source_id_for_row(row),
                row_id(row),
            ],
        )
    )
    for pattern, revision in REVISION_PATTERNS:
        if pattern.search(text):
            return revision
    return "unknown"


def source_key_for_row(row: dict[str, Any]) -> SourceKey:
    return SourceKey(
        source_id=source_id_for_row(row),
        page_index=page_index_for_row(row),
        revision_group=revision_group_for_row(row),
    )


def source_control_fields(row: dict[str, Any]) -> dict[str, Any]:
    key = source_key_for_row(row)
    return {
        "source_id": key.source_id,
        "source_page_index": key.page_index if key.page_index is not None else "",
        "source_page_key": key.page_key,
        "revision_group": key.revision_group,
    }


def split_for_source_key(
    key: SourceKey,
    *,
    val_fraction: float = 0.2,
    quasi_holdout_revisions: set[str] | None = None,
) -> str:
    holdout = quasi_holdout_revisions if quasi_holdout_revisions is not None else DEFAULT_QUASI_HOLDOUT_REVISIONS
    if key.revision_group in holdout:
        return "quasi_holdout"
    fraction = stable_fraction(key.page_key)
    return "val" if fraction < val_fraction else "train"


def audit_sources(rows: list[dict[str, Any]], eval_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    source_counter: Counter[str] = Counter()
    revision_counter: Counter[str] = Counter()
    page_counter: Counter[str] = Counter()
    split_by_source: dict[str, Counter[str]] = defaultdict(Counter)
    split_by_page: dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        key = source_key_for_row(row)
        split = str(row.get("split") or "unknown")
        source_counter[key.source_id] += 1
        revision_counter[key.revision_group] += 1
        page_counter[key.page_key] += 1
        split_by_source[key.source_id][split] += 1
        split_by_page[key.page_key][split] += 1

    mixed_sources = {
        source: dict(counter)
        for source, counter in sorted(split_by_source.items())
        if len([split for split, count in counter.items() if count > 0]) > 1
    }
    mixed_pages = {
        page: dict(counter)
        for page, counter in sorted(split_by_page.items())
        if len([split for split, count in counter.items() if count > 0]) > 1
    }

    summary: dict[str, Any] = {
        "rows": len(rows),
        "source_count": len(source_counter),
        "source_page_count": len(page_counter),
        "top_sources": source_counter.most_common(20),
        "top_source_pages": page_counter.most_common(20),
        "revision_groups": dict(revision_counter.most_common()),
        "mixed_split_sources": mixed_sources,
        "mixed_split_source_pages": mixed_pages,
    }

    if eval_rows is not None:
        train_sources = {source_key_for_row(row).source_id for row in rows}
        train_pages = {source_key_for_row(row).page_key for row in rows}
        eval_sources = Counter(source_key_for_row(row).source_id for row in eval_rows)
        eval_pages = Counter(source_key_for_row(row).page_key for row in eval_rows)
        source_overlap = sorted(source for source in eval_sources if source in train_sources)
        page_overlap = sorted(page for page in eval_pages if page in train_pages)
        summary["eval_rows"] = len(eval_rows)
        summary["eval_source_overlap_count"] = len(source_overlap)
        summary["eval_source_page_overlap_count"] = len(page_overlap)
        summary["eval_source_overlap"] = source_overlap
        summary["eval_source_page_overlap"] = page_overlap
    return summary


def dedupe_rows_by_id(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        selected.setdefault(row_id(row), row)
    return list(selected.values())


def source_capped_rows(
    rows: Iterable[dict[str, Any]],
    *,
    max_rows_per_source: int | None = None,
    max_rows_per_source_page: int | None = None,
) -> list[dict[str, Any]]:
    source_counts: Counter[str] = Counter()
    page_counts: Counter[str] = Counter()
    selected: list[dict[str, Any]] = []
    for row in sorted(rows, key=_source_priority_key):
        key = source_key_for_row(row)
        if max_rows_per_source is not None and source_counts[key.source_id] >= max_rows_per_source:
            continue
        if max_rows_per_source_page is not None and page_counts[key.page_key] >= max_rows_per_source_page:
            continue
        source_counts[key.source_id] += 1
        page_counts[key.page_key] += 1
        selected.append(row)
    return selected


def _source_priority_key(row: dict[str, Any]) -> tuple[Any, ...]:
    key = source_key_for_row(row)
    is_positive = bool(row.get("reviewed_box_count") or row.get("has_cloud") or row.get("accepted_box_count"))
    confidence = _float_or_zero(row.get("api_confidence") or row.get("cloud_candidate_score") or row.get("whole_cloud_confidence"))
    return (
        key.revision_group,
        key.source_id,
        key.page_index if key.page_index is not None else 999999,
        not is_positive,
        -confidence,
        row_id(row),
    )


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown_source"
