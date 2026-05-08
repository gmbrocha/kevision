# Client Workflow

Status: client workflow summary as of 2026-05-02.

## Workflow

1. Intake drawing/revision package.
2. Run detection/eval workflow to identify candidate revision-cloud regions.
3. Verify uncertain detections and labels with GPT-prefilled provisional review
   plus human confirmation/correction when queues are repetitive.
4. Preserve crop/full-page evidence and relevant sheet context.
5. Feed accepted evidence into backend/export workflow.
6. Review workbook/app output before treating it as client-facing.

## Trust-But-Verify Principle

ScopeLedger should reduce review burden, not remove responsibility for review.
When evidence is unclear, the product should flag uncertainty rather than infer
scope, contractor, cost, or intent.

For repetitive queues, report item count and estimated burden before asking for
manual review. GPT-prefilled decisions are provisional until human accepted.

## References

- Walkthrough exports live in `docs/references/`.
- Benchmark templates and response tracker files live in `docs/references/`
  unless later promoted into a specific runbook.
- Meeting notes remain under `docs/meetings/` and are historical context, not
  canonical source-of-truth unless summarized into these docs.
