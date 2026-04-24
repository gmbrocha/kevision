# Rebuild Plan

> **Status banner — updated 2026-04-21**
>
> This doc was written *before* the index parser and Kevin-changelog work landed. Status of the pieces it describes:
>
> - **Shipped** — `experiments/2026_04_index_parser/` (deterministic per-revision sheet table; hand-verified against `Rev2_final_current_state.csv` — this is the data spine and stays put). `revision_tool/kevin_changelog.py` (Kevin-shaped Excel exporter, tested, generated for real from `workspace_demo`).
> - **Half-shipped** — Δ marker denoise pipeline in `experiments/delta_v3/` (`denoise_2.png` is the canonical pre-detection image). Detection-on-top is scrapped; restart needed. `2026_04_delta_marker_detector/` and `delta_v2/` are earlier abandoned approaches, kept for provenance.
> - **Paused with documented next step** — `experiments/2026_04_cloud_detector_v2/` (paused at stage 3; blocked on scallop boundary repair before contour assembly works).
> - **Pending** — Δ marker detection v4 (consume `delta_v3/denoise_2.png`, build a fresh detector). The per-file KILL/REWRITE/KEEP execution this doc proposes (see `docs/cleanup_audit_2026_04_21.md` for current state and recommended order). The target package architecture below is also unimplemented.
>
> Read the rest of this doc as the *plan*, not the *current state*.

Two parts: an audit of what we have today and where it lands in the rebuild, and the target package architecture with explicit dependency rules so we don't end up with spaghetti.

## Why a rebuild

The original tool was built around a wrong target (pricing extraction). Kevin's actual deliverable is a verbose Excel of revision items derived from index iteration → cloud detection → symbol/legend lookup. The data model, the pipeline shape, the CV approach, and most of the GUI all need to change. Rather than mutate in place we'll replace by stage and lean on what works.

## Glossary (locked)

- **Revision set** = the package (e.g., "Revision #1 - Drawing Changes")
- **Revision** = one row from the index = one revised sheet within this set
- **Change item** = the smallest unit, the actual thing to be built/ordered/removed
- **Drawing** = an individual page (a page can hold multiple drawings via drawing-label badges)
- **Drawing region** = the rectangular area on a page occupied by one drawing (most pages have one region == the whole page; AD104-style pages have multiple)
- **Cloud** = a closed scallop-chain polygon enclosing a revision
- **Δ-marker** = the triangle with revision number that always accompanies a cloud
- **Legend entry** = a (glyph, description) pair in the per-drawing legend block

---

## File-by-file audit

Status legend:
- **KEEP** — works as-is or with cosmetic tweaks
- **SALVAGE** — pattern/scaffolding survives, internals get replaced
- **REWRITE** — same intent, fundamentally different implementation
- **KILL** — gone, no replacement
- **DEFER** — not needed for v1, revisit later

### `revision_tool/`

| File | Status | Notes |
|---|---|---|
| `__init__.py` | KEEP | Empty package marker |
| `__main__.py` | KEEP | One-liner that delegates to `cli.main` |
| `cli.py` | REWRITE | Same three commands (`scan`, `serve`, `export`) but they orchestrate the new pipeline. Keep the friendly summary pattern. |
| `scanner.py` | KILL → REWRITE in many modules | Old: monolithic OpenCV-contour cloud finder + narrative parser + sheet-id extractor. New architecture splits this into `pdf/`, `detect/`, `parse/`. The narrative-page parsing is dead (we iterate the index, not narratives). The cache + fingerprint + scan-result-restore pattern is good and gets ported to the new orchestrator. |
| `exporter.py` | KILL most, SALVAGE conformed-PDF + preflight | The pricing-relevance machinery (placeholder filter, locator/label tokens, scope keywords, candidate filter, pricing log) is dead. Rewrite as a thin Excel writer + reuse the rasterized conformed-PDF logic and preflight-diagnostics dump. |
| `models.py` | REWRITE | Old dataclasses (`ChangeItem`, `CloudCandidate`, `NarrativeEntry`) reflect the wrong domain. New model: `RevisionSet`, `Revision`, `Drawing`, `DrawingRegion`, `Cloud`, `ChangeItem`, `LegendEntry`, `Symbol`, `Confidence`. |
| `workspace.py` | SALVAGE | Directory layout (`workspace.json`, `assets/pages`, `assets/crops`, `outputs/`) and load/save pattern are good. Swap the data class. Keep cache fingerprinting. |
| `diagnostics.py` | KEEP | Preflight PDF warning capture/summary works for any PDF pipeline. Move to `pdf/diagnostics.py`. |
| `utils.py` | SALVAGE | `slugify`, `stable_id`, `clean_display_text`, `normalize_text`, `parse_mmddyyyy` survive. `choose_best_sheet_id` and `parse_detail_ref` need expansion (more sheet-ID variants — see Kevin's example sheets). `DETAIL_REF_PATTERN` is partially dead. |
| `review.py` | KILL | `change_item_needs_attention` heuristic was for old `ChangeItem`s. New flagging is per-detector and per-parser, lives in `core/confidence.py`. |
| `verification.py` | DEFER | LLM-based clarification might be useful again (e.g., legend-entry description normalization, free-text annotation summarization), but not in v1. Delete the file; reintroduce when we have a concrete need. |
| `web.py` | REWRITE | Flask app factory + asset serving + template helpers stay. Routes are fundamentally different (no `/changes`, no bulk-review, no AI-verify). New routes: `/revisions`, `/revisions/<id>`, `/review`, `/conformed`. Split into `web/app.py` + `web/routes/*.py`. |
| `static/app.css` | KEEP | Solid design system (cards, panels, status pills). Add classes for new components, retire dead ones. |
| `static/app.js` | KEEP | Bbox-overlay logic on rendered images is exactly what we'll need for cloud highlights. |
| `templates/base.html` | KEEP, edit nav | Shell stays. Nav items change to match new routes. Summary-strip drops pricing tiles. |
| `templates/dashboard.html` | REWRITE | New tiles: Revisions extracted, Items needing review, Conformed sheets, Excel ready. |
| `templates/sheets.html` | KEEP, edit | Sheet listing pattern is right. Trim to current need. |
| `templates/sheet_detail.html` | SALVAGE | Image + bbox-overlay pattern is right. Replace bboxes-for-clouds with the new cloud polygons; drop change-item table or rewrite. |
| `templates/changes.html` | KILL | Pricing-era queue UI. New review queue is fundamentally different (per-cloud crop with symbol/legend matching, not per-item text editor). |
| `templates/change_detail.html` | KILL | Same. |
| `templates/conformed.html` | KEEP | Built last week, still 100% correct in the new model. Good template for the rebuild's UI conventions. |
| `templates/diagnostics.html` | KEEP | Preflight UI, still relevant. |
| `templates/export.html` | REWRITE | New buttons: "Generate Excel", "Open Excel folder". Drop pricing-readiness language. |
| `templates/settings.html` | DEFER | Just AI-key settings today. KILL once we remove `verification.py`; bring back if needed. |

### `tests/`

| File | Status | Notes |
|---|---|---|
| `conftest.py` | KEEP | Workspace-fixture pattern is solid. The fixture path will switch from rev1+rev2 to whatever we standardize on. |
| `fixtures/expected_workspace_metrics.json` | KILL | Asserts old metrics. New fixture will assert new metrics. |
| `test_app.py` | KILL most, SALVAGE 2-3 | Re-scan caching test, preflight tests, basic web routing pattern survive. Pricing-filter tests, bulk-review tests, verification tests die. |

### `docs/`

| File | Status | Notes |
|---|---|---|
| `pricing_deliverable_schema.md` | KILL (keep in git history) | Stale spec from the wrong target. Don't edit, don't reference. |
| `pricing_deliverable_schema.sql` | KILL (keep in git history) | Same. |
| `rev1_rev2_benchmark.md` | SALVAGE | Benchmark structure is reusable; metrics need re-framing around change-item recall/precision and review-time-saved (not pricing items). |
| `rev1_rev2_benchmark_template.csv` | SALVAGE | Same. |
| `demo_script.md` | KEEP (frozen) | Snapshot of pre-pivot state. Don't update; will be replaced by a new script post-rebuild. |
| `KEVIN_QUESTIONS.md` (root) | KEEP, live document | Already in active use. |
| `rebuild_plan.md` (this file) | NEW | Source of truth for the rebuild. |

### Repo root

| File | Status | Notes |
|---|---|---|
| `README.md` | REWRITE last | Should reflect the new tool when we ship v1. Don't touch yet. |
| `requirements.txt` | KEEP, add openpyxl | Existing deps survive. Add `openpyxl` for Excel output. Possibly add `shapely` for clean polygon geometry; assess during the cloud-detector experiment. |
| `revision_sets/` | KEEP | Bundled fixture data, untouched. |
| `docs/anchors/revision.png`, `docs/anchors/revision_cloud_example_2.png` | KEEP | Reference images for docs. |

---

## Target package architecture

### Layered layout

```
revision_tool/
├── __init__.py
├── __main__.py
├── cli.py                          # CLI entry: scan / serve / export
│
├── core/                           # data model — no I/O, no CV, no Flask
│   ├── __init__.py
│   ├── models.py                   # RevisionSet, Revision, Drawing, DrawingRegion,
│   │                               # Cloud, ChangeItem, LegendEntry, Symbol, Confidence
│   ├── confidence.py               # Confidence + Flag types, severity rules
│   └── workspace.py                # workspace store: load/save JSON, asset paths, cache
│
├── pdf/                            # PDF I/O primitives — depends on core
│   ├── __init__.py
│   ├── pages.py                    # render page → image, extract text words/blocks
│   ├── diagnostics.py              # preflight warning capture (was diagnostics.py)
│   └── titleblock.py               # extract sheet ID, title, project metadata
│
├── detect/                         # CV detectors — each one stand-alone, testable
│   ├── __init__.py
│   ├── clouds.py                   # SCALLOP-CHAIN cloud detector (the heart)
│   ├── drawing_regions.py          # locate drawing-label badges, segment page into regions
│   ├── delta_markers.py            # Δ-with-revision-number triangles
│   ├── legend.py                   # locate the legend block, segment its entries
│   ├── symbols.py                  # match a glyph against a per-drawing/global symbol table
│   └── containment.py              # is point/element inside a cloud polygon (centroid test)
│
├── parse/                          # detector outputs → structured data
│   ├── __init__.py
│   ├── index.py                    # parse the sheet-index page → list of Revisions
│   ├── revisions.py                # per revised sheet: clouds → ChangeItems
│   └── cross_reference.py          # match Δ + X-col + cloud, surface disagreements
│
├── aggregate/                      # combine across revision sets / sheets
│   ├── __init__.py
│   ├── conformed.py                # build conformed sheet set (latest per sheet ID)
│   └── duplicates.py               # cross-sheet duplicate detection (placeholder for v1)
│
├── output/                         # writers — pure write, no detection logic
│   ├── __init__.py
│   ├── excel.py                    # the audit Excel + bill-of-items + review queue
│   ├── conformed_pdf.py            # rasterized latest-set PDF (logic ported from old exporter)
│   └── workspace_dump.py           # debug JSON dumps of the workspace
│
├── pipeline.py                     # orchestrator: composes pdf → detect → parse → aggregate → output
│
├── web/                            # GUI for review — consumer only
│   ├── __init__.py
│   ├── app.py                      # Flask app factory
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── dashboard.py
│   │   ├── revisions.py
│   │   ├── review.py
│   │   └── conformed.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── revision_detail.html
│   │   ├── review_queue.html
│   │   └── conformed.html
│   └── static/
│       ├── app.css
│       └── app.js
│
└── utils.py                        # truly cross-cutting helpers (slugify, stable_id, clean text)
```

```
tests/
├── conftest.py
├── unit/
│   ├── test_clouds.py
│   ├── test_legend.py
│   ├── test_containment.py
│   ├── test_index_parser.py
│   └── ...
├── integration/
│   ├── test_pipeline_smoke.py
│   └── test_excel_output.py
└── fixtures/
    └── (existing rev1+rev2 fixture)

experiments/
└── 2026_04_cloud_detector/         # tonight's experiment lives here
    ├── README.md                   # what we tried, what we learned
    ├── detect.py                   # the throwaway script
    └── output/                     # overlays, screenshots, eyeball evidence
```

### Anti-spaghetti rules (enforced by code review, not tooling — for now)

1. **One direction of dependency.** Layers stack like this: `core` ← `pdf` ← `detect` ← `parse` ← `aggregate` ← `output`. Each layer may import only from layers below it. `cli` and `web` import from `pipeline` and `output` (and `core` for types). `pipeline` orchestrates everything.
2. **`core` is pure.** No `fitz`, no `cv2`, no `flask`, no file I/O. Just dataclasses, enums, and pure helper functions. Makes everything below trivially unit-testable.
3. **Detectors are isolated and single-purpose.** Each `detect/*.py` exposes a clean function like `detect_clouds(image: np.ndarray, ...) -> list[Cloud]`. No global state, no `Workspace` parameter, no cross-detector calls. They take pixels in, return structured findings out. This is what makes the rebuild testable and what lets us swap the cloud detector if a better one shows up.
4. **Parse layer translates findings into meaning.** Takes detector outputs + page text, returns `Revision`s and `ChangeItem`s with confidence. Has no opinion about what gets exported.
5. **Output layer is write-only.** Take structured data in, write files out. Never re-detects, never re-parses.
6. **`pipeline.py` is the only orchestration code.** If you want to know what runs in what order, you read `pipeline.py` top-to-bottom. Business logic doesn't get spread across modules.
7. **`web` is a consumer, not a participant.** GUI reads from the workspace and triggers re-runs/edits via well-defined APIs in `pipeline`. It does NOT contain detection or parsing logic.
8. **Confidence/flagging is cross-cutting, owned by `core`.** Every detector and parser produces output with a `Confidence` and a list of flag reasons. Aggregation collects flags. Review queue = "everything with severity ≥ X".
9. **Tests mirror the package.** `tests/unit/test_clouds.py` tests `detect/clouds.py`. Integration tests live in `tests/integration/` and exercise `pipeline.py`. Fixtures are PDFs (real or synthetic small ones).
10. **Throwaway scripts go in `experiments/<date>_<topic>/`** with a `README.md` describing what was tried and what was learned. They never import from `revision_tool/` packages they shouldn't (so we don't accidentally couple production code to throwaway code).

### What stays public vs. private

- **Public API** = `pipeline.scan(input_dir, workspace_dir)`, `pipeline.export(workspace_dir, ...)`, `web.app.create_app(workspace_dir)`. CLI calls only these.
- **Everything else is internal** to its layer. If `web/` needs to render a Cloud, it imports the `Cloud` dataclass from `core/models.py` — never calls into `detect/clouds.py` directly.

### Migration order (when we start coding)

1. **Stand up `core/` and `pdf/`** — empty new model + ported diagnostics, ported titleblock parsing. Smoke test: load a PDF, render a page, extract title-block text. **No business value yet, but a clean spine.**
2. **Build `detect/clouds.py`** — the experiment we're about to run produces this. Once it works on the bundled fixture, promote the script into the module.
3. **Build `detect/drawing_regions.py` and `detect/delta_markers.py`** — both are simpler than clouds. Verify on the fixture.
4. **Build `parse/index.py`** — full index extraction → list of Revisions, with the Δ + X-col + cloud cross-check. **First real value: we can list every Revision in a set.**
5. **Build `detect/legend.py` + `detect/symbols.py`** — per-drawing legend parsing and symbol matching.
6. **Build `parse/revisions.py`** — for each Revision, walk clouds → ChangeItems with symbol/legend lookup and centroid containment.
7. **Build `output/excel.py`** — write the audit workbook from structured data. **Second real value: a usable Excel for Kevin to look at.**
8. **Stand up `web/`** — minimal review queue first; extend as we learn what Kevin actually does with the flagged items.
9. **`aggregate/duplicates.py`** — only after we have real data and Kevin tells us what dedup he wants.

Each step is independently shippable. We don't try to do steps 4 and 6 in the same week; finish step 4, get something Kevin can actually look at, then move on.

---

## Risks the rebuild surfaces

- **Cloud detector is the single biggest unknown.** If scallop-chain detection turns out to be much less reliable than we think (e.g., on rotated/skewed scans), it forces a rethink of steps 4–6. Hence: experiment first, before any rebuild commits.
- **Drawing-region segmentation may be harder than it looks** for pages where badges are in unusual places or missing. Probably needs a fallback: "if no badge found, treat the page as one region".
- **Legend extraction is OCR-heavy.** Tesseract will struggle on tiny glyphs. Mitigation: per-drawing legend matching first (small closed set), only fall back to global matching if per-drawing fails.
- **Excel hierarchical cells** (merged Sheet/Cloud parents) get fragile in some viewers. We'll prototype both merged-cell and flat-with-repeated-IDs and see what reads better.

## What this plan does NOT decide

- The exact Excel column list (deferred to its own design doc once Kevin's Excel arrives).
- The review-GUI interaction model (depends on what flagged items look like in practice).
- Whether we keep the existing rev1+rev2 fixture or pull a richer one (need a longer revision package to stress-test).
- Anything that depends on Kevin's transcript.
