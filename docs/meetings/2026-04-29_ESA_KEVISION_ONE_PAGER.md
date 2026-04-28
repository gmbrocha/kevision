# KEVISION Meeting One-Pager - 2026-04-29

## Plain-English Pitch

KEVISION is being built to reduce the time and risk involved in reviewing
construction revision packages.

The current MVP finds suspected revision clouds on drawings, crops the evidence,
and puts those crops into an Excel workbook so a human can review them.

It is not trying to replace Kevin's judgment. It is trying to keep Kevin's team
from manually hunting through PDFs and missing changed scope.

## What Works Today

- Finds many real revision-cloud areas on blueprint sheets.
- Groups cloud fragments into larger whole-cloud crop candidates.
- Exports crop evidence into the real Excel deliverable workflow.
- Produces a workbook that can be opened and reviewed.
- Keeps generated project artifacts local.

Latest proof point:

- `137` suspected cloud crops exported into the real workbook:
  `runs/cloudhammer_real_export_v3/outputs/revision_changelog.xlsx`

## What Does Not Work Yet

- It does not reliably read the scope text inside the cloud.
- It does not yet produce final polished pricing descriptions.
- It does not yet fully handle RFIs or modification package workflow.
- It still needs more tuning for false positives, overmerged clouds, and missed
  clouds.

## Why It Matters

Manual revision review is slow and risky because someone has to:

- identify the latest drawing versions
- find every clouded change
- decide which changes matter for pricing/build coordination
- collect crop evidence
- organize it into a usable workbook

KEVISION's first business value is reducing the search-and-crop burden while
keeping a human in control.

## Security Position

Default position:

- source PDFs stay local
- text layers stay local
- RFIs and modification documents stay local
- workbooks stay local
- no live external API use without ESA approval

Possible future OpenAI API use:

- only as a fallback for low-confidence cloud-shape confirmation
- only after sanitizing the image so readable project information is removed
- only if ESA approves the policy

## What We Need From Kevin / ESA

Security:

- Who should review/approve the security policy?
- Is sanitized external API fallback allowed at all for live project data?
- Are Zero Data Retention or other vendor controls required?

Product:

- Is Excel still the right first review surface?
- What fields need to appear in the first demo workbook header?
- Should review happen by sheet, revision set, trade, or mod?
- What sample RFIs/mod packages can be used to understand the broader workflow?

Benchmark:

- What manual process should we compare against?
- Which revision package should be the first real benchmark?
- What does "useful enough for the next demo" mean in Kevin's terms?

## Recommended Next Step

Run one focused demo cycle:

1. Use the current local pipeline to produce a better Rev 1 / Rev 2 workbook.
2. Compare it against the manual review process.
3. Count missed clouds, false positives, unclear rows, and time saved.
4. Use Kevin's feedback to decide the next tuning target.
