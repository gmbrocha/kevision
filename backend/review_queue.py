from __future__ import annotations

from dataclasses import replace
from math import isfinite
from typing import Iterable

from .revision_state.models import ChangeItem


QUEUE_ORDER_STEP = 1000.0
REPLACEMENT_ORDER_STEP = 0.001


def is_superseded(item: ChangeItem) -> bool:
    return bool(item.superseded_by_change_item_ids or item.superseded_reason or item.superseded_at)


def visible_change_items(items: Iterable[ChangeItem]) -> list[ChangeItem]:
    return [item for item in items if not is_superseded(item)]


def legacy_review_sort_key(item: ChangeItem) -> tuple[bool, str, str, str]:
    return (item.status != "pending", item.sheet_id, item.detail_ref or "", item.id)


def review_queue_sort_key(item: ChangeItem) -> tuple[float, bool, str, str, str]:
    order = _finite_order(item.queue_order)
    if order <= 0:
        order = float("inf")
    return (order, item.status != "pending", item.sheet_id, item.detail_ref or "", item.id)


def ordered_change_items(items: Iterable[ChangeItem], *, include_superseded: bool = False) -> list[ChangeItem]:
    rows = list(items if include_superseded else visible_change_items(items))
    return sorted(rows, key=review_queue_sort_key)


def ensure_queue_order(items: Iterable[ChangeItem]) -> tuple[list[ChangeItem], bool]:
    rows = list(items)
    if not rows:
        return rows, False

    existing_orders = [_finite_order(item.queue_order) for item in rows if _finite_order(item.queue_order) > 0]
    if not existing_orders:
        changed = False
        ordered_rows = sorted(rows, key=legacy_review_sort_key)
        assigned: dict[str, ChangeItem] = {}
        for index, item in enumerate(ordered_rows, start=1):
            updated = replace(item, queue_order=index * QUEUE_ORDER_STEP)
            assigned[item.id] = updated
            changed = True
        return [assigned[item.id] for item in rows], changed

    next_order = max(existing_orders) + QUEUE_ORDER_STEP
    changed = False
    assigned: dict[str, ChangeItem] = {}
    missing = sorted(
        [
            item
            for item in rows
            if _finite_order(item.queue_order) <= 0
        ],
        key=legacy_review_sort_key,
    )
    for item in missing:
        assigned[item.id] = replace(item, queue_order=next_order)
        next_order += QUEUE_ORDER_STEP
        changed = True
    if not changed:
        return rows, False
    return [assigned.get(item.id, item) for item in rows], True


def review_queue_counts(items: Iterable[ChangeItem]) -> dict[str, int]:
    visible = visible_change_items(items)
    return {
        "all": len(visible),
        "pending": len([item for item in visible if item.status == "pending"]),
        "approved": len([item for item in visible if item.status == "approved"]),
        "rejected": len([item for item in visible if item.status == "rejected"]),
    }


def replacement_queue_order(parent: ChangeItem, index: int) -> float:
    base_order = _finite_order(parent.queue_order)
    if base_order <= 0:
        base_order = QUEUE_ORDER_STEP
    return round(base_order + (index + 1) * REPLACEMENT_ORDER_STEP, 6)


def _finite_order(value: object) -> float:
    try:
        order = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return order if isfinite(order) else 0.0
