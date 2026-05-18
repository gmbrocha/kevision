# App Audit: Populate Workspace Efficiency

Date: 2026-05-18

Scope: ScopeLedger app-layer Populate Workspace runtime, especially the Pre
Review API stage. This audit does not change CloudHammer_v2 eval/training
policy, revision detection semantics, review state semantics, exports, API
contracts, stored data structures, or source drawing packages.

## Current Populate Flow Reviewed

- Revision package planning validates staged packages, package revision
  numbers, fingerprints, dirty reasons, and reusable package-level runs.
- Dirty packages run the local CloudHammer full-page pipeline; clean packages
  reuse prior package output.
- Populate assembles package manifests into a project-level live scan, then
  rescans/imports review data.
- App enrichment extracts scope text, builds the same-sheet keynote registry,
  resolves legend context, runs Pre Review API enrichment when enabled, and
  applies deterministic keynote expansion after Pre Review.
- Overview polls `/workspace/populate/status` for package progress, artifact
  counts, keynote counts, Pre Review counts, and final review/export context.

## Implemented In This Pass

- Increased default `SCOPELEDGER_PREREVIEW_CONCURRENCY` from `2` to `3` API
  batch workers. The existing override remains bounded to `1..4`.
- Added provider-level shared rate-limit backoff. When a worker receives a
  rate-limit response, all workers pause behind the same retry window before
  making the next OpenAI request.
- Preserved the existing per-request retry cap, exponential fallback, and
  `retry-after` handling. `retry-after` is preferred when the API provides it.
- Added retry and rate-limit backoff counts to Pre Review request metadata and
  populate status summaries for operational inspection.

## Expected Impact

The third worker should reduce wall time for projects where GPT/API latency is
the bottleneck and current account limits can absorb another concurrent batch.
If rate limits appear, shared backoff should keep retries coordinated instead
of allowing every worker to immediately retry into the same limit window.

## Further Efficiency Candidates

1. Add stage-duration instrumentation to Populate status/history.
   This should record package planning, CloudHammer processing/reuse,
   manifest assembly, scan import, scope extraction, keynote registry, legend
   context, Pre Review, keynote expansion, and final save timing. This is the
   next highest-value step because it will separate API latency from local PDF
   and CloudHammer costs.

2. Tune Pre Review batch size after collecting duration and usage data.
   The current default batch size is `5`. Larger batches may reduce request
   overhead, but they should be tested against response reliability and token
   limits before changing the default.

3. Consider a background Populate job if browser/tunnel timeouts reappear.
   This would improve operational reliability more than raw compute speed, and
   should be treated as a workflow change with durable job state.

4. Profile CloudHammer dirty-package processing before adding package-level
   parallelism. Parallel package execution could help multi-package projects,
   but it may compete for the same CPU/GPU/PDF-render resources and should not
   be added without timing data.

5. Tighten dirty-work detection further.
   Package reuse already avoids clean runs. A later pass could evaluate
   page-level or candidate-level fingerprints where package-level dirtiness is
   too broad, but it must preserve revision/package auditability.

6. Reuse expensive page context more broadly.
   Existing fixes reuse PDF words for scope extraction. Similar measured
   caching may be useful for repeated sheet metadata, OCR/context, and export
   row collection if profiling shows those stages are visible.

## Deferred

- No change to CloudHammer execution policy.
- No background job conversion.
- No export/review schema changes.
- No stored workspace data migration.
- No change to the meaning of Pre Review 1, Pre Review 2, reviewer selection,
  approvals, rejections, legends, or supersession.
