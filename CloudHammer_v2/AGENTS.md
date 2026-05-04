# CloudHammer_v2 AGENTS.md

## Scope

This directory is the active eval-pivot workspace for CloudHammer.

Work here should focus on:

- model-vs-pipeline audit
- touched-page registry
- frozen eval subsets
- GPT-assisted labeling policy/workflows
- YOLOv8 model-only tiled eval
- full pipeline eval
- synthetic cloud grammar/specs

Do not implement unrelated application backend, webapp, deployment, invoicing, or client UI work from this directory.

## Required Reading

Before CloudHammer_v2 work, read:

1. `README.md`
2. `PIVOT_PLAN.md`
3. `docs/CURRENT_STATE.md`
4. `docs/EVAL_POLICY.md`
5. `docs/DECISIONS.md`
6. `docs/MODEL_VS_PIPELINE_AUDIT.md`

## Legacy Import Rules

The old `../CloudHammer/` directory is legacy/reference.

Do not copy old scripts wholesale.

Before importing old code, identify:

- old path
- new path
- reason for import
- whether it is copied unchanged or modified
- dependencies
- risks

Record imports in `IMPORT_LOG.md`.

## Eval Safety

Frozen real eval pages are sacred.

Never use frozen real eval pages for:

- training
- crop extraction
- hard-negative mining
- synthetic backgrounds
- threshold tuning
- GPT/model relabel loops
- future mining

Full-page eval labels are the source of truth.

Inference may tile/crop pages, but scoring must map predictions back to full-page coordinates.

## Synthetic Rules

Do not implement full synthetic generation until the real full-page eval baseline exists.

For now, synthetic work is limited to grammar/spec stubs unless explicitly instructed.

Synthetic diagnostic metrics must remain separate from real eval metrics.

## Final Response Format

End with:

- Changed files
- Tests/checks run
- Eval contamination risk check
- Recommended follow-up

## Standard Workflow Automation

For any non-trivial task, follow this workflow:

1. Read the required docs listed in this file before editing.
2. Keep the task scoped to the user request.
3. Make the smallest useful change.
4. Do not fix unrelated issues automatically.
5. Report unrelated findings under “Recommended follow-up.”
6. Update project state docs when the task changes current status, next steps, risks, or decisions.
7. End with the standard final report format.

## Required Final Report

Every task response must end with:

- Changed files
- Tests/checks run
- Risks or unresolved questions
- Recommended follow-up

If no files changed, say so.

If no tests/checks were run, say why.

Do not claim tests passed unless they were actually run.

## Documentation State Updates

After meaningful changes, update the appropriate state docs.

Update root-level docs when the change affects the broader application/product:

- `docs/CURRENT_STATE.md`
- `docs/DECISIONS.md`
- `docs/RUNBOOK.md` if commands/workflows changed

Update CloudHammer_v2 docs when the change affects detection, eval, training, labeling, model/pipeline behavior, or synthetic diagnostics:

- `CloudHammer_v2/docs/CURRENT_STATE.md`
- `CloudHammer_v2/docs/DECISIONS.md`
- `CloudHammer_v2/docs/RUNBOOK.md` if commands/workflows changed
- `CloudHammer_v2/IMPORT_LOG.md` if anything is imported from legacy CloudHammer

Do not rewrite state docs for trivial formatting-only changes.

## Decision Log Rules

When a task makes or implements a project-level decision, add an entry to the relevant `DECISIONS.md`.

Each entry should include:

- Date
- Decision
- Reason
- Consequences / follow-up

Keep entries concise.

## Current State Rules

`CURRENT_STATE.md` should remain short and operational.

Update it when any of these change:

- active branch/workspace
- current priority
- frozen/not-frozen status
- eval status
- training status
- known blockers
- immediate next step
- important “do not touch” warnings

Do not turn `CURRENT_STATE.md` into a long history file. Put history in `DECISIONS.md` or archived docs.

## Runbook Rules

Only add commands to `RUNBOOK.md` if they are verified or clearly marked as TODO/unverified.

For each command, include:

- purpose
- working directory
- command
- expected output/artifact
- whether it is safe, dry-run, or destructive/expensive

Never invent commands.

## Report-Only Mode

For tasks involving scary or high-impact areas, prefer a report-only pass first unless the user explicitly asks to implement.

High-impact areas include:

- datasets
- model checkpoints
- training runs
- frozen eval pages
- source drawing packages
- bulk file moves
- legacy CloudHammer imports
- dependency changes
- deployment/security changes

In report-only mode:

- inspect and summarize
- list candidate files/actions
- recommend next steps
- do not modify files

## Dry-Run First Rules

For scripts or workflows that affect datasets, eval manifests, frozen pages, synthetic data, labels, or model outputs:

- implement a dry-run option where practical
- run dry-run before real execution
- report what would change
- do not execute destructive or expensive actions unless explicitly requested

## Selection Before Copying

Before copying, freezing, moving, or generating datasets/eval pages at scale:

1. Create a selection/candidate file first.
2. Include inclusion/exclusion reasons.
3. Report the candidate selection.
4. Wait for approval unless the user explicitly authorized execution.

Examples:

- candidate page_disjoint_real selection
- touched-page registry candidates
- hard-negative mining candidates
- synthetic diagnostic background candidates

## Import Discipline

Do not copy legacy code wholesale.

Before importing from legacy `CloudHammer/`, identify:

- old path
- new path
- why it is needed
- whether it will be copied unchanged or modified
- dependencies
- risks

After importing, update `CloudHammer_v2/IMPORT_LOG.md`.

## Naming Discipline

Use stable canonical names.

Do not invent alternate names for established concepts.

Canonical eval subset names:

- `page_disjoint_real`
- `gold_source_family_clean_real`
- `synthetic_diagnostic`

Canonical eval modes:

- `model_only_tiled`
- `pipeline_full`

Canonical workspace:

- `CloudHammer_v2`

If a new name is needed, add it to the relevant docs and use it consistently.

## Related Issue Handling

If related problems are discovered during a task:

- do not fix them unless required for the task
- list them under “Recommended follow-up”
- include file paths and why they matter
- identify whether they are blocking or optional

and extra goblins on the side.

## Fresh Session Check

Before starting high-risk or high-context work, pause and ask the user whether they want to start a fresh agent session.

High-risk/high-context work includes:

- touched-page registry changes
- eval selection or freezing
- GPT labeling runs
- label conversion or label promotion
- model-vs-pipeline evaluation
- training or retraining
- importing legacy CloudHammer code
- moving datasets, model runs, generated outputs, or revision sets
- modifying security/deployment behavior
- bulk cleanup or archive moves
- any task that relies on subtle distinctions between touched, reviewed, training, validation, eval, synthetic, or frozen data

Use this wording:

“Before I proceed: this is a high-risk/high-context task. Do you want to start a fresh agent session and have me re-read the canonical docs first?”

If the user says continue, proceed with extra caution and restate the key assumptions before making changes.

Do not ask this for minor documentation edits, typo fixes, report summaries, or non-destructive read-only inspections unless the context appears stale or ambiguous.

When in doubt, fresh session beats compacted context for eval, labels, data, training, or legacy imports.