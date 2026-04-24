# CloudHammer API Prelabel Workflow

Status: `Current source of truth for API prelabels. Treat the live API output folders as hands-off during active runs.`

API prelabels are optional review accelerators, not ground truth.

## Inputs And Outputs

- input images: `data/cloud_roi_images`
- raw API label guesses: `data/api_cloud_labels_unreviewed`
- raw prediction log: `data/api_cloud_predictions`
- review overlays: `data/api_cloud_review`
- reviewed labels for training: `data/cloud_labels_reviewed`

If a prelabel run is actively writing output, do not modify the live API output folders until it finishes.

## Typical Flow

1. Generate cloud ROI crops.
2. Dry-run the API prelabel script if needed.
3. Run API prelabeling into the unreviewed folders.
4. Copy the YOLO `.txt` files into `data/cloud_labels_reviewed`.
5. Review and correct every file in LabelImg.
6. Train only from the reviewed label directory.

## Commands

```powershell
python scripts/prelabel_cloud_rois_openai.py --limit 25 --dry-run
python scripts/prelabel_cloud_rois_openai.py --limit 25 --max-dim 1024 --request-delay 1.0
python scripts/prepare_labelimg_review.py
```

## Rule

API guesses are never training truth by themselves. Human-corrected labels in
`data/cloud_labels_reviewed` are the only source of truth for model training.
