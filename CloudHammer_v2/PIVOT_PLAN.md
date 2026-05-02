# CloudHammer_v2 Pivot Plan

## Summary

CloudHammer_v2 exists to establish an eval-first path before more detector
training. The immediate objective is to prove what the YOLOv8 model knows
versus what the surrounding pipeline fixes.

GPT-heavy labeling is allowed for the current project under the project-specific
approval exception, but frozen real holdouts remain the measuring stick.

## Current Objective

Freeze real full-page eval before more training, then compare:

- `model_only_tiled`: YOLOv8 full-page tiled detection with only NMS and
  coordinate mapping
- `pipeline_full`: the full CloudHammer pipeline including grouping, cropper,
  filtering, and export-facing behavior

Both paths must score against the same frozen full-page labels.

## Priority Order

1. Build touched-page registry and freeze guards.
2. Select and freeze `page_disjoint_real` from all eligible page-clean full
   pages unless this removes rare training-needed positives.
3. Generate GPT-provisional full-page labels.
4. Produce overlays/contact sheets for human audit.
5. Run baseline eval for `model_only_tiled` and `pipeline_full`.
6. Implement `synthetic_diagnostic` only after the real baseline exists.

## Training Gate

Training resumes only after the baseline eval exists. New training data should
come from GPT-assisted labeling, model/GPT disagreement queues, reviewed hard
negatives, and pipeline findings converted into training signal.

## Reporting Rule

Never blend scores across:

- `page_disjoint_real`
- `gold_source_family_clean_real`
- `synthetic_diagnostic`

Report provisional label status honestly.
