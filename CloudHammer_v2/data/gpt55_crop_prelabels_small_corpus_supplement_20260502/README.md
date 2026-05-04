# GPT-5.5 Cropped Prelabels - Small Corpus Supplement

Status: `gpt_provisional` review inputs. Do not use for training until human-reviewed or corrected.

Source manifest: `CloudHammer/data/review_batches/small_corpus_expansion_supplement_20260502/prelabel_manifest.jsonl`
Model: `gpt-5.5`
Rows: `150`
Status counts: `{'ok': 150}`
Has-cloud counts: `{'False': 101, 'True': 49}`
Accepted boxes: `51`
Nonempty label files: `49`
Empty label files: `101`
Visual type counts: `{'thin': 2, 'partial': 41, 'intersected': 8}`

## Outputs

- Predictions: `CloudHammer_v2\data\gpt55_crop_prelabels_small_corpus_supplement_20260502\api_predictions\predictions.jsonl`
- Review manifest: `CloudHammer_v2\data\gpt55_crop_prelabels_small_corpus_supplement_20260502\review_manifest.gpt_provisional.jsonl`
- Labels: `CloudHammer_v2\data\gpt55_crop_prelabels_small_corpus_supplement_20260502\labels_gpt_provisional`
- Review overlays: `CloudHammer_v2\data\gpt55_crop_prelabels_small_corpus_supplement_20260502\review_overlays`

## Rules

- These labels are not eval truth.
- These labels are not training truth.
- Human review/correction is required before any training manifest consumes them.
