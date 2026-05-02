# Deployment

Status: deployment notes as of 2026-05-02.

ScopeLedger is not yet in a polished production deployment state. Current work
is focused on establishing a reliable detection/eval baseline before broader
rollout.

## Current Assumptions

- Work is local/development oriented.
- Generated datasets, model runs, and large outputs stay local unless
  explicitly promoted.
- `CloudHammer_v2` is not yet a packaged service; it is the active eval-pivot
  workspace.
- Existing `CloudHammer/` remains legacy/reference.

## Before Rollout

- Freeze and score real full-page eval.
- Document repeatable scan/eval/export commands.
- Keep generated artifacts out of canonical docs.
- Revisit security approval for any new client/project.
- Clarify which outputs are deliverable-ready versus diagnostic.
