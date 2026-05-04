# CloudHammer_v2 Decisions

## 2026-05-02 - Eval-Pivot Workspace

`CloudHammer_v2/` is the active workspace for detection/eval/training policy.
The old `CloudHammer/` folder is legacy/reference.

## 2026-05-02 - Baseline Before Training

Freeze real full-page eval and run baseline comparisons before further detector
training.

## 2026-05-02 - Model vs Pipeline Split

Evaluate `model_only_tiled` and `pipeline_full` separately against the same
frozen labels.

## 2026-05-02 - Separate Eval Subsets

Use separate named subsets: `page_disjoint_real`,
`gold_source_family_clean_real`, and `synthetic_diagnostic`. Do not blend
scores.

## 2026-05-02 - GPT Labeling Exception

GPT may be used heavily for this current project. Label status must distinguish
GPT-provisional output from human-audited or human-corrected truth.

## 2026-05-02 - Synthetic Deferred

Write grammar/spec stubs now, but do not implement synthetic generation until
the real full-page eval baseline exists.

## 2026-05-02 - Experiment Lessons Promoted Without Code Import

Approved lessons from the experiment-retention review were promoted into
`MODEL_VS_PIPELINE_AUDIT.md` and `EVAL_POLICY.md`. Delta/marker logic remains
metadata or selection context, not proof of a cloud. Stamp/circle/scallop
findings become diagnostic and hard-negative guidance. No experiment code was
imported.

## 2026-05-02 - Model vs Pipeline Audit Completed

The audit report lives at
`CloudHammer_v2/docs/MODEL_VS_PIPELINE_AUDIT_REPORT_2026_05_02.md`.
`model_only_tiled` is defined as YOLO tiled full-page inference plus coordinate
mapping and NMS only. `pipeline_full` must explicitly declare active stages
such as grouping, whole-cloud confidence, policy routing, review/release logic,
crop tightening, marker/delta context, and backend manifest ingestion.

The latest symbol/text hard-negative checkpoint is a continuity checkpoint, not
a promoted model. It was trained before the source-controlled split became the
active standard and has not passed frozen page-disjoint full-page eval.

## 2026-05-02 - First Page-Disjoint Baseline Completed

The touched-page registry found `17` eligible untouched standard drawing pages,
and all `17` were frozen as `page_disjoint_real`. GPT-provisional labels were
generated before baseline scoring.

The first baseline compared `model_only_tiled` and `pipeline_full` against the
same frozen GPT-provisional labels. The result is a diagnostic ruler, not
promotion evidence, because human audit is still required.

Report: `CloudHammer_v2/docs/BASELINE_EVAL_REPORT_2026_05_02.md`

## 2026-05-02 - GPT Full-Page Eval Labels Are Scratch Only

`page_disjoint_real` should be human-reviewed directly. GPT full-page labels on
the frozen real eval pages are provisional scratch only and must not be used as
eval ground truth, training data, threshold-tuning input, or promotion evidence.

The accidental GPT-5.5 full-page eval outputs were marked with `DO_NOT_SCORE.md`.

## 2026-05-02 - GPT-5.5 Cropped Supplement Prelabels Completed

GPT-5.5 was run on the intended cropped training/review supplement batch:

`CloudHammer/data/review_batches/small_corpus_expansion_supplement_20260502/prelabel_manifest.jsonl`

Outputs live under:

`CloudHammer_v2/data/gpt55_crop_prelabels_small_corpus_supplement_20260502/`

Label status is `gpt_provisional`. These labels require human review/correction
before any training manifest consumes them.

## 2026-05-02 - Track Cloud Style As Metadata

Decision: track cloud stroke style as visual diagnostic metadata/eval buckets,
not separate YOLO classes for now. Track discipline, company/EOR, source
family, and drawing set separately where known.

Reason: stroke style can affect recall and false-positive behavior, but stroke
thickness alone is not cloud truth. The model should still learn the visual
class `cloud_motif`, while eval and hard-negative mining distinguish style
contexts.

Consequences:

- Keep one YOLO class: `cloud_motif`
- Add source/style diagnostic buckets
- Mine style-specific hard negatives from dense linework, arcs, symbols, and
  rounded technical geometry
- Include thick/dark and thin/light scenario families in future synthetic
  diagnostics
- Revisit separate classes only if data volume and eval evidence justify it

## 2026-05-03 - Correct Cloud Style Discipline Rule

Decision: track cloud stroke style as visual diagnostic metadata and track
discipline, company/EOR, source family, and drawing set separately where known.
Do not infer discipline solely from cloud thickness.

Reason: different drawing sets may come from different disciplines and
different companies/EORs. Some companies/EORs may provide multiple stamped
disciplines, so company, EOR, source family, and discipline are not
interchangeable labels. Stroke style may be internally consistent within a
source family or drawing set, but there is no confirmed universal rule that
dark/thick or thin/light clouds always correspond to one discipline.

Consequences:

- Keep one YOLO class: `cloud_motif`
- Track visual source/style family metadata for eval and review
- Track discipline, company/EOR, source family, and drawing set separately where
  known
- Report thick/dark and thin/light performance separately where possible
- Do not use stroke thickness alone as cloud truth
- Revisit only after source-family audit provides evidence

## 2026-05-03 - Mixed Cloud-Present Pages Can Contain No-Cloud Trap Regions

Decision: track pages with both a real revision cloud and separate dense
no-cloud false-positive regions as mixed diagnostic pages, not empty-label
full-page negatives.

Observed candidates:

`F:\Desktop\m\projects\scopeLedger\CloudHammer\data\rasterized_pages\260313_-_VA_Biloxi_Rev_3_ff19da68_p0192.png`

This page has a real revision cloud in a sub-drawing, but the main drawing
area, estimated around the top `55%` of the page, contains dense technical
linework that is useful for checking false positives on thick rounded linework,
arcs, callouts, circles, symbols, and annotation clusters.

`F:\Desktop\m\projects\scopeLedger\CloudHammer\data\rasterized_pages\260313_-_VA_Biloxi_Rev_3_ff19da68_p0196.png`

This page has a cloud-free upper/main drawing region with many door swings,
arcs, symbols, curved line elements, and dense drawing linework. The lower
approximately `30%` of the page contains at least one real cloud, so the full
page is not an empty-label no-cloud page. Approximate future crop guidance for
the upper trap region is from the top of the page down to about `70%` page
height, roughly the first `800 px` of a `1170 px` displayed raster view.

Consequences:

- Do not treat the full page as no-cloud.
- For full-page eval, label the real cloud in the sub-drawing.
- Tag mixed pages with `mixed_cloud_with_dense_false_positive_regions` and
  region-level diagnostic buckets such as
  `no_cloud_door_swing_arc_false_positive_trap` or
  `no_cloud_dense_dark_linework` as appropriate.
- Later hard-negative crops may be taken from dense no-cloud regions only if
  they exclude any real cloud-containing region on the same page.
- Do not modify labels, eval manifests, or training data from this observation
  without an explicit follow-up task.


## 2026-05-03 — Keep binary touched guard unchanged

Decision: Keep the current binary touched registry guard unchanged for now.

Reason: The legacy manifest superset audit found that the four current touched manifests are complete for model training and review-stage human labeling. Older manifests add only weaker provenance signals such as delta marker detection, review-priority queue membership, and unreviewed candidate ROI generation.

Consequences:
- `page_disjoint_real` remains valid for the first real full-page eval baseline.
- Do not add old delta/ROI/priority manifests to the binary `touched` guard.
- Future registry refinement may add `delta_marker_detected`, `was_in_review_priority_queue`, and `had_unreviewed_candidate_rois` as separate provenance fields.
- Before that enrichment, decide whether `roi_manifest.jsonl` and `roi_manifest_resolved_20260427.jsonl` should be deduped to avoid double-counting.
- Optionally regenerate `delta_manifest.jsonl` against current workspace paths before consuming it as registry provenance.

## 2026-05-03 — Keep weak provenance separate from binary touched status

Decision: Do not collapse weaker provenance signals into the binary `touched` guard.

Reason: The legacy manifest superset audit found that `delta_manifest.jsonl`, review-priority lists, and unreviewed ROI manifests add weaker provenance signals but do not indicate model training contamination. Collapsing them into `touched` would mark all 17 frozen `page_disjoint_real` pages as touched, leaving no surplus clean page-disjoint pool to replace them.

Consequences:
- Keep `page_disjoint_real` valid for the first real full-page eval baseline.
- Keep the binary `touched` guard unchanged for now.
- Future registry enrichment may add `delta_marker_detected`, `was_in_review_priority_queue`, and `had_unreviewed_candidate_rois` as separate fields.
- Before adding `had_unreviewed_candidate_rois`, dedupe or choose between `roi_manifest.jsonl` and `roi_manifest_resolved_20260427.jsonl` to avoid double-counting.
- Before relying on `delta_manifest.jsonl` as a registry input, refresh it or normalize old workspace path prefixes.

## 2026-05-04 - Human-Audited Page-Disjoint Baseline Completed

Decision: Treat the human-audited `page_disjoint_real` scoring as the current
steering baseline, while keeping it separate from promotion claims until
mismatch cases are audited and bucketed.

Reason: The same frozen human-audited truth was used to score
`model_only_tiled` and `pipeline_full`. At IoU `0.25`, `pipeline_full` reduced
false positives substantially and produced stronger F1, while
`model_only_tiled` retained higher recall.

Consequences:

- Current report:
  `CloudHammer_v2/docs/BASELINE_EVAL_REPORT_2026_05_04.md`
- Mismatch queue:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/mismatch_review_queue.jsonl`
- Do not train, tune thresholds, mine hard negatives, or generate synthetic
  backgrounds from frozen `page_disjoint_real` pages.
- Next action is human mismatch audit and error-family bucketing before the
  next training decision.
