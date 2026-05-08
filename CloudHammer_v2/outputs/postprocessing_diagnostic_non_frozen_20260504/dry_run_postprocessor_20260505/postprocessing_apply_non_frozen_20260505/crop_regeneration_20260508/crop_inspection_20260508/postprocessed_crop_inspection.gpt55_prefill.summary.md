# GPT-5.5 Postprocessed Crop Inspection Prefill

This is provisional inspection metadata only. It does not modify source manifests, labels, eval truth, predictions, datasets, model files, training data, or threshold-tuning inputs.

- Dry run: `False`
- Rows: `32`
- API predictions: `32`
- Prefill CSV: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\crop_regeneration_20260508\crop_inspection_20260508\postprocessed_crop_inspection.gpt55_prefill.csv`
- Prediction JSONL: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\crop_regeneration_20260508\crop_inspection_20260508\gpt55_crop_inspection_prefill\predictions.jsonl`
- API overlay inputs: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_apply_non_frozen_20260505\crop_regeneration_20260508\crop_inspection_20260508\gpt55_crop_inspection_prefill\api_inputs`

## By GPT Status

- `gpt_prefilled`: `28`
- `needs_followup`: `2`
- `not_actionable`: `2`

## By GPT Decision

- `accept_crop`: `28`
- `needs_human_review`: `2`
- `reject_no_visible_cloud`: `2`

## By Recommended Next Step

- `exclude_from_crop_consumption`: `2`
- `human_review_before_use`: `2`
- `use_for_crop_inspection_or_export`: `28`

## Non-Accepted Rows

| Row | Decision | Next step | Candidate | Notes |
| ---: | --- | --- | --- | --- |
| 20 | `reject_no_visible_cloud` | `exclude_from_crop_consumption` | `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3_p0005_whole_001` | GPT-5.5 crop precheck, confidence 0.78: The red bbox covers a busy architectural plan area with room labels, walls, door swings, and a revision triangle, but I do not see a clear scalloped revision-cloud boundary in or near the box. Per policy, the revision triangle and dense linework alone are insufficient evidence of a cloud. |
| 23 | `needs_human_review` | `human_review_before_use` | `Drawing_Rev2-_Steel_Grab_Bars_AE107_e23b5995_p0000_whole_001` | GPT-5.5 crop precheck, confidence 0.58: There appears to be a possible scalloped revision-cloud boundary around the central patient bathroom area, but the red bbox is broad and includes dense architectural linework plus portions of adjacent rooms/bathrooms. It is not fully clear whether this is one complete clouded area or a partial/over-broad capture, so human review is recommended before use. |
| 24 | `needs_human_review` | `human_review_before_use` | `Drawing_Rev2-_Steel_Grab_Bars_R1_AE107.1_9b6a81f4_p0000_whole_001` | GPT-5.5 crop precheck, confidence 0.55: The red bbox covers a large, dense plan area with some heavy rounded/curvilinear linework near the bbox edges that may be a revision cloud, but a complete scalloped cloud outline is not clearly distinguishable from walls/plan graphics. The candidate is likely not blank or corrupted, but visual confirmation is borderline. |
| 29 | `reject_no_visible_cloud` | `exclude_from_crop_consumption` | `Revision_Set_7_37f6066a_p0002_whole_002` | GPT-5.5 crop precheck, confidence 0.95: The red bbox encloses a circular north arrow/plan symbol with straight crosshair/arrow linework. There is no visible scalloped revision cloud in or near the bbox. |

All GPT decisions remain provisional until accepted by the review/apply workflow.
