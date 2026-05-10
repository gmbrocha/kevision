# Data Flow

Status: canonical high-level data flow as of 2026-05-10.

## Flow

1. Source drawings enter through browser PDF upload, browser folder selection,
   or allowed server-local roots such as `revision_sets/`.
2. App project workspaces copy or reconstruct PDFs into the selected project's
   input folder; durable source packages are not moved or deleted.
3. Populate runs the current local drawing-analysis pipeline and writes
   generated review artifacts under the selected project workspace.
4. Backend workflows scan generated candidates, sheet context, OCR/context
   text, and diagnostics into normal app review surfaces.
5. Human review accepts or rejects review items before deliverable use.
6. The application produces reviewable exports/workbooks and client-facing
   evidence.

## Human-In-The-Loop Points

- Frozen `page_disjoint_real` eval truth should be confirmed directly.
  GPT full-page output on those pages is scratch only. GPT-5.5 prelabeling is
  appropriate for cropped training/review candidates with `gpt_provisional`
  status.
- Detection outputs may need review before deliverable inclusion. Repetitive
  review queues should report item count and consider GPT-5.5 provisional
  prefill before manual review is requested.
- Scope/detail text remains reviewable evidence, not final automated truth.
- Exploratory app-run observations in `FINDINGS_FIRST_REAL_RUN.md` are triage
  notes only and do not become labels or training data without a durable review
  workflow.

## Boundaries

Root docs describe the application flow only. Detailed detection mechanics,
model-only vs pipeline eval, and labeling policy live under
`CloudHammer_v2/docs/`.
