# CloudHammer

Status: current source of truth for CloudHammer pipeline, labeling, prelabeling,
training, inference, and integration boundaries.

CloudHammer is the computer-vision child project inside ScopeLedger. Its job is
narrow: detect scalloped revision-cloud motifs on real blueprint pages and emit
clean artifacts that the main product can consume later.

## Current Model Focus

Primary target for the current CloudHammer v2 pass: train CloudHammer to
reliably crop one real clouded revision area at a time while keeping all
applicable revision detail items that are inside or immediately surrounding
that cloud visible in the output crop.

Project sequencing note:

- CloudHammer v1 already produced a usable rough release path: reviewed
  whole-cloud candidates, split-review correction, backend manifest intake, and
  Excel crop rows.
- ScopeLedger also completed a first-pass local text-layer/OCR extraction pass
  for demo context.
- The current CloudHammer v2 pass exists because that demo path was not yet
  reliable enough: false positives, held-out eval behavior, partial crops, and
  overmerged crops still need to be driven down before deeper scope/detail
  extraction takes priority again.

Do not continue work that drifts away from this target unless it directly
creates training data, evaluation data, or model-facing feedback for that
target. Review tools, suppression rules, marker-anchor logic, and postprocessing
experiments are useful only when their lessons are converted into durable
training/eval cases or model behavior.

Review guardrail:

- review only if it creates training/eval artifacts or validates the cropper
  after the detector
- every reviewed item should become a precise positive label, an empty-label
  hard negative, a held-out eval/failure case, or a validated cropper rule

Near-term priority order:

1. Beat down false positives with reviewed hard negatives and held-out evals.
2. Improve single-cloud crop reliability, including overmerge/split failure
   cases.
3. After CloudHammer is strong, expand detail capture for items inside and
   immediately around accepted clouds.

## Scope

CloudHammer owns:

- drawing page cataloging and rasterization
- marker/delta context extraction for dataset bootstrapping
- cloud ROI extraction
- API prelabels as review accelerators
- human-reviewed label prep
- one-class `cloud_motif` training
- ROI/full-page inference experiments
- JSON/crop/overlay outputs for backend integration

CloudHammer does not own:

- OCR/detail extraction
- deliverable row generation
- Excel export
- review UI behavior
- workspace persistence
- old OpenCV cloud-candidate rescue

## Data Policy

The old heuristic cloud candidates and their crops are junk for this purpose.
Do not use them as:

- evidence
- training data
- validation data
- pseudo-labels
- negative mining

Primary corpus:

- real drawing PDFs under `revision_sets/`
- obvious narrative/spec pages excluded where possible

Training target:

- one YOLO class: `cloud_motif`

API labels are never training truth by themselves. Human-reviewed labels in
`CloudHammer/data/cloud_labels_reviewed` are the training truth.

## Important Paths

Inside `CloudHammer/`:

- config: `configs/cloudhammer.yaml`
- class list: `configs/cloud_classes.txt`
- ROI images to review: `data/cloud_roi_images`
- raw API label guesses: `data/api_cloud_labels_unreviewed`
- raw API predictions: `data/api_cloud_predictions` and/or `data/api_cloud_predictions_unreviewed`
- API review overlays: `data/api_cloud_review`
- reviewed training truth: `data/cloud_labels_reviewed`
- manifests: `data/manifests`
- generated YOLO datasets: `data/yolo_*`
- training/inference runs: `runs/`
- generated outputs: `outputs/`

Do not touch live API output folders while a prelabel run is active.

## Pipeline Stages

1. Page cataloging and rasterization
   - `scripts/catalog_pages.py`
   - builds page manifests and rendered drawing pages
2. Marker-context extraction
   - `scripts/run_delta_bootstrap.py`
   - `scripts/extract_delta_rois.py`
   - uses legacy delta output only as context
3. Cloud ROI generation
   - `scripts/extract_cloud_rois.py`
   - creates candidate crops for labeling/training
4. API prelabeling
   - `scripts/prelabel_cloud_rois_openai.py`
   - writes raw machine guesses into unreviewed folders
5. Human review in LabelImg
   - `scripts/prepare_labelimg_review.py`
   - reviewer corrects labels in `data/cloud_labels_reviewed`
6. Training
   - `scripts/create_reviewed_training_manifest.py`
   - `scripts/train_roi_detector.py`
   - trains only from reviewed labels/manifests
7. Inference and review loop
   - `scripts/infer_pages.py`
   - produces model outputs for later backend integration

## Typical Commands

From `CloudHammer/`:

```powershell
python scripts/catalog_pages.py --no-render
python scripts/catalog_pages.py --limit 5 --overwrite
python scripts/run_delta_bootstrap.py --limit 1
python scripts/extract_delta_rois.py --limit 20
python scripts/extract_cloud_rois.py --limit 20
```

API prelabeling:

```powershell
python scripts/prelabel_cloud_rois_openai.py --limit 25 --dry-run
python scripts/prelabel_cloud_rois_openai.py --limit 25 --max-dim 1024 --request-delay 1.0
python scripts/prepare_labelimg_review.py
```

Reviewed-only manifest:

```powershell
python scripts/create_reviewed_training_manifest.py
python scripts/create_marker_fp_hard_negative_training_manifest.py --overwrite --overwrite-labels
python scripts/create_combined_reviewed_manifest.py --base-manifest data\manifests\reviewed_batch_001_002_004partial_plus_broad_deduped_20260428.jsonl --base-manifest data\manifests\marker_fp_hard_negatives_20260502.jsonl --output data\manifests\reviewed_plus_marker_fp_hard_negatives_20260502.jsonl --summary-json data\manifests\reviewed_plus_marker_fp_hard_negatives_20260502.summary.json --overwrite
```

Training:

```powershell
python scripts/train_roi_detector.py --roi-manifest data\manifests\reviewed_batch_001_priority_train.jsonl --model yolov8n.pt --imgsz 640 --epochs 50 --batch 16
python scripts\train_roi_detector.py --roi-manifest data\manifests\reviewed_plus_marker_fp_hard_negatives_20260502.jsonl --dataset-dir data\yolo_reviewed_plus_marker_fp_hard_negatives_20260502 --model runs\cloudhammer_roi-broad-deduped-20260428\weights\best.pt --name cloudhammer_roi-marker-fp-hn-20260502 --epochs 35 --batch 16 --imgsz 640
```

Inference:

```powershell
python scripts/infer_pages.py --model runs/cloudhammer_roi\weights\best.pt --limit 5
```

Whole-cloud candidate extraction:

```powershell
python scripts\infer_pages.py --config configs\fullpage_all_broad_deduped_lowconf_20260428.yaml --model runs\cloudhammer_roi-broad-deduped-20260428\weights\best.pt --pages-manifest data\manifests\pages_standard_drawings_no_index_20260427.jsonl
python scripts\group_fragment_detections.py --detections-dir runs\fullpage_all_broad_deduped_lowconf_20260428\outputs\detections --output-dir runs\fragment_grouping_fullpage_all_broad_deduped_lowconf_20260428
python scripts\export_whole_cloud_candidates.py --grouped-detections-dir runs\fragment_grouping_fullpage_all_broad_deduped_lowconf_20260428\detections_grouped --output-dir runs\whole_cloud_candidates_broad_deduped_lowconf_context_20260428 --crop-margin-ratio 0.16 --min-crop-margin 550 --max-crop-margin 950
```

## Delta Bootstrap Stack

The bootstrap dependency is not just `delta_v4`.

Treat this full stack as the legacy delta adapter:

- `experiments/delta_v3/denoise_1.py`
- `experiments/delta_v3/denoise_x.py`
- `experiments/delta_v3/denoise_2.py`
- `experiments/delta_v4/detect.py`
- `experiments/2026_04_delta_marker_detector/detect_deltas.py`

Constraints:

- `delta_v4/detect.py` expects a denoised grayscale search image on disk.
- It does not run the `delta_v3` denoise stages internally.
- It uses the source PDF separately for text-layer digit attachment.
- Delta markers/digits are context/debug signals, not the target.

Desired v1 end state: cloud-first page inference. Delta-guided inference should
be optional context or debugging, not a runtime gate.

## Labeling Rules

Use one class only:

- `cloud_motif`

Rules:

- label all visible real cloud motifs in the crop
- label multiple clouds separately when a crop contains multiple real clouds
- include bold, faint, thin, intersected, and partial clouds when real
- do not include door swing arcs, plan geometry arcs, fixture outlines, text
  glyph curves, seals, or other non-cloud curved geometry in training boxes
- leave revision triangles and revision digits unlabeled
- marker ROIs are context only, not targets
- if a crop clearly contains part of a real cloud, label the visible portion
- if a crop only shows ambiguous noise or non-cloud artifact, leave it unlabeled

For L-shaped or otherwise non-rectangular clouds:

- use one rectangle around the visible cloud motif unless the pieces are truly
  disconnected separate clouds
- it is acceptable for the rectangle to include unrelated drawing content in
  the empty part of the L

Outside notes/labels:

- keep the training box focused on the cloud motif itself
- treat outside labels connected by leader arrows as downstream context, not
  part of the YOLO target box

Open labeling policy:

- Dense repeated small clouds may need a later policy: separate instances,
  larger local group, or special training-balance case.
- Until resolved, label each distinct visible real cloud motif and note dense
  repeat cases during review.

## LabelImg Review

Use:

- image directory: `data/cloud_roi_images`
- save directory: `data/cloud_labels_reviewed`
- format: YOLO

Prepare review labels:

```powershell
python scripts/prepare_labelimg_review.py
```

For reviewed negatives:

- do not create a fake `negative_cloud` class
- if an image has no real cloud boxes, save the empty label
- patched local LabelImg can write an empty `.txt` plus `.review.json`
- manifest/resume scripts treat either a newer reviewed label or `.review.json`
  sidecar as reviewed

Known local LabelImg patch from the work-computer environment:

- cast scrollbar/zoom values to int
- honor `LABELIMG_START_IMAGE`
- honor `LABELIMG_IMAGE_LIST`
- use `QRectF` and `QLineF` for PyQt drawing compatibility

Those patches were applied inside `.venv/Lib/site-packages`, not repo source.
If LabelImg crashes on another machine during zoom or box creation, capture the
patch properly or reapply it locally.

## API Prelabel Policy

OpenAI prelabels are review accelerators only.

Inputs/outputs:

- input images: `data/cloud_roi_images`
- raw API label guesses: `data/api_cloud_labels_unreviewed`
- raw prediction log: `data/api_cloud_predictions`
- review overlays: `data/api_cloud_review`
- reviewed labels for training: `data/cloud_labels_reviewed`

Typical flow:

1. Generate cloud ROI crops.
2. Dry-run the API prelabel script.
3. Run API prelabeling into the unreviewed folders.
4. Copy only YOLO `.txt` files into `data/cloud_labels_reviewed`.
5. Review/correct every file in LabelImg.
6. Train only from reviewed labels.

Do not overwrite human-reviewed labels with API guesses.

## Current Data / Training State

As of the latest retained handoff:

- API prelabel images processed: `2,185`
- failed API images: `0`
- review image source: `CloudHammer/data/cloud_roi_images`
- raw API labels: `CloudHammer/data/api_cloud_labels_unreviewed`
- reviewed labels: `CloudHammer/data/cloud_labels_reviewed`

Review batches:

- `batch_001_priority_train`: `500` images
- `batch_002_thin_faint`: `95` images
- `batch_003_weird_partial`: `965` images
- `batch_004_hard_negatives`: `506` images
- `batch_later`: `119` images

Batch 1 review was at `204 / 500` in the retained handoff. This number rots
quickly; regenerate counts from file mtimes/sidecars before acting on it.

Reviewed manifest noted in the handoff:

- `CloudHammer/data/manifests/reviewed_batch_001_priority_train.jsonl`
- total rows at that time: `204`
- train split: `163`
- val split: `41`
- test split: `0`

Review-count rule:

- reviewed label exists in `data/cloud_labels_reviewed`
- raw API label exists in `data/api_cloud_labels_unreviewed`
- reviewed label mtime is more than 1 second newer than raw API label mtime
- or a `.review.json` sidecar marks an intentional reviewed negative

Do not count file existence alone, because label files may be seeded from
prelabels.

## GPU / Environment Notes

The work computer was CPU-only in the retained handoff:

- `torch 2.11.0+cpu`
- `torch.cuda.is_available() == False`

Full training should run on the home PC with RTX 4070 or another CUDA-capable
machine.

CUDA check:

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no cuda')"
```

If CUDA prints `False` on the training machine, install a CUDA-enabled PyTorch
build before real training.

Current local training environment on 2026-05-02:

- `.venv` has `ultralytics` and `torch 2.11.0+cu128`
- CUDA is available on `NVIDIA GeForce RTX 4070 Ti SUPER`
- old upper-level folders such as `F:\Desktop\m\yolo-config`,
  `F:\Desktop\m\pip-tmp`, and `F:\Desktop\m\torch-cache` are cache/temp
  folders, not training data or truth labels
- active CloudHammer cache redirection is in `cloudhammer/runtime.py` and points
  Torch/YOLO/temp artifacts under `CloudHammer/models/cache` and
  `CloudHammer/runs/tmp`

## Current Training Checkpoint

Latest model-facing run:

- run: `CloudHammer/runs/cloudhammer_roi-symbol-text-fp-hn-20260502`
- weights: `CloudHammer/runs/cloudhammer_roi-symbol-text-fp-hn-20260502/weights/best.pt`
- base weights: `CloudHammer/runs/cloudhammer_roi-marker-fp-hn-20260502/weights/best.pt`
- manifest: `CloudHammer/data/manifests/reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`
- dataset: `CloudHammer/data/yolo_reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502`
- training rows: `931` total, `639` cloud positives, `292` empty-label negatives
- newly added eval false-positive hard negatives: `9`
  - `5` circular symbol / fixture geometry
  - `4` text / glyph arcs
- final val metrics: precision `0.910`, recall `0.899`, mAP50 `0.915`, mAP50-95 `0.758`

Hard-negative eval command:

```powershell
python scripts\evaluate_hard_negative_hits.py --manifest data\manifests\marker_fp_hard_negatives_20260502.jsonl --model runs\cloudhammer_roi-broad-deduped-20260428\weights\best.pt --model runs\cloudhammer_roi-marker-fp-hn-20260502\weights\best.pt --model runs\cloudhammer_roi-symbol-text-fp-hn-20260502\weights\best.pt --output runs\cloudhammer_roi-symbol-text-fp-hn-20260502\marker_hard_negative_hit_eval.json
python scripts\evaluate_hard_negative_hits.py --manifest data\manifests\eval_symbol_text_fp_hard_negatives_20260502.jsonl --model runs\cloudhammer_roi-marker-fp-hn-20260502\weights\best.pt --model runs\cloudhammer_roi-symbol-text-fp-hn-20260502\weights\best.pt --output runs\cloudhammer_roi-symbol-text-fp-hn-20260502\eval_symbol_text_hard_negative_hit_eval.json
```

Hard-negative result:

- old broad-deduped model: `2 / 29` reviewed false-positive crops still hit
- marker-FP model: `0 / 29` marker false-positive crops hit at confidence
  `0.50`, but `3 / 9` symbol/text eval false positives still hit at confidence
  `0.25`
- symbol/text-FP model: `0 / 29` marker false-positive crops and `0 / 9`
  symbol/text false-positive crops hit even at confidence `0.10`

## CloudHammer V2 Small-Corpus Controls

CloudHammer v2 is now treated as a company-specific ESA/VA-style revision
package detector, not a generic blueprint cloud detector. The optimization goal
is lower human review burden without quietly losing real clouds, especially
large, faint, intersected, or dense-context clouds.

Current source-control artifacts:

- source audit script: `CloudHammer/scripts/audit_training_sources.py`
- source-controlled split builder:
  `CloudHammer/scripts/build_source_split_manifest.py`
- balanced expansion batch builder:
  `CloudHammer/scripts/build_balanced_expansion_review_batch.py`
- safe GPT-to-LabelImg seed copier:
  `CloudHammer/scripts/seed_review_batch_from_api_labels.py`
- latest audit:
  `CloudHammer/runs/source_audit_small_corpus_20260502/source_audit_summary.md`
- source-controlled reviewed manifest:
  `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.jsonl`
- quasi-holdout reviewed manifest:
  `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.quasi_holdout.jsonl`
- next review batch:
  `CloudHammer/data/review_batches/small_corpus_expansion_20260502`
- fresh supplemental review batch:
  `CloudHammer/data/review_batches/small_corpus_expansion_supplement_20260502`
- temporary handoff note for the active review step:
  `CloudHammer/docs/TEMP_CLOUDHAMMER_V2_REVIEW_HANDOFF_20260502.md`

Important audit findings:

- current reviewed manifest: `931` rows across `12` source families and `157`
  source pages
- current 14-page full-page eval overlaps training source pages on `12 / 14`
  pages, so it is a debug regression set only
- source-controlled split output: `502` reviewed train/val rows after caps,
  split as `397` train and `105` val
- quasi-holdout output: `30` reviewed rows, currently Rev 5 / Rev 7
- cap effect: `399` rows dropped from the source-controlled training manifest
  to reduce Rev 1/source-page dominance
- expansion batch: `300` review crops selected, with `131` normal hard
  negatives, `153` weird/faint/partial/intersected-style candidates, and `16`
  large/dense-context candidates
- GPT prelabels for the expansion batch were generated on 2026-05-02:
  `166` new API calls, `134` skipped existing labels, `0` failures
- all `300` API labels were copied into the batch-local LabelImg label folder
  with API mtimes preserved; timestamp check showed `0 / 300` seed labels are
  currently newer than their API labels, so they should not count as reviewed
  training truth until a human saves them or adds review markers
- supplemental fresh batch: `150` more candidates selected after excluding
  current reviewed rows, the first 300-crop expansion batch, and already
  API-labeled IDs
  - selected mix: `87` normal hard negatives, `60` weird/faint/partial-style
    candidates, `3` large/dense-context candidates
  - revision mix: Rev 1 `35`, Rev 2 `38`, Rev 3 `62`, Rev 4 `15`
  - GPT prelabels: `150` new API calls, `0` skipped, `0` failures
  - seed-label safety check: `0 / 150` labels currently newer than API labels

GPT/API labels may seed review, but only human-reviewed labels or reviewed empty
labels may enter training. Do not train the next source-controlled baseline or
fine-tuned continuity model until the expansion batch has been reviewed.

## Output Contract

CloudHammer v1 should emit:

- page-space cloud bounding boxes
- crop image paths
- confidence scores
- debug overlays
- JSON manifests per source PDF

These outputs must be convertible into backend cloud-region models without
redesign.

Backend integration should happen through `backend/cloudhammer_client/`, not by
making CloudHammer own product review/export concerns.

## Current Whole-Cloud Export

Latest full-page eval from the current model checkpoint:

- model: `CloudHammer/runs/cloudhammer_roi-symbol-text-fp-hn-20260502/weights/best.pt`
- config: `CloudHammer/configs/fullpage_eval_symbol_text_fp_hn_20260502.yaml`
- tiled eval detections: `CloudHammer/runs/fullpage_eval_symbol_text_fp_hn_20260502/outputs/detections`
- grouped eval output: `CloudHammer/runs/fragment_grouping_fullpage_eval_symbol_text_fp_hn_20260502`
- tangible review queue: `CloudHammer/runs/whole_cloud_eval_symbol_text_fp_hn_20260502/whole_cloud_candidates_manifest.jsonl`
- durable review log target: `CloudHammer/data/whole_cloud_candidate_reviews/whole_cloud_eval_symbol_text_fp_hn_20260502.review.jsonl`
- same 14-page eval sample comparison:
  - previous broad-deduped model/grouping: `72` fragments, `34` groups
  - marker-FP hard-negative model/grouping: `101` fragments, `38` groups
  - symbol/text-FP hard-negative model/grouping: `81` fragments, `34` groups
- whole-cloud export comparison:
  - marker-FP model: `38` candidates, `29` high, `8` medium, `1` low
  - symbol/text-FP model: `34` candidates, `28` high, `5` medium, `1` low
- automatic overlap check against the prior reviewed eval:
  - removed all `9 / 9` prior reviewed false positives from crop containment
  - retained crop containment for `19 / 21` prior reviewed accepts
  - did not crop-contain `2` prior reviewed accepts, so this model is not
    promotable without visual review and recall repair
- manual large-cloud audit on this small eval export dropped from `15` matched
  labels to `12`; treat that as a recall warning, not a promotion signal
- interpretation: useful hard-negative improvement, but not promoted

Review launch:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\launch_review_queue.ps1 -Queue symbol_text_model_eval
```

After review, analyze the structured feedback:

```powershell
python scripts\analyze_whole_cloud_candidate_reviews.py --manifest runs\whole_cloud_eval_symbol_text_fp_hn_20260502\whole_cloud_candidates_manifest.jsonl --review-log data\whole_cloud_candidate_reviews\whole_cloud_eval_symbol_text_fp_hn_20260502.review.jsonl --output-dir runs\whole_cloud_eval_symbol_text_fp_hn_20260502\review_analysis
```

The analysis emits accepted candidates, false positives, overmerged cases,
partials, and issue manifests that can feed the next training/eval iteration.

Accepted crops with non-cloud curved geometry:

- use reviewer shortcut `C` / `Accept + Arc` when the crop is acceptable but
  includes a door swing arc, plan geometry arc, fixture circle, text curve, or
  similar nearby non-cloud curve
- the review log still records `status: accept`, plus
  `accept_reason: non_cloud_curve_contamination`
- after analysis, build a precise-label review batch from the tagged accepts:

```powershell
python scripts\create_accept_contamination_label_review_batch.py --overwrite
python scripts\launch_labelimg_batch.py accept_contamination_precise_labels_20260502 --reviewed-label-dir data\cloud_labels_reviewed_accept_contamination_20260502
```

- in LabelImg, draw/save only true `cloud_motif` boxes; leave the non-cloud
  curved geometry unlabeled as background
- `scripts\create_combined_reviewed_manifest.py` can then include this reviewed
  batch once the precise labels are saved, so the lesson reaches training

```powershell
python scripts\create_combined_reviewed_manifest.py --base-manifest data\manifests\reviewed_plus_marker_fp_hard_negatives_20260502.jsonl --queue-root data\review_batches\accept_contamination_precise_labels_20260502 --output data\manifests\reviewed_plus_marker_fp_hn_plus_accept_contamination_20260502.jsonl --summary-json data\manifests\reviewed_plus_marker_fp_hn_plus_accept_contamination_20260502.summary.json --overwrite
```

Review bias guardrail:

- Accept dense plan-context crops when the intended single clouded revision
  area is actually captured. Do not mark a crop partial or false-positive just
  because the surrounding plan content is noisy, hard to visually parse, or
  contains many overlapping symbols/text labels.
- Mark partial only when the visible clouded revision area is materially clipped
  or the crop misses meaningful parts of the intended cloud.
- Mark overmerged only when distinct clouded revision areas are bundled into
  one candidate, not merely because one real cloud surrounds dense drawing
  content.
- Crop-level accept does not mean the full crop rectangle is training truth.
  If an accepted crop includes a door swing arc or other non-cloud geometry
  near the real cloud, keep the training target on the actual cloud motif only.
  Do not convert accepted whole-cloud crop bounds into YOLO positive boxes.

Last integrated whole-cloud export artifact run:

- `CloudHammer/runs/whole_cloud_candidates_broad_deduped_lowconf_context_20260428`

Inputs:

- model: `CloudHammer/runs/cloudhammer_roi-broad-deduped-20260428/weights/best.pt`
- standard non-index pages: `CloudHammer/data/manifests/pages_standard_drawings_no_index_20260427.jsonl`
- low-confidence tiled detections: `CloudHammer/runs/fullpage_all_broad_deduped_lowconf_20260428/outputs/detections`
- grouped fragments: `CloudHammer/runs/fragment_grouping_fullpage_all_broad_deduped_lowconf_20260428/detections_grouped`

Outputs:

- manifest: `whole_cloud_candidates_manifest.jsonl`
- per-PDF whole-cloud detection JSON: `detections_whole/`
- crop artifacts: `crops/`
- debug overlays: `overlays/`
- contact sheets: `contact_sheets/`
- manual audit: `manual_large_cloud_audit_summary.md`

Current counts:

- pages processed: `115`
- whole-cloud candidates: `283`
- size buckets: `136 small`, `76 medium`, `52 large`, `19 xlarge`
- confidence tiers: `210 high`, `18 medium`, `55 low`
- manual large-cloud audit: `78 / 78` hand-labeled large-cloud boxes have at
  least `95%` containment inside exported crop artifacts

Important interpretation:

- `bbox_page_xyxy` is the model/grouping evidence box.
- `crop_box_page_xyxy` is the high-recall extraction artifact box used to save
  the whole-cloud crop.
- The wider crop context is intentional because some large clouds only produce
  partial motif detections on one edge.

## GPT Prelabel Benchmark

Before trusting hundreds or thousands of GPT-assisted labels, compare raw GPT
labels against human-reviewed labels where review is known.

Compare:

- GPT raw labels: `data/api_cloud_labels_unreviewed`
- human labels: `data/cloud_labels_reviewed`
- reviewed subset: files where human labels are known by mtime or sidecar

Metrics:

- image-level cloud/no-cloud accuracy
- box precision
- box recall
- IoU at `0.25`, `0.40`, `0.50`
- error rates by visual type/reason bucket
- confidence calibration

Candidate training experiments:

- `human_only_204`
- `gpt_only_high_conf`
- `human_plus_gpt_high_conf`
- `gpt_pretrain_then_human_finetune`

Do not treat GPT labels as truth until this benchmark is done. The risk is
systematic bias: overboxing partials, missing faint clouds, or labeling repeated
geometry incorrectly.

## Near-Term Milestones

1. Treat the rough CloudHammer v1 deliverable path and first-pass OCR/text
   extraction as already proven enough for demo context.
2. Visually compare latest full-page eval overlays against the previous model.
3. Convert reviewed false positives, misses, and overmerge/split failures into
   training/eval manifests.
4. Train the next reviewed-label detector iteration from the current best
   checkpoint.
5. Track false-positive hit rates on reviewed hard-negative sets and recall on
   held-out revision pages.
6. Promote a model only after full-page eval review shows fewer false positives
   without unacceptable missed clouds.
7. Keep deeper OCR/detail extraction deferred until single-cloud crops are
   reliable enough to be high-trust inputs.
