# Non-Frozen Postprocessing Behavior Comparison

Status: report-first metadata comparison only. This compares the original non-frozen source candidate manifest with the derived postprocessed manifest.

Safety: no labels, eval manifests, predictions, model files, source manifests, datasets, training data, crops, or threshold-tuning inputs were edited.

## Counts

- source candidates: `34`
- postprocessed candidates: `32`
- candidate count delta: `-2`
- suppressed source candidates: `13`
- source pages: `14`
- postprocessed pages: `14`

## BBox Area

- source bbox area sum: `38442489.873`
- postprocessed bbox area sum: `31970507.296`
- bbox area delta: `-6471982.577`
- bbox area ratio postprocessed/source: `0.831645`

## Postprocessing Actions

- `carried_through_not_flagged_by_diagnostic`: `9`
- `corrected_bbox_update`: `1`
- `merge_component_bbox`: `3`
- `split_child_bbox`: `8`
- `tighten_bbox`: `10`
- `unchanged`: `1`

## Source Behavior Counts

- `carried_through_not_flagged_by_diagnostic`: `9`
- `corrected_bbox_update`: `1`
- `replaced`: `13`
- `tighten_bbox`: `10`
- `unchanged`: `1`

## Crop Status

- `needs_regeneration_for_postprocessed_bbox`: `22`
- `source_crop_preserved`: `10`

## Page Count Delta Buckets

- `candidate_count_decreased`: `2`
- `candidate_count_increased`: `1`
- `candidate_count_same`: `11`

## Largest Page Area Reductions

- `Revision_Set__7:p0002`: candidates `2` -> `2`, area delta `-2831399.906`
- `260303-VA_Biloxi_Rev_5_RFI-126:p0002`: candidates `5` -> `1`, area delta `-2127744.072`
- `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: candidates `8` -> `14`, area delta `-1273048.895`
- `260313_-_VA_Biloxi_Rev_3:p0173`: candidates `1` -> `1`, area delta `-339310.251`
- `Revision__1_-_Drawing_Changes:p0001`: candidates `2` -> `2`, area delta `-139380.937`

## Artifacts

- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_behavior_comparison_20260505\postprocessing_non_frozen_behavior_by_source.jsonl`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_behavior_comparison_20260505\postprocessing_non_frozen_behavior_by_page.jsonl`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_behavior_comparison_20260505\postprocessing_non_frozen_behavior_summary.json`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_behavior_comparison_20260505\postprocessing_non_frozen_behavior_summary.md`

Next step: if crop-based inspection/export is needed, regenerate crops for the rows marked `needs_regeneration_for_postprocessed_bbox`.
