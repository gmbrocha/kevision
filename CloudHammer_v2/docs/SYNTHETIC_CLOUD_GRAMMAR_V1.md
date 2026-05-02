# Synthetic Cloud Grammar v1

Do not implement full synthetic generation until the real full-page eval
baseline exists. For now, this is a grammar/spec stub.

## Purpose

Create synthetic diagnostic examples by adding realistic revision-cloud contours
onto real no-cloud blueprint backgrounds. Synthetic diagnostics are separate
from real eval and are not proof of real-world performance.

## Generation Order

1. Select a real no-cloud page or page region as the background.
2. Select a target placement area without a real cloud.
3. Generate a closed footprint shape.
4. Convert the footprint into a legal contour path.
5. Render cloud-chain sections along the contour.
6. Apply realism degradation.
7. Save full-page image, full-page label, and generation metadata.

## Shape Families

- small compact blobs
- medium rectangular/rounded clouds
- large clouds around broad drawing areas
- long skinny horizontal clouds
- long skinny vertical clouds
- L-shaped clouds
- C-shaped clouds
- one or two controlled dents/notches
- edge-clipped partial clouds
- dense-linework overlap clouds
- mostly-empty-background clouds

Defer branching or overlapping cloud contours for v1, even though they exist
infrequently in real data. Add them later as a separate scenario family.

## Tile / Connector Grammar

Connectors:

- `N`
- `S`
- `E`
- `W`

Legal sections:

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

- Closed synthetic clouds form one continuous loop.
- Every non-partial section connects to exactly two valid neighbors.
- No dangling ends in closed clouds.
- No T-junctions in v1.
- No 4-way intersections in v1.
- No self-intersections in v1.
- Partial end caps are allowed only for clouds intentionally clipped by the
  crop/page boundary.

## Footprint Constraints

- Prefer shape-first closed footprints.
- Prefer orthogonal-ish closed shapes with rounded/scalloped edges.
- Avoid random spaghetti.
- Avoid extremely tiny ambiguous loops.
- Avoid swallowing nearly the entire page except explicit large-region tests.
- Limit dents/notches so the shape remains one revision cloud.
- Avoid dense repeated perfect symmetry.

## Rendering Rules

- Render realistic revision-cloud chain segments, not smooth generic outlines.
- Prefer real extracted client cloud-chain fragments if available.
- Otherwise use closely matched synthetic segments.
- Vary spacing, arc size, stroke thickness, opacity, and local jitter.
- Do not make synthetic clouds cleaner than real clouds.

## Realism Degradation

- opacity variation
- stroke weight variation
- slight blur or raster softness
- scan/compression noise
- broken or faint gaps
- local contrast differences
- overlap with existing linework
- coordinate jitter
- occasional partial occlusion by existing drawing lines or text

## Labels

- Auto-generate YOLOv8-compatible full-page labels.
- Use class `cloud_motif`.
- Label the complete visible extent of the synthetic cloud.
- For clipped clouds, label only the visible portion.

## Diagnostic Reporting

- Keep `synthetic_diagnostic` separate from real eval.
- Do not blend synthetic metrics with real metrics.
- Use held-out no-cloud backgrounds not used for synthetic training
  augmentation.
- Use fixed random seeds.
- Record generation metadata for every example.
- Report by scenario family.

## Scenario Families

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

## Later Synthetic Training

- Keep synthetic augmentation training-only.
- Do not reuse synthetic diagnostic eval backgrounds.
- Do not reuse exact diagnostic seeds/configs.
- Keep real-only eval as the source of truth.
- Start with modest synthetic ratios.
