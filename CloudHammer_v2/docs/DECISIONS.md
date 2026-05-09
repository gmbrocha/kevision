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

`page_disjoint_real` eval truth should be confirmed directly. GPT full-page
labels on the frozen real eval pages are provisional scratch only and must not
be used as eval ground truth, training data, threshold-tuning input, or
promotion evidence.

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


## 2026-05-03 - Keep Binary Touched Guard Unchanged

Decision: Keep the current binary touched registry guard unchanged for now.

Reason: The legacy manifest superset audit found that the four current touched manifests are complete for model training and review-stage human labeling. Older manifests add only weaker provenance signals such as delta marker detection, review-priority queue membership, and unreviewed candidate ROI generation.

Consequences:
- `page_disjoint_real` remains valid for the first real full-page eval baseline.
- Do not add old delta/ROI/priority manifests to the binary `touched` guard.
- Future registry refinement may add `delta_marker_detected`, `was_in_review_priority_queue`, and `had_unreviewed_candidate_rois` as separate provenance fields.
- Before that enrichment, decide whether `roi_manifest.jsonl` and `roi_manifest_resolved_20260427.jsonl` should be deduped to avoid double-counting.
- Optionally regenerate `delta_manifest.jsonl` against current workspace paths before consuming it as registry provenance.

## 2026-05-03 - Keep Weak Provenance Separate From Binary Touched Status

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

## 2026-05-04 - Mismatch Review Is Error Analysis, Not Human Uncertainty

Decision: The mismatch reviewer treats human cloud/not-cloud judgment as
authoritative when adequate context is shown, and separates model errors from
IoU matching, duplicate-prediction, localization, truth-followup, and reviewer
tooling artifacts.

Reason: Some `false_positive` rows visibly overlap real cloud geometry because
the scoring row was unmatched by greedy IoU assignment or because another
prediction already claimed the truth box. The review surface must explain that
workflow instead of implying the human is unsure.

Consequences:

- `mismatch_review_log.csv` is the blank/template metadata log.
- Browser review exports `mismatch_review_log.reviewed.csv`.
- Status values are `unreviewed`, `resolved`, `truth_followup`,
  `tooling_or_matching_artifact`, and `not_actionable`.
- `truth_followup` queues a separate frozen-truth recheck; it does not modify
  truth automatically.
- Reviewed mismatch metadata must not be converted directly into training
  data, threshold tuning, hard-negative mining, or eval truth edits.

## 2026-05-04 - Canonical Eval Sets And Candidate Pools

Decision: Keep `synthetic_diagnostic` as the canonical synthetic eval-set name
and define near-term candidate pools separately from eval subsets.

Reason: The next loop needs queue/manifests for full-page review, hard-negative
mining, synthetic background planning, and future training expansion, but those
queues are not themselves eval sets and must not blur promotion metrics.

Consequences:

- Current eval subsets remain:
  `page_disjoint_real`, `gold_source_family_clean_real`,
  `style_balance_diagnostic_real_touched`, and `synthetic_diagnostic`.
- Canonical candidate pools are:
  `full_page_review_candidates_from_touched`,
  `mining_safe_hard_negative_candidates`,
  `synthetic_background_candidates`, and
  `future_training_expansion_candidates`.
- Candidate pools must preserve frozen eval guards and label/provenance status.
- Candidate pool creation does not authorize training, hard-negative mining,
  threshold tuning, synthetic generation, or eval truth edits without a separate
  explicit task.

## 2026-05-04 - Postprocessing-First After Mismatch Review

Decision: After reviewing all `77` baseline mismatch rows, run a
postprocessing-first diagnostic before starting the next training cycle.

Reason: The reviewed mismatch summary is dominated by prediction fragments,
duplicate predictions on real clouds, overmerges, split fragments, and
localization issues. Only a smaller share is direct visual false-positive or
missed-cloud signal. Training now would blur postprocessing failures with model
perception failures.

Consequences:

- Use `mismatch_review_log.reviewed.csv` and its summary as error-analysis
  metadata, not as training labels or tuning data.
- Do merge/suppress/split/localization diagnostics on non-frozen data first.
- Keep frozen `page_disjoint_real` pages for measurement after candidate
  postprocessing changes, not for threshold tuning.
- Queue the two `truth_followup` rows as a separate frozen-truth recheck task;
  do not auto-edit truth from mismatch review metadata.

## 2026-05-04 - First Postprocessing Diagnostic Uses Non-Frozen Candidate Output

Decision: The first postprocessing diagnostic consumes the existing non-frozen
whole-cloud candidate manifest from
`CloudHammer/runs/whole_cloud_eval_symbol_text_fp_hn_20260502/` as input data,
while writing only v2 diagnostic reports under `CloudHammer_v2/outputs/`.

Reason: Current v2 prediction outputs are for frozen `page_disjoint_real`
baseline pages, which must not be used for tuning. The legacy-generated
candidate manifest provides a small non-frozen geometry source for
merge/suppress/split/localization diagnosis without importing legacy code.

Consequences:

- The diagnostic excludes frozen `page_disjoint_real` pages by manifest guard.
- The output is report-only and not a postprocessor, training manifest,
  threshold-tuning result, or eval truth edit.
- No legacy code is imported or modified.
- The reviewed `crossing_line_x_patterns` count remains a later hard-negative
  or training-family candidate, not the primary postprocessing blocker.

## 2026-05-04 - Static Diagnostic Viewer Before Postprocessor

Decision: Use a static read-only HTML viewer as the review surface for the
first non-frozen postprocessing diagnostic before building the dry-run
postprocessor.

Reason: The diagnostic rows are easier to understand when grouped candidate
IDs, crop links, source page renders, and diagnostic-family metrics are visible
together. Raw JSONL review is too easy to misread and too slow for spotting
merge, duplicate, overmerge, and localization patterns.

Consequences:

- Viewer artifact:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_viewer.html`
- At creation time, the viewer was read-only and wrote no review metadata. This
  was superseded on 2026-05-05 by separate review-log controls.
- It consumes existing non-frozen diagnostic rows and existing crop/page paths
  only.
- It must not edit truth labels, eval manifests, predictions, model files,
  datasets, training data, or frozen eval artifacts.
- Next implementation step remains a dry-run postprocessor on non-frozen
  diagnostic inputs.

## 2026-05-05 - Review Requires Durable Decisions

Decision: A CloudHammer review, audit, triage, spot-check, or human look-over is
not complete unless it produces a durable decision record or explicitly states a
report-only purpose and where decisions will be recorded next.

Reason: passive visual inspection does not create usable inputs for label
correction, candidate metadata changes, postprocessing dry-runs, training
selection, or eval truth follow-up.

Consequences:

- Static viewers, overlays, contact sheets, and screenshots are visual context
  only unless paired with a manifest, CSV, JSONL, label file, or review log.
- Review tools should expose explicit decisions such as merge, reject merge,
  split, tighten, tighten-adjust, expand, suppress, ignore, truth follow-up, or
  correction notes when those decisions are relevant to the task.
- If direct mutation is unsafe, write decisions to a separate review artifact
  and require a dry-run or explicit apply step before changing labels,
  predictions, eval manifests, datasets, or training inputs.
- The current non-frozen postprocessing diagnostic now has reviewer controls
  and a blank/template review log. It must export a reviewed CSV before it can
  gate the dry-run postprocessor.

## 2026-05-05 - GPT-5.5 Prefill Is Provisional Review Metadata

Decision: GPT-5.5 may prefill the non-frozen postprocessing diagnostic review
log, but the output is provisional review metadata only.

Reason: model-suggested decisions can speed human confirmation, but they are
not a replacement for durable human review and must not silently steer
postprocessing behavior.

Consequences:

- GPT-5.5 prefill writes separate artifacts under
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/`.
- The prefill must not edit labels, eval manifests, predictions, datasets,
  model files, training data, threshold-tuning inputs, or frozen eval artifacts.
- A human must confirm or correct the companion reviewer and export a final
  reviewed CSV before any dry-run postprocessor consumes the decisions.

## 2026-05-05 - Review Fatigue Guardrail

Decision: Agents must not default to handing Michael repetitive review queues.
Before presenting a review queue, they must report queue size, estimate manual
burden, and ask whether GPT-5.5 should prefill provisional decisions first.

Reason: Repetitive late-night review is expensive and error-prone. GPT-5.5 can
provide provisional first-pass decisions that Michael confirms or corrects.

Consequences:

- `<= 10` items may be manual after the item count is stated.
- `10-50` items should usually get a GPT-5.5 sample or full prefill
  recommendation.
- `> 50` items should get staged GPT-5.5 prefill unless explicitly declined.
- GPT prefill remains provisional and must never be treated as ground truth.

## 2026-05-05 - Dry-Run Postprocessing Plan From Reviewed Diagnostics

Decision: The first postprocessing implementation step after reviewed
diagnostic rows is a dry-run action plan, not an apply script.

Reason: The reviewed diagnostic rows include deterministic tighten and merge
signals, but also expand, split, and `tighten_adjust` cases where the correct
geometry is not safely derivable from the current candidate boxes or tight
member boxes.

Consequences:

- Dry-run script:
  `CloudHammer_v2/scripts/build_postprocessing_dry_run_plan.py`
- Output:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/`
- The plan proposes `3` merge components and `10` tighten bbox actions.
- It blocks `12` expand/`tighten_adjust` rows and `3` split rows until explicit
  reviewed geometry exists.
- The dry-run must not edit the legacy source candidate manifest, labels, eval
  manifests, predictions, model files, datasets, training data, or
  threshold-tuning inputs.

## 2026-05-05 - Blocked Geometry Requires Separate Review Artifact

Decision: Expand, split, `tighten_adjust`, and merge-component geometry from
the first postprocessing dry-run must be resolved in a separate geometry review
artifact before any apply script consumes it.

Reason: These cases require explicit full-cloud or child geometry. The correct
boxes are not safely derivable from current candidate boxes, tight member
boxes, or merge-component unions.

Consequences:

- Reviewer script:
  `CloudHammer_v2/scripts/build_postprocessing_geometry_reviewer.py`
- Output:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/`
- Current queue has `18` items: `11` expand geometry, `3` merge-component
  geometry, `3` split geometry, and `1` `tighten_adjust` geometry.
- Under the review fatigue guardrail, GPT-5.5 provisional geometry prefill may
  be considered before manual review, but any prefilled geometry is provisional
  until human accepted.
- The geometry reviewer must not edit the legacy source candidate manifest,
  labels, eval manifests, predictions, model files, datasets, training data, or
  threshold-tuning inputs.

## 2026-05-05 - GPT-5.5 Geometry Prefill Remains Provisional

Decision: The `18` blocked postprocessing geometry items may be prefilled by
GPT-5.5 into a separate review CSV, but the output is provisional metadata only
until Michael confirms or corrects it in the geometry reviewer.

Reason: The queue is above the manual-review comfort threshold and requires
repetitive geometry entry. GPT-5.5 can reduce that burden, but its geometry is
not ground truth and cannot be applied automatically.

Consequences:

- Prefill script:
  `CloudHammer_v2/scripts/prefill_postprocessing_geometry_gpt.py`
- Prefill CSV:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_review.gpt55_prefill.csv`
- Companion reviewer:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_reviewer.gpt55_prefill.html`
- The human-confirmed export must still be
  `postprocessing_geometry_review.reviewed.csv` before any apply script consumes
  expand, split, `tighten_adjust`, or merge-component geometry.
- Prefill rows use `gpt_prefilled` status, not human `reviewed` status.
- The prefill must not edit the legacy source candidate manifest, labels, eval
  manifests, predictions, model files, datasets, training data, or
  threshold-tuning inputs.

## 2026-05-05 - Postprocessing Apply Preview Is Report-First

Decision: The first postprocessing apply follow-through is a non-mutating
candidate-level dry-run comparison, not an apply script.

Reason: The reviewed diagnostic and geometry records are enough to measure
candidate behavior, but they should not directly mutate the legacy source
candidate manifest or any eval/training artifact. The comparison must expose
merge, split, tighten, corrected, unchanged, and unresolved cases first.

Consequences:

- Comparison script:
  `CloudHammer_v2/scripts/build_postprocessing_apply_dry_run_comparison.py`
- Output:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_dry_run_20260505/`
- Current preview converts `25` referenced source candidates into `23` output
  candidates and leaves `0` unresolved manual geometry rows.
- One duplicate split geometry record is collapsed into the latest reviewed row
  and reported as a warning.
- The comparison must not edit the legacy source candidate manifest, labels,
  eval manifests, predictions, model files, datasets, training data, or
  threshold-tuning inputs.

## 2026-05-05 - Non-Frozen Postprocessing Apply Writes Derived Manifest

Decision: The accepted postprocessing apply preview is consumed by a dedicated
non-frozen apply script that writes a new derived manifest and suppression log,
not an in-place edit to the legacy source manifest.

Reason: The reviewed postprocessing decisions are ready to become a concrete
candidate artifact, but the source manifest and all eval/training artifacts
must remain immutable unless a later explicit workflow consumes the derived
output.

Consequences:

- Apply script:
  `CloudHammer_v2/scripts/apply_postprocessing_non_frozen.py`
- Output:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/`
- Current derived manifest converts `34` source candidates into `32`
  postprocessed candidates and writes `13` suppression records.
- Changed/merged/split/corrected boxes are marked as needing crop
  regeneration; unchanged and carried-through candidates preserve source crops.
- The apply path must not edit the legacy source candidate manifest, labels,
  eval manifests, predictions, model files, datasets, training data, or
  threshold-tuning inputs.

## 2026-05-05 - Behavior Comparison Before Crop Regeneration

Decision: After writing the derived non-frozen postprocessed manifest, compare
it against the original source manifest before regenerating crops or wiring
pipeline consumers.

Reason: The metadata comparison answers whether the accepted postprocessing
changes are coherent without creating more visual artifacts or asking for more
review. Crop regeneration is useful only once the derived manifest behavior is
understood.

Consequences:

- Comparison script:
  `CloudHammer_v2/scripts/compare_postprocessing_non_frozen_behavior.py`
- Output:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_behavior_comparison_20260505/`
- Current comparison reports `34` source candidates becoming `32`
  postprocessed candidates, a total bbox area ratio of `0.831645`, and `22`
  candidates needing crop regeneration before crop-based inspection/export.
- The comparison must not edit the legacy source candidate manifest, labels,
  eval manifests, predictions, model files, datasets, training data, crops, or
  threshold-tuning inputs.

## 2026-05-08 - Crop Regeneration Writes A Separate Derived Manifest

Decision: Regenerate crops for changed non-frozen postprocessed candidates into
a separate crop-ready manifest and crop folder instead of editing the accepted
apply manifest or legacy source candidate manifest in place.

Reason: The accepted apply manifest is useful provenance for the postprocessing
decision, while crop consumers need concrete image paths for the changed boxes.
Keeping regeneration as a derived artifact preserves source manifests and makes
the crop-writing step auditable.

Consequences:

- Script:
  `CloudHammer_v2/scripts/regenerate_postprocessed_non_frozen_crops.py`
- Output:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/`
- Dry-run must be run before real crop writing.
- The current run wrote `22` regenerated crops and a `32`-row crop-ready
  manifest with `10` source crops preserved.
- This artifact must not be treated as eval truth, training data, threshold
  tuning, or a mutation of the legacy source candidate manifest.

## 2026-05-08 - GPT-5.5 Crop Precheck Before Human Inspection

Decision: Postprocessed crop inspection should be prechecked with GPT-5.5 into
a separate provisional CSV before asking Michael to review the crop-ready
queue.

Reason: The regenerated crop manifest has `32` items and the user explicitly
asked to avoid drifting into another blank manual inspection pass. GPT-5.5 can
separate likely-usable crops from obvious no-cloud or ambiguous rows while
preserving a durable record of the findings.

Consequences:

- Inspection packet script:
  `CloudHammer_v2/scripts/build_postprocessed_crop_inspection_viewer.py`
- GPT precheck script:
  `CloudHammer_v2/scripts/prefill_postprocessed_crop_inspection_gpt.py`
- Prefill CSV:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.csv`
- Companion viewer:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.html`
- Current precheck result: `28` `accept_crop`, `2` `needs_human_review`, and
  `2` `reject_no_visible_cloud`.
- GPT crop decisions are provisional inspection metadata only. They must not
  edit the legacy source candidate manifest, labels, eval manifests,
  predictions, model files, datasets, training data, or threshold-tuning inputs.

## 2026-05-08 - Review Viewers Must Show Decision Overlays

Decision: CloudHammer review viewers and inspection packets must render the
visual target of the decision directly on the image, not just list bbox
coordinates or metadata.

Reason: Reviewers cannot reliably assess candidate, prediction, truth, crop, or
geometry decisions from raw crops alone. The artifact must show what the model,
pipeline, or review queue is asking about.

Consequences:

- Detection and crop-inspection viewers must show candidate bbox overlays.
- Mismatch viewers must show prediction/truth overlays and matching context.
- Geometry viewers must show source and proposed geometry overlays when
  available.
- Rows without renderable visual evidence should be marked missing evidence or
  blocked, not handed to a human as a normal review item.

## 2026-05-05 - Diagnostic Scope Reset

Decision: CloudHammer diagnostics must maximize value per reviewed item, not
the number of review queues. New diagnostic dimensions require a stoplight
classification before any queue is created.

Reason: The eval-pivot loop needs reliable baselines and targeted model or
pipeline improvements. Repeated visual review of the same evidence burns human
time without necessarily changing frozen truth, training inclusion,
postprocessing behavior, baseline interpretation, or delivery behavior.

Consequences:

- `GREEN` queues are required now and decision-changing.
- `YELLOW` queues are useful but must be cheap, GPT-prefilled/backfilled or
  sampled where practical, and explicitly approved.
- `RED` queues are interesting but not actionable now and must not be created.
- Do not re-review already-seen visual items if existing review records,
  geometry, metadata, or GPT-5.5 prefill can answer the question.
- Current audit:
  `CloudHammer_v2/docs/DIAGNOSTIC_STOPLIGHT_AUDIT_2026_05_05.md`
