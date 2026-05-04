# CloudHammer_v2 Pivot Plan

## Summary

CloudHammer_v2 exists to establish an eval-first path before more detector
training. The immediate objective is to prove what the YOLOv8 model knows
versus what the surrounding pipeline fixes.

GPT-heavy labeling is allowed for the current project under the project-specific
approval exception, but frozen real holdouts remain the measuring stick. For
`page_disjoint_real`, GPT full-page labels are scratch only; the eval truth
should be human-reviewed directly.

## Current Objective

Use the frozen, human-audited full-page eval before more training, then compare
and audit:

- `model_only_tiled`: YOLOv8 full-page tiled detection with only NMS and
  coordinate mapping
- `pipeline_full`: the full CloudHammer pipeline including grouping, cropper,
  filtering, and export-facing behavior

Both paths have now been scored against the same frozen human-audited full-page
labels, and the baseline mismatch rows have been human-bucketed. Current work is
postprocessing-first diagnostics and guarded candidate-pool generation before the
next training or synthetic decision.

## Priority Order

1. Build touched-page registry and freeze guards. Completed.
2. Select and freeze `page_disjoint_real` from all eligible page-clean full
   pages unless this removes rare training-needed positives. Completed.
3. Human-review frozen `page_disjoint_real` pages directly to create eval truth.
   Completed.
4. Produce overlays/contact sheets for human audit. Completed for the current
   baseline mismatch packet.
5. Run baseline eval for `model_only_tiled` and `pipeline_full`. Completed
   against human-audited `page_disjoint_real` truth.
6. Human-audit mismatch cases and bucket errors by approved error family.
   Completed for the current `77`-row baseline review.
7. Run postprocessing diagnostics on non-frozen data for fragment merging,
   duplicate suppression, overmerge splitting, and localization. First
   report-only diagnostic and static viewer generated; spot-check the rows
   before implementing any dry-run postprocessor.
8. Define/generate guarded candidate pools:
   `full_page_review_candidates_from_touched`,
   `mining_safe_hard_negative_candidates`,
   `synthetic_background_candidates`, and
   `future_training_expansion_candidates`.
9. Implement `synthetic_diagnostic` only after the real baseline,
   postprocessing findings, and candidate pools are trustworthy enough to steer
   diagnostics.

## Training Gate

Training resumes only after the human-audited baseline mismatch review and
postprocessing diagnostics clarify what remains true model-training signal. New
training data should come from GPT-assisted labeling, model/GPT disagreement
queues, reviewed hard negatives, candidate-pool review, and pipeline findings
converted into training signal without mining frozen eval pages.

The next implementation step is postprocessing-first: build a dry-run
merge/suppress/split/localization postprocessor on non-frozen diagnostic inputs,
then measure candidate behavior before deciding whether any remaining signal is
training data.

## Reporting Rule

Never blend scores across:

- `page_disjoint_real`
- `gold_source_family_clean_real`
- `style_balance_diagnostic_real_touched`
- `synthetic_diagnostic`

Report provisional label status honestly.

`synthetic_diagnostic` is the canonical synthetic eval-set name. Candidate pools
are separate from eval subsets and must not be reported as promotion metrics.
