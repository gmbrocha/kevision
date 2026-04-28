# CloudHammer Handoff

CloudHammer is the cloud-detector subproject inside `KEVISION`.

Its job is narrow:
- detect revision clouds on real blueprint pages
- save cloud crops
- save visual debug overlays
- emit machine-readable detections that the main pipeline can consume later

It is not responsible for:
- OCR/detail extraction
- Excel/export wiring
- review UI
- rescuing the old OpenCV cloud candidates

## Current Decisions

- Treat the existing heuristic cloud candidates and their crops as junk. They
  are excluded from training, validation, and pseudo-labeling.
- Use the real drawing PDFs under `revision_sets/` as the corpus. Current repo
  inventory is about `301` likely drawing pages once obvious narrative/spec
  PDFs are excluded.
- Use the delta stack only as optional context for dataset creation. Delta
  markers/digits can seed large nearby search windows, but the target remains
  the scalloped cloud motif and delta detection must not become a runtime gate.
- Use only the current revision set's marker digit as a strong seed by default.
  Older marker digits are context/debug negatives, not primary cloud candidates.
- Keep YOLO one-class: `cloud_motif`. Crops may contain multiple clouds; label
  all visible real cloud motifs, including thin/faint, intersected, partial, and
  bold examples. Leave triangles and digits unlabeled.
- API-assisted labels are prelabels only. They live under
  `data/api_cloud_labels_unreviewed`, with raw predictions in
  `data/api_cloud_predictions/predictions.jsonl` and review overlays in
  `data/api_cloud_review`. Do not overwrite human-reviewed labels with these.
- If an active prelabel run is in progress, treat the live API output folders as
  hands-off until the run completes.
- LabelImg review uses `data/cloud_roi_images` as the image directory and
  `data/cloud_labels_reviewed` as the YOLO save directory. Copy only `.txt`
  prelabels into the reviewed directory before correcting.
- Start with real labeled data first. Synthetic generation is phase 2 only if
  the real-data baseline underperforms.
- CloudHammer v1 ends at cloud detections: JSON, page-space boxes, crops, and
  overlays.

## Delta Bootstrap Dependency Chain

The bootstrap dependency is not just `delta_v4`.

CloudHammer needs to treat this full stack as the legacy delta adapter:
- `experiments/delta_v3/denoise_1.py`
- `experiments/delta_v3/denoise_x.py`
- `experiments/delta_v3/denoise_2.py`
- `experiments/delta_v4/detect.py`
- `experiments/2026_04_delta_marker_detector/detect_deltas.py`

Important constraints:
- `delta_v4/detect.py` expects a denoised grayscale search image on disk.
- It does not run the `delta_v3` denoise stages internally.
- It uses the source PDF separately for text-layer digit attachment.

## Output Contract

CloudHammer v1 should emit:
- page-space cloud bounding boxes
- crop image paths
- confidence scores
- debug overlays
- JSON manifests per source PDF

These outputs should later be convertible into the main app's cloud-region
model without redesign.

## Immediate Milestone

1. Catalog the drawing-bearing pages in `revision_sets/`.
2. Wrap the delta stack into one reproducible bootstrap command.
3. Extract cloud candidate ROIs from rendered drawing pages, excluding
   index/cover/non-drawing sheets and using marker windows only as context.
4. Manually label the first cloud ROI set with `cloud_motif` boxes only.
5. Optionally use OpenAI vision prelabels as a review accelerator.
6. Train the first ROI detector.
7. Run held-out ROI inference.
8. Graduate to tiled full-page inference so cloud detection does not require
   delta runtime gating.
9. Save JSON and overlays that are clean enough to plug into the later
   deliverable pipeline.

## Reference

The detailed implementation spec lives in [PROJECT_PLAN.md](PROJECT_PLAN.md).
