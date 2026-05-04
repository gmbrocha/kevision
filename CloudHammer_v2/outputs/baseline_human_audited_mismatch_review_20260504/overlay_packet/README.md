# Mismatch Review Packet

Status: error-analysis packet for already-reviewed `page_disjoint_real` pages.

This is not a truth-labeling pass. Do not open LabelImg for this packet. Do not
modify truth labels, eval manifests, prediction files, model files, datasets, or
training data. The mismatch review log is intentionally editable for
error-analysis metadata only.

## What To Review

- HTML reviewer: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_reviewer.html`
- Crisp PNG review crops: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\reviewer_crops`
- Contact sheet: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\contact_sheets\mismatch_truth_vs_predictions_contact_sheet.jpg`
- Mismatch JSONL: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_manifest.jsonl`
- Mismatch CSV: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_manifest.csv`
- Blank/template review log: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_review_log.csv`
- Individual overlays: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\overlays`

The HTML reviewer is the primary review surface. The contact sheet is retained
only as a quick overview and should not be the main review tool.

## Human Review Rule

The human cloud/not-cloud judgment is authoritative when the displayed context
is adequate. If the display does not make the case understandable, mark the row
as `tooling_or_matching_artifact` or `not_actionable`; do not treat that as
human uncertainty.

`truth_followup` creates a separate frozen-truth correction/recheck task. It
does not change truth automatically.

`tooling_or_matching_artifact` means the row may reflect IoU matching, duplicate
predictions, crop context, overlay/scoring behavior, or reviewer display limits
rather than a meaningful model error.

Overlay colors:

- Green: human-audited truth box matched at IoU 0.25
- Orange: human-audited truth box missed at IoU 0.25
- Red: prediction false positive at IoU 0.25
- Blue: prediction matched with IoU at least 0.50
- Purple: prediction matched at IoU 0.25 but below IoU 0.50

## HTML Reviewer Workflow

Open `mismatch_reviewer.html` through a local server from the repo root:

```powershell
python -m http.server 8766 --bind 127.0.0.1
```

Then browse to:

```text
http://127.0.0.1:8766/CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_reviewer.html
```

Use the browser UI to fill review metadata and click `Export Reviewed CSV`.
Save the export as `mismatch_review_log.reviewed.csv` in this packet directory,
then run:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\summarize_mismatch_review.py --review-log CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_review_log.reviewed.csv
```

## Auto-Suggested Rows 44-77

Rows `44` through `77` have an auto-suggested draft for human spot review:

- Suggested CSV:
  `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_review_log.autosuggest_rows44_77.csv`
- Suggested-row report:
  `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_review_autosuggest_rows44_77.md`
- Auto-suggest reviewer:
  `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_reviewer.autosuggest_rows44_77.html`

Open the auto-suggest reviewer through the same local server:

```text
http://127.0.0.1:8766/CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_reviewer.autosuggest_rows44_77.html
```

If the suggested rows look reasonable, click `Apply Review Log Values`. This
copies only nonblank embedded review-log values into browser localStorage. It
does not edit truth labels, eval manifests, predictions, model files,
datasets, or training data. Then use the browser reviewer to inspect/correct
rows and export `mismatch_review_log.reviewed.csv`.

## Review Fields

Editable fields:

- `human_error_bucket`
- `human_review_status`
- `human_notes`

Read-only explanation/scoring fields include:

- `nearest_truth_iou`
- `nearest_truth_id`
- `nearest_prediction_id`
- `nearest_prediction_iou`
- `matched_elsewhere`
- `possible_duplicate_prediction`
- `mismatch_reason_raw`

## Review Status Values

- `unreviewed`
- `resolved`
- `truth_followup`
- `tooling_or_matching_artifact`
- `not_actionable`

## Approved Error Buckets

- `actual_false_positive`
- `duplicate_prediction_on_real_cloud`
- `localization_matching_issue`
- `truth_box_needs_recheck`
- `truth_box_too_tight`
- `truth_box_too_loose`
- `prediction_fragment_on_real_cloud`
- `not_actionable_matching_artifact`
- `marker_neighborhood_no_cloud_regions`
- `historical_or_nonmatching_revision_marker_context`
- `isolated_arcs_and_scallop_fragments`
- `fixture_circles_and_symbol_circles`
- `glyph_text_arcs`
- `crossing_line_x_patterns`
- `index_table_x_marks`
- `dense_linework_near_valid_clouds`
- `thick_dark_cloud_false_positive_context`
- `thin_light_cloud_low_contrast_miss`
- `no_cloud_dense_dark_linework`
- `no_cloud_door_swing_arc_false_positive_trap`
- `mixed_cloud_with_dense_false_positive_regions`
- `overmerged_grouping`
- `split_fragment`
- `localization_too_loose`
- `localization_too_tight`
- `truth_needs_recheck`
- `other`

## Packet Summary

- Pages with mismatch rows: `16`
- Mismatch rows: `77`
- By mode: `{'model_only_tiled': 55, 'pipeline_full': 22}`
- By mismatch type: `{'false_positive': 55, 'localization_low_iou': 13, 'false_negative': 9}`
