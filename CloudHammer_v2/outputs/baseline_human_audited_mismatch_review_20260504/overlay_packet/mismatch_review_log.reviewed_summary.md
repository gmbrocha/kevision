# Mismatch Review Summary

Review log: `CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_review_log.reviewed.csv`
Rows: `77`
Reviewed rows: `77`
Unreviewed rows: `0`

## By Status

- `resolved`: `75`
- `truth_followup`: `2`

## By Human Error Bucket

- `crossing_line_x_patterns`: `4`
- `duplicate_prediction_on_real_cloud`: `12`
- `localization_too_loose`: `8`
- `localization_too_tight`: `4`
- `overmerged_grouping`: `5`
- `prediction_fragment_on_real_cloud`: `36`
- `split_fragment`: `6`
- `truth_box_needs_recheck`: `2`

## By Bucket Category

- `matching_or_scoring_artifact`: `50`
- `true_model_error_or_visual_family`: `27`

## By Mode And Bucket

### `model_only_tiled`
- `crossing_line_x_patterns`: `2`
- `duplicate_prediction_on_real_cloud`: `11`
- `localization_too_loose`: `1`
- `localization_too_tight`: `4`
- `prediction_fragment_on_real_cloud`: `33`
- `split_fragment`: `3`
- `truth_box_needs_recheck`: `1`

### `pipeline_full`
- `crossing_line_x_patterns`: `2`
- `duplicate_prediction_on_real_cloud`: `1`
- `localization_too_loose`: `7`
- `overmerged_grouping`: `5`
- `prediction_fragment_on_real_cloud`: `3`
- `split_fragment`: `3`
- `truth_box_needs_recheck`: `1`

## By Mismatch Type And Bucket Category

### `false_negative`
- `true_model_error_or_visual_family`: `9`

### `false_positive`
- `matching_or_scoring_artifact`: `50`
- `true_model_error_or_visual_family`: `5`

### `localization_low_iou`
- `true_model_error_or_visual_family`: `13`

## Next Action

Use this summary only after the review log has human error buckets. Do not use
frozen eval-page crops as training data, hard negatives, threshold-tuning
inputs, GPT relabel inputs, or synthetic backgrounds.
