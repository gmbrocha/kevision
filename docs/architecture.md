# KEVISION Architecture

For a docs map, start at `README.md` in this folder.

Status: `Current source of truth for repo structure and ownership boundaries.`

## Responsibilities

- `CloudHammer/`
  CV/model pipeline only. It owns page cataloging, delta bootstrap adapters, ROI extraction, API prelabels, human-reviewed label prep, YOLO training, and cloud inference experiments.
- `backend/`
  Product orchestration. It owns revision-set scanning, index/parser logic, workspace persistence, revision-state tracking, deliverable generation, and the seam where CloudHammer inference will plug into the rest of the product.
- `webapp/`
  Review UI. It presents the backend workspace and export flow. The legacy API verification helper is archived; the current UI is local-review-first.
- `resources/`
  Intended home for source drawing sets and curated sample outputs. `revision_sets/` remains at the repo root temporarily for compatibility.
- `archive/`
  Quarantine for old experiments, deprecated scripts, and old outputs.

## Current Boundaries

### CloudHammer

CloudHammer should not own:

- deliverable Excel generation
- revision-state tracking
- workspace persistence
- review GUI behavior

CloudHammer should own:

- image/data generation for cloud training and inference
- labeling workflow docs
- local model training/inference scripts
- model-specific data/manifests/configs

### Backend

Backend should own:

- parsing drawing packages and sheet metadata
- supersedence tracking
- review queue state
- exportable deliverables
- integration seam for CloudHammer detections

The active scanner path now treats cloud detection as an integration boundary rather than running the legacy OpenCV contour detector inline.

## Staged Migration Notes

- `revision_tool/` is now a compatibility wrapper, not the canonical implementation.
- `webapp/` contains the current Flask route/template/static surface, but it still depends on backend workspace objects.
- `experiments/2026_04_index_parser/` remains in place as reference material while equivalent parser logic is promoted into `backend/parsers/`.
- `revision_sets/` has not been physically moved yet because both tests and CloudHammer defaults still reference the root path.
- During any active CloudHammer prelabel run, the API input/output folders should be treated as hands-off runtime state rather than cleanup candidates.

## Near-Term Workflow

1. Build or refine the CloudHammer model pipeline under `CloudHammer/`.
2. Produce reviewed cloud labels and train local inference.
3. Reattach CloudHammer inference to backend scanning/review.
4. Use `backend/` plus `webapp/` to review outputs and export deliverables.
