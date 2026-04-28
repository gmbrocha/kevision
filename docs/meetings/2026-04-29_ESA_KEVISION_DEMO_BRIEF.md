# ESA / Kevin Demo Brief - 2026-04-29

Purpose: walk Kevin/ESA through where KEVISION is today, show the real
CloudHammer-to-workbook proof point, align on security/privacy policy before
live data, and leave with clear next decisions.

## Audience And Tone

Kevin is a construction business user, not a technical reviewer.

Use business/process language:

- "find the clouded drawing changes"
- "crop the evidence into Excel"
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
  an Excel workbook for review.
- Not done yet: reading the actual scope text and producing final polished
  pricing rows.
- Security posture: local-first, no live external API use unless ESA approves
  it.

## Meeting Goals

1. Show that this is no longer just an experiment: CloudHammer detections now
   flow into the real backend scanner/exporter and produce an Excel workbook.
2. Set expectations honestly: cloud/crop detection is promising; scope text,
   OCR/detail extraction, RFI handling, and production hardening are not done.
3. Get ESA aligned on the security/privacy policy before any live sensitive
   project data uses an external API.
4. Confirm the next milestone: demo-grade Rev 1 / Rev 2 deliverable and
   benchmark against manual workflow.

## Files To Have Open

Open these before the meeting:

- `SECURITY_PRIVACY_POLICY.md`
- `ROADMAP.md`
- `PRODUCT_AND_DELIVERABLE.md`
- `CLOUDHAMMER.md`
- `runs/cloudhammer_real_export_v3/outputs/revision_changelog.xlsx`
- `docs/anchors/mod_5_changelog.xlsx`

Do not lead with:

- `runs/cloudhammer_real_export_v3/outputs/conformed_preview.pdf`

That PDF exists, but it is very large and not the best first demo artifact.
Use the Excel workbook first.

## 90-Second Opening

Suggested opening:

> The goal is to reduce the time and risk involved in finding changed scope in
> revision packages. The current MVP finds suspected revision-cloud areas,
> crops those areas, and puts the evidence into an Excel workbook for review.
>
> This is still bare bones. It does not yet read the scope for you or produce a
> final polished pricing log. What it proves is that we can get the clouded
> drawing evidence into the workflow Kevin already uses: Excel.
>
> Before using live sensitive project data with any external AI fallback, we
> want ESA to review the security policy. The default approach is local-first.

## Demo Flow

### 1. Security First

Open `SECURITY_PRIVACY_POLICY.md`.

Say:

- KEVISION is local-first by default.
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

### 2. Roadmap

Open `ROADMAP.md`.

Show the sequence:

1. ESA security/privacy review.
2. CloudHammer reliability foundation.
3. Demo-grade end-to-end deliverable.
4. Scope/OCR/detail extraction.
5. Kevin workflow integration: RFIs, mods, carry-forward notes.
6. Production hardening.

Say:

- The next practical product milestone is not "build every possible feature."
- The next milestone is a demo-grade Excel deliverable Kevin can compare
  against his manual process.

### 3. Real Pipeline Proof

Open:

`runs/cloudhammer_real_export_v3/outputs/revision_changelog.xlsx`

Show:

- embedded crop images in the workbook
- many rows coming from CloudHammer whole-cloud candidates
- current placeholder scope text
- the fact that the rows are in the real deliverable format, not a separate
  model sandbox

Say:

- The latest run exported `137` CloudHammer crop images into the real workbook.
- Those crops came from the current CloudHammer release manifest.
- The backend scanner/exporter is the real one; this is not a fake exporter.
- The workbook is not final because scope text is not solved yet.

Translate if needed:

- "The important thing to look at is the crop evidence, not the wording in the
  scope column yet."
- "Today this is a review accelerator, not an automatic estimator."
- "The current job is to stop people from hunting through PDFs manually for
  every cloud."

### 4. Anchor / Target Workbook

Open:

`docs/anchors/mod_5_changelog.xlsx`

Show:

- current desired Excel style
- crop evidence column
- scope column
- downstream pricing fields

Say:

- This anchor is the shape we are aiming toward.
- Our current generated workbook proves the crop/evidence pipeline.
- Next work is making the generated rows useful enough that Kevin edits/reviews
  them instead of rewriting them.

### 5. Product Rules

Open `PRODUCT_AND_DELIVERABLE.md` if there is time.

Hit only these points:

- completeness plus legibility wins
- do not invent contractor/cost/scope when uncertain
- Excel is the v1 review surface
- RFIs are real but not required for the first demo deliverable
- duplicate/carry-forward rules need Kevin/ESA confirmation

## What To Emphasize

Strong claims we can make:

- CloudHammer is detecting real revision-cloud shapes from blueprint pages.
- We now have an end-to-end path into the real backend/export workflow.
- The latest verified workbook contains `137` embedded CloudHammer crop images.
- Generated run artifacts are local and ignored, not pushed to GitHub.
- The security policy blocks live external API use until ESA approves it.
- Kevin already understands this is a bare-bones MVP focused on crop evidence.

Claims to avoid:

- "This is production-ready."
- "The tool understands scope now."
- "RFIs are automated."
- "OpenAI will receive live project data."
- "External API use is risk-free."
- "False positives/misses are solved."

## Current Technical Status

Working:

- CloudHammer whole-cloud candidate generation
- human candidate review and split-risk review loops
- release manifest routing
- crop tightening
- real backend manifest integration
- real Excel export with embedded crop images

Not done:

- reliable scope text extraction
- detail-reference understanding for all cases
- final false-positive/overmerge reduction
- production security gates for external API fallback
- RFI/modification workflow automation
- final benchmark against Kevin's manual workflow

## Questions For ESA / Kevin

Security / API:

- Is external API use allowed at all for live ESA project data?
- If allowed, is sanitized low-confidence cloud-shape confirmation acceptable?
- Is Zero Data Retention or Modified Abuse Monitoring required?
- Who approves vendor/security language?
- Are there project categories where external API use is always prohibited?

Workflow / deliverable:

- Is the Excel workbook still the right first review surface?
- What exact header fields should appear on the first demo deliverable?
- Should review happen by sheet, revision set, trade, or mod?
- Should no-drawing-change RFIs live in the same workbook or a separate
  artifact?

Data needed:

- representative RFIs
- Government letters or mod packages
- shared-file/mod tracker examples
- a non-sensitive or approved sample package for future testing
- Kevin's expected manual process timing for Rev 1 / Rev 2 benchmark

## If The Demo Goes Sideways

If Excel fails to open or the workbook looks rough:

1. Do not defend the rough parts.
2. Say: "This artifact is proof of pipeline integration, not final row
   quality."
3. Open `ROADMAP.md` and point to Milestone 2 and Milestone 3.
4. Use the anchor workbook to show the intended target.
5. Recenter on the concrete achievement: the model output now reaches the real
   backend/export path.

If security questions dominate:

1. Open `SECURITY_PRIVACY_POLICY.md`.
2. Say the default is local-only.
3. Say no live data goes to external APIs without ESA approval.
4. Offer to treat OpenAI fallback as disabled unless/until ESA signs off.

## Suggested Close

Say:

> The immediate next step is not to ask you to trust automation blindly. The
> next step is to use this working pipeline to produce a better demo workbook,
> measure it against the manual workflow, and keep the security gate in front
> of any live external API use.

Ask for agreement on:

- ESA security/privacy review owner
- whether sanitized external API fallback remains allowed as a future option
- sample documents Kevin/ESA can provide
- benchmark scope and timing
- the next demo checkpoint

## Follow-Up Actions To Capture

After the meeting, record:

- ESA API/security decision
- required vendor/privacy controls
- approved/prohibited data categories
- Kevin's workbook feedback
- Kevin's preferred review flow
- whether duplicate standalone/package sheet rows are too noisy in practice
- sample documents promised
- benchmark target package
- next checkpoint date
