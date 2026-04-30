# ScopeLedger Roadmap

ScopeLedger turns drawing revision packages into a reviewable Excel workbook
with the latest drawing context, clouded-change evidence, and clear review
flags for pricing and build coordination.

## Goal

The near-term goal is a demo-grade workbook that Kevin can compare against the
current manual workflow.

The product does not need to replace professional judgment. It needs to reduce
the time spent hunting through PDFs, collecting crop evidence, and organizing
changes into a usable workbook.

## Where We Are Now

Working today:

- The system finds real revision-cloud areas on blueprint sheets accurately.
- It crops clouded change areas so reviewers can see the evidence.
- Human review feedback has already improved the cloud results.
- The app can produce an Excel workbook with embedded crop images.
- The app can produce a browser review packet that shows each crop with source
  drawing context.
- The app supports project/package import, project processing, review queue
  decisions, and export.
- The security approach is local-first unless ESA approves any external API
  use.

Latest verified checkpoint:

- `217` cloud crop rows exported into the real workbook path.
- `217` embedded workbook crop images verified.
- `80` human split-review corrections included.
- `10` still-overmerged cloud results intentionally excluded instead of
  polluting the workbook.
- The workbook/review packet is available through the currently served app.

Important limitation:

- The crop evidence workflow is much stronger than the scope-writing workflow.
  The first text-reading pass exists, but many rows still need a reviewer to
  rewrite or confirm the scope wording.

## What Still Needs Work

The main remaining work is not finding a place to put the data. The workbook
and review flow exist. The remaining work is making each row more useful before
a human touches it.

Needs work:

- better wording for `Scope Included`
- detail references when a cloud points to another detail
- legend, keynote, symbol, and callout interpretation
- better handling of clouds that only point somewhere else
- reducing missed clouds, false positives, and merged-together clouds to near-zero
- deciding how RFIs and modification documents fit into the workflow in the future
- production-ready security controls before any live external AI (Chat GPT) use

## Roadmap

### 1. ESA Security And Privacy Review

Purpose:

- Agree on the rules before any live sensitive project data uses an external
  API.

What needs to be decided:

- whether any external API fallback is allowed at all
- whether ESA requires Zero Data Retention, Modified Abuse Monitoring, or other
  vendor controls
- who owns final approval of the policy
- what data categories are always prohibited from external use

Current position:

- Local review, local workbook generation, and local exports can continue.
- Live project data does not go to external AI unless ESA approves it.
- RFIs, Government letters, modification documents, and shared-file documents
  stay local unless separately approved.

### 2. Cloud Detection Reliability

Purpose:

- Make the cloud detection trusted enough that reviewers are mostly checking
  real drawing changes, not sorting through noise.

What this means in plain English:

- catch the important clouded changes
- avoid random false positives
- avoid combining separate clouds into one confusing crop
- keep crop images legible enough for workbook review
- keep human review as the final source of truth

Success looks like:

- crop evidence is clear in Excel
- obvious bad detections are filtered out
- review time goes down because the queue is cleaner
- missed major clouded changes are rare enough to benchmark seriously

### 3. Demo-Grade Workbook

Purpose:

- Produce a workbook that proves the end-to-end workflow.

What the workbook should show:

- latest drawing context
- cloud crop evidence
- accepted/rejected/pending review status
- rows that are useful enough to inspect, edit, and compare against manual
  work
- uncertainty flags instead of silent guesses

Success looks like:

- Kevin can compare the tool-assisted workbook against his manual process.
- We can count missed clouds, false positives, unclear rows, and time saved.
- The workbook is mostly review/edit work, not rebuild-from-scratch work.

### 4. Scope Text, Details, Legends, And Symbols

Purpose:

- Make the workbook text more useful, not just the crop evidence.

Current state:

- A first text-reading pass is wired.
- It can find nearby PDF text or locally read image text, but it is noisy.
- Many rows still need reviewer rewrite - the next implementation (current week) will reduce this substantially.

Next work:

- read text inside and around cloud crops more accurately
- identify when a cloud points to a detail elsewhere
- capture detail references when visible
- separate real scope from sheet titles, index text, revision block text, and
  labels
- flag weak rows clearly instead of pretending they are final
- avoid guessing contractor, cost, or scope when the evidence is unclear

Success looks like:

- more rows start with useful `Scope Included` text
- leader/callout-only clouds preserve location and point reviewers to the
  right detail
- reviewers spend more time confirming and less time rewriting

### 5. Kevin Workflow And Mod/RFI Integration

Purpose:

- Connect the drawing-change workbook to the broader modification workflow
  without overbuilding before the core demo is validated.

What we need to understand:

- how revision sets map to higher-level mods
- how Government letters, RFIs, shared files, and mod trackers define the
  official scope
- whether no-drawing-change RFIs belong in the same workbook or a separate
  file
- how prior comments or notes from superseded sheets should carry forward
- whether review should happen by sheet, revision set, trade, or mod package

Needed from ESA/Kevin:

- representative RFI PDFs
- Government letters or mod packages
- shared-file/mod tracker examples
- manual process timing for a benchmark
- feedback on the first real workbook fields and review order

### 6. Production Hardening

Purpose:

- Make the workflow repeatable, inspectable, and safe enough for real project
  use after security approval.

Work needed:

- clear operator steps for import, scan, review, and export
- stable output-file locations and backup expectations
- strong local audit trail
- performance checks on large packages
- security gates that prevent accidental external disclosure
- clear local-only and ESA-approved-live operating modes

Success looks like:

- another operator can run the workflow without special knowledge
- outputs are reproducible enough for project records
- security controls match ESA requirements
- generated workbooks and review packets can be shared confidently through the
  approved handoff path

## Near-Term Actions

1. Review the security/privacy policy with ESA.
2. Use the current app and workbook to gather Kevin's feedback.
3. Improve scope text, detail references, legend/keynote interpretation, and
   review reasons.
4. Generate the next demo workbook.
5. Compare the tool-assisted workbook against Kevin's manual process.
6. Collect RFI/mod examples for the broader workflow.
7. Decide the next review checkpoint.

## Open Decisions

- Is any external API use allowed for live ESA data?
- If yes, what vendor controls are required?
- What exact workbook header fields should appear after Kevin sees the first
  real example?
- Should the review order be by sheet, revision set, trade, or mod?
- Should no-drawing-change RFIs appear in the same workbook or a separate
  file?
- What benchmark package should define whether the tool is saving enough time?

## Simple Talk Track

ScopeLedger already proves the crop-evidence workflow: find clouded changes,
show the evidence, review the queue, and export a workbook.

The next product leap is better row quality: clearer scope text, better detail
references, and fewer rows that require rewrite.

The security gate stays in front of any live external AI use.
