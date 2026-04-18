"""denoise_part_2.py — additional denoising on top of part 1.

Starts from `03_denoise_AE122_threshold_150_bases_fixed.png` (the winning
part-1 output, with the thickness-aware horizontal mask preserving Δ bases
that touch walls) and applies three further passes, saving intermediate
images so each effect can be inspected independently:

  Step 1  -> 04_text_alpha_removed.png
            Erase every text string that contains ANY alphabetic character,
            regardless of orientation. Pure-numeric strings survive this step.

  Step 2  -> 05_rotated_removed.png
            Additionally erase every text string oriented at 90 degrees
            (rotated left from the reader's perspective) — both numeric
            and alpha variants.

  Step 3  -> 06_arcs_removed.png
            Additionally drop connected ink components that do not touch a
            generous halo around any surviving pure-upright-numeric word.
            Intended to wipe scallop arcs / fixture arcs that aren't part
            of (or near) a real digit pattern, while sparing the digit
            strokes themselves and the Δ outline that wraps them.

This is orchestration / experimental denoise — no algorithm changes to the
production detector. Run:

    python experiments/delta_v2/denoise_part_2.py
"""
from __future__ import annotations

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

PDF_PATH = REPO_ROOT / "revision_sets" / "Revision #1 - Drawing Changes" / "Revision #1 - Drawing Changes.pdf"
PAGE = 17
INPUT_IMG = OUT_DIR / "03_denoise_AE122_threshold_150_bases_fixed.png"

# Padding (px at 300 DPI) added around every erased text bbox to also wipe
# the anti-aliased fringe that PyMuPDF's tight bbox can leave behind.
TEXT_ERASE_PAD = 4

# Step 3 — arc removal halo around each surviving pure-numeric word.
# Δ_side ≈ 1.8 × digit_height, so a halo of ~2.5 × digit_height comfortably
# encloses the surrounding Δ outline.
ARC_KEEP_HALO_MULTIPLIER = 2.5
ARC_KEEP_HALO_MIN_PX = 60

ALPHA_RE = re.compile(r"[A-Za-z]")
PURE_NUMERIC_RE = re.compile(r"^\d+$")
ROT_TOL = 0.15


# ---------------------------------------------------------------------------
# Word classification helpers
# ---------------------------------------------------------------------------


def contains_alpha(text: str) -> bool:
    return bool(ALPHA_RE.search(text))


def is_pure_numeric(text: str) -> bool:
    return bool(PURE_NUMERIC_RE.match(text))


def displayed_direction(native_dir: tuple[float, float], page_rotation_deg: int) -> tuple[float, float]:
    """Map a native text-line direction vector into the displayed pixel space.

    PyMuPDF's `dir` is in native page coords. When the page is rotated for
    display, vectors rotate with it. For drawing pages this is usually a
    no-op (rotation=0), but we handle it for safety.
    """
    if page_rotation_deg % 360 == 0:
        return native_dir
    rad = np.radians(page_rotation_deg)
    cos_r, sin_r = float(np.cos(rad)), float(np.sin(rad))
    dx, dy = native_dir
    # PyMuPDF page rotation is clockwise; in y-down screen coords this maps:
    return (dx * cos_r + dy * sin_r, -dx * sin_r + dy * cos_r)


def is_upright(displayed_dir: tuple[float, float]) -> bool:
    dx, dy = displayed_dir
    return abs(dx - 1.0) < ROT_TOL and abs(dy) < ROT_TOL


def is_rotated_left(displayed_dir: tuple[float, float]) -> bool:
    """Rotated 90° CCW from the reader = baseline points up = (0, -1)."""
    dx, dy = displayed_dir
    return abs(dx) < ROT_TOL and abs(dy + 1.0) < ROT_TOL


# ---------------------------------------------------------------------------
# PDF text extraction (per-word bbox + per-line direction)
# ---------------------------------------------------------------------------


def collect_words(pdf_path: Path, page_idx: int) -> list[dict]:
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_idx]
        page_rotation = page.rotation
        native_to_pixel = detect_deltas._native_to_pixel_matrix(page, detect_deltas.DEFAULT_DPI)

        # PyMuPDF's `get_text("words")` gives per-word bboxes but no rotation.
        # `get_text("dict")` gives per-line `dir` vectors. Match by (block, line) idx.
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
            x0, y0, x1, y1, text, bno, lno, _wno = w
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
# Main pipeline
# ---------------------------------------------------------------------------


def main() -> None:
    if not INPUT_IMG.exists():
        print(f"ERROR: {INPUT_IMG} not found. Run run_denoise.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {INPUT_IMG.name} ...")
    base = cv2.imread(str(INPUT_IMG), cv2.IMREAD_GRAYSCALE)
    if base is None:
        print(f"ERROR: failed to read {INPUT_IMG}", file=sys.stderr)
        sys.exit(1)
    print(f"  {base.shape[1]}x{base.shape[0]}")

    print(f"Reading text layer from {PDF_PATH.name} page {PAGE} ...")
    words = collect_words(PDF_PATH, PAGE)

    alpha_words = [w for w in words if contains_alpha(w["text"])]
    rotated_words = [w for w in words if is_rotated_left(w["dir"])]
    rotated_only_numeric = [w for w in rotated_words if not contains_alpha(w["text"])]
    kept_numeric = [
        w for w in words
        if is_pure_numeric(w["text"]) and is_upright(w["dir"])
    ]

    print(f"  total words: {len(words)}")
    print(f"  - alpha-containing  (erased step 1): {len(alpha_words)}")
    print(f"  - rotated-left      (erased step 2): {len(rotated_words)}"
          f"  ({len(rotated_only_numeric)} of those are pure-numeric)")
    print(f"  - kept pure-numeric upright (anchors): {len(kept_numeric)}")

    # --- Step 1: erase alpha-containing words -------------------------------
    img1 = base.copy()
    erase_bboxes(img1, [w["bbox"] for w in alpha_words])
    out1 = OUT_DIR / "04_text_alpha_removed.png"
    cv2.imwrite(str(out1), img1)
    print(f"  wrote {out1.name}")

    # --- Step 2: additionally erase 90-deg rotated text (any kind) ---------
    img2 = img1.copy()
    erase_bboxes(img2, [w["bbox"] for w in rotated_words])
    out2 = OUT_DIR / "05_rotated_removed.png"
    cv2.imwrite(str(out2), img2)
    print(f"  wrote {out2.name}")

    # --- Step 3: drop ink components not anchored on a kept numeric -------
    h, w = img2.shape[:2]
    keep_mask = np.zeros((h, w), dtype=np.uint8)
    for word in kept_numeric:
        x0, y0, x1, y1 = word["bbox"]
        digit_h = max(1, y1 - y0)
        halo = max(ARC_KEEP_HALO_MIN_PX, int(digit_h * ARC_KEEP_HALO_MULTIPLIER))
        x0p = max(0, x0 - halo)
        y0p = max(0, y0 - halo)
        x1p = min(w, x1 + halo)
        y1p = min(h, y1 + halo)
        cv2.rectangle(keep_mask, (x0p, y0p), (x1p, y1p), 255, -1)

    binary = cv2.threshold(
        img2, detect_deltas.DELTA_SEARCH_INK_THRESHOLD, 255, cv2.THRESH_BINARY_INV
    )[1]
    n_labels, labels, _stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

    keep_per_component = np.zeros(n_labels, dtype=bool)
    keep_per_component[0] = True  # background
    inside = (keep_mask > 0) & (labels > 0)
    label_ids_inside = np.unique(labels[inside])
    keep_per_component[label_ids_inside] = True

    drop_pixels = (~keep_per_component[labels]) & (labels > 0)
    img3 = img2.copy()
    img3[drop_pixels] = 255

    n_kept_cc = int(np.sum(keep_per_component[1:]))
    n_drop_cc = int((n_labels - 1) - n_kept_cc)
    print(f"  components: kept {n_kept_cc} / dropped {n_drop_cc} (total {n_labels - 1})")

    out3 = OUT_DIR / "06_arcs_removed.png"
    cv2.imwrite(str(out3), img3)
    print(f"  wrote {out3.name}")


if __name__ == "__main__":
    main()
