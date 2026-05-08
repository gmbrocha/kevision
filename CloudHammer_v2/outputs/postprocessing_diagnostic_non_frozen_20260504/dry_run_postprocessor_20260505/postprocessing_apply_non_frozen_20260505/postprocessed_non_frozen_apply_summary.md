# Postprocessed Non-Frozen Candidate Manifest

Status: derived non-frozen apply output. This writes a new manifest from the accepted apply dry-run comparison and does not mutate the legacy source manifest.

Approval note: accepted by user in Codex session on 2026-05-05

## Counts

- source manifest candidates: `34`
- referenced source candidates: `25`
- carried-through unflagged candidates: `9`
- postprocessed output candidates: `32`
- candidate count delta vs source manifest: `-2`
- suppressed source candidates: `13`

## Postprocessing Actions

- `carried_through_not_flagged_by_diagnostic`: `9`
- `corrected_bbox_update`: `1`
- `merge_component_bbox`: `3`
- `split_child_bbox`: `8`
- `tighten_bbox`: `10`
- `unchanged`: `1`

## Crop Status

- `needs_regeneration_for_postprocessed_bbox`: `22`
- `source_crop_preserved`: `10`

## Warnings Carried Forward

- `duplicate_child_geometry_rows_collapsed`: `{'ignored_geometry_item_ids': ['row_009_split_geometry'], 'kept_geometry_item_id': 'row_010_split_geometry', 'reason': 'Multiple reviewed split rows targeted the same source candidate; the latest source row was used for the apply-preview.', 'source_candidate_id': '260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_001', 'warning_type': 'duplicate_child_geometry_rows_collapsed'}`

## Artifacts

- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\postprocessed_non_frozen_candidates_manifest.jsonl`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\postprocessed_non_frozen_suppressed_sources.jsonl`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\postprocessed_non_frozen_apply_summary.json`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\postprocessed_non_frozen_apply_summary.md`

Safety: no labels, eval manifests, prediction files, model files, source candidate manifests, datasets, training data, or threshold-tuning inputs were edited.
