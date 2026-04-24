# CloudHammer Labeling Workflow

Status: `Current source of truth for human labeling and reviewed-label rules.`

## Directory Roles

- images to review live in `data/cloud_roi_images`
- API guesses live in `data/api_cloud_labels_unreviewed`
- reviewed labels live in `data/cloud_labels_reviewed`

Only `data/cloud_labels_reviewed` is training truth.

## Labeling Rules

- one YOLO class only: `cloud_motif`
- label all visible real cloud motifs in the crop
- revision triangles and revision digits stay unlabeled
- a crop may contain multiple clouds; label each real cloud
- include bold, faint, intersected, and partial clouds when they are real
- marker ROIs are context only and are not the target class

## Partial / Clipped Cloud Guidance

- if the crop clearly contains part of a real cloud, label the visible portion
- if the crop only shows ambiguous noise or a non-cloud artifact, leave it unlabeled
- when in doubt, prefer consistent human review over preserving an API guess

## Open Labeling Policy Question

- Some crops contain many small repetitive clouds that appear to mark the same
  copied/detail element. Decide whether these should be reviewed as separate
  `cloud_motif` instances, merged into a larger local group, or treated as a
  special case for training balance. Until this is resolved, label each distinct
  visible real cloud motif and note dense-repeat cases during review.

## LabelImg

Use:

- image directory: `data/cloud_roi_images`
- save directory: `data/cloud_labels_reviewed`
- format: YOLO

Copy prelabels into the reviewed directory first with:

```powershell
python scripts/prepare_labelimg_review.py
```
