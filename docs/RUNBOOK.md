# ScopeLedger Runbook

Status: application-level runbook as of 2026-05-12.

Use this file for verified application-level commands only. Do not invent
commands here.

## Read Order

1. `docs/CURRENT_STATE.md`
2. `ROADMAP.md`
3. `docs/ARCHITECTURE.md`
4. `CloudHammer_v2/README.md`

## Current Verified Workflow

Reset the app project registry without deleting project workspaces or source
packages:

- Purpose: return the Projects UI to an empty state before creating fresh
  client/project work.
- Working directory: repo root.
- Command:

```powershell
.\.venv\Scripts\python.exe -m backend reset-projects
```

- Expected output: reports the number of cleared app project registrations and
  the registry path, usually `app_workspaces\projects.json`.
- Safety: safe registry-only cleanup. It does not delete workspace folders,
  generated runs, `revision_sets/`, CloudHammer artifacts, model runs, or
  outputs.

Delete a test project and its managed project workspace from the UI:

- Purpose: remove a throwaway project registration and its app-managed
  workspace during local testing.
- Working directory: no shell command; use the Projects page.
- Browser steps:
  1. Open `/projects`.
  2. Click Delete on the project row.
  3. Confirm the dialog says `Are you sure?`.
  4. Type `DELETE` in all caps.
  5. Click Delete project.
- Expected output/artifact: the project disappears from the registry and its
  direct managed workspace under `app_workspaces/projects/` is removed.
- Safety: destructive with no undo. The backend refuses unmanaged, custom,
  symlinked, reparse-point, nested, or cross-project workspace paths and must
  not delete `revision_sets/`, CloudHammer artifacts, model runs, or outputs
  outside the managed project workspace. Deletion is blocked while the target
  project has a bulk review job running.

Serve the local review app:

- Purpose: run the browser review surface.
- Working directory: repo root.
- Command:

```powershell
.\.venv\Scripts\python.exe -m backend serve --host 127.0.0.1 --port 5000
```

- Expected output/artifact: Flask serves the app at
  `http://127.0.0.1:5000`; if the registry is empty, `/projects` shows no
  active projects and allows project creation. By default, app registry and
  project workspaces live under repo-local `app_workspaces/`.
- Note: `serve` expects an app data root. Do not pass a project workspace path
  such as an old `runs\...\workspace.json` folder; the CLI rejects that shape.
- Safety: local development server; it does not expose the app externally by
  itself.

Serve the private client handoff app behind the existing Cloudflare Access
route:

- Purpose: run ScopeLedger for the immediate client handoff at
  `https://ledger.nezcoupe.net`.
- Working directory: repo root.
- Prerequisites:
  - `C:\Users\gmbro\.cloudflared\config.yml` maps `ledger.nezcoupe.net` to
    `http://localhost:5000`.
  - Cloudflare Access has an allowed-users policy for `ledger.nezcoupe.net`.
  - `cloudflared` tunnel `nez-dev-projects` is connected.
  - The Windows host stays awake and online.
  - ScopeLedger auto-loads allowlisted defaults from repo-root `.env` and
    `CloudHammer/.env` at startup. Process environment values still override
    local files. Keep API keys and secrets out of Git.
- Command:

```powershell
$env:SCOPELEDGER_WEBAPP_SECRET = "<generated-long-random-secret>"
$env:SCOPELEDGER_ALLOWED_IMPORT_ROOTS = "F:\Desktop\m\projects\scopeLedger\revision_sets"
$env:SCOPELEDGER_MAX_UPLOAD_BYTES = "2147483648"
$env:SCOPELEDGER_PREREVIEW_ENABLED = "1"
$env:SCOPELEDGER_PREREVIEW_MODEL = "gpt-5.5"
$env:SCOPELEDGER_PREREVIEW_BATCH_SIZE = "5"
$env:SCOPELEDGER_PREREVIEW_CONCURRENCY = "2"
# Optional live inference override values, also supported from repo-root .env:
$env:SCOPELEDGER_CLOUDHAMMER_MODEL = "CloudHammer\runs\cloudhammer_roi-symbol-text-fp-hn-20260502\weights\best.pt"
$env:SCOPELEDGER_CLOUDHAMMER_TIMEOUT_SECONDS = "3600"
# Optional if already present in repo-root .env or CloudHammer\.env:
$env:OPENAI_API_KEY = "<server-side-api-key>"
.\.venv\Scripts\python.exe -m backend serve --host 127.0.0.1 --port 5000 --production
```

- Expected output/artifact: Waitress serves ScopeLedger at
  `http://127.0.0.1:5000`; Cloudflare Tunnel exposes it at
  `https://ledger.nezcoupe.net`, where Cloudflare Access prompts before the
  app loads.
- Safety: private handoff mode. Cloudflare Access is the auth gate. The app
  must bind only to loopback in `--production`; POST requests require CSRF
  tokens; session cookies are secure/HttpOnly/Lax; manual server-path imports
  are restricted to the configured import root; project workspaces are managed
  under the app-owned `app_workspaces/projects/` root. When Pre Review is
  enabled, focused downscaled crop images and local OCR context are sent
  through the server-side OpenAI API key in small batches and cached under the
  active project `outputs/pre_review/` folder. Per-call API usage is logged as
  JSONL under `outputs/pre_review/usage/pre_review_usage.jsonl` for internal
  cost/progress inspection. This does not make the app public-hosting ready without
  additional background jobs, durable process supervision, retention policy,
  and app-level user/session management.

Check the existing Cloudflare Tunnel mapping:

- Purpose: confirm the local route still points `ledger.nezcoupe.net` at the
  local app port.
- Working directory: repo root or any PowerShell directory.
- Command:

```powershell
Get-Content $env:USERPROFILE\.cloudflared\config.yml
```

- Expected output/artifact: an ingress entry for `ledger.nezcoupe.net` with
  service `http://localhost:5000`.
- Safety: read-only.

Check the Cloudflare Tunnel connector:

- Purpose: confirm the `nez-dev-projects` tunnel has an active connector.
- Working directory: repo root or any PowerShell directory.
- Command:

```powershell
C:\cloudflared\cloudflared.exe tunnel info b829004a-c4f7-4141-98d0-a83bf1b90068
```

- Expected output/artifact: tunnel info for `nez-dev-projects` with at least
  one active connector.
- Safety: read-only.

Run the repo test suite:

- Purpose: verify ScopeLedger app tests and legacy CloudHammer unit tests from
  a clean repo-level command.
- Working directory: repo root.
- Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- Expected output/artifact: pytest completes without collection errors.
- Safety: local test run; no source packages, eval artifacts, model
  checkpoints, or project registries are modified.

Run the fast release smoke suite:

- Purpose: verify the main app handoff path without live CloudHammer/GPT
  processing. The suite covers empty project shell, active-project navigation,
  chunked PDF upload, package history/status rows, package-scoped review
  filters, manual Mark as legend, sheet overlay coordinate rendering, workbook
  and review-packet generation, and active project selection.
- Working directory: repo root.
- Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_smoke_http.py -q
```

- Expected output/artifact: `9 passed`. The tests build disposable tiny
  project workspaces and PDFs under pytest temp directories.
- Safety: local temp-fixture test run. It does not use live GPT, run
  CloudHammer, mutate `revision_sets/`, app-managed project registries,
  CloudHammer_v2 eval/training artifacts, model checkpoints, or client source
  packages.

Run optional browser smoke tests:

- Purpose: verify the same core handoff screens through a real Chromium
  browser when Playwright is installed.
- Working directory: repo root.
- Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_smoke_playwright.py -q
```

- Expected output/artifact: `4 passed` when Playwright and the Chromium browser
  are installed, or `4 skipped` when Playwright is not installed in the local
  environment.
- Safety: local in-process browser smoke. It uses pytest temp directories and
  does not touch source packages, eval artifacts, model checkpoints, or app
  project registries.

Export internal review events:

- Purpose: write the hidden review-event audit/truth records for one app
  project as JSONL.
- Working directory: repo root.
- Command:

```powershell
.\.venv\Scripts\python.exe -m backend export-review-events app_workspaces --project-id <project-id>
```

- Optional explicit output:

```powershell
.\.venv\Scripts\python.exe -m backend export-review-events app_workspaces --project-id <project-id> --out exports\review_events_<project-id>.jsonl
```

- Expected output/artifact: one JSON object per review event. If `--out` is
  omitted, the file is written to the project's `outputs/` folder as
  `review_events_<project-id>.jsonl`.
- Safety: internal export only. It reads the project `workspace.json` and does
  not appear in the client UI or normal workbook/review-packet exports.

Fresh client project flow with live Populate and optional Pre Review:

- Purpose: create an empty app project, import durable source revision sets,
  run live drawing analysis, optionally run server-side Pre Review, and
  populate review/export surfaces.
- Working directory: repo root.
- Command:

```powershell
.\.venv\Scripts\python.exe -m backend serve --host 127.0.0.1 --port 5000
```

- Browser steps:
  1. Open `http://127.0.0.1:5000/projects`.
  2. Create a new project.
  3. On Overview, import packages by selecting PDFs or folders in the browser.
     Enter the package revision number before import. One number applies to
     the selected PDF batch or folder package.
  4. Confirm the Revision packages table shows a positive integer revision
     number for every staged package. Edit numbers and click Save package
     order if needed before Populate. Before Populate, the
     staged-for-population card should list the imported packages and PDF
     filenames. After Populate, loaded package revision numbers should render
     as static values, not editable number controls.
  5. Click Populate Workspace. This processes only new or dirty packages and
     reuses clean package runs. Use Rebuild all packages only when every staged
     package needs a fresh CloudHammer run.
  6. Review Overview, Drawings, Latest Set, Review Changes, Diagnostics,
     Export Workbook, and Review Packet.
- Expected output/artifact: Populate writes package-level live detection
  artifacts under the selected project workspace at
  `outputs/cloudhammer_live/run_*/`, writes an assembled manifest under
  `outputs/cloudhammer_live/assembled/`, then imports the assembled
  `whole_cloud_candidates_manifest.jsonl` into normal app review items. If Pre
  Review is enabled and `OPENAI_API_KEY` is present, provisional second-pass
  metadata is cached under `outputs/pre_review/` and appears in the review
  screen as `Pre Review 2`; otherwise review items keep raw `Pre Review 1`.
  API calls batch up to
  `SCOPELEDGER_PREREVIEW_BATCH_SIZE` items at a time, defaulting to `5`, and
  run up to `SCOPELEDGER_PREREVIEW_CONCURRENCY` batches in parallel, defaulting
  to `2`. API input images are focused around the detected box and downscaled;
  usage records are written under `outputs/pre_review/usage/`. Populate also
  builds the sheet-version keynote registry and deterministically expands
  matching `Pre Review 2` keynote references without extra API calls. While
  Populate is running, Overview polls `/workspace/populate/status` and should
  show staged PDF count, package reuse/process counts, the current
  revision/package, keynote registry/expansion counts, and live artifact count
  before final package/sheet/change counts appear.
  Drawing index pages remain context only; they should not create review items
  or be used as previous/current comparison sheets. Populate is blocked until
  staged package revision numbers are complete and unique. A later package with
  the same sheet number does not automatically remove older package review
  items; approved scope carries forward unless explicitly rejected or
  item-superseded.
- Safety: local inference/product workflow. Browser-selected PDF files upload
  in 8 MiB chunks and are reconstructed in the selected app workspace. It writes
  generated project outputs only and must not delete or mutate `revision_sets/`,
  CloudHammer_v2 eval/training artifacts, frozen pages, labels, datasets, or
  model checkpoints.

Large remote browser uploads:

- Purpose: stage package PDFs through `https://ledger.nezcoupe.net` without
  hitting Cloudflare's per-request upload limit.
- Working directory: no shell command; use the Overview page.
- Browser steps:
  1. Open the project Overview page.
  2. Under Import new package, choose a PDF or folder from the browser file
     dialog.
  3. Enter the package revision number.
  4. Click Import package.
  5. Wait for the chunked upload progress bar to finish and redirect back to
     Overview.
  6. Confirm package order and click Populate Workspace.
- Expected output/artifact: selected PDFs appear under the active project's
  `input/` folder; temporary chunks are created under `.chunked_uploads/` and
  removed after successful reconstruction, browser aborts, or stale cleanup.
- Safety: upload-only into the active project workspace. Only `.pdf` files are
  accepted by the chunked upload init endpoint. Upload batches are capped by
  `SCOPELEDGER_MAX_UPLOAD_BYTES`, defaulting to `2 GiB`, and by `500` PDF
  files per batch.

Find keyed-note legend rows from header text and marker graphics:

- Purpose: run the same backend keynote extraction service used by Populate as
  a standalone diagnostic. It builds a registry of sheet keynote legend entries
  by finding `KEYNOTE`/`KEYNOTES`/`KEY NOTE`/`KEY NOTES`/`KEYED NOTES`
  headers, then extracting marker labels with adjacent description text or
  `KEYED NOTES` numbered-list entries where the header uses an empty sample
  marker, or no marker, and the definitions are plain `1.` / `2.` rows.
- Working directory: repo root.
- Command:

```powershell
.\.venv\Scripts\python.exe utils\find_keynote_legends.py --input-dir "revision_sets\Revision #1 - Drawing Changes"
```

- Expected output/artifact: a timestamped folder under
  `test_tmp\keynote_legend_finder\` containing `summary.json`,
  `keynote_legend_rows.csv`, `keynote_legend_rows.jsonl`,
  `keynote_legend_regions.jsonl`, `keynotes_by_sheet.json`, and
  `keynote_legend_viewer.html`.
- Safety: derived diagnostic output only. It reads source PDFs with PyMuPDF
  text/vector extraction and does not mutate source PDFs, revision sets, app
  workspace state, CloudHammer_v2 eval/training artifacts, labels, model
  files, or exports.

Run pre-release audit checks:

- Purpose: verify tests, dependency vulnerability posture, static security
  scan, and installed package consistency before sharing the client link.
- Working directory: repo root.
- Commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
.\.venv\Scripts\python.exe -m pip_audit
.\.venv\Scripts\python.exe -m bandit -q -r backend webapp -x tests
.\.venv\Scripts\python.exe -m pip check
node --check webapp\static\app.js
```

- Expected output/artifact: tests pass, declared/runtime dependency audits
  report no known vulnerabilities, Bandit reports no actionable findings,
  `pip check` reports no broken requirements, and JavaScript syntax check
  succeeds. Torch CUDA wheels may be skipped by `pip-audit` because they are
  not PyPI-resolvable.
- Safety: read-only checks except for normal test/cache artifacts.

CloudHammer_v2-specific runbook content belongs in
`CloudHammer_v2/docs/RUNBOOK.md`.

Reference walkthrough exports and benchmark templates live in
`docs/references/`.

## TODO

- Add artifact cleanup/retention guidance for generated outputs.
