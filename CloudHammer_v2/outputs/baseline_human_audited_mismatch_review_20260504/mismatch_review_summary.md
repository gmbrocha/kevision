# Human-Audited Baseline Mismatch Review Queue

Status: page-level review queue derived from the human-audited `page_disjoint_real` baseline.

This queue is for human audit only. It is not training data, hard-negative
mining input, threshold tuning input, or label truth.

## Inputs

- Model-only eval:
  `CloudHammer_v2/outputs/baseline_model_only_tiled_page_disjoint_real_20260502/eval_human_audited/per_page_eval.jsonl`
- Pipeline-full eval:
  `CloudHammer_v2/outputs/baseline_pipeline_full_page_disjoint_real_20260502/eval_human_audited/per_page_eval.jsonl`
- Eval truth:
  `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.human_audited.jsonl`

## Priority Queue

Rows are sorted by `review_priority_score`, defined as:

`model_only_tiled_iou25_fp + model_only_tiled_iou25_fn + pipeline_full_iou25_fp + pipeline_full_iou25_fn`

| Page | Labels | Model pred | Model FP@0.25 | Model FN@0.25 | Pipeline pred | Pipeline FP@0.25 | Pipeline FN@0.25 | Priority |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `Revision_1_-_Drawing_Changes:p0041` | `2` | `14` | `14` | `2` | `2` | `2` | `2` | `20` |
| `260313_-_VA_Biloxi_Rev_3:p0188` | `2` | `10` | `8` | `0` | `2` | `0` | `0` | `8` |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0028` | `1` | `3` | `3` | `1` | `2` | `2` | `1` | `7` |
| `260303-VA_Biloxi_Rev_5_RFI-126:p0007` | `4` | `10` | `6` | `0` | `3` | `0` | `1` | `7` |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0025` | `1` | `5` | `4` | `0` | `2` | `1` | `0` | `5` |
| `260313_-_VA_Biloxi_Rev_3:p0197` | `2` | `3` | `1` | `0` | `1` | `1` | `2` | `4` |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0022` | `1` | `3` | `2` | `0` | `1` | `0` | `0` | `2` |
| `Revision_1_-_Drawing_Changes:p0036` | `2` | `3` | `1` | `0` | `3` | `1` | `0` | `2` |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0014` | `1` | `3` | `2` | `0` | `1` | `0` | `0` | `2` |
| `Revision_1_-_Drawing_Changes:p0037` | `0` | `1` | `1` | `0` | `1` | `1` | `0` | `2` |
| `Revision_1_-_Drawing_Changes:p0003` | `1` | `2` | `1` | `0` | `1` | `0` | `0` | `1` |
| `Revision_1_-_Drawing_Changes:p0033` | `2` | `3` | `1` | `0` | `2` | `0` | `0` | `1` |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0020` | `1` | `2` | `1` | `0` | `1` | `0` | `0` | `1` |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0026` | `1` | `2` | `1` | `0` | `1` | `0` | `0` | `1` |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0027` | `1` | `2` | `1` | `0` | `1` | `0` | `0` | `1` |

## Immediate Audit Targets

Start with:

- `Revision_1_-_Drawing_Changes:p0041`, because both modes miss both labels at
  IoU 0.25 and both modes also produce false positives.
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0028`, because both modes miss the
  single label and both modes produce false positives.
- `260313_-_VA_Biloxi_Rev_3:p0197`, because `pipeline_full` collapses to one
  prediction while missing both labels at IoU 0.25.

Do not convert any frozen eval-page crops into training examples. Audit results
should update eval truth only if the human-audited label itself is found wrong.
