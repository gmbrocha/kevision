# Pre-Handoff Polish Checklist

Status: durable review record for final ScopeLedger polish checks.

Screenshots and browser notes are context only. Record the actual review
decision in this checklist so follow-up work has a durable source of truth.

Allowed statuses: `ok`, `needs_fix`, `defer`, `blocked`.

Current stabilization note: this docs pass does not mark any route reviewed.
Fill the table during an actual browser review. If no populated project is
available, mark data-dependent routes `blocked` with the reason instead of
leaving the route outcome implied by screenshots.

| Route / Screen | Review Focus | Status | Reviewer | Date | Notes | Follow-up |
| --- | --- | --- | --- | --- | --- | --- |
| `/projects` | Project list, selected project row, archive/delete controls, create-project form, delete confirmation dialog. |  |  |  |  |  |
| `/overview` | Stat row, Populate status, package run history, import and append upload forms, staged-package table, revision-package table. |  |  |  |  |  |
| `/changes` | Search/status filters, package filters, attention callout, bulk review status, change table, selected rows. |  |  |  |  |  |
| `/changes/<change_id>` | Image evidence, Pre Review selection, legend context, crop adjustment controls, geometry correction controls, accept/reject actions, keyboard navigation footer. |  |  |  |  |  |
| `/sheets` | Drawing filters, active/superseded rows, index-match indicators. |  |  |  |  |  |
| `/sheets/<sheet_version_id>` | Full-sheet image, overlay boxes, version chain, sheet change list. |  |  |  |  |  |
| `/conformed` | Latest Set thumbnail grid, revised/latest flags, sheet metadata. |  |  |  |  |  |
| `/export` | Review status, generated output rows, attention override, generation buttons, export history. |  |  |  |  |  |
| `/settings` | Secondary settings/audit surface if exposed in the current build. |  |  |  |  |  |

## Review Rules

- Mark `needs_fix` only when the issue should block handoff or active-dev
  acceptance.
- Mark `defer` when the issue is real but should not block the current handoff.
- Mark `blocked` when the route cannot be reviewed because required project
  state, screenshots, or app service access is missing.
