"""Stage 1: mask PDF text.

Use the PDF's embedded text layer to white out every word's bounding box in the
rendered page image. This kills the densest source of arc-shaped noise (letters
like S, B, C, O, D, G, etc.) before we look for cloud scallops.

No OCR fallback in this experiment — our fixture PDFs all have a real text layer.
"""
from __future__ import annotations

import cv2
import numpy as np


def mask_text(
    gray: np.ndarray,
    text_rects: list[tuple[int, int, int, int]],
    pad: int = 2,
) -> np.ndarray:
    """Return a copy of `gray` with every text rect painted white.

    `text_rects` are pixel-coord (x0, y0, x1, y1) tuples. `pad` is a small
    dilation in pixels to absorb anti-aliasing fringe around glyphs.
    """
    out = gray.copy()
    h, w = out.shape[:2]
    for x0, y0, x1, y1 in text_rects:
        x0 = max(0, x0 - pad)
        y0 = max(0, y0 - pad)
        x1 = min(w, x1 + pad)
        y1 = min(h, y1 + pad)
        if x1 <= x0 or y1 <= y0:
            continue
        out[y0:y1, x0:x1] = 255
    return out


def overlay_text_rects(
    gray: np.ndarray,
    text_rects: list[tuple[int, int, int, int]],
) -> np.ndarray:
    """Diagnostic overlay: original page with text rects outlined in red."""
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for x0, y0, x1, y1 in text_rects:
        cv2.rectangle(bgr, (x0, y0), (x1, y1), (0, 0, 220), 2)
    return bgr
