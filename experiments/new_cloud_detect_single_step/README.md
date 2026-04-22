# new_cloud_detect_single_step

This folder is the "slow the fuck down" cloud CV bench.

Goal:

- stop doing 8 hidden transformations at once
- inspect one concrete delta ROI at a time
- save numbered intermediate outputs so a human can see what changed

Current cases:

1. `rev1_p17_delta07`
   - Rev 1 main PDF
   - page 17
   - active delta #7 from `delta_v4`
2. `rev2_main_p11_delta01`
   - Rev 2 main grab-bar PDF
   - page 11
   - active delta #1 from `delta_v4`

Current input variants:

1. `current_line_masked`
   - raw render -> text mask -> cloud line mask
2. `denoise_1`
   - delta pipeline stage 1 image
3. `denoise_x`
   - delta pipeline stage X image

Note:

- `denoise_x` is already the output of `denoise_1 -> denoise_x`.
- There is no separate standalone "raw -> x" image.
- `denoise_2` is intentionally excluded here because it is hostile to clouds.

Generated steps per variant:

- `step_00_input.png` — input crop with the delta triangle overlaid
- `step_01_binary.png` — thresholded / inverted binary crop
- `step_02_components_overlay.png` — connected components overlaid and labeled
- `step_03_close_k3.png`
- `step_04_close_k5.png`
- `step_05_close_k7.png`
- `step_06_close_k9.png`
- `step_07_scallops_overlay.png` — local scallop detections on the input crop
- `step_08_thickness_heatmap.png` — local thickness estimate (hotter = thicker)
- `step_09_component_thickness_overlay.png` — top components by area with median/max thickness labels
- `step_10_thin_component_filter.png` — keeps only components whose thickness profile stays mostly thin
- `step_11_hard_thin_filter.png` — removes 3px-ish support morphologically, then lightly repairs the remaining thin lines
- `step_12_pair_motif_overlay.png` — ordered paired-arc motif matches using the big/small ratio prior
- `contact_sheet.png` — one-file overview for the whole variant
- `step_13_manifest.json` — metadata for the run

Run it from the repo root:

```powershell
python "F:\Desktop\m\projects\drawing_revision\experiments\new_cloud_detect_single_step\build_step_bench.py"
```

Run just one case:

```powershell
python "F:\Desktop\m\projects\drawing_revision\experiments\new_cloud_detect_single_step\build_step_bench.py" --case rev2_main_p11_delta01
```

## Arc ratio helper

If you want to measure a big/small scallop pair manually without doing mental
gymnastics at 3am:

```powershell
python "F:\Desktop\m\projects\drawing_revision\experiments\new_cloud_detect_single_step\measure_arc_ratio.py" --image "path\to\snippet.png"
```

How to use it:

1. Left click several points along the **big** arc
2. Press `Space`
3. Left click several points along the **small** arc
4. Press `Enter`

It will save:

- an annotated PNG with fitted circles
- a JSON file with big radius, small radius, ratio, and center spacing

The window now autosizes to the displayed image so old manual resizes should not
distort the click mapping across runs.

Output goes to:

- `experiments/new_cloud_detect_single_step/measurements/`
