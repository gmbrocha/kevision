# delta_v3 - Delta marker denoise pipeline

**Status:** denoise pipeline kept; detection scrapped on 2026-04-21 after the
recursive-triangle failure mode. The denoise stages remain the canonical input
path for delta bootstrapping.

## What's here

- `denoise_1.py`, `denoise_2.py`, `denoise_x.py` - the staged denoise pipeline
- canonical denoised page images for the main test pages

## Canonical Input for Restart

`Revision #1 - Drawing Changes_p17_denoise_2.png` is the cleanest
pre-detection image we have. Whatever detector comes next should consume this
image as input rather than re-running denoise from an unrelated path.

## Lineage

- `2026_04_delta_marker_detector/` - legacy helper and rendering utilities
  still used by the denoise scripts here via `detect_deltas.py`
- older superseded delta branches were removed from the active tree; use git
  history if their provenance is needed again
- `delta_v3/` (this folder) - the clean denoise pipeline that survived after
  the detector on top of it was discarded
