# CloudHammer_v2 Runbook

Status: verified command runbook.

Only add commands here after they are verified for CloudHammer_v2. Do not copy
legacy commands from `CloudHammer/` without audit.

## Current Verified Commands

Run from the repo root with the project venv.

Build touched-page registry and freeze `page_disjoint_real`:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_touched_page_registry.py
```

Launch human review for frozen `page_disjoint_real` eval truth.

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

Human-review queue:
`CloudHammer_v2/eval/page_disjoint_real_human_review/manifest.jsonl`

Human truth labels:
`CloudHammer_v2/eval/page_disjoint_real_human_review/labels/`

These labels are frozen eval truth only. Do not add them or their pages to
training, mining, synthetic backgrounds, threshold tuning, or GPT/model relabel
loops.

Launch human review for the diagnostic touched-real style-balance supplement:

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
but `page_disjoint_real` should now be human-reviewed directly. Do not use this
command to create eval truth:

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

Build a static HTML viewer for the non-frozen postprocessing diagnostic rows.
This links each diagnostic row to grouped candidate IDs, existing crop paths,
and source page renders:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\build_postprocessing_diagnostic_viewer.py
```

Purpose: make the diagnostic rows reviewable without opening raw JSONL or
manually chasing crop paths.

Working directory: repo root.

Expected artifact:

- `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_viewer.html`

Open it from a browser or from a static server rooted at the repo root. If crop
images return `404`, the server is likely rooted in the wrong directory.

Safety: read-only. It consumes existing diagnostic rows and candidate crop
paths. It must not edit truth labels, eval manifests, prediction files, model
files, datasets, or training data.

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
