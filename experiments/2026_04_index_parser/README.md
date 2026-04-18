# Experiment: Sheet Index Parser

**Status:** in progress

**Goal.** For each revision package PDF, find the sheet-index page and extract every revision item — one row per (sheet revised in this revision) — directly from the PDF text layer + table geometry. Output a CSV.

This sidesteps cloud detection entirely on the index page. The "X" marks in each revision's column are characters in the PDF text layer with exact bounding boxes. Combined with row numbers, sheet IDs, and sheet titles (also in the text layer), the index iteration loop is fully deterministic.

## Why this is the right approach for the index

Per the iteration-2 cloud-detector experiment (`../2026_04_cloud_detector_v2/`), text + line masking left the index page with just clouds + Δ markers + a few footer artifacts. But the cloud detector itself is much harder than what's needed here — the index already encodes "which rows changed" via the X column. Cloud detection on the index is a sanity check, not a primary signal.

For drawing pages we still need cloud detection (no equivalent shortcut). That work continues separately in `../2026_04_cloud_detector_v2/` once we resume.

## Approach

For a target revision (e.g., "Revision #1"):

1. Open the PDF, identify the index page (search for "SHEET INDEX" text).
2. `page.search_for("REVISION #1")` returns one rect per physical column the index spans (the index wraps across multiple columns on the page). Each rect's x-range defines its column's X-mark area.
3. For each "X" word in any of those x-ranges, find its row by y-coordinate.
4. For that row, locate sheet number (regex match against sheet-ID pattern) and sheet name (the wider text cell to the right of the sheet number).
5. Emit one CSV row per match.

## Files

- `explore.py` — diagnostic dump of revision-column headers, X marks, sheet IDs, and row-number positions on the Rev 1 and Rev 2 index pages. Run first to verify assumptions before writing the parser.
- `parse.py` — the actual parser. Reads one PDF + one revision label, writes one CSV.
- `dedupe.py` — combine multiple per-revision CSVs into a single "current state" CSV. For each sheet, keeps the row from the latest revision that touched it; adds `revision_count` and `revision_history` columns showing every revision that touched the sheet.
- `debug_misses.py` — diagnostic for missing X marks; prints in-column / out-of-column breakdown, dedup cases, and rejection reasons.
- `output/` — generated CSVs and any diagnostic artifacts.

## Test inputs

| Revision set | PDF | Target revision label |
|---|---|---|
| Revision #1 | `revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf` | `REVISION #1` |
| Revision #2 | `revision_sets/Revision #2 - Mod 5 grab bar supports/260309 - Drawing Rev2- Steel Grab Bars.pdf` | `REVISION #2` |

## Findings

### explore.py

- Index page is **not always page 0**. Rev 2's PDF has 3 narrative pages first; the index lives on page 3. Built a content-based heuristic (table-header tokens `PAGE NO.` + `SHEET NO.` + `SHEET NAME` + sheet-ID density) to find the right page automatically.
- The index spans **3 physical columns** on the page; each physical column has its own copy of the column headers (`CONFORMED SET`, `REVISION #1`, `REVISION #2`, ...). For a target revision we get one HeaderBlock per physical column and union the X marks across all of them.
- **Rev 2's index page has `page.rotation = 90`**. PyMuPDF returns word/header bboxes in the page's *native* (un-rotated) coord space. So even though Rev 1 and Rev 2 indexes look visually identical (vertical column headers, X marks stacking down the column), Rev 2's raw bboxes report as horizontally-laid-out. Apply `page.rotation_matrix` to every bbox/dir once at parser entry to put everything in display-canonical coords; the rest of the parser then works in a single orientation.

### parse.py

Final flow:
1. Find the index page via `score_index_likelihood`.
2. Apply `page.rotation_matrix` to every word and header bbox.
3. Find every `REVISION #N MM/DD/YYYY` header line; keep ones whose post-rotation bbox is a tall-narrow rectangle (the actual column headers, not the small footer references).
4. For each header, find every `X` word whose x-centroid falls within the header's column x-extent.
5. For each X, find the row by y-band, anchor on the sheet-ID column, and walk left for the row number / right for the sheet name.
6. Dedupe `(row_number, sheet_number)` across the 3 physical columns and emit a CSV row per item.

### Verification (`output/`)

Both expected revision sets parse cleanly and were hand-checked by the user.

| Run | Revisions found | Date extracted | Index page |
|---|---|---|---|
| Rev 1 PDF, `REVISION #1` | **50** | 10/10/2025 | 0 |
| Rev 2 PDF, `REVISION #2` | **26** | 01/30/2026 | 3 |
| Rev 2 PDF, `REVISION #1` | **50** (matches Rev 1 PDF result exactly) | 10/10/2025 | 3 |

### Dedupe → "current final revision" view

`dedupe.py` combines per-revision CSVs into a single sheet-level snapshot. For each sheet it keeps the row from the latest revision that touched it (by `revision_date`) and adds a `revision_history` column showing every revision that touched the sheet, oldest first.

Run on Rev 2's two revision exports:

```
python dedupe.py \
  output/260309*__revision_1.csv \
  output/260309*__revision_2.csv \
  -o output/Rev2_final_current_state.csv
```

Result: **60 unique sheets** from 76 input rows; **16 sheets** were touched by both Rev 1 and Rev 2 (their `latest` is `REVISION #2`, history shows both). Sheets revised only in Rev 1 carry `latest=REVISION #1` and a single-entry history. This is the "what's the current state of every sheet that's ever been revised" view that downstream consumers (build-set updater, estimator) actually want.

### Bugs found and fixed during verification

The first run reported 42 for Rev 1; user spot-checked and counted 49+ revisions in the source. Two bugs:

1. **Row-data extraction was column-blind.** When an X mark in the *middle* physical column was looked up by y-coordinate, `words_on_same_row` returned every word at that y across the whole page. `extract_row_data` then picked the first sheet ID it saw (the *left* physical column's). The middle-column sheet got silently lost (then deduped against the false left-column hit).

   Fix: pass the X word's x-position into `extract_row_data` and only consider candidate words with center_x strictly less than the X but within `SHEET_ID_MAX_DISTANCE_FROM_X` (1100 px). Pick the rightmost sheet ID among those — it's guaranteed to be in the same physical column as the X.

2. **Sheet-ID regex was too narrow.** `^(?:GI|AD|AE|IN|PL|EL|EP|MP|MH|ME|E|M|S|SF|CS|RFP)\d{3}(?:\.\d+)?$` missed prefixes like `QH` (equipment) and `FA` (fire alarm) that exist in the bundled fixture, dropping their rows from the output.

   Fix: relaxed to `^[A-Z]{1,3}\d{3,4}(?:\.\d+)?$`. Permissive but still distinctive — sheet IDs are always upper-case letters followed by digits.

### Promotion path

When we start the rebuild, this becomes `revision_tool/parse/index.py` per `docs/rebuild_plan.md`. The output dataclass `RevisionItem` is the seed of the `core/models.Revision` row that the rest of the pipeline expands by walking each revised sheet for its change items.
