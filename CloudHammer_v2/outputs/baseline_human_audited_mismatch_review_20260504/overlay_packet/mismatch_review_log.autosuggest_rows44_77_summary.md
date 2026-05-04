# Mismatch Review Summary

Review log: `CloudHammer_v2\outputs\baseline_human_audited_mismatch_review_20260504\overlay_packet\mismatch_review_log.autosuggest_rows44_77.csv`
Rows: `77`
Reviewed rows: `34`
Unreviewed rows: `43`

## By Status

- `resolved`: `34`
- `unreviewed`: `43`

## By Human Error Bucket

- `duplicate_prediction_on_real_cloud`: `5`
- `localization_too_loose`: `4`
- `localization_too_tight`: `3`
- `overmerged_grouping`: `1`
- `prediction_fragment_on_real_cloud`: `17`
- `split_fragment`: `4`

## By Bucket Category

- `matching_or_scoring_artifact`: `22`
- `true_model_error_or_visual_family`: `12`

## By Mode And Bucket

### `model_only_tiled`
- `duplicate_prediction_on_real_cloud`: `5`
- `localization_too_tight`: `3`
- `prediction_fragment_on_real_cloud`: `14`
- `split_fragment`: `1`

### `pipeline_full`
- `localization_too_loose`: `4`
- `overmerged_grouping`: `1`
- `prediction_fragment_on_real_cloud`: `3`
- `split_fragment`: `3`

## By Mismatch Type And Bucket Category

### `false_negative`
- `true_model_error_or_visual_family`: `5`

### `false_positive`
- `matching_or_scoring_artifact`: `22`

### `localization_low_iou`
- `true_model_error_or_visual_family`: `7`

## Next Action

Use this summary only after the review log has human error buckets. Do not use
frozen eval-page crops as training data, hard negatives, threshold-tuning
inputs, GPT relabel inputs, or synthetic backgrounds.
