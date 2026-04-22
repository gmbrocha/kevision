# delta_v3 — Δ marker denoise pipeline

**Status:** denoise pipeline kept; detection scrapped 2026-04-21 (was producing
the recursive-triangle apocalypse — see git history). Restarting detection
from scratch in a future session, using this pipeline's output as input.

## What's here

- `denoise_1.py`, `denoise_2.py`, `denoise_x.py` — the staged denoise pipeline.
- `Revision #1 - Drawing Changes_p17_denoise_{1,2,x}.png` — outputs of the
  three denoise stages on the canonical test page (Rev1 p17).

## Canonical input for the restart

`Revision #1 - Drawing Changes_p17_denoise_2.png` is the cleanest pre-detection
image we have. The deltas are visually clear (thin outlines, page is large —
zoom to see them). Whatever detector comes next should consume this image as
its input rather than re-running denoise from raw render.

## Lineage

- `2026_04_delta_marker_detector/` — original attempt, contour + hull +
  PDF-text-digit confirmation. Different approach (detect on raw render). Not
  the basis for this work.
- `delta_v2/` — Tier 2 digit-anchored detection + early denoise. Fed denoise
  ideas into v3.
- `delta_v3/` (this folder) — clean denoise pipeline + bottom-up triangle
  detector that didn't pan out. **Detector deleted; denoise kept.**
