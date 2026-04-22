# Cloud Detector v2 — Resume Checklist

One-pager for restarting work without re-deriving everything from the README. Read this; only open `README.md` when you need the *why*.

## TL;DR — where we left off

**Pipeline state:** stages 1 + 2 work. Stage 3 (scallop template matching) failed because line masking nicks the cloud arcs into fragments — `detect_scallops.py` finds nothing real and lights up only on the architect seal and consultant block. Stages 4–6 never started.

**Last good output:** `output/rev1_p00_index_02_lines_masked.png` (index page after stages 1 + 2 — clean enough that the next stage *should* work, with the right primitive).

**Decision when paused:** ship the index parser first (done — see `experiments/2026_04_index_parser/`), come back here with a fix for the scallop fragmentation problem.

## Resume in 3 steps

### Step 1 — Add scallop repair preprocessing

**Problem:** stage 2 line masking removes pixels at every grid-line × cloud-arc crossing, leaving each scallop broken into short dashes. Template matching needs intact arcs.

**Fix (try in this order):**

1. **Morphological close along the inner rim of each grid-line mask** — dilate the line mask by 1–2 px, then close any non-mask pixels that lie within that dilated band. Cheapest, no new state.
2. If that under-fills: **skeleton-bridge** — skeletonize the post-mask image, find endpoint pairs within ~8 px of each other on opposite sides of a masked region, draw a 1-px line between them. More expensive but reconstructs only where there's evidence.
3. If that over-fills: bound (2) by orientation — only bridge endpoints whose local tangents are within ~30° of each other, so unrelated severed lines don't get reconnected.

**File:** new `stages/repair_scallops.py`. **Output:** `<page>_02b_repaired.png`. **Verification:** eyeball the index page output — scallop arcs should be visually continuous again.

### Step 2 — Strip the three remaining non-cloud features

After stages 1 + 2, the only non-cloud curved features left are:

- **Architect seal** — dotted circle in a known location (top-right or footer). Strip via Hough circles in a single localized ROI, or simpler: mask everything below the seal's top y as "footer" since clouds don't live there.
- **Consultant address block** — text inside a rectangle in the page footer. Already partially stripped by stage 1; the rectangle border survives. Add it to the line-mask sweep at a 30 px floor for short rectangle edges, or detect-and-fill via connected-components area floor.
- **"VA" stamp glyph remnants** — filled connected-component blobs above a pixel-density threshold. Drop with `cv2.connectedComponentsWithStats` filter on `solidity > 0.7` AND `area < 400`.

**File:** extend `stages/mask_text.py` or add `stages/mask_artifacts.py`. **Output:** `<page>_02c_artifacts_masked.png`. **Verification:** stage 3 detector should stop firing on the seal and consultant block (the false-positive set should shrink to ≤ a handful per page).

### Step 3 — Re-run stage 3 template matching

With repair + artifact stripping in place, re-run `stages/detect_scallops.py` unchanged on the same 5 test pages. The detector itself is fine; it just needs intact arcs to match against.

**Pass criterion:** ≥ 1 detection per known cloud on the 5 test pages, and < 5 false positives per page. If pass → build stages 4 (orientation tagging), 5 (run grouping), 6 (loop matching) per the README's design. If fail → the primitive itself is wrong; consider Hough-arc detection or a learned scallop classifier instead of templates.

## Test pages and expected outcomes

(unchanged from README — copied here so you don't have to flip files)

| Label | Expected clouds |
|---|---|
| `rev1_p00_index` | many small row-bracket clouds; dense table grid |
| `rev1_p01_GI104` | two known FEC + exit-light clouds |
| `rev1_p04_SF110` | one cloud around a black-square mystery |
| `rev1_p06_AD104` | one X-hexagon cloud, multi-drawing page |
| `rev2_AE107_1_R1` | sanity check, different style |

## What NOT to spend time on

- **Index pages.** The PDF text layer gives you the X marks deterministically; that's what `experiments/2026_04_index_parser/` already does. Cloud detection on index pages is unnecessary.
- **Going back to iteration 1's contour scoring.** Checkpoint 1 confirmed it doesn't work on cleaned images (rejects every clean cloud as `low_solidity`). The cleaning was the right move; the *primitive* needed to change with it.
- **Hough lines for stage 2.** Tried it; produced tens of thousands of segments on a 12600×9000 image and the companion-pair check exploded O(n²). Morphological erosion is correct.

## When stage 3 passes

The README has the full design for stages 4–6. Quick recap so you can scope:

- **Stage 4** — orientation tagging: each scallop detection already carries its template orientation (TOP/BOTTOM/LEFT/RIGHT); just record it.
- **Stage 5** — `group_runs.py`: chain scallops of the same orientation whose centers lie within ~1.5× radius of each other into runs. Cloud edges become 4 runs per cloud (one per side).
- **Stage 6** — `match_loops.py`: for each TOP run, find a BOTTOM run roughly below it, plus a LEFT and RIGHT run on the sides. Close the loop. Output one (cloud_id, polygon) per closed loop.

Then it's plumbing into `revision_tool/` so the Kevin changelog gets real cloud crops instead of the synthetic ones from `workspace_demo`.
