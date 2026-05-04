# Mismatch Review Packet

Status: read-only error-analysis packet for already-reviewed `page_disjoint_real` pages.

This is not a truth-labeling pass. Do not open LabelImg for this packet, do not
modify truth labels, do not modify eval manifests, and do not write training
data from these frozen eval pages.

## What To Review

- Contact sheet: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\contact_sheets\mismatch_truth_vs_predictions_contact_sheet.jpg`
- Mismatch JSONL: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_manifest.jsonl`
- Mismatch CSV: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_manifest.csv`
- Editable review log: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_review_log.csv`
- Review summary: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_review_summary.md`
- Individual overlays: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\overlays`

Overlay colors:

- Green: human-audited truth box matched at IoU 0.25
- Orange: human-audited truth box missed at IoU 0.25
- Red: prediction false positive at IoU 0.25
- Blue: prediction matched with IoU at least 0.50
- Purple: prediction matched at IoU 0.25 but below IoU 0.50

## Review Fields

Fill these fields in `mismatch_review_log.csv`:

- `human_error_bucket`
- `human_review_status`
- `human_notes`

Then rerun:

```powershell
.\.venv\Scripts\python.exe CloudHammer_v2\scripts\summarize_mismatch_review.py
```

Recommended `human_review_status` values:

- `bucketed`
- `needs_second_look`
- `truth_needs_recheck`
- `not_actionable`

## Approved Error Buckets

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
