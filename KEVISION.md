# KEVISION

Status: current source of truth for repository structure, setup, and active
workflow.

KEVISION is the product repo for turning blueprint revision packages into a
reviewable deliverable for downstream pricing/build coordination.

## Active Project Shape

```text
kevision/
  backend/       product orchestration, workspace state, scanners, exports
  webapp/        local Flask review UI backed by backend workspaces
  CloudHammer/   computer-vision model pipeline for revision-cloud detection
  resources/     durable sample/source resources, staged migration target
  experiments/   retained experiments that still support active work
  archive/       deprecated code, stale docs, old outputs, historical context
```

## Ownership Boundaries

### backend

`backend/` owns the product pipeline:

- revision-set scanning
- index and sheet metadata parsing
- supersedence tracking
- workspace persistence
- review queue state
- deliverable generation
- the integration seam where CloudHammer detections will plug into the product

Supported entry point:

```powershell
python -m backend --help
```

The retired `revision_tool/` package was archived on 2026-04-28. New work
should import from `backend.*` and `webapp.*` directly.

### webapp

`webapp/` contains the current local review UI. It is a Flask app that presents
backend workspace data and export flow. It does not own parsing, persistence,
or deliverable logic.

Current app command:

```powershell
python -m backend serve workspace --port 5000
```

### CloudHammer

`CloudHammer/` is the CV/model child project. It owns model data prep,
labeling, training, inference, and model-facing output contracts. It does not
own workbook generation, review UI behavior, or workspace persistence.

See `CLOUDHAMMER.md` for the CloudHammer source of truth.

### resources

`resources/` is the intended home for durable product resources:

- curated sample outputs
- source drawing sets after path compatibility work is finished

`revision_sets/` still lives at the repo root for compatibility. Tests and
CloudHammer defaults still reference that path, so moving it is a separate
staged migration.

### experiments

`experiments/` is intentionally not a junk drawer. Keep only experiments that
still matter:

- `2026_04_index_parser/`: reference for revision-index extraction
- `delta_v3/`: best denoise pipeline for delta bootstrapping
- `delta_v4/`: best-so-far delta detector
- `2026_04_delta_marker_detector/`: legacy support used by delta bootstrap
- `extract_changelog.py`: reference workbook extraction utility
- `preview_revision_changelog.py`: preview workbook utility

Throwaway exploration should either become production code, move to archive, or
be deleted once its lesson is captured.

### archive

`archive/` is quarantine for old code, old plans, stale handoffs, generated
outputs, and historical docs. It is searchable context, not active guidance.

## Happy Path

### Install

```powershell
python -m pip install -r requirements.txt
```

Use the repo parent virtual environment if present:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Scan a Workspace

```powershell
python -m backend scan revision_sets workspace
```

### Run the Review UI

```powershell
python -m backend serve workspace --port 5000
```

### Export Approved Results

```powershell
python -m backend export workspace
```

If attention items are still pending, export is blocked by default. To allow an
interim export anyway:

```powershell
python -m backend export workspace --force-attention
```

Export outputs include:

- `revision_changelog.xlsx`
- `approved_changes.csv`
- `approved_changes.json`
- `pricing_change_candidates.csv`
- `pricing_change_candidates.json`
- `pricing_change_log.csv`
- `pricing_change_log.json`
- `preflight_diagnostics.csv`
- `preflight_diagnostics.json`
- `supersedence.csv`
- `conformed_sheet_index.csv`
- `conformed_sheet_index.json`
- `revision_index.csv`
- `conformed_preview.pdf`

## Current Workflow

1. Use `backend/` to scan source revision packages and build workspace state.
2. Use `webapp/` or exported Excel to review uncertain items.
3. Use `CloudHammer/` to improve cloud detection from real blueprint pages.
4. Reattach CloudHammer inference to backend scanning/review once detections
   are reliable enough.
5. Export the Kevin-facing workbook and supporting machine-readable files.

## CloudHammer Integration Boundary

The active scanner treats cloud detection as an integration boundary. The old
inline OpenCV contour detector is not the target architecture.

CloudHammer v1 should eventually hand backend:

- page-space cloud bounding boxes
- crop image paths
- confidence scores
- debug overlay paths
- JSON manifests per source PDF

Backend should convert those into product cloud/change-region models without
CloudHammer knowing about Excel, Flask routes, or workspace persistence.

## Durable Product Docs

The maintained docs are:

- `KEVISION.md`: repo architecture, setup, and workflow
- `PRODUCT_AND_DELIVERABLE.md`: stakeholder decisions, workbook rules, benchmark, open questions, backlog
- `CLOUDHAMMER.md`: CV pipeline, labeling, prelabeling, training, inference, output contract

Older handoffs, epoch plans, and historical notes belong under `archive/`.

## Tests

```powershell
python -m pytest -q
```

## Cleanup Guardrails

- Do not move active CloudHammer runtime folders during a prelabel/training run.
- Do not move `revision_sets/` until tests and CloudHammer defaults are
  migrated together.
- Do not restore archived `revision_tool/` imports. Use `backend.*` and
  `webapp.*`.
- Do not treat `archive/` files as current implementation guidance unless a
  current doc explicitly points there for historical context.
