# V1 Demo Decisions

Status: current as of Kevin's 2026-04-24 answers.

This file turns stakeholder answers into product decisions for the first
actual-working demo.

## Primary Demo Goal

Produce a useful revision/modification workbook that Kevin's team can review in
Excel.

The demo should prove:

- changed sheets and clouded/change areas can be found,
- extracted change rows are legible,
- uncertain items are clearly flagged for human review,
- the workbook fits the team's shared-file / Excel workflow.

## Review Surface

Decision: Excel is the canonical v1 review surface.

Reason:

- Kevin's team is comfortable in Excel.
- He does not yet know what an app review flow should look like.
- A review list in Excel can be worked internally by the team.

Implementation:

- Add `Needs Review` and `Review Reason` columns.
- Do not rely on numeric confidence in the visible workbook.
- Keep numeric confidence internally for thresholds and debugging.

## Confidence Policy

Decision: show simple review flags, not confidence percentages.

Reason:

- Kevin does not see confidence as directly equivalent to accuracy.
- A low-confidence item may still be correct.
- The important thing is that questionable items are caught by the team.

Implementation:

- User-facing workbook: `Needs Review`, `Review Reason`.
- Internal data: retain model/parser confidence values.

## Recall vs Noise

Decision: bias toward catching more relevant items.

Reason:

- Missed small changes can cost significant money later.
- Extra review is acceptable if the items are relevant.
- Random false positives that add review time are not acceptable.

Implementation:

- Use conservative thresholds for omission.
- Flag uncertainty rather than dropping potentially relevant changes.
- Invest in hard-negative training to reduce random noise.

## Revision Package Grouping

Decision: do not assume filenames alone determine package/mod grouping.

Reason:

- Shared file, Government letter, and modification log are the correlation
  source today.
- Files can be issued separately.
- Grouping is currently manual.

Implementation:

- V1 should allow manual grouping/confirmation.
- If package membership is inferred, mark it reviewable.

Anchor:

- Kevin sent `Biloxi RFP and Undefinitized Mod response tracker.xlsx`.
- Analysis: `docs/anchors/mod_response_tracker_analysis.md`.

This appears to be the higher-level shared-file tracker for RFPs, mods,
response dates, costs, commitments, and action history. It is not the same as
the detailed drawing-change workbook, but our output should be easy to connect
back to one of its Mod/RFP rows.

## Duplicate Sheet PDFs

Decision: compare bottom-left revision dates.

Reason:

- If a standalone sheet PDF and a full-package sheet have the same latest
  revision date, both can be trusted.
- If dates differ, the latest should win.

Implementation:

- Detect duplicate sheet IDs.
- Compare revision dates when available.
- If dates mismatch or content differs unexpectedly, flag for review.

## Workbook Header

Decision: make the header task-aware.

For Modification work, include:

- Modification title/number, such as `Modification 5`
- drawing revision date when available
- modification issuance date when available

Final exact header fields should be confirmed after Kevin sees the first demo
workbook.

## Summary View

Decision: detailed workbook first.

Reason:

- Kevin needs to see examples before deciding whether a simpler summary is
  useful.

Implementation:

- Do not block v1 on a separate summary.
- Optional simple summary tab is fine if cheap.

## Current Drawing Set / Conformed Set

Decision: do not model current-set update as simple sheet replacement only.

Reason:

- RFI information, ESA notes, and comments from superseded sheets must carry
  forward.
- RFIs can address dimensions/layout without a formal revision set.

Implementation for v1:

- At minimum, flag superseded sheets where prior notes/comments may need
  carry-forward review.
- Full RFI ingestion/automation remains backlog unless explicitly pulled into
  demo scope.

## Not Required For V1

- Custom viewer integration.
- Fully automatic subcontractor assignment.
- Numeric confidence display in the workbook.
- Fully automated RFI handling.
- Replacing Kevin's full RFP / undefinitized mod response tracker.
