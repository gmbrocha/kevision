# page_disjoint_real Human Review Queue

This queue is for direct human eval truth for `page_disjoint_real`.

Use this queue to draw YOLO boxes around every visible revision cloud motif on the frozen full-page images. These labels are evaluation truth, not GPT prelabels and not training labels.

Rules:
- Class: `cloud_motif`
- Draw one box around each complete visible revision cloud motif.
- For clipped/partial clouds, box only the visible cloud extent.
- For true no-cloud pages, leave the label file empty and save/review the page.
- Do not use accidental GPT full-page labels as truth.
- Do not add these frozen eval pages or labels to training, crop mining, threshold tuning, synthetic backgrounds, or relabel loops.

Known working launch command from repo root:

```powershell
$imageList = Resolve-Path CloudHammer_v2\eval\page_disjoint_real_human_review\images_resolved.txt
$startImage = Get-Content CloudHammer_v2\eval\page_disjoint_real_human_review\images_resolved.txt -TotalCount 1
$imageDir = Split-Path -Parent $startImage
$env:LABELIMG_IMAGE_LIST = $imageList
$env:LABELIMG_START_IMAGE = $startImage
.\.venv\Scripts\python.exe .\.venv\Lib\site-packages\labelImg\labelImg.py $imageDir (Resolve-Path CloudHammer_v2\eval\page_disjoint_real_human_review\labels\classes.txt) (Resolve-Path CloudHammer_v2\eval\page_disjoint_real_human_review\labels)
```

The older `labelImg.exe` entrypoint may exit immediately in this environment.

Dry run:

```powershell
.\.venv\Scripts\python.exe CloudHammer\scripts\launch_labelimg_batch.py page_disjoint_real_human_review --batch-root CloudHammer_v2\eval --reviewed-label-dir CloudHammer_v2\eval\page_disjoint_real_human_review\labels --class-file CloudHammer_v2\eval\page_disjoint_real_human_review\labels\classes.txt --dry-run --start-first
```
