from __future__ import annotations

from pathlib import Path

import fitz
import numpy as np


def native_to_pixel_matrix(page: fitz.Page, dpi: int) -> fitz.Matrix:
    zoom = dpi / 72.0
    return page.rotation_matrix * fitz.Matrix(zoom, zoom)


def rendered_pixel_size(page: fitz.Page, dpi: int) -> tuple[int, int]:
    zoom = dpi / 72.0
    rect = page.rect
    width = int(round(rect.width * zoom))
    height = int(round(rect.height * zoom))
    if page.rotation in {90, 270}:
        return height, width
    return width, height


def render_page_gray(pdf_path: str | Path, page_index: int, dpi: int = 300) -> tuple[np.ndarray, fitz.Matrix]:
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, colorspace=fitz.csGRAY)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        return image, native_to_pixel_matrix(page, dpi)
    finally:
        doc.close()


def save_page_png(pdf_path: str | Path, page_index: int, output_path: str | Path, dpi: int = 300) -> tuple[int, int]:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, colorspace=fitz.csGRAY)
        pix.save(out)
        return pix.width, pix.height
    finally:
        doc.close()
