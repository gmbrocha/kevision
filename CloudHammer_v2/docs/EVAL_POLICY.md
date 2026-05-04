# Eval Policy

Status: canonical CloudHammer_v2 eval policy.

## Eval Subsets

Use separate named subsets:

- `page_disjoint_real`: main steering eval for this cycle
- `style_balance_diagnostic_real_touched`: diagnostic-only touched-real style
  supplement; not promotion-clean
- `gold_source_family_clean_real`: tiny pristine sanity check if available
- `synthetic_diagnostic`: controlled diagnostic wind tunnel, not proof of
  real-world performance

Do not blend scores across subsets.

`style_balance_diagnostic_real_touched` exists because the strict untouched
page-disjoint pool inside current sets is exhausted and style/source-family
skewed. It may help diagnose thick/dark and thin/light cloud behavior, dense
linework false positives, and source-family-specific distractors, but it must
not be used for promotion claims because its pages were already touched by known
training or eval manifests.

## Full-Page Truth

Full-page labels are the source of truth. Inference may tile/crop internally,
but predictions must map back to full-page coordinates for scoring.

Empty labels are required for true no-cloud pages.

## Frozen Real Page Rules

No frozen real eval page may enter:

- training
- crop extraction
- hard-negative mining
- synthetic backgrounds
- threshold tuning
- GPT/model relabel loops
- future mining

Marker/delta context, index-page parsing, and stamp/circle diagnostics must
follow the same frozen-page rule. They may not mine, relabel, tune, or generate
training crops from frozen real eval pages.

## Label Status

Labels must track status:

- `gpt_provisional`
- `human_audited`
- `human_corrected`

Reports must state label status.

For `page_disjoint_real`, GPT full-page labels are not eval truth. The frozen
real pages should be human-reviewed directly. Any GPT full-page output on these
pages is scratch/provisional only and must not be used for training, threshold
tuning, or promotion scoring.

Current human-truth review queue:
`CloudHammer_v2/eval/page_disjoint_real_human_review/manifest.jsonl`

Current human-truth label directory:
`CloudHammer_v2/eval/page_disjoint_real_human_review/labels/`

## Baseline Paths

- `model_only_tiled`: YOLOv8 tiled full-page inference with NMS and coordinate
  mapping only
- `pipeline_full`: full CloudHammer pipeline behavior

Both must evaluate against the same frozen labels.

Audit clarification:

- `model_only_tiled` excludes fragment grouping, whole-cloud confidence
  recalculation, candidate policy, marker/delta context, crop tightening, human
  review decisions, release routing, and backend manifest ingestion.
- `pipeline_full` must declare exactly which audited pipeline stages are active.
  If marker/delta context is enabled, the report must say where it entered the
  pipeline.

## Hard-Negative And Diagnostic Buckets

Track product-relevant error families separately when possible. Current
approved buckets from the experiment-retention review:

- marker-neighborhood no-cloud regions
- historical or nonmatching revision-marker context
- isolated arcs and scallop fragments
- fixture circles and symbol circles
- glyph/text arcs
- crossing-line X-patterns
- index/table `X` marks
- dense linework near valid clouds

These buckets are for diagnosis, review prioritization, and future training
selection. Do not blend them into one opaque score.

## Source And Style Diagnostic Buckets

Track cloud stroke style as visual diagnostic/eval metadata when the
information is available. Track discipline, company/EOR, source family, and
drawing set separately where known. These are not new YOLO classes for now:

- `thick_dark_cloud`
- `thin_light_cloud`
- `no_cloud_dense_dark_linework`
- `no_cloud_door_swing_arc_false_positive_trap`
- `mixed_cloud_with_dense_false_positive_regions`

The primary YOLO class remains `cloud_motif` unless a future audited decision
changes this.

Current understanding: different drawing sets may come from different
disciplines and different companies/EORs, and one company/EOR may stamp
multiple disciplines. There is no reliable universal rule that maps cloud stroke
thickness to discipline. Style may be internally consistent within a given
source family or drawing set, but stroke thickness alone does not prove
discipline, company/EOR, validity, or cloud truth.

Evaluate thick/dark and thin/light styles separately because they create
different risks. Thick/dark examples can be confused with dense dark technical
linework, pipe/duct/conduit-like runs, rounded corners, symbols, arcs, and dark
annotation clusters. Thin/light examples need explicit faint and low-contrast
recall checks. These are diagnostic metadata buckets, not class splits.

## Mixed Diagnostic Pages

Some pages contain a real revision cloud in one sub-drawing while another large
region of the same page contains high-value no-cloud false-positive traps. Do
not treat those full pages as empty-label no-cloud pages.

Specific observed candidate:

- Rasterized page:
  `F:\Desktop\m\projects\scopeLedger\CloudHammer\data\rasterized_pages\260313_-_VA_Biloxi_Rev_3_ff19da68_p0192.png`
- Tag: `mixed_cloud_with_dense_false_positive_regions`
- Observation: the page has a real revision cloud in a sub-drawing, but the
  main drawing area, estimated around the top `55%` of the page, contains dense
  technical linework useful as a false-positive trap.

Policy:

- For full-page eval, label the real cloud in the sub-drawing.
- Do not mark the full page as empty/no-cloud.
- Use the dense main drawing region to check hallucinations on thick rounded
  linework, arcs, callouts, circles, symbols, and annotation clusters.
- For future hard-negative mining, crop the main drawing region separately only
  if the crop excludes the real sub-drawing cloud.
- Any such crop must carry provenance back to this mixed page and must not be
  confused with full-page no-cloud truth.

Second observed candidate:

- Rasterized page:
  `F:\Desktop\m\projects\scopeLedger\CloudHammer\data\rasterized_pages\260313_-_VA_Biloxi_Rev_3_ff19da68_p0196.png`
- Tag: `mixed_cloud_with_dense_false_positive_regions`
- Suggested upper-region buckets: `no_cloud_door_swing_arc_false_positive_trap`
  and, if the region's linework style warrants it, `no_cloud_dense_dark_linework`
- Observation: the page has no revision clouds in the main drawing region, but
  the lower/sub-drawing region contains at least one real cloud. The main
  drawing region has door swings, arcs, symbols, curved line elements, and
  dense drawing linework that make it a valuable false-positive trap.
- Approximate crop guidance: use the upper/main drawing region from the top of
  the page down to about `70%` page height. In the displayed raster view this
  was approximately the first `800 px` of a roughly `1170 px` page height,
  about `0.68` to `0.70` of the page. Exclude the lower `30%` cloud-containing
  region.

Policy:

- For full-page eval, label any real cloud or clouds in the lower/sub-drawing
  region.
- Do not mark the full page as empty/no-cloud.
- Use the upper/main drawing region to check hallucinations on door swings,
  arcs, symbols, curved line elements, and dense drawing linework.
- For future hard-negative mining, crop the upper/main drawing region
  separately only if the crop excludes the lower cloud-containing region.
- Any such crop must carry provenance back to this mixed page and must not be
  confused with full-page no-cloud truth.

## Context Signal Policy

Marker/delta and stamp/circle signals may be used to create review queues,
hard-negative candidates, or diagnostic reports. They must not be treated as
ground truth and must not silently change promotion metrics.
