# Postprocessing Blocked-Geometry Reviewer

Status: review artifact only. This viewer is seeded from the dry-run postprocessing plan and captures explicit geometry decisions for blocked expand, split, and merge-component cases.

Safety: no source candidate manifest, labels, eval manifests, predictions, model files, datasets, training data, or threshold-tuning inputs are edited.

## Queue

- geometry items: `18`
- `expand_geometry`: `11`
- `merge_component_geometry`: `3`
- `split_geometry`: `3`
- `tighten_adjust_geometry`: `1`

Review fatigue guardrail: queue size is between `10` and `50`; GPT-5.5 geometry prefill may be considered, but any geometry remains provisional until human accepted.

## Artifacts

- viewer: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\blocked_geometry_review\postprocessing_geometry_reviewer.html`
- review log: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\blocked_geometry_review\postprocessing_geometry_review.csv`
- source dry-run plan: `F:\Desktop\m\projects\scopeLedger\CloudHammer_v2\outputs\postprocessing_diagnostic_non_frozen_20260504\dry_run_postprocessor_20260505\postprocessing_dry_run_plan.jsonl`

Export reviewed geometry as `postprocessing_geometry_review.reviewed.csv` beside the template log.
