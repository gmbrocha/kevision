# CloudHammer

Status: current source of truth for CloudHammer pipeline, labeling, prelabeling,
training, inference, and integration boundaries.

CloudHammer is the computer-vision child project inside KEVISION. Its job is
narrow: detect scalloped revision-cloud motifs on real blueprint pages and emit
clean artifacts that the main product can consume later.

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
```

Training:

```powershell
python scripts/train_roi_detector.py --roi-manifest data\manifests\reviewed_batch_001_priority_train.jsonl --model yolov8n.pt --imgsz 640 --epochs 50 --batch 16
```

Inference:

```powershell
python scripts/infer_pages.py --model runs/cloudhammer_roi\weights\best.pt --limit 5
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

1. Keep reviewing high-value batch labels.
2. Regenerate reviewed-only manifests after review progress.
3. Train the first reviewed-label ROI detector on GPU.
4. Inspect validation predictions and failure modes.
5. Benchmark/filter GPT labels before using them as pseudo-labels.
6. Graduate from ROI-only inference toward tiled full-page cloud-first
   inference.
7. Emit JSON/crops/overlays clean enough for backend integration.
