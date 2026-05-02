# Synthetic Cloud Grammar v1

This document defines the first procedural grammar for synthetic revision-cloud
examples. Do not implement full synthetic generation yet. Keep implementation
gated until the real full-page eval baseline exists.

## Purpose

The generator should create full-page or page-region synthetic examples by
adding realistic revision-cloud contours onto real no-cloud blueprint
backgrounds.

These generated pages should support:

- `synthetic_diagnostic` eval
- later training-only augmentation
- controlled stress testing of shape, size, faintness, density, and
  false-positive-prone backgrounds

## Generation Order

1. Select a real no-cloud page or page region as the background.
2. Select a target placement area that does not already contain a real cloud.
3. Generate a closed footprint shape.
4. Convert the footprint into a legal contour path.
5. Render cloud-chain sections along the contour.
6. Apply realism degradation.
7. Save the full-page image, full-page label, and generation metadata.

## Shape Families

- small compact blobs
- medium rectangular/rounded clouds
- large clouds around broad drawing areas
- long skinny horizontal clouds
- long skinny vertical clouds
- L-shaped clouds
- C-shaped clouds
- clouds with one or two controlled dents/notches
- edge-clipped partial clouds
- dense-linework overlap clouds
- mostly-empty-background clouds

Defer branching or overlapping cloud contours for v1. Synthetic v1 should focus
on single-loop cloud contours first. Add branching/overlap later only as a
separate scenario family once the baseline synthetic generator is working and
real eval behavior is understood.

## Tile / Connector Grammar

Represent the contour as connected sections with four possible connectors:

- `N`
- `S`
- `E`
- `W`

Legal section types:

- horizontal: `E-W`
- vertical: `N-S`
- corner_NE: `N-E`
- corner_ES: `E-S`
- corner_SW: `S-W`
- corner_WN: `W-N`
- partial_end_N: `N` only, only for intentionally clipped partial clouds
- partial_end_S: `S` only, only for intentionally clipped partial clouds
- partial_end_E: `E` only, only for intentionally clipped partial clouds
- partial_end_W: `W` only, only for intentionally clipped partial clouds

Rules:

- Closed synthetic clouds should form one continuous loop.
- Every non-partial section must connect to exactly two valid neighbors.
- No dangling ends in closed clouds.
- No T-junctions in v1.
- No 4-way intersections in v1.
- No self-intersections unless explicitly testing weird failure cases later.
- Partial end caps are allowed only when the cloud is intentionally clipped by
  the crop/page boundary.

## Footprint Constraints

Generated footprints should be plausible for blueprint revision clouds.

Rules:

- Prefer orthogonal-ish closed shapes with rounded/scalloped edges, not random
  spaghetti.
- Minimum cloud size should be large enough to be visually meaningful after
  page scaling/tiling.
- Maximum cloud size should avoid swallowing nearly the entire page unless
  testing large revision areas.
- Limit dents/notches so the shape still reads as a single revision cloud.
- Avoid extremely tiny loops that would be ambiguous or useless.
- Avoid dense repeated perfect symmetry.

## Rendering Rules

The contour should be rendered as a repeated revision-cloud chain, not as a
smooth generic outline.

Preferred approach:

- Use real extracted cloud-chain fragments from the client's drawings if
  available.
- Otherwise use closely matched synthetic chain segments with the same visual
  language.
- Each chain section should connect cleanly to neighbors.
- Vary spacing, arc size, stroke thickness, and opacity slightly.
- Add small jitter so the result does not look grid-snapped.

Do not make the synthetic cloud cleaner than real clouds.

## Realism Degradation

After rendering, apply blueprint-like imperfections:

- opacity variation
- stroke weight variation
- slight blur or rasterization softness
- scan/compression noise
- broken or faint gaps
- local contrast differences
- overlap with existing linework
- slight coordinate jitter
- occasional partial occlusion by existing drawing lines or text

## Label Rules

Synthetic labels should be generated automatically from the final cloud extent.

For full-page YOLO detection labels:

- label the complete visible extent of the synthetic cloud
- for clipped clouds, label only the visible portion
- use class `cloud_motif`
- save labels in the same coordinate system expected by YOLOv8

## Synthetic Diagnostic Eval Rules

The `synthetic_diagnostic` eval set is useful but not proof of real-world
performance.

Rules:

- Keep it separate from real eval subsets.
- Do not blend its metrics with real eval metrics.
- Use held-out no-cloud backgrounds not used for synthetic training
  augmentation.
- Use fixed random seeds for reproducibility.
- Record generation metadata for every synthetic page/example.
- Report synthetic results by scenario family, not just one overall number.

Suggested scenario families:

- `compact_bold`
- `compact_faint`
- `long_skinny_horizontal`
- `long_skinny_vertical`
- `partial_clipped`
- `dense_linework_overlap`
- `low_contrast`
- `large_region`
- `notch_or_dent`
- `mostly_empty_background`

## Synthetic Training Rules Later

When synthetic data is later used for training augmentation:

- keep it training-only
- do not reuse synthetic diagnostic eval backgrounds
- do not reuse the exact same seeds/configs as `synthetic_diagnostic`
- keep real-only eval as the source of truth
- start with modest synthetic ratios before increasing synthetic volume
