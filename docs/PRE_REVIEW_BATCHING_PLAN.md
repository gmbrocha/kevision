# Pre Review Batching Plan

Status: implemented on 2026-05-11 for the app-layer Pre Review path.

## Summary

Reduce Pre Review request overhead by batching multiple review items into each
API call while preserving per-item cache files, per-item validation, and the
existing reviewer workflow. This is an app-layer optimization only. It does not
change CloudHammer candidates, review items, review-event capture, or export
truth selection.

Default behavior should be batch size `5`, configurable with
`SCOPELEDGER_PREREVIEW_BATCH_SIZE`. Batch size `1` should keep current
single-item behavior.

Implementation notes:

- `SCOPELEDGER_PREREVIEW_BATCH_SIZE` defaults to `5`, accepts `1`, and clamps
  larger values to `10`.
- Existing single-item cache files remain readable and are reused before new
  batch requests are made.
- New batch cache writes use prompt version
  `scopeledger_pre_review_batch_prompt_v1`.
- Per-call API usage is logged as JSONL under each project at
  `outputs/pre_review/usage/pre_review_usage.jsonl`.
- Live Populate status tracks completed Pre Review count, failures, cache hits,
  API request count, batch size, and token totals for internal inspection.
- The Overview UI shows only compact `Pre Review` progress, failures, and cache
  hits. It does not expose model/vendor, cost, token, training, eval, or
  labeling language.

## Key Changes

- Extend the Pre Review provider interface with batch support.
  - Add `review_batch(contexts)` returning results keyed by `item_id`.
  - Keep `review(context)` for compatibility with fake providers and
    single-item mode.
  - Batch only uncached, valid visual review items.
  - Keep the existing per-item cache as the canonical cache format.

- Add OpenAI batch requests.
  - Send up to `5` candidate overlay images per request by default.
  - Return a strict `results[]` JSON object keyed by `item_id`.
  - Validate that returned IDs match requested items with no duplicates.
  - Normalize each row through the existing per-item normalization path.
  - Missing, duplicate, unknown, invalid, or malformed rows should fail only
    that item.
  - If a whole batch request fails after retries, mark each item in that batch
    failed and continue to the next batch.

- Preserve cache and retry safety.
  - Load existing per-item cache files before batching.
  - Support current single-item cache files so interrupted runs are reusable.
  - Write each successful batch result as its own per-item cache JSON.
  - Keep per-item API input overlay PNGs for debugging.
  - Use a new batch prompt version for new writes while preserving read
    compatibility with current cache files.

- Add API usage and cost telemetry.
  - Capture response `usage` for every API request, including prompt/input
    tokens, cached input tokens when reported, output tokens, total tokens, and
    model name.
  - For batch requests, allocate request-level usage back to each returned
    `item_id` using a simple proportional default and keep the raw batch usage
    record for audit.
  - Store usage metadata in each per-item cache JSON and in a run-level JSONL
    file under `outputs/pre_review/usage/`.
  - Include request start/end timestamps, duration, retry count, batch size,
    cache hit status, and failure reason when available.
  - Do not expose usage, model/vendor names, cost, or token terminology in the
    client-facing UI.

- Add live Pre Review progress status.
  - Track completed, total, failed, cache hits, and batch size.
  - Track API request count and token/cost totals in `populate_status` for
    internal inspection only.
  - Update `workspace.populate_status` after each batch.
  - Save completed item provenance after each completed batch so an interrupted
    run preserves completed metadata.
  - Keep client-facing status wording generic: `Running pre-review on detected
    regions`.

- Update the Overview status UI.
  - Show compact Pre Review progress, such as `Pre Review 19 / 192`.
  - Show failures and cache hits.
  - Do not expose `GPT`, `CloudHammer`, `training`, `eval`, or `labeling`
    language in the UI.

## Response Shape

Batch responses should use this logical shape:

```json
{
  "results": [
    {
      "item_id": "change-id",
      "geometry_decision": "same_box",
      "boxes": [[10, 20, 300, 160]],
      "refined_text": "concise visible scope text",
      "reason": "short reason for the proposed box/text",
      "confidence": 0.82,
      "tags": []
    }
  ]
}
```

Allowed `geometry_decision` values remain:

- `same_box`
- `adjusted_box`
- `partial`
- `overmerged`
- `false_positive`
- `unclear`

## Test Plan

- Unit tests:
  - batch schema normalization maps results to the correct `item_id`
  - duplicate, missing, unknown, and invalid `item_id` rows fail safely
  - batch provider writes individual cache files
  - per-call usage metadata is captured in cache JSON and run-level JSONL
  - batch usage allocation preserves raw request usage and links rows to
    returned `item_id`s
  - existing single-item cache files are reused
  - `SCOPELEDGER_PREREVIEW_BATCH_SIZE` defaults to `5`, accepts `1`, and
    rejects or clamps unsafe values

- Populate/service tests:
  - fake batch provider processes multiple items in fewer provider calls
  - failed batch does not hide candidates and records item failures
  - progress callback updates `populate_status` after each batch
  - partial batch save leaves completed item provenance in `workspace.json`

- UI/route tests:
  - `/workspace/populate/status` returns Pre Review progress counters
  - Overview renders Pre Review progress without internal model/vendor labels
  - no client-facing `GPT`, `CloudHammer`, `training`, `eval`, or `labeling`
    appears in the status UI

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check webapp\static\app.js
```

## Assumptions

- Batch size default is `5`, chosen as a conservative handoff-safe setting.
- Existing per-item cache remains the source of truth, not a batch-level cache.
- The intended Pre Review count is the number of visual review items, not the
  CloudHammer artifact count.
- Current CloudHammer live artifacts remain diagnostic/output files and do not
  affect API call count.
- Implementation is explicitly deferred until requested.
