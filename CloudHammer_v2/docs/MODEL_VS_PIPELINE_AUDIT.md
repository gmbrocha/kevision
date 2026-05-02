# Model vs Pipeline Audit

Purpose: determine what intelligence lives inside the YOLOv8 detector and what
is handled by surrounding CloudHammer pipeline logic.

## Audit Checklist

- Confirm model architecture and task:
  - YOLOv8
  - detection, not segmentation
  - model input size and training config
- Confirm labels:
  - class names
  - class IDs
  - whether only `cloud_motif` is labeled
  - whether triangles, markers, sheets, notes, or other cues are labeled
- Inventory model artifacts:
  - trained checkpoints
  - dataset YAMLs/configs
  - generated datasets
- Inventory data statistics:
  - train image count
  - val image count
  - label count
  - empty-label hard-negative count
  - hard-negative bucket counts
- Check leakage:
  - source-family leakage
  - source-page leakage
  - train/val split policy
- Audit crop selection:
  - random page crops
  - delta-based ROIs
  - marker/triangle-based ROIs
  - manually curated crops
  - GPT-assisted crops
  - reviewed labels only
- Determine whether triangle/marker/delta logic affected:
  - training data selection
  - label creation
  - inference
  - post-processing
  - grouping/filtering/export
- Separate:
  - model input/training signal
  - post-model procedural logic

## Output

Produce a short report that states what the model was trained on, what the
pipeline adds after detection, and which pipeline lessons should become labels,
hard negatives, or eval cases.
