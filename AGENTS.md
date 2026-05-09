# AGENTS.md

## Repo Operating Rules

This repository contains a larger application plus the CloudHammer detection subsystem. Do not treat any one folder as the whole product unless the task explicitly says so.

Before making project-level changes, read:

1. `README.md`
2. `docs/CURRENT_STATE.md`
3. `docs/ARCHITECTURE.md`
4. `docs/MODULES.md`
5. `docs/DECISIONS.md`

For CloudHammer-specific work, also read:

1. `CloudHammer_v2/README.md`
2. `CloudHammer_v2/PIVOT_PLAN.md`
3. `CloudHammer_v2/docs/CURRENT_STATE.md`
4. `CloudHammer_v2/docs/EVAL_POLICY.md`
5. `CloudHammer_v2/docs/DECISIONS.md`

## Scope Control

Do only the requested task.

Do not perform broad cleanup, refactors, migrations, renames, formatting passes, dependency upgrades, or architecture changes unless explicitly requested.

If you discover related problems, report them under "Recommended follow-up"
instead of fixing them automatically.

Prefer small, reviewable changes.

## Repository Boundaries

`CloudHammer_v2/` is the active eval-pivot workspace for revision-cloud detection.

`CloudHammer/` is legacy/reference unless the task explicitly says to import from it.

Do not modify, delete, rename, or reorganize legacy folders unless explicitly instructed.

Do not move datasets, model runs, client resources, generated outputs, or revision sets unless explicitly instructed.

## Documentation Rules

Flat Markdown files in the repo are the canonical project documentation.

Root docs describe the overall application/product.

`CloudHammer_v2/docs/` describes only the CloudHammer detection/eval/training subsystem.

Non-canonical reference artifacts belong in `docs/references/`. Raw meeting
notes belong in `docs/meetings/`; historical notes belong in `docs/history/`.

Documentation archives belong under:

`docs/archive/docs_archive_YYYY_MM_DD/`

Do not put documentation archives in root `archive/`. Root `archive/` is for old scripts, experiments, outputs, and implementation artifacts.

When replacing or superseding docs, preserve the old version in the dated docs archive. Do not delete old docs.

## CloudHammer Eval Rules

Frozen real eval pages must never enter training, crop extraction, hard-negative mining, synthetic backgrounds, threshold tuning, GPT/model relabel loops, or future mining.

Do not blend eval subset scores. Report separately for:

- `page_disjoint_real`
- `gold_source_family_clean_real`
- `style_balance_diagnostic_real_touched`
- `synthetic_diagnostic`

Synthetic diagnostics are not proof of real-world performance.

## Coding Rules

Do not invent commands. Use documented commands or inspect the repo.

Do not claim tests passed unless you ran them.

If tests cannot be run, explain why and list what was checked instead.

Prefer adding small purpose-specific scripts over modifying broad legacy scripts.

## Final Response Format

End with:

- Changed files
- Tests/checks run
- Risks or unresolved questions
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

## Review Workflow Rules

Do not recommend passive visual review as a standalone next step.

Any task described as review, audit, triage, spot-check, or human look-over
must have a system that can persist the review result before it blocks later
work. At minimum, provide one of:

- an editable manifest, CSV, JSONL, label file, or review log with explicit
  allowed decisions
- a viewer or app control that writes those decisions to a separate review
  artifact
- a report-only protocol that names the exact decisions to record and where
  they will be stored next

Review systems must make it possible to change labels, candidate metadata,
decisions, or notes when that is the point of the review. If direct mutation is
too risky, write a separate review artifact first and feed it into a dry-run or
apply step later.

Screenshots, static viewers, overlays, and "look this over" instructions are
context only. They are not a completed review unless paired with a durable
decision record.

## Visual Evidence Rule

Any viewer, review packet, contact sheet, or inspection artifact prepared for a
human reviewer must show the visual target of the decision directly on the
image. For detection or geometry work, this means rendered overlays for the
candidate bbox, truth bbox, prediction bbox, crop boundary, or other relevant
decision target. Raw crops or page images alone are not acceptable review
evidence unless the task is explicitly about the raw image itself.

If a review item cannot show its visual target, mark it blocked or missing
evidence in the durable review artifact instead of asking for human review.

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
- `style_balance_diagnostic_real_touched`
- `synthetic_diagnostic`

Canonical candidate pool names:

- `full_page_review_candidates_from_touched`
- `mining_safe_hard_negative_candidates`
- `synthetic_background_candidates`
- `future_training_expansion_candidates`

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

## High-Risk Session And Reasoning Check

Default reasoning may be medium. Do not assume medium reasoning or the current
session context is sufficient for high-risk/high-context work.

Before starting high-risk/high-context work, pause and ask the user whether they
want to:

1. start a fresh agent session and re-read the canonical docs,
2. increase reasoning effort for the task,
3. run report-only or dry-run first.

High-risk/high-context work includes:

- touched-page registry changes or touched-policy changes
- eval selection or freezing
- GPT labeling runs
- label conversion or label promotion
- training manifest generation
- train/val split changes
- model-vs-pipeline evaluation or scoring-logic changes
- model training or retraining
- importing legacy CloudHammer code
- moving datasets, model runs, generated outputs, or revision sets
- synthetic generation implementation
- modifying security/deployment behavior
- bulk cleanup or archive moves
- any task that relies on subtle distinctions between touched, reviewed,
  training, validation, eval, synthetic, frozen, or provisional data

Use this wording:

“Before I proceed: this is a high-risk/high-context task. Do you want to start a fresh session, increase reasoning effort, or run a report-only/dry-run pass first?”

If the user says continue, proceed with extra caution and restate the key
assumptions before making changes.

Do not ask this for minor documentation edits, typo fixes, report summaries, or
read-only inspections unless context appears stale or ambiguous.
