# ScopeLedger Roadmap

Status: canonical application roadmap as of 2026-05-02.

Detailed application docs live in `docs/`. Cloud detection details live in
`CloudHammer_v2/`.

## Active Pivot

The active blocker is the CloudHammer v2 eval pivot: use the human-audited
`page_disjoint_real` baseline and reviewed mismatch buckets to run
postprocessing diagnostics and prepare guarded candidate pools before more
detector training or synthetic data generation.

Completed foundation:

1. Build touched-page registry and freeze guards.
2. Freeze `page_disjoint_real` from eligible full pages.
3. Directly confirm `page_disjoint_real` eval truth, with GPT outputs
   treated as scratch/provisional only.
4. Produce overlays/contact sheets for audit, paired with durable review logs.
5. Evaluate `model_only_tiled` and `pipeline_full` against the same
   human-audited labels.
6. Bucket the `77` baseline mismatch rows in a durable review log.

Current priority:

1. Inspect the reviewed first postprocessing dry-run plan on non-frozen data
   and decide whether to apply only safe reviewed tighten/merge actions or
   build geometry-review tooling for blocked expand/split cases first.
2. Define/generate candidate pools:
   `full_page_review_candidates_from_touched`,
   `mining_safe_hard_negative_candidates`,
   `synthetic_background_candidates`, and
   `future_training_expansion_candidates`.
3. Keep `synthetic_diagnostic` deferred until the real baseline and candidate
   pools are trustworthy enough to support diagnostic generation.

## Product Sequence

1. **Demo-grade workbook path:** already proven as a rough end-to-end flow from
   CloudHammer candidates into backend/export workbook output.
2. **First-pass text/OCR extraction:** exists as review scaffolding, but not as
   solved scope understanding.
3. **CloudHammer_v2 eval/reliability pivot:** current work; use the
   human-audited full-page eval to clarify model-vs-pipeline behavior and create
   guarded next-loop candidate pools.
4. **CloudHammer_v2 training improvement:** resume only after the frozen real
   eval baseline exists.
5. **Detail extraction:** improve itemized/detail extraction from accepted
   cloud regions after detection/crop trust improves.
6. **Client workflow integration:** align output with Kevin's pricing/review
   workflow and modification/RFI context.
7. **Production hardening:** repeatable runs, artifact hygiene, deployment
   notes, and project-specific security gates.

## Near-Term Exit Criteria

- Frozen real eval pages are protected by guards.
- Full-page ground truth labels exist with label status recorded.
- `model_only_tiled` and `pipeline_full` are reported separately.
- Baseline mismatch cases are human-audited and bucketed before training or
  tuning; current signal points to postprocessing-first work.
- Candidate pools are defined separately from eval subsets.
- Synthetic diagnostics remain deferred until the real baseline and candidate
  pools are trustworthy.
- Repetitive review queues must report item count and consider GPT-5.5
  provisional prefill before asking for manual review.
- Root docs and `CloudHammer_v2` docs stay separated by responsibility.

## Current Non-Goals

- Do not reorganize source code or data while creating the eval pivot.
- Do not move existing datasets, model runs, or legacy `CloudHammer/` assets.
- Do not blend synthetic diagnostic scores with real eval scores.
- Do not treat future-project GPT approval as implied by the current project
  exception.
