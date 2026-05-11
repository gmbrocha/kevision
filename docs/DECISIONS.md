# Decision Log

Status: canonical application decision log.

## 2026-05-11 - Startup Loads Allowlisted Local Env Defaults

Decision: ScopeLedger loads allowlisted environment defaults from repo-root
`.env` and the existing legacy `CloudHammer/.env` during app startup.

Reason: The private handoff app needs to reliably find the server-side API key
and production settings after restarts without relying on a manually rebuilt
PowerShell environment each time.

Consequences / follow-up:

- Process environment values still take precedence over local env files.
- The loader is intentionally narrow: only known ScopeLedger/OpenAI keys are
  accepted, and values are not printed or exposed in the UI.
- Root and nested `.env` files are ignored by Git; `.env.example` files remain
  allowed if a sample is needed later.

## 2026-05-11 - Pre Review API Calls Are Batched

Decision: Batch app-layer Pre Review API calls by default while preserving
per-item cache files and reviewer workflow.

Reason: Full project Populate can create hundreds of detected regions. Sending
one API request per region adds avoidable request overhead and makes progress
harder to inspect during a synchronous handoff run.

Consequences / follow-up:

- `SCOPELEDGER_PREREVIEW_BATCH_SIZE` defaults to `5`; `1` keeps the prior
  single-item behavior and oversized values clamp to `10`.
- Existing single-item cache files remain readable before new batch requests
  are made.
- Batch responses are validated by `item_id`; missing, duplicate, or unknown
  rows fail safely for the affected items while keeping candidates visible.
- Per-call usage is written to project JSONL under
  `outputs/pre_review/usage/pre_review_usage.jsonl`.
- This is still synchronous Populate. Background jobs remain follow-up if the
  handoff app becomes long-running shared infrastructure.

## 2026-05-02 - CloudHammer_v2 Eval-Pivot Workspace

Created `CloudHammer_v2/` as the active eval-pivot workspace. Existing
`CloudHammer/` is legacy/reference until code is audited and imported.

## 2026-05-02 - Separate Eval Subsets

The eval corpus is split into separate named subsets:

- `page_disjoint_real`
- `gold_source_family_clean_real`
- `synthetic_diagnostic`

Scores must not be blended across these subsets.

## 2026-05-02 - Synthetic Diagnostics Deferred

Synthetic diagnostics are important but deferred until the real full-page eval
baseline exists. Grammar/spec stubs may be written first.

## 2026-05-02 - GPT Project Exception

GPT/API use is broadly allowed for the current project under Kevin/boss
approval. This does not automatically apply to future projects.

## 2026-05-02 - Documentation Archive Location

Documentation archives live under `docs/archive/`. The root `archive/` remains
for old scripts, experiments, outputs, and implementation artifacts.

## 2026-05-02 - Root Pointer Docs Removed

Archived root pointer/tombstone docs and folded the CloudHammer pointer into
`README.md` and `docs/MODULES.md`.

## 2026-05-05 - Review Requires Durable Decisions

Do not treat passive visual look-over as a review gate. Review tasks must have
a way to persist decisions, corrections, labels, candidate metadata, or notes
before they block implementation.

Reason: static output inspection repeatedly creates ambiguous next steps and
does not produce usable inputs for later workflows.

Consequences:

- Review surfaces should write or pair with a manifest, CSV, JSONL, label file,
  or review log.
- Read-only screenshots, overlays, and static viewers are context only unless
  they are paired with a durable decision record.
- If direct mutation is risky, capture decisions separately first and consume
  them through a dry-run or explicit apply step.

## 2026-05-08 - Review Viewers Require Visual Evidence

Review viewers, inspection packets, contact sheets, and similar human-facing
artifacts must show the decision target directly on the image. For detection
and geometry workflows, raw crops are not enough; the viewer must render the
candidate bbox, truth bbox, prediction bbox, crop boundary, or other relevant
overlay needed to understand the requested decision.

Reason: repeated review packets without visible boxes forced the reviewer to
infer what the machine meant from metadata, which is not a reasonable human
review task and creates avoidable drift.

Consequences:

- Human-facing review artifacts must include visual overlays or explicitly mark
  the row as missing visual evidence.
- Raw-image-only viewers are acceptable only when the raw image itself is the
  decision target.
- This rule complements the durable decision-record rule; both are required for
  review gates.

## 2026-05-09 - No Seeded App UI Project

Decision: ScopeLedger app project state starts empty unless a user explicitly
creates or restores a project. The registry reset workflow clears project
registrations only; it does not delete generated run folders, source revision
sets, CloudHammer artifacts, model runs, or outputs.

Reason: the client-facing product should not depend on a pre-seeded demo
project. A fresh project should be creatable from the UI, then populated from
durable source packages such as `revision_sets/`.

Consequences:

- Missing or empty `projects.json` means no active app projects.
- Main read-only workspace pages render empty project state without crashing.
- Mutating workspace actions redirect to `/projects` until a project exists.
- Importing the repo-level `revision_sets/` folder preserves each
  `Revision #...` child as a separate package in the new workspace.
- CloudHammer_v2 diagnostic/training artifacts remain internal and are not
  treated as client product data.

## 2026-05-09 - Populate Runs Live CloudHammer Pipeline

Decision: Client-facing Populate Workspace runs the local CloudHammer
full-page pipeline before the ScopeLedger scanner imports review data.

Reason: The handoff product needs the best current cloud-detection behavior,
not the older scanner-only path or a pre-seeded demo manifest.

Consequences:

- Populate catalogs the selected project input folder, renders CloudHammer
  300-DPI page images, runs the current continuity checkpoint model, groups
  fragments with `review_v1`, exports whole-cloud candidates, and scans the
  generated manifest into normal review surfaces.
- Generated inference artifacts stay under the app project workspace at
  `outputs/cloudhammer_live/`.
- CloudHammer detections enter the UI as review items; they are not
  auto-approved for export.
- This does not mutate `revision_sets/`, CloudHammer_v2 eval/training
  artifacts, frozen pages, labels, datasets, or model checkpoints.

## 2026-05-10 - App-Owned Project Workspace Root

Decision: ScopeLedger is served as a standalone app with a managed application
data root, defaulting to repo-local `app_workspaces/`. Project workspaces are
created under `app_workspaces/projects/`; the app is no longer launched from,
or structurally defined by, a project workspace.

Reason: During preloaded demo work, the serve command pointed at an existing
workspace, which made `ProjectRegistry` derive new project storage from that
workspace's parent. For the client handoff, the app itself must own the
storage boundary while users create projects inside the app.

Consequences / follow-up:

- `python -m backend serve` defaults to the managed repo-local app data root.
- A custom app data root can still be supplied to the CLI for testing or
  operator-controlled relocation, but it is not a client-facing project field.
- The CLI rejects paths that look like a project workspace containing
  `workspace.json` for `serve` and `reset-projects`.
- The Projects UI hides server-local workspace paths.
- Project workspace path selection is rejected by the web route in all modes.
- Existing generated workspaces under `runs/` are not deleted or migrated by
  this change.

## 2026-05-10 - Populate Status Polling

Decision: Keep Populate synchronous for the private handoff, but make the
Overview page poll `/workspace/populate/status` while the request is running.

Reason: Full CloudHammer inference can take minutes, and a disabled button plus
stale zero-count status looks broken even when subprocesses are actively
writing artifacts.

Consequences / follow-up:

- The browser now shows staged PDF count and live artifact count while the
  backend run is in progress.
- The status endpoint also reports inferred CloudHammer page/candidate rows
  when those manifests exist.
- Background jobs and resumable server-side run supervision remain follow-up
  work after the immediate handoff.

## 2026-05-10 - App-Layer Pre Review Enrichment

Decision: During Populate, ScopeLedger may run a server-side Pre Review pass on
each detected visual region when explicitly configured with
`SCOPELEDGER_PREREVIEW_ENABLED=1`, `SCOPELEDGER_PREREVIEW_MODEL`, and
`OPENAI_API_KEY`.

Reason: The immediate handoff needs the best current review queue without
turning provisional model/API judgment into final truth. A second pass can
suggest tighter or multi-box geometry and cleaner text, while the reviewer
keeps control.

Consequences / follow-up:

- Every detected candidate remains visible; the API pass cannot hide, approve,
  reject, or split rows.
- Each visual item stores `scopeledger.pre_review.v1` provenance with
  `Pre Review 1`, optional `Pre Review 2`, and the reviewer-selected source.
- Workbook and review packet exports use the selected pre-review text and
  selected overlay geometry, defaulting to `Pre Review 1` when no selection is
  stored.
- The API key stays server-side, and failures fall back to `Pre Review 1`
  without blocking Populate.
- OCR context was tightened around the detected box, but symbol/legend lookup
  and split/merge model quality remain follow-up work.

## 2026-05-10 - Internal Review Truth Capture

Decision: Store internal review truth events in each project `workspace.json`
using the existing `WorkspaceStore` persistence layer, and export them only
through a CLI JSONL command.

Reason: Client review actions should quietly produce durable truth data for
future QA, eval, retraining, and pipeline analysis without adding a labeling
workflow or exposing telemetry concepts to the normal app user.

Consequences / follow-up:

- Existing accept/reject, reviewer text changes, Pre Review selection, notes,
  and bulk review actions append `review_events` records server-side.
- Events preserve immutable snapshots for original machine candidate, optional
  AI/Pre Review suggestion, OCR/context, and human final result.
- Cloudflare Access reviewer headers are captured when available; otherwise a
  stable anonymous browser-session reviewer id is used.
- No normal UI, client exports, or review screens expose these records.
- Future geometry tools can reuse the internal service for resize, merge,
  split, needs-followup, undo, and comment events without changing the storage
  contract.

## 2026-05-10 - Reviewer Crop Adjustment Is Derived Evidence

Decision: Let reviewers adjust an oversized detected crop on the existing
review item, regenerate a derived crop asset, and capture the change as an
internal `resize` review event.

Reason: The client review workflow needs a simple way to correct visibly large
or poorly bounded evidence without creating duplicate review items or mutating
the original machine candidate.

Consequences / follow-up:

- The original cloud candidate bbox remains unchanged.
- Adjusted geometry is stored separately under
  `scopeledger.crop_adjustment.v1` provenance and used by review/export
  surfaces.
- Each update writes a durable `resize` event with original candidate,
  optional Pre Review data, and the human-adjusted result.
- Split/merge controls and OCR refresh after crop adjustment remain follow-up
  work.

## 2026-05-10 - Index Pages Are Context Only

Decision: Drawing index pages remain available as context, but they are not
eligible for detected-region review items or previous/current comparison
matches.

Reason: Index tables can contain real sheet numbers and revision-cloud symbols,
which can make an index row masquerade as a drawing page. This produced bogus
review crops and a false "previous" page inside a Revision 1 package.

Consequences / follow-up:

- Uploaded folders named `Revision Set 1` are parsed as revision set number
  `1`, not `0`.
- Scanner detection is skipped on index-like pages.
- Previous/current comparison requires the same sheet number from a strictly
  earlier real revision set; pages from the same package are not treated as
  previous revisions.
- Existing project workspaces should be rescanned or repopulated to remove
  already-generated index-page review items.

## 2026-05-10 - First Real App Run Findings Are Observational

Decision: Preserve first real app-run notes in `FINDINGS_FIRST_REAL_RUN.md`,
but do not treat that exploratory run as reviewed scope, training data, or
CloudHammer_v2 label input.

Reason: the throwaway project was used to check whether the handoff app could
surface useful clouds and visible failure modes, not to create durable review
decisions.

Consequences / follow-up:

- The project registry can stay empty for the next clean handoff project.
- `FINDINGS_FIRST_REAL_RUN.md` is product triage input for UI polish,
  OCR/context extraction, symbol/legend handling, split/merge behavior, and
  zoom legibility.
- CloudHammer_v2 work resumes from the existing crop-precheck return point
  instead of starting a new mining pass from exploratory app output.

## 2026-05-09 - Handoff Webapp Hardening

Decision: Before client handoff, keep the app local-first but harden the routes
most likely to cause visible problems during review.

Reason: The app handles server-local paths and generated visual assets. A few
loose route behaviors were acceptable during internal iteration but risky for a
client-facing demo.

Consequences:

- Review writes only accept `pending`, `approved`, or `rejected`.
- Form-provided redirects must stay local to the app.
- `/project-assets/` serves only generated image assets from known CloudHammer
  artifact roots; active workspace outputs use `/outputs/`.
- Manual folder import copies PDF files only and rejects folders with no PDFs.
- CloudHammer subprocess failures are compacted before they reach Populate
  status or flash messages.
- `pytest.ini` keeps the legacy `CloudHammer/` package importable during a
  plain repo-level test run.

## 2026-05-09 - Cloudflare Access Client Handoff

Decision: Use the existing Cloudflare Tunnel hostname `ledger.nezcoupe.net` for
the immediate client handoff, with Cloudflare Access as the authentication
gate and ScopeLedger served locally through Waitress on `127.0.0.1:5000`.

Reason: This is the fastest usable private handoff path without moving source
revision packages, model checkpoints, or generated app workspaces to a new
host.

Consequences:

- Production serve mode requires `SCOPELEDGER_WEBAPP_SECRET`; the development
  fallback secret is not allowed when `--production` is used.
- Manual server-path imports in production are limited to
  `SCOPELEDGER_ALLOWED_IMPORT_ROOTS`; browser uploads remain available.
- Cloudflare Access allowed-user policy for `ledger.nezcoupe.net` was
  confirmed before sharing the link.
- Populate remains synchronous for this handoff. Background jobs and app-level
  auth remain follow-up work if this becomes a longer-lived deployment.
- Production serve mode refuses non-loopback hosts. The Cloudflare Tunnel is
  the external ingress path.
- Custom project workspace paths are disabled in the UI; projects are created
  under the app-owned `app_workspaces/projects/` root by default.
- Production POST requests require app-level CSRF tokens even though
  Cloudflare Access is the authentication gate.

## 2026-05-09 - Chunked Remote PDF Uploads

Decision: Browser-selected package PDFs upload through app-level chunked
endpoints during the client handoff. Each request carries a small chunk, and
the server reconstructs the original PDF in the selected project workspace.

Reason: Cloudflare can reject oversized request bodies with `413 Payload Too
Large` before Flask receives the request. The remote client workflow must be
able to stage large drawing-package PDFs through the browser.

Consequences:

- The Overview import and append forms use chunked upload when browser files
  are selected; manual server-path imports still use the existing form path.
- Chunks are 8 MiB, with a server-side per-chunk cap of 16 MiB.
- Only PDF filenames are accepted by the chunked upload init endpoint.
- Temporary chunk folders are removed after successful reconstruction, explicit
  browser aborts, and automatic stale cleanup. Upload resume is deferred.

## 2026-05-09 - Pre-Release Handoff Audit

Decision: Treat the current `ledger.nezcoupe.net` handoff as a private
release candidate and harden the application surface before client use.

Reason: The client will use the app remotely with real package PDFs. The app
needs predictable failure behavior and concrete browser-session protections
without delaying the handoff for a full SaaS rewrite.

Consequences:

- Production mode sets secure/HttpOnly/Lax session cookies plus
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and
  `Cache-Control: no-store`.
- Upload sessions are capped by `SCOPELEDGER_MAX_UPLOAD_BYTES`, defaulting to
  `2 GiB`, and limited to `500` PDF files per batch.
- Unreadable PDFs are recorded as high-severity diagnostics instead of
  crashing Populate.
- Declared and runtime Python dependencies were audited; Pillow is now pinned
  to `>=12.2.0` to avoid the vulnerable `12.1.1` runtime.
