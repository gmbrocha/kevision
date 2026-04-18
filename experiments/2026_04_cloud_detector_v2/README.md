# Experiment: Cloud Detector Iteration 2

**Status:** in progress

**Approach:** detect by negation, then assemble. Mask everything we can confidently identify (text via PDF text layer, structural lines via Hough), then look for revision-cloud scallops as primitives, tag each with its bulge orientation (∩/∪/⊃/⊂), group same-orientation scallops into runs, and assemble runs into closed loops via opposite-side geometric inference.

See `c:/Users/gmbro/.cursor/plans/cloud_detector_iteration_2_*.plan.md` for the full plan and rationale.

## Why iteration 2 (one-paragraph recap)

Iteration 1 (`../2026_04_cloud_detector/`) used convexity-defect analysis on closed contours. Top-scoring contours included real clouds, so the geometric prior is real — but the approach plateaued because cloud outlines that overlap other linework lose contour purity and because the "concave-bumpy" primitive isn't unique to clouds. Iteration 2 attacks both: clean the image first (mask), then detect a primitive that *is* unique to clouds (a chain of identically-oriented scallops).

## Layout

```
experiments/2026_04_cloud_detector_v2/
├── README.md                 # this file — design + per-stage findings
├── detect.py                 # orchestrator
├── stages/
│   ├── __init__.py
│   ├── mask_text.py          # stage 1
│   ├── mask_lines.py         # stage 2
│   ├── detect_scallops.py    # stage 3 + 4
│   ├── group_runs.py         # stage 5
│   └── match_loops.py        # stage 6
└── output/                   # per-page, per-stage overlay PNGs
```

Per test page we save:
- `<page>_01_text_masked.png`
- `<page>_02_lines_masked.png`
- `<page>_03_scallops.png`
- `<page>_04_runs.png`
- `<page>_05_loops.png` (the final overlay)

## Test pages

Same as iteration 1 for apples-to-apples comparison.

| Label | Source | What we expect |
|---|---|---|
| `rev1_p00_index` | Rev 1 PDF, page 0 | Many small row-bracket clouds; dense table grid |
| `rev1_p01_GI104` | Rev 1 PDF, page 1 | Two known FEC + exit-light clouds |
| `rev1_p04_SF110` | Rev 1 PDF, page 4 | Framing plan; one cloud around a black-square mystery |
| `rev1_p06_AD104` | Rev 1 PDF, page 6 | Multi-drawing demo page; X-hexagon cloud |
| `rev2_AE107_1_R1` | Rev 2 standalone | Different style sanity check |

## Findings

### Stage 1 — text mask (`stages/mask_text.py`)

PDF-text-layer extraction worked perfectly on all five test pages with no OCR fallback needed. Coverage by page: index 3.9% of pixels altered, GI104 2.1%, SF110 0.2%, AD104 2.1%, AE107.1 0.3% — small percentages because text is sparse, but it removes the densest source of arc-shaped noise.

The index page after text mask was already a dramatic improvement: just the table grid + cloud row-brackets + Δ markers + tiny architect stamp left. See `output/rev1_p00_index_01_text_masked.png`.

### Stage 2 — line mask (`stages/mask_lines.py`)

Pivoted from `cv2.HoughLinesP` to morphological line extraction after Hough produced tens of thousands of segments on a 12600x9000 image and the companion-pair check exploded O(n²). Morphological erosion with long horizontal/vertical kernels is O(image), gives a clean structural-mask binary in one shot, and naturally handles "any axis-aligned line longer than X" without enumerating segments.

For index pages we use a 60-px floor (very aggressive — the user observed virtually no isolated short lines exist on index pages outside the table framework). For drawing pages we use 80 px plus a separate "very long" pass at 250 px for borders/section dividers. Diagonal lines aren't masked in v1 — most architectural framework is axis-aligned, and diagonals are also less likely to confuse a scallop detector since scallops aren't diagonal.

After stages 1+2 the index page is essentially just the cloud scallop outlines (`output/rev1_p00_index_02_lines_masked.png`). Drawing pages still have door-swing arcs, dimension marks, equipment outlines, and small wall fragments — work for stages 3-6.

### Checkpoint 1 — does iteration 1's scoring work on cleaned images? (`checkpoint_1.py`)

No, and the failure mode is informative.

| Page | Iteration 1 (raw) | Iteration 1 on cleaned image |
|---|---|---|
| `rev1_p00_index` | 6 clouds | **0** |
| `rev1_p01_GI104` | 11 clouds | **0** |
| `rev1_p04_SF110` | 4 clouds | **0** |
| `rev1_p06_AD104` | 2 clouds | **0** |
| `rev2_AE107_1_R1` | 1 cloud | **1** |

The dominant reject reason on every page is `low_solidity` (207 / 48 / 139 / 143 / 198). Inspecting `output/rev1_p00_index_checkpoint1.png` confirms why: the clouds are now isolated as **thin scallop curves**, not tangled-mass contours. A thin curve has tiny area relative to its convex hull, so iteration 1's "solidity ≥ 0.40" floor — which was calibrated for tangled clouds — rejects every clean cloud outline.

This is actually the result we wanted from the cleaning stage. Iteration 1's score formula assumed clouds would arrive as filled-region contours (because they were tangled with text/grid/walls). Now that the cleaning produces clean cloud outlines, the contour-shape primitive is wrong; we need a primitive that operates on the scallop chain directly. That's exactly what stages 3-6 do.

**Decision:** proceed with stages 3-6 (scallop primitive detection + orientation + run grouping + loop matching). The cleaning has set up a much easier problem for the next stage to solve.

### Stage 3 — scallop primitive detection (`stages/detect_scallops.py`)

Built a multi-scale (radius 12/18/28/42/60 px) × four-orientation (TOP/BOTTOM/LEFT/RIGHT) template bank, ran `cv2.matchTemplate` with `TM_CCOEFF_NORMED` threshold 0.50, applied per-orientation NMS at 0.7×radius. Runtime ~41 s for the index page.

Result on the index page: **53 detections, none of which were on real scallops**. The detector lit up only on the architect seal (a dotted-line circle) and the consultant address block in the page footer. Eyeballing the cleaned image with the user confirmed the failure mode: **the scallops in the cleaned image are fragmented** — the line mask nicked them at every grid-line crossing, leaving each scallop arc broken into multiple short dashes. Template matching expects intact arcs and finds none.

Two follow-on observations from the inspection:
- The seal + consultant block + the small "VA" stamp glyphs are the only remaining non-cloud features after stages 1+2. Future preprocessing should strip them: the seal is a dotted circle (Hough circles, or "everything below the seal's top y = footer mask"), the consultant block sits inside its own bounding rectangle, and the "VA" remnants are filled connected-component blobs above a pixel-density threshold.
- More importantly: **for the SHEET INDEX page we don't need cloud detection at all**. The "X" marks in the revision column are characters in the PDF text layer with exact bounding boxes. Combined with row-number text + sheet-ID text, we can extract the entire revision list deterministically. See `experiments/2026_04_index_parser/`.

**Decision:** pause stages 4-6 of the cloud detector. Ship index parsing first — that's a complete deliverable for Kevin without solving the harder cloud-on-drawings problem. Resume stages 4-6 with a "scallop repair" preprocessing step (morphological close at the inner-rim of each grid-line mask, or skeleton-bridge nearby endpoints) once the index parser is working.
