# GPT-5.5 Prelabel Comparison - 2026-05-02

Status: accidental scratch output. Do not score.

Correction: `page_disjoint_real` is intended for direct human review and should
not rely on GPT full-page labels. The GPT-5.5 full-page label pass documented
here is retained only as scratch context and must not be used as eval ground
truth, training data, threshold tuning input, or promotion evidence.

## What Changed

A separate GPT-5.5 full-page label pass was generated for the frozen
`page_disjoint_real` pages. The existing GPT-5.4 labels and baseline outputs
were left untouched.

- GPT-5.4 labels:
  `CloudHammer_v2/eval/page_disjoint_real/`
- GPT-5.5 labels:
  `CloudHammer_v2/eval/page_disjoint_real_gpt55/`
- GPT-5.5 overlay contact sheet:
  `CloudHammer_v2/eval/page_disjoint_real_gpt55/gpt_fullpage_overlay_contact_sheet.jpg`

## Label Volume

| Label Pass | Pages | Pages With Boxes | Accepted Boxes |
| --- | ---: | ---: | ---: |
| `gpt-5.4` | `17` | `8` | `14` |
| `gpt-5.5` | `17` | `11` | `34` |

GPT-5.5 found substantially more boxes. This may be better recall, more false
positives, or both.

## Notable Per-Page Difference

The main outlier is:

- `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0020`
  - GPT-5.4 labels: `0`
  - GPT-5.5 labels: `18`

This page should be audited early. A single page adding 18 labels can dominate
the diagnostic comparison and may indicate either a dense valid revision area
or GPT over-labeling repeated non-cloud features.

## Eval Against Existing Predictions

These results reuse the already-generated model and pipeline predictions. No
new YOLO inference was run.

| Label Pass | Run | Predictions | IoU | TP | FP | FN | Precision | Recall | FP/Page |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.4` | `model_only_tiled` | `70` | `0.25` | `2` | `68` | `12` | `0.029` | `0.143` | `4.000` |
| `gpt-5.4` | `pipeline_full` | `28` | `0.25` | `5` | `23` | `9` | `0.179` | `0.357` | `1.353` |
| `gpt-5.5` | `model_only_tiled` | `70` | `0.25` | `11` | `59` | `23` | `0.157` | `0.324` | `3.471` |
| `gpt-5.5` | `pipeline_full` | `28` | `0.25` | `9` | `19` | `25` | `0.321` | `0.265` | `1.118` |

IoU 0.50 under GPT-5.5:

- `model_only_tiled`: precision `0.086`, recall `0.176`
- `pipeline_full`: precision `0.107`, recall `0.088`

Detailed GPT-5.5 eval reports:

- `CloudHammer_v2/outputs/baseline_model_only_tiled_page_disjoint_real_20260502/eval_gpt55/eval_summary.md`
- `CloudHammer_v2/outputs/baseline_pipeline_full_page_disjoint_real_20260502/eval_gpt55/eval_summary.md`

## Interpretation

GPT-5.5 produced a more permissive provisional label set. Against that label
set, the existing detector appears less catastrophically mismatched than it did
against GPT-5.4, but the higher label count also increases missed-label count.

The correct conclusion is not that either GPT pass is automatically right. The
next step is to human-audit disagreements, especially:

- pages where GPT-5.5 added labels and GPT-5.4 was empty
- pages where GPT-5.4 labeled clouds and GPT-5.5 did not
- model/pipeline predictions that match only one GPT pass
- the `p0020` outlier with 18 GPT-5.5 boxes

## Decision

Do not use this GPT-5.5 full-page pass for scoring. The folder has been marked
with `DO_NOT_SCORE.md`.

The correct GPT-5.5 use now is cropped training/review candidate prelabeling,
not frozen real eval-page labeling.
