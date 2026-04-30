# Product And Deliverable

Status: current source of truth for ScopeLedger product behavior, stakeholder
decisions, workbook/export shape, benchmark plan, open questions, and backlog.

## Product Goal

ScopeLedger should help Kevin's team turn blueprint revision packages into a
reviewable Excel workbook that captures all relevant change information
clearly enough for downstream pricing/build coordination.

The tool should prove that:

- changed sheets and clouded/change areas can be found
- latest drawing versions can be identified
- extracted change rows are legible
- uncertain items are clearly flagged for human review
- the workbook fits the team's shared-file and Excel workflow

## Guiding Principle

Kevin's guiding standard from 2026-04-22:

> As long as we have all the information, and it's legible.

Completeness plus legibility wins. Do not guess fields that cannot be verified.
Prefer leaving a field blank for a human over inventing a contractor, cost, or
certainty level. Do not drop rows that preserve location/context, even if they
look redundant.

## V1 Review Surface

Excel is the canonical v1 review surface.

Reasons:

- Kevin's team is comfortable in Excel.
- He does not yet need or want a custom viewer as the mandatory review surface.
- Excel can carry review flags, notes, and blanks for downstream pricing.
- Review copies should also be placed in Google Drive under `/kevin_usage/`
  so they can be opened in Google Sheets when local Excel is unavailable.

Implementation policy:

- Add user-facing `Needs Review` and `Review Reason` fields when uncertainty
  needs to be surfaced.
- Do not show numeric confidence as the primary review signal.
- Keep numeric confidence internally for thresholds and debugging.
- For future review exports, upload/copy review workbooks to Google Drive
  folder `kevin_usage`:
  `https://drive.google.com/drive/folders/1_6LogBKmxt38bF9dGBPyc1l_z38z1MaT`.

## Recall And Noise Policy

Bias toward catching more relevant items. Missed small changes can cost serious
money later. Extra review is acceptable when the candidate is plausibly
relevant; random false positives are not acceptable because they burn reviewer
time and trust.

Practical policy:

- Do not silently omit potentially relevant changes because confidence is low.
- Flag uncertainty rather than dropping it.
- Invest in hard negatives so the review queue is not filled with random
  geometry.
- Treat human review as mandatory until the system is proven against Kevin's
  workflow.

## Revision / Mod Concepts

Current terminology:

- Revision set: the issued package, such as `Revision #1 - Drawing Changes`.
- Revision: one revised sheet row from an index.
- Change item: the smallest build/order/remove thing inside a cloud/detail.
- Drawing: an individual page; one sheet page can contain multiple drawings.
- Mod: a higher-level pricing/owner wrapper that can contain one or more
  revision sets.

Confirmed behavior:

- Mod to revision set is 1:N, not guaranteed 1:1.
- Later revision sets may point back to earlier changes without re-clouding the
  older change.
- The shared file, Government letter, and modification log are likely the
  source of truth for grouping.
- Do not rely on filenames alone for package/mod grouping.
- V1 should support manual grouping/confirmation if package membership is
  inferred.

## Duplicate And Carry-Forward Rules

Confirmed rules:

- Multiple identical clouds on the same sheet generally split into separate
  rows so the order list remains accurate.
- Same note inside the same detail collapses to one row.
- Same note in different details on the same sheet remains separate.
- Same note across sheets referencing one master detail should remain called
  out, with wording such as `See XX Detail for reference`.
- Cross-sheet duplicates should be noted per sheet for now.
- If multiple scope items are in the same cloud, they can be one workbook row
  as long as the specific cloud's included items are listed.
- If multiple small clouds are near each other but clearly separate, list them
  as separate details.
- If duplicate standalone/package sheet PDFs differ or might differ, duplicate
  the candidate rows and let the reviewer compare both instead of silently
  choosing one.

Current-set updates are more than sheet replacement. RFI information, ESA
notes, and comments from superseded sheets may need to carry forward to the
latest sheets. Full RFI automation is backlog, but v1 should at least flag
superseded sheets where prior notes/comments may need review.

## Duplicate Sheet PDFs

If a standalone sheet PDF and a full-package sheet have the same latest
bottom-left revision date, both can be trusted.

If dates differ or the content appears to differ:

- keep both candidate sources visible for reviewer comparison
- flag the conflict/redundancy for review
- do not assume the package PDF always wins

Known open case:

- Rev 2 includes both the main package and standalone AE107 / AE107.1 PDFs.
- `Drawing Rev2- Steel Grab Bars R1 AE107.1.pdf` appears to cloud a slightly
  larger area than the main package's AE107.1 page.
- Kevin's current preference is to duplicate both sources and let the reviewer
  confirm whether they are actually different.

## Current Workbook Shape

Canonical anchor file:

- `docs/anchors/mod_5_changelog.xlsx`

Implementation:

- workbook exporter: `backend/deliverables/revision_changelog_excel.py`
- export wiring: `backend/deliverables/excel_exporter.py`
- command: `python -m backend export workspace`
- smoke test: `tests/test_app.py::test_revision_changelog_xlsx_matches_expected_layout`

Observed workbook shape:

- one sheet named `Sheet1`
- 10 columns
- content rows plus many intentional spacer rows
- embedded PNG crops in the `Detail View` column
- merged cells in `Scope Included` for stacked numbered sub-items

Columns:

| Column | Header | Meaning |
| --- | --- | --- |
| A | `Correlation ` | readable grouping key, not a primary key |
| B | `Drawing #` | sheet ID such as `AD-105` or `AE-110` |
| C | `Revision # ` | package label plus date |
| D | `Detail #` | `N/A - Cloud Only`, `Cloud Only`, or `Detail <n>` |
| E | `Scope Included ` | single scope line or stacked numbered sub-items |
| F | `Detail View ` | embedded crop image |
| G | no header | Kevin's ad-hoc manual notes; do not reproduce automatically |
| H | `Responsible Contractor` | downstream pricing field, emit blank |
| I | `Cost?` | downstream pricing field, emit blank |
| J | `Qoute Received?` | downstream pricing field, emit blank; preserve typo |

## Correlation And Rows

`Correlation` is a grouping key. One logical change can span more than one row.
Do not treat it as a primary key.

Cloud-only plan change:

- `Detail #`: `N/A - Cloud Only` or `Cloud Only`
- `Scope Included`: direct description of the changed scope
- `Detail View`: crop of the clouded region

Plan cloud enclosing a detail callout:

- emit a `Cloud Only` anchor row pointing to the detail
- emit a `Detail <n>` row carrying the actual detail scope
- both rows may share the same correlation value

Dropping the `Cloud Only` anchor loses location/context and violates the
completeness principle.

Leader-only cloud with no readable scope:

- `Scope Included` should say `See Detail <n> on <sheet/page> for scope` when
  the referenced detail can be identified.
- The row should reference which deliverable row/detail carries the actual
  scope when that relationship is known.
- If the referenced detail cannot be identified, keep the row and flag it for
  review rather than inventing scope.

Multiple drawings/details on one sheet:

- each detail must be listed separately.
- Sheet-level reference alone is not enough when the page contains multiple
  details.

## Scope Included Rules

`Scope Included` may be:

- a single line of scope text
- a numbered list of sub-items inside one logical row

Sub-item rollup has implementation freedom. Default to one row per cloud/detail
with bullets stacked in `Scope Included`, matching Kevin's Mod 5 workbook.

Kevin confirmed on 2026-04-28 that multiple items in one cloud can remain one
row if the row lists the items included in that specific cloud.

## Scope Extraction Tracker

Status as of 2026-04-30:

- current CloudHammer-backed rows still often use placeholder text instead of
  useful scope descriptions
- the next implementation slice is OCR/detail extraction from cloud context
  crops
- first PDF text-layer pass is wired and was backfilled onto the active demo
  workspace: 217 CloudHammer clouds produced 12 `text-layer-near-cloud`, 150
  `needs-reviewer-rewrite`, 35 `index-or-title-noise`, and 20
  `leader-or-callout-only`; extraction methods were 196 PDF text-layer and 21
  local Tesseract OCR fallback
- simple OCR is expected to be only partially effective; it should improve the
  starting text for review, not pretend to fully understand scope
- review confidence/reason fields are appropriate now because they make weak
  extraction explicit

First-pass extraction should:

- expand each cloud bbox into a larger source-PDF context crop
- read PDF text-layer words inside and near that expanded region
- use local OCR fallback only where available and safe
- prefill `Scope Included` / reviewer text with the best candidate text when
  the evidence is usable
- leave placeholder or reviewer-warning text when no readable scope is found
- record provenance for how the text was produced

Reviewer-facing confidence/reason examples:

- `text-layer-near-cloud`: PDF text was found near the cloud region
- `ocr-near-cloud`: OCR found plausible text near the cloud region
- `no-readable-text`: no usable text was found in the expanded region
- `leader-or-callout-only`: the cloud appears to point elsewhere instead of
  containing complete scope
- `needs-reviewer-rewrite`: extracted text is too noisy or broad to use
  directly
- `index-or-title-noise`: extracted text appears to be sheet index/title/block
  noise rather than scope

Running tally of extraction cases to handle later:

- detail references visible inside or just outside a cloud
- leader-only clouds pointing to details elsewhere
- detail-callout clouds where the actual scope lives on another sheet/detail
- clouds around multiple independent scope items
- multiple drawings/details on one sheet
- plan notes versus sheet title/index/revision-block text
- text that crosses cloud boundaries
- symbols or dimensions that matter even when OCR text is sparse
- repeated notes across sheets or details
- superseded-sheet notes that may carry forward to the latest set
- readable crop evidence with no trustworthy text extraction

## Crops / Detail View

`Detail View` should point at a crop image generated from the drawing and
preserved through export.

Crop size rule: whatever is legible.

Kevin has floated a more spacious report mode with roughly two changes per page
for maximum legibility. That is optional/future unless it becomes demo scope.

## Header Policy

Workbook header is task-aware.

For Modification work, include fields such as:

- Modification title/number, such as `Modification 5`
- drawing revision date when available
- modification issuance date when available
- project metadata when available

Final exact header fields should be confirmed after Kevin sees a first example.

## Not Required For V1

- Custom viewer integration as the canonical review surface.
- Fully automatic subcontractor assignment.
- Numeric confidence display in the workbook.
- Fully automated RFI handling.
- Replacing Kevin's full RFP / undefinitized mod response tracker.
- A separate rolled-up build/order summary before the detailed workbook is
  validated.

## Benchmark Plan

Benchmark scope:

- `Revision #1 - Drawing Changes`
- `Revision #2 - Mod 5 grab bar supports`

Measure whether the tool improves the manual workflow for:

1. building a conformed set of the latest drawings
2. surfacing clouded revisions on the correct sheets
3. producing a clear reviewable deliverable

Manual workflow:

- start timer when Kevin begins opening/comparing files
- stop when latest sheets, superseded sheets, and usable change rows/report are
  identified

Tool-assisted workflow:

```powershell
python -m backend scan revision_sets workspace_demo_accuracy
python -m backend serve workspace_demo_accuracy --port 5000
```

After CloudHammer is integrated enough to affect output, rerun the same
benchmark as `tool-assisted-cloudhammer`.

Record:

- elapsed minutes
- affected sheet count
- final deliverable row count
- review items seen/accepted/rejected/pending
- matching rows
- manual-only rows
- tool-only rows
- wrong latest sheet count
- unclear rows requiring rewrite
- notes

What good looks like:

- reduce total time by at least 30 to 50 percent
- correctly identify latest sheet versions
- avoid missing major clouded changes
- keep reviewer cleanup manageable
- produce a deliverable that is mostly review/edit, not rewrite-from-scratch

Template:

- `docs/rev1_rev2_benchmark_template.csv`

## Current Open Questions

Product/workflow:

- What exact header field list should appear after Kevin sees the first example?
- What iteration order does Kevin prefer: sheet-by-sheet, by trade, one
  revision set at a time, or multiple sets together?
- What does `R1` mean in standalone sheet filenames such as the AE107.1 case?
- Are there other pain points adjacent to revision packages that should shape
  v1 review/export?

Specific interpretation:

- SF110 row 14: identify the black-filled square inside the cloud.
- Textual cloud contents: should each dimension/note edit become its own change
  item?
- Index title vs drawing title: capture both verbatim unless told otherwise.
- Index page changes: decide whether revised index rows become change rows.
- Symbol overlaps cloud boundary: confirm centroid-containment is the right
  mental model.
- Delta marker, index X-column, and cloud disagreement: confirm whether this is
  always a review flag.

## Backlog

### RFI Handling

RFI handling is real but not v1 must-ship.

Future feature 1: auto-cloud RFI context areas when an architect response
references a drawing region but did not draw a cloud. This would generate a
synthetic cloud polygon so downstream extraction can use the same
thing-in-cloud workflow.

Future feature 2: document RFIs that have no drawing changes. These still
belong in the audit trail, but may need a separate row type or tab.

Need before scoping:

- representative RFI PDFs
- how RFIs anchor to drawings today
- who owns/issues/archives RFIs
- typical RFI volume per project/mod
- whether no-change RFIs belong in the same workbook or a separate artifact

## Reference Artifacts

Keep these as data/reference, not competing source-of-truth docs:

- `docs/anchors/mod_5_changelog.xlsx`
- `docs/anchors/kevin_email.txt`
- `docs/anchors/mod_response_tracker_analysis.md`
- `docs/rev1_rev2_benchmark_template.csv`
