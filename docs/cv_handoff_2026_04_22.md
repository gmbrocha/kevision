# CV Handoff — 2026-04-22

This is the "if I get hit by a bus" document for the revision CV work.
The repo is messy, but there are now a few genuinely good pieces worth
salvaging into a cleaner project later.

## What works now

### 1. Delta detection is in good shape

**Pipeline**

`denoise_1.py -> denoise_x.py -> denoise_2.py -> delta_v4/detect.py`

**Key idea**

- Delta geometry is detected from the denoised raster.
- The digit label is attached from the PDF text layer, not from the rendered
  digit surviving denoise.
- Later revision sheets may contain older digits (`1`, `2`, `3`, ...). We
  detect all deltas, label all deltas, then filter to the current revision's
  `active_deltas`.

**Important files**

- `experiments/delta_v3/denoise_1.py`
- `experiments/delta_v3/denoise_x.py`
- `experiments/delta_v3/denoise_2.py`
- `experiments/delta_v4/detect.py`

**Best canonical result**

- `experiments/delta_v4/output/Revision #1 - Drawing Changes_p17_denoise_2_delta_v4_overlay.png`
- `experiments/delta_v4/output/Revision #1 - Drawing Changes_p17_denoise_2_delta_v4_overlay_results.json`

On Rev1 p17 (`AE122`), `delta_v4` gets `10/10` highlighted deltas with `0`
false positives.

**Useful JSON contract**

`delta_v4` writes:

- `all_deltas`
- `active_deltas`
- `historical_deltas`
- `geometry_only_deltas`

Each delta now includes:

- triangle geometry
- attached digit
- `digit_source`
- `digit_centroid`
- `digit_bbox`

This is the clean handoff for downstream cloud work.

## Cloud work: what we learned

### 2. Page-wide cloud detection is the wrong starting point

The older cloud detector experiments are useful for primitives, but as a
production strategy the page-wide search is too noisy and too brittle.

**Relevant old experiment**

- `experiments/2026_04_cloud_detector_v2/`

**Useful parts to salvage**

- `stages/mask_text.py`
- `stages/mask_lines.py`
- `stages/detect_scallops.py`

Those stages are still valuable locally around a delta ROI.

### 3. Delta-anchored local ROI is the correct framing

The new cloud work should start from:

- `active_deltas` only
- local ROI around each active delta
- local cleanup + local candidate generation

This massively reduces the search space and lines up with the drafting
convention better than any whole-page search.

### 4. The cloud is a closed scalloped polygon in the drawing

Important constraint from the user:

- In the source drawing, the revision cloud is a **closed scalloped loop**.
- If it appears partial, that is damage from preprocessing / overlap.
- The cloud shape is **dynamic**, not necessarily "4 sides / 4 corners."
  It can be rounded, stretched, or L-shaped.
- The delta may intersect the cloud, may connect via a straight leader, or may
  appear visually detached if the leader is broken.

So the cloud detector should **not** require:

- rectangular loop shape
- top/bottom/left/right side pairs only
- direct delta-cloud attachment

It **should** assume:

- a damaged closed loop made of repeated scalloped contour fragments
- near an active delta

### 5. Local line-masked ROIs can look surprisingly good

Some local outputs are promising. Example:

- `experiments/cloud_anchor_v1/output/Revision #1 - Drawing Changes_p17/Revision #1 - Drawing Changes_p17_delta07_roi_line_masked.png`

This supports the strategy:

- detect active delta
- build local ROI
- mask text + long lines locally
- extract the cloud locally

## Current cloud experiment

### 6. `cloud_anchor_v1` exists, but it is still experimental

**File**

- `experiments/cloud_anchor_v1/detect_local_clouds.py`

**What it currently does**

- reads `active_deltas` from the `delta_v4` JSON
- renders the raw page
- applies text mask + line mask
- builds local ROIs around each active delta
- proposes crop boxes via connected-component neighborhoods
- tries to promote some proposals into `loop_mask`s using local contour scoring

**Outputs**

- per-delta raw ROI
- per-delta line-masked ROI
- per-delta overlay
- per-delta crop
- sometimes per-delta loop overlay / loop mask / loop masked crop
- per-page JSON summary

**Current results**

- Some anchors promote to plausible `loop_mask`s.
- Others fall back to `bbox_crop`.
- There are still real false-positive modes where fixtures, labels, or nearby
  room geometry win over the cloud.

**Example outputs**

- `experiments/cloud_anchor_v1/output/Revision #1 - Drawing Changes_p17/`
- `experiments/cloud_anchor_v1/output/260309 - Drawing Rev2- Steel Grab Bars_p11/`

## Key failure modes found so far

### 7. Toilets and fixture geometry are real confounders

Toilets can sit right beside a cloud and look like clean closed contours.
The good news is that they usually do **not** merge with the cloud; the bad
news is they can still win naive contour scoring.

Observed issue:

- a contour scorer that values closure too strongly will pick the toilet or a
  fixture symbol instead of the cloud.

### 8. Triangle erasure can hurt loop reconstruction

Erasing the triangle before loop scoring seemed sensible at first, but when the
triangle intersects or touches the cloud, erasing it can damage the correct
contour more than the wrong one.

Takeaway:

- treat the triangle as evidence / context, not something that must always be
  removed before local loop reasoning

### 9. Simple scallop-hit or contour scoring alone is not enough

Tried so far:

- bbox from nearby scallop hits
- connected-component seed neighborhoods
- contour scoring on local crops
- contour scoring with local closing kernels
- contour scoring with scallop-hit support

All of these help, but none of them alone is fully reliable yet.

## What looks most promising next

### 10. Best next classical-CV direction

The next real attempt should be:

1. Delta-anchored local ROI
2. Local text/line mask
3. Generate a few cloud candidates:
   - component-neighborhood crop
   - contour-loop candidates after local close
   - maybe fragment-bridged loop candidates
4. Score candidates by **cloudness**, not just closure:
   - repeated scallop structure
   - many curvature peaks
   - scallop-hit support on the contour
   - low smooth-oval / fixture-like compactness
   - plausibly near active delta
5. If a strong closed loop exists, emit mask
6. Otherwise emit crop proposal

### 11. GenAI should be an adjudicator, not the primary detector

If multimodal genAI is used later, the right role is:

- rank 3-5 delta-local cloud candidates
- explain which candidate is actually the revision cloud
- help with ugly edge cases

It should not be the sole geometry source or the sole authority.

The safest future architecture is:

- classical CV proposes candidates
- genAI adjudicates low-confidence cases
- human review remains in the loop for liability-sensitive outputs

## What to salvage into a clean project later

### Keep

- `experiments/delta_v3/denoise_1.py`
- `experiments/delta_v3/denoise_x.py`
- `experiments/delta_v3/denoise_2.py`
- `experiments/delta_v4/detect.py`
- `experiments/2026_04_cloud_detector_v2/stages/mask_text.py`
- `experiments/2026_04_cloud_detector_v2/stages/mask_lines.py`
- `experiments/2026_04_cloud_detector_v2/stages/detect_scallops.py`

### Keep as reference only

- `experiments/cloud_anchor_v1/detect_local_clouds.py`

This file is valuable because it records what was tried and what failed, but it
is still experimental and should probably be rewritten rather than promoted as-is.

### Likely clean-project shape

- `detect/delta.py`
- `detect/cloud_candidates.py`
- `detect/cloud_loops.py`
- `detect/cloud_masks.py`
- `adjudicate/clouds.py`

## Immediate next steps

1. Keep improving local cloud extraction for one more pass.
2. Make `cloud_anchor_v1` emit multiple candidate masks/crops instead of just one.
3. Build an adjudication bundle for hard cases:
   - raw ROI
   - line-masked ROI
   - delta overlay
   - candidate overlays
   - candidate masks
   - candidate scores
4. Later, optionally add multimodal ranking on top of that bundle.

## Blunt summary

- **Delta detection:** good and worth salvaging.
- **Cloud detection:** not solved yet, but the correct framing is now known:
  delta-local, closed-loop, scalloped-polygon reasoning.
- **Repo state:** messy, but there is now enough signal here to start a cleaner
  project later and transplant the good parts instead of re-deriving them.
