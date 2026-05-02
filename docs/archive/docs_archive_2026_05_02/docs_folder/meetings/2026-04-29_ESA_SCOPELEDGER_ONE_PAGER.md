# ScopeLedger Meeting One-Pager - 2026-04-29

Status: historical ESA/Kevin meeting prep snapshot. Current sequencing lives in
`../../ROADMAP.md`; current security policy lives in
`../SECURITY_PRIVACY_POLICY.md`; current CloudHammer state lives in
`../../CLOUDHAMMER.md`.

Turn drawing revisions into accountable scope records.

## Overview

ScopeLedger reduces the time and risk involved in reviewing construction revision
packages.

The current MVP finds suspected revision clouds on drawing sheets, crops the
evidence, places the crops into a review workbook, and provides a simple web
review surface for importing packages, populating a workspace, accepting,
rejecting, and exporting changes.

It is not replacing any professional judgment. It is reducing the manual hunting
through PDFs so the project team can focus review time on the actual changed
scope.

## What Works Today

- Finds many real revision-cloud areas on blueprint sheets.
- Groups detected cloud fragments into whole-cloud crop candidates.
- Applies human split-review feedback to reduce overmerged results.
- Exports crop evidence into the real workbook deliverable path.
- Provides a local review portal for reviewing changes and exporting
  the workbook.
- Generates a browser review packet showing each workbook crop beside source
  drawing context.
- Provides project/package import, Populate Workspace status, review/export
  controls, and a Google Drive handoff link. (google drive folder is only for testing, will be removed for production)
- Keeps live project workflow local by default unless ESA approves otherwise. If approved, the backend & review workflow will
  have a "safe" export to OpenAI GPT model for follow up verifications on difficult-to-analyze revisions (and all identifiable data
  is removed prior to this data exchange)
- Has a first PDF text-layer/OCR scope-text pass, though it is still
  review-assist quality. Goal is to actually minimize review assist with high confidence.

Latest proof point:

- `217` corrected CloudHammer crop rows exported through the real backend:
  `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog.xlsx`
- `217` embedded crop images verified in the workbook.
- first workbook tab is now a summary cover sheet with package counts and
  review guidance.
- `80` human split-review replacements included.
- `10` still-overmerged candidates intentionally excluded from this release.
- first-pass scope extraction distribution on the active demo workspace:
  `12` text-layer-near-cloud, `150` needs-reviewer-rewrite, `35`
  index/title-noise, and `20` leader/callout-only; extraction methods were
  `196` PDF text-layer and `21` local Tesseract OCR fallback.

## What Does/Does Not Work Yet

1. It does not very-confidently read or summarize the scope text inside every cloud;
  the first scope pass mostly creates review reasons and rewrite starting
  points. Implementation just hasn't really been worked on for this; it's not difficult but it will require est.
  1 week to write.
2. It does not yet very-confidently parse legends, keynotes, detail references, or
  symbol meaning into final polished workbook descriptions. This is the same implementation as the point above, and both will
  be added within the next week in parallel.
3. It does not yet fully handle RFIs or modification package workflow. (This was briefly discussed between us as a future implement)
4. It still needs tuning for false positives, overmerged clouds, and missed
  cloud crops. This portion is quite stable at the moment, and the local trained AI that performs this is quite accurate. On pause
  for the next week while items #1 and #2 (full/accurate cloud details and legend/references hooks) are implemented.

## Why The App Matters

Manual revision review is slow and potentially risky because someone has to:

- identify the latest drawing versions
- find every clouded change
- decide which changes matter for pricing/build coordination
- collect crop evidence
- organize the results into a usable workbook

ScopeLedger's first business value is reducing the search-and-crop burden while
keeping a human in control.

## Demo Artifacts

- Web review portal: the active remote app URL served from the home machine
- Review workbook, available through the app Export page and on the serving
  host:
  `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog.xlsx`
- Visual review packet, available through the app Export page and on the
  serving host:
  `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog_review_packet.html`
- Web app walkthrough: `docs/SCOPELEDGER_WEB_APP_WALKTHROUGH.html`
- Security policy: `SECURITY_PRIVACY_POLICY.md`
- Roadmap: `ROADMAP.md`

## Security Position

Default position:

- source PDFs stay local
- text layers stay local
- RFIs and modification documents stay local
- workbooks stay local
- no live external API use without ESA approval
- the old web-app OpenAI verification helper is archived; no new API
  verification calls are made from the review screen

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

- Confirm Excel as the primary v1 review/handoff surface
- What fields need to appear in the first demo workbook header?
- Should review happen by sheet, revision set, trade, or modification package?
- What sample RFIs/mod packages can be used to understand the broader workflow?

Benchmark:

- What manual process should we compare against?
- Which revision package should be the first real benchmark?
- What would make the next demo useful enough to compare against manual review?

## Recommended

Focused demo cycle:

1. Use the current local pipeline to produce a better Rev 1 / Rev 2 workbook.
2. Compare it against the manual review process.
3. Count missed clouds, false positives, unclear rows, and time saved.
4. Use stakeholder feedback to decide the next tuning target.
