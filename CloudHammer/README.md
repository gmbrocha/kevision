# CloudHammer

CloudHammer is a standalone revision-cloud detector project. It catalogs
drawing pages, uses legacy delta-marker output only as optional context for
cloud candidate generation, supports manual ROI labeling, trains a one-class
YOLO detector, and runs tile-based page inference that emits JSON, crops, and
overlays.

## Quick Start

From `CloudHammer/`:

```powershell
python scripts/catalog_pages.py --no-render
python scripts/catalog_pages.py --limit 5 --overwrite
python scripts/run_delta_bootstrap.py --limit 1
python scripts/extract_cloud_rois.py --limit 20
```

Training requires labeled ROI images:

```powershell
python scripts/prelabel_cloud_rois_openai.py --limit 25 --dry-run
python scripts/prelabel_cloud_rois_openai.py --limit 25 --max-dim 1024 --request-delay 1.0
python scripts/train_roi_detector.py
python scripts/infer_pages.py --model runs/cloudhammer_roi/weights/best.pt --limit 5
```

Label only the `cloud_motif` class. A crop may contain multiple clouds, and
the first labeling pass should include bold, thin/faint, intersected, partial,
and marker-neighborhood negative examples. Revision triangles and digits stay
unlabeled. API prelabels are written separately under `data/api_cloud_labels`
and should be reviewed before promotion to human labels.

OpenAI prelabeling defaults to `gpt-5.4` and reads `OPENAI_API_KEY` from
`CloudHammer/.env` unless the key is already set in the shell environment.
Use `--env-file path\to\.env` to point at a different file.

The default config is `configs/cloudhammer.yaml`. Runtime outputs stay under
`data/`, `runs/`, and `outputs/` inside this directory.
