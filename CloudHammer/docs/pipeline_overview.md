# CloudHammer Pipeline Overview

Status: `Current source of truth for the CloudHammer pipeline stages.`

CloudHammer is the CV/model pipeline for revision-cloud detection.

## Stages

1. Page cataloging and rasterization
   - `scripts/catalog_pages.py`
   - builds a page manifest and rasterized drawing pages
2. Marker-context extraction
   - `scripts/run_delta_bootstrap.py`
   - `scripts/extract_delta_rois.py`
   - uses legacy delta-marker output only as context, not as the target
3. Cloud ROI generation
   - `scripts/extract_cloud_rois.py`
   - creates candidate cloud crops for review/training
4. API prelabeling
   - `scripts/prelabel_cloud_rois_openai.py`
   - writes machine guesses into unreviewed API-label folders
5. Human review in LabelImg
   - `scripts/prepare_labelimg_review.py`
   - reviewer corrects labels in `data/cloud_labels_reviewed`
6. YOLO training
   - `scripts/train_roi_detector.py`
   - trains only from reviewed labels
7. Inference and review loop
   - `scripts/infer_pages.py`
   - runs the trained model on pages and produces model outputs for later backend integration

## Terminology

- `revision_marker`: numbered triangle/delta marker on the drawing
- `cloud_motif`: the actual revision cloud / scalloped boundary target
- marker ROI: context crop around revision markers
- cloud ROI: candidate training/review crop that may contain a cloud
- unreviewed labels: API guesses only
- reviewed labels: human-corrected training truth

## Ownership Boundary

CloudHammer owns model data prep, training, and inference.

CloudHammer does not own:

- deliverable Excel generation
- workspace review state
- revision tracking
- the broader web app
