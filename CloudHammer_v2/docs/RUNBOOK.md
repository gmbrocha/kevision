# CloudHammer_v2 Runbook

Status: verified command runbook.

Only add commands here after they are verified for CloudHammer_v2. Do not copy
legacy commands from `CloudHammer/` without audit.

## Current Verified Commands

Run from the repo root with the project venv.

Before launching any review queue, apply the review fatigue guardrail from
`CloudHammer_v2/docs/EVAL_POLICY.md#review-fatigue-guardrail`: report item
count, item type, image/API-cost risk, estimated manual burden, and whether
GPT-5.5 provisional prefill is recommended. Do not default to manual review for
repetitive queues.

Build touched-page registry and freeze `page_disjoint_real`:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_touched_page_registry.py
```

Launch direct review for frozen `page_disjoint_real` eval truth.

Burden and policy note: this queue has `17` frozen eval pages. GPT output may
be used only as scratch/provisional support and must not become eval truth,
training data, threshold-tuning input, or promotion evidence.

Known working launch command:

```powershell
$imageList = Resolve-Path CloudHammer_v2\eval\page_disjoint_real_human_review\images_resolved.txt
$startImage = Get-Content CloudHammer_v2\eval\page_disjoint_real_human_review\images_resolved.txt -TotalCount 1
$imageDir = Split-Path -Parent $startImage
$env:LABELIMG_IMAGE_LIST = $imageList
$env:LABELIMG_START_IMAGE = $startImage
.\.venv\Scripts\python.exe .\.venv\Lib\site-packages\labelImg\labelImg.py $imageDir (Resolve-Path CloudHammer_v2\eval\page_disjoint_real_human_review\labels\classes.txt) (Resolve-Path CloudHammer_v2\eval\page_disjoint_real_human_review\labels)
```

The older `labelImg.exe` entrypoint may exit immediately in this environment.
The batch launcher still works as a dry-run/path verifier:

Dry-run result should show `17` images and start at item `1`.

```powershell
.\.venv\Scripts\python.exe CloudHammer\scripts\launch_labelimg_batch.py page_disjoint_real_human_review --batch-root CloudHammer_v2\eval --reviewed-label-dir CloudHammer_v2\eval\page_disjoint_real_human_review\labels --class-file CloudHammer_v2\eval\page_disjoint_real_human_review\labels\classes.txt --dry-run --start-first
```

Eval truth review queue:
`CloudHammer_v2/eval/page_disjoint_real_human_review/manifest.jsonl`

Human truth labels:
`CloudHammer_v2/eval/page_disjoint_real_human_review/labels/`

These labels are frozen eval truth only. Do not add them or their pages to
training, mining, synthetic backgrounds, threshold tuning, or GPT/model relabel
loops.

Launch review for the diagnostic touched-real style-balance supplement only
after applying the review fatigue guardrail:

Burden note: this queue has `12` pages, so GPT-5.5 sample or full prefill
should be considered before asking for manual LabelImg review.

```powershell
$imageList = Resolve-Path CloudHammer_v2\eval\style_balance_diagnostic_real_touched_20260503\images_resolved.txt
$startImage = Get-Content CloudHammer_v2\eval\style_balance_diagnostic_real_touched_20260503\images_resolved.txt -TotalCount 1
$imageDir = Split-Path -Parent $startImage
$env:LABELIMG_IMAGE_LIST = $imageList
$env:LABELIMG_START_IMAGE = $startImage
.\.venv\Scripts\python.exe .\.venv\Lib\site-packages\labelImg\labelImg.py $imageDir (Resolve-Path CloudHammer_v2\eval\style_balance_diagnostic_real_touched_20260503\labels\classes.txt) (Resolve-Path CloudHammer_v2\eval\style_balance_diagnostic_real_touched_20260503\labels)
```

This supplement is diagnostic-only and not promotion-clean. Do not blend its
metrics with `page_disjoint_real`.

Historical only: GPT-provisional full-page labels were generated during setup,
but `page_disjoint_real` eval truth should be confirmed directly. Do not use
this command to create eval truth:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\generate_gpt_fullpage_labels.py --manifest CloudHammer_v2\eval\page_disjoint_real\page_disjoint_real_manifest.jsonl --output-dir CloudHammer_v2\eval\page_disjoint_real --model gpt-5.4 --detail high --max-dim 3000 --image-format jpeg --min-confidence 0.40 --env-file CloudHammer\.env --request-delay 0.25
```

Do not run the GPT-5.5 full-page diagnostic pass on `page_disjoint_real`. The
existing accidental output is marked scratch/do-not-score.

Run GPT-5.5 cropped prelabeling on the supplement review batch:

```powershell
.\.venv\Scripts\python.exe CloudHammer\scripts\prelabel_cloud_rois_openai.py --config CloudHammer_v2\configs\gpt55_crop_prelabel_small_corpus_supplement_20260502.yaml --manifest CloudHammer\data\review_batches\small_corpus_expansion_supplement_20260502\prelabel_manifest.jsonl --model gpt-5.5 --detail high --max-dim 1536 --min-confidence 0.40 --image-format jpeg --env-file CloudHammer\.env --request-delay 0.25
```

Historical provisional baseline only: the following commands scored against a
GPT-provisional manifest. Rerun against a human-audited `page_disjoint_real`
manifest once it exists.

Human-audited manifest now exists:

```powershell
CloudHammer_v2\eval\page_disjoint_real\page_disjoint_real_manifest.human_audited.jsonl
```

Rerun model-only scoring against human-audited truth:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\evaluate_fullpage_detections.py --eval-manifest CloudHammer_v2\eval\page_disjoint_real\page_disjoint_real_manifest.human_audited.jsonl --detections-dir CloudHammer_v2\outputs\baseline_model_only_tiled_page_disjoint_real_20260502\detections --output-dir CloudHammer_v2\outputs\baseline_model_only_tiled_page_disjoint_real_20260502\eval_human_audited --run-name model_only_tiled_page_disjoint_real_human_audited_20260503 --prediction-source model_only_tiled
```

Rerun pipeline-full scoring against human-audited truth:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\evaluate_fullpage_detections.py --eval-manifest CloudHammer_v2\eval\page_disjoint_real\page_disjoint_real_manifest.human_audited.jsonl --detections-dir CloudHammer_v2\outputs\baseline_pipeline_full_page_disjoint_real_20260502\whole_cloud_candidates\detections_whole --output-dir CloudHammer_v2\outputs\baseline_pipeline_full_page_disjoint_real_20260502\eval_human_audited --run-name pipeline_full_page_disjoint_real_human_audited_20260503 --prediction-source pipeline_full_grouped_whole_cloud_candidates
```

Build the mismatch review packet from existing human truth and existing
model/pipeline predictions. This writes only error-analysis artifacts and the
blank/template mismatch review log; it must not edit truth labels, eval
manifests, predictions, model files, datasets, training data, mining inputs, or
tuning inputs:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_mismatch_review_packet.py
```

Expected artifacts:

- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/README.md`
- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/contact_sheets/mismatch_truth_vs_predictions_contact_sheet.jpg`
- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_manifest.jsonl`
- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_manifest.csv`
- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.csv`

Build the static HTML reviewer with crisp PNG local/wide crops. The reviewer
shows all nearby truth/prediction boxes, matched-elsewhere/duplicate flags, and
the raw scoring reason for the row:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_mismatch_html_reviewer.py
```

Expected artifacts:

- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_reviewer.html`
- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/reviewer_crops/local/`
- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/reviewer_crops/wide/`

The reviewer stores browser-local edits and exports
`mismatch_review_log.reviewed.csv`. It must not be used to edit truth labels,
eval manifests, prediction files, model files, datasets, or training data.

Use these review statuses:

- `unreviewed`
- `resolved`
- `truth_followup`
- `tooling_or_matching_artifact`
- `not_actionable`

Generate auto-suggested review metadata for a row range when the mismatch
family is visually/mechanically repetitive. This writes a separate suggested
CSV and Markdown report; it does not overwrite the blank/template review log:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\suggest_mismatch_review.py --start-row 44 --end-row 77
```

Expected artifacts:

- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.autosuggest_rows44_77.csv`
- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_autosuggest_rows44_77.md`

Build an auto-suggest reviewer from that CSV:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_mismatch_html_reviewer.py --review-log CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_review_log.autosuggest_rows44_77.csv --output-html CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_reviewer.autosuggest_rows44_77.html
```

Open it from the local server and click `Apply Review Log Values` only after
checking that the suggestions are suitable. The button copies nonblank embedded
review-log values into browser localStorage; it does not modify eval/prediction
artifacts.

Summarize the blank/template review log:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\summarize_mismatch_review.py --review-log CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_review_log.csv
```

After exporting `mismatch_review_log.reviewed.csv` from the browser reviewer,
summarize the reviewed metadata directly:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\summarize_mismatch_review.py --review-log CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_review_log.reviewed.csv
```

Expected artifacts:

- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.csv`
- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_summary.json`
- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_summary.md`
- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.reviewed_summary.json`
- `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.reviewed_summary.md`

Build the report-only non-frozen postprocessing diagnostic. This consumes the
existing non-frozen whole-cloud candidate manifest from the legacy run as input
data only; it does not import legacy code. It excludes frozen
`page_disjoint_real` pages and writes only diagnostic reports:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\diagnose_postprocessing_candidates.py
```

Purpose: surface candidate rows for fragment merging, duplicate suppression,
overmerge splitting, and loose-localization review before any training cycle.

Working directory: repo root.

Expected artifacts:

- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_candidates.jsonl`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_summary.json`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_summary.md`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/excluded_frozen_candidates.jsonl`

Safety: report-only. It must not edit truth labels, eval manifests,
prediction files, model files, datasets, or training data. It is not threshold
tuning, and frozen eval pages remain measurement-only.

Build a static HTML reviewer for the non-frozen postprocessing diagnostic rows.
This links each diagnostic row to grouped candidate IDs, existing crop paths,
source page renders, and reviewer controls for durable decision export:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_postprocessing_diagnostic_viewer.py
```

Purpose: make the diagnostic rows reviewable without opening raw JSONL or
manually chasing crop paths.

Working directory: repo root.

Expected artifact:

- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_viewer.html`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_review_log.csv`

Open it from a browser or from a static server rooted at the repo root. If crop
images return `404`, the server is likely rooted in the wrong directory.

The reviewer stores browser-local edits and exports
`postprocessing_diagnostic_review_log.reviewed.csv`. Use review statuses:

- `unreviewed`
- `reviewed`
- `needs_followup`
- `not_actionable`

Use review decisions:

- `merge`
- `reject_merge`
- `suppress_duplicate`
- `reject_suppress`
- `split`
- `reject_split`
- `tighten`
- `tighten_adjust`
- `reject_tighten`
- `expand`
- `ignore`
- `unclear`

Use `tighten_adjust` when the candidate should tighten but the displayed tight
member bbox is not acceptable, such as when it clips part of the visible cloud
or remains materially too loose in one axis.

Safety: review-metadata only. It consumes existing diagnostic rows and
candidate crop paths. It must not edit truth labels, eval manifests, prediction
files, model files, datasets, or training data. The exported reviewed CSV is
input for a later dry-run or explicit apply step only.

Prefill the non-frozen postprocessing diagnostic review log with GPT-5.5
suggestions. Run dry-run first to generate/check API overlay inputs without API
calls:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\prefill_postprocessing_review_gpt.py --dry-run
```

Then run the API prefill:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\prefill_postprocessing_review_gpt.py --overwrite
```

Expected artifacts:

- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_review_log.gpt55_prefill.csv`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_review_log.gpt55_prefill.summary.md`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/gpt55_review_prefill/predictions.jsonl`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/gpt55_review_prefill/api_inputs/`

Build a companion reviewer using the GPT-5.5 prefill:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_postprocessing_diagnostic_viewer.py --review-log CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\postprocessing_diagnostic_review_log.gpt55_prefill.csv --output-html CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\postprocessing_diagnostic_viewer.gpt55_prefill.html
```

Open the companion reviewer and click `Apply Review Log Values` to load the
GPT suggestions into browser state, then confirm or correct each row and export
`postprocessing_diagnostic_review_log.reviewed.csv`.

Safety: GPT-5.5 prefill is provisional review metadata only. It must not be
treated as human-reviewed truth, training data, threshold tuning, eval truth,
or automatic postprocessor input until the human-reviewed CSV is exported.

Build the dry-run postprocessing action plan from the reviewed diagnostic CSV:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_postprocessing_dry_run_plan.py
```

Purpose: convert reviewed postprocessing decisions into a report-only action
plan. The plan proposes deterministic merge/tighten candidates where possible
and flags expand, split, and `tighten_adjust` cases that still need explicit
geometry before any apply step.

Working directory: repo root.

Expected artifacts:

- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_dry_run_plan.jsonl`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_dry_run_summary.json`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_dry_run_summary.md`

Current dry-run result from the reviewed `44` rows:

- `3` reviewed merge components
- `10` tighten bbox proposals
- `12` manual geometry rows for expand/`tighten_adjust`
- `3` manual split rows
- `10` no-change rows

Safety: dry-run only. It must not edit the legacy source candidate manifest,
truth labels, eval manifests, predictions, model files, datasets, training
data, or threshold-tuning inputs.

Build the blocked-geometry reviewer from the dry-run plan:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_postprocessing_geometry_reviewer.py
```

Purpose: review only the dry-run cases that need explicit geometry before any
apply step. This includes expand, split, `tighten_adjust`, and merge-component
rollups whose final full-cloud bbox cannot be safely inferred.

Working directory: repo root.

Expected artifacts:

- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_reviewer.html`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_review.csv`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_reviewer_summary.md`

Current queue size is `18`: `11` expand geometry items, `3` merge-component
geometry items, `3` split geometry items, and `1` `tighten_adjust` geometry
item. Under the review fatigue guardrail, GPT-5.5 geometry prefill may be
considered, but any prefilled geometry is provisional until human accepted.

The reviewer exports `postprocessing_geometry_review.reviewed.csv`. Save it in
the same `blocked_geometry_review` directory.

Safety: review artifact only. It must not edit the legacy source candidate
manifest, truth labels, eval manifests, predictions, model files, datasets,
training data, or threshold-tuning inputs.

Prefill the blocked-geometry reviewer with GPT-5.5 provisional geometry:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\prefill_postprocessing_geometry_gpt.py --overwrite
```

Purpose: reduce repetitive manual geometry entry for the `18` blocked
postprocessing geometry items. GPT-5.5 writes provisional review metadata only;
the output must be human-confirmed or corrected before any apply script consumes
it.

Working directory: repo root.

Expected artifacts:

- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_review.gpt55_prefill.csv`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_review.gpt55_prefill.summary.md`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/gpt55_geometry_prefill/predictions.jsonl`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/gpt55_geometry_prefill/api_inputs/`

Build a companion reviewer using the GPT-5.5 geometry prefill:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_postprocessing_geometry_reviewer.py --review-log CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\blocked_geometry_review\postprocessing_geometry_review.gpt55_prefill.csv --output-html CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\blocked_geometry_review\postprocessing_geometry_reviewer.gpt55_prefill.html
```

Expected artifact:

- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_reviewer.gpt55_prefill.html`

Open the prefilled reviewer, confirm or correct each row, and export
`postprocessing_geometry_review.reviewed.csv` to the same
`blocked_geometry_review` directory. Prefilled rows use `gpt_prefilled` status;
the reviewer must change accepted rows to `reviewed` before the export is used
by any apply step.

Safety: GPT-5.5 geometry prefill is provisional review metadata only. It must
not edit the legacy source candidate manifest, truth labels, eval manifests,
predictions, model files, datasets, training data, or threshold-tuning inputs.

Build the postprocessing apply dry-run comparison from the reviewed diagnostic
and geometry logs:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_postprocessing_apply_dry_run_comparison.py
```

Purpose: convert the reviewed diagnostic decisions, dry-run plan, and reviewed
geometry CSV into a candidate-level apply preview and change log. This is a
report-first comparison only, not an apply script.

Working directory: repo root.

Expected artifacts:

- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_dry_run_20260505/postprocessing_apply_dry_run_candidate_preview.jsonl`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_dry_run_20260505/postprocessing_apply_dry_run_changes.jsonl`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_dry_run_20260505/postprocessing_apply_dry_run_summary.json`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_dry_run_20260505/postprocessing_apply_dry_run_summary.md`

Current dry-run comparison result:

- `25` referenced source candidates
- `23` preview output candidates
- `3` merge-component bboxes
- `8` split-child bboxes
- `10` tighten bboxes
- `1` corrected bbox
- `1` unchanged candidate
- `0` unresolved manual geometry rows after geometry review
- `1` duplicate split geometry record collapsed into the latest reviewed row

Safety: dry-run comparison only. It must not edit the legacy source candidate
manifest, truth labels, eval manifests, predictions, model files, datasets,
training data, or threshold-tuning inputs.

Apply the accepted postprocessing preview into a derived non-frozen candidate
manifest:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\apply_postprocessing_non_frozen.py
```

Purpose: write a new non-frozen postprocessed candidate manifest from the
accepted apply dry-run comparison. This is an explicit derived-output apply
path; it does not mutate the legacy source candidate manifest.

Working directory: repo root.

Expected artifacts:

- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/postprocessed_non_frozen_candidates_manifest.jsonl`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/postprocessed_non_frozen_suppressed_sources.jsonl`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/postprocessed_non_frozen_apply_summary.json`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/postprocessed_non_frozen_apply_summary.md`

Current derived-output result:

- `34` source manifest candidates
- `32` postprocessed output candidates
- `13` suppressed source candidates replaced by merge/split outputs
- `9` carried-through unflagged candidates
- `10` tighten bboxes
- `8` split-child bboxes
- `3` merge-component bboxes
- `1` corrected bbox
- `1` unchanged reviewed candidate

Safety: derived output only. It must not edit the legacy source candidate
manifest, truth labels, eval manifests, predictions, model files, datasets,
training data, or threshold-tuning inputs.

Compare the derived non-frozen postprocessed manifest against the original
source candidate manifest:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\compare_postprocessing_non_frozen_behavior.py
```

Purpose: produce a report-first metadata comparison between the original
non-frozen source candidates and the derived postprocessed candidates. This
does not score against eval truth, tune thresholds, regenerate crops, or create
a review queue.

Working directory: repo root.

Expected artifacts:

- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_behavior_comparison_20260505/postprocessing_non_frozen_behavior_by_source.jsonl`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_behavior_comparison_20260505/postprocessing_non_frozen_behavior_by_page.jsonl`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_behavior_comparison_20260505/postprocessing_non_frozen_behavior_summary.json`
- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_behavior_comparison_20260505/postprocessing_non_frozen_behavior_summary.md`

Current behavior comparison result:

- `34` source candidates -> `32` postprocessed candidates
- candidate count delta `-2`
- total bbox area ratio postprocessed/source `0.831645`
- `13` source candidates replaced by merge/split outputs
- `22` postprocessed candidates need crop regeneration before crop-based
  inspection/export
- page count remains `14`

Safety: report-first comparison only. It must not edit the legacy source
candidate manifest, truth labels, eval manifests, predictions, model files,
datasets, training data, crops, or threshold-tuning inputs.

Run model-only tiled inference using the latest continuity checkpoint:

```powershell
.\.venv\Scripts\python.exe CloudHammer\scripts\infer_pages.py --config CloudHammer_v2\configs\baseline_page_disjoint_real_20260502.yaml --model CloudHammer\runs\cloudhammer_roi-symbol-text-fp-hn-20260502\weights\best.pt --pages-manifest CloudHammer_v2\eval\page_disjoint_real\page_disjoint_real_manifest.gpt_provisional.jsonl
```

Score model-only tiled detections:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\evaluate_fullpage_detections.py --eval-manifest CloudHammer_v2\eval\page_disjoint_real\page_disjoint_real_manifest.gpt_provisional.jsonl --detections-dir CloudHammer_v2\outputs\baseline_model_only_tiled_page_disjoint_real_20260502\detections --output-dir CloudHammer_v2\outputs\baseline_model_only_tiled_page_disjoint_real_20260502\eval --run-name model_only_tiled_page_disjoint_real_20260502 --prediction-source model_only_tiled
```

Run pipeline grouping and whole-cloud export:

```powershell
.\.venv\Scripts\python.exe CloudHammer\scripts\group_fragment_detections.py --detections-dir CloudHammer_v2\outputs\baseline_model_only_tiled_page_disjoint_real_20260502\detections --output-dir CloudHammer_v2\outputs\baseline_pipeline_full_page_disjoint_real_20260502\fragment_grouping --overmerge-refinement --overmerge-refinement-profile review_v1
```

```powershell
.\.venv\Scripts\python.exe CloudHammer\scripts\export_whole_cloud_candidates.py --grouped-detections-dir CloudHammer_v2\outputs\baseline_pipeline_full_page_disjoint_real_20260502\fragment_grouping\detections_grouped --output-dir CloudHammer_v2\outputs\baseline_pipeline_full_page_disjoint_real_20260502\whole_cloud_candidates --crop-margin-ratio 0.16 --min-crop-margin 550 --max-crop-margin 950
```

Score pipeline-full detections:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\evaluate_fullpage_detections.py --eval-manifest CloudHammer_v2\eval\page_disjoint_real\page_disjoint_real_manifest.gpt_provisional.jsonl --detections-dir CloudHammer_v2\outputs\baseline_pipeline_full_page_disjoint_real_20260502\whole_cloud_candidates\detections_whole --output-dir CloudHammer_v2\outputs\baseline_pipeline_full_page_disjoint_real_20260502\eval --run-name pipeline_full_page_disjoint_real_20260502 --prediction-source pipeline_full_grouped_whole_cloud_candidates
```

## TODO

- Add synthetic diagnostic commands only after implementation.
