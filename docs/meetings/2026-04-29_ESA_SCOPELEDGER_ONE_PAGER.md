# ScopeLedger Meeting One-Pager - 2026-04-29

Turn drawing revisions into accountable scope records.

## Plain-English Pitch

ScopeLedger reduces the time and risk involved in reviewing construction revision
packages.

The current MVP finds suspected revision clouds on drawing sheets, crops the
evidence, places the crops into a review workbook, and provides a simple web
review surface for accepting, rejecting, and exporting changes.

It is not replacing professional judgment. It is reducing the manual hunting
through PDFs so the project team can focus review time on the actual changed
scope.

## What Works Today

- Finds many real revision-cloud areas on blueprint sheets.
- Groups detected cloud fragments into whole-cloud crop candidates.
- Applies human split-review feedback to reduce overmerged results.
- Exports crop evidence into the real workbook deliverable path.
- Provides a dark-mode local review portal for reviewing changes and exporting
  the workbook.
- Generates a browser review packet showing each workbook crop beside source
  drawing context.
- Keeps generated project artifacts local by default.

Latest proof point:

- `217` corrected CloudHammer crop rows exported through the real backend:
  `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog.xlsx`
- `217` embedded crop images verified in the workbook.
- first workbook tab is now a summary cover sheet with package counts and
  review guidance.
- `80` human split-review replacements included.
- `10` still-overmerged candidates intentionally excluded from this release.

## What Does Not Work Yet

- It does not reliably read or summarize the scope text inside every cloud.
- It does not yet parse legends, keynotes, detail references, or symbol meaning
  into final polished workbook descriptions.
- It does not yet fully handle RFIs or modification package workflow.
- It still needs tuning for false positives, overmerged clouds, and missed
  clouds.

## Why It Matters

Manual revision review is slow and risky because someone has to:

- identify the latest drawing versions
- find every clouded change
- decide which changes matter for pricing/build coordination
- collect crop evidence
- organize the results into a usable workbook

ScopeLedger's first business value is reducing the search-and-crop burden while
keeping a human in control.

## Demo Artifacts

Open before the meeting:

- Local web app: `http://127.0.0.1:5000/`
- Review workbook:
  `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog.xlsx`
- Visual review packet:
  `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog_review_packet.html`
- Security policy: `SECURITY_PRIVACY_POLICY.md`
- Roadmap: `ROADMAP.md`

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

## What We Need From ESA / Project Stakeholders

Security:

- Who should review/approve the security policy?
- Is sanitized external API fallback allowed at all for live project data?
- Are Zero Data Retention or other vendor controls required?

Product:

- Is the Excel/Google Sheets workbook still the right first review surface?
- What fields need to appear in the first demo workbook header?
- Should review happen by sheet, revision set, trade, or modification package?
- What sample RFIs/mod packages can be used to understand the broader workflow?

Benchmark:

- What manual process should we compare against?
- Which revision package should be the first real benchmark?
- What would make the next demo useful enough to compare against manual review?

## Recommended Next Step

Run one focused demo cycle:

1. Use the current local pipeline to produce a better Rev 1 / Rev 2 workbook.
2. Compare it against the manual review process.
3. Count missed clouds, false positives, unclear rows, and time saved.
4. Use stakeholder feedback to decide the next tuning target.
