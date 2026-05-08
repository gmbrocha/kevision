# Postprocessing Dry-Run Plan

Status: dry-run only. This report proposes postprocessing actions from the reviewed diagnostic CSV.

Safety: no labels, eval manifests, prediction files, model files, source candidate manifests, datasets, or training data were edited.

## Counts

- review rows: `44`
- row actions: `44`
- merge components: `3`
- candidate rollups: `25`

## Decisions

- `expand`: `11`
- `merge`: `9`
- `reject_merge`: `10`
- `split`: `3`
- `tighten`: `10`
- `tighten_adjust`: `1`

## Proposed Action Types

- `manual_geometry_required`: `12`
- `manual_split_required`: `3`
- `merge_component_edge`: `9`
- `no_change`: `10`
- `tighten_bbox`: `10`

## Manual Or Blocked Reasons

- `expand_needs_reviewed_full_cloud_geometry_or_merge_component`: `11`
- `split_needs_child_candidate_geometry`: `3`
- `tighten_adjust_not_safe_to_apply_from_tight_member_bbox`: `1`

## Artifacts

- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_dry_run_plan.jsonl`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_dry_run_summary.json`

Next step: inspect this dry-run plan before writing any explicit apply script.
