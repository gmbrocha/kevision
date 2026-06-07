# Current State

Last updated: 2026-06-07

## Summary

ScopeLedger turns drawing revision packages into reviewable change evidence and
client-facing deliverables. The repository contains the application layer plus
the `CloudHammer_v2` detection/eval/training-policy subsystem. `CloudHammer/`
is legacy/reference unless explicitly audited and imported.

## Current Status

- Active branch/workspace observed for this setup pass: `kevin-handoff` at the
  repo root.
- Current application priority remains the private client handoff: create a
  fresh project from `/projects`, stage revision-package PDFs, run Populate,
  and verify review/export surfaces behind Cloudflare Access.
- The app registry is local ignored state under `app_workspaces/`; empty
  registry state is valid and `/projects` is the expected first screen.
- Immediate handoff hosting uses `ledger.nezcoupe.net` through Cloudflare
  Tunnel to `http://localhost:5000`, with Cloudflare Access as the auth gate.
- CloudHammer_v2 training/eval work remains paused for client handoff work and
  should resume afterward at the documented crop-precheck return point.

## Blockers

- CloudHammer_v2 follow-up is blocked on resolving or accepting the four
  non-accepted GPT crop-precheck rows before deciding the next
  pipeline-consumption/training step.
- No Command Center schema is final yet; `.project-command/project.json` is a
  provisional V1 manifest.

## Current Decisions

- Command Center reads `.project-command/project.json` for source-grounded
  project metadata and `docs/CURRENT_STATE.md` as the project pulse.
- Command Center registration is manual from Settings by repository path; the
  manifest does not create registry membership.
- Command Center is read-only for this repository. The user or a project agent
  updates files, current-state docs, manifests, tasks, and git state.
- Frozen real eval pages remain eval-only and must not enter training, mining,
  synthetic backgrounds, tuning, GPT/model relabel loops, or future mining.

## Assumptions

- `front-row` is the appropriate Command Center category because the active
  priority is a private client handoff path.
- `active-client-handoff` is the current status label for Command Center
  metadata; this is source-grounded from roadmap/product/deployment docs but
  should be revisited when Command Center finalizes status vocabulary.
- Local app service metadata uses the documented repo-root commands and port
  `5000`; no additional service suite was inferred.

## Known Gaps

- Command Center's final manifest schema is not implemented yet.
- Broader rollout still needs background Populate jobs, durable process
  supervision, artifact retention/workspace cleanup policy, and app-level
  identity/session management beyond Cloudflare Access.
- First-pass OCR/context and symbol/legend interpretation remain active quality
  risks.
- `docs/archive/docs_archive_2026_06_07/CURRENT_STATE.before_command_center_v1.md`
  preserves the pre-Command Center long-form state snapshot.

## Next Actions

- Register the repo manually in Command Center from Settings using the
  repository path after reviewing the provisional manifest.
- For the next handoff smoke, create a fresh project from `/projects`, stage
  PDFs by browser upload or allowed import root, configure server-side Pre
  Review if needed, and run Populate.
- During the next populate/review smoke, verify index pages do not create
  review items, package revision filters behave correctly, and overlay boxes
  align with visible clouds.
- After client handoff work, resume CloudHammer_v2 at the crop-precheck return
  point documented in the archived long-form state and CloudHammer_v2 docs.

## Recent Activity

- 2026-06-07: Metadata-only Command Center setup pass created a provisional
  V1 manifest, restructured this current-state pulse, added project-agent sync
  guidance, and allowlisted the canonical Cursor project rule.

## Service Notes

- Local app serve command: `.\.venv\Scripts\python.exe -m backend serve --host 127.0.0.1 --port 5000`.
- Process helper: `.\scopeledger.ps1 check|start|stop|restart`; logs are written
  to `logs/scopeledger_backend.out.log` and
  `logs/scopeledger_backend.err.log`.
- Production handoff serve mode requires `SCOPELEDGER_WEBAPP_SECRET`, loopback
  binding, Cloudflare Access, and restricted manual import roots.
- Shared local prerequisite: `cloudflared` tunnel `nez-dev-projects` maps
  `ledger.nezcoupe.net` to `http://localhost:5000`.
