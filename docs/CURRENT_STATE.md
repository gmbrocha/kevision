# Current State

Last updated: 2026-06-07

## Summary

ScopeLedger is an application for turning drawing revision packages into reviewable, client-facing change evidence and deliverables. The repository includes the application layer plus `CloudHammer_v2`, the active revision-cloud detection/eval/training subsystem.

## Current Status

Active development is on `main` in this repository. The current application priority remains the private client handoff path: keep the frozen Kevin handoff service stable, use this main repo for local development, and continue from `/projects` for fresh project creation, upload/import, Populate, review, and export smoke checks.

CloudHammer_v2 training/eval work is paused during the handoff pass and should resume at the documented crop-precheck return point after handoff work.

This file is now the Command Center project pulse. The previous long-form current-state record is preserved at `docs/archive/docs_archive_2026_06_07/docs_folder/CURRENT_STATE.md`.

## Blockers

- Private handoff readiness still depends on a clean fresh-project populate/review smoke.
- CloudHammer_v2 training remains paused at the crop-precheck return point with `4` non-accepted GPT-5.5 crop-precheck rows to resolve or accept before choosing the next pipeline-consumption or training step.
- Candidate pool manifests still need report-first definition/generation without changing frozen eval truth, training data, mining inputs, or synthetic outputs.

## Current Decisions

- `CloudHammer_v2/` is the active eval-pivot workspace; `CloudHammer/` is legacy/reference unless explicitly audited and imported.
- The frozen Kevin/client handoff clone is separate from active development. The handoff clone uses port `5000`; this active repo normally uses port `5001` for local development.
- Command Center reads `.project-command/project.json` for project metadata and `docs/CURRENT_STATE.md` as the project pulse. Command Center is read-only; project agents or the user update repo files when instructed.
- Frozen real eval pages must not enter training, crop extraction, hard-negative mining, synthetic backgrounds, threshold tuning, GPT/model relabel loops, or future mining.

## Assumptions

- The repository-derived Command Center manifest id is `scopeledger`.
- The source-grounded Command Center category is `front-row` because current docs describe an active private client handoff.
- The source-grounded Command Center status is `active` because current docs describe active development and handoff work.
- `priorityRank` is unverified and intentionally unset in the provisional manifest.

## Known Gaps

- Command Center's final manifest schema is not implemented yet; the current manifest is provisional V1 metadata and will need review when the final schema lands.
- Service control is source-grounded only for the active local development service in this repo. The frozen Kevin handoff service is documented as a separate clone and is not modeled as a controllable service for this workspace.
- The previous long-form state had accumulated detailed history; future durable history should live in `docs/DECISIONS.md`, `docs/history/`, or archived docs rather than expanding this pulse file.

## Next Actions

- Use `docs/NEXT_ACTIONS.md` for the active operational queue.
- Keep Kevin's frozen handoff clone on port `5000` healthy through Dev Switchboard before client use; use this main repo on port `5001` for active development.
- Complete a clean fresh-project populate/review smoke from `/projects`.
- After handoff work, resume CloudHammer_v2 at the crop-precheck blocker documented in `CloudHammer_v2/docs/CURRENT_STATE.md`.

## Recent Activity

- 2026-06-07: Metadata-only Command Center setup pass created the provisional project manifest, converted this file to the Command Center pulse structure, archived the previous long-form current state, and added current-state sync guidance for agents.

## Service Notes

- Active dev service: `.\scopeledger.ps1 start -Port 5001`, health URL `http://127.0.0.1:5001/projects`, logs under `logs/scopeledger_backend.*.log`.
- Frozen handoff service: separate clone on port `5000` behind `https://ledger.nezcoupe.net`; do not use `-Cloudflare` or `-All` for this active dev repo unless explicitly instructed.
