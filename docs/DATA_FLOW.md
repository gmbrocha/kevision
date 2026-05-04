# Data Flow

Status: canonical high-level data flow as of 2026-05-02.

## Flow

1. Source drawings enter through `revision_sets/` or durable resources.
2. CloudHammer_v2 evaluates and detects revision-cloud regions.
3. Human review/audit verifies uncertain labels, frozen eval truth, and
   deliverable evidence.
4. Backend workflows consume accepted detection outputs and package context.
5. The application produces reviewable exports/workbooks and client-facing
   evidence.

## Human-In-The-Loop Points

- Frozen `page_disjoint_real` eval pages should be human-reviewed directly.
  GPT full-page output on those pages is scratch only. GPT-5.5 prelabeling is
  appropriate for cropped training/review candidates with `gpt_provisional`
  status.
- Detection outputs may need review before deliverable inclusion.
- Scope/detail text remains reviewable evidence, not final automated truth.

## Boundaries

Root docs describe the application flow only. Detailed detection mechanics,
model-only vs pipeline eval, and labeling policy live under
`CloudHammer_v2/docs/`.
