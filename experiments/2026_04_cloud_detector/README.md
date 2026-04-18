# Experiment: Scallop-chain Cloud Detector

**Goal.** Verify we can reliably detect revision clouds on the bundled fixture PDFs using a geometric prior (clouds are closed chains of similar-radius scallops, each scallop = a pair of arcs in a fixed ratio). Differentiate clouds from door-swing arcs, wall hatching, and other noise.

**Status.** Throwaway. Lives outside `revision_tool/` so production code never depends on it.

## Approach

Convex-hull defect analysis on closed contours.

1. Render each test page at 300 DPI grayscale (PyMuPDF).
2. Threshold + light morphological close (3×3 kernel) to bridge small gaps in cloud arcs.
3. `cv2.findContours(RETR_TREE, CHAIN_APPROX_NONE)` to get every closed contour with full point detail.
4. For each contour:
   - Compute convex hull and convexity defects.
   - Filter "significant" defects (depth > 3px) — these are the valleys *between* scallops.
   - Score the contour by:
     - **Number of significant defects** (clouds = many; door swings = ≤1; circles = 0)
     - **Depth coefficient of variation** (clouds = low; random shapes = high)
     - **Spacing coefficient of variation** along the perimeter (clouds = regular; random = irregular)
5. Apply a score threshold; everything above = cloud.
6. Emit overlay PNG: original page in background, detected clouds outlined green with score annotation, borderline rejects in faint red so we can tune.

## Files

- `discover.py` — one-shot helper that lists every page in the fixture PDFs with the sheet ID we extract from it. Used to find the right page indices for `detect.py`.
- `detect.py` — the experiment itself. Run with `python experiments/2026_04_cloud_detector/detect.py`.
- `output/` — overlay PNGs and any other artifacts.

## Test pages (per `detect.py:PAGES`)

| Label | Source | What we expect to find |
|---|---|---|
| `rev1_p00_index` | Rev 1 PDF, page 0 | Sheet index. Many small row-bracket clouds (rectangular shape, scallops on all four sides). The hardest test for the detector — small, dense, intersecting table grid lines. |
| `rev1_p01_GI104` | Rev 1 PDF, page 1 | 5TH FLOOR CODE PLAN. Two medium clouds containing FEC label + exit-light symbol. Sparse plan content; clouds should be cleanly closed. |
| `rev1_p04_SF110` | Rev 1 PDF, page 4 | 4TH FLOOR FRAMING PLAN. One cloud around a filled black square in a wall. Dense structural content nearby — risk: framing lines confused with cloud arcs. |
| `rev1_p06_AD104` | Rev 1 PDF, page 6 | DEMO 4TH+5TH FLOOR. Cloud around X-in-hexagon symbol with a leader to a wall, and an AD202 cross-reference arrow that grazes the cloud edge. Multi-drawing page (two drawing badges). |
| `rev2_AE107_1_R1` | Rev 2 standalone PDF | Rev 2 grab-bar revision. Different package, different sub-architect — a cross-style sanity check. |

## What "good" looks like

- Every visible cloud on each test page outlined in green with score ≥ threshold.
- No green outlines on door swings, callout bubbles, walls, framing elements, dimension lines, or text.
- Per-cloud scores cluster well above the threshold; per-non-cloud scores cluster well below. A clear gap = robust detector.

## What we'll do if it doesn't work

- **Many clouds missed (under-detection):** investigate fragmentation — clouds may not close as a single contour because they overlap grid/wall lines. Add Hough-line removal of straight features before contour finding, or work on a thinned skeleton image.
- **Many false positives (over-detection):** tighten the score, add geometric checks (e.g., scallop arc-length consistency, all-bulges-same-direction).
- **Both:** pivot to template matching (one canonical scallop, slid across the page) or to a small purpose-trained detector. Document the pivot here before any code in `revision_tool/` changes.

---

## Iteration 1 results (convexity-defect approach)

**Verdict: partial success — the geometric prior works, but the convexity-defect primitive is too generic to be sufficient on its own.**

### What worked

- Index row-bracket clouds *were* detected (visible as green/colored outlines along the left edge of each row group in `output/rev1_p00_index.png`).
- GI104's smallest clouds scored at the top of their page (`score=0.61`, `arc%=1.00`, `solidity=0.87`, `perimeter=499`) — these are almost certainly the real FEC + exit-light clouds.
- Adding the **inter-defect arc-fraction filter** (segment between two convexity defects must be an arc, not a chord) correctly killed many false positives that the original approach made: it removes stars, text-box edges, and X-in-bubble shapes whose "defects" are actually corners of straight-line meetings, not scallop joins.
- The **solidity range filter** killed filled black squares (columns) and other fully-convex shapes.
- Runtime is fine: 5 pages at 300 DPI in ~10 seconds.

### What didn't work

- **Cloud outlines that overlap other drawing content lose contour purity.** When a cloud is drawn over grid lines (index) or walls (drawing pages), `findContours` returns a tangled contour that's part-cloud, part-background. The "between defects" segments are then a mix of arcs (real scallops) and straight runs (gridlines), polluting both `arc_fraction` and `depth_cv`. This is the dominant failure mode.
- **Generic concave-bumpy shapes survive.** Even with the arc filter, contours like leader arrows, life-safety symbols, and complex callout boxes can have multiple curve segments and pass.
- **Real cloud scallops have very low `depth_cv` (~0.1–0.3) on a clean cloud,** but our measured `depth_cv` values are universally 0.4–1.0 because of the contour pollution above. Penalizing `depth_cv` harder would correctly reject the noise but also kills real clouds whose contour has been polluted.

### Root cause

The convexity-defect primitive measures "how concave is this contour", but it doesn't actually verify "is this a chain of repeating arc primitives". It's a *consequence* of being a cloud, not the *defining feature*. The defining feature is the arc-chain itself.

### Decision

Don't continue twiddling thresholds on this approach. Pivot the next iteration to one of:

- **Template matching for a canonical scallop arc**, multi-scale, then chain consecutive matches into clouds. Most aligned with the "scallop chain" mental model. Should be highly discriminative because no other element on the page repeats a small arc primitive in a chain. ~2-3 hours.
- **Hough-line removal first** (strip straight lines from the binary, then run the same contour pipeline). Cheapest pivot. ~1 hour. But doesn't address the fundamental limitation.
- **Skeletonize, then walk the skeleton looking for periodic curvature.** Theoretically the cleanest solution. Compute-heavy but works on large images at reduced resolution. ~3-4 hours.

Recommended path: **template matching** as iteration 2. Cleanest mapping from the geometric prior to the implementation, and it gives us per-scallop confidence (not just per-contour), which means we can reason about cloud completeness and partial occlusions.
