# ScopeLedger Roadmap

Status: current sequencing roadmap. Keep this file short. Detailed product
rules live in `PRODUCT_AND_DELIVERABLE.md`; repo workflow lives in
`SCOPELEDGER.md`; CloudHammer training/inference state lives in
`CLOUDHAMMER.md`; security policy lives in `docs/SECURITY_PRIVACY_POLICY.md`.

## Active Focus

Current focus is the **CloudHammer v2 reliability pass**. The project already
proved a rough demo-grade end-to-end workbook path, then added a first-pass
local text/OCR extraction layer. Those were real milestones, but they did not
finish the production reliability problem.

Immediate target:

- reliable single-cloud revision-area crops
- false positives driven down through reviewed hard negatives
- held-out evals that measure whether the model actually improved
- model-facing feedback converted into training/eval artifacts

Guardrail:

Review only if it creates training/eval artifacts or validates the cropper
after the detector. Do not spend time polishing pipeline/review behavior unless
the result becomes one of:

- a precise positive label
- an empty-label hard negative
- a held-out eval/failure case
- a validated cropper rule needed after model inference

Next major goal after the CloudHammer v2 reliability pass: return to
Milestone 3 part 2, meaning better itemized/detail extraction from accepted
crops, not just broad local text/OCR snippets.

## Actual Sequence

The roadmap is not strictly linear anymore. The practical history is:

1. **CloudHammer v1 / Milestone 1a:** first detector, reviewed labels,
   whole-cloud candidate export, split-review correction, and backend manifest
   integration.
2. **Milestone 2:** rough demo-grade end-to-end workbook was achieved before
   the demo. It proved the deliverable path, crop embedding, latest-sheet
   context, and review flags, but did not prove production model quality.
3. **Milestone 3a:** first-pass local PDF text-layer/OCR extraction replaced
   pure placeholder CloudHammer scope text for many rows. It is helpful review
   scaffolding, not solved scope/detail understanding.
4. **CloudHammer v2 / Milestone 1b:** current work. Improve detector/cropper
   reliability with hard negatives, held-out full-page evals, and failure
   feedback from review.
5. **Milestone 3b:** after CloudHammer v2 is reliable enough, improve
   itemized/detail extraction around accepted crops.
6. **Milestone 4:** Kevin workflow/mod/RFI integration.
7. **Milestone 5:** production hardening.

## North Star

ScopeLedger should turn blueprint revision packages into a legible Excel
deliverable that captures relevant clouded changes, latest-sheet context,
review flags, and crop evidence clearly enough for Kevin's team to use in
pricing and build coordination.

## Milestone 0: ESA Security And Privacy Review

Goal:

- establish the policy gate before any live sensitive project data uses an
  external API

Exit criteria:

- `docs/SECURITY_PRIVACY_POLICY.md` reviewed with ESA
- ESA decision recorded for whether OpenAI API fallback is allowed
- if allowed, approved scope is limited to sanitized low-confidence cloud-shape
  confirmation unless ESA approves more
- sanitizer, dry-run report, configuration gate, and audit log requirements are
  clear

Non-goals:

- no live RFI/modification document API use
- no external OCR/scope extraction approval assumed
- no production API fallback until the gate is implemented

## Milestone 1: CloudHammer Reliability Foundation

Status:

- **Partially achieved as CloudHammer v1:** produced usable reviewed
  whole-cloud candidate manifests, split-review-corrected release artifacts,
  and a real backend/export integration path.
- **Current active pass as CloudHammer v2:** false positives, held-out evals,
  partial/overmerge failures, and single-cloud crop reliability are still being
  improved before promotion.

Goal:

- make CloudHammer reliable enough that candidate release manifests are
  high-trust inputs to the backend deliverable pipeline

Key work:

- freeze repeatable eval sets across revision sets, not just training-label
  pages
- review high-impact candidate queues only when they produce training/eval
  artifacts or validate cropper behavior
- convert reviewed false positives into empty-label hard negatives
- convert accepted contaminated crops into precise positive-label review
  batches, keeping non-cloud geometry unlabeled as background
- record partial, overmerged, and missed cases as eval failures before adding
  more postprocessing
- track false-positive rate and recall against held-out revision pages
- keep API prelabels advisory only; never treat them as training truth without
  human review

Exit criteria:

- held-out revision-set eval reports recall and false-positive rate
- reviewed hard-negative buckets regress less often
- split/merge cropper behavior avoids obvious bad merges after model inference
- release manifest generation is reproducible from documented commands
- accepted candidate crops are visually reviewable in Excel

## Milestone 2: Demo-Grade End-To-End Deliverable

Status:

- **Achieved for rough demo proof.** A real backend scan/export path consumed
  a CloudHammer release manifest and produced a Kevin-visible workbook with
  CloudHammer crop rows.
- **Not production-complete.** The result was intentionally rough: scope text
  still needed cleanup, CloudHammer still had false positives/overmerge risk,
  and the benchmark needs to be rerun after the current reliability pass.

Goal:

- produce a Kevin-visible workbook that proves the core workflow end to end

Key work:

- run the Rev 1 / Rev 2 benchmark from `PRODUCT_AND_DELIVERABLE.md`
- generate a workbook close enough to `docs/anchors/mod_5_changelog.xlsx` for
  Kevin to inspect
- preserve cloud crop evidence and latest-sheet context
- flag uncertain rows instead of silently dropping them
- separate meaningful review candidates from random false positives

Exit criteria:

- workbook includes the CloudHammer crop rows expected from the release
  manifest
- latest and superseded sheets are identified accurately enough for review
- missed-cloud, false-positive, and unclear-row counts are recorded
- Kevin can compare tool-assisted output against his manual workflow

## Milestone 3: Scope, OCR, And Detail Extraction

Status:

- **Part 3a completed:** first-pass local PDF text-layer/OCR extraction now
  runs through scan/populate/export and replaces many pure placeholder rows
  with explicit reviewer-facing extraction results.
- **Part 3b not complete:** itemized/detail extraction is still not solved.
  Detail references, leader-only clouds, callouts, symbols, legends, and
  multiple-detail sheets remain future work.

Goal:

- replace placeholder CloudHammer scope text with reviewable itemized/detail
  information

Current sequencing:

- deeper scope/detail extraction is deferred until CloudHammer v2 produces
  reliable accepted cloud crops
- first-pass PDF text-layer/OCR extraction exists, but it is not solved scope
  understanding
- the next major product goal is reliable itemized/detail extraction from
  accepted crops, not more pipeline work before detector/cropper trust

Key work:

- read text inside and near accepted cloud regions
- identify detail references, leader-only clouds, and detail-callout clouds
- handle multiple drawings/details on one sheet
- preserve uncertainty with `Needs Review` and `Review Reason`
- avoid guessing contractor, cost, or scope when evidence is unclear

Exit criteria:

- CloudHammer-backed rows contain useful `Scope Included` text or an explicit
  review reason
- detail references are populated when visible or inferable
- leader-only/detail-callout cases produce location-preserving rows
- review burden shifts from rewriting rows to confirming rows

## Milestone 4: Kevin Workflow Integration

Goal:

- connect drawing-change output to the broader modification workflow after the
  detector/cropper and demo workbook are credible

Key work:

- collect representative RFI PDFs, Government letters, shared-file examples,
  and modification trackers
- define how revision sets map to higher-level mods
- decide how carry-forward notes from superseded sheets should surface
- decide where no-drawing-change RFIs belong
- preserve duplicate standalone/package sheet sources when they differ or may
  differ

Exit criteria:

- mod/RFI source-of-truth documents are cataloged
- minimum data model for mod grouping is documented
- no-change RFI handling is explicitly in or out of the workbook
- Kevin's preferred review order is known

## Milestone 5: Production Hardening

Goal:

- make the workflow repeatable, inspectable, and safe enough for real project
  use after security approval

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

1. Treat the rough Milestone 2 workbook and Milestone 3a OCR/text pass as
   already proven enough for demo context; do not keep redoing them while
   CloudHammer reliability is the blocker.
2. Finish the current `new_model_eval` structured review only as far as it
   yields training/eval artifacts.
3. Analyze the review log and create manifests for:
   - false positives as empty-label hard negatives
   - `Accept + Arc` cases as precise positive-label review batches
   - partial/overmerged/missed cases as held-out eval failures
4. Train the next CloudHammer detector iteration from the current best
   checkpoint and reviewed artifacts.
5. Compare against the held-out full-page eval before promoting the model.
6. After detector/cropper trust improves, resume Milestone 3b reliable
   itemized/detail extraction from accepted crops.
7. Review `docs/SECURITY_PRIVACY_POLICY.md` with ESA before any live-data API
   use.

## Open Decisions

- ESA: whether any external API use is allowed for live data.
- ESA: whether Zero Data Retention or Modified Abuse Monitoring is required.
- Kevin: exact workbook header fields after he sees a first real example.
- Kevin: preferred review order by sheet, trade, revision set, or mod.
- Kevin/ESA: whether no-drawing-change RFIs belong in the same workbook or a
  separate artifact.
