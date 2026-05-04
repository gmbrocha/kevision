# Baseline Eval Report - 2026-05-02

Status: completed first provisional `page_disjoint_real` baseline.

This is not promotion evidence. The labels are GPT-provisional and need human
audit before the numbers are used for model selection, threshold tuning, or
training decisions.

## Frozen Real Eval Set

- Eval subset: `page_disjoint_real`
- Frozen pages: `17`
- Source rule: page-disjoint from current continuity training, source-controlled
  train/val, quasi-holdout crop rows, and the old debug eval pages
- Registry report:
  `CloudHammer_v2/outputs/touched_page_registry_20260502/touched_page_registry_summary.md`
- Frozen manifest:
  `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.jsonl`

Revision mix:

- `Revision #1 - Drawing Changes`: `7`
- `Revision #2 - Mod 5 grab bar supports`: `7`
- `Revision #3 - EHRM Drawings`: `2`
- `Revision #5 - RFI 126 - Concrete Repairs`: `1`

## GPT-Provisional Labels

- Model: `gpt-5.4`
- Label status: `gpt_provisional`
- Pages processed: `17`
- Pages with accepted boxes: `8`
- Accepted boxes: `14`
- Overlay contact sheet:
  `CloudHammer_v2/eval/page_disjoint_real/gpt_fullpage_overlay_contact_sheet.jpg`
- Label summary:
  `CloudHammer_v2/eval/page_disjoint_real/gpt_fullpage_label_summary.md`

Visual type counts:

- `bold`: `5`
- `thin`: `6`
- `faint`: `1`
- `intersected`: `2`

## Model Under Test

- Checkpoint:
  `CloudHammer/runs/cloudhammer_roi-symbol-text-fp-hn-20260502/weights/best.pt`
- Status: latest continuity checkpoint, not promoted
- Inference config:
  `CloudHammer_v2/configs/baseline_page_disjoint_real_20260502.yaml`

## Baseline Results

| Run | Predictions | IoU | TP | FP | FN | Precision | Recall | FP/Page |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `model_only_tiled` | `70` | `0.25` | `2` | `68` | `12` | `0.029` | `0.143` | `4.000` |
| `model_only_tiled` | `70` | `0.50` | `0` | `70` | `14` | `0.000` | `0.000` | `4.118` |
| `pipeline_full` | `28` | `0.25` | `5` | `23` | `9` | `0.179` | `0.357` | `1.353` |
| `pipeline_full` | `28` | `0.50` | `0` | `28` | `14` | `0.000` | `0.000` | `1.647` |

Detailed reports:

- `CloudHammer_v2/outputs/baseline_model_only_tiled_page_disjoint_real_20260502/eval/eval_summary.md`
- `CloudHammer_v2/outputs/baseline_pipeline_full_page_disjoint_real_20260502/eval/eval_summary.md`

Pipeline stages used:

- legacy tiled YOLO inference from `CloudHammer/scripts/infer_pages.py`
- legacy fragment grouping from `CloudHammer/scripts/group_fragment_detections.py`
- overmerge refinement enabled with `review_v1`
- legacy whole-cloud candidate export from
  `CloudHammer/scripts/export_whole_cloud_candidates.py`
- whole-cloud crop params: `crop_margin_ratio=0.16`,
  `min_crop_margin=550`, `max_crop_margin=950`

Pipeline output:

- Fragments: `70`
- Grouped candidates: `28`
- Multi-fragment groups: `16`
- Whole-cloud confidence tiers: `22` high, `5` medium, `1` low

## Interpretation

The pipeline improves candidate volume and loose-box recall compared with
model-only tiled inference, but the current checkpoint is still noisy on the
fresh page-disjoint pages and misses many GPT-provisional labels.

The zero IoU-0.50 result is a warning about box fit and/or label quality. It
should not be overinterpreted until the provisional labels and overlays are
human-audited.

## Next Step

Human-review `page_disjoint_real` directly and rerun the baseline against
human-audited truth before any more training, threshold tuning, or synthetic
generation. Preserve the frozen page set as eval only; do not mine it for
training examples.

## GPT-5.5 Full-Page Scratch Correction

A separate GPT-5.5 full-page prelabel pass was generated after the first
GPT-5.4 baseline, but this was the wrong target. `page_disjoint_real` is meant
for direct human review and should not use GPT full-page labels as eval truth.

The accidental GPT-5.5 full-page outputs are marked scratch/do-not-score:

- `CloudHammer_v2/eval/page_disjoint_real_gpt55/DO_NOT_SCORE.md`
- `CloudHammer_v2/outputs/baseline_model_only_tiled_page_disjoint_real_20260502/eval_gpt55/DO_NOT_SCORE.md`
- `CloudHammer_v2/outputs/baseline_pipeline_full_page_disjoint_real_20260502/eval_gpt55/DO_NOT_SCORE.md`

Do not use the GPT-5.5 full-page labels or scores as eval ground truth.
