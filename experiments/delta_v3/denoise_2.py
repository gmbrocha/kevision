"""denoise_2.py — Stage 2 denoising on top of denoise_1 output.

Reads stage-1 output plus the PDF text layer, and produces a further-cleaned
image suitable as input to Δ-detection.

Pipeline (operates on the stage-1 grayscale):
  1. Erase every word whose text contains any alphabetic character (any
     orientation). Pure-numeric words survive this step.
  2. Erase every word at 90° rotation (rotated left from the reader).
     Both numeric and alpha variants are removed; rotated dimensions
     and labels go.
  3. Drop ink components that don't touch a halo around any surviving
     pure-upright-numeric word. Halo radius = max(60, 2.5 × digit_height).
     Designed to wipe scallop arcs, fixture curves, and stray ink while
     sparing real digit strokes and the Δ outlines that wrap them.

Output:
  experiments/delta_v3/<pdf_stem>_p<page>_denoise_2.png

Usage:
  python experiments/delta_v3/denoise_2.py
  python experiments/delta_v3/denoise_2.py --pdf path/to.pdf --page 17

Defaults: AE122 (Revision #1, page 17).

Known limitation: this stage aggressively prunes non-digit-adjacent ink and is
therefore useful for delta bootstrapping, not for cloud reasoning.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import cv2
import fitz
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DETECTOR_DIR = REPO_ROOT / "experiments" / "2026_04_delta_marker_detector"
OUT_DIR = Path(__file__).parent

sys.path.insert(0, str(DETECTOR_DIR))
import detect_deltas  # noqa: E402

# Local import: derive the stage-1 output filename via the same convention.
sys.path.insert(0, str(OUT_DIR))
from denoise_1 import output_path as denoise_1_output_path  # noqa: E402

DEFAULT_PDF = REPO_ROOT / "revision_sets" / "Revision #1 - Drawing Changes" / "Revision #1 - Drawing Changes.pdf"
DEFAULT_PAGE = 17

# Stage-1 ink threshold mirrors denoise_1.INK_THRESHOLD; only used here for
# the connected-components binarization in step 3.
INK_THRESHOLD = 150

# Step 1/2 — text bbox erase padding (px at 300 DPI), absorbs anti-alias fringe.
TEXT_ERASE_PAD = 4

# Step 3 — keep-halo radius around each surviving pure-numeric upright word.
ARC_KEEP_HALO_MULTIPLIER = 2.5
ARC_KEEP_HALO_MIN_PX = 60

ALPHA_RE = re.compile(r"[A-Za-z]")
PURE_NUMERIC_RE = re.compile(r"^\d+$")
ROT_TOL = 0.15


# ---------------------------------------------------------------------------
# Word classification
# ---------------------------------------------------------------------------


def contains_alpha(text: str) -> bool:
    return bool(ALPHA_RE.search(text))


def is_pure_numeric(text: str) -> bool:
    return bool(PURE_NUMERIC_RE.match(text))


def displayed_direction(native_dir: tuple[float, float], page_rotation_deg: int) -> tuple[float, float]:
    """Map a native PyMuPDF text-line dir into displayed pixel space."""
    if page_rotation_deg % 360 == 0:
        return native_dir
    rad = np.radians(page_rotation_deg)
    cos_r, sin_r = float(np.cos(rad)), float(np.sin(rad))
    dx, dy = native_dir
    return (dx * cos_r + dy * sin_r, -dx * sin_r + dy * cos_r)


def is_upright(d: tuple[float, float]) -> bool:
    return abs(d[0] - 1.0) < ROT_TOL and abs(d[1]) < ROT_TOL


def is_rotated_left(d: tuple[float, float]) -> bool:
    """Rotated 90° CCW from reader = baseline points up = (0, -1) in screen coords."""
    return abs(d[0]) < ROT_TOL and abs(d[1] + 1.0) < ROT_TOL


def collect_words(pdf_path: Path, page_idx: int) -> list[dict]:
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_idx]
        page_rotation = page.rotation
        native_to_pixel = detect_deltas._native_to_pixel_matrix(page, detect_deltas.DEFAULT_DPI)

        line_dirs: dict[tuple[int, int], tuple[float, float]] = {}
        raw = page.get_text("dict")
        for bi, block in enumerate(raw.get("blocks", [])):
            if block.get("type") != 0:
                continue
            for li, line in enumerate(block.get("lines", [])):
                native_d = tuple(line.get("dir", (1.0, 0.0)))
                line_dirs[(bi, li)] = displayed_direction(native_d, page_rotation)

        out: list[dict] = []
        for w in page.get_text("words"):
            x0, y0, x1, y1, text, bno, lno, _ = w
            text = (text or "").strip()
            if not text:
                continue
            rect = fitz.Rect(x0, y0, x1, y1) * native_to_pixel
            rect.normalize()
            d = line_dirs.get((bno, lno), (1.0, 0.0))
            out.append(
                {
                    "text": text,
                    "bbox": (int(rect.x0), int(rect.y0), int(rect.x1), int(rect.y1)),
                    "dir": d,
                }
            )
    finally:
        doc.close()
    return out


def erase_bboxes(img: np.ndarray, bboxes: list[tuple[int, int, int, int]], pad: int = TEXT_ERASE_PAD) -> None:
    h, w = img.shape[:2]
    for x0, y0, x1, y1 in bboxes:
        x0p = max(0, x0 - pad)
        y0p = max(0, y0 - pad)
        x1p = min(w, x1 + pad)
        y1p = min(h, y1 + pad)
        if x1p > x0p and y1p > y0p:
            img[y0p:y1p, x0p:x1p] = 255


# ---------------------------------------------------------------------------
# Stage-2 denoise
# ---------------------------------------------------------------------------


def denoise_stage_2(stage1_img: np.ndarray, words: list[dict]) -> np.ndarray:
    img = stage1_img.copy()

    # Step 1: alpha-containing words.
    alpha_words = [w for w in words if contains_alpha(w["text"])]
    erase_bboxes(img, [w["bbox"] for w in alpha_words])

    # Step 2: 90°-rotated words (any text).
    rotated_words = [w for w in words if is_rotated_left(w["dir"])]
    erase_bboxes(img, [w["bbox"] for w in rotated_words])

    # Step 3: drop ink components not anchored on a kept pure-numeric upright word.
    kept_numeric = [
        w for w in words
        if is_pure_numeric(w["text"]) and is_upright(w["dir"])
    ]
    h, w_dim = img.shape[:2]
    keep_mask = np.zeros((h, w_dim), dtype=np.uint8)
    for word in kept_numeric:
        x0, y0, x1, y1 = word["bbox"]
        digit_h = max(1, y1 - y0)
        halo = max(ARC_KEEP_HALO_MIN_PX, int(digit_h * ARC_KEEP_HALO_MULTIPLIER))
        x0p = max(0, x0 - halo)
        y0p = max(0, y0 - halo)
        x1p = min(w_dim, x1 + halo)
        y1p = min(h, y1 + halo)
        cv2.rectangle(keep_mask, (x0p, y0p), (x1p, y1p), 255, -1)

    binary = cv2.threshold(img, INK_THRESHOLD, 255, cv2.THRESH_BINARY_INV)[1]
    n_labels, labels, _stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

    keep_per_component = np.zeros(n_labels, dtype=bool)
    keep_per_component[0] = True  # background
    inside = (keep_mask > 0) & (labels > 0)
    label_ids_inside = np.unique(labels[inside])
    keep_per_component[label_ids_inside] = True

    drop_pixels = (~keep_per_component[labels]) & (labels > 0)
    img[drop_pixels] = 255

    n_kept_cc = int(np.sum(keep_per_component[1:]))
    n_drop_cc = int((n_labels - 1) - n_kept_cc)
    print(f"  step 1: erased {len(alpha_words)} alpha words")
    print(f"  step 2: erased {len(rotated_words)} rotated-left words")
    print(f"  step 3: kept {n_kept_cc} / dropped {n_drop_cc} ink components"
          f" (halo around {len(kept_numeric)} kept pure-numeric upright anchors)")
    return img


def output_path(pdf_path: Path, page: int) -> Path:
    return OUT_DIR / f"{pdf_path.stem}_p{page}_denoise_2.png"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--page", type=int, default=DEFAULT_PAGE)
    parser.add_argument(
        "--input", type=Path, default=None,
        help="Path to denoise_1 output. Defaults to the path implied by --pdf and --page.",
    )
    args = parser.parse_args()

    pdf_path = args.pdf if args.pdf.is_absolute() else (Path.cwd() / args.pdf).resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    in_path = args.input or denoise_1_output_path(pdf_path, args.page)
    if not in_path.exists():
        print(f"ERROR: stage-1 image not found: {in_path}", file=sys.stderr)
        print(f"       run denoise_1.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {in_path.name} ...")
    stage1 = cv2.imread(str(in_path), cv2.IMREAD_GRAYSCALE)
    if stage1 is None:
        print(f"ERROR: could not read {in_path}", file=sys.stderr)
        sys.exit(1)
    print(f"  {stage1.shape[1]}x{stage1.shape[0]}")

    print(f"Reading text layer from {pdf_path.name} page {args.page} ...")
    words = collect_words(pdf_path, args.page)
    print(f"  {len(words)} words on page")

    out_img = denoise_stage_2(stage1, words)

    out_path = output_path(pdf_path, args.page)
    cv2.imwrite(str(out_path), out_img)
    print(f"  wrote {out_path.name}")


if __name__ == "__main__":
    main()
