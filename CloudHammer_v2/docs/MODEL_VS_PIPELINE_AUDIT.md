# Model vs Pipeline Audit

Purpose: determine what intelligence lives inside the YOLOv8 detector and what
is handled by surrounding CloudHammer pipeline logic.

## Completed Audit

Audit report:

`CloudHammer_v2/docs/MODEL_VS_PIPELINE_AUDIT_REPORT_2026_05_02.md`

Result: the latest legacy checkpoint is a useful continuity model, not a
promoted model. The model detects `cloud_motif` fragments/crops. The pipeline
adds grouping, confidence recalculation, crop logic, policy routing, human
review/release behavior, and backend manifest ingestion. The latest checkpoint
was trained before the source-controlled split became the active standard and
must not be promoted without frozen page-disjoint full-page eval.

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

## Experiment Lessons To Preserve

Approved lessons from
`docs/archive_cleanup_audits/experiments_retention_review_2026_05_02.md`:

- Delta/marker outputs are context and dataset-selection metadata, not proof
  that a revision cloud exists.
- If marker logic is imported later, prefer geometry-first marker detection.
  Text/digit association should be secondary metadata so the model does not
  learn a shortcut from nearby revision digits.
- Delta-specific denoising can help marker bootstrapping, but it is not general
  cloud reasoning and must not be treated as model evidence.
- Marker/delta context may seed review queues, crop selection, and training
  candidates only after leakage checks. It must not silently rescue, suppress,
  or re-score detections in promotion metrics.
- Stamp/circle/scallop geometry is useful as a diagnostic and hard-negative
  source for arcs, fixture circles, glyphs, and partial scallops. It should not
  be imported as core inference without a separate audit.
- Index-page parsing belongs primarily to the application/backend workflow.
  CloudHammer_v2 should only consume page-selection implications where they
  affect eval, training hygiene, or page exclusion.

## Source And Style Hypothesis

Observed correction: cloud stroke style should be tracked as visual diagnostic
metadata. Discipline, company/EOR, source family, and drawing set should be
tracked separately where known.

- Different drawing sets may come from different disciplines and different
  companies/EORs.
- A company/EOR may provide multiple stamped disciplines, so company and
  discipline are not interchangeable labels.
- Cloud style may be internally consistent within a given source/PDF/revision
  family or drawing set.
- There is no confirmed universal rule that dark/thick or thin/light clouds
  always correspond to one discipline, company, or EOR.
- Stroke thickness alone cannot prove a valid revision cloud. The actual
  repeated scalloped `cloud_motif` must be present.

The audit should verify style family per source/PDF/revision group and report
coverage by visual stroke style, source family, discipline, company/EOR, and
drawing set where known. It should also check whether false positives cluster
around dense dark linework, door swings/arcs, symbols, pipe/duct/conduit-like
linework, rounded technical geometry, or other style-specific distractors.

This should inform hard-negative mining. Candidate source/style-specific
negatives include:

- source-family pages with no clouds
- dense dark technical linework
- door swings and isolated arcs
- symbols, fixture circles, and glyph arcs
- pipe/duct/conduit-like runs
- valve or equipment clusters where present
- rounded dark linework
- dense annotation clusters

Keep the primary YOLO class as `cloud_motif`. Do not split classes by source
family, discipline, or stroke thickness unless a future audited decision is
supported by sufficient data volume and eval evidence.

## Import Boundary

Do not import experiment code into CloudHammer_v2 during this audit. Candidate
imports must first be classified as one of:

- training/review selection metadata
- eval bucket generation
- diagnostic-only tooling
- post-model pipeline logic

Any future import from old experiments or legacy `CloudHammer/` must be logged
in `CloudHammer_v2/IMPORT_LOG.md`.

## Output

Produce a short report that states what the model was trained on, what the
pipeline adds after detection, and which pipeline lessons should become labels,
hard negatives, or eval cases.
