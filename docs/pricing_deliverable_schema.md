# Pricing Deliverable Schema

Status: `Legacy reference. Kept for historical context only; do not treat this as the current deliverable spec.`

## Recommendation

Do not replace the current workspace JSON store with SQLite yet.

The current app uses `workspace.json` as a scan-and-review artifact store. That is fine for:

- local single-user review
- cached rescans
- review state persistence
- image asset lookup

SQLite becomes useful when the product goal changes from "review a workspace" to "produce a stable, queryable pricing dataset".

So the recommended path is:

1. Keep `workspace.json` as the working review store.
2. Define a deliverable-oriented schema now.
3. Export the reviewed workspace into that schema.
4. Move the app to SQLite later only if querying, dedupe, reporting, or multi-run history become central.

## Real Deliverable

Based on the email context, the tool needs to produce two outputs:

1. A conformed drawing set
   - latest sheet version wins
   - earlier revised sheets are marked superseded

2. A pricing change log
   - one row per pricing-relevant clouded change
   - grouped by sheet and detail
   - deduped across revision sets when the later revision supersedes the earlier one
   - human-readable scope text, not raw OCR

## Core Entities

### `revision_sets`

One incoming package such as `Revision #1 - Drawing Changes`.

| column | type | notes |
| --- | --- | --- |
| `id` | text primary key | stable ID |
| `label` | text not null | folder/package label |
| `set_number` | integer not null | revision ordering key |
| `set_date` | text | drawing-set issue date when known |
| `source_dir` | text not null | original folder path |

### `documents`

One source PDF inside a revision set.

| column | type | notes |
| --- | --- | --- |
| `id` | text primary key | stable ID |
| `revision_set_id` | text not null | FK to `revision_sets.id` |
| `source_pdf` | text not null | full file path |
| `page_count` | integer not null | source PDF pages |
| `warning_count` | integer not null default 0 | preflight warning count |
| `issue_count` | integer not null default 0 | preflight issue count |
| `max_severity` | text not null default 'ok' | `ok`, `low`, `medium`, `high` |

### `sheet_versions`

One detected sheet page from one revision set.

| column | type | notes |
| --- | --- | --- |
| `id` | text primary key | stable ID |
| `revision_set_id` | text not null | FK |
| `document_id` | text | FK |
| `source_pdf` | text not null | provenance |
| `page_number` | integer not null | source page |
| `sheet_id` | text not null | drawing number like `AE113` |
| `sheet_title` | text | sheet title |
| `issue_date` | text | drawing issue date |
| `status` | text not null | `active` or `superseded` |
| `superseded_by_sheet_version_id` | text | later version if known |
| `render_path` | text | page preview asset |
| `is_latest_for_pricing` | integer not null default 0 | 1 for conformed winner |

### `pricing_changes`

One pricing-relevant change candidate after review and dedupe.

This is the table that should eventually drive the estimator-facing export.

| column | type | notes |
| --- | --- | --- |
| `id` | text primary key | stable ID |
| `sheet_version_id` | text not null | FK to current/latest relevant sheet |
| `sheet_id` | text not null | denormalized for export |
| `detail_ref` | text | detail or callout reference |
| `detail_title` | text | human-readable detail title if known |
| `change_summary` | text not null | concise reviewer-approved pricing summary |
| `pricing_status` | text not null | `pending`, `approved`, `rejected` |
| `needs_attention` | integer not null default 0 | unresolved weak extraction |
| `source_kind` | text not null | `narrative`, `visual-region`, or `manual` |
| `extraction_signal` | real | scan confidence |
| `superseded_by_change_id` | text | later equivalent change if replaced |
| `is_latest_for_pricing` | integer not null default 1 | 1 means include in pricing log |
| `reviewer_notes` | text | optional notes |

### `pricing_change_lines`

Normalized scope bullets for a change.

This matches the email example better than one giant text blob.

| column | type | notes |
| --- | --- | --- |
| `id` | text primary key | stable ID |
| `pricing_change_id` | text not null | FK to `pricing_changes.id` |
| `line_order` | integer not null | display order |
| `scope_text` | text not null | one pricing scope line |

Example for the AE113 email example:

- `1" Fire Shield Shaftliner`
- `2 1/2" CT Studs 24" O.C.`
- `2 Layers 5/8" Fire-Shield Gypsum Board`
- `Corner Bead`

### `change_sources`

Evidence rows showing how a pricing change was formed.

| column | type | notes |
| --- | --- | --- |
| `id` | text primary key | stable ID |
| `pricing_change_id` | text not null | FK |
| `revision_set_id` | text not null | FK |
| `sheet_version_id` | text | FK |
| `raw_source_text` | text | original narrative/OCR text |
| `source_change_item_id` | text | current app change-item ID if present |
| `source_cloud_candidate_id` | text | current app cloud ID if present |
| `source_kind` | text not null | `narrative`, `visual-region`, `manual` |
| `confidence` | real | extraction confidence if available |

## What Should Be Exported

The estimator-facing export should not be the raw queue.

It should be a flattened view shaped roughly like:

| revision_set | sheet_id | detail_ref | detail_title | change_summary | scope_lines | latest_for_pricing |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | AE113 | 3 | 2 HR Rated Enclosure at Attic | New 2-hour rated enclosure scope at attic detail | `1" Fire Shield Shaftliner; 2 1/2" CT Studs 24" O.C.; 2 Layers 5/8" Fire-Shield Gypsum Board; Corner Bead` | yes |

## Why Not Switch The Whole App To SQLite Yet

Not yet, because the current pain is not "storage is too weak". The pain is:

- too many noisy candidate rows
- not enough normalization into pricing-ready scope
- output shape does not match the estimator's task

SQLite helps when you need:

- cross-run comparisons
- robust dedupe logic
- strong query/reporting workflows
- auditable change lineage
- larger datasets with repeated filtering/grouping

That is likely where this tool is headed, but it is not the first bottleneck.

## Suggested Next Implementation Step

Add a new export artifact:

- `pricing_change_log.csv`
- `pricing_change_log.json`

Each row should represent one reviewed pricing change, not one raw scan item.

That output should be based on the schema above, even if the app still persists its workspace in JSON.
