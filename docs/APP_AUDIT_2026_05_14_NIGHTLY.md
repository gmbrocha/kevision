# Nightly App Audit - 2026-05-14

Scope: final application-layer audit after the incremental Populate, package
review filter, keynote registry, pipeline efficiency, and PL505/PL511 sheet
metadata fixes. CloudHammer_v2 training/eval policy and datasets were not
changed.

## Paths Audited

- Populate package planning, scan-cache short-circuiting, and package history
  status.
- Review queue filters, detail navigation, superseded-item redirects, and
  geometry correction flow.
- Export/readiness surfaces and the Overview duplicate readiness-card removal.
- Current project docs for stale handoff/testing guidance.

## Findings Fixed

### Geometry correction could seed replacement items with stale text

Finding: `Correct overmerge` / `Correct partial` created replacement review
items from the last persisted `reviewer_text` or raw text only. If the reviewer
had current text visible in the scope textarea that had not been independently
saved, the replacement child could reopen with stale text. This matched the
kind of confusing review loop seen while testing overmerge correction.

Fix: the geometry correction route now accepts the current review textarea text,
the browser sends it when saving a correction, and replacement child items use
that text as their initial raw/reviewer text.

### Detail pending link dropped current package review scope

Finding: the pending-count link on the review detail page always returned to
the global pending queue, even when the reviewer was inside a package-scoped
queue.

Fix: the link now preserves search, attention, and package filter parameters.

## Findings Confirmed Without New Code

- The PL505/PL511 issue was a sheet metadata parsing/cache problem, not a
  package supersede problem. Commit `12a83ab6` fixed the parser, scan cache
  versioning, and review-state preservation by stable CloudHammer candidate id.
- The active local `TEST Revision` workspace can still display stale PL511
  sheet labels until `Populate Workspace` is run once after that commit. The
  package runs should be reused, while the scan metadata refreshes.
- The lower Overview export readiness card is removed in current templates and
  verified absent from the running server response.

## Verification

- Targeted geometry/filter tests passed after this audit.
- Full app regression suite should be run before the final commit for the
  nightly checkpoint.

## Residual Risk / Morning Smoke

- Run one Populate on the active reduced-copy test project, then confirm the
  PL505 drawing overlays and version chain are relabeled correctly.
- Exercise `Correct overmerge`, accept the first replacement child, and confirm
  navigation advances to the next child rather than reopening the accepted one.
- Export after approving one Revision 1 and one Revision 2 item on the same
  sheet to confirm revision-scope carry-forward remains intact.
