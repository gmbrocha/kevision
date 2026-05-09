# Decision Log

Status: canonical application decision log.

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
- Cloudflare Access allowed-user policy must be confirmed in the Cloudflare
  dashboard before sharing the link.
- Populate remains synchronous for this handoff. Background jobs and app-level
  auth remain follow-up work if this becomes a longer-lived deployment.
- Production serve mode refuses non-loopback hosts. The Cloudflare Tunnel is
  the external ingress path.
- Custom project workspace paths are disabled in production handoff mode;
  projects are created under the registry's managed projects folder.
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
