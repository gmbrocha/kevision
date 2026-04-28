# Stakeholder Answers Part 2

Source: Kevin response relayed 2026-04-24.

Status: canonical for the current open workflow/product questions.

## Revision Package Consistency

Question: If there is more than one revision package for the same job, do they
always point back to older changes the same way, or does it vary?

Answer:

- Old changes will not be clouded again in this Architect's current revision
  sets.
- Old changes do have an indicator next to the changed area listing which
  revision it belongs to.
- The same project is typically consistent because the same Architect/Engineer
  uses the same convention.
- This may vary on a new project or with a new Architect.

Product implication:

- For a single project, learn and apply the project's convention.
- Across projects, do not hard-code one universal convention.
- For v1, clouds plus revision indicators are both important signals.

## Mod / Revision Package Grouping

Question: Is there usually a main file, cover page, or folder setup that tells
you which revision packages belong together?

Answer:

- There is a shared file where information is included.
- The Government letter should indicate this.
- Sometimes files are issued separately, but ideally they reference the
  correlation.
- This is currently a manual task.
- Kevin tracks modifications with a modification log.

Product implication:

- Do not assume filenames alone are enough to group revision packages.
- The v1 app should allow manual grouping or confirmation.
- The modification log / Government letter is the likely source of truth when
  available.

## Duplicate Sheet PDFs

Question: If the same sheet is in the full package and also sent as its own
separate PDF, which one should we trust?

Answer:

- If both have the same revision date on the bottom-left side, they should be
  the same file from the Architect/Engineer.
- Both can be trusted if the revision date matches and is the latest.

Product implication:

- Compare revision dates when duplicate sheets appear.
- If dates match, either copy can be trusted.
- If dates differ, prefer the latest and flag for review.

## Detailed Workbook vs Summary

Question: Do you want just the detailed workbook, or would a second simpler
summary also be useful?

Answer:

- Kevin needs to see examples before deciding.

Product implication:

- For v1 demo, produce the detailed workbook first.
- A simpler summary can be shown as an optional second tab/example, not a
  blocker.

## Workbook Header

Question: What info do you want at the top of the workbook every time?

Answer:

- It depends on the task.
- If it is specifically a Modification, include a title labeling it as
  something like `Modification 5`.
- Drawing revision date or modification issuance date may be useful.

Product implication:

- Header should be task-aware.
- Include Mod title/number when known.
- Include revision date / mod issue date when available.
- Leave uncertain fields blank or review-flagged rather than guessing.

## Human Review Surface

Question: If the tool is not sure about something, how should the team review it:
in an app, in Excel, or both?

Answer:

- Excel is easy.
- Kevin does not know what the app would look like, so cannot judge that yet.
- Everyone on the team is familiar with Excel.
- As long as the information/question is in Excel, the team can work through
  the list internally.

Product implication:

- Excel is the canonical v1 review surface.
- The workbook should contain review questions/flags inline.
- The app can still exist, but v1 should not depend on app-only review.

## Confidence Display

Question: Should the workbook show actual confidence scores or just a simple
needs-review flag?

Answer:

- Kevin questioned whether confidence maps directly to accuracy.
- A low confidence item could still be accurate.
- A simple `needs review` flag is good because it ensures the item is caught by
  the team.

Product implication:

- Use `Needs Review` / `Review Reason` instead of numeric confidence in the
  primary workbook.
- Keep numeric confidence internally for thresholding/debugging.

## Catch More vs Be Selective

Question: Should the tool catch more and send extra items to review, or be more
selective and risk missing things?

Answer:

- Catch more, as long as it is not catching random things that increase review
  time.
- Missing small things can cost large amounts of money later if not
  incorporated.
- More is better if it is relevant information.

Product implication:

- Tune for high recall on relevant revision/change signals.
- Use review flags to manage uncertainty.
- Avoid noisy random false positives because review time still matters.

## First Action When a Revision Package Lands

Question: When a new revision package comes in, what is the first thing you
usually do?

Answer:

- In a perfect world, the Owner sends a Scope of Work letter or document showing
  which plans changed.
- Kevin's team reviews the changed plans.
- They send the package to all subcontractors.
- While subcontractors review, Kevin's team refines the exact scope and
  determines which subcontractors should price it.
- Then they follow up with the specific affected subcontractors.
- Sometimes one subcontractor is affected; sometimes 3 or 15.

Product implication:

- V1 should help identify changed sheets and affected scope quickly.
- Contractor assignment can remain blank/manual in v1.
- The workbook should support downstream subcontractor follow-up.

## Custom Viewer

Question: You mentioned a custom viewer before. What is it, and do we need to
work with it?

Answer:

- Kevin was not sure what this referred to and asked for more context.

Product implication:

- No custom-viewer integration is required for v1.
- Keep this as a low-priority clarification only if it resurfaces.

## Current Tracking Workflow

Question: How are you tracking this today?

Answer:

- A mix of tools.
- Modification Log in Excel for general information, Government estimate, due
  date, and updates.
- Bluebeam notes.
- Sometimes a specific mod document.
- Whoever puts the mod together may use Word, Excel, handwritten notes, or
  other methods.
- The shared file is the workflow hub.
- It stores general information, quotes, Government mod letter, schedule info,
  ESA estimate templates, VA proposal forms, and related files.

Product implication:

- Excel compatibility is critical.
- The tool should fit into a shared-folder workflow.
- Do not assume one current source of truth besides the shared file and mod log.

## Updating The Current Drawing Set

Question: When you update the current drawing set, is it mostly swapping old
sheets for new sheets, or is there more to it?

Answer:

- There is more to it.
- RFI information and relevant notes need to be transferred.
- RFIs must be incorporated onto the plans.
- RFIs may address things like water line location or ceiling height.
- If RFIs are no-cost or extremely minor, a revision set may not be issued.
- It is critical that RFIs addressing a dimension or layout remain on the plans.
- When a revision set is issued, comments from the superseded previous page need
  to be transferred to the latest drawing so RFI comments and ESA notes are not
  lost.

Product implication:

- The conformed/current-set workflow is not just sheet replacement.
- Carry-forward of prior RFI comments and ESA notes is important.
- For v1 demo, at minimum flag superseded sheets where prior notes/comments
  need carry-forward review.
- Full RFI incorporation can remain backlog unless demo scope explicitly expands.
