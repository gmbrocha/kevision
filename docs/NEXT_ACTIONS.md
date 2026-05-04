# Next Actions

Status: operational queue as of 2026-05-02.

## Now

1. Finish docs/root cleanup if not complete.
   - Current status: substantially complete. Root canonical docs are reduced to
     `README.md`, `AGENTS.md`, `PRODUCT_AND_DELIVERY.md`, `ROADMAP.md`, and
     `docs/`. `docs/SECURITY_PRIVACY_POLICY.md` remains as a compatibility stub.
2. Add/verify AGENTS.md and Cursor rules.
   - Current status: verified by project owner on 2026-05-02.
3. Run report-only experiments retention review.
   - Current status: completed at
     `docs/archive_cleanup_audits/experiments_retention_review_2026_05_02.md`.
     Approved lessons were promoted to CloudHammer_v2 docs.
4. Run model-vs-pipeline audit.
   - Current status: completed at
     `CloudHammer_v2/docs/MODEL_VS_PIPELINE_AUDIT_REPORT_2026_05_02.md`.
5. Build touched-page registry dry run.
   - Current status: completed at
     `CloudHammer_v2/outputs/touched_page_registry_20260502/touched_page_registry_summary.md`.
6. Select `page_disjoint_real` candidates.
   - Current status: completed. `17` untouched eligible pages were frozen at
     `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.jsonl`.
7. Correct GPT-provisional full-page label handling.
   - Current status: corrected. GPT full-page labels are provisional only.
     `page_disjoint_real` should be human-reviewed directly.
   - Accidental GPT-5.5 full-page outputs are scratch/do-not-score at
     `CloudHammer_v2/eval/page_disjoint_real_gpt55/DO_NOT_SCORE.md`.
8. Run baseline eval: `model_only_tiled` vs `pipeline_full`.
   - Current status: completed against human-audited `page_disjoint_real`
     truth. Current report:
     `CloudHammer_v2/docs/BASELINE_EVAL_REPORT_2026_05_04.md`.
   - Prior GPT-provisional report:
     `CloudHammer_v2/docs/BASELINE_EVAL_REPORT_2026_05_02.md`.
9. Only after real baseline exists, implement `synthetic_diagnostic`.
   - Current status: grammar/spec exists; keep generation deferred until the
     reviewed baseline mismatch summary, postprocessing diagnostics, and
     candidate pools are trustworthy enough to steer diagnostics.

## Immediate Human Review

1. Human-review `page_disjoint_real` directly and create audited eval truth.
   - Current status: completed and consolidated.
   - Review queue:
     `CloudHammer_v2/eval/page_disjoint_real_human_review/manifest.jsonl`.
   - Labels write to
     `CloudHammer_v2/eval/page_disjoint_real_human_review/labels/`.
   - Human-audited eval manifest:
     `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.human_audited.jsonl`.
   - Summary:
     `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_human_audited_summary.md`.
2. Human-review/correct GPT-5.5 cropped training/review candidate prelabels.
   - Current status: completed for
     `CloudHammer/data/review_batches/small_corpus_expansion_supplement_20260502/prelabel_manifest.jsonl`.
     Output:
     `CloudHammer_v2/data/gpt55_crop_prelabels_small_corpus_supplement_20260502/README.md`.
3. Human-review the style-balance diagnostic touched-real queue.
   - Current status: queued and launched.
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
8. Use audited mismatches to plan a postprocessing-first diagnostic without
   mining, tuning on, or training from frozen eval pages.

## Later

- Import approved legacy code into CloudHammer_v2 after audit.
- Archive runtime noise.
- Decide old experiment retention.
- Archive older generated runs.
- Implement synthetic training augmentation.
- Run GPT-assisted training loop.

## Current Blockers

- Baseline overlay mismatch review is complete; next blocker is translating the
  reviewed buckets into a non-frozen postprocessing diagnostic.
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
