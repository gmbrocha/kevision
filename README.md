# ScopeLedger

ScopeLedger is an application for turning drawing revision packages into
reviewable, client-facing change evidence and deliverables.

The project currently has two layers:

- the application layer: backend scan/export workflow, webapp/review surfaces,
  client workflow, resources, and deliverable shaping
- the detection subsystem: `CloudHammer_v2`, which owns revision-cloud
  detection, eval, labeling, and training policy

`CloudHammer_v2/` is the active eval-pivot workspace. The older `CloudHammer/`
folder is legacy/reference only unless code is explicitly audited and imported.

## Read First

1. `docs/CURRENT_STATE.md`
2. `ROADMAP.md`
3. `docs/ARCHITECTURE.md`
4. `docs/MODULES.md`
5. `docs/DECISIONS.md`
6. `CloudHammer_v2/README.md`

## Canonical Docs

- `PRODUCT_AND_DELIVERY.md`: product and deliverable intent
- `ROADMAP.md`: current sequence and milestones
- `FINDINGS_FIRST_REAL_RUN.md`: first real app-run observations and follow-up
  triage; not reviewed labels or training data
- `docs/`: application architecture, data flow, security, runbook, decisions,
  deployment, and client workflow
- `docs/references/`: non-canonical reference artifacts such as walkthroughs,
  templates, spreadsheets, and PDFs
- `CloudHammer_v2/docs/`: detection/eval/training subsystem docs

Documentation history lives under `docs/archive/`. The root `archive/` folder
is reserved for old scripts, experiments, outputs, and implementation artifacts.

## CloudHammer Subsystem

CloudHammer_v2 is the active revision-cloud detection subsystem.

- Active workspace: `CloudHammer_v2/`
- Pivot plan: `CloudHammer_v2/PIVOT_PLAN.md`
- Current subsystem state: `CloudHammer_v2/docs/CURRENT_STATE.md`
- Eval policy: `CloudHammer_v2/docs/EVAL_POLICY.md`
- Model-vs-pipeline audit: `CloudHammer_v2/docs/MODEL_VS_PIPELINE_AUDIT.md`
- Synthetic grammar: `CloudHammer_v2/docs/SYNTHETIC_CLOUD_GRAMMAR_V1.md`

The existing `CloudHammer/` folder is legacy/reference unless explicitly
audited and imported into `CloudHammer_v2`.

CloudHammer_v2 owns revision-cloud detection, eval, labeling, and
model-training policy. The application layer owns client workflow,
backend/webapp integration, deliverable shaping, deployment, and product
decisions.
