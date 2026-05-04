# ROI / Crop / Review Candidate Selection Audit - 2026-05-03

Status: report-only audit. No code, labels, manifests, datasets, model files,
eval files, or existing docs were modified. This file is the only intended
deliverable.

## Executive Summary

Legacy CloudHammer training and review data is strongly candidate-conditioned.
Most human review did not start from exhaustive full-page truth. It started from
selected crops and whole-cloud candidates produced by a mix of:

- delta/triangle marker detection
- target revision marker proximity
- marker-neighborhood crop expansion
- GPT crop prelabels and GPT confidence/status buckets
- YOLO tiled full-page predictions
- fragment grouping and whole-cloud candidate confidence
- targeted review of false positives and overmerged candidates
- later random drawing crops and source-capped expansion batches

That means prior human review is useful, but it is not representative of every
cloud on every page. Valid clouds could have been missed if they were never near
a detected marker, never selected as a random crop, never produced by YOLO, or
never surfaced by GPT/model review queues.

The current CloudHammer_v2 pivot correctly addresses this by freezing full-page
eval truth (`page_disjoint_real`) and keeping the touched style-balance set as a
diagnostic supplement rather than a promotion-clean holdout.

Highest-risk bias found:

- marker/delta proximity bias in early crop selection
- model-confidence bias in whole-cloud candidate review
- GPT-confidence/status bias in crop review queues
- duplicate/source-family imbalance in older reviewed manifests
- row-level and page-group split leakage in older training manifests
- undercoverage of full-page missed-cloud cases, especially clouds never selected
  as candidates
- discipline/style imbalance, including plumbing/electrical/MEP thick-linework
  false-positive traps and faint/thin architectural/general recall cases

## Bottom-Line Answer

Yes: prior human review was likely biased by ROI selection, model confidence,
delta logic, marker/triangle proximity, and duplicate-heavy source selection.
The bias is not fatal for training, but it is fatal for treating old validation
or crop-review accept rates as real-world performance.

Use old reviewed crops as training signal and hard-negative history. Use
CloudHammer_v2 full-page human truth as the ruler.

## Scripts And Configs Inspected

### Legacy Bootstrap And Crop Generation

| Path | Role |
| --- | --- |
| `CloudHammer/cloudhammer/bootstrap/delta_stack.py` | Wraps legacy delta/triangle detector and writes normalized delta payloads. |
| `CloudHammer/scripts/run_delta_bootstrap.py` | CLI for delta bootstrap over drawing pages. |
| `CloudHammer/cloudhammer/bootstrap/roi_extract.py` | Extracts marker-centered ROI crops from active delta payloads. |
| `CloudHammer/scripts/extract_delta_rois.py` | CLI wrapper for marker ROI extraction. |
| `CloudHammer/cloudhammer/bootstrap/cloud_roi_extract.py` | Builds larger candidate cloud crops around revision markers. |
| `CloudHammer/scripts/extract_cloud_rois.py` | CLI wrapper for cloud ROI extraction. |
| `CloudHammer/scripts/create_random_drawing_crops.py` | Creates random drawing-area crops for broader review/prelabel coverage. |
| `experiments/2026_04_delta_marker_detector/detect_deltas.py` | Early contour/text delta-marker detector. |
| `experiments/delta_v3/*.py` | Delta-denoising experiments used by the wrapped legacy stack. |
| `experiments/delta_v4/detect.py` | Geometry-first delta-marker detector. |

### GPT Prelabel And Review Queue Generation

| Path | Role |
| --- | --- |
| `CloudHammer/scripts/prelabel_cloud_rois_openai.py` | CLI for GPT crop prelabeling. |
| `CloudHammer/cloudhammer/prelabel/openai_clouds.py` | GPT crop prompt, validation, label writing, overlays. |
| `CloudHammer/scripts/create_review_batches.py` | Builds early review batches from GPT predictions. |
| `CloudHammer/scripts/build_gpt_review_queues.py` | Builds isolated LabelImg queues from GPT prediction buckets. |
| `CloudHammer/cloudhammer/prelabel/gpt_review_queue.py` | GPT queue classification and balancing logic. |
| `CloudHammer/scripts/dedupe_gpt_manifest.py` | CLI for crop geometry dedupe before GPT/review. |
| `CloudHammer/cloudhammer/prelabel/manifest_dedupe.py` | Same-page crop IoU/overlap dedupe logic. |
| `CloudHammer/scripts/prepare_labelimg_review.py` | Copies prelabels into a LabelImg review workspace. |
| `CloudHammer/scripts/seed_review_batch_from_api_labels.py` | Seeds review labels from GPT output without marking reviewed. |
| `CloudHammer/scripts/launch_labelimg_batch.py` | Launches/resumes LabelImg for review batches. |
| `CloudHammer/scripts/launch_labelimg_resume.py` | Launches LabelImg at first unsaved reviewed crop. |
| `CloudHammer/scripts/launch_random_gpt_review_queue.py` | Launches LabelImg for random GPT review queues. |

### Whole-Page Inference And Whole-Cloud Candidate Flow

| Path | Role |
| --- | --- |
| `CloudHammer/cloudhammer/infer/detect.py` | YOLO tiled full-page inference with NMS. |
| `CloudHammer/scripts/infer_pages.py` | CLI wrapper for tiled inference. |
| `CloudHammer/cloudhammer/infer/fragment_grouping.py` | Groups nearby motif detections into whole-cloud candidates. |
| `CloudHammer/scripts/group_fragment_detections.py` | CLI wrapper for fragment grouping. |
| `CloudHammer/cloudhammer/infer/whole_clouds.py` | Whole-cloud confidence, crop margins, size buckets, candidate manifest rows. |
| `CloudHammer/scripts/export_whole_cloud_candidates.py` | Exports grouped candidates as reviewable crops/manifests. |
| `CloudHammer/cloudhammer/infer/candidate_policy.py` | Whole-cloud policy buckets by confidence/member/fill ratio. |
| `CloudHammer/cloudhammer/infer/candidate_release.py` | Release/review/quarantine routing after policy and human review. |
| `CloudHammer/scripts/build_whole_cloud_candidate_release.py` | Builds release and review queues from policy rows. |
| `CloudHammer/utilities/whole_cloud_candidate_reviewer.py` | Human review UI for whole-cloud candidate crops. |
| `CloudHammer/utilities/whole_cloud_split_reviewer.py` | Human review UI for overmerge/split candidates. |
| `CloudHammer/scripts/build_corrected_whole_cloud_candidate_manifest.py` | Replaces split parents with accepted split artifacts. |
| `CloudHammer/scripts/export_split_review_artifacts.py` | Exports crops from split-review decisions. |
| `CloudHammer/scripts/export_reviewed_whole_cloud_artifacts.py` | Exports accepted whole-cloud crops and feedback manifests. |
| `CloudHammer/scripts/tighten_whole_cloud_candidate_crops.py` | Tightens reviewed candidate crops after selection. |

### Hard Negatives And Source Controls

| Path | Role |
| --- | --- |
| `CloudHammer/scripts/analyze_whole_cloud_candidate_reviews.py` | Turns review logs into accepted/FP/partial/overmerged manifests. |
| `CloudHammer/scripts/export_marker_false_positive_hard_negatives.py` | Converts reviewed marker false positives into hard-negative candidates. |
| `CloudHammer/scripts/create_marker_fp_hard_negative_training_manifest.py` | Writes empty-label hard-negative training rows. |
| `CloudHammer/scripts/create_accept_contamination_label_review_batch.py` | Creates precise-label review for accepted crops with non-cloud contamination. |
| `CloudHammer/scripts/evaluate_hard_negative_hits.py` | Evaluates models against hard-negative crops. |
| `CloudHammer/scripts/create_combined_reviewed_manifest.py` | Combines base reviewed manifests and reviewed queues. |
| `CloudHammer/scripts/create_reviewed_training_manifest.py` | Early row-level reviewed training manifest builder. |
| `CloudHammer/scripts/build_source_split_manifest.py` | Rewrites reviewed manifests with source-controlled splits and caps. |
| `CloudHammer/scripts/audit_training_sources.py` | Audits source/page concentration and train/val/eval leakage. |
| `CloudHammer/cloudhammer/data/source_control.py` | Source/page/revision normalization, caps, source audit helpers. |
| `CloudHammer/cloudhammer/data/splits.py` | Stable hash split by PDF filename and 20-page group. |
| `CloudHammer/cloudhammer/data/yolo.py` | Materializes YOLO datasets from manifests. |

### CloudHammer_v2 Eval Pivot

| Path | Role |
| --- | --- |
| `CloudHammer_v2/scripts/build_touched_page_registry.py` | Builds touched-page registry and `page_disjoint_real` candidates. |
| `CloudHammer_v2/scripts/evaluate_fullpage_detections.py` | Full-page prediction-vs-label evaluator. |
| `CloudHammer_v2/scripts/generate_gpt_fullpage_labels.py` | GPT full-page provisional labels; scratch only for `page_disjoint_real`. |
| `CloudHammer_v2/configs/baseline_page_disjoint_real_20260502.yaml` | Baseline inference config. |
| `CloudHammer_v2/configs/gpt55_crop_prelabel_small_corpus_supplement_20260502.yaml` | GPT-5.5 cropped supplement prelabel config. |
| `CloudHammer_v2/eval/page_disjoint_real/*` | Frozen full-page eval candidates and human-audited truth. |
| `CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/*` | Touched-real style-balance diagnostic review set. |

## ROI / Crop Generation Flow

### 1. Delta Bootstrap

Primary files:

- `CloudHammer/cloudhammer/bootstrap/delta_stack.py`
- `CloudHammer/scripts/run_delta_bootstrap.py`
- `experiments/delta_v4/detect.py`
- `experiments/delta_v3/*.py`

Inputs:

- drawing-page manifest rows, usually `CloudHammer/data/manifests/pages.jsonl`
- source PDFs under `revision_sets/`
- optional target revision digit

Outputs:

- normalized delta JSON under `CloudHammer/data/delta_json/`
- legacy JSON under `CloudHammer/data/delta_json/legacy/`
- denoised/audit images under `CloudHammer/outputs/audit/`
- rebuilt `CloudHammer/data/manifests/delta_manifest.jsonl`

Selection logic:

- Processes drawing pages only.
- Runs denoising stages to suppress normal blueprint linework and preserve
  triangle-like geometry.
- Runs geometry-first delta detection, then attaches text digits after geometry
  has passed.
- Splits detected markers into active, historical, and geometry-only groups.

Signal use:

- Delta/change detection: yes, in the sense of revision marker detection.
- Marker/triangle logic: yes.
- Model predictions/confidence: no.
- Manual lists/manifests: page manifest and optional target digit only.

Bias risk:

- Strongly anchors downstream candidate generation to detected revision markers.
- Missed or misclassified markers can prevent related clouds from entering the
  crop/review universe.
- Denoising is useful for marker metadata but should not be treated as cloud
  evidence.

### 2. Marker-Centered Delta ROIs

Primary files:

- `CloudHammer/cloudhammer/bootstrap/roi_extract.py`
- `CloudHammer/scripts/extract_delta_rois.py`

Inputs:

- pages manifest
- delta JSON directory
- config `bootstrap.roi_size` default `1400`

Outputs:

- ROI images under `CloudHammer/data/roi_images`
- `CloudHammer/data/manifests/roi_manifest.jsonl`

Selection logic:

- Skips non-drawing pages and pages classified as index/cover.
- Iterates `active_deltas`.
- Creates one square crop around each marker center.
- Split assigned by `assign_split(pdf_path, page_index)`.

Signal use:

- Delta/change detection: yes.
- Marker/triangle logic: yes.
- Model predictions/confidence: no.
- Manual lists/manifests: page/delta manifests.

Bias risk:

- Produces marker-centered crops, not cloud-centered or page-representative
  crops.
- Clouds outside active marker neighborhoods are underrepresented.

### 3. Marker-Neighborhood Cloud ROIs

Primary files:

- `CloudHammer/cloudhammer/bootstrap/cloud_roi_extract.py`
- `CloudHammer/scripts/extract_cloud_rois.py`

Inputs:

- pages manifest
- marker manifest, default `roi_manifest.jsonl`
- delta JSON directory
- target revision digit or derived revision digit
- crop sizes and offsets

Key defaults:

- crop size: `1536`
- large crop size: `2048`
- crop offsets: center, left, right, up, down
- optional diagonals only with flag
- dedupe IoU: `0.82`
- blank ink-ratio threshold: `0.002`
- skip lower-right title-block markers by default

Outputs:

- cloud ROI images under configured `cloud_roi_images`
- cloud ROI manifests such as:
  - `CloudHammer/data/manifests/cloud_roi_manifest.jsonl`
  - `CloudHammer/data/manifests/cloud_roi_broad_candidates_20260427.jsonl`
  - `CloudHammer/data/manifests/cloud_roi_broad_allmarkers_20260427.jsonl`

Selection logic:

- Uses marker seeds from the marker manifest and delta payloads.
- Derives a target revision digit from the PDF/revision name when possible.
- By default keeps target-matching markers and skips old/nonmatching markers.
- Can include nonmatching markers when `--include-nonmatching-markers` is used.
- Skips title-block marker locations unless explicitly allowed.
- Generates neighborhood crops around each marker.
- Filters blank crops.
- Scores each crop with a hand-built `cloud_likeness_score` based on Canny
  edges, curved/short fragments, and Hough-line penalty.
- Dedupes same-page overlapping crops after sorting by cloud-likeness and ink.

Signal use:

- Delta/change detection: yes.
- Marker/triangle logic: yes.
- Model predictions/confidence: no.
- Manual lists/manifests: yes, via source page and marker manifests.

Bias risk:

- This is the most important legacy selection bias.
- The crop universe is marker-neighborhood-first, not page-first.
- Target revision filtering can underrepresent historical/nonmatching marker
  context.
- Title-block skip can remove true edge/title-area cases if they exist.
- Cloud-likeness scoring favors curved/scalloped local geometry and may also
  pull in fixture/symbol/arc false positives.

### 4. Random Drawing Crops

Primary file:

- `CloudHammer/scripts/create_random_drawing_crops.py`

Inputs:

- pages manifest, default `CloudHammer/data/manifests/pages.jsonl`
- rasterized page images

Key defaults:

- count: `200`
- crop size: `1024`
- seed: `20260424`
- min ink ratio: `0.002`
- drawing-area margins: left `0.04`, right `0.18`, top `0.06`, bottom `0.12`

Outputs:

- image crops
- `manifest.jsonl`
- CSV review sheet

Selection logic:

- Uses drawing pages only.
- Groups by revision and round-robins/randomly chooses pages.
- Randomly samples crop locations within a margin-trimmed drawing area.
- Accepts crops over the ink threshold, or falls back after max attempts.

Signal use:

- Delta/change detection: no.
- Marker/triangle logic: no.
- Model predictions/confidence: no.
- Manual lists/manifests: pages manifest.

Bias risk:

- Helps reduce marker bias, but is still crop-level and margin-trimmed.
- May exclude right/bottom/edge regions and title blocks.
- Same page can be sampled multiple times; no strong page-level dedupe.
- Rare clouds may still be missed by random sampling.

### 5. Model-Generated Whole-Cloud Candidates

Primary files:

- `CloudHammer/cloudhammer/infer/detect.py`
- `CloudHammer/scripts/infer_pages.py`
- `CloudHammer/cloudhammer/infer/fragment_grouping.py`
- `CloudHammer/scripts/group_fragment_detections.py`
- `CloudHammer/cloudhammer/infer/whole_clouds.py`
- `CloudHammer/scripts/export_whole_cloud_candidates.py`

Inputs:

- rendered full-page drawings
- YOLO checkpoint
- inference config

Key inference defaults:

- tile size: `1280`
- tile overlap: `192`
- confidence threshold: `0.5`
- NMS IoU: `0.5`

Grouping defaults:

- expansion ratio: `0.55`
- min padding: `120`
- max padding: `850`
- group margin ratio: `0.08`
- split/refinement thresholds based on member count, gap, and fill ratio

Whole-cloud candidate defaults:

- crop margin ratio: `0.12`
- min crop margin: `48`
- max crop margin: `650`
- minimum box side: `20`
- confidence tier cutoffs: high `>=0.82`, medium `>=0.65`, else low

Outputs:

- page-level detection JSON
- raw detection crops/overlays
- grouped whole-cloud candidate manifests
- candidate crops, overlays, contact sheets

Selection logic:

- Runs YOLO over page tiles.
- Maps tile predictions back to page coordinates.
- Applies NMS.
- Groups nearby motif-fragment boxes into larger whole-cloud candidates.
- Recalculates whole-cloud confidence from max confidence, mean confidence,
  member count, and page-span penalty.
- Exports candidates above configured thresholds.

Signal use:

- Delta/change detection: no for core tiled inference and grouping.
- Marker/triangle logic: no for core tiled inference and grouping.
- Model predictions/confidence: yes, primary selection source.
- Manual lists/manifests: pages and detection manifests.

Bias risk:

- Human review only sees model-produced candidates. If the model misses a cloud,
  it never enters this review flow.
- Low confidence thresholds help surface more candidates, but the universe is
  still bounded by model detections and grouping heuristics.
- Grouping can create overmerged or partial crops; those are review/cropper
  failure cases, not simple positive labels.

## Review Candidate Generation Flow

### GPT-Based Crop Review Batches

Primary files:

- `CloudHammer/scripts/prelabel_cloud_rois_openai.py`
- `CloudHammer/cloudhammer/prelabel/openai_clouds.py`
- `CloudHammer/scripts/create_review_batches.py`
- `CloudHammer/scripts/build_gpt_review_queues.py`
- `CloudHammer/cloudhammer/prelabel/gpt_review_queue.py`

GPT crop prelabel behavior:

- Default legacy model: `gpt-5.4`
- Prompt asks for `cloud_motif` boxes and explicitly rejects triangles, digits,
  text, title blocks, fixtures, doors/walls, symbols, and isolated arcs.
- Min confidence default: `0.60` in the legacy crop script.
- Rejects tiny boxes and boxes covering more than 85 percent of the image.
- Writes predictions JSONL, YOLO labels, and review overlays.

Early review batch logic:

- Source: GPT predictions over selected ROI/crop images.
- Buckets:
  - bold/easy positive
  - thin/faint positive
  - weird/partial/intersected
  - hard-negative no-cloud
  - common false-positive geometry
  - later
- Default target: 500 rows.
- Quotas favor a mixture of positives, weird cases, and negatives.
- Rows are sorted by GPT confidence, cloud-likeness, and ROI id.
- Dedupe is by `cloud_roi_id`, not by source page or crop geometry.

GPT review queue logic:

- Queue names:
  - `high_conf_positive`
  - `ambiguous_positive`
  - `weird_multi_faint_partial`
  - `hard_negative_marker_no_cloud`
  - `gpt_negative_spotcheck`
- Balanced selection groups by revision and candidate source.
- No strong geometry dedupe beyond row id in this stage.

Bias risk:

- GPT confidence/status affects what humans review.
- GPT false negatives can become empty-label candidates if not audited carefully.
- High-confidence GPT positives are overrepresented in some review flows.
- Weird/faint/partial positives are included, but only if GPT or metadata
  surfaced them.

### Balanced Small-Corpus Expansion Batches

Primary file:

- `CloudHammer/scripts/build_balanced_expansion_review_batch.py`

Observed outputs:

- `CloudHammer/data/review_batches/small_corpus_expansion_20260502/`
- `CloudHammer/data/review_batches/small_corpus_expansion_supplement_20260502/`

Inputs:

- random drawing crop manifests
- broad marker-neighborhood crop manifests
- whole-cloud eval candidate manifests
- temporary random GPT review queues
- existing reviewed manifests for exclusion

Default quotas:

- normal hard negative: `75`
- symbol/text false positive: `60`
- weird positive: `60`
- high-confidence positive: `60`
- large dense context: `45`

Default caps:

- max rows per source: `70`
- max rows per source page: `10`
- exclude quasi-holdout revisions by default: Rev 5 and Rev 7

Observed first 300-row expansion:

- selected rows: `300`
- selected buckets: `153` weird positive, `131` normal hard negative,
  `16` large dense context
- selected revisions: Rev 1 `80`, Rev 2 `96`, Rev 3 `83`, Rev 4 `41`
- skipped existing reviewed rows: `830`
- skipped quasi-holdout rows: `124`

Observed 150-row supplement:

- selected rows: `150`
- selected buckets: `87` normal hard negative, `60` weird positive,
  `3` large dense context
- selected revisions: Rev 1 `35`, Rev 2 `38`, Rev 3 `62`, Rev 4 `15`
- skipped existing reviewed rows: `990`
- skipped existing API labels: `1180`
- skipped quasi-holdout rows: `165`

Bias risk:

- This is much better than early ad hoc batches because it has caps and skips
  already reviewed/prelabeled rows.
- It still inherits the candidate universe from marker crops, whole-cloud model
  candidates, and random crops.
- Symbol/text and high-confidence quotas were often not filled by available
  candidates, so the actual selected mix can differ from intended quotas.

### Whole-Cloud Candidate Review

Primary files:

- `CloudHammer/scripts/launch_review_queue.ps1`
- `CloudHammer/utilities/whole_cloud_candidate_reviewer.py`
- `CloudHammer/scripts/analyze_whole_cloud_candidate_reviews.py`
- `CloudHammer/scripts/build_whole_cloud_candidate_release.py`

Inputs:

- whole-cloud candidate manifests
- policy/release queue manifests
- human review logs

Selection/routing logic:

- Candidate policy uses whole-cloud confidence, member count, and fill ratio.
- Very low confidence becomes likely false positive.
- high-member or low-fill groups become split-review risk.
- mid/high confidence modest groups can become auto-deliverable candidates.
- Human review overrides policy.
- Review order is often confidence ascending for targeted cleanup queues.

Bias risk:

- Review candidates already came from YOLO and grouping.
- Missed model detections are invisible.
- Whole-cloud confidence and grouping shape which errors humans see.

### Marker-Anchor False-Positive Review

Primary files:

- `CloudHammer/scripts/apply_marker_anchor_suppression.py`
- `CloudHammer/scripts/build_marker_anchor_retained_review_queue.py`
- `CloudHammer/scripts/export_marker_false_positive_hard_negatives.py`

Selection/routing logic:

- Marker-anchor analysis classifies candidates by relationship to nearby matching
  revision markers.
- Reviewed marker false positives are suppressed.
- Reviewed accept/partial/overmerged/uncertain rows are protected.
- Unreviewed original candidates in `no_near_matching_marker` can be suppressed
  if confidence is below `0.45`.
- Retained marker-risk buckets are queued for targeted review.

Bias risk:

- Useful for reducing marker-related false positives.
- If used silently in scoring, it would mix model performance with marker logic.
- CloudHammer_v2 should keep this out of `model_only_tiled` and make any future
  marker-aware pipeline variant explicit.

### Full-Page Human Review In CloudHammer_v2

Primary locations:

- `CloudHammer_v2/eval/page_disjoint_real/`
- `CloudHammer_v2/eval/page_disjoint_real_human_review/`
- `CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/`

Current status:

- `page_disjoint_real` froze `17` page-disjoint candidates from an eligible pool
  after excluding touched pages.
- Human-audited truth exists for `17` pages.
- Human-audited page count: `17`
- Total cloud boxes: `26`
- Pages with cloud boxes: `16`
- Empty truth pages: `1`
- Heuristic discipline guess: `12` plumbing, `2` electrical, `2` structural,
  `1` architectural/general.
- The touched style-balance diagnostic supplement has `12` pages, selected from
  low-touch pages with touch totals from `2` to `6`.

Bias risk:

- `page_disjoint_real` is cleanest available, but plumbing-heavy.
- `style_balance_diagnostic_real_touched_20260503` improves style coverage but is
  not promotion-clean because pages were already touched by prior workflows.

## Current Training Image Selection Flow

### Dataset YAMLs

Observed YOLO dataset YAMLs:

- `CloudHammer/data/yolo/cloudhammer.yaml`
- `CloudHammer/data/yolo_reviewed_batch_001/cloudhammer.yaml`
- `CloudHammer/data/yolo_reviewed_batch_001_002_plus_004partial_current_20260427/cloudhammer.yaml`
- `CloudHammer/data/yolo_reviewed_batch_001_002_004partial_plus_broad_deduped_20260428/cloudhammer.yaml`
- `CloudHammer/data/yolo_reviewed_plus_marker_fp_hard_negatives_20260502/cloudhammer.yaml`
- `CloudHammer/data/yolo_reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502/cloudhammer.yaml`

All observed YAMLs use:

- task data root: materialized YOLO images/labels
- train: `images/train`
- val: `images/val`
- test: `images/test`
- class `0: cloud_motif`

### YOLO Dataset Materialization

Primary files:

- `CloudHammer/cloudhammer/data/yolo.py`
- `CloudHammer/scripts/train_roi_detector.py`
- `CloudHammer/cloudhammer/train/trainer.py`

Behavior:

- Reads a manifest with `roi_image_path`, `label_path`, and `split`.
- Copies images into YOLO split folders.
- Converts VOC XML or validates YOLO TXT.
- Accepts class id `0` only.
- Missing labels become empty labels.
- Does not create splits or dedupe; it trusts the manifest.

Important risk:

- A missing or wrong `label_path` can become an accidental empty-label negative.
- Duplicate output basenames can overwrite materialized image/label pairs.

### Training Manifest Lineage

Legacy manifests include:

- early marker ROI manifests
- GPT-reviewed crop manifests
- broad deduped crop manifests
- whole-cloud accepted/split artifacts
- reviewed marker false-positive hard negatives
- reviewed symbol/text false-positive hard negatives

Latest continuity manifest:

- `CloudHammer/data/manifests/reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`
- rows: `931`
- positives: `639`
- empty-label negatives: `292`
- split rows: `715` train, `216` val
- training source mix:
  - base manifest: `723`
  - review queue: `170`
  - marker false-positive hard negatives: `29`
  - eval symbol/text false-positive hard negatives: `9`

Source-controlled manifest:

- `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.jsonl`
- rows after caps: `502`
- train: `397`
- val: `105`
- quasi-holdout rows: `30`
- leakage failures: `0`
- max rows per source: `150`
- max rows per source page: `15`

Split methods found:

- `create_reviewed_training_manifest.py` uses random row-level shuffle.
- `assign_split()` hashes PDF filename plus 20-page group.
- `create_combined_reviewed_manifest.py` preserves base splits and uses
  page-group hashing for queue rows.
- `build_source_split_manifest.py` rewrites to source-disjoint splits and source
  caps.

Bias/leakage risk:

- Older row-level splits can put same-source or same-page crop variants in both
  train and val.
- Page-group splits reduce some leakage but not source-family leakage across PDF
  stems/revisions.
- Source-controlled split is the correct standard for the next clean training
  cycle.

## Hard-Negative Selection Flow

Hard negatives entered training through several routes.

### GPT No-Cloud / Marker No-Cloud Crops

Source:

- GPT prediction queues and early review batches.

Selection:

- Crops with no accepted GPT boxes and `has_cloud=false`.
- Target marker-neighborhood no-cloud candidates become
  `hard_negative_marker_no_cloud`.

Risk:

- Negative truth is only as good as the human review or GPT/status audit.
- Marker no-cloud negatives are still marker-neighborhood negatives, not general
  no-cloud page coverage.

### Marker False-Positive Hard Negatives

Source:

- reviewed whole-cloud false positives from
  `whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428`

Observed summary:

- rows: `29`
- marker anchor bucket: `no_near_matching_marker`
- false-positive reasons:
  - repeating section scallop: `13`
  - text/glyph arcs: `5`
  - circular symbol/fixture: `1`
  - generic false positive: `10`

Selection:

- Only reviewed whole-cloud candidates marked false positive.
- Converted to empty labels with review sidecars.
- Split by page-group hash.

Risk:

- Highly useful but model/pipeline-selected.
- Does not cover no-cloud pages or regions that never became candidates.

### Symbol/Text False-Positive Hard Negatives

Source:

- reviewed false positives from
  `CloudHammer/runs/whole_cloud_eval_marker_fp_hn_20260502/review_analysis/false_positive_candidates.jsonl`

Observed summary:

- rows: `9`
- false-positive reasons:
  - circular symbol/fixture: `5`
  - text/glyph arcs: `4`

Risk:

- Very focused and valuable, but small.
- Selected from a specific eval candidate run, not broad no-cloud coverage.

### Accepted-Crop Contamination Review

Source:

- accepted whole-cloud candidates tagged with non-cloud contamination.

Purpose:

- Force precise labels around true cloud motif while excluding nearby door swing
  arcs, plan geometry arcs, fixture circles, text curves, seals, and other
  non-cloud geometry.

Risk:

- Good guard against training boxes becoming too loose.
- Still based on accepted model/pipeline candidate crops.

### MEP / Utility Dense-Linework Coverage

Current status:

- Plumbing/electrical/MEP dense linework is now documented as an important
  diagnostic/hard-negative context.
- Older hard negatives include some symbol/fixture/text/arc cases, but the audit
  did not find a broad, systematic no-cloud utility/MEP dense-linework mining
  process in legacy training selection.

Recommendation:

- Mine utility/MEP no-cloud dense-linework crops only from human-confirmed no-cloud
  regions or full-page truth regions that exclude real clouds.

## Full-Page Coverage Assessment

Legacy CloudHammer has full-page inference, but prior review was usually
candidate/crop review, not exhaustive full-page labeling.

Full-page pieces found:

- YOLO tiled full-page inference.
- Full-page rendered overlays.
- Whole-cloud grouping/export from full-page predictions.
- Debug full-page eval samples.
- Candidate review over crops generated from full-page predictions.

What was missing before CloudHammer_v2:

- A frozen full-page human truth set with labels for every real cloud and empty
  labels for true no-cloud pages.
- A clean rule preventing eval pages from entering training, crop mining,
  synthetic backgrounds, threshold tuning, GPT relabel loops, or future mining.

Current CloudHammer_v2 correction:

- `page_disjoint_real` now has human-audited full-page truth.
- Accidental GPT full-page labels are provisional scratch and must not be scored
  as truth.
- The style-balance touched-real set is diagnostic-only and should not be blended
  with promotion-clean eval metrics.

Prior review could miss valid clouds:

- yes, if the cloud was outside selected marker crops
- yes, if the marker detector missed the marker
- yes, if the cloud was not in a random crop
- yes, if YOLO failed to detect enough motifs to create a whole-cloud candidate
- yes, if grouping/crop export created only partial or overmerged candidates that
  were not resolved into full truth

## Triangle / Marker / Delta Signal Map

| Phase | Signal Use |
| --- | --- |
| Before training / crop selection | Heavy use. Delta/triangle detection creates marker seeds; marker neighborhoods create many crop candidates. |
| Review candidate generation | Heavy use in marker-neighborhood GPT queues and marker-anchor false-positive review. |
| Training labels/classes | Not a class. Training labels remain one class: `cloud_motif`. |
| Model-only tiled inference | No marker/delta use in the audited core path. |
| Fragment grouping | No marker/delta use in core geometry grouping. |
| Post-model procedural logic | Marker-anchor suppression/review exists in legacy scripts and must be treated as pipeline logic if used. |
| Export/release routing | Review/policy/release can include marker-derived context via prior manifests, but backend export consumes final candidate manifests. |
| Currently inactive / not baseline | Any marker-aware suppression or rescue should stay outside CloudHammer_v2 baseline scoring unless explicitly named as a pipeline variant. |

Key rule:

Delta/marker context can seed metadata, crop selection, and targeted review, but
it must not be treated as evidence that a cloud exists.

## Duplicate And Deduping Assessment

Controls found:

- `cloud_roi_extract.py` dedupes same-page overlapping marker-neighborhood crops
  at IoU `0.82`.
- `manifest_dedupe.py` dedupes same-page crop geometry before GPT/review using
  IoU `0.30` or overlap-smaller `0.65`.
- GPT review queues dedupe only by row id after bucketing.
- Early reviewed manifest builders dedupe by `cloud_roi_id`.
- `build_balanced_expansion_review_batch.py` dedupes by row id and caps by source
  and source page.
- `build_source_split_manifest.py` dedupes by row id, caps source/source-page
  rows, and audits leakage.
- `audit_training_sources.py` reports source-family and source-page leakage.

Weaknesses:

- Older batches could be duplicate-heavy by page/source because row-id dedupe does
  not catch overlapping crop geometry or repeated similar crops from the same
  page.
- Early row-level split can place sibling crops in train and val.
- Materialized YOLO datasets can overwrite duplicate output basenames unless
  guarded.
- Source IDs are not perfectly normalized across old hashed and unhashed PDF
  stems, though newer source-control code improves this.

## Likely Bias Risks

### ROI / Crop Selection Bias

Early training material was dominated by selected crop windows, especially marker
neighborhoods. This is useful for finding revision clouds, but it does not teach
the model the full distribution of no-cloud drawing areas.

### Confidence Threshold Bias

Whole-cloud candidate review depends on YOLO predictions and confidence. GPT
review queues also depend on GPT confidence/status. Both can miss unknown unknowns:
clouds that neither system proposes.

### Duplicate-Heavy Review Bias

Older review batches could include many similar crops from the same source/page.
This makes apparent progress look better than generalization actually is.

### Source-Family Imbalance

Revision #1 and nearby source families dominate several legacy manifests.
Source-controlled splitting and caps are necessary before treating validation as
meaningful.

### Discipline / Style Imbalance

`page_disjoint_real` is currently plumbing-heavy. The touched style-balance
diagnostic supplement exists because the clean untouched pool was exhausted and
needed more architectural/electrical/mechanical/structural coverage.

### Thick Utility / MEP Cloud Undercoverage

Thick/dark clouds appear in utility/MEP contexts such as plumbing and electrical.
Those pages also contain thick pipe/conduit runs, elbows, valves, symbols,
rounded corners, and dense annotation clusters that can look cloud-like. Training
must see both true thick clouds and no-cloud dense MEP false-positive regions.

### Thin Architectural / General Cloud Undercoverage

Thin/faint clouds are a recall risk. They can be lost by crop scaling, GPT
prelabel conservatism, YOLO thresholding, or model training dominated by darker
examples.

### Full-Page Edge-Case Undercoverage

Crops may miss edge-clipped, huge, faint, partial, or isolated clouds. Full-page
truth is needed to detect these failure modes.

## Specific Recommendations For CloudHammer_v2

1. Treat legacy reviewed crops as training data, not eval proof.

   The old reviewed set is valuable for positive labels, hard negatives, and
   known false-positive families. It should not be used to claim full-page
   reliability.

2. Keep `page_disjoint_real` as the main real full-page ruler.

   Score against the human-audited manifest only. Do not use GPT provisional
   labels as truth.

3. Keep `style_balance_diagnostic_real_touched_20260503` separate.

   Use it to understand style/discipline behavior, not promotion performance.
   Do not blend it with `page_disjoint_real`.

4. Require provenance fields on every new candidate/review/training row.

   Minimum recommended fields:

   - `source_id`
   - `source_page_key`
   - `revision_group`
   - `candidate_generation_method`
   - `selection_signal_used`
   - `crop_box_page_xyxy`
   - `contains_marker`
   - `marker_match_status`
   - `model_confidence`
   - `gpt_label_status`
   - `human_review_status`
   - `style_discipline_bucket`
   - `training_allowed`
   - `eval_allowed`

5. Do not allow frozen eval pages into training/mining.

   This includes crop extraction, hard-negative mining, synthetic backgrounds,
   threshold tuning, GPT/model relabel loops, and future active-learning queues.

6. Use source/page-family split only for future training.

   Avoid row-level random splits. Use source/page caps and fail on leakage.

7. Add dataset export guards before more training.

   Fail if materialized YOLO output basenames collide. Fail if a missing label
   would become an empty label without explicit reviewed-empty metadata.

8. Build future review batches with explicit quotas for unknowns.

   Include:

   - full-page human-truth positives
   - true no-cloud full pages or regions
   - thick utility/MEP cloud positives
   - no-cloud utility/MEP dense linework
   - thin/faint architectural/general positives
   - no-cloud door-swing/arc/symbol regions
   - large/intersected/partial/edge-clipped cloud cases
   - random crops from page regions not selected by marker/model/GPT

9. Keep marker/delta context explicit.

   If a future pipeline uses marker context to suppress or rescue candidates,
   name it as a pipeline variant and evaluate it separately from
   `model_only_tiled`.

10. Report product-relevant metrics.

   Continue tracking:

   - false positives per page
   - high-confidence candidate precision
   - recall on known large clouds
   - no-cloud page false-positive rate
   - hard-negative bucket hit rate
   - partial/overmerge counts
   - style/discipline bucket results

## Proposed Next Cleanup / Implementation Task

Before training again, add a CloudHammer_v2 candidate provenance schema and a
dry-run audit that can read any proposed review/training manifest and report:

- generation method counts
- marker/model/GPT/random selection signal counts
- source and source-page concentration
- overlap with frozen eval pages
- missing-label and duplicate-basename risks
- style/discipline bucket coverage

That gives future review batches a measurable bias profile before they become
training data.
