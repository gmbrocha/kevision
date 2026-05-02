# CloudHammer_v2

CloudHammer_v2 is the active eval-pivot workspace.

The immediate purpose of this workspace is to establish a clean evaluation-first
path for CloudHammer v2 before more model training or synthetic data generation.

## Workspace Rules

- Existing `CloudHammer/` is legacy/reference only.
- Do not modify, delete, rename, or reorganize existing folders yet.
- Do not copy old scripts yet.
- Do not move existing data.
- Only import old code after audit.
- Track every import from old `CloudHammer/` in `IMPORT_LOG.md`.
- Make no functional code changes here until the eval-pivot scaffolding and
  audit path are explicit.

## Current Priority

1. Build the touched-page registry and freeze guards.
2. Freeze `page_disjoint_real` full-page eval.
3. Generate GPT-provisional full-page labels.
4. Produce overlays/contact sheets for human audit.
5. Run baseline eval for `model_only_tiled` and `pipeline_full`.
6. Implement synthetic diagnostics only after the real eval baseline exists.
