# Temporary Random GPT Review Queue

This folder is a quick human review queue built from `data/random_drawing_crops`.

Contents:

- GPT positives: `14`
- GPT negative spot checks: `50`
- Total images: `64`

Folders:

- `images/`: crops to review
- `labels/`: seeded GPT YOLO labels; this is the LabelImg save folder
- `gpt_overlays/`: JPG overlays showing GPT boxes
- `review_queue.csv`: quick review sheet
- `manifest.jsonl`: same queue in JSONL
- `images.txt`: absolute image list in queue order

LabelImg command from `CloudHammer/`:

```powershell
..\.venv\Scripts\labelImg.exe data\temp_random_gpt_review_queue\images configs\cloud_classes.txt data\temp_random_gpt_review_queue\labels
```

Or use the queue launcher from `CloudHammer/`:

```powershell
..\.venv\Scripts\python.exe scripts\launch_random_gpt_review_queue.py
```

Quick labels to use in `review_queue.csv` if you are just browsing:

- `positive`
- `negative`
- `unsure`

Suggested workflow:

1. Review every `gpt_positive` item.
2. Spot-check the `negative_spotcheck` items.
3. If using LabelImg, save corrections into `labels/`.
