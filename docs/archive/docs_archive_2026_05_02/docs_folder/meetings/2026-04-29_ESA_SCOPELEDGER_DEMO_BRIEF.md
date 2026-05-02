# ESA / ScopeLedger Demo Brief - 2026-04-29

Status: historical ESA demo prep snapshot. Current sequencing lives in
`../../ROADMAP.md`; current security policy lives in
`../SECURITY_PRIVACY_POLICY.md`; current CloudHammer state lives in
`../../CLOUDHAMMER.md`.

Turn drawing revisions into accountable scope records.

Purpose: show the current MVP in business terms, prove that cloud detection now
flows into the real review workbook, align on security/privacy policy before
live data, and leave with clear next decisions.

Meeting environment note for 2026-04-30:

- We are accessing the already-running ScopeLedger app remotely from the home
  machine. Treat that served app as the meeting source of truth.
- The verified `217`-row CloudHammer workbook/review-packet run is available
  to the served app. Direct `runs/...` paths below are host-machine paths.
- Scope text extraction is no longer completely unwired. A first PDF
  text-layer/OCR pass has been backfilled, but it is still review-assist
  quality: most rows still need reviewer rewrite or interpretation.
- The web app is now project/workspace based and is already being served for
  the meeting.

## Audience And Tone

Assume the audience cares about construction workflow, risk, and speed, not
model internals.

Use business/process language:

- "find the clouded drawing changes"
- "crop the evidence into the workbook"
- "reduce missed scope"
- "reduce manual searching"
- "make review faster"
- "keep sensitive project data local"

Avoid leading with technical language:

- model architecture
- YOLO
- manifests
- inference
- confidence policy internals
- backend/exporter wiring

Translate technical status into business status:

- Current MVP: finds suspected revision-cloud areas and puts crop evidence into
  a workbook for review.
- New demo surface: a dark-mode local project review portal for importing
  packages, populating a workspace, inspecting changes, and exporting the
  workbook/review packet.
- Not done yet: reliable scope understanding, symbols/legends/keynotes/detail
  references, RFI/mod workflow, and final polished pricing rows.
- Security posture: local-first, no live external API use unless ESA approves
  it.

## Meeting Goals

1. Show that this is no longer just a model experiment: detections now flow
   through the real scan/export path and produce a workbook with embedded crop
   evidence.
2. Set expectations honestly: cloud/crop detection is promising; scope text,
   OCR/detail extraction, RFI handling, and production hardening are first-pass
   or incomplete, not solved.
3. Get ESA aligned on the security/privacy policy before any live sensitive
   project data uses an external API.
4. Confirm the next milestone: a demo-grade Rev 1 / Rev 2 deliverable and a
   benchmark against manual workflow.

## Files To Have Open

Open these before the meeting:

- Web review portal: the active remote app URL served from the home machine
- Security policy: `SECURITY_PRIVACY_POLICY.md`
- Roadmap: `ROADMAP.md`
- Product rules: `PRODUCT_AND_DELIVERABLE.md`
- Web app walkthrough:
  `docs/SCOPELEDGER_WEB_APP_WALKTHROUGH.html`
- Review workbook, available through the app Export page and on the serving
  host:
  `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog.xlsx`
- Visual review packet, available through the app Export page and on the
  serving host:
  `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog_review_packet.html`
- Google Drive handoff folder:
  `https://drive.google.com/drive/folders/1_6LogBKmxt38bF9dGBPyc1l_z38z1MaT`
- Anchor workbook: `docs/anchors/mod_5_changelog.xlsx`

Do not lead with:

- the enormous `conformed_preview.pdf`
- training folders, manifests, or command-line details

## 90-Second Opening

Suggested opening:

> The goal is to reduce the time and risk involved in finding changed scope in
> revision packages. The current MVP finds suspected revision-cloud areas,
> crops those areas, and puts the evidence into a workbook for review.
>
> This is still an MVP. A first scope-text pass exists, but most extracted text
> still needs human review before it can become a pricing log. What it proves
> is that we can get the clouded drawing evidence into a review workflow
> quickly and consistently.
>
> Before using live sensitive project data with any external AI fallback, we
> want ESA to review the security policy. The default approach is local-first.

## Demo Flow

### 1. Product Portal First

Open:

The active remote app URL served from the home machine.

Show:

- dark-mode project review dashboard
- project/package import and Populate Workspace controls
- populate status/progress
- accepted changes count
- current sheets count
- review/export actions
- "Review Changes" page
- "Export Workbook" page
- Google Drive folder link

Say:

- This is the direction for a non-technical project review workflow.
- The UI is intentionally about drawings, changes, review, and workbook export.
- The model details stay behind the scenes.

### 2. Real Workbook Proof

Open:

Open from the app Export page, or from the serving host path:

`runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog.xlsx`

Show:

- summary cover sheet with package counts and review guidance
- embedded crop images in the workbook
- crop evidence rows generated by the real export path
- first-pass scope text/review reasons, with many rows still requiring rewrite
- clean workbook formatting for review

Say:

- The latest verified integration checkpoint exported `217` crop rows into the
  real workbook.
- `217` embedded crop images were verified in the workbook.
- The workbook opens on a summary tab: `6` revision sets, `70` current sheets,
  `217` accepted changes, and `13` items still needing review.
- `80` rows came from human split-review replacements.
- `10` still-overmerged parents were intentionally excluded instead of
  polluting the deliverable.
- Scope extraction has a first pass, but it is not final: the active demo
  distribution was `12` text-layer-near-cloud rows, `150` needs-reviewer-
  rewrite rows, `35` index/title-noise rows, and `20` leader/callout-only
  rows. Extraction methods were `196` PDF text-layer and `21` local Tesseract
  OCR fallback.
- The workbook is still a review artifact, not a final estimator deliverable.

Translate if needed:

- "The important thing to judge today is the crop evidence and workflow, not
  the scope wording yet."
- "Today this is a review accelerator, not an automatic estimator."
- "The current job is to stop people from manually hunting through PDFs for
  every cloud."

### 3. Visual Review Packet

Open:

Open from the app Export page, or from the serving host path:

`runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog_review_packet.html`

Show:

- each exported crop beside a marked source drawing context crop
- quick scrolling review
- less need to flip between PDF and workbook

Say:

- This is an inspection helper for the meeting and for internal QA.
- The workbook remains the formal deliverable; this view helps evaluate whether
  the crop evidence is useful.

### 4. Security First

Open `SECURITY_PRIVACY_POLICY.md`.

Say:

- ScopeLedger is local-first by default.
- Source PDFs, text layers, metadata, RFIs, workbooks, filenames, and full
  drawing pages stay local.
- External API use is not core product behavior.
- The only contemplated API use is optional fallback confirmation for
  low-confidence cloud shapes.
- Live ESA project data will not use that path unless ESA approves it.
- RFIs/modification documents are treated as higher sensitivity and are not
  covered by the cloud-shape fallback approval.

Ask:

- Does ESA allow any external API fallback on live project data?
- If yes, does ESA require Zero Data Retention, Modified Abuse Monitoring,
  contract review, or other controls?
- Who at ESA should own final approval of this policy?

### 5. Roadmap

Open `ROADMAP.md`.

Show the sequence:

1. ESA security/privacy review.
2. CloudHammer reliability foundation.
3. Demo-grade end-to-end deliverable.
4. Scope/OCR/detail extraction.
5. Workflow integration: RFIs, mods, carry-forward notes.
6. Production hardening.

Say:

- The next practical product milestone is not "build every possible feature."
- The next milestone is a demo-grade workbook that can be compared against the
  manual process.

### 6. Anchor / Target Workbook

Open:

`docs/anchors/mod_5_changelog.xlsx`

Show:

- target workbook shape
- crop evidence column
- scope column
- downstream pricing fields

Say:

- This anchor is the shape we are aiming toward.
- The current generated workbook proves the crop/evidence pipeline.
- Next work is improving scope extraction so reviewers edit/confirm more rows
  instead of rewriting them.

## What To Emphasize

Strong claims we can make:

- The system is detecting real revision-cloud shapes from blueprint pages.
- We now have an end-to-end path into the real review workbook workflow.
- The latest verified workbook contains `217` embedded crop images.
- Human split-review feedback is already improving the export.
- Future generated run artifacts should stay local or in the approved Drive
  handoff path; do not overstate that every historical CloudHammer artifact is
  absent from GitHub.
- The security policy blocks live external API use until ESA approves it.

Claims to avoid:

- "This is production-ready."
- "The tool understands scope now."
- "RFIs are automated."
- "OpenAI will receive live project data."
- "External API use is risk-free."
- "False positives/misses are solved."

## Current Technical Status

Working:

- whole-cloud candidate generation
- human candidate review and split-risk review loops
- release manifest routing
- crop tightening
- real backend manifest integration
- real workbook export with embedded crop images
- dark-mode review portal
- visual review packet
- first-pass PDF text-layer/OCR enrichment for CloudHammer rows
- project import/append flow and Populate Workspace status
- Google Drive handoff link in the export surface

Not done:

- reliable scope text extraction beyond the first pass
- detail-reference understanding for all cases
- legend/keynote/symbol parsing
- final false-positive/overmerge reduction
- production security gates for external API fallback
- RFI/modification workflow automation
- final benchmark against manual workflow

## Questions For ESA / Project Stakeholders

Security / API:

- Is external API use allowed at all for live ESA project data?
- If allowed, is sanitized low-confidence cloud-shape confirmation acceptable?
- Is Zero Data Retention or Modified Abuse Monitoring required?
- Who approves vendor/security language?
- Are there project categories where external API use is always prohibited?

Workflow / deliverable:

- Is the Excel/Google Sheets workbook still the right first review surface?
- What exact header fields should appear on the first demo deliverable?
- Should review happen by sheet, revision set, trade, or mod?
- Should no-drawing-change RFIs live in the same workbook or a separate
  artifact?

Data needed:

- representative RFIs
- Government letters or mod packages
- shared-file/mod tracker examples
- a non-sensitive or approved sample package for future testing
- expected manual process timing for a Rev 1 / Rev 2 benchmark

## If The Demo Goes Sideways

If Excel fails to open or the workbook looks rough:

1. Do not defend the rough parts.
2. Say: "This artifact is proof of pipeline integration, not final row
   quality."
3. Open the web review portal or review packet and show the crop evidence.
4. Open `ROADMAP.md` and point to Milestone 2 and Milestone 3.
5. Use the anchor workbook to show the intended target.

If security questions dominate:

1. Open `SECURITY_PRIVACY_POLICY.md`.
2. Say the default is local-only.
3. Say no live data goes to external APIs without ESA approval.
4. Offer to treat OpenAI fallback as disabled unless/until ESA signs off.

## Suggested Close

Say:

> The immediate next step is not to trust automation blindly. The next step is
> to use this working pipeline to produce a better demo workbook, measure it
> against the manual workflow, and keep the security gate in front of any live
> external API use.

Ask for agreement on:

- ESA security/privacy review owner
- whether sanitized external API fallback remains allowed as a future option
- sample documents ESA can provide
- benchmark scope and timing
- the next demo checkpoint

## Follow-Up Actions To Capture

After the meeting, record:

- ESA API/security decision
- required vendor/privacy controls
- approved/prohibited data categories
- workbook feedback
- preferred review flow
- whether duplicate standalone/package sheet rows are too noisy in practice
- sample documents promised
- benchmark target package
- next checkpoint date
