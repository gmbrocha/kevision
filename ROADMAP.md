# ScopeLedger Roadmap

Status: canonical application roadmap as of 2026-05-15.

Detailed application docs live in `docs/`. Cloud detection details live in
`CloudHammer_v2/`.

## Active Pivot

The active application priority is the private client handoff: keep the app
registry clean, create a fresh project from `/projects`, stage drawing packages
through browser upload or allowed server-local import, run Populate, and verify
the review/export surfaces behind Cloudflare Access. The final app
release-readiness audit is recorded in
`docs/APP_AUDIT_2026_05_15_RELEASE_READINESS.md`.

CloudHammer_v2 training/eval work is paused only for this handoff pass. Resume
afterward at the crop-inspection return point documented in
`docs/CURRENT_STATE.md` and `FINDINGS_FIRST_REAL_RUN.md`.

Completed foundation:

1. Build touched-page registry and freeze guards.
2. Freeze `page_disjoint_real` from eligible full pages.
3. Directly confirm `page_disjoint_real` eval truth, with GPT outputs
   treated as scratch/provisional only.
4. Produce overlays/contact sheets for audit, paired with durable review logs.
5. Evaluate `model_only_tiled` and `pipeline_full` against the same
   human-audited labels.
6. Bucket the `77` baseline mismatch rows in a durable review log.

CloudHammer return priority:

1. Resolve or accept the `4` non-accepted GPT-5.5 crop-precheck rows, then use
   the `28` GPT-accepted crop-ready postprocessed candidates for crop-based
   inspection/export wiring if appropriate, or decide the next contained
   pipeline-consumption comparison from the behavior summary, regenerated
   crops, and GPT precheck.
2. Define/generate candidate pools:
   `full_page_review_candidates_from_touched`,
   `mining_safe_hard_negative_candidates`,
   `synthetic_background_candidates`, and
   `future_training_expansion_candidates`.
3. Keep `synthetic_diagnostic` deferred until the real baseline and candidate
   pools are trustworthy enough to support diagnostic generation.

## Product Sequence

1. **Private handoff app path:** current work; empty app registry, project
   creation, chunked PDF upload/import, incremental live Populate, package
   focused review, keyed-note expansion, legend soft-hide controls, and
   workbook/review packet export are the near-term product flow.
2. **First-pass text/OCR extraction:** exists as review scaffolding, but not as
   solved scope understanding. First real-run observations show broad OCR
   context and symbol/legend interpretation still need work.
3. **CloudHammer_v2 eval/reliability pivot:** paused during handoff; use the
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
