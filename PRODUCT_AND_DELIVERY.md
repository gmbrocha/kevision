# Product And Delivery

Status: canonical product/deliverable summary as of 2026-05-02. Historical
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

- A rough demo-grade workbook path has been proven.
- First-pass local text/OCR extraction exists as review scaffolding.
- Cloud detection reliability is the active blocker.
- `CloudHammer_v2` is now the active detection/eval subsystem.

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
