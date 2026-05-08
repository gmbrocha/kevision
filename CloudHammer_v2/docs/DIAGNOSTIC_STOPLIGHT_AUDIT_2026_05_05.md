# Diagnostic Stoplight Audit - 2026-05-05

Purpose: contain diagnostic depth. This audit inventories current
CloudHammer_v2 review work without creating new review items.

## Stoplight Rule

- `GREEN`: required now and decision-changing.
- `YELLOW`: useful but can be GPT-prefilled, backfilled, or sampled.
- `RED`: interesting but not actionable now.

Do not create `RED` queues. Do not create `YELLOW` queues unless they are
cheap, GPT-prefilled or backfilled where practical, and explicitly approved.
Do not re-review already-seen visual items unless the new question cannot be
answered from existing review data, geometry, metadata, or GPT-5.5 prefill.

## Current Queues

| Queue / artifact | Count | Status | Stoplight | Why |
| --- | ---: | --- | --- | --- |
| `page_disjoint_real_human_review` | 17 pages | Completed | GREEN, closed | Created frozen eval truth. No further review unless the two `truth_followup` rows prove a specific truth edit is needed. |
| Baseline mismatch review | 77 rows | Completed | GREEN, closed | Already human-bucketed model-vs-pipeline baseline failures. Collapse future error-family questions into this reviewed CSV where possible. |
| Non-frozen postprocessing diagnostic review | 44 rows | Completed | GREEN, closed | Already produced reviewed merge, reject, tighten, split, expand, and `tighten_adjust` decisions. Do not re-review these crops for new taxonomy. |
| Blocked postprocessing geometry review | 18 rows | Human-reviewed export complete and consumed by comparison | GREEN, closed | Provides full-cloud, child, and merge-component geometry for the postprocessing apply/dry-run comparison. |
| Postprocessed crop inspection precheck | 32 rows | GPT-5.5 precheck complete | GREEN, small | Documents whether regenerated/preserved crops are suitable for crop-based consumption. GPT accepted `28`, flagged `2` for human review, and rejected `2` no-visible-cloud rows. |
| `truth_followup` rows from mismatch review | 2 rows | Pending targeted recheck | GREEN, small | Potentially changes frozen eval truth. Handle as targeted truth recheck from existing mismatch records, not a broad new queue. |
| `style_balance_diagnostic_real_touched_20260503` | 12 pages | Deferred diagnostic-only queue | YELLOW | May help baseline interpretation, but it is not promotion-clean and does not block the current usable baseline. Use GPT prefill/sample only if explicitly approved. |
| GPT-5.5 cropped supplement prelabels | 150 crops | Provisional labels | YELLOW | May support future training inclusion after confirmation, but does not block the current frozen baseline. Prefer sampled confirmation or targeted subsets over full manual pass. |
| Candidate pools: `full_page_review_candidates_from_touched`, `mining_safe_hard_negative_candidates`, `synthetic_background_candidates`, `future_training_expansion_candidates` | Not generated here | Planned | YELLOW | Generate report-first manifests only when they directly support training inclusion or postprocessing follow-up. Do not turn them into manual queues by default. |
| Additional diagnostic dimensions, contact sheets, broad LabelImg queues, hard-negative visual taxonomies | N/A | Not active | RED unless reclassified | Interesting analysis only. Do not create unless a concrete decision path is named first. |

## Blocking The Frozen Eval / Baseline

The frozen human-audited `page_disjoint_real` baseline is already usable for
model-vs-pipeline interpretation.

Only two items can still affect frozen eval truth: the two existing
`truth_followup` rows in
`CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.reviewed.csv`.
They should be resolved as a targeted truth recheck, not as a new visual queue.

The 18-row blocked-geometry review does not block the frozen eval baseline. It
is complete and has been consumed by the postprocessing behavior apply/dry-run
comparison.

## Collapse Into Existing Records

- Further model-vs-pipeline explanation should use
  `mismatch_review_log.reviewed.csv` and its summary.
- Further postprocessing behavior should use
  `postprocessing_diagnostic_review_log.reviewed.csv`,
  `postprocessing_dry_run_plan.jsonl`, and
  `postprocessing_geometry_review.reviewed.csv`; the current candidate-level
  preview is
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_dry_run_20260505/postprocessing_apply_dry_run_summary.md`.
  The accepted derived manifest is
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/postprocessed_non_frozen_apply_summary.md`.
  The metadata behavior comparison is
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_behavior_comparison_20260505/postprocessing_non_frozen_behavior_summary.md`.
  Crop-based consumption should start from the GPT-5.5 precheck:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.summary.md`.
- Style/source-family notes should be additive metadata on existing rows or
  sampled diagnostics, not a full repeated review pass.
- Training inclusion from GPT crop prelabels should be sampled or targeted by
  decision need, not reviewed exhaustively as a new default queue.

## Stop Or Defer

- Defer full manual review of `style_balance_diagnostic_real_touched_20260503`
  unless explicitly approved as a GPT-prefilled or sampled YELLOW queue.
- Defer broad candidate-pool manual review. Generate report-first manifests
  only when they feed a concrete training or postprocessing decision.
- Stop adding new visual taxonomy dimensions for already-reviewed mismatch or
  postprocessing rows unless the field changes frozen truth, training inclusion,
  postprocessing behavior, baseline interpretation, or delivery-facing behavior.

## Shortest Path To Usable Eval Baseline

1. Keep the current human-audited `page_disjoint_real` baseline as the usable
   steering baseline.
2. Resolve only the two existing `truth_followup` rows if baseline truth
   correctness is in doubt.
3. Resolve or accept the `4` non-accepted GPT-5.5 crop-precheck rows, then use
   the `28` accepted crop-ready postprocessed candidates for crop-based
   inspection/export wiring if needed, or use the behavior comparison plus
   regenerated crops to decide the next contained pipeline-consumption step.
4. Defer style-balance, crop supplement, candidate-pool, and synthetic work
   until the postprocessing comparison identifies a decision-changing need.
