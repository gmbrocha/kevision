# CloudHammer

Superseded for active work by `CloudHammer_v2/` as of 2026-05-02. Preserved at
this root path as the application-level pointer to the cloud detection
subsystem.

## Current Source of Truth

- Active workspace: `CloudHammer_v2/`
- Pivot plan: `CloudHammer_v2/PIVOT_PLAN.md`
- Current subsystem state: `CloudHammer_v2/docs/CURRENT_STATE.md`
- Eval policy: `CloudHammer_v2/docs/EVAL_POLICY.md`
- Model-vs-pipeline audit: `CloudHammer_v2/docs/MODEL_VS_PIPELINE_AUDIT.md`
- Synthetic grammar: `CloudHammer_v2/docs/SYNTHETIC_CLOUD_GRAMMAR_V1.md`

## Legacy Folder Policy

The existing `CloudHammer/` folder is legacy/reference unless explicitly
audited and imported into `CloudHammer_v2`.

Do not:

- delete or reorganize old `CloudHammer/`
- copy old scripts into `CloudHammer_v2` without audit
- move existing data or model runs
- treat generated legacy run summaries as canonical product docs

Any import from old `CloudHammer/` must be logged in
`CloudHammer_v2/IMPORT_LOG.md`.

## Role in ScopeLedger

CloudHammer_v2 is a subsystem/dependency of ScopeLedger. It owns revision-cloud
detection, eval, labeling, and model-training policy. The application layer owns
client workflow, backend/webapp integration, deliverable shaping, deployment,
and product decisions.
