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
