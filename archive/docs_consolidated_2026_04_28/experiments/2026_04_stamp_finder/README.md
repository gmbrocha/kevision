# Experiment: Stamp Finder

**Status:** in progress (just started)

## Idea (one paragraph)

A revision-cloud scallop is a **2-arc motif** with a fixed big/small radius ratio (~1.77 measured) and a fixed center-to-center distance (~1.28 · r_big measured). The motif is rigid: scale and rotation only. Find arcs in the raw/cleaned image, complete each to a circle, then pair circles whose **radius ratio AND center spacing** are both consistent with the motif at some shared scale `s`. The pair geometry is wildly more discriminative than any single arc primitive — door swings, dimension fillets, and seal arcs do not have a smaller companion arc at the right ratio at the right distance.

## Why this is different from cloud_detector_v2

`v2` (`../2026_04_cloud_detector_v2/`) tried to detect scallop primitives via template matching on the cleaned image. The line-mask stage nicked every scallop into dashes and template matching starved. It also assumed scallops are "puffy bumps" — same-orientation chains of identical arcs.

This experiment goes one level lower. It does not try to detect a scallop *shape*. It detects circles (HoughCircles or RANSAC arc fits), then uses the **stamp invariants** as the discriminator. Edge fragments are fine; you just need enough vote support per arc for HoughCircles' accumulator to find a center.

## Measured stamp parameters (from `../new_cloud_detect_single_step/measurements/`)

| Sample | source | r_big | r_small | ratio | center_dist | dist / r_big |
|---|---|---|---|---|---|---|
| step_07_scallops_overlay | full-res page | 59.5 | 34.0 | 1.752 | 75.9 | 1.276 |
| temp_scallop | full-res page | 92.0 | 51.3 | 1.795 | 118.2 | 1.285 |
| test.png run 1 | hand-cleaned diag | 19.41 | 11.73 | 1.655 | 25.11 | 1.293 |
| test.png run 2 | hand-cleaned diag | 19.67 | 11.05 | 1.779 | 25.66 | 1.304 |
| test.png run 3 | hand-cleaned diag | 19.55 | 12.17 | 1.606 | 24.98 | 1.278 |
| test.png run 4 | hand-cleaned diag | 19.65 | 11.62 | 1.691 | 25.32 | 1.289 |
| test.png run 5 | hand-cleaned diag | 20.04 | 11.88 | 1.687 | 25.26 | 1.260 |

Working invariants (post-test.png):

- `radius_ratio_big_over_small ≈ 1.70 ± 0.10` (real spread + measurement noise from short partial arcs; small radius is the noisy one)
- `center_distance / r_big ≈ 1.285 ± 0.025` (rock solid across all 7 samples — this is the real discriminator)
- `center_distance / r_small ≈ 2.18 ± 0.15`

## Pipeline (planned)

1. **`find_circles.py`** — run `cv2.HoughCircles` on a cleaned input page (or arbitrary crop), dump every candidate circle as JSON + overlay PNG. No filtering. Eyeball: do real scallops show up as candidate circles? If yes, proceed. If no, drop to RANSAC arc fitting on Canny edges.
2. **`find_pairs.py`** — load circle dump, enumerate all pairs (yes O(n²), accepted), filter by `(ratio ≈ 1.77) AND (dist/r_big ≈ 1.28)`. Dump matched pairs as overlay + JSON.
3. **`find_chains.py`** — group matched pairs into runs that share a stamp scale `s` and lie on a smooth curve. Output one polyline per cloud.
4. **(later)** wire into `revision_tool/` so Kevin's changelog gets real cloud crops.

## Inputs

Default test set re-uses `cloud_detector_v2` outputs (already cleaned of text + structural lines):

- `../2026_04_cloud_detector_v2/output/rev1_p00_index_02_lines_masked.png`
- `../2026_04_cloud_detector_v2/output/rev1_p01_GI104_02_lines_masked.png`
- `../2026_04_cloud_detector_v2/output/rev1_p04_SF110_02_lines_masked.png`
- `../2026_04_cloud_detector_v2/output/rev1_p06_AD104_02_lines_masked.png`
- `../2026_04_cloud_detector_v2/output/rev2_AE107_1_R1_02_lines_masked.png`

All five are 12600 × 9000 grayscale. For fast iteration `find_circles.py` accepts `--crop x,y,w,h`.

## Quick start

```powershell
# from repo root, with .venv active
python experiments\2026_04_stamp_finder\find_circles.py `
  --image experiments\2026_04_cloud_detector_v2\output\rev1_p01_GI104_02_lines_masked.png `
  --crop 4500,3500,2500,2500 `
  --rmin 15 --rmax 110 --param2 18
```

Outputs land in `output/<image_stem>__circles.png` (overlay) and `output/<image_stem>__circles.json` (raw circle list with run metadata).

## Findings

### First run — gate check on `find_circles.py` (does HoughCircles return anything sensible?)

| Input | Crop | Hough params | Circles found | Time |
|---|---|---|---|---|
| `rev1_p01_GI104_02_lines_masked.png` | `5300,3500,2000,2000` | r=[12,110], param2=18 | 14 | 0.18s |
| `rev1_p00_index_02_lines_masked.png` | full 12600×9000 | r=[12,80], param2=18 | 952 | 6.57s |

**What the GI104 crop showed:** the 14 circles are tightly clustered into 3 groups — multiple Hough hits with near-identical centers and overlapping radii (e.g. 4 circles at full-page (6921–6934, 4982–4992) with r ∈ {28.5, 34.3, 36.6, 28.5+}). That's consistent with HoughCircles firing repeatedly on real arcs with slightly different accumulator paths. Pairing in step 2 will need NMS / cluster collapse before enumerating O(n²) pairs.

**What the full index showed:** 952 candidates is fine — the (1.281 ± 0.005) `dist/r_big` invariant is so tight that the pair filter will gut this list. Per-page runtime <10s on full res means we don't need to worry about scale optimization.

**Decision:** HoughCircles is viable as the primitive. Proceed to `find_pairs.py`.

### Step 2 — `find_pairs.py` (NMS + ordered-pair filter)

Built greedy single-link NMS (merge if center distance ≤ `0.5 · min(r_i, r_j)` AND radii within ±30%), then enumerate all ordered (big, small) pairs and keep those passing **both** invariants:

- `r_big / r_small ∈ [1.72, 1.82]` (default tol 0.05)
- `dist / r_big ∈ [1.251, 1.311]` (default tol 0.03)

| Input | Raw circles | Post-NMS | Pairs | Time (NMS + pair) |
|---|---|---|---|---|
| `rev1_p01_GI104` (2k crop @ 5300,3500) | 14 | 8 | **0** | <0.05s |
| `rev1_p01_GI104` (full 12600×9000) | 2687 | 1454 | **43** | 1.1s + 1.1s |
| `rev1_p00_index` (full 12600×9000) | 952 | 568 | **31** | 0.2s + 0.2s |

Notes on what these numbers might mean (pre-eyeball):

- **2k GI104 crop returned zero pairs.** Hough only found 14 circles in that region clustered into 3 groups, none with a smaller companion at the right distance. Most likely explanation: the crop bounds I picked were a blind guess and don't actually contain a cloud. The full-page run is the real test.
- **Full GI104 → 43 pairs.** v2 README says GI104 has 2 known FEC/exit-light clouds. If each cloud has 4–8 scallop motifs and Hough is generous, ~20 pairs per cloud is plausible. If the 43 are scattered randomly across the page, the ratio constraint isn't biting hard enough and we'll need to tighten or add a second filter.
- **Full index → 31 pairs.** v2 README says "many small row-bracket clouds" (the row-revision indicator brackets). 31 feels low for an index page that has 20+ revision brackets — possible Hough is missing the small scallops because of `--rmin 12` being too aggressive a floor relative to actual bracket arc size.

Pipeline runtime is fine end-to-end: ~5s per full page from raw image to matched-pairs JSON + overlay.

### Open questions for next run

- **Do the matched pairs land on real cloud scallops?** Critical eyeball test. If GI104's 43 pairs cluster in the two known cloud locations, the primitive works and we proceed to chain assembly. If they're scattered randomly, the filter is too loose or Hough is fitting circles to non-arc edges (long dash patterns, dimension fillets, etc.).
- **Tighten or widen tolerances?** `dist_tol = 0.03` is 5× the measured spread (0.005). Could tighten safely. `ratio_tol = 0.05` is wider than the measured spread (0.022). Both can come down once we see the false-positive distribution.
- **Drop `--rmin` to catch index brackets?** Index row brackets are visibly smaller than the FEC clouds. Try `--rmin 6` on the index page and see if pair count rises.
- **Per-pair scale clustering as a sanity stat.** Add a histogram of `scale_rbig` to the pairs JSON — real chains share a scale, random pairs don't. Easy step toward chain assembly.

### Step 2.5 — diagnostic on hand-cleaned `test.png` (visible motifs only)

Single-band Hough at the original `--rmin 12` ceiling missed every small companion arc on `test.png`. Added two new capabilities to `find_circles.py`:

- `--mode {gradient,gradient_alt}` — wraps both Hough variants. **Verdict:** `HOUGH_GRADIENT_ALT` returns 0 circles even at `param2=0.3` on these scallops; the partial arcs are too short/incomplete for its perfectness scoring. Stick with classic gradient.
- `--bands "rmin:rmax:param2,..."` — multi-pass Hough with different sensitivity per radius band. Small companion arcs need a much lower accumulator floor (`param2 ≈ 4–6`) than big arcs (`param2 ≈ 8–10`) because they have fewer edge votes.

Best-so-far run on test.png:

```powershell
python experiments\2026_04_stamp_finder\find_circles.py --image test.png --bands "5:14:4,15:25:8" --min-dist 3 --out-stem diag_dualband_v2
python experiments\2026_04_stamp_finder\find_pairs.py --circles diag_dualband_v2__circles.json --ratio 1.70 --ratio-tol 0.20 --dist-ratio 1.28 --dist-tol 0.07 --no-nms
```

→ 103 circles → 11 pairs → matched pairs cluster on ~3–4 of the visible motifs. Top horizontal chain motifs unmatched (small arcs not detected at all in that region).

### Two real bugs surfaced

**Bug 1: NMS-by-median destroys the radius.** The current NMS in `find_pairs.py` does single-link clustering and takes the per-cluster *median* of `(cx, cy, r)`. On real scallop data Hough returns multiple concentric circles for the same partial arc — fitted at the true radius plus a long tail of larger phantom radii (because a short arc underdetermines the circle and Hough drifts large). Median of (true, true, large_phantom) skews the radius up by 10–20%, which **breaks** the `dist/r_big ≈ 1.28` invariant before pairing even runs. Confirmed on test.png: a real (r=19.6, r=12.2) pair existed but NMS merged the 19.6 with a phantom 23.3 sitting 4 px away, output radius 21.45, `dist/r_big` dropped to 1.13, filter rejected. Workaround: `--no-nms`. Real fix: replace median with "pick the candidate whose perimeter best matches the actual edge pixels" (count Canny pixels within ±1 px of each candidate's circumference, keep the highest count).

**Bug 2: Recall on small arcs is the bottleneck, not pair filtering.** Even with dual-band Hough at aggressive thresholds, the small companion arcs of half the visible motifs aren't being detected. Two possible causes: (a) they're too short to clear even `param2=4`, or (b) they sit very close to other geometry (text, neighbor scallops) and get suppressed by `min_dist`. Worth trying: drop to `param2=3`, `min_dist=2`, accept the noise explosion and let the much-stricter pair filter clean it up downstream.

### Next concrete steps

1. **Replace NMS with edge-pixel scoring** in `find_pairs.py` (or move it to a helper in `find_circles.py`). For each cluster pick the candidate with max edge-pixel-count along its perimeter, not the median geometry.
2. **Sweep small-band recall.** On test.png, try `--bands "4:14:3,15:25:8"` with `--min-dist 2` and see if the missing motifs get small-arc candidates.
3. **Per-pair NMS** at the pair level — collapse pairs whose `(big_center, small_center)` are within a few pixels into a single representative pair. The 11 pairs on test.png include several near-duplicates that all describe the same motif.
4. Then re-run on the full GI104 page and recount.

### Step 3 — edge-fit NMS + pair-NMS (all three changes landed)

Implemented all three concrete steps above in one pass. `find_pairs.py` now:

- Computes a **Canny + distance-transform** of the source image once at startup.
- Scores every candidate circle by the **fraction of perimeter** that sits within `--edge-tol-px` (default 1.5 px) of a Canny edge. Score ∈ [0, 1].
- Replaces median-NMS with **score-based NMS**: greedy single-link clustering as before, but the cluster representative is the *highest-scoring* member, not the per-axis median. This preserves the true-arc fit instead of drifting toward concentric phantoms.
- Adds **pair-level NMS** anchored on the **midpoint of each (big, small) pair** (not the big-center alone — the big-center jitters too much across duplicate fits). Cluster on `midpoint within 0.5·r_big` AND `r_big within ±30%`, keep the pair with highest summed edge-support.

Run on `test.png` with the relaxed dual-band Hough:

```powershell
python experiments\2026_04_stamp_finder\find_circles.py --image test.png --bands "4:14:3,15:25:8" --min-dist 2 --out-stem diag_v3
python experiments\2026_04_stamp_finder\find_pairs.py --circles diag_v3__circles.json --ratio 1.70 --ratio-tol 0.20 --dist-ratio 1.28 --dist-tol 0.07
```

| Stage | Count |
|---|---|
| Raw Hough circles (dual-band) | 293 |
| Post edge-fit NMS | 157 |
| Pair filter pass | 19 |
| Post pair-NMS | **16** |

Visual eyeball: ~15 motifs visible in the L-shape chain on `test.png`, 16 detections, **~1:1 coverage** along the entire chain (top horizontal + right vertical + top-left stack + bottom-left isolated). Going from 1 detected pair → 16 in this session by stacking the three fixes above.

The edge-support score range was [~0.5, ~0.7] for real motif circles — partial scallops can never score 1.0 because only a fraction of the underlying circle is actually drawn. That's the right shape; tightening below ~0.4 would risk killing real motifs.

### Real next concrete steps

1. **Run the new pipeline on the full pages** (`rev1_p01_GI104`, `rev1_p00_index`) and eyeball whether matched pairs cluster on real cloud locations vs. scattered as architecture noise. The diagnostic established the geometry works; full-page tells us whether the page-scale noise floor still kills it.
2. **Build `find_chains.py`.** Group surviving pairs into runs by (similar `scale_rbig`, similar orientation of the big→small vector continuity, and proximity along a smooth curve). One polyline per cloud is the deliverable.
3. **Wire into `revision_tool/`** so the changelog crops are real cloud bounding polygons rather than the v2 placeholder.

