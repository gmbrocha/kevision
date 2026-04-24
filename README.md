# KEVISION

KEVISION is the root product repo.

- `CloudHammer/` is the computer-vision child project for revision-cloud data prep, labeling, training, and inference.
- `backend/` owns orchestration, revision-state parsing, workspace persistence, and deliverable generation.
- `webapp/` is the current review UI surface.
- `resources/` is the landing zone for source drawing sets and curated sample outputs.
- `archive/` holds quarantined experiments, outputs, and deprecated scripts.

`revision_tool/` still exists only as a compatibility wrapper around the migrated `backend/` and `webapp/` modules.

## Repo Layout

```text
kevision/
  CloudHammer/
  backend/
  webapp/
  resources/
  docs/
  archive/
```

See:

- `docs/README.md` for the docs index
- `docs/architecture.md` for the current structure and migration boundaries

## Install

```powershell
python -m pip install -r requirements.txt
```

## Happy Path

### CloudHammer model pipeline

From `CloudHammer/`:

```powershell
python scripts/catalog_pages.py --no-render
python scripts/catalog_pages.py --limit 5 --overwrite
python scripts/run_delta_bootstrap.py --limit 1
python scripts/extract_delta_rois.py --limit 20
python scripts/extract_cloud_rois.py --limit 20
python scripts/prelabel_cloud_rois_openai.py --limit 25 --dry-run
python scripts/prepare_labelimg_review.py
python scripts/train_roi_detector.py
python scripts/infer_pages.py --model runs/cloudhammer_roi/weights/best.pt --limit 5
```

Labeling and prelabel docs live in:

- `CloudHammer/docs/README.md`
- `CloudHammer/docs/pipeline_overview.md`
- `CloudHammer/docs/labeling_workflow.md`
- `CloudHammer/docs/api_prelabel_workflow.md`

The live API prelabel run writes under `CloudHammer/data/`; if that run is in
progress, treat those API folders as active runtime state and do not move or
edit them.

### Backend workspace and export flow

Scan a workspace:

```powershell
python -m backend scan revision_sets workspace
```

Run the current web review UI:

```powershell
python -m backend serve workspace --port 5000
```

Export approved results:

```powershell
python -m backend export workspace
```

If attention items are still pending, export is blocked by default. To allow an interim export anyway:

```powershell
python -m backend export workspace --force-attention
```

Exports include:

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

## Notes

- The old API-backed verification helper is archived. Human review is the active path until CloudHammer inference is reattached to the review queue.
- `revision_sets/` still lives at the repo root for compatibility. The future target is `resources/revision_sets/`, but the path migration is staged.
- Do not touch active CloudHammer API output folders while a prelabel run is in progress.

## Tests

```powershell
python -m pytest -q
```
