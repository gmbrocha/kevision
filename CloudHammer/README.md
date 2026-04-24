# CloudHammer

CloudHammer is the computer-vision child project inside `KEVISION`.

It owns the revision-cloud model workflow:

- drawing page cataloging and rasterization
- marker ROI extraction used as context
- cloud ROI extraction
- API prelabel generation for review acceleration
- LabelImg review prep
- one-class `cloud_motif` training
- page inference and model-facing outputs

It does **not** own the broader deliverable-building workflow, review UI, or
backend orchestration logic.

## Quick Start

From `CloudHammer/`:

```powershell
python scripts/catalog_pages.py --no-render
python scripts/catalog_pages.py --limit 5 --overwrite
python scripts/run_delta_bootstrap.py --limit 1
python scripts/extract_delta_rois.py --limit 20
python scripts/extract_cloud_rois.py --limit 20
```

Training requires labeled ROI images:

```powershell
python scripts/prelabel_cloud_rois_openai.py --limit 25 --dry-run
python scripts/prelabel_cloud_rois_openai.py --limit 25 --max-dim 1024 --request-delay 1.0
python scripts/prepare_labelimg_review.py
python scripts/train_roi_detector.py
python scripts/infer_pages.py --model runs/cloudhammer_roi/weights/best.pt --limit 5
```

Label only the `cloud_motif` class. A crop may contain multiple clouds, and
the first labeling pass should include bold, thin/faint, intersected, partial,
and marker-neighborhood negative examples. Revision triangles and digits stay
unlabeled. API guesses are review accelerators only and must be corrected by a
human before they become training truth.

OpenAI prelabeling defaults to `gpt-5.4` and reads `OPENAI_API_KEY` from
`CloudHammer/.env` unless the key is already set in the shell environment.
Use `--env-file path\to\.env` to point at a different file.

API prelabels are raw machine output in `data/api_cloud_labels_unreviewed`.
For LabelImg correction, copy only those YOLO `.txt` files into
`data/cloud_labels_reviewed`:

```powershell
python scripts/prepare_labelimg_review.py
```

Use `data/cloud_roi_images` as the LabelImg image directory,
`data/cloud_labels_reviewed` as the save directory, and YOLO format.
The helper also writes `data/cloud_labels_reviewed/classes.txt`, which
LabelImg needs when opening existing YOLO boxes.

The default config is `configs/cloudhammer.yaml`. Runtime outputs stay under
`data/`, `runs/`, and `outputs/` inside this directory.

## Important Paths

- images to review: `data/cloud_roi_images`
- API prelabel txt files: `data/api_cloud_labels_unreviewed`
- reviewed training truth: `data/cloud_labels_reviewed`
- ROI manifests: `data/manifests`

Do not touch active API output folders while a prelabel run is in progress.

## Docs

- `docs/README.md`
- `docs/pipeline_overview.md`
- `docs/labeling_workflow.md`
- `docs/api_prelabel_workflow.md`
