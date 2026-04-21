# Revision Review Tool

Local Flask app for scanning drawing revision PDFs, building a review workspace, and exporting approved results.

## Install

```powershell
python -m pip install -r requirements.txt
```

## Scan a Workspace

```powershell
python -m revision_tool scan revision_sets workspace
```

This creates:

- `workspace/workspace.json`
- `workspace/assets/pages/*.png`
- `workspace/assets/crops/*.png`
- persisted preflight diagnostics for PDF integrity issues
- `workspace/outputs/` after export

Re-running `scan` against the same workspace now reuses unchanged PDFs from a persisted cache and preserves existing review decisions for unchanged change items.

## Run the GUI

```powershell
python -m revision_tool serve workspace --port 5000
```

Open `http://127.0.0.1:5000`.

The GUI includes:

- a `Diagnostics` view that summarizes malformed-PDF warnings by file and page
- a filtered review queue with search, bulk approve/reject, and keyboard shortcuts
- next-item navigation on each change record
- an attention-only queue for weak visual extractions or missing detail refs
- optional manual AI verification for confusing items

## Export Approved Results

```powershell
python -m revision_tool export workspace
```

If attention items are still pending, export is blocked by default. To allow an interim export anyway:

```powershell
python -m revision_tool export workspace --force-attention
```

Exports include:

- `kevin_changelog.xlsx` — Kevin-shaped Excel deliverable (one row per cloud/detail with embedded crops; layout reverse-engineered from `mod_5_changelog.xlsx`, schema in `docs/kevin_changelog_format.md`)
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

`conformed_preview.pdf` is assembled from rendered page images rather than direct PDF page imports. This is intentional: it avoids brittle xref/object issues in malformed source PDFs and makes preview export more reliable.

The scanner also uses PDF text first and falls back to local OCR on weak review crops when Tesseract is available.

## Optional AI Verification

The app works without model access.

To enable manual verification buttons in the GUI:

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_VERIFY_MODEL = "gpt-4.1-mini"
python -m revision_tool serve workspace
```

AI output is advisory only and is stored in the workspace audit history.

## Tests

```powershell
python -m pytest -q
```
