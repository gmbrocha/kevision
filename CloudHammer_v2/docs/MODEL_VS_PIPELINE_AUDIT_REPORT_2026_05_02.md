# Model vs Pipeline Audit Report - 2026-05-02

Status: completed read-only audit. No legacy code was imported into
CloudHammer_v2.

## Executive Conclusion

The current CloudHammer detector is a YOLOv8 detection model trained to detect
`cloud_motif` boxes on crops and tiled full-page images. It is not, by itself,
a complete product-grade whole-cloud system.

The surrounding legacy CloudHammer pipeline adds substantial behavior after the
model:

- tiled full-page inference and page-coordinate mapping
- NMS
- fragment grouping into whole-cloud candidates
- overmerge splitting/refinement heuristics
- whole-cloud confidence recalculation
- crop margin and size-bucket logic
- review/export policy buckets
- release routing and human-review overrides
- tightened crop export
- backend manifest ingestion and workbook export

Therefore, `model_only_tiled` and `pipeline_full` must be evaluated separately.
The latest available checkpoint is useful for diagnosis, but it is not promoted
because it was trained before the source-controlled split became the active
standard and has not been measured against frozen page-disjoint full-page truth.

## Latest Model Lineage

Current latest model-facing checkpoint:

- Run: `CloudHammer/runs/cloudhammer_roi-symbol-text-fp-hn-20260502`
- Weights: `CloudHammer/runs/cloudhammer_roi-symbol-text-fp-hn-20260502/weights/best.pt`
- Base weights: `CloudHammer/runs/cloudhammer_roi-marker-fp-hn-20260502/weights/best.pt`
- Task: YOLOv8 `detect`
- Input size: `640`
- Epochs: `35`
- Batch: `16`
- Dataset: `CloudHammer/data/yolo_reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502`
- Manifest: `CloudHammer/data/manifests/reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`

Final validation metrics from the latest run:

- precision: `0.910`
- recall: `0.899`
- mAP50: `0.915`
- mAP50-95: `0.758`

These numbers are not promotion evidence because the validation split is not
source/page-family clean.

## Model Artifacts Inventory

Detected legacy checkpoints:

- `CloudHammer/runs/cloudhammer_roi/weights/best.pt`
- `CloudHammer/runs/cloudhammer_roi-2/weights/best.pt`
- `CloudHammer/runs/cloudhammer_roi-3/weights/best.pt`
- `CloudHammer/runs/cloudhammer_roi-hardneg-20260427/weights/best.pt`
- `CloudHammer/runs/cloudhammer_roi-broad-deduped-20260428/weights/best.pt`
- `CloudHammer/runs/cloudhammer_roi-marker-fp-hn-20260502/weights/best.pt`
- `CloudHammer/runs/cloudhammer_roi-symbol-text-fp-hn-20260502/weights/best.pt`

The latest checkpoint is the symbol/text hard-negative model above. It improved
reviewed hard-negative crop behavior, but it has not passed the CloudHammer_v2
real full-page eval gate.

## Label And Class Audit

Training labels support one class only:

- Class id: `0`
- Class name: `cloud_motif`

`CloudHammer/cloudhammer/data/yolo.py` validates YOLO labels and rejects class
IDs other than `0`. VOC XML conversion ignores non-`cloud_motif` objects.
Triangles, revision digits, sheets, notes, and other context objects are not
training classes.

## Latest Training Data Audit

The latest training manifest reports:

- total rows: `931`
- cloud-positive rows: `639`
- empty-label negative rows: `292`
- split rows: `715` train, `216` val
- training source mix:
  - `base_manifest`: `723`
  - `review_queue`: `170`
  - `marker_fp_hard_negative`: `29`
  - `eval_symbol_text_fp_hard_negative`: `9`

Materialized YOLO dataset counts:

- images: `714` train, `215` val
- labels: `714` train, `215` val
- positive label files: `639`
- empty label files: `290`
- total boxes: `1217`

The manifest has `931` rows but the materialized dataset has `929` image/label
pairs because two image basenames occur twice and are overwritten during YOLO
dataset creation:

- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3_p0004_whole_003_medium.png`
- `Revision_1_-_Drawing_Changes_6cbee960_p0001_whole_003_medium.png`

This needs a guard before the next training run: dataset export should fail on
duplicate output basenames or namespace copied images.

## Source And Leakage Audit

The current reviewed training manifest is not clean enough for promotion
measurement:

- rows: `931`
- source families: `12`
- source pages: `157`
- mixed train/val/test source families: `6`
- mixed train/val/test source pages: `47`
- current 14-page full-page eval overlaps training source pages on `12 / 14`
  pages

The source-controlled manifest fixes the split, but has not been used for a
training run yet:

- manifest: `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.jsonl`
- rows after caps: `502`
- split: `397` train, `105` val
- positives: `348`
- negatives: `154`
- leakage failures: `0`
- quasi-holdout manifest:
  `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.quasi_holdout.jsonl`
- quasi-holdout rows: `30`

Conclusion: the latest trained model is a useful continuity checkpoint, but the
next legitimate training/eval cycle should start from source-controlled splits
and frozen full-page eval pages.

## Crop Selection And Training Signal

Marker/delta logic affects legacy training data selection heavily:

- `delta_stack.py` imports legacy experiment code to detect revision markers.
- `roi_extract.py` extracts square marker ROIs from active deltas.
- `cloud_roi_extract.py` expands marker neighborhoods into candidate cloud
  crops, filters old/nonmatching revision markers, derives target revision
  digits, computes ink ratio and cloud-likeness, and writes crop manifests.
- GPT prelabels and human review then turn selected crops into YOLO labels.

This is acceptable as dataset selection metadata only. Marker/delta detections
are not a YOLO class and should not be treated as proof of a cloud.

Random drawing crops, whole-cloud candidate crops, and reviewed hard negatives
also feed the training manifests. GPT labels are used as accelerators, but only
reviewed labels or reviewed empty labels should enter training truth.

## `model_only_tiled` Boundary

The audited legacy model-only path is:

- `CloudHammer/cloudhammer/infer/detect.py`
- `CloudHammer/scripts/infer_pages.py`

Behavior:

- load YOLOv8 detector
- read rendered full-page grayscale image
- tile page with `tile_size=1280`, `tile_overlap=192`
- convert each tile to BGR for YOLO
- run `model.predict`
- map tile boxes back to page coordinates
- clip boxes to page bounds
- run NMS with `nms_iou=0.5`
- write per-page detection manifests and raw crops/overlays

This path does not use marker/delta context, fragment grouping, candidate
policy, manual review, release decisions, crop tightening, or backend export.

CloudHammer_v2 should implement `model_only_tiled` as this minimal behavior:
YOLO tiled full-page inference plus coordinate mapping and NMS only.

## `pipeline_full` Boundary

The audited legacy pipeline behavior is a composition of multiple steps, not a
single clean subsystem yet:

- tiled detection: `infer_pages.py`
- fragment grouping: `group_fragment_detections.py`
- whole-cloud candidate export: `export_whole_cloud_candidates.py`
- candidate policy: `candidate_policy.py`
- release routing: `candidate_release.py`
- crop tightening: `crop_tightening.py`
- review tools and split-review tools
- backend manifest bridge: `backend/cloudhammer_client/inference.py`

The pipeline adds meaningful intelligence:

- groups motif fragments into larger candidates
- recalculates confidence from member count, max confidence, mean confidence,
  and page-span penalty
- classifies confidence tiers and size buckets
- routes likely false positives, split-risk candidates, auto-deliverable
  candidates, and human-reviewed overrides
- filters rejected/quarantined rows before backend ingestion
- scales candidate boxes into backend sheet coordinates
- provides placeholder text until OCR/scope extraction is wired

This means `pipeline_full` can improve or degrade results independently from
model quality. It must be measured separately from `model_only_tiled`.

## Marker/Delta Logic Inference Boundary

Core full-page tiled inference and fragment grouping do not require marker/delta
context. Marker/delta logic appears in:

- dataset/crop bootstrapping
- review tooling
- split-review context
- experimental marker-anchor suppression scripts

CloudHammer_v2 should not silently include marker/delta suppression or rescue
logic in the baseline. If marker/delta context is later used, it must be
classified explicitly as metadata, eval bucket generation, diagnostic tooling,
or post-model pipeline logic.

## Current Eval Evidence

The 14-page eval remains a debug regression set only.

Marker-FP model on the 14-page sample:

- fragments: `101`
- grouped candidates: `38`
- reviewed candidates: `38`
- accepted: `21`
- false positives: `9`
- partial: `6`
- overmerged: `2`

Symbol/text-FP model on the same sample:

- fragments: `81`
- grouped candidates: `34`
- high-confidence candidates: `28`
- medium-confidence candidates: `5`
- low-confidence candidates: `1`

Hard-negative crop checks improved:

- marker-FP model: `0 / 29` marker false-positive crops hit at confidence
  `0.50`, but `3 / 9` symbol/text eval false positives still hit at confidence
  `0.25`
- symbol/text-FP model: `0 / 29` marker false-positive crops and `0 / 9`
  symbol/text false-positive crops hit even at confidence `0.10`

But the latest full-page comparison also warned:

- all `9 / 9` prior reviewed false positives were removed from crop containment
- only `19 / 21` prior reviewed accepts were retained by crop containment
- manual large-cloud audit dropped from `15` matched labels to `12`

Conclusion: hard-negative behavior improved, but the latest model is not
promotable without frozen full-page truth and recall checks.

## Backend Boundary

The backend currently consumes precomputed CloudHammer release manifests through
`ManifestCloudInferenceClient`. It does not run YOLO.

Backend behavior:

- filters rows rejected by review/policy/release fields
- scales CloudHammer page-space boxes into backend sheet coordinates
- emits `CloudDetection` records with `extraction_method=cloudhammer_manifest`
- creates visual-region change items
- can auto-approve CloudHammer manifest detections for preview export

This is application integration, not model intelligence.

## Audit Decisions

- Treat the latest symbol/text hard-negative model as the current continuity
  checkpoint, not a promoted model.
- Do not resume training from the `931`-row leaked manifest unless explicitly
  doing a continuity comparison.
- Use source-controlled splits for the next clean baseline/training path.
- Fix duplicate image basename handling before any new training dataset export.
- Implement frozen `page_disjoint_real` before training or synthetic generation.
- Evaluate `model_only_tiled` and `pipeline_full` against the same frozen
  full-page labels.
- Keep marker/delta context out of promotion metrics unless it is explicitly
  part of the named `pipeline_full` variant being tested.

## Recommended Next Step

Build the touched-page registry and freeze guards, then select
`page_disjoint_real`. The audit found enough pipeline complexity and training
leakage that more training before the frozen eval ruler would be misleading.
