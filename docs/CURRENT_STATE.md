# Current State

Status: read this first before changing ScopeLedger or CloudHammer_v2.

## Active Branch And Workspace

- Branch: `cloudhammer-v2-eval-pivot`
- Application workspace: repo root
- Active detection workspace: `CloudHammer_v2/`
- Legacy detection workspace: `CloudHammer/` reference only

## Documentation Structure Status

Root-level docs now describe the overall ScopeLedger application. CloudHammer_v2
docs describe only revision-cloud detection, eval, labeling, and training
policy.

Canonical root docs:

- `README.md`
- `AGENTS.md`
- `PRODUCT_AND_DELIVERY.md`
- `ROADMAP.md`
- `docs/`

Canonical application docs live directly under `docs/`. Reference artifacts live
under `docs/references/`, `docs/anchors/`, `docs/history/`, and
`docs/meetings/` as appropriate.

## Cleanup Status

Root docs cleanup is substantially complete:

- Root `CLOUDHAMMER.md`, `SCOPELEDGER.md`, `PLAN_PIVOT_5_2_26.md`, and
  duplicate `PRODUCT_AND_DELIVERABLE.md` were removed or replaced by canonical
  paths in prior cleanup work.
- `docs/SECURITY_PRIVACY_POLICY.md` remains as a compatibility stub only.
- Documentation history is preserved under
  `docs/archive/docs_archive_2026_05_02/`.
- Report-only cleanup audits live under `docs/archive_cleanup_audits/`.
- The experiments retention review has been completed, and approved lessons were promoted into CloudHammer_v2 docs without importing experiment code.

## Canonical Now

- Product entrypoint: `README.md`
- Product/deliverable intent: `PRODUCT_AND_DELIVERY.md`
- Product roadmap: `ROADMAP.md`
- Application state: `docs/CURRENT_STATE.md`
- Application module map: `docs/MODULES.md`
- CloudHammer subsystem entrypoint: `CloudHammer_v2/README.md`
- CloudHammer pivot plan: `CloudHammer_v2/PIVOT_PLAN.md`
- Next action queue: `docs/NEXT_ACTIONS.md`

## Intentionally Archived

- Superseded root planning and pointer docs.
- Pre-restructure product, CloudHammer, ScopeLedger, and roadmap drafts.
- Older source policy docs that were summarized into canonical policy docs.
- Report-only audits for runs/experiments cleanup and experiment-retention
  review.

## Do Not Touch

- Do not reorganize source code, data, model runs, or generated outputs.
- Do not move datasets or legacy CloudHammer artifacts.
- Do not import old CloudHammer or experiment scripts without audit.
- Do not treat archived docs as current source of truth.
- Do not blend real and synthetic eval scores.
- Do not treat current-project GPT/API approval as future-project approval.

## CloudHammer_v2 Baseline Status

The first CloudHammer_v2 `page_disjoint_real` baseline was completed on
2026-05-02 using GPT-provisional full-page labels, but that run is now treated
only as provisional scaffolding. The current steering baseline is the
human-audited `page_disjoint_real` scoring completed on 2026-05-04.

- Frozen pages: `17`
- Human truth review queue:
  `CloudHammer_v2/eval/page_disjoint_real_human_review/manifest.jsonl`
- Human truth labels:
  `CloudHammer_v2/eval/page_disjoint_real_human_review/labels/`
- Human-audited eval manifest:
  `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.human_audited.jsonl`
- Human-audited truth summary:
  `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_human_audited_summary.md`
- Human-audited truth contains `26` cloud boxes across `17` pages, with `1`
  empty truth page.
- The clean page-disjoint pool is exhausted under the current strict registry:
  all `17` eligible untouched standard drawing pages were frozen. The set is
  likely plumbing-heavy by sheet metadata heuristic, so aggregate scores need
  bucketed interpretation.
- Style-balance diagnostic touched-real queue:
  `CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/manifest.jsonl`
  with `12` low-use touched pages. This is diagnostic-only and not
  promotion-clean.
- GPT-5.4 full-page labels: provisional only
- GPT-5.5 full-page labels: accidental scratch only, do-not-score
- Current human-audited baseline report:
  `CloudHammer_v2/docs/BASELINE_EVAL_REPORT_2026_05_04.md`
- Prior GPT-provisional baseline report:
  `CloudHammer_v2/docs/BASELINE_EVAL_REPORT_2026_05_02.md`
- Human-audited baseline result at IoU `0.25`: `pipeline_full` F1 `0.741`
  with `8` false positives and `6` misses; `model_only_tiled` F1 `0.479`
  with `47` false positives and `3` misses.
- Human-audited mismatch queue:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/mismatch_review_queue.jsonl`
- Read-only overlay mismatch packet:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/README.md`
- Reviewed mismatch log:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.reviewed.csv`
  with `77` reviewed rows, `0` unreviewed rows, and `0` invalid rows.
- First non-frozen postprocessing diagnostic:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_summary.md`
  with `44` report-only diagnostic rows from `34` non-frozen candidates.
- Static viewer for the diagnostic:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_viewer.html`
  links grouped candidate IDs to existing crop paths and source page renders.
- GPT-5.5 prefilled postprocessing diagnostic review metadata:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_review_log.gpt55_prefill.csv`
  embedded in the default reviewer and also available in companion reviewer
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_viewer.gpt55_prefill.html`.
  These suggestions were human-confirmed/corrected and exported to
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/postprocessing_diagnostic_review_log.reviewed.csv`.
- Dry-run postprocessing plan:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_dry_run_summary.md`.
  It is report-only and proposes `3` merge components plus `10` tighten bbox
  actions, while blocking `12` expand/`tighten_adjust` rows and `3` split rows
  for explicit geometry before any apply step.
- Blocked-geometry reviewer:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_reviewer.html`
  produced
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_review.reviewed.csv`
  with `18` reviewed geometry items.
- GPT-5.5 provisional blocked-geometry prefill:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_review.gpt55_prefill.csv`
  with `18` `gpt_prefilled` provisional rows. Companion reviewer:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/blocked_geometry_review/postprocessing_geometry_reviewer.gpt55_prefill.html`.
- Postprocessing apply dry-run comparison:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_dry_run_20260505/postprocessing_apply_dry_run_summary.md`.
  It is report-first and non-mutating. It previews `25` referenced source
  candidates becoming `23` output candidates, resolves all `15` manual geometry
  row actions, and reports one duplicate split geometry record collapsed into
  the latest reviewed row.
- Non-frozen postprocessing apply output:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/postprocessed_non_frozen_apply_summary.md`.
  It writes a derived manifest only. The `34` source candidates become `32`
  postprocessed candidates, with `13` suppression records for source candidates
  replaced by merge/split outputs.
- Non-frozen postprocessing behavior comparison:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_behavior_comparison_20260505/postprocessing_non_frozen_behavior_summary.md`.
  It compares the original source manifest with the derived postprocessed
  manifest without scoring, tuning, or crop generation. Candidate count changes
  `34` -> `32`, total bbox area ratio is `0.831645`, and it identified `22`
  rows that needed crop regeneration before crop-based inspection/export.
- Postprocessed non-frozen crop regeneration:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/postprocessed_non_frozen_crop_regeneration_summary.md`.
  Dry-run was run first, then `22` regenerated PNG crops were written. The
  crop-ready manifest has `32` rows: `22` regenerated postprocessed crops and
  `10` preserved source crops. It is a separate derived manifest and does not
  mutate labels, eval manifests, predictions, datasets, training data, source
  candidate manifests, or threshold-tuning inputs.
- GPT-5.5 postprocessed crop inspection precheck:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.summary.md`.
  It prechecked all `32` crop-ready candidates after dry-run overlay creation:
  `28` `accept_crop`, `2` `needs_human_review`, and `2`
  `reject_no_visible_cloud`. Companion viewer:
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/dry_run_postprocessor_20260505/postprocessing_apply_non_frozen_20260505/crop_regeneration_20260508/crop_inspection_20260508/postprocessed_crop_inspection.gpt55_prefill.html`.
  The viewer renders red-bbox overlay images as the primary visual evidence for
  all `32` rows. The short browser copy is:
  `CloudHammer_v2/outputs/postprocessed_crop_inspection.gpt55_prefill.html`
  with short local assets under
  `CloudHammer_v2/outputs/postprocessed_crop_inspection_assets/`. These
  findings are provisional inspection metadata only.
- GPT-5.5 cropped supplement prelabels:
  `CloudHammer_v2/data/gpt55_crop_prelabels_small_corpus_supplement_20260502/README.md`
- Current blocker: resolve or accept the `4` non-accepted GPT crop-precheck
  rows, then decide whether the `28` GPT-accepted crop-ready candidates feed
  crop-based inspection/export wiring or a contained pipeline-consumption
  comparison. No labels, eval manifests, predictions, datasets, training data,
  or legacy candidate manifests were mutated.
- Diagnostic scope reset:
  `CloudHammer_v2/docs/DIAGNOSTIC_STOPLIGHT_AUDIT_2026_05_05.md`.
  New CloudHammer diagnostic/review queues must be classified `GREEN`,
  `YELLOW`, or `RED` before creation. Do not create `RED` queues, and do not
  create `YELLOW` queues unless cheap, GPT-prefilled/backfilled or sampled, and
  explicitly approved.

Correction note: GPT-5.5 full-page labels on `page_disjoint_real` were created
by mistake and are marked do-not-score. GPT-5.5 was rerun on the intended
cropped supplement review batch; those outputs are `gpt_provisional` and need
human confirmation/correction before training use.

## Immediate Next Steps

- AGENTS.md and Cursor rules were manually verified against the current docs.
- Resolve or accept the `4` non-accepted GPT-5.5 crop-precheck rows, then use
  the `28` GPT-accepted crop-ready candidates for crop-based inspection/export
  wiring if appropriate; keep frozen `page_disjoint_real` pages as
  measurement-only.
- Triage the two `truth_followup` rows as a separate frozen-truth recheck task.
- Do not create new CloudHammer diagnostic queues unless they pass the
  stoplight rule in the diagnostic scope reset.
- Define and generate the next candidate pools without treating them as eval
  subsets:
  `full_page_review_candidates_from_touched`,
  `mining_safe_hard_negative_candidates`,
  `synthetic_background_candidates`, and
  `future_training_expansion_candidates`.
- Apply the review fatigue guardrail before asking for any remaining
  style-balance diagnostic touched-real review; the queued set has `12` pages,
  so GPT-5.5 sample or full prefill should be considered first.
- Human-confirm/correct the GPT-5.5 cropped supplement prelabels.
- Preserve frozen `page_disjoint_real` pages as eval-only.
- Decide the next CloudHammer training cycle only after postprocessing
  diagnostics and candidate-pool review clarify the remaining training signal.
