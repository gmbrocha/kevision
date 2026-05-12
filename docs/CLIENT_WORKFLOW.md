# Client Workflow

Status: client workflow summary as of 2026-05-12.

## Workflow

1. Create or select an app project from `/projects`.
2. Stage drawing/revision packages through browser PDF upload, browser folder
   selection, or an allowed server-local import root.
3. Run Populate to perform drawing analysis and create reviewable detected
   revision regions.
4. Review detected regions, visual evidence, sheet context, OCR/context text,
   and previous/current comparisons.
5. Accept or reject review items before using them as deliverable evidence.
6. Generate and review workbook/review-packet output before treating it as
   client-facing.

For local testing cleanup, archive projects when the workspace should be kept.
Use the Projects page Delete action only for disposable projects; it requires
typing `DELETE` and removes the app-managed project workspace.

## Trust-But-Verify Principle

ScopeLedger should reduce review burden, not remove responsibility for review.
When evidence is unclear, the product should flag uncertainty rather than infer
scope, contractor, cost, or intent.

For repetitive queues, report item count and estimated burden before asking for
manual review. GPT-prefilled decisions are provisional until human accepted.

## References

- Walkthrough exports live in `docs/references/`.
- First real-run observations live in `FINDINGS_FIRST_REAL_RUN.md` and are
  triage notes, not review labels.
- Benchmark templates and response tracker files live in `docs/references/`
  unless later promoted into a specific runbook.
- Meeting notes remain under `docs/meetings/` and are historical context, not
  canonical source-of-truth unless summarized into these docs.
