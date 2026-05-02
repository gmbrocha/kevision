# CloudHammer Pivot Plan: Freeze the Ruler Before More Training

## Summary

The current pivot is to stop training-loop momentum until CloudHammer has an
honest ruler. The immediate goal is to separate what the YOLO model knows from
what the surrounding pipeline fixes, then evaluate both against frozen
full-page labels.

GPT is approved broadly for this current client/project. Use it heavily for
provisional labeling, audit acceleration, and future synthetic planning, but do
not blend provisional truth with final human-audited truth in reporting.

## Priority Order

1. Build the touched-page registry and freeze guards.
2. Select and freeze `page_disjoint_real` using all eligible page-clean full
   pages unless that removes rare training-needed positives.
3. Generate GPT-provisional full-page labels for frozen real pages.
4. Produce overlays/contact sheets for human audit.
5. Run baseline eval for both `model_only_tiled` and `pipeline_full` against
   the same frozen full-page labels.
6. Only after the real baseline exists, implement `synthetic_diagnostic` from
   the grammar.

## Key Changes

- Record a project-specific GPT/API exception:
  - Broad GPT use is approved for this current project.
  - Preserve future security gates for later projects.
- Maintain three separate eval subsets:
  - `gold_source_family_clean_real`: pristine real full-page holdout, likely
    tiny or empty until new untouched source-family pages exist.
  - `page_disjoint_real`: practical frozen real eval; exact pages must never
    enter training, mining, relabel loops, synthetic backgrounds, or threshold
    tuning.
  - `synthetic_diagnostic`: controlled synthetic stress eval; useful for
    diagnosis, never proof of real-world performance.
- Report all eval metrics separately by subset. Do not blend real and synthetic
  scores.
- Use GPT-provisional full-page labels first, with label status recorded as
  `gpt_provisional`, `human_audited`, or `human_corrected`.

## Implementation Changes

- Documentation freeze:
  - Update `PLAN_PIVOT_5_2_26.md` with this pivot plan.
  - Add cross-reference from `CLOUDHAMMER.md`.
  - Update roadmap language so the active blocker is frozen full-page
    evaluation, not more immediate training.
- Touched-page registry:
  - Scan all known reviewed manifests, candidate manifests, eval manifests,
    review batches, random crop manifests, and whole-cloud outputs.
  - Emit page/source touch status and reason.
  - Add guard checks that reject frozen real pages from future
    train/review/synthetic candidate manifests.
- Frozen real eval:
  - Select all eligible page-clean full pages for `page_disjoint_real`, unless
    manual inspection shows they contain rare positives needed more urgently for
    training.
  - Emit full-page eval manifests with source/page keys, render paths, subset
    names, leak status, and label status.
  - Preserve empty label files for true no-cloud pages.
- GPT-provisional labeling:
  - Generate full-page labels in page coordinates.
  - Produce overlays/contact sheets for audit.
  - Do not treat provisional labels as final promotion truth without stating
    their status.
- Baseline evaluation:
  - `model_only_tiled`: YOLO tiled full-page inference plus NMS and
    page-coordinate mapping only.
  - `pipeline_full`: current CloudHammer inference, grouping, cropper,
    filtering, and export behavior.
  - Compare both against the same frozen full-page labels.

## Synthetic Cloud Grammar v1

Do not implement synthetic generation yet, except for grammar/spec stubs.
Synthetic work begins only after the real full-page baseline exists.

Primary goal: create synthetic diagnostic examples by adding realistic
single-loop revision-cloud contours onto real no-cloud blueprint backgrounds.

Generation order:

1. Select a real no-cloud page or page region as background.
2. Select a placement area without a real cloud.
3. Generate a closed footprint shape.
4. Convert the footprint into a legal contour path.
5. Render cloud-chain sections along the contour.
6. Apply realism degradation.
7. Save full-page image, full-page label, and generation metadata.

Shape families:

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

Connector grammar:

- Connectors: `N`, `S`, `E`, `W`
- Legal sections: horizontal `E-W`, vertical `N-S`, corners `N-E`, `E-S`,
  `S-W`, `W-N`
- Partial end caps `N`, `S`, `E`, `W` are allowed only for intentionally
  clipped partial clouds.
- Closed clouds must form one continuous loop.
- No dangling ends, T-junctions, 4-way intersections, self-intersections,
  branching, or overlapping contours in v1.

Footprint constraints:

- Prefer orthogonal-ish closed shapes with rounded/scalloped edges.
- Avoid random spaghetti, tiny ambiguous loops, page-swallowing shapes except
  explicit large-region tests, and dense perfect symmetry.
- Limit dents/notches so each shape still reads as one revision cloud.

Rendering rules:

- Render repeated revision-cloud chain segments, not smooth generic outlines.
- Prefer real extracted client cloud-chain fragments if available; otherwise
  use closely matched synthetic segments.
- Vary spacing, arc size, stroke thickness, opacity, and local jitter.
- Do not make synthetic clouds cleaner than real clouds.

Realism degradation:

- opacity variation
- stroke weight variation
- slight blur/raster softness
- scan/compression noise
- broken/faint gaps
- local contrast differences
- overlap with linework
- coordinate jitter
- occasional partial occlusion by drawing lines or text

Label rules:

- Generate labels automatically from final visible cloud extent.
- Use class `cloud_motif`.
- For clipped clouds, label only the visible portion.
- Save labels in YOLOv8-compatible full-page coordinate space.

Synthetic diagnostic rules:

- Keep separate from real eval subsets.
- Use held-out no-cloud backgrounds not used for synthetic training
  augmentation.
- Use fixed random seeds.
- Record metadata for every example.
- Report by scenario family, not only overall score.

Scenario families:

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

Later synthetic training rules:

- Training-only augmentation.
- Do not reuse diagnostic eval backgrounds.
- Do not reuse exact diagnostic seeds/configs.
- Keep real-only eval as the source of truth.
- Start with modest synthetic ratios.

## Test Plan

- Unit-test source/page normalization and touched-page registry matching.
- Unit-test freeze guards against train/review/synthetic manifest
  contamination.
- Dry-run page selection and inspect every selected `page_disjoint_real` page.
- Verify every frozen page has render path, label path, overlay path, and label
  status.
- Run `model_only_tiled` and `pipeline_full` against the same frozen manifests.
- Confirm reports stay separated by `gold_source_family_clean_real`,
  `page_disjoint_real`, and `synthetic_diagnostic`.
- Add grammar validation tests before synthetic generation: legal connectors,
  closed loop validity, no v1-forbidden intersections, and reproducible seeds.

## Assumptions

- Broad GPT use is approved for this current project only.
- `gold_source_family_clean_real` may be unavailable until a new untouched
  package arrives.
- `page_disjoint_real` is the main steering eval for this cycle.
- GPT-provisional labels are acceptable for rapid baseline creation, but their
  provisional status must remain visible.
- No synthetic image generation starts until the real full-page eval baseline
  exists.
