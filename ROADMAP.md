# KEVISION Roadmap

Status: current planning roadmap. Product rules live in
`PRODUCT_AND_DELIVERABLE.md`; architecture and workflow live in `KEVISION.md`;
CloudHammer details live in `CLOUDHAMMER.md`; security policy lives in
`SECURITY_PRIVACY_POLICY.md`.

## North Star

KEVISION should turn blueprint revision packages into a legible Excel
deliverable that captures all relevant clouded changes, latest-sheet context,
review flags, and crop evidence clearly enough for Kevin's team to use in
pricing and build coordination.

Near-term success is a demo-grade end-to-end deliverable that Kevin can inspect
against his current manual workflow. Production success requires stronger
CloudHammer reliability, scope extraction, workflow integration, and ESA
security approval before live sensitive project use.

## Current Baseline

Working:

- CloudHammer can generate whole-cloud candidate manifests from real revision
  sets.
- Reviewed candidate feedback and split-review feedback exist.
- Candidate release manifests can route accepted, auto-deliverable,
  split-risk, review, and quarantined candidates.
- Tightened crop artifacts can be generated for deliverable experiments.
- The real backend scanner can consume a CloudHammer manifest.
- The real backend exporter can produce a workbook with embedded CloudHammer
  crop images.

Latest verified integration checkpoint:

- input: split-review-corrected low-fill tuned CloudHammer release manifest
- output workspace:
  `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246`
- corrected manifest rows: `217`
- approved CloudHammer change items: `217`
- embedded workbook crop images: `217`
- human split-review replacements included: `80`
- Google Drive review handoff folder:
  `https://drive.google.com/drive/folders/1_6LogBKmxt38bF9dGBPyc1l_z38z1MaT`

Known gaps:

- scope text is still placeholder text
- OCR/detail extraction is not wired into CloudHammer-backed rows
- overmerge and false-positive reduction still need more iteration
- RFI/modification workflow is discovery only
- live sensitive project API use is blocked pending ESA policy approval

## Milestone 0: ESA Security And Privacy Review

Goal:

- establish the policy gate before any live sensitive project data uses an
  external API.

Exit criteria:

- `SECURITY_PRIVACY_POLICY.md` reviewed with ESA
- ESA decision recorded for whether OpenAI API fallback is allowed
- if allowed, approved scope is limited to sanitized low-confidence cloud-shape
  confirmation unless ESA approves more
- implementation requirements are clear for sanitizer, dry-run report,
  configuration gate, and audit log

Non-goals:

- no live RFI/modification document API use under this milestone
- no external OCR/scope extraction approval assumed
- no production API fallback until the gate is implemented

## Milestone 1: CloudHammer Reliability Foundation

Goal:

- make CloudHammer reliable enough that candidate release manifests are
  high-trust inputs to the backend deliverable pipeline.

Key work:

- freeze repeatable eval sets across revision sets, not just the sets used for
  training labels
- continue reviewing high-impact candidate queues and split-risk queues
- reduce overmerges, false positives, and missed large-cloud fragments
- refine crop tightening so deliverable images are legible without excessive
  page context
- keep API prelabels and any future API fallback advisory only, never training
  truth without human review
- define confidence/policy gates for release manifests

Exit criteria:

- held-out revision-set eval reports recall and false-positive rate
- split-risk policy is reliable enough to avoid obvious bad merges
- release manifest generation is reproducible from documented commands
- accepted candidate crops are visually reviewable in Excel

## Milestone 2: Demo-Grade End-To-End Deliverable

Goal:

- produce a Kevin-visible workbook that proves the core workflow end to end.

Key work:

- run the Rev 1 / Rev 2 benchmark from `PRODUCT_AND_DELIVERABLE.md`
- generate an Excel workbook close enough to `docs/anchors/mod_5_changelog.xlsx`
  for Kevin to inspect
- preserve all cloud crop evidence and latest-sheet context
- flag uncertain rows instead of silently dropping them
- separate meaningful review candidates from random false positives

Exit criteria:

- workbook includes the CloudHammer crop rows expected from the release
  manifest
- latest and superseded sheets are identified accurately enough for review
- missed-cloud, false-positive, and unclear-row counts are recorded
- Kevin can compare the tool-assisted output against the manual workflow
- roadmap is updated with Kevin's demo feedback

## Milestone 3: Scope, OCR, And Detail Extraction

Goal:

- replace placeholder CloudHammer scope text with reviewable scope information.

Key work:

- read text inside and near accepted cloud regions
- identify detail references, leader-only clouds, and detail-callout clouds
- handle multiple drawings/details on one sheet
- preserve uncertainty with `Needs Review` and `Review Reason` fields
- avoid guessing contractor, cost, or scope when the evidence is unclear

Exit criteria:

- CloudHammer-backed rows contain useful `Scope Included` text or an explicit
  review reason
- detail references are populated when visible or inferable
- leader-only/detail-callout cases produce location-preserving rows
- review burden shifts from rewriting rows to confirming rows

## Milestone 4: Kevin Workflow Integration

Goal:

- connect the drawing-change workbook to the broader modification workflow
  without overbuilding before the demo is validated.

Key work:

- collect representative RFI PDFs, Government letters, shared-file examples,
  and modification trackers
- define how revision sets map to higher-level mods
- decide how carry-forward notes from superseded sheets should be surfaced
- decide where no-drawing-change RFIs belong
- implement duplicate standalone/package sheet behavior: keep both candidate
  sources visible when they differ or might differ, and let the reviewer compare
  them

Exit criteria:

- mod/RFI source-of-truth documents are cataloged
- minimum data model for mod grouping is documented
- no-change RFI handling is explicitly in or out of the workbook
- Kevin's preferred review order is known

## Milestone 5: Production Hardening

Goal:

- make the workflow repeatable, inspectable, and safe enough for real project
  use after security approval.

Key work:

- stable commands for scan, CloudHammer inference, release manifest creation,
  review, and export
- clear artifact locations and backup policy for large local files
- reviewer ergonomics for high-volume candidate review
- performance checks on large packages
- explicit audit trail for external API fallback if ESA approves it
- deployment notes for local-only and approved-live modes

Exit criteria:

- a clean operator can run the documented workflow
- large generated artifacts remain local and ignored
- security gates prevent accidental external disclosure
- outputs are reproducible enough for project records

## Near-Term Next Actions

1. Review `SECURITY_PRIVACY_POLICY.md` with ESA before any live-data API use.
2. Continue CloudHammer candidate/split feedback loops on the strongest queues.
3. Generate the next release manifest after split/crop tuning.
4. Run the real backend scan/export using that manifest.
5. Put any generated review workbook in Google Drive `/kevin_usage/` for
   Google Sheets review.
6. Compare the resulting workbook against the Rev 1 / Rev 2 benchmark criteria.
7. Start collecting RFI/mod examples for discovery, without external API use.

## Open Decisions

- ESA: whether any external API use is allowed for live data.
- ESA: whether Zero Data Retention or Modified Abuse Monitoring is required.
- Kevin: exact workbook header fields after he sees a first real example.
- Kevin: preferred review order by sheet, trade, revision set, or mod.
- Kevin/ESA: whether no-drawing-change RFIs belong in the same workbook or a
  separate artifact.
