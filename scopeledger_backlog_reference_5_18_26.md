# ScopeLedger Backlog Reference

_Date captured: 2026-05-18_

This is a parking-lot backlog for items noticed during testing and planning. These are **not immediate implementation tasks**. Use this as a reference for future cleanup, polish, testing, and Kevin handoff prep.

## Current State / Observations

### Pre-review queue may be stuck

- ScopeLedger appears stuck near the end of the pre-review queue at **189 / 194**.
- It seems like everything may already have been pre-reviewed, but the queue/status may not be resolving cleanly.
- Need to determine whether this is:
  - A real remaining-item issue.
  - A stale queue/counting issue.
  - A status/state mismatch.
  - A UI display issue only.

## Follow-up With Kevin

### Request more revision sets

- Ask Kevin whether he can provide more revision sets for broader testing.
- Goal is to test against more real-world variation before final handoff.
- Useful types to request:
  - Different project phases.
  - Different disciplines/trades.
  - Messier or more complex revisions.
  - Sets with known edge cases or unusual notation.

### Schedule a meeting

- Set up a meeting with Kevin before handoff.
- Purpose:
  - Walk through the current ScopeLedger workflow.
  - Explain what the tool does well.
  - Explain nuance and review expectations.
  - Clarify where human judgment is still required.
  - Gather feedback before final polish.

## UI / UX Cleanup Backlog

### Review queue cloud field may be unnecessary

- The **cloud field** in the review queue may not be needed.
- Reassess whether it provides meaningful information during review.
- If it does not help the user make decisions, consider hiding/removing it.

### Do another reduction pass for unneeded UI elements

- Perform one more UI reduction pass focused on removing or de-emphasizing anything that does not support the main workflow.
- Keep the workflow centered on:
  - Reviewing revisions.
  - Understanding confidence/status.
  - Exporting usable deliverables.
  - Avoiding unnecessary raw/debug/audit clutter in default views.

Possible targets for reduction:

- Duplicate status labels.
- Fields that are technically true but not useful to the reviewer.
- Overly detailed metadata in default views.
- Anything that feels like internal pipeline evidence rather than user-facing workflow support.
- Controls or labels that make the interface feel busier without improving decisions.

## Manual Review / QA Backlog

### Go through review items manually

- Manually inspect review items and look for "weird shit."
- This should be a human sanity pass, not just automated test coverage.
- Look for:
  - Odd classifications.
  - Duplicate or near-duplicate items.
  - Missing expected revisions.
  - Strange page/sheet associations.
  - Misleading confidence/status displays.
  - Review items that feel technically valid but operationally confusing.
  - Anything that would cause Kevin to pause, ask questions, or lose trust.

### Investigate pre-review completion behavior

- Specifically check the queue state around the final few items.
- Confirm whether item counts, statuses, and queue progression all agree.
- If the queue says **189 / 194**, identify what the remaining 5 items are supposed to be.
- Determine whether those items are hidden, already processed, invalid, filtered out, or blocked by status logic.

## Pre-handoff Polish

### Final polish audit

Before handoff, perform one more focused polish audit.

Audit goals:

- Confirm the core workflow feels clear and bounded.
- Confirm review/export paths are obvious.
- Confirm there is no unnecessary debug/internal clutter in default screens.
- Confirm status language is understandable.
- Confirm Kevin can tell what needs action versus what is already complete.
- Confirm the app presents as trustworthy, practical, and not overbuilt.

Areas to check:

- Dashboard / project status.
- Pre-review queue.
- Review item detail pages.
- Export flow.
- Settings or diagnostics views.
- Empty, loading, and completed states.
- Any final wording that might overpromise automation accuracy.

## Deferred Priority Grouping

### P1 - Before handoff

- Investigate the pre-review queue stuck at **189 / 194**.
- Manually inspect review items for strange or confusing behavior.
- Do a final polish audit.
- Schedule Kevin meeting.

### P2 - Cleanup / reduction

- Reassess the review queue cloud field.
- Run another UI reduction pass for unnecessary elements.
- Simplify or hide fields that do not support reviewer decisions.

### P3 - Additional testing material

- Ask Kevin for more revision sets.
- Use additional sets to broaden real-world testing coverage.

## Notes / Intent

This backlog is intentionally a parking lot. The goal is not to expand ScopeLedger right now. The goal is to preserve testing observations, UX cleanup ideas, and handoff prep items so they are not lost.

The main principle for future work: **reduce noise, preserve trust, and keep the reviewer focused on bounded decisions.**
