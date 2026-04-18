# Experiment: Δ Revision Marker Detector

**Status:** in progress

**Goal.** On a drawing page, find every Δ (delta) revision marker — small equilateral triangle outline with a single revision digit inside (1, 2, 3, ...). The Δ marker is the cleanest possible anchor for cloud detection: it's geometrically constrained, contains the revision number explicitly, and per user observation always sits adjacent to its cloud.

If we find every Δ on the page reliably, we collapse the cloud-detection problem from "search all 12,000×9,000 pixels for scallop chains" to "search a few hundred pixels around each Δ".

## Approach (cascade)

1. **Threshold + findContours** on the raw rendered page (no cleaning needed — per user observation, the Δ outline is rarely fully crossed by content).
2. **Convex hull + approxPolyDP** on each contour. If the simplified hull has 3 vertices that form an equilateral triangle (sides within ~15% of each other, angles within ~12° of 60°), it's a candidate Δ. The hull-based approach handles the partial-occlusion case (an 11-px door tail across one vertex) because the hull of the merged contour is still triangular.
3. **PDF-text-digit confirmation.** Pull all single-character text words from the PDF text layer. For each candidate triangle, find a digit ("1"–"9") whose centroid sits inside the triangle's polygon. No digit → reject. Digit present → record (triangle, digit).
4. **Filter by current revision** (e.g., for Rev 2 processing keep only digit == "2"). Other-revision digits are kept for diagnostics but greyed out in the overlay.

## Test page

`Drawing Rev2- Steel Grab Bars` page 12 (1-indexed) = page 11 (0-indexed) = `AE109` 5TH FLOOR PLAN - BUILDOUT. User flagged this page because at least one Δ marker is "nicely fucked up" by adjacent linework — a real test of robustness.

## Output

`output/AE109_deltas.png` — original page rendered at 300 DPI with detected triangles overlaid:
- Bright green outline + green digit label = current-revision (Rev 2) Δ
- Grey outline + grey digit label = older-revision Δ (still detected, just not for this rev)
- Faint red outline = candidate triangle with no digit inside (reject)
