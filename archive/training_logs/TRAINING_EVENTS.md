# Training Events

## 2026-04-24 - First CloudHammer YOLO Training Run

### Goal

Train the first revision-cloud detector using only human-reviewed labels.

The target class was:

- `cloud_motif`

### Machine

Training was run from:

- `F:\Desktop\m\projects\kevision\CloudHammer`

The machine had:

- GPU: `NVIDIA GeForce RTX 4070 Ti SUPER`
- PyTorch: `2.11.0+cu128`
- CUDA available: `True`

The Python environment was created at:

- `F:\Desktop\m\projects\kevision\.venv`

Extra cache/temp folders were pointed at `F:` to avoid using much `C:` space:

- `F:\Desktop\m\pip-cache`
- `F:\Desktop\m\pip-tmp`
- `F:\Desktop\m\yolo-config`

### Data Used

Training used the reviewed truth set, not raw GPT labels.

Dataset:

- Manifest: `CloudHammer/data/manifests/reviewed_batch_001_priority_train.jsonl`
- Total reviewed examples: `204`
- Train split: `163`
- Validation split: `41`
- Test split: `0`

Important note: after syncing to this machine, file timestamps were no longer
reliable for detecting reviewed labels. Regenerating the reviewed manifest by
timestamp produced the wrong count. The original 204-row reviewed manifest was
restored and its paths were rewritten to the current `F:` checkout before
training.

### Command Run

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe scripts\train_roi_detector.py --roi-manifest data\manifests\reviewed_batch_001_priority_train.jsonl --model yolov8n.pt --imgsz 640 --epochs 50 --batch 16
```

### Output

Run directory:

- `CloudHammer/runs/cloudhammer_roi`

Best model:

- `CloudHammer/runs/cloudhammer_roi/weights/best.pt`

Last model:

- `CloudHammer/runs/cloudhammer_roi/weights/last.pt`

### Result

Final validation result against the 41 reviewed validation images:

- Precision: `0.987`
- Recall: `0.962`
- mAP50: `0.991`
- mAP50-95: `0.891`

Plain English: the first model trained cleanly. On the small reviewed validation
set, it usually found the cloud motifs and usually avoided extra false boxes.

### Caveat

This result is promising but probably optimistic.

Reasons:

- The validation set is small: only `41` images.
- The validation data comes from the same reviewed batch strategy as training.
- We have not yet tested against untouched pages, untouched batches, or a wider
mix of weird/faint/hard-negative examples.
- We have not yet measured how good or bad the GPT prelabels are compared with
human review.

## Still Not Done

### Real-World Model Inspection

We should run the trained model on images or pages that were not part of this
204-example truth set and visually inspect:

- good detections,
- missed faint clouds,
- false positives,
- repeated-detail cases,
- partial/intersected clouds,
- hard negatives near revision markers.

## Good Next Steps

1. Run inference with `best.pt` on untouched ROI crops or full pages.
2. Create visual review overlays for those predictions.
3. Inspect the failure modes by eye.
4. Run the GPT-vs-human benchmark on the 204 reviewed examples.
5. Decide whether to:
   - review more batch 1 labels,
   - add hard negatives and faint-cloud cases,
   - use only high-confidence GPT pseudo-labels,
   - or fine-tune after a GPT pretraining pass.

## Files Created During Training

Generated artifacts include:

- `CloudHammer/runs/cloudhammer_roi/`
- `CloudHammer/data/yolo/`
- `CloudHammer/yolov8n.pt`
- `CloudHammer/yolo26n.pt`
- `CloudHammer/models/cache/`

These are generated training outputs and downloaded model/cache files, not hand
edited source code.

## 2026-04-24 - GPT Prelabels Compared Against Human Review

### Goal

Check whether the raw GPT prelabels are good enough to use as extra training
data, especially if we cherry-pick high-confidence predictions.

### What Was Compared

Compared:

- raw GPT labels: `CloudHammer/data/api_cloud_labels_unreviewed`
- human-reviewed labels: `CloudHammer/data/cloud_labels_reviewed`
- reviewed manifest: `CloudHammer/data/manifests/reviewed_batch_001_priority_train.jsonl`

The benchmark used the same 204 human-reviewed examples from the first training
run.

Benchmark script:

- `CloudHammer/scripts/benchmark_gpt_prelabels.py`

Output folder:

- `CloudHammer/outputs/gpt_prelabel_benchmark`

### Image-Level Result

This checks whether GPT correctly decided "this crop has a cloud" versus "this
crop has no cloud."

- Images checked: `204`
- GPT true cloud images: `203`
- GPT false cloud images: `1`
- GPT missed cloud images: `0`
- Image-level accuracy: `0.995`
- Image-level precision: `0.995`
- Image-level recall: `1.000`

Plain English: GPT was extremely good at deciding whether a crop contained a
cloud motif in this reviewed set.

Important clarification: this `99.5%` number is not an overall "GPT was 99.5%
done" score. The 204 reviewed examples used here were almost all positive cloud
crops: `203` had human cloud boxes and `1` had no human cloud boxes. That makes
image-level cloud/no-cloud accuracy look very high. The more meaningful score
for training labels is the box-level comparison below.

### Box-Level Result

This checks whether GPT boxes line up with the human-edited boxes.

At IoU `0.25`:

- Precision: `0.881`
- Recall: `0.789`
- F1: `0.832`

At IoU `0.40`:

- Precision: `0.803`
- Recall: `0.720`
- F1: `0.759`

At IoU `0.50`:

- Precision: `0.740`
- Recall: `0.663`
- F1: `0.699`

Plain English: GPT is very good at finding that clouds exist, but its exact
boxes do not always match the human-edited boxes. The mismatch is mostly about
box count and box tightness, not total failure.

A direct file check confirmed the benchmark compared raw GPT labels against
reviewed labels:

- raw GPT folder: `CloudHammer/data/api_cloud_labels_unreviewed`
- reviewed folder: `CloudHammer/data/cloud_labels_reviewed`
- exact same label files among the 204 examples: `0`
- different label files among the 204 examples: `204`

### Confidence Cutoff Test

At IoU `0.40`, using all GPT boxes:

- Box precision: `0.803`
- Box recall: `0.720`
- Box F1: `0.759`

Keeping only GPT boxes with confidence `>= 0.90`:

- Box precision: `0.817`
- Box recall: `0.685`
- Box F1: `0.745`

Keeping only GPT boxes with confidence `>= 0.95`:

- Box precision: `0.855`
- Box recall: `0.556`
- Box F1: `0.674`

Plain English: higher confidence gives cleaner boxes, but throws away a lot of
valid boxes. A `0.90` cutoff looks like a reasonable starting point. A `0.95`
cutoff may be too strict if we care about recall.

### Current Takeaway

The data supports the hunch that GPT prelabels are useful.

Best current interpretation:

- GPT is probably safe as a cloud/no-cloud filter.
- GPT high-confidence boxes are probably useful as pseudo-labels.
- GPT boxes should not yet be treated as perfect human truth.
- The first pseudo-label experiment should probably use confidence `>= 0.90`,
  then compare against the human-only model.

### Sensible Next Experiment

Train a second model using:

- the 204 human-reviewed labels, plus
- GPT pseudo-label boxes with confidence `>= 0.90`

Then compare that model against the current human-only model on the same
reviewed validation set and, more importantly, on fresh visual inspection
overlays.

## 2026-04-24 - Random Drawing Crop Audit Set

### Goal

Create a more realistic random sample from the drawings, instead of only testing
on cloud-heavy review crops.

This is meant to answer a different question:

- Does GPT stay quiet on normal drawing areas?
- Does GPT hallucinate clouds on ordinary linework?
- How many random drawing crops actually contain revision clouds?

### What Was Created

Random crop script:

- `CloudHammer/scripts/create_random_drawing_crops.py`

GPT output config:

- `CloudHammer/configs/random_drawing_crops_prelabel.yaml`

Output folder:

- `CloudHammer/data/random_drawing_crops`

The sample:

- `200` crops
- `1024 x 1024` pixels each
- sampled across revision sets
- sampled from drawing pages only
- avoided likely title block/header/footer areas
- used only a tiny ink check to avoid pure blank paper

Revision spread:

- about `33-34` crops from each revision group
- `50` unique sheets represented

### GPT Run

The 200 random crops were sent through GPT using:

- model: `gpt-5.4`
- detail: `auto`
- max image dimension: `1024`
- image format sent to API: `jpeg`
- min accepted box confidence: `0.60`

Run result:

- processed: `200`
- failed: `0`
- GPT said no cloud: `186`
- GPT said cloud: `14`

Accepted GPT box counts:

- `0` boxes: `187` crops
- `1` box: `11` crops
- `2` boxes: `1` crop
- `3` boxes: `1` crop

Accepted GPT box confidence:

- min: `0.67`
- max: `0.98`
- average: `0.905`

### Why This Matters

This random set is probably more useful for checking GPT false positives than
the first 204 reviewed set, because the first set was almost all positive cloud
crops.

The quick read is encouraging: GPT stayed negative on most random drawing-area
crops. The next step is human spot-checking the `14` GPT-positive crops and a
sample of the `186` GPT-negative crops.

### Review Files

Use:

- `CloudHammer/data/random_drawing_crops/gpt_quick_review.csv`
- `CloudHammer/data/random_drawing_crops/gpt_review/`

Suggested quick labels:

- `positive`
- `negative`
- `unsure`

## 2026-04-24 - Temporary Random GPT Review Queue

Created a smaller browse/review queue from the random crop GPT output.

Queue folder:

- `CloudHammer/data/temp_random_gpt_review_queue`

Contents:

- all GPT-positive random crops: `14`
- deterministic GPT-negative spot checks: `50`
- total queued images: `64`

The queue includes:

- `images/`: crop images
- `labels/`: seeded GPT YOLO labels, also the LabelImg save folder
- `gpt_overlays/`: GPT overlay JPGs
- `review_queue.csv`: quick human review sheet
- `manifest.jsonl`: queue metadata
- `images.txt`: image list in queue order

LabelImg was installed into the repo venv on `F:`.

Launch from `CloudHammer/`:

```powershell
..\.venv\Scripts\python.exe scripts\launch_random_gpt_review_queue.py
```

Launcher script:

- `CloudHammer/scripts/launch_random_gpt_review_queue.py`

## 2026-04-24 - Second YOLO Training Run With Thin/Faint Batch

### Goal

Improve the detector by adding more thin/faint cloud examples to the original
204 human-reviewed truth set.

### Added Human Review

Reviewed batch:

- `CloudHammer/data/review_batches/batch_002_thin_faint`

Batch size:

- `95` images

Timestamp check after LabelImg review:

- reviewed/saved: `95 / 95`

### Training Data

Combined manifest:

- `CloudHammer/data/manifests/reviewed_batch_001_plus_002.jsonl`

Rows:

- total: `299`
- batch 1 priority truth rows: `204`
- batch 2 thin/faint rows: `95`

Split:

- train: `239`
- val: `60`
- test: `0`

### Command Run

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe scripts\train_roi_detector.py --roi-manifest data\manifests\reviewed_batch_001_plus_002.jsonl --model yolov8n.pt --imgsz 640 --epochs 50 --batch 16
```

### Output

Run directory:

- `CloudHammer/runs/cloudhammer_roi-2`

Best model:

- `CloudHammer/runs/cloudhammer_roi-2/weights/best.pt`

Last model:

- `CloudHammer/runs/cloudhammer_roi-2/weights/last.pt`

### Result On Combined Validation Set

New model final validation:

- images: `60`
- instances: `123`
- precision: `0.873`
- recall: `0.854`
- mAP50: `0.897`
- mAP50-95: `0.686`

For a fair comparison, the first 204-only model was also evaluated on this same
combined validation set:

- precision: `0.923`
- recall: `0.837`
- mAP50: `0.888`
- mAP50-95: `0.661`

Plain English:

- The new model gave up some precision.
- It improved recall.
- It improved both mAP50 and mAP50-95 on the harder combined validation set.
- This is the expected tradeoff from adding harder thin/faint examples.

Current best candidate for next inspection:

- `CloudHammer/runs/cloudhammer_roi-2/weights/best.pt`

### Human Quick Review Result

Human-reviewed CSV:

- `CloudHammer/data/temp_random_gpt_review_queue/review_queue_human_reviewed.csv`

Reviewed queue:

- GPT-positive crops reviewed: `14`
- GPT-negative spot checks reviewed: `50`

Human labels:

- GPT positives that were real positives: `11 / 14`
- GPT positives that were false positives: `3 / 14`
- GPT negative spot checks that were actually negative: `50 / 50`
- Missed cloud noted in the GPT-positive queue: `1`

Notes from review:

- `8` GPT positives were marked "GPT great read"
- `3` GPT positives were false positives
- `1` had a box above a horizontal cloud line
- `1` had a box too tight
- `1` missed a cloud

Confidence mattered a lot:

- false positives had GPT confidence `0.67`, `0.72`, and `0.78`
- reviewed GPT positives at `>= 0.90` were real positives in this sample

Plain English: GPT was good, but not magic. On random drawing crops it was very
good at staying negative, and the high-confidence positives looked useful. The
low-confidence positives were not reliable enough to trust as training labels
without review.

Current practical rule:

- Treat GPT negatives as promising but still spot-check periodically.
- Treat GPT positives `>= 0.90` as good pseudo-label candidates.
- Do not use GPT positives below `0.90` as training truth without review.
- Still expect box quality issues even when the cloud/no-cloud decision is right.

## 2026-04-24 - Hard-Negative Batch Review In Progress

Reviewed batch:

- `CloudHammer/data/review_batches/batch_004_hard_negatives`

Purpose:

- add hard negatives that look cloud-like but are not clouds
- especially door swing arcs, marker-neighborhood noise, fixtures, callout
  bubbles, and repeated architectural linework

Important review rule:

- if a crop has door swing arcs or other cloud-like linework but no real cloud,
  save it with no boxes; YOLO learns these as negative examples from the empty
  reviewed label file

LabelImg issue:

- LabelImg has been unstable during this pass and has closed/crashed multiple
  times
- the launcher now supports manual resume with `--start-index`
- when `--start-index` is used, it writes a sliced image list like
  `images_from_308.txt`, so LabelImg opens only the remaining images instead of
  forcing review from the beginning of the 506-image batch

## 2026-04-25 - Reviewed Negative Capture Fixed

Problem found:

- LabelImg does not naturally mark an already-empty image as reviewed when the
  reviewer simply inspects it and moves on.
- Relying only on label-file modification time is not reliable after machine
  sync/copy operations.
- Adding a fake `negative_cloud` YOLO class would be the wrong training signal,
  because YOLO would learn a whole-image object instead of learning from an
  empty-label negative example.

Fix:

- Keep YOLO single-class: `cloud_motif`.
- Represent no-cloud examples as empty YOLO `.txt` files.
- Record review completion separately with a sidecar marker:
  `*.review.json`.
- Patched local LabelImg so `Ctrl+S` works on an untouched empty image and
  writes both the empty label and the `.review.json` marker.
- Updated review resume and training-manifest scripts to treat `.review.json`
  as the reliable reviewed signal.
- Backfilled `.review.json` markers for the 325 rows already present in
  `CloudHammer/data/manifests/reviewed_batch_004_hard_negatives_partial_001_325.jsonl`.

Current hard-negative resume point:

- `batch_004_hard_negatives` now resumes at item `326 / 506`.

## 2026-04-27 - Planned Next CloudHammer Training And Broader Data Pass

Status:

- planning note only
- do not delete, overwrite, reset, or regenerate prior CloudHammer labels,
  review batches, manifests, API outputs, model runs, or evaluation outputs
  unless a later note explicitly records that decision

Current human-review state:

- hard-negative review is paused before completing the remaining sliced queue
- the active hard-negative batch is
  `CloudHammer/data/review_batches/batch_004_hard_negatives`
- the last resumed sliced queue started at item `391 / 506` using
  `CloudHammer/data/review_batches/batch_004_hard_negatives/images_from_391.txt`
- review was stopped roughly `34 / 116` images into that sliced queue
- exact training inclusion must be determined from reliable reviewed markers:
  use `.review.json` sidecars plus reviewed `.txt` label files, not file
  existence alone

Immediate next plan:

1. Freeze the current reviewed-label state as-is.
2. Build a new training manifest from all currently reviewed truth, including
   the partial hard-negative review completed so far.
3. Train the next CloudHammer ROI model using the existing positives plus the
   newly reviewed hard negatives.
4. Evaluate the model in two ways:
   - normal validation for continuity with prior runs
   - a more honest held-out evaluation against revision material not used to
     choose or label the training crops, because random crop-level validation
     is likely over-optimistic when near-duplicate floors/pages are split across
     train and validation

Evaluation concern:

- current labeled data appears concentrated in a small number of revision sets,
  especially Revision #1 and likely Revision #4
- many crops are near-duplicates across similar floor plans
- reported accuracy/mAP will be inflated if train and validation contain sibling
  crops from the same page, same PDF, or same repeated floor stack
- future manifests should group related crops by source PDF/page/floor family
  where practical, and held-out testing should use whole revision sets or whole
  source PDFs

Next data-expansion plan after the hard-negative training/eval run:

1. Create a new crop candidate pool across all available target revision sets:
   `Revision #1`, `Revision #2`, `Revision #3`, `Revision #4`, `Revision #5`,
   and `Revision #7`.
2. Preserve all existing crop, prelabel, review, and model-output directories.
   New outputs should go into new dated or numbered directories/manifests rather
   than reusing prior live folders.
3. Send the new broad crop pool through the GPT API for pre-review labels, using
   the same principle as earlier API-assisted labeling:
   GPT labels are prelabels only, not training truth.
4. Create new review subsets from the GPT-prelabeled pool, with emphasis on
   diversity across revision sets and source PDFs rather than many near-duplicate
   crops from one floor stack.
5. Include subset types such as:
   - hard negatives / cloud-like no-cloud crops
   - high-confidence GPT positives for quick human correction
   - low-confidence or ambiguous GPT positives
   - faint/thin/partial/weird clouds
   - GPT negatives for periodic spot checks
6. Human-review those subsets into `data/cloud_labels_reviewed` or a clearly
   documented successor reviewed-label location before using them as training
   truth.

Working rule going forward:

- use the model-validation number for iteration only
- trust held-out revision-set performance more than random split performance
- cap near-duplicate siblings so human review time buys visual variety
- keep a written event log before every training, evaluation, crop-generation,
  API-prelabel, or batch-construction step

## 2026-04-27 - Partial Hard-Negative Training Run

Purpose:

- train the next ROI detector using the trusted reviewed `batch_001` +
  `batch_002` manifest plus the current partial hard-negative review state
- preserve prior run directories and avoid overwriting the prior `data/yolo`
  staging directory

Code change made for preservation:

- `CloudHammer/scripts/train_roi_detector.py` now accepts `--dataset-dir` and
  `--name`
- `CloudHammer/cloudhammer/train/trainer.py` passes those through to the YOLO
  dataset builder and Ultralytics run name

Training manifest:

- `CloudHammer/data/manifests/reviewed_batch_001_002_plus_004partial_current_20260427.jsonl`
- source base manifest:
  `CloudHammer/data/manifests/reviewed_batch_001_plus_002.jsonl`
- hard-negative source:
  `CloudHammer/data/review_batches/batch_004_hard_negatives/manifest.jsonl`
- hard negatives included only when confirmed by `.review.json`

Manifest counts:

- total rows: `723`
- train: `578`
- val: `145`
- positive/non-empty label files: `494`
- negative/empty label files: `229`
- by batch:
  - `batch_001_priority_train`: `204`
  - `batch_002_thin_faint`: `95`
  - `batch_004_hard_negatives`: `424`

YOLO staging directory:

- `CloudHammer/data/yolo_reviewed_batch_001_002_plus_004partial_current_20260427`

Training command:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe scripts\train_roi_detector.py --roi-manifest data\manifests\reviewed_batch_001_002_plus_004partial_current_20260427.jsonl --dataset-dir data\yolo_reviewed_batch_001_002_plus_004partial_current_20260427 --name cloudhammer_roi-hardneg-20260427
```

Run directory:

- `CloudHammer/runs/cloudhammer_roi-hardneg-20260427`

Weights:

- best: `CloudHammer/runs/cloudhammer_roi-hardneg-20260427/weights/best.pt`
- last: `CloudHammer/runs/cloudhammer_roi-hardneg-20260427/weights/last.pt`

Training result on the new mixed validation set:

- images: `145`
- instances: `210`
- backgrounds in val scan: `39`
- final best-weight validation:
  - precision: `0.862`
  - recall: `0.890`
  - mAP50: `0.882`
  - mAP50-95: `0.710`
- best epoch by mAP50-95: `49`
  - precision: `0.862`
  - recall: `0.891`
  - mAP50: `0.882`
  - mAP50-95: `0.710`

Comparison on the same new mixed validation set:

- previous model:
  `CloudHammer/runs/cloudhammer_roi-3/weights/best.pt`
  - precision: `0.887`
  - recall: `0.898`
  - mAP50: `0.919`
  - mAP50-95: `0.728`
- new partial-hard-negative model:
  `CloudHammer/runs/cloudhammer_roi-hardneg-20260427/weights/best.pt`
  - precision: `0.862`
  - recall: `0.891`
  - mAP50: `0.882`
  - mAP50-95: `0.710`

Read:

- the new partial-hard-negative model did not beat `cloudhammer_roi-3` on this
  mixed validation set
- this comparison is still not a true unknown-revision-set test because the
  validation rows are drawn from the same reviewed crop universe
- the next trustworthy test should use whole held-out revision sets or source
  PDFs not used to choose/review the training crops

Verification:

- CloudHammer tests passed: `17 passed`

## 2026-04-27 - Broad GPT Prelabel Candidate Queue Prepared

Status:

- preparation only
- no OpenAI API requests were sent in this step
- existing API output folders, reviewed labels, prior crop manifests, and model
  runs were not overwritten

Reason:

- prepare a new GPT prelabel batch comparable to the previous full API pass
- previous full GPT prelabel pass processed `2,185` marker-neighborhood ROI
  crops
- the new candidate queue should cover all current revision sets under
  `revision_sets/`, not only the earlier Rev `#1-#4` mix

Page filtering:

- new filtered page manifest:
  `CloudHammer/data/manifests/pages_standard_drawings_no_index_20260427.jsonl`
- kept only standard rendered drawing sheets: `12600 x 9000` pixels
- excluded letter/nonstandard pages, narrative/spec pages, and drawing index
  pages detected by PDF text
- filtering result:
  - source page rows: `332`
  - included standard non-index drawing pages: `115`
  - excluded nonstandard-size pages: `148`
  - excluded non-drawing page kinds: `62`
  - excluded index pages: `7`
- included pages by revision:
  - Rev `#1`: `49`
  - Rev `#2`: `27`
  - Rev `#3`: `26`
  - Rev `#4`: `5`
  - Rev `#5`: `6`
  - Rev `#7`: `2`

Marker candidate extraction:

- resolved marker manifest:
  `CloudHammer/data/manifests/roi_manifest_resolved_20260427.jsonl`
- target-marker crop manifest:
  `CloudHammer/data/manifests/cloud_roi_broad_candidates_20260427.jsonl`
- target-marker crop images:
  `CloudHammer/data/cloud_roi_images_broad_20260427`
- target-marker extraction result:
  - total crops: `2,143`
  - Rev `#1`: `1,571`
  - Rev `#2`: `208`
  - Rev `#3`: `150`
  - Rev `#4`: `214`
  - Rev `#5`: `0`
  - Rev `#7`: `0`

Important finding:

- Rev `#5` and Rev `#7` had detected markers only on pages excluded from the
  usable standard drawing set, mainly index pages
- therefore, random standard drawing-area crops were added so those revision
  sets are represented without using index pages

Random standard drawing supplement:

- output folder:
  `CloudHammer/data/random_drawing_crops_broad_20260427`
- crop count: `720`
- crop size: `1536`
- seed: `20260427`
- distribution: `120` crops per revision set for Rev `#1`, `#2`, `#3`, `#4`,
  `#5`, and `#7`

Proposed GPT prelabel queue:

- queue folder:
  `CloudHammer/data/gpt_prelabel_broad_20260427`
- queue manifest:
  `CloudHammer/data/gpt_prelabel_broad_20260427/manifest.jsonl`
- summary:
  `CloudHammer/data/gpt_prelabel_broad_20260427/summary.json`
- total queue size: `2,185`
- candidate sources:
  - target marker-neighborhood crops: `1,572`
  - random standard drawing crops: `613`
- counts by revision:
  - Rev `#1`: `1,093`
  - Rev `#2`: `301`
  - Rev `#3`: `243`
  - Rev `#4`: `308`
  - Rev `#5`: `120`
  - Rev `#7`: `120`

Prelabel output config for the eventual API run:

- `CloudHammer/configs/broad_gpt_prelabel_20260427.yaml`
- planned GPT outputs will go under:
  `CloudHammer/data/gpt_prelabel_broad_20260427`
- this keeps new API inputs, predictions, GPT labels, and review overlays
  separate from the old `api_cloud_*` folders

Sample preview:

- contact sheet:
  `CloudHammer/data/gpt_prelabel_broad_20260427/samples/sample_contact_sheet_by_revision.jpg`
- sample manifest:
  `CloudHammer/data/gpt_prelabel_broad_20260427/samples/sample_manifest.jsonl`

Next step:

- inspect the sample contact sheet before sending the queue through GPT
- if approved, run GPT prelabeling with model `gpt-5.4`, `detail=auto`,
  `max_dim=1024`, `image_format=jpeg`, and `min_confidence=0.60`

## 2026-04-27 - Broad GPT Prelabel API Run Started

Status:

- API run started
- output remains isolated under:
  `CloudHammer/data/gpt_prelabel_broad_20260427`
- old `api_cloud_*` folders were not reused

Crop-size check before launch:

- previous full API batch:
  - total crops: `2,185`
  - `1536 x 1536`: `1,110`
  - `2048 x 2048`: `1,075`
- new broad queue:
  - total crops: `2,185`
  - `1536 x 1536`: `1,426`
  - `2048 x 2048`: `759`
- conclusion: the new queue uses the same crop scale as the first full API
  batch; random supplement crops are `1536 x 1536`

Command:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe scripts\prelabel_cloud_rois_openai.py --config configs\broad_gpt_prelabel_20260427.yaml --manifest data\gpt_prelabel_broad_20260427\manifest.jsonl --model gpt-5.4 --detail auto --max-dim 1024 --min-confidence 0.60 --image-format jpeg --request-delay 1.0 --max-retries 5 --retry-initial-delay 3.0 --flush-every 10
```

Rate/retry settings:

- model: `gpt-5.4`
- detail: `auto`
- max image dimension sent to API: `1024`
- image format sent to API: `jpeg`
- min accepted box confidence: `0.60`
- request delay: `1.0` second
- max retries: `5`
- retry initial delay: `3.0` seconds
- prediction flush interval: `10`

Run logs:

- stdout:
  `CloudHammer/data/gpt_prelabel_broad_20260427/api_run_stdout.log`
- stderr:
  `CloudHammer/data/gpt_prelabel_broad_20260427/api_run_stderr.log`
- predictions:
  `CloudHammer/data/gpt_prelabel_broad_20260427/api_predictions/predictions.jsonl`
- GPT YOLO labels:
  `CloudHammer/data/gpt_prelabel_broad_20260427/gpt_labels`
- GPT review overlays:
  `CloudHammer/data/gpt_prelabel_broad_20260427/gpt_review`

Initial health check:

- process started successfully
- stderr was empty at first check
- first flush contained `10` successful prediction rows
- initial accepted-box distribution among those `10` rows:
  - `0` accepted boxes: `4`
  - `1` accepted box: `3`
  - `2` accepted boxes: `2`
  - `3` accepted boxes: `1`

## 2026-04-27 - GPT Post-Run Review Tooling Prepared

Status:

- implemented while the broad GPT API run was still active
- did not write to the live API output folders
- live API checks during this work were read-only

New helper module:

- `CloudHammer/cloudhammer/prelabel/gpt_review_queue.py`

New scripts:

- `CloudHammer/scripts/summarize_gpt_prelabels.py`
  - reads a `predictions.jsonl`
  - optionally compares against the source queue manifest
  - reports processed/expected counts, missing predictions, failures,
    cloud/no-cloud counts, confidence buckets, revision/source distribution,
    and proposed review buckets
- `CloudHammer/scripts/build_gpt_review_queues.py`
  - builds isolated LabelImg queues after the GPT run completes
  - requires an explicit `--output-dir`
  - refuses partial predictions by default unless `--allow-partial` is passed
  - never writes to `data/cloud_labels_reviewed`
  - copies selected images, GPT labels, and GPT overlays into separate queue
    folders

Planned post-run review buckets:

- `high_conf_positive`
- `ambiguous_positive`
- `weird_multi_faint_partial`
- `hard_negative_marker_no_cloud`
- `gpt_negative_spotcheck`

Example read-only summary command after completion:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe scripts\summarize_gpt_prelabels.py data\gpt_prelabel_broad_20260427\api_predictions\predictions.jsonl --manifest data\gpt_prelabel_broad_20260427\manifest.jsonl --output data\gpt_prelabel_broad_20260427\postrun_summary.json
```

Example review-queue build command after completion:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe scripts\build_gpt_review_queues.py --predictions data\gpt_prelabel_broad_20260427\api_predictions\predictions.jsonl --manifest data\gpt_prelabel_broad_20260427\manifest.jsonl --output-dir data\review_queues\broad_gpt_20260427 --max-per-queue 80
```

Verification:

- CloudHammer tests passed: `21 passed`

Live API read-only status during this tooling work:

- process was still running
- flushed prediction rows observed: `1120`
- live stdout had reached approximately `1126 / 2185`

## 2026-04-27 - Broad GPT Prelabel Run Completed

Status:

- API prelabel run completed
- manifest rows: `2185`
- prediction rows: `2185`
- skipped: `0`
- failed: `0`
- stderr: empty
- no remaining `prelabel_cloud_rois_openai.py` Python process was found after completion

Primary outputs:

- input payloads:
  `CloudHammer/data/gpt_prelabel_broad_20260427/api_inputs`
- predictions:
  `CloudHammer/data/gpt_prelabel_broad_20260427/api_predictions/predictions.jsonl`
- GPT YOLO labels:
  `CloudHammer/data/gpt_prelabel_broad_20260427/gpt_labels`
- GPT review overlays:
  `CloudHammer/data/gpt_prelabel_broad_20260427/gpt_review`
- stdout:
  `CloudHammer/data/gpt_prelabel_broad_20260427/api_run_stdout.log`
- stderr:
  `CloudHammer/data/gpt_prelabel_broad_20260427/api_run_stderr.log`

Prediction summary:

- `1197` crops were marked as containing at least one cloud
- `988` crops were marked as no-cloud
- accepted-box distribution included:
  - `0` boxes: `990`
  - `1` box: `588`
  - `2` boxes: `289`
  - `3+` boxes: `318`

Proposed review buckets from the full run:

- `high_conf_positive`: `244`
- `ambiguous_positive`: `9`
- `weird_multi_faint_partial`: `944`
- `hard_negative_marker_no_cloud`: `490`
- `gpt_negative_spotcheck`: `498`

Isolated review queues were built at:

- `CloudHammer/data/review_queues/broad_gpt_20260427`

Queue contents:

- `high_conf_positive`: `80` images, labels, and overlays copied
- `ambiguous_positive`: `9` images, labels, and overlays copied
- `weird_multi_faint_partial`: `80` images, labels, and overlays copied
- `hard_negative_marker_no_cloud`: `80` images, labels, and overlays copied
- `gpt_negative_spotcheck`: `80` images, labels, and overlays copied

These queues are review-only working copies. They do not replace or mutate
`CloudHammer/data/cloud_labels_reviewed`.

## 2026-04-27 - LabelImg Resume And Crash Logging Added For Broad GPT Queue

Context:

- LabelImg crashed during review of:
  `CloudHammer/data/review_queues/broad_gpt_20260427/weird_multi_faint_partial`
- Timestamp review found `20 / 80` queue items with `.review.json` sidecar
  markers from the current review session.
- First unreviewed queue item was item `21 / 80`:
  `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_random_0081.png`

Launcher update:

- `CloudHammer/scripts/launch_random_gpt_review_queue.py` now resumes at the
  first queue image missing a `.review.json` marker by default.
- `--start-first` can still force opening from item `1`.
- `--start-index N` can force a specific 1-based queue item.
- launcher writes a sliced image list such as `images_from_021.txt` for resume
  launches.
- launcher writes per-run logs and metadata under each queue's
  `labelimg_logs` folder.
- launcher enables `PYTHONFAULTHANDLER=1` and `PYTHONUNBUFFERED=1` for better
  traceback capture if the GUI crashes.

Current resumed launch:

- queue:
  `CloudHammer/data/review_queues/broad_gpt_20260427/weird_multi_faint_partial`
- start item: `21 / 80`
- image list:
  `CloudHammer/data/review_queues/broad_gpt_20260427/weird_multi_faint_partial/images_from_021.txt`
- logs:
  `CloudHammer/data/review_queues/broad_gpt_20260427/weird_multi_faint_partial/labelimg_logs`
- launch metadata:
  `CloudHammer/data/review_queues/broad_gpt_20260427/weird_multi_faint_partial/labelimg_logs/labelimg_20260427_214826.launch.json`

## 2026-04-27 - Near-Duplicate Review Handling Added

Reason:

- broad GPT review queues contain near-duplicate crops from the same page area
  with only small crop shifts
- these are low-value manual review items after one representative crop has
  already been corrected
- including many near-identical crops can overweight one drawing/page family and
  inflate apparent performance if validation is not grouped by source

Behavior added:

- `CloudHammer/scripts/launch_random_gpt_review_queue.py` now treats either
  `.review.json` or `.duplicate.json` as a completed queue item when resuming.
- local LabelImg package was patched with a `Skip Duplicate` action:
  - shortcut: `Ctrl+K`
  - writes `<image_stem>.duplicate.json` beside the queue label file
  - does not write a `.review.json`
  - does not make the GPT label training truth
  - advances to the next image
- duplicate markers are review workflow metadata only. They should be excluded
  from future training-manifest creation unless we explicitly implement label
  propagation from a reviewed representative.

Relaunch after second crash:

- queue:
  `CloudHammer/data/review_queues/broad_gpt_20260427/weird_multi_faint_partial`
- completed markers before relaunch: `34 / 80`
- duplicate skip markers before relaunch: `0`
- start item: `35 / 80`
- start image:
  `260303-VA_Biloxi_Rev_5_RFI-126_56f520d9_p0004_random_0379.png`
- image list:
  `CloudHammer/data/review_queues/broad_gpt_20260427/weird_multi_faint_partial/images_from_035.txt`
- launch metadata:
  `CloudHammer/data/review_queues/broad_gpt_20260427/weird_multi_faint_partial/labelimg_logs/labelimg_20260427_220736.launch.json`

## 2026-04-27 - Pre-GPT Aggressive Crop Deduplication Added

Decision:

- Do not use `Ctrl+K` / `.duplicate.json` markers as truth.
- Do not use manual duplicate memory as an exclusion source for future GPT
  candidate selection.
- Use code-level same-page crop geometry instead.

Launcher adjustment:

- `CloudHammer/scripts/launch_random_gpt_review_queue.py` now ignores
  `.duplicate.json` markers by default when resuming.
- `.review.json` remains the only default resume-completion marker.
- `--respect-duplicate-skips` exists only as an explicit override.

New pre-GPT dedupe code:

- `CloudHammer/cloudhammer/prelabel/manifest_dedupe.py`
- `CloudHammer/scripts/dedupe_gpt_manifest.py`

Rule:

- group candidates by `pdf_path + page_index`
- compare crop boxes from `roi_bbox_page`, `bbox_on_page`, or
  `crop_box_page`
- exclude later candidates from the same page when either:
  - IoU is at least `0.30`, or
  - intersection covers at least `0.65` of the smaller crop
- prefer target marker-neighborhood crops over random drawing crops
- prefer centered/high-scoring/high-ink candidates when choosing a keeper
- never reads `.duplicate.json`

Preview on the already-sent broad GPT manifest:

- input rows: `2185`
- kept rows: `1097`
- excluded same-page overlapping crops: `1088`
- kept by source:
  - `target_marker_neighborhood`: `662`
  - `random_standard_drawing_crop`: `435`
- excluded by source:
  - `target_marker_neighborhood`: `910`
  - `random_standard_drawing_crop`: `178`
- preview summary:
  `CloudHammer/data/gpt_prelabel_broad_20260427/dedupe_aggressive_preview_summary.json`
- preview excluded rows:
  `CloudHammer/data/gpt_prelabel_broad_20260427/dedupe_aggressive_preview_excluded.jsonl`

Verification:

- CloudHammer tests passed: `23 passed`

## 2026-04-27 - Dedupe-Kept Review Queues Built From Existing GPT Output

Decision:

- no API resend is needed
- use the existing completed GPT predictions from:
  `CloudHammer/data/gpt_prelabel_broad_20260427/api_predictions/predictions.jsonl`
- build a fresh dedupe-kept review queue set instead of deleting/mutating the
  original `broad_gpt_20260427` queues

Dedupe manifests:

- kept:
  `CloudHammer/data/gpt_prelabel_broad_20260427/manifest_deduped_aggressive.jsonl`
- excluded:
  `CloudHammer/data/gpt_prelabel_broad_20260427/manifest_deduped_aggressive_excluded.jsonl`
- summary:
  `CloudHammer/data/gpt_prelabel_broad_20260427/dedupe_aggressive_summary.json`

Fresh dedupe-kept queues:

- root:
  `CloudHammer/data/review_queues/broad_gpt_20260427_deduped`
- source manifest:
  `CloudHammer/data/gpt_prelabel_broad_20260427/manifest_deduped_aggressive.jsonl`
- built with `--filter-to-manifest`, so only dedupe-kept predictions were
  selected

Deduped prediction pool:

- total kept predictions: `1097`
- review bucket counts in the dedupe-kept pool:
  - `weird_multi_faint_partial`: `361`
  - `gpt_negative_spotcheck`: `373`
  - `hard_negative_marker_no_cloud`: `240`
  - `high_conf_positive`: `119`
  - `ambiguous_positive`: `4`

Queue files created:

- `high_conf_positive`: `80`
- `ambiguous_positive`: `4`
- `weird_multi_faint_partial`: `80`
- `hard_negative_marker_no_cloud`: `80`
- `gpt_negative_spotcheck`: `80`

Human-reviewed carryover:

- copied `28` real `.review.json` human-reviewed labels from the old queue set
  into the new dedupe-kept queues when the same `cloud_roi_id` survived
  selection
- did not carry over `.duplicate.json` markers
- `49` old reviewed items were not copied because they were either geometry
  dedupe exclusions or were not selected into the capped dedupe-kept queue set

Current next review launch:

- queue:
  `CloudHammer/data/review_queues/broad_gpt_20260427_deduped/hard_negative_marker_no_cloud`
- start item: `1 / 80`
- start image:
  `260313_-_VA_Biloxi_Rev_3_ff19da68_p0174_m005.png`
- LabelImg PID: `28076`
- launch metadata:
  `CloudHammer/data/review_queues/broad_gpt_20260427_deduped/hard_negative_marker_no_cloud/labelimg_logs/labelimg_20260427_224149.launch.json`

Completion:

- reviewed markers: `80 / 80`
- duplicate skip markers: `0`
- last reviewed item:
  `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3_p0011_m009.png`
- last reviewed timestamp: `2026-04-27 22:52:13`
- LabelImg process was no longer running at the completion check

## 2026-04-27 - Dedupe-Kept Weird/Multi/Faint Review Relaunched

Queue:

- `CloudHammer/data/review_queues/broad_gpt_20260427_deduped/weird_multi_faint_partial`

Launch state:

- queue rows: `80`
- reviewed markers before launch: `28`
- duplicate markers before launch: `0`
- first unreviewed item by `.review.json`: `2 / 80`
- start image:
  `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_m057.png`
- image list:
  `CloudHammer/data/review_queues/broad_gpt_20260427_deduped/weird_multi_faint_partial/images_from_002.txt`
- LabelImg PID: `21036`
- launch metadata:
  `CloudHammer/data/review_queues/broad_gpt_20260427_deduped/weird_multi_faint_partial/labelimg_logs/labelimg_20260427_230930.launch.json`

Completion state before moving on:

- real reviewed markers: `79 / 80`
- duplicate markers: `1`
- the duplicate marker is not training truth
- unresolved non-reviewed item:
  `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_m037.png`
- decision: leave the duplicate-marked item out of reviewed training truth and
  continue to the next review bucket

## 2026-04-27 - Dedupe-Kept High-Confidence Positive Review Launched

Queue:

- `CloudHammer/data/review_queues/broad_gpt_20260427_deduped/high_conf_positive`

Launch state:

- queue rows: `80`
- reviewed markers before launch: `0`
- duplicate markers before launch: `0`
- start item: `1 / 80`
- start image:
  `260313_-_VA_Biloxi_Rev_3_ff19da68_p0176_m001.png`
- LabelImg PID: `19516`
- launch metadata:
  `CloudHammer/data/review_queues/broad_gpt_20260427_deduped/high_conf_positive/labelimg_logs/labelimg_20260427_233311.launch.json`

Completion:

- reviewed markers: `80 / 80`
- duplicate skip markers: `0`
- last reviewed item:
  `Revision_1_-_Drawing_Changes_6cbee960_p0046_m026.png`
- last reviewed timestamp: `2026-04-27 23:56:24`
- LabelImg process was no longer running at the completion check

## 2026-04-27 - Dedupe-Kept Ambiguous Positive Review Launched

Queue:

- `CloudHammer/data/review_queues/broad_gpt_20260427_deduped/ambiguous_positive`

Launch state:

- queue rows: `4`
- reviewed markers before launch: `0`
- duplicate markers before launch: `0`
- start item: `1 / 4`
- start image:
  `Revision_1_-_Drawing_Changes_6cbee960_p0012_m029.png`
- LabelImg PID: `30468`
- launch metadata:
  `CloudHammer/data/review_queues/broad_gpt_20260427_deduped/ambiguous_positive/labelimg_logs/labelimg_20260427_235731.launch.json`

Completion:

- reviewed markers: `4 / 4`
- duplicate skip markers: `0`
- LabelImg process was no longer running at the training-prep check

## 2026-04-28 - Combined Training Manifest Prepared

Input reviewed sources:

- previous trusted manifest:
  `CloudHammer/data/manifests/reviewed_batch_001_002_plus_004partial_current_20260427.jsonl`
- dedupe-kept review queues:
  `CloudHammer/data/review_queues/broad_gpt_20260427_deduped`

Queue review state included:

- `hard_negative_marker_no_cloud`: `80 / 80` real reviewed labels
- `weird_multi_faint_partial`: `79 / 80` real reviewed labels
  - the remaining item has a `.duplicate.json` marker only and is not training
    truth
- `high_conf_positive`: `80 / 80` real reviewed labels
- `ambiguous_positive`: `4 / 4` real reviewed labels
- `gpt_negative_spotcheck`: `0 / 80` reviewed labels, not included

New helper:

- `CloudHammer/scripts/create_combined_reviewed_manifest.py`

Output manifest:

- `CloudHammer/data/manifests/reviewed_batch_001_002_004partial_plus_broad_deduped_20260428.jsonl`

Summary:

- total rows: `893`
- prior/base rows: `723`
- new review-queue rows added: `170`
- duplicate `cloud_roi_id`s skipped: `73`
- cloud-positive rows: `639`
- empty negative rows: `254`
- split counts:
  - train: `690`
  - val: `203`

New queue rows by source queue after duplicate-id skipping:

- `ambiguous_positive`: `4`
- `hard_negative_marker_no_cloud`: `41`
- `high_conf_positive`: `51`
- `weird_multi_faint_partial`: `74`

YOLO preflight dataset:

- `CloudHammer/data/yolo_reviewed_batch_001_002_004partial_plus_broad_deduped_20260428`
- dataset YAML:
  `CloudHammer/data/yolo_reviewed_batch_001_002_004partial_plus_broad_deduped_20260428/cloudhammer.yaml`
- train split: `690` images / `690` labels
  - positives: `490`
  - empty negatives: `200`
- val split: `203` images / `203` labels
  - positives: `149`
  - empty negatives: `54`

Verification:

- YOLO dataset build completed without invalid-label errors
- CloudHammer tests passed: `23 passed`

Ready training command:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe scripts\train_roi_detector.py --roi-manifest data\manifests\reviewed_batch_001_002_004partial_plus_broad_deduped_20260428.jsonl --dataset-dir data\yolo_reviewed_batch_001_002_004partial_plus_broad_deduped_20260428 --name cloudhammer_roi-broad-deduped-20260428
```

## 2026-04-28 - Broad Deduped ROI Detector Trained

Training command:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe scripts\train_roi_detector.py --roi-manifest data\manifests\reviewed_batch_001_002_004partial_plus_broad_deduped_20260428.jsonl --dataset-dir data\yolo_reviewed_batch_001_002_004partial_plus_broad_deduped_20260428 --name cloudhammer_roi-broad-deduped-20260428
```

Run:

- `CloudHammer/runs/cloudhammer_roi-broad-deduped-20260428`
- best weights:
  `CloudHammer/runs/cloudhammer_roi-broad-deduped-20260428/weights/best.pt`
- last weights:
  `CloudHammer/runs/cloudhammer_roi-broad-deduped-20260428/weights/last.pt`

Training setup:

- model: `yolov8n.pt`
- epochs: `50`
- image size: `640`
- batch: `16`
- device: CUDA on `NVIDIA GeForce RTX 4070 Ti SUPER`
- training duration reported by Ultralytics: `0.115` hours

Dataset:

- manifest:
  `CloudHammer/data/manifests/reviewed_batch_001_002_004partial_plus_broad_deduped_20260428.jsonl`
- YOLO dataset:
  `CloudHammer/data/yolo_reviewed_batch_001_002_004partial_plus_broad_deduped_20260428`
- train: `690` images, `200` backgrounds
- val: `203` images, `54` backgrounds
- val instances: `325`

Best/final validation metrics on this run's val split:

- precision: `0.908`
- recall: `0.912`
- mAP50: `0.923`
- mAP50-95: `0.759`
- best mAP50-95 occurred at epoch `50`
- best mAP50 occurred at epoch `48` with mAP50 `0.924`

Notes:

- Training completed successfully.
- A follow-up apples-to-apples validation comparison against prior models was
  attempted but exceeded the tool timeout before returning metrics.
- No lingering validation/training Python process was found after the timeout
  check.

## 2026-04-28 - Broad Deduped Apples-to-Apples Eval Completed

The prior comparison timeout was rerun with `workers=0` on Windows and completed
successfully.

Eval target:

- dataset YAML:
  `CloudHammer/data/yolo_reviewed_batch_001_002_004partial_plus_broad_deduped_20260428/cloudhammer.yaml`
- validation split: `203` images, `325` cloud instances
- metrics JSON:
  `CloudHammer/runs/eval_broad_deduped_20260428_metrics.json`
- eval output root:
  `CloudHammer/runs/eval_broad_deduped_20260428`

Model comparison on the same validation split:

| Model | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| `cloudhammer_roi-3` | `0.907` | `0.862` | `0.915` | `0.755` |
| `cloudhammer_roi-hardneg-20260427` | `0.880` | `0.880` | `0.893` | `0.742` |
| `cloudhammer_roi-broad-deduped-20260428` | `0.908` | `0.912` | `0.923` | `0.755` |

Readout:

- `cloudhammer_roi-broad-deduped-20260428` is the best current candidate by
  recall and mAP50 on this validation split.
- mAP50-95 is essentially tied with `cloudhammer_roi-3`, but the new model has
  a materially better recall profile on the newly reviewed broad/deduped data.
- This is still an in-family crop validation set, not a true unknown full-page
  drawing test. The next quality check should be qualitative full-page inference
  on held-out standard drawing pages from the revision sets.

## 2026-04-28 - Broad Deduped Full-Page Qualitative Eval Sample

Purpose:

- Run a non-destructive full-page tiled inference check using the new
  `cloudhammer_roi-broad-deduped-20260428` weights.
- Use standard non-index drawing pages from the broad page manifest.
- Keep eval outputs out of the normal `CloudHammer/outputs` tree.

One-off eval config:

- `CloudHammer/configs/fullpage_eval_broad_deduped_20260428.yaml`
- output root:
  `CloudHammer/runs/fullpage_eval_broad_deduped_20260428/outputs`

Sample manifest:

- `CloudHammer/data/manifests/fullpage_eval_sample_broad_deduped_20260428.jsonl`
- `14` pages total
- selected up to `2` standard non-index drawing pages per source PDF stem

Inference command:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe scripts\infer_pages.py --config configs\fullpage_eval_broad_deduped_20260428.yaml --model runs\cloudhammer_roi-broad-deduped-20260428\weights\best.pt --pages-manifest data\manifests\fullpage_eval_sample_broad_deduped_20260428.jsonl
```

Runtime fix discovered during eval:

- Full-page inference was feeding grayscale page tiles directly to YOLO.
- The trained detector expects `3` input channels.
- Patched `CloudHammer/cloudhammer/infer/detect.py` to convert each grayscale
  tile to BGR before prediction.
- Added regression coverage in `CloudHammer/tests/test_cloudhammer.py`.
- Verification after patch: `24 passed`.

Full-page sample outputs:

- detection JSON files: `8`
- overlay PNGs: `14`
- detection crops: `72`

Detection counts by source:

| Source PDF stem | Pages | Detections | Max confidence |
| --- | ---: | ---: | ---: |
| `260219 - VA Biloxi Rev 4_Plumbing 1` | `2` | `15` | `0.917` |
| `260303-VA Biloxi Rev 5 RFI-126` | `2` | `12` | `0.947` |
| `260309 - Drawing Rev2- Steel Grab Bars` | `2` | `5` | `0.946` |
| `260313 - VA Biloxi Rev 3` | `2` | `4` | `0.901` |
| `Drawing Rev2- Steel Grab Bars AE107` | `1` | `2` | `0.865` |
| `Drawing Rev2- Steel Grab Bars R1 AE107.1` | `1` | `2` | `0.954` |
| `Revision #1 - Drawing Changes` | `2` | `10` | `0.959` |
| `Revision Set #7` | `2` | `22` | `0.975` |

Readout:

- The qualitative full-page eval ran successfully after the inference input
  channel fix.
- These outputs are for visual inspection, not a scored unknown-set metric,
  because there is no full-page ground truth manifest for these pages yet.

## 2026-04-28 - Full-Page Eval Audit Pack Created

Generated a compact audit pack from the `14` full-page eval overlays and `72`
detected crops.

Artifacts:

- overlay contact sheet:
  `CloudHammer/runs/fullpage_eval_broad_deduped_20260428/audit/overlay_contact_sheet.png`
- detection crop contact sheet:
  `CloudHammer/runs/fullpage_eval_broad_deduped_20260428/audit/detection_crop_contact_sheet.png`
- markdown summary:
  `CloudHammer/runs/fullpage_eval_broad_deduped_20260428/audit/audit_summary.md`
- JSON summary:
  `CloudHammer/runs/fullpage_eval_broad_deduped_20260428/audit/audit_summary.json`

Sanity check:

- Contact sheets were opened locally and are nonblank.
- The overlay sheet shows all `14` evaluated pages.
- The crop sheet shows all `72` detections sorted by confidence.

Initial readout:

- The detector is catching many obvious cloud motifs on full-page drawings.
- Large/detail clouds can still fragment into multiple partial detections,
  especially on pages with large clouded detail regions.
- `Revision Set #7` page `4` is currently the highest-density stress sample
  in this small audit set, with `19` detections.

## 2026-04-28 - Large Cloud Context Labeling Utility Added

Reason:

- Full-page qualitative eval shows the current detector is strong at local cloud
  motifs but can fragment large/detail clouds into multiple partial detections.
- We need a way to create whole-cloud context examples without relying on PDF
  viewer zoom or one-off screenshots.

Utility:

- `CloudHammer/utilities/large_cloud_context_labeler.py`
- docs:
  `CloudHammer/utilities/README.md`

Purpose:

- Open standardized rendered page images or a page manifest.
- Draw whole-cloud label boxes in source rendered-page coordinates.
- Draw or auto-generate a square context crop around the labels.
- Support multiple labeled regions per source page.
- Save both full-page coordinates and crop-local coordinates.
- Export the actual crop PNGs for later training-set construction.

Default launch:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe utilities\large_cloud_context_labeler.py --manifest data\manifests\pages_standard_drawings_no_index_20260427.jsonl
```

Default outputs:

- sidecar JSON:
  `CloudHammer/data/large_cloud_context_labels/*.largecloud.json`
- exported crop PNGs:
  `CloudHammer/data/large_cloud_context_crops/*.png`

Schema:

- `cloudhammer.large_cloud_context.v1`
- coordinate space: `source_image_pixels`
- default class name: `cloud_whole`
- each source image can contain multiple `regions`
- each region can contain one `crop_box` plus multiple `labels`

Verification:

- CLI help works.
- CloudHammer tests passed: `26 passed`.

## 2026-04-28 - Large Cloud Context Utility Launched On Stress Pages

Created a prioritized stress-page manifest from the `14` full-page qualitative
eval pages, sorted by detector fragment count.

Manifest:

- `CloudHammer/data/manifests/large_cloud_context_stress_pages_20260428.jsonl`
- rows: `14`
- first page: `Revision Set #7`, page `4`, with `19` detector fragments in the
  full-page eval sample

Launch command:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe utilities\large_cloud_context_labeler.py --manifest data\manifests\large_cloud_context_stress_pages_20260428.jsonl --output-dir data\large_cloud_context_labels_20260428 --crop-dir data\large_cloud_context_crops_20260428
```

Expected outputs from this labeling pass:

- sidecar JSON:
  `CloudHammer/data/large_cloud_context_labels_20260428/*.largecloud.json`
- exported square context crops:
  `CloudHammer/data/large_cloud_context_crops_20260428/*.png`

## 2026-04-28 - Large Cloud Context Utility Crash Fix

Issue:

- The first user rectangle draw crashed as soon as the mouse was released.
- Reproduced with a headless smoke path.
- Root cause was a PyQt brush type error when repainting the newly created
  rectangle item.

Fix:

- Patched `CloudHammer/utilities/large_cloud_context_labeler.py` to use
  `QBrush(Qt.NoBrush)` and `QBrush(color)` where PyQt requires brush objects.
- Added a GUI smoke regression test for drawing saved regions on the canvas.
- Added utility exception logging to:
  `CloudHammer/data/large_cloud_context_labels_20260428/large_cloud_context_labeler.log`
- Added in-app help on `H`.
- Updated `CloudHammer/utilities/README.md` with the recommended workflow.

Verification:

- Headless draw smoke passed.
- CloudHammer tests passed: `27 passed`.

Relaunched on the same stress manifest with stdout/stderr capture:

- stdout:
  `CloudHammer/data/large_cloud_context_labels_20260428/launch_stdout.log`
- stderr:
  `CloudHammer/data/large_cloud_context_labels_20260428/launch_stderr.log`
- exception log:
  `CloudHammer/data/large_cloud_context_labels_20260428/large_cloud_context_labeler.log`

## 2026-04-28 - Revision Set 1 Large Context Labeler Launch

Created and launched a Revision Set 1-only manifest for manual large-cloud
context labeling.

Manifest:

- `CloudHammer/data/manifests/large_cloud_context_revision1_pages_20260428.jsonl`
- rows: `49`
- source filter: `pdf_stem == "Revision #1 - Drawing Changes"`
- source catalog: standard non-index drawing pages from
  `CloudHammer/data/manifests/pages_standard_drawings_no_index_20260427.jsonl`

Launch command:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe utilities\large_cloud_context_labeler.py --manifest data\manifests\large_cloud_context_revision1_pages_20260428.jsonl --output-dir data\large_cloud_context_labels_20260428 --crop-dir data\large_cloud_context_crops_20260428
```

Logs:

- stdout:
  `CloudHammer/data/large_cloud_context_labels_20260428/revision1_launch_stdout.log`
- stderr:
  `CloudHammer/data/large_cloud_context_labels_20260428/revision1_launch_stderr.log`

## 2026-04-28 - Large Context Review Pass Completed

The user completed the Revision Set 1 large-context pass after the initial
stress-page pass.

Saved artifacts:

- label sidecars:
  `CloudHammer/data/large_cloud_context_labels_20260428/*.largecloud.json`
- exported crop PNGs:
  `CloudHammer/data/large_cloud_context_crops_20260428/*.png`
- saved-set summary:
  `CloudHammer/data/large_cloud_context_labels_20260428/large_context_summary_20260428.json`
- crop audit contact sheet:
  `CloudHammer/runs/large_cloud_context_audit_20260428/large_context_crop_contact_sheet.png`
- crop audit summary:
  `CloudHammer/runs/large_cloud_context_audit_20260428/large_context_crop_audit_summary.md`

Counts:

- sidecar JSON files: `37`
  - stress/sample pages: `10`
  - Revision Set 1 pages: `27`
- exported context crop PNGs: `67`
- regions total: `68`
- regions with crop: `67`
- regions with labels: `67`
- whole-cloud labels: `78`
- empty regions: `1`
  - `Revision_1_-_Drawing_Changes_6cbee960_p0011.largecloud.json`, `region_004`
  - this region has no crop and no labels and should be ignored downstream
- missing crop paths: `0`

Initial audit readout:

- The generated contact sheet is nonblank and shows the saved crops with
  green whole-cloud boxes overlaid.
- The set is useful as whole-cloud/context supervision, but it is still too
  small and skewed toward Revision Set 1 to replace the motif detector.
- Best immediate use is to support a fragment-grouping prototype and/or a
  small experimental whole-cloud-context detector.

## 2026-04-28 - Fragment Grouping Prototype Implemented

Goal:

- Use the current motif detector's full-page detections as cloud-edge fragment
  proposals.
- Group nearby/related fragments into whole-cloud candidate boxes.
- Produce inspectable outputs before any retraining.

Code:

- `CloudHammer/cloudhammer/infer/fragment_grouping.py`
- `CloudHammer/scripts/group_fragment_detections.py`
- detection contract updated to allow `source_mode == "fragment_group"` and
  optional detection metadata

Grouping behavior:

- expands each motif-fragment box
- connects intersecting expanded boxes into components
- recursively splits oversized low-fill components when large center gaps
  suggest multiple whole-cloud candidates
- emits grouped `CloudDetection` records with metadata:
  - member count
  - source fragment indexes
  - source member boxes
  - confidence list
  - fill ratio

Verification:

- CloudHammer tests passed: `30 passed`

## 2026-04-28 - Fragment Grouping Full Standard-Page Run

Ran the current broad-deduped motif detector over all standard non-index drawing
pages, then grouped those full-page detections.

Full-page inference config:

- `CloudHammer/configs/fullpage_all_broad_deduped_20260428.yaml`
- output root:
  `CloudHammer/runs/fullpage_all_broad_deduped_20260428/outputs`

Full-page inference command:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe scripts\infer_pages.py --config configs\fullpage_all_broad_deduped_20260428.yaml --model runs\cloudhammer_roi-broad-deduped-20260428\weights\best.pt --pages-manifest data\manifests\pages_standard_drawings_no_index_20260427.jsonl
```

Grouping command:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe scripts\group_fragment_detections.py --detections-dir runs\fullpage_all_broad_deduped_20260428\outputs\detections --output-dir runs\fragment_grouping_fullpage_all_broad_deduped_20260428 --split-max-fill-ratio 0.45
```

Grouped output artifacts:

- grouped detection JSON:
  `CloudHammer/runs/fragment_grouping_fullpage_all_broad_deduped_20260428/detections_grouped`
- grouped overlays:
  `CloudHammer/runs/fragment_grouping_fullpage_all_broad_deduped_20260428/overlays`
- full summary:
  `CloudHammer/runs/fragment_grouping_fullpage_all_broad_deduped_20260428/fragment_grouping_summary.md`
- compact audit:
  `CloudHammer/runs/fragment_grouping_fullpage_all_broad_deduped_20260428/fragment_grouping_compact_audit.md`
- top-stress contact sheet:
  `CloudHammer/runs/fragment_grouping_fullpage_all_broad_deduped_20260428/fragment_grouping_top_stress_contact_sheet.png`

Full standard-page grouping totals:

- pages: `115`
- motif fragments: `964`
- grouped whole-cloud candidates: `260`
- multi-fragment groups: `183`

By source:

| Source | Pages | Fragments | Groups | Multi groups | Largest group |
| --- | ---: | ---: | ---: | ---: | ---: |
| `260219 - VA Biloxi Rev 4_Plumbing 1` | `5` | `36` | `15` | `7` | `6` |
| `260303-VA Biloxi Rev 5 RFI-126` | `6` | `45` | `13` | `8` | `10` |
| `260309 - Drawing Rev2- Steel Grab Bars` | `25` | `142` | `34` | `24` | `49` |
| `260313 - VA Biloxi Rev 3` | `26` | `177` | `37` | `36` | `18` |
| `Drawing Rev2- Steel Grab Bars AE107` | `1` | `2` | `1` | `1` | `2` |
| `Drawing Rev2- Steel Grab Bars R1 AE107.1` | `1` | `2` | `1` | `1` | `2` |
| `Revision #1 - Drawing Changes` | `49` | `538` | `155` | `102` | `24` |
| `Revision Set #7` | `2` | `22` | `4` | `4` | `7` |

Readout:

- The full pipeline now exists: motif full-page inference -> grouped
  whole-cloud candidate boxes -> grouped overlays and JSON.
- The grouped output is not final production quality yet. The top-stress sheet
  shows likely false-positive/overgroup targets around dense schedule/table
  drawings and some large page detail regions.
- `Revision Set #7` page `4` improved from `19` fragments to `3` grouped
  candidates with the split-enabled grouping pass, matching the intended
  direction for large-cloud fragmentation.
- Next best step is qualitative review/tuning of the top-stress grouped
  overlays, then add post-group filters or a verifier before treating grouped
  candidates as final detections.

## 2026-04-28 - Whole-Cloud Candidate Review Completed

Goal:

- Hand-review the broad whole-cloud candidate export to separate deliverable
  candidates from false positives and grouping failures.
- Preserve the review labels as reusable feedback for filtering, grouping
  tuning, and future verifier training.

Reviewed source run:

- `CloudHammer/runs/whole_cloud_candidates_broad_deduped_lowconf_context_20260428`

Review tooling:

- `CloudHammer/utilities/whole_cloud_candidate_reviewer.py`
- review log:
  `CloudHammer/data/whole_cloud_candidate_reviews/whole_cloud_candidates_broad_deduped_lowconf_context_20260428.review.jsonl`
- review analyzer:
  `CloudHammer/scripts/analyze_whole_cloud_candidate_reviews.py`
- reviewed artifact exporter:
  `CloudHammer/scripts/export_reviewed_whole_cloud_artifacts.py`

Review results:

- candidates reviewed: `283 / 283`
- accepted: `173`
- false positives: `50`
- overmerged: `51`
- partial: `9`
- overall accept rate: `61.1%`

Accepted artifact bundle:

- output:
  `CloudHammer/runs/whole_cloud_candidates_broad_deduped_lowconf_context_20260428/reviewed_artifacts`
- accepted crop artifacts copied: `173`
- accepted manifest:
  `reviewed_artifacts/accepted_whole_cloud_candidates.jsonl`
- issue feedback manifests:
  - `reviewed_artifacts/feedback_false_positive_candidates.jsonl`
  - `reviewed_artifacts/feedback_overmerged_candidates.jsonl`
  - `reviewed_artifacts/feedback_partial_candidates.jsonl`
  - `reviewed_artifacts/feedback_issue_candidates.jsonl`

Important readout:

- Low-confidence candidates were mostly false positives:
  - confidence `< 0.50`: `1 / 39` accepted
  - confidence `0.50-0.65`: `4 / 16` accepted
- Very high confidence did not mean deliverable-ready. The `0.97-1.01`
  bucket was often overmerged: `23 / 52` accepted, `28` overmerged.
- Overmerge is primarily a grouping/splitting problem, not a confidence
  threshold problem.
- The accepted set is immediately useful as reviewed whole-cloud crop
  artifacts. The issue set is useful as feedback for post-group filters,
  overmerge splitting rules, and a later verifier.

Verification:

- review analysis generated successfully
- reviewed artifact export generated successfully
- CloudHammer tests passed: `33 passed`

## 2026-04-28 - Whole-Cloud Candidate Policy v1

Goal:

- Use the completed 283-candidate review pass to build a measurable routing
  policy for whole-cloud candidates.
- Separate high-trust deliverable candidates from obvious false positives and
  overmerge/split-risk candidates before deeper model or grouping work.

Code:

- `CloudHammer/cloudhammer/infer/candidate_policy.py`
- `CloudHammer/scripts/apply_whole_cloud_candidate_policy.py`

Policy v1 output:

- `CloudHammer/runs/whole_cloud_candidates_broad_deduped_lowconf_context_20260428/policy_v1`

Measured on reviewed candidates:

| Bucket | Total | Accepted | Issues | Accept Rate |
| --- | ---: | ---: | ---: | ---: |
| `auto_deliverable_candidate` | `110` | `101` | `9` | `91.8%` |
| `likely_false_positive` | `32` | `0` | `32` | `0.0%` |
| `low_priority_review` | `23` | `5` | `18` | `21.7%` |
| `needs_split_review` | `37` | `10` | `27` | `27.0%` |
| `review_candidate` | `81` | `57` | `24` | `70.4%` |

Readout:

- A conservative policy can remove `32` obvious junk candidates without losing
  reviewed accepts in this pass.
- The high-trust bucket gives a useful immediate deliverable queue:
  `110` candidates at `91.8%` accept rate.
- The split-risk bucket is mostly true overmerge and should drive the next
  grouping/splitting iteration.

Verification:

- CloudHammer tests passed: `34 passed`
