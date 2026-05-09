# ScopeLedger Runbook

Status: application-level runbook stub as of 2026-05-02.

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
.\.venv\Scripts\python.exe -m backend reset-projects runs\cloudhammer_real_export_corrected_split_v1_20260428_171246
```

- Expected output: reports the number of cleared app project registrations and
  the registry path, usually `runs\projects.json`.
- Safety: safe registry-only cleanup. It does not delete workspace folders,
  generated runs, `revision_sets/`, CloudHammer artifacts, model runs, or
  outputs.

Serve the local review app after creating or selecting a project registry root:

- Purpose: run the browser review surface.
- Working directory: repo root.
- Command:

```powershell
.\.venv\Scripts\python.exe -m backend serve runs\cloudhammer_real_export_corrected_split_v1_20260428_171246 --host 127.0.0.1 --port 5000
```

- Expected output/artifact: Flask serves the app at
  `http://127.0.0.1:5000`; if the registry is empty, `/projects` shows no
  active projects and allows project creation.
- Safety: local development server; it does not expose the app externally by
  itself.

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

Fresh client project flow with live CloudHammer Populate:

- Purpose: create an empty app project, import durable source revision sets,
  run live CloudHammer inference, and populate review/export surfaces.
- Working directory: repo root.
- Command:

```powershell
.\.venv\Scripts\python.exe -m backend serve runs\cloudhammer_real_export_corrected_split_v1_20260428_171246 --host 127.0.0.1 --port 5000
```

- Browser steps:
  1. Open `http://127.0.0.1:5000/projects`.
  2. Create a new project.
  3. On Overview, import manual server path:
     `F:\Desktop\m\projects\scopeLedger\revision_sets`.
  4. Click Populate Workspace.
  5. Review Overview, Drawings, Latest Set, Review Changes, Diagnostics,
     Export Workbook, and Review Packet.
- Expected output/artifact: Populate writes CloudHammer live artifacts under
  the selected project workspace at `outputs/cloudhammer_live/run_*/`, then
  imports the generated `whole_cloud_candidates_manifest.jsonl` into normal
  app review items.
- Safety: local inference/product workflow. It copies source packages into the
  selected app workspace and writes generated project outputs only. Manual
  folder import copies PDF files, not arbitrary sidecar files. It must not
  delete or mutate `revision_sets/`, CloudHammer_v2 eval/training artifacts,
  frozen pages, labels, datasets, or model checkpoints.

CloudHammer_v2-specific runbook content belongs in
`CloudHammer_v2/docs/RUNBOOK.md`.

Reference walkthrough exports and benchmark templates live in
`docs/references/`.

## TODO

- Add artifact cleanup/retention guidance for generated outputs.
