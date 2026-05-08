# Postprocessing Apply Dry-Run Comparison

Status: report-first dry-run only. This preview converts the reviewed diagnostic and geometry logs into candidate-level behavior without editing any source manifest.

Safety: no labels, eval manifests, prediction files, model files, source candidate manifests, datasets, training data, or threshold-tuning inputs were edited.

## Inputs

- reviewed diagnostic rows: `44`
- reviewed geometry rows: `18`
- source candidate manifest: `F:\Desktop\m\projects\scopeLedger\CloudHammer\runs\whole_cloud_eval_symbol_text_fp_hn_20260502\whole_cloud_candidates_manifest.jsonl`
- frozen manifest guard: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\eval\page_disjoint_real\page_disjoint_real_manifest.human_audited.jsonl`

## Candidate Count Comparison

- referenced source candidates: `25`
- preview output candidates: `23`
- candidate count delta: `-2`

## Output Candidates By Action

- `corrected_bbox_update`: `1`
- `merge_component_bbox`: `3`
- `split_child_bboxes`: `8`
- `tighten_bbox`: `10`
- `unchanged`: `1`

## Source Candidates By Action

- `corrected_bbox_update`: `1`
- `merge_component_bbox`: `11`
- `split_child_bboxes`: `2`
- `tighten_bbox`: `10`
- `unchanged`: `1`

## Geometry Decisions Consumed

- `child_bboxes`: `3`
- `component_bbox`: `3`
- `corrected_bbox`: `1`
- `merge_with_component`: `11`

## Resolution Check

- manual geometry row actions before geometry review: `15`
- unresolved manual geometry rows after geometry review: `0`

## Warnings

- `duplicate_child_geometry_rows_collapsed`: `{'warning_type': 'duplicate_child_geometry_rows_collapsed', 'source_candidate_id': '260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_001', 'kept_geometry_item_id': 'row_010_split_geometry', 'ignored_geometry_item_ids': ['row_009_split_geometry'], 'reason': 'Multiple reviewed split rows targeted the same source candidate; the latest source row was used for the apply-preview.'}`

## Artifacts

- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_dry_run_20260505\postprocessing_apply_dry_run_candidate_preview.jsonl`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_dry_run_20260505\postprocessing_apply_dry_run_changes.jsonl`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_dry_run_20260505\postprocessing_apply_dry_run_summary.json`
- `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_dry_run_20260505\postprocessing_apply_dry_run_summary.md`

Next step: inspect this comparison and decide whether to implement an explicit non-frozen postprocessing apply path.
