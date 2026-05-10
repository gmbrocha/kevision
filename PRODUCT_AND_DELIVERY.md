# Product And Delivery

Status: canonical product/deliverable summary as of 2026-05-10. Historical
source content is archived under `docs/archive/docs_archive_2026_05_02/`.

## Product Goal

ScopeLedger should help turn drawing revision packages into reviewable change
evidence and deliverables that Kevin's team can use for pricing, coordination,
and client review.

The product is not intended to silently decide scope. It should preserve
evidence, surface uncertainty, and keep a human verification step in the loop.

## Deliverable Shape

Expected deliverables include:

- revision/cloud evidence rows
- sheet and page context
- crop or full-page visual evidence
- extracted or reviewable text/detail context where available
- review flags and reasons
- export/workbook output suitable for client-facing review

## Current Delivery State

- A private client-handoff app path is active at `ledger.nezcoupe.net` behind
  Cloudflare Access and a local Waitress server.
- The app project registry intentionally starts empty; a real project should
  be created in `/projects`, then populated from uploaded PDFs or allowed
  server-local revision packages.
- Populate runs the current local drawing-analysis pipeline and writes normal
  review items into the app. These detections are evidence for human review,
  not automatic scope approval.
- Large remote PDF uploads use chunked browser upload, then reconstruction
  inside the active app project workspace.
- First-pass text/OCR extraction exists as review scaffolding, but broad OCR
  context and symbol/legend interpretation remain active quality risks.
- First real app-run findings are captured in `FINDINGS_FIRST_REAL_RUN.md`;
  those notes are observational only and are not training labels or reviewed
  client scope.
- `CloudHammer_v2` remains the active detection/eval/training policy
  workspace. Training/eval work resumes after handoff at the documented
  crop-inspection return point.

## Trust Principle

The product should operate as trust-but-verify:

- preserve visual evidence
- avoid guessing scope when evidence is unclear
- flag uncertain rows
- separate model/pipeline confidence from human acceptance
- keep final deliverables reviewable

## References

- Architecture: `docs/ARCHITECTURE.md`
- Data flow: `docs/DATA_FLOW.md`
- Client workflow: `docs/CLIENT_WORKFLOW.md`
- Detection subsystem: `CloudHammer_v2/README.md`
