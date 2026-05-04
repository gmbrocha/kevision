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
- GPT-5.5 cropped supplement prelabels:
  `CloudHammer_v2/data/gpt55_crop_prelabels_small_corpus_supplement_20260502/README.md`
- Current blocker: spot-check the non-frozen postprocessing diagnostic in the
  static viewer, then build a dry-run postprocessor for merge/suppress/split
  and localization behavior before model selection, training decisions,
  threshold tuning, or promotion claims.

Correction note: GPT-5.5 full-page labels on `page_disjoint_real` were created
by mistake and are marked do-not-score. GPT-5.5 was rerun on the intended
cropped supplement review batch; those outputs are `gpt_provisional` and need
human review before training use.

## Immediate Next Steps

- AGENTS.md and Cursor rules were manually verified against the current docs.
- Spot-check the completed non-frozen postprocessing diagnostic in the static
  viewer for fragments, duplicate predictions, overmerges, split fragments, and
  localization.
- Build the first dry-run postprocessor only on non-frozen diagnostic inputs;
  keep frozen `page_disjoint_real` pages as measurement-only.
- Triage the two `truth_followup` rows as a separate frozen-truth recheck task.
- Define and generate the next candidate pools without treating them as eval
  subsets:
  `full_page_review_candidates_from_touched`,
  `mining_safe_hard_negative_candidates`,
  `synthetic_background_candidates`, and
  `future_training_expansion_candidates`.
- Human-review the diagnostic touched-real style-balance queue.
- Human-review/correct the GPT-5.5 cropped supplement prelabels.
- Preserve frozen `page_disjoint_real` pages as eval-only.
- Decide the next CloudHammer training cycle only after postprocessing
  diagnostics and candidate-pool review clarify the remaining training signal.
