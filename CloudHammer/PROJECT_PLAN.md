# CloudHammer Project Plan

## Summary

CloudHammer is a standalone subproject inside `drawing_revision` whose only
job is to reliably detect revision clouds on blueprint sheets and emit
machine-readable cloud regions plus visual debug artifacts.

It is explicitly not a rescue attempt for the existing OpenCV cloud
candidates. Those candidates and crops are excluded from training, validation,
and pseudo-labeling.

The downstream goal is straightforward: once CloudHammer is reliable, its
cloud detections can be plugged into the existing parts of the repo that
already do useful work, including revision/index parsing, deliverable setup,
crop embedding, and later export/review flow.

## Product Boundary

CloudHammer v1 owns:
- page-space cloud bounding boxes
- crop images for each detection
- confidence scores
- visual debug overlays
- JSON manifests for downstream consumers

CloudHammer v1 does not own:
- OCR/detail extraction
- nearby-text extraction
- deliverable row generation
- Excel export
- review UI integration

## Current Repo Facts

- The repo contains about `301` likely drawing pages in `revision_sets/` once
  obvious narrative/spec PDFs are excluded.
- The main drawing packages are:
  - `Revision #1 - Drawing Changes.pdf` - 51 pages
  - `260309 - Drawing Rev2- Steel Grab Bars.pdf` - 29 pages
  - `260313 - VA Biloxi Rev 3.pdf` - 198 pages
- Existing OpenCV cloud candidates are fabricated/noisy and should not be used
  as evidence, training data, or negative mining.
- `delta_v4` is useful for bootstrapping, but it is not cleanly packaged and
  is not self-contained.

## Delta Bootstrap Reality

Do not refer to the bootstrap dependency as just `delta_v4`.

The actual bootstrap stack is:
- `experiments/delta_v3/denoise_1.py`
- `experiments/delta_v3/denoise_x.py`
- `experiments/delta_v3/denoise_2.py`
- `experiments/delta_v4/detect.py`
- `experiments/2026_04_delta_marker_detector/detect_deltas.py`

Important constraints:
- `delta_v4/detect.py` expects a denoised grayscale search image on disk.
- It does not run the `delta_v3` denoise pipeline internally.
- It separately uses the source PDF text layer for digit attachment.
- CloudHammer therefore needs a wrapped bootstrap adapter around this full
  stack, not a direct dependency on a clean module.

## Architecture

CloudHammer should have two detection phases.

### Phase A - Bootstrap with Delta-Anchored ROIs

Use the delta stack to accelerate the first dataset and first model:
- run the delta stack on drawing pages
- use detected active deltas to propose local ROIs
- label clouds inside those ROIs
- train the first detector on those ROIs only

This phase exists to get to a viable model quickly.

### Phase B - Graduate to Cloud-First Page Inference

Once the ROI-trained model is serviceable:
- run the model on tiled full-page images
- detect clouds without requiring delta detection at runtime
- keep delta-guided inference only as a debugging or comparison mode

This is the desired end state for v1. If the cloud detector is reliable,
delta checks become redundant.

## Data Strategy

### Excluded Data

Do not use:
- existing heuristic cloud candidates
- existing heuristic crop dumps
- existing workspace cloud boxes
- pseudo-labels derived from those outputs

### Primary Corpus

Use drawing-bearing PDFs from `revision_sets/`.

Create a page manifest that classifies each page as:
- `drawing`
- `narrative`
- `spec`
- `unknown`

Narrative/spec pages are excluded from training and evaluation.

### Render Standard

Use `PyMuPDF` rasterization at `300 DPI` for v1.

Only increase DPI if visual inspection shows cloud lines are too weak at 300.

## Proposed Directory Layout

```text
CloudHammer/
  HANDOFF.md
  PROJECT_PLAN.md
  README.md
  requirements-train.txt
  configs/
    cloudhammer.yaml
  cloudhammer/
    __init__.py
    config.py
    manifests.py
    rasterize.py
    page_catalog.py
    bootstrap/
      __init__.py
      delta_stack.py
      cloud_roi_extract.py
      roi_extract.py
    data/
      splits.py
      yolo.py
    train/
      trainer.py
      evaluate.py
    infer/
      tiles.py
      detect.py
      merge.py
      visualize.py
    contracts/
      detections.py
  scripts/
    catalog_pages.py
    run_delta_bootstrap.py
    extract_cloud_rois.py
    extract_delta_rois.py
    prelabel_cloud_rois_openai.py
    train_roi_detector.py
    infer_pages.py
    visualize_detections.py
  data/
    raw_pdfs/
    rasterized_pages/
    delta_json/
    cloud_roi_images/
    api_cloud_inputs/
    api_cloud_predictions/
    api_cloud_labels/
    api_cloud_review/
    roi_images/
    cloud_labels/
    labels/
    manifests/
    synthetic/
  models/
  runs/
  outputs/
```

## Config Contract

Create `configs/cloudhammer.yaml` with at least:

```yaml
paths:
  raw_pdfs: data/raw_pdfs
  rasterized_pages: data/rasterized_pages
  delta_json: data/delta_json
  roi_images: data/roi_images
  labels: data/labels
  manifests: data/manifests
  models: models
  runs: runs
  outputs: outputs

render:
  dpi: 300

bootstrap:
  roi_size: 1400
  target_revision_digit: null

training:
  model: yolov8n.pt
  imgsz: 640
  epochs: 50
  batch: 16

inference:
  confidence_threshold: 0.5
  tile_size: 1280
  tile_overlap: 192
  nms_iou: 0.5
```

## Phase 0 - Corpus Catalog and Audit

Build a reproducible page catalog before any training.

### Script

`scripts/catalog_pages.py`

### Responsibilities

- walk all PDFs under `revision_sets/`
- classify pages by page kind
- record page counts and source metadata
- render only drawing pages
- write `data/manifests/pages.jsonl`

### Required Manifest Fields

- `pdf_path`
- `pdf_stem`
- `page_index`
- `page_number`
- `page_kind`
- `width_px`
- `height_px`
- `render_path`
- `sheet_id` if extractable
- `sheet_title` if extractable

### Acceptance

- all drawing pages are discoverable from a single manifest
- non-drawing pages are explicitly marked, not silently dropped

## Phase 1 - Delta Bootstrap Adapter

Wrap the real delta dependency stack behind one CloudHammer entrypoint.

### Script

`scripts/run_delta_bootstrap.py`

### Responsibilities

For each drawing page:
1. generate the delta-search raster through the `delta_v3` denoise pipeline
2. run `delta_v4/detect.py` against that raster
3. persist JSON results and overlays under `data/delta_json/` and
   `outputs/audit/`
4. expose a normalized CloudHammer-side manifest of active/historical deltas

### Required Normalized Delta Fields

- `pdf_path`
- `page_index`
- `target_digit`
- `active_deltas`
- `historical_deltas`
- `geometry_only_deltas`
- `canonical_side_px`

Each delta entry should preserve:
- `digit`
- `status`
- `center`
- `triangle`
- `score`
- `geometry_score`
- `side_support`
- `base_support`
- `interior_ink_ratio`

### Acceptance

- bootstrap runs as one CloudHammer command even if it wraps ugly legacy
  scripts internally
- normalized output is independent of the legacy experiment file layout

## Phase 2 - Cloud ROI Extraction

### Script

`scripts/extract_cloud_rois.py`

### Responsibilities

- exclude index, table-of-contents, cover, and clearly non-drawing sheets
- derive the current revision digit from source names such as `Rev 4` or accept
  an explicit `--target-revision-digit` / map
- generate large marker-neighborhood windows only from markers whose digit
  matches the current revision set
- keep old revision marker digits out of primary cloud candidates by default
- retain weak `cloud_likeness` as debug/ranking metadata only
- store ROI images under `data/cloud_roi_images/`
- write `data/manifests/cloud_roi_manifest.jsonl`

### Default ROI Rule

- centered, shifted-left/right/up/down marker-neighborhood windows
- default crop sizes `1536x1536` and `2048x2048` page pixels
- clipped at page edges
- exact mapping back to page coordinates retained in the manifest

### Required ROI Manifest Fields

- `pdf_path`
- `page_index`
- `cloud_roi_id`
- `roi_type`
- `seed_type`
- `contains_marker`
- `delta_digit` as context only
- `target_revision_digit`
- `marker_digit`
- `marker_matches_target`
- `marker_bbox`
- `crop_offset`
- `is_excluded`
- `exclude_reason`
- `roi_bbox_page`
- `roi_image_path`
- `split`
- `label_path`

## Phase 3 - Manual Labeling

Use an off-the-shelf local annotation tool.

Default assumption: `labelImg`.

### Label Target

Initial target:
- `250-500` ROIs total
- enough positives and hard negatives from real pages only

### Labeling Rules

- label `cloud_motif` boxes directly on the ROI images
- label every real cloud motif in a crop; one ROI may have multiple boxes
- include both bold/high-contrast and thin/faint clouds intentionally
- include intersected clouds, partial/cropped clouds, and clouds crossing other
  drawing linework
- label only the scalloped revision cloud boundary
- leave revision triangles, digits, text, fixtures, intersections, and ordinary
  linework unlabeled
- do not seed labels from old cloud crops
- include hard negatives from real ROI pages:
  - toilets/fixtures
  - text clusters
  - leader-line clutter
  - dense structural linework
  - triangle-touching clouds
  - marker-neighborhood crops with no visible cloud
  - multi-cloud sheets
  - damaged/partial-looking clouds

### Split Strategy

Split by source document or grouped page ranges, not by random ROI alone.

The goal is to prevent train/validation leakage from nearly identical drawing
pages.

## Phase 4 - ROI Detector Baseline

### Optional API Prelabeling

`scripts/prelabel_cloud_rois_openai.py` can inspect compressed ROI copies with
an OpenAI vision-capable model and write approximate prelabels:

- compressed inputs: `data/api_cloud_inputs/`
- raw/parsed predictions: `data/api_cloud_predictions/predictions.jsonl`
- YOLO prelabels: `data/api_cloud_labels/*.txt`
- review overlays: `data/api_cloud_review/*.jpg`

Prelabels are never human labels. Keep them separate until reviewed. The API
prompt and label validation allow only class `0: cloud_motif`; no triangle or
digit classes are generated.

### Script

`scripts/train_roi_detector.py`

### Model

- `ultralytics` YOLO
- one class: `cloud_motif`
- default weights: `yolov8n.pt`

### Initial Training Defaults

- `imgsz=640`
- `epochs=50`
- `batch=16`

Adjust only if VRAM or convergence requires it.

### Real-Data-First Policy

Train on real labeled ROIs before building any synthetic compositor.

### Expected Augmentations

- scale
- mild rotation
- blur
- JPEG compression
- contrast shift
- line-thickness variation
- partial occlusion
- local clutter overlap

### Acceptance

- held-out ROI detections are visually credible
- false positives are lower than the old CV failure modes
- results are good enough to justify moving to page inference

## Phase 5 - Page-Tile Inference

### Script

`scripts/infer_pages.py`

### Goal

Run the trained cloud detector on full drawing pages without requiring delta
detection.

### Flow

- load rendered drawing page
- tile page into overlapping windows
- run detector on each tile
- map tile detections back to page coordinates
- merge duplicates via NMS
- save crops and overlays

### Required Detection Output

`outputs/detections/<pdf_stem>.json`

Each page entry should include:
- `pdf`
- `page`
- `detections`

Each detection should include:
- `confidence`
- `bbox_page`
- `crop_path`
- `source_mode`

`source_mode` must be one of:
- `roi_bootstrap`
- `page_tile`

### Acceptance

- the model can find clouds on held-out full pages
- page inference does not require delta runtime dependency
- output is good enough to feed later pipeline integration

## Phase 6 - Optional Synthetic Phase

Synthetic generation is explicitly phase 2 work, not a blocker.

Only add it if:
- the real ROI baseline underperforms
- false positives cluster on recurring confounders
- recall is too low on held-out full-page inference

If added, synthetic generation should use:
- real cloud crops
- real blueprint backgrounds
- real hard negatives
- ROI-shaped scenes first, not arbitrary fantasy layouts

## Output Contract for Later Integration

CloudHammer's later consumer will likely be the main app's cloud-region
model.

For compatibility, every final page detection must be convertible into:
- page bbox `[x, y, w, h]`
- crop image path
- confidence
- extraction method marker such as `cloudhammer-yolo`

That is enough to feed downstream deliverable logic later.

## Tests

### Unit Tests

- page classification
- page-to-ROI coordinate round-trip
- tile-to-page coordinate round-trip
- delta manifest normalization
- ROI clipping at page borders
- merge/NMS behavior across overlapping tiles

### Integration Tests

- corpus catalog smoke test
- delta bootstrap smoke test
- ROI extraction smoke test
- 1-epoch training smoke test
- held-out page inference smoke test

### Acceptance Criteria

- old heuristic cloud outputs are not used anywhere
- delta stack is wrapped as a reproducible bootstrap step
- first detector works on held-out real drawing pages
- page-tile inference works without delta dependency
- JSON plus overlay artifacts are strong enough for human review and later
  integration

## Assumptions

- old cloud candidates are invalid and ignored
- the delta stack is good enough to accelerate the first dataset
- delta detection should not remain a required runtime gate
- bounding boxes are sufficient for v1
- no new review UI is required in v1
- precision matters more than perfect recall for the first credible demo

## Immediate First Milestone

1. Catalog drawing pages from `revision_sets/`.
2. Wrap the delta stack into one bootstrap command.
3. Extract cloud candidate ROIs.
4. Manually label only real `cloud_motif` instances in the first cloud ROI set.
5. Train the first ROI detector.
6. Run inference on held-out ROI pages.
7. Graduate to page-tile inference on a small held-out page set.
8. Save JSON and debug overlays suitable for later pipeline wiring.

## Cleanup Notes

While CloudHammer is being built, keep the repo clean enough that future work
does not accidentally depend on junk:
- keep legacy delta dependencies documented explicitly
- keep the old heuristic cloud outputs out of every training path
- keep reference/source artifacts under `docs/anchors/` instead of repo root
- make CloudHammer self-contained rather than spreading new code across the
  old experiment tree
