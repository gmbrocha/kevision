# Module Map

Status: canonical module map as of 2026-05-02.

- `backend/`: application services for scan, workspace state, populate/export,
  and deliverable integration.
- `webapp/`: user-facing application/review interface.
- `CloudHammer_v2/`: active eval-pivot workspace for revision-cloud detection,
  labeling, eval, and training policy. Start with `CloudHammer_v2/README.md`
  and `CloudHammer_v2/PIVOT_PLAN.md`.
- `CloudHammer/`: legacy/reference detection workspace. Do not modify or import
  from it without audit and a `CloudHammer_v2/IMPORT_LOG.md` entry.
- `resources/`: durable project resources and source-like inputs intended to be
  reusable.
- `revision_sets/`: current source drawing packages.
- `app_workspaces/`: ignored local application data root for the project
  registry and user-created project workspaces.
- `runs/` and `outputs/`: generated application artifacts.
- `experiments/`: exploratory work and prototypes.
- `docs/`: canonical application docs, references, meetings, history, and docs
  archive.
- `docs/anchors/`: reference artifacts such as benchmark templates, example
  images, and product evidence anchors.
- `docs/references/`: non-canonical reference artifacts such as spreadsheets,
  walkthrough exports, CSV templates, and compatibility policy references.
- `archive/`: old scripts, experiments, outputs, and implementation artifacts;
  not documentation history.
