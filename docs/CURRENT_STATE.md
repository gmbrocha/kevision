# Current State

Status: read this first before changing ScopeLedger or CloudHammer_v2.

## Active Branch And Workspace

- Branch: `cloudhammer-v2-eval-pivot`
- Application workspace: repo root
- Active detection workspace: `CloudHammer_v2/`
- Legacy detection workspace: `CloudHammer/` reference only

## Application Project Registry Status

- The app registry is local ignored state under `app_workspaces/` and may
  contain throwaway smoke-test projects. Any current `TEST Revision` style
  rows are disposable local app data, not client-approved scope, reviewed
  labels, training data, or CloudHammer_v2 eval material. `/projects` remains
  the expected first screen before creating or selecting a handoff project.
- The web app no longer seeds a `Demo Project` automatically when the project
  registry is missing or empty.
- The app registry and managed project workspaces now live under the
  application data root, defaulting to repo-local `app_workspaces/`. The app is
  not launched from a project workspace; user-created projects define their own
  workspaces under `app_workspaces/projects/`.
- The Projects UI intentionally does not expose local workspace filesystem
  paths. Custom project workspace paths are not accepted from the UI.
- Empty app registry state is valid: `/projects` and the main read-only
  workspace pages should render with no active project and prompt explicit
  project creation. Mutating workspace actions still require an active project.
- App project reset is registry-only. It must not delete old generated run
  folders, `revision_sets/`, CloudHammer artifacts, model runs, or outputs.
- The Projects UI has an explicit hard-gated Delete action for project cleanup.
  The operator must type `DELETE`; the action removes the project registry
  entry and its direct managed workspace under `app_workspaces/projects/`.
  It refuses unmanaged, custom, nested, linked, reparse-point, or cross-project
  paths and is blocked while that project has a bulk review job running.
- Fresh projects can import the repo-level `revision_sets/` folder; each
  `Revision #...` child folder is copied as its own package into the selected
  project input folder before Populate Workspace runs.
- Revision package order is now explicit app state. Overview shows each staged
  package with an editable positive integer revision number; Populate is
  blocked until every staged package with PDFs has a revision number and no two
  packages share the same number. Folder-name parsing is only a convenience
  fallback for newly reconciled legacy/staged folders. Browser file or folder
  upload uses one package revision number for the whole selected package.
  Before Populate, Overview also shows a staged-for-population package/file
  summary so imported PDFs are visible without exposing local workspace paths.
  After Populate, the Revision packages table displays the assigned revision
  number as static package metadata rather than an editable control.
- Populate Workspace now processes revision packages incrementally. The
  default action runs the local CloudHammer full-page pipeline only for new or
  dirty staged packages, reuses clean package runs, assembles all package
  manifests into a project-level scan, then imports review data. `Rebuild all
  packages` remains available when every package needs a fresh run. The live
  handoff path uses the current continuity checkpoint
  `CloudHammer/runs/cloudhammer_roi-symbol-text-fp-hn-20260502/weights/best.pt`,
  grouping profile `review_v1`, and whole-cloud export under the selected app
  project's `outputs/cloudhammer_live/` folder. A clean follow-up Populate now
  short-circuits when package runs, scan cache, keynote registry, and Pre
  Review state are already current, so accidentally pressing Populate again
  does not reassemble manifests, rescan PDFs, or make GPT calls.
- Populate then runs app-layer Pre Review enrichment when
  `SCOPELEDGER_PREREVIEW_ENABLED=1` and `OPENAI_API_KEY` are configured. The
  app keeps every detected candidate visible, stores raw `Pre Review 1` plus a
  provisional `Pre Review 2`, and makes the reviewer choose which text/geometry
  becomes export truth. Missing, disabled, rate-limited, or failed API calls do
  not block Populate. Pre Review API calls now batch up to
  `SCOPELEDGER_PREREVIEW_BATCH_SIZE` items at a time, defaulting to `5`, and
  runs up to `SCOPELEDGER_PREREVIEW_CONCURRENCY` API batches in parallel,
  defaulting to `2`. API calls use focused downscaled crops around the Pre
  Review 1 box rather than the entire review crop; review UI crops remain
  unchanged. Stable cache keys are based on item/candidate/box/text/context
  metadata rather than full crop file bytes, while legacy cache files remain
  readable. Per-call usage JSONL is written under the active project
  `outputs/pre_review/usage/` folder. After Pre Review, a deterministic
  same-sheet keynote pass expands resolved `Pre Review 2` references such as
  `Z.8` or `Keynotes: 1, 2` into `TOKEN: definition` text without additional
  API calls.
- Populate now adds a conservative legend-context pass between OCR extraction
  and Pre Review. Probable legend/keynote regions remain visible in the review
  queue until the reviewer clicks `Accept as legend`; every review detail also
  has a lower-emphasis `Mark as legend` action for missed detections. Confirmed
  legend context is soft-hidden from normal queues, counts, workbook export,
  pricing candidates, review packet, and Drawings overlays while staying preserved in
  `workspace.json` and review-event JSONL. The post-implementation audit is
  documented in `docs/APP_AUDIT_2026_05_11_LEGEND_CONTEXT.md`.
- At app startup, ScopeLedger loads allowlisted local environment defaults from
  repo-root `.env` and the existing legacy `CloudHammer/.env` if present.
  Already-set process environment variables still win. This supports the
  server-side `OPENAI_API_KEY`, handoff app settings, and live CloudHammer
  runtime keys without exposing values in the UI or committing secrets.
- Review actions now append internal `review_events` records to the active
  project `workspace.json`. These events preserve the original detected
  candidate, optional Pre Review metadata, and the human final result for
  future internal QA, audit, and pipeline analysis. They are not exposed in the
  normal UI or client-facing exports; use the CLI-only JSONL export when
  needed. For local test sessions, setting `REVIEW_CAPTURE=false` disables new
  `review_events` writes while leaving normal review state changes enabled.
  Bulk accept/reject now runs as an in-memory background job: the
  browser can continue navigating read-only pages, each changed item still
  gets its own review event, and the job commits the workspace in one save.
  Other workspace mutations are temporarily blocked until the job finishes.
- The review page now supports client-facing crop adjustment for individual
  detected regions. Adjustments regenerate a derived crop asset, make
  review/export surfaces use the adjusted geometry, and append an internal
  `resize` review event while leaving the original machine candidate
  unchanged.
- Review items now have explicit queue ordering and soft supersession fields.
  Superseded parent items remain in `workspace.json` for audit/review-event
  history but are hidden from the normal queue, counts, bulk review, workbook
  export, pricing candidates, and review packet. Direct parent URLs redirect
  to replacement items when possible, and mutation endpoints reject superseded
  parents.
- Review items are revision-scope records. A later package containing the same
  sheet number does not automatically hide, reject, or supersede older package
  clouds on that sheet; approved scope from multiple revision packages remains
  exportable unless explicitly rejected or item-superseded.
- Review Changes now has package-scoped review filters. The default remains all
  pending active review items, while reviewers can switch to the newest
  revision package or one specific package without losing status/search/needs
  check filtering. `Start reviewing` now preserves those composed filters when
  entering detail review.
- The review page now supports `Correct overmerge` and `Correct partial` from
  the current crop image. Overmerge correction creates multiple pending child
  review items in the same queue position and records an internal `split`
  event. Partial correction creates one replacement review item and records an
  internal `resize` event. Full-sheet correction remains a later follow-up.
- The Overview page now polls `/workspace/populate/status` during Populate so
  the browser shows staged PDF count, package-level reuse/process progress,
  current revision/package markers, keynote registry/expansion counts, live
  artifact count, and completion/fail state while CloudHammer runs inside long
  synchronous backend work. Overview also shows a package processing history
  panel with current dirty, reused, processed, failed, and pending state for
  each staged package. On app startup, a persisted `running` Populate status is
  marked `interrupted` so a killed or restarted server does not leave Overview
  looking permanently stuck; generated artifacts and completed Pre Review cache
  entries are preserved.
- Copied manual-test package folders `revision_sets/Revision #8 - test copy
  reduced size` and `revision_sets/Revision #9 - test copy 2 reduced size`
  are intentionally reduced subsets for app flow testing. The original
  Revision #1 and Revision #2 source package folders remain untouched.
- OCR extraction is now intentionally tighter around detected boxes, with
  isolated numeric clutter filtered unless it looks like a tag/callout/keynote
  reference. Legend symbol lookup is available as provisional context from
  probable legend/keynote regions; image-shape detection for hexagons/circles
  and split/merge quality remain follow-up work.
- Keynote legend extraction is now a shared backend service used by Populate
  and by the standalone `utils/find_keynote_legends.py` diagnostic wrapper.
  Populate builds a sheet-version-scoped keynote registry from explicit
  `KEYNOTE` / `KEYED NOTES` headers, marker labels, and numbered-list blocks,
  then uses that registry to expand same-sheet GPT `Pre Review 2` keynote
  references. The registry caches sheet entries, including sheets with no
  detected keynote definitions, so unchanged follow-up Populates avoid
  repeated PyMuPDF header/shape scans. The diagnostic wrapper still writes
  derived inspection artifacts under `test_tmp/` without mutating source PDFs
  or app workspaces.
- The 2026-05-14 app pipeline audit is documented in
  `docs/APP_AUDIT_2026_05_14_PIPELINE_EFFICIENCY.md`. Implemented fixes keep
  revision changelog workbook grouping scoped by sheet version, reuse PDF text
  words across same-page cloud scope extraction, reuse scanner cache entries
  without rebuilding them, pass assembled candidate rows in memory, and make
  populate artifact polling stream counts instead of materializing every file
  path.
- Drawing index pages are context only. The scanner keeps them available as
  sheet metadata/context, but they are not eligible for detected-region review
  items, and previous/current comparisons now require the same sheet number
  from a strictly earlier real revision set.
- Sheet metadata extraction prefers right-side title-block sheet IDs and
  repeated same-page sheet IDs before late cross-reference tokens. Scan cache
  entries carry a sheet metadata version so parser fixes invalidate stale sheet
  assignments on the next Populate.
- The 2026-05-14 nightly app audit is documented in
  `docs/APP_AUDIT_2026_05_14_NIGHTLY.md`. It fixed geometry corrections so
  replacement review items keep the current visible scope text and tightened
  package-filter preservation on the review detail page.
- Latest Set revision chains also require strictly earlier revision numbers.
  Duplicate sheet-number detections inside the same package do not count as
  prior versions in the conformed/latest-set view.
- Handoff hardening pass is complete for the current web app surface: review
  status writes are validated, form redirects are constrained to local paths,
  project-root asset serving is limited to generated image assets, manual
  folder import copies PDFs only, and CloudHammer subprocess failures are
  compact enough to display in the UI. Plain repo-level pytest now includes
  the legacy CloudHammer import path through `pytest.ini`.
- Immediate client handoff hosting uses the existing Cloudflare Tunnel route
  `ledger.nezcoupe.net` -> `http://localhost:5000`. Production serve mode runs
  Waitress, requires `SCOPELEDGER_WEBAPP_SECRET`, and restricts manual
  server-path imports to `SCOPELEDGER_ALLOWED_IMPORT_ROOTS`. It also requires
  loopback binding, secure session cookies, production CSRF tokens on POST
  requests, and release security headers. Cloudflare Access is confirmed as
  the authentication gate for `ledger.nezcoupe.net`; this is not a public SaaS
  deployment.
- Remote browser PDF intake now uses chunked upload endpoints for selected
  files/folders, with 8 MiB chunks reconstructed inside the active project
  workspace before Populate runs. This avoids Cloudflare request-body 413s for
  large package PDFs. The client-facing Overview UI no longer shows manual
  server-path import fields.
  Failed or abandoned chunk sessions are cleaned by browser abort calls when
  possible and by automatic stale cleanup under `.chunked_uploads/`. Uploads
  are capped by `SCOPELEDGER_MAX_UPLOAD_BYTES`, defaulting to `2 GiB`.
- Pre-release app audit is complete for the private handoff surface. Declared
  dependencies and the current runtime environment pass `pip-audit` after
  pinning `urllib3>=2.7.0`; the local CUDA `torch` wheels are skipped by
  `pip-audit` because they are not PyPI distributions. Bandit has no remaining
  actionable findings after documenting controlled subprocess calls,
  non-security stable IDs, and explicit usage-parsing fallback behavior.
  Uploaded unreadable PDFs now become high-severity diagnostics instead of
  crashing scans.
- First real app-run observations are captured in
  `FINDINGS_FIRST_REAL_RUN.md`. That run was exploratory, then reset; its
  notes are not reviewed labels, training data, or client-approved scope.
- CloudHammer_v2 training/eval work remains paused for client handoff work and
  should resume afterward at the existing crop-precheck blocker:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.summary.md`.

## Documentation Structure Status

Root-level docs now describe the overall ScopeLedger application. CloudHammer_v2
docs describe only revision-cloud detection, eval, labeling, and training
policy.

Canonical root docs:

- `README.md`
- `AGENTS.md`
- `PRODUCT_AND_DELIVERY.md`
- `ROADMAP.md`
- `docs/`

Canonical application docs live directly under `docs/`. Reference artifacts live
under `docs/references/`, `docs/anchors/`, `docs/history/`, and
`docs/meetings/` as appropriate.

## Cleanup Status

Root docs cleanup is substantially complete:

- Root `CLOUDHAMMER.md`, `SCOPELEDGER.md`, `PLAN_PIVOT_5_2_26.md`, and
  duplicate `PRODUCT_AND_DELIVERABLE.md` were removed or replaced by canonical
  paths in prior cleanup work.
- `docs/SECURITY_PRIVACY_POLICY.md` remains as a compatibility stub only.
- Documentation history is preserved under
  `docs/archive/docs_archive_2026_05_02/`.
- Report-only cleanup audits live under `docs/archive_cleanup_audits/`.
- The experiments retention review has been completed, and approved lessons were promoted into CloudHammer_v2 docs without importing experiment code.

## Canonical Now

- Product entrypoint: `README.md`
- Product/deliverable intent: `PRODUCT_AND_DELIVERY.md`
- Product roadmap: `ROADMAP.md`
- Application state: `docs/CURRENT_STATE.md`
- Application module map: `docs/MODULES.md`
- CloudHammer subsystem entrypoint: `CloudHammer_v2/README.md`
- CloudHammer pivot plan: `CloudHammer_v2/PIVOT_PLAN.md`
- Next action queue: `docs/NEXT_ACTIONS.md`

## Intentionally Archived

- Superseded root planning and pointer docs.
- Pre-restructure product, CloudHammer, ScopeLedger, and roadmap drafts.
- Older source policy docs that were summarized into canonical policy docs.
- Report-only audits for runs/experiments cleanup and experiment-retention
  review.

## Do Not Touch

- Do not reorganize source code, data, model runs, or generated outputs.
- Do not move datasets or legacy CloudHammer artifacts.
- Do not import old CloudHammer or experiment scripts without audit.
- Do not treat archived docs as current source of truth.
- Do not blend real and synthetic eval scores.
- Do not treat current-project GPT/API approval as future-project approval.

## CloudHammer_v2 Baseline Status

The first CloudHammer_v2 `page_disjoint_real` baseline was completed on
2026-05-02 using GPT-provisional full-page labels, but that run is now treated
only as provisional scaffolding. The current steering baseline is the
human-audited `page_disjoint_real` scoring completed on 2026-05-04.

- Frozen pages: `17`
- Human truth review queue:
  `CloudHammer_v2/eval/page_disjoint_real_human_review/manifest.jsonl`
- Human truth labels:
  `CloudHammer_v2/eval/page_disjoint_real_human_review/labels/`
- Human-audited eval manifest:
  `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.human_audited.jsonl`
- Human-audited truth summary:
  `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_human_audited_summary.md`
- Human-audited truth contains `26` cloud boxes across `17` pages, with `1`
  empty truth page.
- The clean page-disjoint pool is exhausted under the current strict registry:
  all `17` eligible untouched standard drawing pages were frozen. The set is
  likely plumbing-heavy by sheet metadata heuristic, so aggregate scores need
  bucketed interpretation.
- Style-balance diagnostic touched-real queue:
  `CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/manifest.jsonl`
  with `12` low-use touched pages. This is diagnostic-only and not
  promotion-clean.
- GPT-5.4 full-page labels: provisional only
- GPT-5.5 full-page labels: accidental scratch only, do-not-score
- Current human-audited baseline report:
  `CloudHammer_v2/docs/BASELINE_EVAL_REPORT_2026_05_04.md`
- Prior GPT-provisional baseline report:
  `CloudHammer_v2/docs/BASELINE_EVAL_REPORT_2026_05_02.md`
- Human-audited baseline result at IoU `0.25`: `pipeline_full` F1 `0.741`
  with `8` false positives and `6` misses; `model_only_tiled` F1 `0.479`
  with `47` false positives and `3` misses.
- Human-audited mismatch queue:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/mismatch_review_queue.jsonl`
- Read-only overlay mismatch packet:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/README.md`
- Reviewed mismatch log:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.reviewed.csv`
  with `77` reviewed rows, `0` unreviewed rows, and `0` invalid rows.
- First non-frozen postprocessing diagnostic:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_summary.md`
  with `44` report-only diagnostic rows from `34` non-frozen candidates.
- Static viewer for the diagnostic:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_viewer.html`
  links grouped candidate IDs to existing crop paths and source page renders.
- GPT-5.5 prefilled postprocessing diagnostic review metadata:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_review_log.gpt55_prefill.csv`
  embedded in the default reviewer and also available in companion reviewer
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_viewer.gpt55_prefill.html`.
  These suggestions were human-confirmed/corrected and exported to
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_review_log.reviewed.csv`.
- Dry-run postprocessing plan:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_dry_run_summary.md`.
  It is report-only and proposes `3` merge components plus `10` tighten bbox
  actions, while blocking `12` expand/`tighten_adjust` rows and `3` split rows
  for explicit geometry before any apply step.
- Blocked-geometry reviewer:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_reviewer.html`
  produced
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_review.reviewed.csv`
  with `18` reviewed geometry items.
- GPT-5.5 provisional blocked-geometry prefill:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_review.gpt55_prefill.csv`
  with `18` `gpt_prefilled` provisional rows. Companion reviewer:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_reviewer.gpt55_prefill.html`.
- Postprocessing apply dry-run comparison:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_dry_run_20260505/postprocessing_apply_dry_run_summary.md`.
  It is report-first and non-mutating. It previews `25` referenced source
  candidates becoming `23` output candidates, resolves all `15` manual geometry
  row actions, and reports one duplicate split geometry record collapsed into
  the latest reviewed row.
- Non-frozen postprocessing apply output:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/postprocessed_non_frozen_apply_summary.md`.
  It writes a derived manifest only. The `34` source candidates become `32`
  postprocessed candidates, with `13` suppression records for source candidates
  replaced by merge/split outputs.
- Non-frozen postprocessing behavior comparison:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_behavior_comparison_20260505/postprocessing_non_frozen_behavior_summary.md`.
  It compares the original source manifest with the derived postprocessed
  manifest without scoring, tuning, or crop generation. Candidate count changes
  `34` -> `32`, total bbox area ratio is `0.831645`, and it identified `22`
  rows that needed crop regeneration before crop-based inspection/export.
- Postprocessed non-frozen crop regeneration:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/postprocessed_non_frozen_crop_regeneration_summary.md`.
  Dry-run was run first, then `22` regenerated PNG crops were written. The
  crop-ready manifest has `32` rows: `22` regenerated postprocessed crops and
  `10` preserved source crops. It is a separate derived manifest and does not
  mutate labels, eval manifests, predictions, datasets, training data, source
  candidate manifests, or threshold-tuning inputs.
- GPT-5.5 postprocessed crop inspection precheck:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.summary.md`.
  It prechecked all `32` crop-ready candidates after dry-run overlay creation:
  `28` `accept_crop`, `2` `needs_human_review`, and `2`
  `reject_no_visible_cloud`. Companion viewer:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.html`.
  The viewer renders red-bbox overlay images as the primary visual evidence for
  all `32` rows. The short browser copy is:
  `CloudHammer_v2/outputs/postprocessed_crop_inspection.gpt55_prefill.html`
  with short local assets under
  `CloudHammer_v2/outputs/postprocessed_crop_inspection_assets/`. These
  findings are provisional inspection metadata only.
- GPT-5.5 cropped supplement prelabels:
  `CloudHammer_v2/data/gpt55_crop_prelabels_small_corpus_supplement_20260502/README.md`
- Current blocker: resolve or accept the `4` non-accepted GPT crop-precheck
  rows, then decide whether the `28` GPT-accepted crop-ready candidates feed
  crop-based inspection/export wiring or a contained pipeline-consumption
  comparison. No labels, eval manifests, predictions, datasets, training data,
  or legacy candidate manifests were mutated.
- Diagnostic scope reset:
  `CloudHammer_v2/docs/DIAGNOSTIC_STOPLIGHT_AUDIT_2026_05_05.md`.
  New CloudHammer diagnostic/review queues must be classified `GREEN`,
  `YELLOW`, or `RED` before creation. Do not create `RED` queues, and do not
  create `YELLOW` queues unless cheap, GPT-prefilled/backfilled or sampled, and
  explicitly approved.

Correction note: GPT-5.5 full-page labels on `page_disjoint_real` were created
by mistake and are marked do-not-score. GPT-5.5 was rerun on the intended
cropped supplement review batch; those outputs are `gpt_provisional` and need
human confirmation/correction before training use.

## Immediate Next Steps

- Create the next real project from `/projects`, stage PDFs through browser
  upload or the allowed `revision_sets/` import root, configure server-side
  Pre Review if using API enrichment, and run Populate.
- During the next populate/review, verify that index pages do not create review
  items and that previous/current comparison only matches the same sheet from
  a strictly earlier revision set.
- After `REVIEW_CAPTURE` is re-enabled for real client review, confirm normal
  accept/reject and Pre Review selection create internal review events, then
  export them with the CLI-only `export-review-events` command if analysis is
  needed.
- During the next review smoke, resize one oversized crop with `Adjust crop`,
  confirm the regenerated crop stays on the same review item, and verify the
  JSONL review-event export contains a `resize` event.
- During the next review smoke, confirm one probable legend/keynote item with
  `Accept as legend`, verify it disappears from the normal queue, and verify a
  linked real scope item shows the resolved legend context.
- Use `FINDINGS_FIRST_REAL_RUN.md` as observational triage for UI polish,
  OCR/context extraction, geometry split/merge work, symbol/legend handling,
  and zoom legibility. Do not treat it as training ground truth.
- After client handoff work, resume CloudHammer_v2 at the crop-precheck return
  point above: resolve or accept rows `20`, `23`, `24`, and `29`, then decide
  the next pipeline-consumption/training step from that existing path.
- Preserve frozen `page_disjoint_real` pages as eval-only and do not create
  new CloudHammer diagnostic queues unless they pass the stoplight rule in the
  diagnostic scope reset.
