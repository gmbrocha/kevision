# App Audit - Legend Context Review

Date: 2026-05-11

Scope: code audit after adding the legend-context Populate/Review workflow.
This pass covered the new legend-context service plus adjacent Populate,
Pre Review, Review Changes, Drawings, review-event, export, review-packet, and
bulk-review paths.

## Findings Fixed

1. Pre Review cache keys changed for all items after adding legend context.

   Fix: preserve the prior cache key shape when an item has no resolved legend
   context. Legend context is included in the cache key only when it is present.

2. Superseded but unconfirmed probable legend parents could still act as
   provisional context sources.

   Fix: only visible probable legend rows or confirmed legend rows feed symbol
   context. Superseded unconfirmed rows are ignored.

3. Bandit flagged the token-boundary regex as a hardcoded-password false
   positive because it contains the word `token`.

   Fix: add a narrow `# nosec B105` on that regex constant.

## Verified Behavior

- Probable legend/keynote rows remain in the normal review queue.
- `Accept as legend` confirms the row, soft-hides it, records an internal
  `relabel` review event, and advances to the next pending item.
- Confirmed legend rows are excluded from normal queues, counts, Drawings
  overlays, workbook/pricing exports, and review packets.
- Resolved legend context is available to Pre Review as separate context and
  does not replace the original OCR text.
- Existing Pre Review cache files remain reusable for ordinary items that have
  no legend context.

## Checks

- `.\.venv\Scripts\python.exe -m pytest tests\test_app.py -q -k "legend_context or accept_as_legend or confirmed_legend or pre_review_one_carries or superseded_unconfirmed or cache"`
- `.\.venv\Scripts\python.exe -m compileall -q backend webapp`
- `.\.venv\Scripts\python.exe -m bandit -q -r backend webapp`
- `node --check webapp\static\app.js`

The full repository test suite is still required before release commit.
