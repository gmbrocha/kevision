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
- Do not implement synthetic generation until the human-audited baseline,
  mismatch review, postprocessing findings, and candidate pools are trustworthy
  enough to steer diagnostics.
- Before presenting repetitive review queues, report queue size and estimated
  burden, then ask whether GPT-5.5 should prefill provisional decisions first.

## Folder Roles

- `docs/`: subsystem policy, audit, state, reports, and runbook docs
- `configs/`: eval/training configs and audited workflow configs
- `scripts/`: purpose-specific v2 scripts and audited helpers
- `data/`: v2 manifests and small metadata artifacts
- `models/`: promoted v2 model references when a model is promoted
- `eval/`: frozen eval manifests, review queues, and eval reports
- `outputs/`: generated v2 diagnostics, reports, and review artifacts
