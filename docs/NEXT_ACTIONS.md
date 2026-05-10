# Next Actions

Status: operational queue as of 2026-05-10.

## Now

1. Finish the private client handoff pass.
   - Confirm Cloudflare Access allowed-user policy on `ledger.nezcoupe.net`
     from a fresh/incognito browser session before sharing the link.
   - Start from the intentionally empty app registry, create the next real
     project in `/projects`, stage package PDFs, and run Populate.
   - Verify Overview, Drawings, Latest Set, Review Changes, Diagnostics,
     Export Workbook, and Review Packet after Populate completes.
2. Watch the fixes made after the first real exploratory run.
   - Index pages must stay context-only.
   - Previous/current comparison must match the same sheet from a strictly
     earlier real revision set.
   - The exploratory project was reset; observations live in
     `FINDINGS_FIRST_REAL_RUN.md` and are not reviewed labels or training data.
3. After the handoff pass, resume CloudHammer_v2 where it was paused:
   - Return point:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.summary.md`.
   - Next task: resolve or accept rows `20`, `23`, `24`, and `29`, then decide
     the next internal pipeline-consumption/training step from that existing
     path.

## Immediate Review Queues

1. Directly confirm `page_disjoint_real` and create audited eval truth.
   - Current status: completed and consolidated.
   - Burden note: this completed queue had `17` frozen eval pages. GPT output
     for frozen eval pages is scratch/provisional only and cannot become eval
     truth.
   - Review queue:
     `CloudHammer_v2/eval/page_disjoint_real_human_review/manifest.jsonl`.
   - Labels write to
     `CloudHammer_v2/eval/page_disjoint_real_human_review/labels/`.
   - Human-audited eval manifest:
     `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.human_audited.jsonl`.
   - Summary:
     `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_human_audited_summary.md`.
2. Human-confirm/correct GPT-5.5 cropped training/review candidate prelabels.
   - Current status: completed for
     `CloudHammer/data/review_batches/small_corpus_expansion_supplement_20260502/prelabel_manifest.jsonl`.
     Output:
     `CloudHammer_v2/data/gpt55_crop_prelabels_small_corpus_supplement_20260502/README.md`.
3. Review the style-balance diagnostic touched-real queue only after applying
   the review fatigue guardrail.
   - Current status: queued and launched.
   - Queue size: `12` pages, so GPT-5.5 sample or full prefill should be
     considered before asking for manual review.
   - Manifest:
     `CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/manifest.jsonl`.
   - Summary:
     `CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/selection_summary.json`.
   - This set is diagnostic-only and must not be blended with
     `page_disjoint_real`.
4. Audit `model_only_tiled` false positives/misses from:
   `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/README.md`.
   - Current status: completed in
     `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.reviewed.csv`.
5. Audit `pipeline_full` grouped-candidate false positives/misses from the same
   overlay mismatch packet.
   - Current status: completed in the same reviewed mismatch log.
6. Define/generate the near-term candidate pools as candidate pools, not eval
   subsets:
   `full_page_review_candidates_from_touched`,
   `mining_safe_hard_negative_candidates`,
   `synthetic_background_candidates`, and
   `future_training_expansion_candidates`.
7. Convert full-page corrections into frozen eval truth only.
8. Use the durable review workflow for the first non-frozen postprocessing
   diagnostic without mining, tuning on, or training from frozen eval pages.
   - Queue size: `44` diagnostic rows, so GPT-5.5 prefill was appropriate and
     has been generated before manual confirmation.
   - Current report:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_summary.md`.
   - Static viewer:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_viewer.html`.
   - Blank/template review log:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_review_log.csv`.
   - GPT-5.5 prefilled review log:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_review_log.gpt55_prefill.csv`.
   - GPT-5.5 companion reviewer:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_viewer.gpt55_prefill.html`.
   - Reviewed CSV:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_review_log.reviewed.csv`.
   - Dry-run plan:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_dry_run_summary.md`.
   - Current dry-run result: `3` merge components, `10` tighten bbox proposals,
     `12` expand/`tighten_adjust` rows requiring explicit geometry, `3` manual
     split rows, and `10` no-change rows.
   - Blocked-geometry reviewer:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_reviewer.html`.
   - Geometry review:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_review.reviewed.csv`
     completed with `18` reviewed geometry items.
   - Apply dry-run comparison:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_dry_run_20260505/postprocessing_apply_dry_run_summary.md`.
   - Derived non-frozen apply output:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/postprocessed_non_frozen_apply_summary.md`.
   - Behavior comparison:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_behavior_comparison_20260505/postprocessing_non_frozen_behavior_summary.md`.
   - Crop regeneration:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/postprocessed_non_frozen_crop_regeneration_summary.md`.
     Dry-run was run first; `22` regenerated crops were written and `10`
     source crops were preserved.
   - GPT-5.5 crop inspection precheck:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.summary.md`.
     Current result: `28` `accept_crop`, `2` `needs_human_review`, and `2`
     `reject_no_visible_cloud`; companion viewer:
     `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.html`.
   - Next step: resolve or accept the `4` non-accepted GPT crop-precheck rows,
     then decide whether the `28` GPT-accepted crop-ready candidates feed
     crop-based inspection/export wiring or another contained
     pipeline-consumption comparison.

## Later

- Polish first-run product findings from `FINDINGS_FIRST_REAL_RUN.md`,
  especially OCR/context extraction, symbol/legend lookup, geometry split/merge
  behavior, review UI controls, and zoom legibility.
- Add background Populate jobs and durable process supervision if the handoff
  becomes a longer-lived deployment.
- Import approved legacy code into CloudHammer_v2 after audit.
- Archive runtime noise.
- Decide old experiment retention.
- Archive older generated runs.
- Implement synthetic training augmentation.
- Run GPT-assisted training loop.

## Current Blockers

- Private handoff readiness now depends on Cloudflare Access confirmation and
  a clean fresh-project populate/review smoke, not on seeded demo data.
- CloudHammer_v2 training remains paused at the crop-precheck return point.
  Baseline overlay mismatch review is complete; first non-frozen
  postprocessing diagnostic review, geometry review, apply preview, derived
  manifest, behavior comparison, crop regeneration, and GPT-5.5 crop precheck
  are complete. The next CloudHammer blocker is resolving or accepting the `4`
  non-accepted crop-precheck rows before choosing whether the `28` accepted
  crop-ready candidates should feed crop-based inspection/export wiring or
  another contained pipeline-consumption comparison.
- Candidate pool manifests need to be defined and generated without changing
  frozen eval truth, training data, mining inputs, or synthetic outputs.
- The strict clean page-disjoint pool is exhausted inside current sets; any
  style-balanced supplement must be classified honestly as new-data holdout,
  future retrain-from-scratch holdout, or diagnostic touched-real slice.
- No permanent audited legacy code import has been executed for CloudHammer_v2;
  current baseline reuse executed legacy scripts in place and logged that
  boundary.
- Latest legacy model is not promoted; it was trained before the
  source-controlled split became the active standard and now needs
  postprocessing diagnostics plus candidate-pool review before any promotion or
  next training decision.
