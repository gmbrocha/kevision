# UI Visual Review Routes

Use this checklist after visual styling changes. It is not a pixel-perfect
regression test; it is a route list for screenshot capture or manual review.

## Setup

- Working directory: repo root.
- Preferred check: run the optional browser smoke tests with
  `.\.venv\Scripts\python.exe -m pytest tests\test_smoke_playwright.py -q`.
- For manual review, run `.\.venv\Scripts\python.exe -m backend serve --host 127.0.0.1 --port 5000` and review the active local project.

## Screenshot Artifacts

There is no committed pixel-regression or screenshot-capture helper for this
app yet. Keep the automated check to the existing Playwright smoke tests. When
visual comparison artifacts are useful, capture the routes below into an
ignored `test_tmp/ui_rectangle_reduction_<date>/` folder and record any
accept/rework notes alongside the pass audit rather than adding pixel-perfect
assertions.

## Route List

- `/projects`: project list, selected project row, archive/delete controls,
  create-project form, delete confirmation dialog.
- `/overview`: hero, stat row, Populate status, package run history, import and
  append upload forms, staged-package table, revision-package table.
- `/changes`: search/status filters, package filters, attention callout, bulk
  review status, change table, selected rows.
- `/changes/<change_id>`: image evidence, Pre Review selection, legend context,
  crop adjustment controls, geometry correction controls, accept/reject actions,
  keyboard navigation footer.
- `/sheets`: drawing filters, active/superseded rows, index-match indicators.
- `/sheets/<sheet_version_id>`: full-sheet image, overlay boxes, version chain,
  sheet change list.
- `/conformed`: Latest Set thumbnail grid, revised/latest flags, sheet metadata.
- `/export`: review status, generated output rows, attention override,
  generation buttons, export history.
- `/diagnostics`: parser warning callout, summary stats, ingested PDF table,
  issue summary table.
- `/settings`: secondary settings/audit surface if exposed in the current build.

## Review Criteria

- The screen should have fewer nested boxed regions than before.
- Review decisions, warnings, selected states, and active filters must remain
  obvious.
- Dense operational tables should stay readable without double borders.
- Blueprint evidence and overlays should remain visually dominant on review and
  sheet-detail screens.
- Text must not overlap, truncate unexpectedly, or become ambiguous at
  1280x900 and a narrow mobile-width viewport.
