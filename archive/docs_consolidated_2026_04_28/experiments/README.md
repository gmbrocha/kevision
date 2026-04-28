# Experiments

This directory is intentionally trimmed down to the experiments and support
artifacts that still matter.

## Kept

- `2026_04_index_parser/`
  - best working revision-index extraction experiment
  - still useful as the data spine for conformed-sheet and deliverable work
- `2026_04_delta_marker_detector/`
  - kept only because `delta_v3` still imports `detect_deltas.py` from here
  - this is legacy support, not the preferred active workflow
- `delta_v3/`
  - best denoise pipeline for delta bootstrapping
  - canonical pre-detection inputs live here
- `delta_v4/`
  - best-so-far delta detector
- `extract_changelog.py`
  - utility to extract structure and embedded images from Kevin's reference
    workbook
- `preview_revision_changelog.py`
  - utility to generate a preview workbook from a workspace export

## Removed

The following dead or superseded experiment branches were intentionally
deleted from the active tree:

- old cloud CV branches
- cloud ROI/proposal experiments
- older superseded delta branches
- generated output folders
- pycache folders
- one-off inspection/preview artifacts

If something from a removed branch is ever needed again, use git history.
