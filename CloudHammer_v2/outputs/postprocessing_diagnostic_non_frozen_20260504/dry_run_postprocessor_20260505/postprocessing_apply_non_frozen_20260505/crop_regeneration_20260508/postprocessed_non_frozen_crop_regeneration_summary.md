# Postprocessed Non-Frozen Crop Regeneration

Status: `regenerated_crop_manifest_written`

Purpose: regenerate crop images for postprocessed non-frozen candidates whose boxes changed after reviewed postprocessing.

Safety: this writes derived crop artifacts only. It does not edit source candidate manifests, labels, eval manifests, predictions, model files, datasets, training data, or threshold-tuning inputs.

## Counts

- candidates in input manifest: `32`
- regeneration targets: `22`
- regenerated crops written: `22`
- preserved source crops: `10`

## Input Crop Status

- `needs_regeneration_for_postprocessed_bbox`: `22`
- `source_crop_preserved`: `10`

## Output Crop Status

- `postprocessed_crop_regenerated`: `22`
- `source_crop_preserved`: `10`

## Target Actions

- `corrected_bbox_update`: `1`
- `merge_component_bbox`: `3`
- `split_child_bbox`: `8`
- `tighten_bbox`: `10`

## Artifacts

- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\crop_regeneration_20260508\postprocessed_non_frozen_crop_regeneration_plan.jsonl`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\crop_regeneration_20260508\postprocessed_non_frozen_candidates_manifest.regenerated_crops.jsonl`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\crop_regeneration_20260508\postprocessed_non_frozen_crop_regeneration_records.jsonl`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\crop_regeneration_20260508\crops`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\crop_regeneration_20260508\postprocessed_non_frozen_crop_regeneration_summary.json`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\crop_regeneration_20260508\postprocessed_non_frozen_crop_regeneration_summary.md`

## Warnings

- none

Next step: use the crop-ready regenerated manifest for any crop-based inspection or export wiring.
