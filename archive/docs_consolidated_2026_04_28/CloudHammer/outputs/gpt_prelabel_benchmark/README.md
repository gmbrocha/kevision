# GPT Prelabel Benchmark

Compared raw GPT prelabels against the human-reviewed 204-image truth set.

## Image Level

- Images: `204`
- Accuracy: `0.995`
- Cloud precision: `0.995`
- Cloud recall: `1.000`
- False cloud images: `1`
- Missed cloud images: `0`

## Box Level

### IoU 0.25

- TP boxes: `318`
- FP boxes: `43`
- FN boxes: `85`
- Precision: `0.881`
- Recall: `0.789`
- F1: `0.832`
- Mean matched IoU: `0.749`

### IoU 0.40

- TP boxes: `290`
- FP boxes: `71`
- FN boxes: `113`
- Precision: `0.803`
- Recall: `0.720`
- F1: `0.759`
- Mean matched IoU: `0.789`

### IoU 0.50

- TP boxes: `267`
- FP boxes: `94`
- FN boxes: `136`
- Precision: `0.740`
- Recall: `0.663`
- F1: `0.699`
- Mean matched IoU: `0.817`

## Confidence Cutoffs

### all GPT boxes

- Image precision: `0.995`
- Image recall: `1.000`
- Box precision at IoU 0.40: `0.803`
- Box recall at IoU 0.40: `0.720`
- Box F1 at IoU 0.40: `0.759`

### GPT boxes >= 0.80

- Image precision: `0.995`
- Image recall: `1.000`
- Box precision at IoU 0.40: `0.809`
- Box recall at IoU 0.40: `0.715`
- Box F1 at IoU 0.40: `0.759`

### GPT boxes >= 0.90

- Image precision: `0.995`
- Image recall: `1.000`
- Box precision at IoU 0.40: `0.817`
- Box recall at IoU 0.40: `0.685`
- Box F1 at IoU 0.40: `0.745`

### GPT boxes >= 0.95

- Image precision: `0.995`
- Image recall: `0.995`
- Box precision at IoU 0.40: `0.855`
- Box recall at IoU 0.40: `0.556`
- Box F1 at IoU 0.40: `0.674`

## Files

- `summary.json`
- `per_image.csv`
