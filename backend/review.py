from __future__ import annotations

from .revision_state.models import ChangeItem


def change_item_needs_attention(item: ChangeItem) -> bool:
    signal = float(item.provenance.get("extraction_signal", 1.0))
    if item.provenance.get("source") != "visual-region":
        return False
    return signal < 0.48 or not item.detail_ref
