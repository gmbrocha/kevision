"""Shared constants + page rendering for the iteration-2 experiment."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import fitz
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_DIR = Path(__file__).parent
OUTPUT_DIR = EXPERIMENT_DIR / "output"
DEFAULT_DPI = 300


@dataclass
class TestPage:
    label: str
    rel_pdf: str
    page_index: int
    page_kind: str  # "index" or "drawing" — controls line-mask aggressiveness
    description: str

    @property
    def pdf_path(self) -> Path:
        return REPO_ROOT / self.rel_pdf


PAGES: list[TestPage] = [
    TestPage(
        label="rev1_p00_index",
        rel_pdf="revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf",
        page_index=0,
        page_kind="index",
        description="Sheet index page (many small row-bracket clouds, dense grid)",
    ),
    TestPage(
        label="rev1_p01_GI104",
        rel_pdf="revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf",
        page_index=1,
        page_kind="drawing",
        description="5TH FLOOR CODE PLAN — FEC + exit light, 2 instances",
    ),
    TestPage(
        label="rev1_p04_SF110",
        rel_pdf="revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf",
        page_index=4,
        page_kind="drawing",
        description="4TH FLOOR FRAMING PLAN — black square in wall (mystery)",
    ),
    TestPage(
        label="rev1_p06_AD104",
        rel_pdf="revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf",
        page_index=6,
        page_kind="drawing",
        description="DEMO 4TH+5TH FLOOR — X-hexagon, multi-drawing page",
    ),
    TestPage(
        label="rev2_AE107_1_R1",
        rel_pdf="revision_sets/Revision #2 - Mod 5 grab bar supports/Drawing Rev2- Steel Grab Bars R1 AE107.1.pdf",
        page_index=0,
        page_kind="drawing",
        description="Rev 2 grab bar — different style sanity check",
    ),
]


def render_page_gray(pdf_path: Path, page_index: int, dpi: int = DEFAULT_DPI) -> tuple[np.ndarray, float]:
    """Render a PDF page to a grayscale numpy array. Returns (image, zoom_factor)."""
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    finally:
        doc.close()
    return img, zoom


def get_text_word_rects(pdf_path: Path, page_index: int, zoom: float) -> list[tuple[int, int, int, int]]:
    """Return text-word bounding boxes in PIXEL coordinates at the given zoom."""
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        words = page.get_text("words")  # each: (x0, y0, x1, y1, "text", block, line, word)
        rects: list[tuple[int, int, int, int]] = []
        for w in words:
            x0, y0, x1, y1 = w[0], w[1], w[2], w[3]
            text = (w[4] or "").strip()
            if not text:
                continue
            rects.append(
                (
                    int(x0 * zoom),
                    int(y0 * zoom),
                    int(x1 * zoom),
                    int(y1 * zoom),
                )
            )
    finally:
        doc.close()
    return rects


def save_overlay(image: np.ndarray, output_path: Path) -> None:
    """Save an image (gray or BGR) to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), image)


def gray_to_bgr(gray: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
