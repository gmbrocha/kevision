from __future__ import annotations

import hashlib
from pathlib import Path


def stable_fraction(value: str) -> float:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return int(digest, 16) / 0xFFFFFFFF


def assign_split(pdf_path: str | Path, page_index: int, val_fraction: float = 0.2, test_fraction: float = 0.1) -> str:
    page_group = int(page_index) // 20
    key = f"{Path(pdf_path).name}:{page_group}"
    fraction = stable_fraction(key)
    if fraction < test_fraction:
        return "test"
    if fraction < test_fraction + val_fraction:
        return "val"
    return "train"
