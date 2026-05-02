# CloudHammer_v2

CloudHammer_v2 is the active eval-pivot workspace for revision-cloud detection,
evaluation, labeling, and training policy.

Existing `CloudHammer/` is legacy/reference only. Do not import old scripts or
data into this workspace without audit, and record every import in
`IMPORT_LOG.md`.

## Read Order For Agents

1. `CloudHammer_v2/README.md`
2. `CloudHammer_v2/PIVOT_PLAN.md`
3. `CloudHammer_v2/docs/CURRENT_STATE.md`
4. `CloudHammer_v2/docs/EVAL_POLICY.md`
5. `CloudHammer_v2/docs/DECISIONS.md`

## Workspace Rules

- Build the real full-page eval ruler before more training.
- Compare `model_only_tiled` against `pipeline_full`.
- Keep real eval subsets separate from synthetic diagnostics.
- Do not copy old code until the relevant behavior is audited.
- Do not move existing datasets, model runs, or legacy artifacts.
- Do not implement synthetic generation until the real eval baseline exists.

## Folder Roles

- `docs/`: subsystem policy, audit, and runbook docs
- `configs/`: future eval/training configs
- `scripts/`: future audited v2 scripts
- `data/`: future v2 manifests and small metadata artifacts
- `models/`: future promoted v2 model references
- `eval/`: future frozen eval manifests and reports
- `outputs/`: future generated v2 outputs
