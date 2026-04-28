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

## Odd Shape / Attached Note Guidance

- for an L-shaped or otherwise non-rectangular cloud, use one rectangle around
  the visible cloud motif unless the pieces are truly separate disconnected
  clouds
- it is acceptable for the box to include unrelated drawing content inside the
  empty part of an L-shaped cloud
- very rarely, a label/note outside the cloud belongs to the clouded change by a
  leader arrow pointing into the cloud; keep the training label focused on the
  cloud motif itself, and treat the outside note as downstream context to
  capture during change extraction
- examples include equipment/detail tags outside the cloud, such as `A5110A` or
  `A5109B`, using a standard skinny leader arrow to point at equipment, handrail,
  grab bar, or other scope inside the cloud

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

For reviewed negatives:

- do not create a fake `negative_cloud` box or class
- if an image has no real cloud boxes, press `Ctrl+S` before moving on
- the patched local LabelImg writes an empty `.txt` label plus a
  `.review.json` sidecar marker, which records that the empty label is a real
  reviewed negative
- manifest/resume scripts treat either a newer reviewed label or a
  `.review.json` sidecar as reviewed

Copy prelabels into the reviewed directory first with:

```powershell
python scripts/prepare_labelimg_review.py
```
