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

## Candidate Pools

Candidate pools are not eval subsets and must not be reported as promotion
metrics. They are review or data-selection queues that may feed later
GPT-prefilled provisional review, human confirmation/correction, training
expansion, hard-negative mining, or synthetic planning only after the
applicable guards are satisfied.

Current canonical candidate pool names:

- `full_page_review_candidates_from_touched`: touched pages or regions that may
  deserve direct full-page review because prior crop-level review does not
  prove full-page truth. Apply the review fatigue guardrail before asking for
  repetitive manual review.
- `mining_safe_hard_negative_candidates`: candidate no-cloud regions for future
  hard-negative mining. Frozen eval pages are excluded, and mixed pages require
  region-level exclusion of real cloud-containing areas.
- `synthetic_background_candidates`: candidate no-cloud pages or regions for
  later synthetic background use. This pool must exclude frozen eval pages and
  does not authorize synthetic generation by itself.
- `future_training_expansion_candidates`: candidate reviewed rows, pages, or
  regions for later training expansion, gated by label status, validation split,
  eval-freeze, and source/provenance policy.

Generating candidate pools should be report-first or dry-run-first where
practical. Promotion into training, mining, eval truth, or synthetic generation
requires a separate explicit decision.

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

For `page_disjoint_real`, GPT full-page labels are not eval truth. Frozen real
eval truth should be confirmed directly. Any GPT full-page output on these
pages is scratch/provisional only and must not be used for training, threshold
tuning, or promotion scoring.

Current human-truth review queue:
`CloudHammer_v2/eval/page_disjoint_real_human_review/manifest.jsonl`

Current human-truth label directory:
`CloudHammer_v2/eval/page_disjoint_real_human_review/labels/`

## Review Artifact Rule

Do not use passive visual inspection as a review gate for eval, diagnostics,
labeling, postprocessing, or candidate-pool work. Review means the workflow can
record explicit decisions and corrections in a durable artifact.

At minimum, a review workflow must provide one of:

- an editable manifest, CSV, JSONL, label file, or review log with explicit
  allowed decisions
- reviewer controls that write decisions to a separate review artifact
- a report-only protocol that names the exact decisions to record and where
  they will be stored next

Static viewers, screenshots, overlays, and contact sheets are visual context
only unless they are paired with a durable decision record. If direct edits to
truth, predictions, labels, or manifests are too risky, write review decisions
separately first and consume them through a dry-run or explicit apply step.

## Review Fatigue Guardrail

Do not hand Michael repetitive review labor by default. Before generating,
presenting, or asking Michael to work through any review queue, estimate the
burden and ask whether GPT-5.5 should prefill provisional decisions first.

This applies to review queues for postprocessing diagnostics, mismatch review,
loose localization candidates, fragment merge/split candidates, duplicate
suppression candidates, hard negatives, crop review, LabelImg queues, contact
sheets, and static visual packets.

For each review queue, report:

- approximate item count
- item type
- image/crop size or API-cost risk
- estimated manual burden
- whether GPT-5.5 prefill is recommended
- recommended prefill mode: none, sample, crop-only, full queue, or staged

Use these thresholds:

- `<= 10` items: manual review may be fine, but still name the item count.
- `10-50` items: usually recommend GPT-5.5 sample or full prefill.
- `> 50` items: recommend staged GPT-5.5 prefill unless explicitly told
  otherwise.

The agent must ask before running GPT-5.5 prefill. GPT prefill must never be
treated as ground truth; it is provisional until human accepted. Keep
GPT-prefilled, human-confirmed, and human-corrected outputs clearly separated.

For frozen real eval truth, GPT prefill remains scratch/provisional only and
must not become eval truth, training data, threshold tuning input, or promotion
evidence. If GPT prefill is inappropriate for a queue because of eval policy,
source sensitivity, cost, or image-size risk, say why before asking for manual
review.

## Diagnostic Scope Reset

CloudHammer diagnostics must support decisions, not become the product.
Maximize value per reviewed item, not the number of review queues.

For current eval and diagnostic work, do not add a new diagnostic dimension
unless it directly changes at least one of:

- frozen eval truth
- training inclusion
- postprocessing behavior
- baseline interpretation
- delivery-facing behavior

Before creating any new review queue, classify the proposed diagnostic:

- `GREEN`: required now and decision-changing.
- `YELLOW`: useful but can be GPT-prefilled, backfilled, or sampled.
- `RED`: interesting but not actionable now.

Do not create `RED` queues. Do not create `YELLOW` queues unless they are
cheap, GPT-prefilled or backfilled where practical, and explicitly approved.
Do not re-review already-seen visual items unless the new question cannot be
answered from existing review logs, geometry records, metadata, or GPT-5.5
prefill outputs.

When in doubt, prefer fewer queues, additive fields on existing review records,
GPT-prefilled provisional fields, sampled diagnostics, decision-changing labels
only, and forward progress toward frozen eval and baseline comparison.

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
