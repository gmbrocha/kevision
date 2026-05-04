# Experiments Retention Review - 2026-05-02

## Executive Summary

This is a report-only review of selected `experiments/` material. No files were moved,
deleted, renamed, imported, or modified as part of this review.

The important conclusion is that several experiment ideas are valuable, but only some
are represented in the active workflow today:

- Delta/triangle-marker logic is partially migrated into legacy `CloudHammer/`
  bootstrap code, but not yet captured clearly in `CloudHammer_v2/` docs as a
  lesson learned.
- Index parsing and changelog/export preview ideas appear largely superseded by
  active backend parser and deliverable-export code.
- Stamp/circle/scallop detection ideas are not materially migrated into current
  docs/code, and they are useful for CloudHammer_v2 false-positive analysis,
  synthetic diagnostic planning, and hard-negative bucketing.
- The best next action is documentation promotion, not code import. CloudHammer_v2
  should preserve these lessons before any cleanup or audited import.

## Reviewed Scope

- `experiments/2026_04_delta_marker_detector/`
- `experiments/2026_04_stamp_finder/`
- `experiments/delta_v3/`
- `experiments/delta_v4/`
- `experiments/2026_04_index_parser/`
- `experiments/extract_changelog.py`
- `experiments/preview_revision_changelog.py`

## Experiment-by-Experiment Findings

### `experiments/2026_04_delta_marker_detector/`

**Apparent purpose:** Detect revision delta/triangle markers and associate them
with revision digits.

**Key scripts/files:**

- `detect_deltas.py`
- `__pycache__/` runtime cache

**Important ideas or algorithms:**

- Render PDF pages through PyMuPDF and normalize text coordinates into the displayed
  pixel coordinate system.
- Detect equilateral triangle candidates with contour extraction, convex hulls,
  polygon approximation, side-length checks, angle checks, and digit-centroid
  containment.
- Use digit-anchored template search as a second pass: estimate triangle size from
  digit height, try candidate orientations and offsets, score outline support, and
  reject filled/dirty interiors.
- Distinguish active revision markers from historical/nonmatching revision markers.
- Produce overlays that separate target-digit, older-digit, and no-digit candidates.

**Already represented in active docs/code:**

- Partially represented in legacy `CloudHammer/` through bootstrap and ROI logic.
- Current `CloudHammer_v2/docs/MODEL_VS_PIPELINE_AUDIT.md` mentions triangle,
  marker, and delta logic at a checklist level, but does not capture the concrete
  lessons from this experiment.

**Recommended status:**

1. Promote to CloudHammer_v2 docs as a lesson learned.
2. Add future tasks for marker-context eval buckets and hard-negative mining.
3. Consider audited import only after the real full-page eval baseline exists.

### `experiments/2026_04_stamp_finder/`

**Apparent purpose:** Explore whether circular/scalloped stamp or cloud-fragment
geometry can be detected with Hough circle methods and pair geometry.

**Key scripts/files:**

- `find_circles.py`
- `find_pairs.py`
- `inspect_pairs.py`

**Important ideas or algorithms:**

- Generate multi-radius Hough circle candidates, including alternate Hough modes.
- Preserve crop offsets and produce overlays/JSON for inspectable intermediate state.
- Filter circle pairs using measured motif geometry, including radius ratio and
  center-distance ratio.
- Score edge support with Canny edges and distance transforms.
- Use non-maximum suppression on individual circle candidates and circle-pair
  candidates.
- Explicitly note that if true scallops are not present in Hough results, RANSAC
  arc fitting may be a better primitive than circle detection.

**Already represented in active docs/code:**

- Not meaningfully represented in current CloudHammer_v2 docs/code.
- Related only indirectly through current false-positive concerns around fixture
  circles, glyph arcs, symbols, and cloud-like arcs.

**Recommended status:**

1. Promote to docs as a useful false-positive and synthetic-diagnostic lesson.
2. Add future task for scallop/arc hard-negative buckets.
3. Consider audited import only as a diagnostic or hard-negative mining tool, not
   as core CloudHammer_v2 inference.

### `experiments/delta_v3/`

**Apparent purpose:** Iterative denoising and preprocessing for delta-marker
bootstrapping.

**Key scripts/files:**

- `denoise_1.py`
- `denoise_2.py`
- `denoise_x.py`
- Generated PNG outputs from denoise stages
- `__pycache__/` runtime cache

**Important ideas or algorithms:**

- Mask long vertical and horizontal drawing lines before marker detection.
- Preserve triangle-like geometry while removing walls, dimensions, filled blobs,
  and unrelated heavy linework.
- Use PDF text extraction to remove alphabetic/rotated text while preserving numeric
  anchors for marker detection.
- Remove long arbitrary-angle segments with Hough line detection while tuning segment
  length to avoid wiping triangle sides.
- Treat preprocessing as task-specific and potentially unsafe outside its intended
  marker-detection context.

**Already represented in active docs/code:**

- Partially represented in legacy `CloudHammer/cloudhammer/bootstrap/delta_stack.py`.
- Not adequately represented in CloudHammer_v2 docs.

**Recommended status:**

1. Promote the lesson that delta-denoising is useful for marker metadata but should
   not be treated as cloud evidence.
2. Add future task for converting recurring denoise targets into explicit hard-negative
   eval buckets.
3. Archive generated PNGs later after choosing any examples worth preserving as
   documentation/reference artifacts.

### `experiments/delta_v4/`

**Apparent purpose:** Geometry-first delta-marker detector that does not depend on
text seeding.

**Key scripts/files:**

- `detect.py`
- `__pycache__/` runtime cache

**Important ideas or algorithms:**

- Use line-segment detection to find triangle geometry first.
- Bucket and merge base/left/right segments.
- Build triangle candidates from endpoint and intersection geometry.
- Verify side support, base support, interior ink ratio, and geometry quality.
- Attach revision digits from PDF text only after geometry is detected.
- Separate active deltas, historical deltas, and geometry-only deltas in output JSON.
- Add a fixed-size second pass seeded from partial base fragments and estimated
  canonical side length.

**Already represented in active docs/code:**

- Partially represented in legacy `CloudHammer/` bootstrap code and tests.
- CloudHammer_v2 only references marker/delta logic abstractly in the audit checklist.

**Recommended status:**

1. Promote to CloudHammer_v2 docs as the preferred marker-detection lesson:
   geometry-first is safer than text-seeded shortcut logic.
2. Consider audited import later only as metadata generation or dataset bootstrap
   support.
3. Do not make this opaque pipeline logic part of promotion scoring until the
   model-only versus pipeline-full baseline exists.

### `experiments/2026_04_index_parser/`

**Apparent purpose:** Parse drawing index pages, revision columns, sheet rows, and
revision-marked sheet entries.

**Key scripts/files:**

- `parse.py`
- `explore.py`
- `dedupe.py`
- `debug_misses.py`
- `output/*.csv`
- `__pycache__/` runtime cache

**Important ideas or algorithms:**

- Find likely drawing-index pages by scoring header tokens and sheet-ID patterns.
- Normalize page rotation before interpreting words and table geometry.
- Detect vertical revision headers such as `REVISION #N MM/DD/YYYY`.
- Find `X` marks in revision columns and associate them with sheet rows.
- Deduplicate sheet rows and preserve revision history across revisions.
- Use targeted miss diagnostics to distinguish parser, geometry, and dedupe failures.

**Already represented in active docs/code:**

- Largely represented by active backend parser/export code, especially
  `backend/parsers/drawing_index_parser.py` and deliverable export flow.
- The experiment remains useful as provenance and debugging context.

**Recommended status:**

4. Archive later with no action after confirming active parser behavior is covered
   by tests and docs.
5. Keep in place pending human decision if parser test coverage is not yet adequate.

### `experiments/extract_changelog.py`

**Apparent purpose:** Inspect and extract useful content from a workbook-style
revision changelog source, including embedded images and cell text.

**Key scripts/files:**

- `extract_changelog.py`
- Referenced workbook: `docs/anchors/mod_5_changelog.xlsx`

**Important ideas or algorithms:**

- Treat the workbook as a reference artifact worth inspecting, not only a binary file.
- Extract sheet dimensions, cell contents, image metadata, and image anchors.
- Use workbook inspection to understand expected deliverable structure.

**Already represented in active docs/code:**

- Conceptually represented by active deliverable/export code and docs that preserve
  workbook artifacts under `docs/anchors/`.
- Not needed as active CloudHammer_v2 logic.

**Recommended status:**

4. Archive later with no action after preserving any workbook reference notes in root
   product/deliverable docs.

### `experiments/preview_revision_changelog.py`

**Apparent purpose:** Generate a preview revision changelog workbook from a demo
workspace and approved sample detections.

**Key scripts/files:**

- `preview_revision_changelog.py`

**Important ideas or algorithms:**

- Build a throwaway demo workspace for export preview.
- Select a subset of candidate detections as approved examples.
- Rebase stale absolute crop paths into the current workspace.
- Exercise the active Excel writer against realistic sample output.

**Already represented in active docs/code:**

- Superseded by active backend deliverable export code, including revision changelog
  Excel generation and review packet/export flow.
- Still useful as a reminder that preview fixtures and path rebasing can catch
  integration defects.

**Recommended status:**

2. Add future task for verified export-preview fixtures if current export tests are
   thin.
4. Archive later once deliverable/export tests cover the same behavior.

## Promote to Docs Candidates

1. Delta/marker outputs should be treated as context and dataset-selection metadata,
   not proof that a cloud exists.
2. Geometry-first marker detection is safer than text-seeded marker detection because
   it reduces shortcut learning from digits/text.
3. Delta-specific denoising is useful for marker bootstrapping but dangerous as a
   general cloud-detection signal.
4. Stamp/circle pair geometry provides a concrete source of hard-negative and
   synthetic-diagnostic scenarios around arcs, fixture circles, glyphs, and partial
   scallops.
5. Index parsing belongs primarily to the backend/product workflow; CloudHammer_v2
   should only consume page-selection implications where relevant.

Recommended destination: add `CloudHammer_v2/docs/EXPERIMENT_LESSONS.md` or add a
dedicated section to `CloudHammer_v2/docs/MODEL_VS_PIPELINE_AUDIT.md`.

## Future Task Candidates

- Add hard-negative/eval buckets for marker-neighborhood no-cloud regions, historical
  revision marker context, isolated arcs/scallops, fixture circles, crossing-line
  X-patterns, and index/table `X` marks.
- Add a rule that marker/delta context can seed review queues, crop selection, and
  metadata, but must not silently rescue or suppress model detections in promotion
  metrics.
- Add source/page filtering tests that make index pages, cover sheets, and general
  note pages explicit instead of accidental.
- Add a small export-preview fixture if current deliverable export tests do not cover
  path rebasing and approved-candidate workbook generation.
- When synthetic diagnostics are implemented, include arc/scallop stress scenarios
  based on the stamp-finder lessons.

## Possible Import After Audit Candidates

- `experiments/delta_v4/detect.py` as a metadata generator for revision-marker
  context, not as a CloudHammer_v2 model substitute.
- Legacy delta payload normalization and manifest handling from `CloudHammer/`
  bootstrap code, only after the model-only versus pipeline-full audit defines the
  boundary.
- ROI extraction concepts that use marker context to select review/training crops,
  only after ensuring frozen eval pages cannot enter training, mining, synthetic
  backgrounds, or threshold tuning.
- Stamp-finder pair scoring only as a diagnostic/hard-negative miner if the current
  false-positive work still needs explicit arc/scallop detection.

## Safe to Archive Later Candidates

- Runtime caches under the reviewed experiment folders.
- Generated denoise PNG outputs in `experiments/delta_v3/`, after preserving any
  selected visual references.
- `experiments/2026_04_stamp_finder/inspect_pairs.py`, unless manual pair inspection
  remains part of a future diagnostic workflow.
- `experiments/2026_04_index_parser/explore.py` and `debug_misses.py`, after active
  parser tests cover the same failure modes.
- `experiments/extract_changelog.py` and `experiments/preview_revision_changelog.py`,
  after deliverable/export docs and tests cover the workbook behaviors they explored.

## Unresolved Human Decisions

- Should CloudHammer_v2 allow marker/delta context as metadata-only immediately, or
  should it be held completely outside the baseline until model-only and pipeline-full
  eval numbers exist?
- Which generated delta-denoise visual examples, if any, should be preserved under
  documentation references before later archival?
- Should stamp/circle invariants become part of the synthetic diagnostic grammar, a
  false-positive eval note, or both?
- Is active backend parser/export test coverage strong enough to archive the index
  parser and changelog preview experiments later?
- Should `preview_revision_changelog.py` be converted into a verified fixture builder,
  or retired once backend export tests are improved?

## Recommended Next Action

Before importing or archiving any experiment code, add a CloudHammer_v2 lesson document
that captures the marker/delta, denoising, stamp/scallop, and index-page-selection
lessons above. The highest-value path is:

1. Create or update a CloudHammer_v2 doc for experiment lessons.
2. Add hard-negative and eval bucket tasks based on these lessons.
3. Revisit audited imports only after the frozen real eval baseline exists.
