# Decision Log

Status: canonical application decision log.

## 2026-05-02 - CloudHammer_v2 Eval-Pivot Workspace

Created `CloudHammer_v2/` as the active eval-pivot workspace. Existing
`CloudHammer/` is legacy/reference until code is audited and imported.

## 2026-05-02 - Separate Eval Subsets

The eval corpus is split into separate named subsets:

- `page_disjoint_real`
- `gold_source_family_clean_real`
- `synthetic_diagnostic`

Scores must not be blended across these subsets.

## 2026-05-02 - Synthetic Diagnostics Deferred

Synthetic diagnostics are important but deferred until the real full-page eval
baseline exists. Grammar/spec stubs may be written first.

## 2026-05-02 - GPT Project Exception

GPT/API use is broadly allowed for the current project under Kevin/boss
approval. This does not automatically apply to future projects.

## 2026-05-02 - Documentation Archive Location

Documentation archives live under `docs/archive/`. The root `archive/` remains
for old scripts, experiments, outputs, and implementation artifacts.

## 2026-05-02 - Root Pointer Docs Removed

Archived root pointer/tombstone docs and folded the CloudHammer pointer into
`README.md` and `docs/MODULES.md`.

## 2026-05-05 - Review Requires Durable Decisions

Do not treat passive visual look-over as a review gate. Review tasks must have
a way to persist decisions, corrections, labels, candidate metadata, or notes
before they block implementation.

Reason: static output inspection repeatedly creates ambiguous next steps and
does not produce usable inputs for later workflows.

Consequences:

- Review surfaces should write or pair with a manifest, CSV, JSONL, label file,
  or review log.
- Read-only screenshots, overlays, and static viewers are context only unless
  they are paired with a durable decision record.
- If direct mutation is risky, capture decisions separately first and consume
  them through a dry-run or explicit apply step.

## 2026-05-08 - Review Viewers Require Visual Evidence

Review viewers, inspection packets, contact sheets, and similar human-facing
artifacts must show the decision target directly on the image. For detection
and geometry workflows, raw crops are not enough; the viewer must render the
candidate bbox, truth bbox, prediction bbox, crop boundary, or other relevant
overlay needed to understand the requested decision.

Reason: repeated review packets without visible boxes forced the reviewer to
infer what the machine meant from metadata, which is not a reasonable human
review task and creates avoidable drift.

Consequences:

- Human-facing review artifacts must include visual overlays or explicitly mark
  the row as missing visual evidence.
- Raw-image-only viewers are acceptable only when the raw image itself is the
  decision target.
- This rule complements the durable decision-record rule; both are required for
  review gates.
