# Experiment: Sheet Index Parser

**Status:** in progress

**Goal.** For each revision package PDF, find the sheet-index page and extract
every revision item: one row per sheet revised in this revision, directly from
the PDF text layer plus table geometry. Output a CSV.

This sidesteps cloud detection entirely on the index page. The "X" marks in
each revision column are characters in the PDF text layer with exact bounding
boxes. Combined with row numbers, sheet IDs, and sheet titles, the index
iteration loop is fully deterministic.

## Why this is the right approach for the index

Earlier cloud-CV exploration showed that text and line masking leaves the
index page with only a small amount of visual clutter. But cloud detection on
the index is still harder than what is actually needed here: the index already
encodes "which rows changed" via the X column.

Cloud detection on the index is a sanity check, not a primary signal.

For drawing pages we still need cloud detection. That work now lives in the
separate CloudHammer track rather than the old classical-CV experiment chain.

## Approach

For a target revision (for example, `Revision #1`):

1. Open the PDF and identify the index page by searching for `SHEET INDEX`.
2. Use `page.search_for("REVISION #1")` to find the revision header rects.
   Each rect's x-range defines its column's X-mark area.
3. For each `X` word in any of those x-ranges, find its row by y-coordinate.
4. For that row, locate the sheet number and sheet title from the neighboring
   text cells.
5. Emit one CSV row per match.

## Files

- `explore.py` - diagnostic dump of revision-column headers, X marks, sheet
  IDs, and row-number positions on the Rev 1 and Rev 2 index pages
- `parse.py` - the actual parser; reads one PDF plus one revision label and
  writes one CSV
- `dedupe.py` - combine multiple per-revision CSVs into a single current-state
  CSV; keeps the latest revision that touched each sheet and adds revision
  history columns
- `debug_misses.py` - diagnostic for missing X marks and rejection reasons
- `output/` - generated CSVs and any diagnostic artifacts worth keeping

## Test Inputs

| Revision set | PDF | Target revision label |
|---|---|---|
| Revision #1 | `revision_sets/Revision #1 - Drawing Changes/Revision #1 - Drawing Changes.pdf` | `REVISION #1` |
| Revision #2 | `revision_sets/Revision #2 - Mod 5 grab bar supports/260309 - Drawing Rev2- Steel Grab Bars.pdf` | `REVISION #2` |
