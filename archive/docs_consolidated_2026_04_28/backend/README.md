# Backend

The `backend/` package owns product orchestration and deliverables.

It includes:

- revision-state models and scanning
- workspace persistence
- diagnostics capture
- drawing-index parsing
- export generation
- the integration seam where CloudHammer detections will plug into the product

Related docs:

- `../docs/README.md`
- `../docs/architecture.md`
- `../docs/revision_changelog_format.md`

Entry point:

```powershell
python -m backend --help
```
