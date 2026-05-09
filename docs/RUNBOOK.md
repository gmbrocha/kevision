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

CloudHammer_v2-specific runbook content belongs in
`CloudHammer_v2/docs/RUNBOOK.md`.

Reference walkthrough exports and benchmark templates live in
`docs/references/`.

## TODO

- Add verified backend scan/export commands after the eval pivot is stable.
- Add artifact cleanup/retention guidance for generated outputs.
