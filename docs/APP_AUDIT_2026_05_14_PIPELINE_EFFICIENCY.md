# App Audit: Pipeline Correctness And Efficiency

Date: 2026-05-14

Scope: ScopeLedger app pipeline, review flow, package/revision carry-forward,
exports, populate status, and processing efficiency. This pass excludes
CloudHammer_v2 eval/training policy changes and source revision package
movement.

## Immediate Findings

### Revision changelog can merge independent revision-scope rows

`backend/deliverables/revision_changelog_excel.py` groups approved workbook
rows by sheet number plus detail/cloud reference. That can collapse Revision 1
`AE101` Detail 1 and Revision 2 `AE101` Detail 1 into one output row even
though review items are now revision-scope records.

Fix: include `sheet_version_id` in the changelog grouping key while keeping
approved/rejected/superseded visibility rules unchanged.

### Pre Review builds expensive context before knowing it is needed

`backend/pre_review.py` creates every `PreReviewContext` before checking
whether Pre Review 2 already exists, whether the provider is disabled, or
whether the item will be skipped. Context construction opens crop images and
builds overlay metadata, so cached/inactive runs still pay avoidable I/O.

Fix: build Pre Review context lazily only for items that need a provider call.
Use the existing first-pass fallback for skipped/disabled items.

### Single-item Pre Review request counts can be overreported

The single-item provider path increments request count once per result and
then again for the flushed request. Usage logs remain correct, but progress
status can show inflated request counts.

Fix: count one provider request per flush that actually made a non-cache call.

### Populate polling omits keynote progress fields

The Overview template exposes keynote registry and expansion counts, but
`webapp/static/app.js` does not update those fields during live polling.

Fix: update keynote registry sheet count, definition count, and expanded item
count in the live populate status renderer.

### Review start link can drop active filters

`Review Changes` computes `first_pending` inside the current composed filter,
but the `Start reviewing` link preserves only package scope. Search and
needs-check filters can be lost when entering detail review.

Fix: preserve `q` and `attention` when building the start-review URL.

### Scope text extraction repeats page text work per cloud

`extract_cloud_scope_text()` calls `page.get_text("words")` for each cloud.
Both scanner detection and workspace enrichment can process many clouds on the
same page, making this repeated PDF text extraction a clear cost multiplier.

Fix: allow callers to pass precomputed page words and reuse them for all clouds
on the same page.

### Populate status scans every artifact into a list on each poll

`summarize_populate_artifacts()` builds a full list of files under the active
CloudHammer run directory every few seconds. Large run folders make this more
expensive than necessary.

Fix: stream-count files and latest mtime without retaining a full list.

### Generated diagnostic output is not ignored

Standalone utilities write outputs under `test_tmp/`, but that directory is not
currently ignored. This leaves large generated audit/viewer artifacts as
untracked noise.

Fix: add `test_tmp/` to `.gitignore`.

## Deferred Efficiency Opportunities

- Cache revision/sheet context maps inside export flows so large exports do
  not rebuild identical maps per row.
- Avoid recomputing pricing/export row collections multiple times inside one
  export request.
- Add a lightweight populate-status cache keyed by run directory and mtime if
  live artifact polling still becomes visible in profiles.
- Add package processing attempt history later if current-state rows are not
  enough for operations/audit.

## Planned Verification

- Add regression coverage for revision-scoped workbook grouping.
- Add regression coverage for lazy Pre Review context reuse and single-request
  count accuracy.
- Run `python -m compileall backend webapp utils -q`.
- Run `python -m pytest tests/test_app.py -q`.
