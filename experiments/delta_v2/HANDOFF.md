# Morning handoff — pick up here

## Where we are

**Test fixture:** `Revision #1 - Drawing Changes.pdf` page 17 (sheet AE122).

**Ground truth:** 10 Δ markers in AE122. (Initially thought 8 — found the
extra 2 only after the denoise cleanup made them visible.)

**Current pipeline output:** `experiments/delta_v2/06_arcs_removed.png`.
This is the cleanest-yet input image for detection. Pipeline:

1. `run_denoise_bases_fixed.py` → `03_denoise_AE122_threshold_150_bases_fixed.png`
   - threshold=150 binarization
   - vertical-line mask (kernel 30px)
   - **NEW** thickness-aware horizontal mask (preserves Δ bases touching walls)
   - filled-blob mask
   - 3×3 dilation of combined mask
2. `denoise_part_2.py` → `04_text_alpha_removed.png` → `05_rotated_removed.png` → `06_arcs_removed.png`
   - step 4: erase every word containing alpha chars (915 words)
   - step 5: erase every word at 90° rotation (117 words, 108 of them numeric)
   - step 6: drop ink components not touching a halo around any surviving
     pure-upright-numeric word

## Detection state (last run, BEFORE bases-fix and updated step 6)

`detect_on_custom_denoise.py` on `06_arcs_removed.png`:
- Tier 1: **0** with-digit hits (3 candidates, all without digit)
- Tier 2: 21 markers, **7/8 of digit "1"** correctly identified, 14 false positives

That was on the old (broken-base) `06`. We now have a freshly regenerated `06`
built on top of the bases-fixed input — has not been re-tested by the detector yet.

## First two things to do tomorrow

1. **Re-run detection on the NEW `06_arcs_removed.png`** (the one rebuilt from
   bases-fixed). Command:
   ```
   python experiments/delta_v2/detect_on_custom_denoise.py
   ```
   Compare:
   - Did Tier 1 finally find any clean triangles now that bases are intact?
   - Of the 10 real Δs, how many got marked? Target: 10/10.
   - How many false positives? (Was 14 last run.)

2. **Inspect the 2 newly-discovered Δs** (the ones we hadn't seen until
   cleanup). Note their approximate locations on the page so we can
   ground-truth detection coverage going forward.

## Then dial in detection

Detection is currently the rough part. Likely angles to attack, in order of
expected payoff:

- **Lower Tier 1 threshold or relax 3-vertex constraint slightly** — bases are
  back, but Tier 1 might still be flunking on tiny outline gaps. Consider:
  - approxPolyDP epsilon: bump from 5% to 6-7%
  - allow polygons with 3-4 vertices (collapse near-collinear vertices to 3)
  - or: morphological close (small isotropic kernel, 2-3px) on the search
    image right before contour detection, to bridge tiny gaps
- **Tier 2 false-positive triage:** the 14 FPs were mostly digits in
  rectangles + dimension digits. Now that step 5 wipes 108 rotated digits,
  a chunk of those FPs should be gone. Check what's left and decide.
- **Tier 2 outline density threshold:** currently 0.55. If recall is good
  but precision suffers, bump to 0.65-0.70.

## Promotion checklist (when AE122 hits 10/10)

When the new pipeline reliably catches all 10 Δs on AE122:

- [ ] Promote `horizontal_mask_thickness_aware` from `run_denoise_bases_fixed.py`
      into `detect_deltas.build_delta_search_image`.
- [ ] Add the digit-halo / arc-removal logic from `denoise_part_2.py` as
      optional later passes in `build_delta_search_image` (or a separate
      preprocessing function).
- [ ] Re-validate on AE109 (Rev 1, page 11) — should still pass since we
      were 2/2 on green there before.
- [ ] Re-validate on the Rev 2 page that uses these markers.
- [ ] Update `experiments/2026_04_delta_marker_detector/README.md` with the
      new findings and tunables.

## Known limitations to revisit later

See `experiments/delta_v2/KNOWN_LIMITATIONS.md`:
1. Δ base collinear with a long thin horizontal feature → still wiped.
   Mitigation candidates already documented.

## Files in delta_v2/ as of handoff

- Scripts:
  - `run_denoise.py` — original threshold A/B (keep for reference)
  - `run_denoise_bases_fixed.py` — current part-1 with thickness-aware H mask
  - `denoise_part_2.py` — part-2 (text/rotated/arc removal)
  - `detect_on_custom_denoise.py` — runs Tier 1 + Tier 2 on a custom denoised image
- Notes:
  - `KNOWN_LIMITATIONS.md`
  - `HANDOFF.md` (this file)
- Images (current pipeline outputs):
  - `01_denoise_AE122.png` (baseline, threshold=100)
  - `02_denoise_AE122_no_horizontal.png` (baseline, h-mask off)
  - `03_denoise_AE122_threshold_150.png` (baseline, threshold=150)
  - `03_denoise_AE122_threshold_150_bases_fixed.png` ← **current part-1 winner**
  - `04_text_alpha_removed.png` (built on bases-fixed)
  - `05_rotated_removed.png` (built on bases-fixed)
  - `06_arcs_removed.png` ← **current pipeline output, untested by detector**
- Older overlays (built on the broken-base inputs, kept for comparison):
  - `03_denoise_AE122_threshold_150_deltas.png`
  - `06_arcs_removed_deltas.png`
