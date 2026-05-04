# Human-Audited Page-Disjoint Baseline Eval

Status: completed `page_disjoint_real` baseline against human-audited truth.

## Scope

- Eval subset: `page_disjoint_real`
- Label status: `human_audited`
- Eval manifest:
  `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.human_audited.jsonl`
- Pages: `17`
- Truth boxes: `26`
- Empty truth pages: `1`

This report replaces the GPT-provisional baseline as the current steering
baseline. It is still a small and style-skewed ruler, not a promotion claim.

## Results

| Mode | Predictions | IoU | TP | FP | FN | Precision | Recall | F1 | FP/page |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `model_only_tiled` | `70` | `0.25` | `23` | `47` | `3` | `0.329` | `0.885` | `0.479` | `2.765` |
| `model_only_tiled` | `70` | `0.50` | `18` | `52` | `8` | `0.257` | `0.692` | `0.375` | `3.059` |
| `pipeline_full` | `28` | `0.25` | `20` | `8` | `6` | `0.714` | `0.769` | `0.741` | `0.471` |
| `pipeline_full` | `28` | `0.50` | `12` | `16` | `14` | `0.429` | `0.462` | `0.444` | `0.941` |

## Interpretation

- `model_only_tiled` has stronger recall at IoU 0.25 but emits many extra
  detections.
- `pipeline_full` substantially reduces false positives and gives the stronger
  IoU 0.25 F1 on the current human-audited set.
- At IoU 0.50, both modes degrade, which suggests localization/grouping quality
  needs mismatch audit before training decisions.
- The `page_disjoint_real` set is only `17` pages and is likely plumbing-heavy,
  so style/source-family buckets still need separate interpretation.

## Artifacts

- Model-only summary:
  `CloudHammer_v2/outputs/baseline_model_only_tiled_page_disjoint_real_20260502/eval_human_audited/eval_summary.md`
- Pipeline-full summary:
  `CloudHammer_v2/outputs/baseline_pipeline_full_page_disjoint_real_20260502/eval_human_audited/eval_summary.md`
- Mismatch review queue:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/mismatch_review_queue.jsonl`
- Mismatch review summary:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/mismatch_review_summary.md`

## Next Step

Human-audit the mismatch queue and bucket misses/false positives by approved
error family. Keep all frozen `page_disjoint_real` pages eval-only.
