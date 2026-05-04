# CloudHammer_v2 Current State

Status: read this first for CloudHammer_v2 work.

## Pivot Status

CloudHammer_v2 is the active eval-pivot workspace for revision-cloud detection.
The old `CloudHammer/` folder is legacy/reference only. No legacy scripts have
been copied wholesale into CloudHammer_v2; adapted helpers and audited legacy
execution are logged in `CloudHammer_v2/IMPORT_LOG.md`.

The immediate objective was to establish the real full-page eval baseline before
more training, synthetic generation, or pipeline tuning. That baseline now
exists against human-audited `page_disjoint_real` truth, and the baseline
mismatch review has been human-bucketed. Current work is postprocessing-first
diagnostics and guarded candidate-pool definition before the next training
decision.

## Eval Baseline Status

- `model_only_tiled`: human-audited baseline scoring completed
- `pipeline_full`: human-audited baseline scoring completed
- Current human-audited baseline report:
  `CloudHammer_v2/docs/BASELINE_EVAL_REPORT_2026_05_04.md`
- Prior GPT-provisional baseline report:
  `CloudHammer_v2/docs/BASELINE_EVAL_REPORT_2026_05_02.md`
- Current result at IoU `0.25`: `pipeline_full` has stronger F1 (`0.741`)
  than `model_only_tiled` (`0.479`) by reducing false positives, while
  `model_only_tiled` has higher recall (`0.885` vs `0.769`).
- Read-only overlay mismatch packet:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/README.md`
  with `77` review rows across `16` pages: `55` false positives, `13`
  low-IoU localization cases, and `9` false negatives.
- Editable mismatch review log:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.csv`
  is the blank/template log and includes scoring/matching explanation fields
  such as `nearest_truth_iou`, `matched_elsewhere`,
  `possible_duplicate_prediction`, and `mismatch_reason_raw`.
- Reviewed mismatch log:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.reviewed.csv`
  has `77` reviewed rows, `0` unreviewed rows, and `0` invalid rows. Summary:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.reviewed_summary.md`.
- Static mismatch reviewer:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_reviewer.html`
  with crisp PNG local and wide crops for each mismatch row. The reviewer now
  shows nearby truth boxes and predictions, explicit IoU/matching context, and
  exports `mismatch_review_log.reviewed.csv`.
- Auto-suggested rows `44`-`77` draft:
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_review_log.autosuggest_rows44_77.csv`
  with a companion spot-review page at
  `CloudHammer_v2/outputs/baseline_human_audited_mismatch_review_20260504/overlay_packet/mismatch_reviewer.autosuggest_rows44_77.html`.
- Human mismatch review signal: `50` rows are matching/scoring artifacts and
  `27` are true model-error or visual-family rows. Dominant buckets are
  `prediction_fragment_on_real_cloud` (`36`), duplicate prediction on real cloud
  (`12`), localization loose/tight (`12` total), `split_fragment` (`6`), and
  `overmerged_grouping` (`5`).
- Current blocker: design the next postprocessing diagnostic on non-frozen data
  before training, threshold tuning, or promotion claims. Two
  `truth_followup` rows require a separate frozen-truth recheck task and do not
  change truth automatically.

## Eval Subset Status

- `page_disjoint_real`: selected, frozen, human-reviewed, and consolidated into
  eval truth:
  `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.human_audited.jsonl`
  with `17` pages, `26` cloud boxes, and `1` empty truth page
- `page_disjoint_real` is plumbing-heavy by sheet metadata heuristic: `12` of
  `17` pages are likely plumbing, so aggregate metrics must be read with that
  skew in mind
- `style_balance_diagnostic_real_touched`: created and queued for human review
  at
  `CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/manifest.jsonl`
  with `12` low-use touched pages: `4` arch, `3` electrical, `2` mechanical,
  `1` structural, and `2` plumbing comparison pages. This set is diagnostic
  only and must not be blended with `page_disjoint_real`.
- `gold_source_family_clean_real`: planned if a tiny pristine source-family-clean
  set is available
- `synthetic_diagnostic`: grammar/spec exists, implementation deferred until the
  reviewed real baseline, postprocessing findings, and candidate pools are
  trustworthy enough to steer diagnostics

## Candidate Pool Status

The following are candidate pools, not eval subsets. They must be generated with
dry-run/report-first discipline where practical and must preserve frozen eval
guards:

- `full_page_review_candidates_from_touched`: touched pages or regions that may
  need direct full-page human review because crop-level review does not equal
  full-page truth.
- `mining_safe_hard_negative_candidates`: candidate no-cloud regions for future
  hard-negative mining, excluding frozen eval pages and any region containing a
  real cloud.
- `synthetic_background_candidates`: candidate no-cloud pages or regions for
  later synthetic background use, excluding frozen eval pages and preserving
  provenance. This does not authorize synthetic generation yet.
- `future_training_expansion_candidates`: candidate rows or regions for later
  reviewed training expansion, gated by eval-freeze, validation, and label-status
  policy.

## Labeling Status

GPT labeling is approved broadly for this current project. GPT labels remain
provisional until reviewed. Current required statuses:

- `gpt_provisional`
- `human_audited`
- `human_corrected`

GPT-provisional full-page labels were generated for the frozen
`page_disjoint_real` pages, but `page_disjoint_real` is now explicitly intended
for direct human review rather than GPT-derived eval truth.

- GPT-5.4 full-page labels: provisional only, not human-audited truth
- GPT-5.5 full-page labels: accidental scratch only, do-not-score
  `CloudHammer_v2/eval/page_disjoint_real_gpt55/DO_NOT_SCORE.md`
- Correct GPT-5.5 target: cropped training/review candidates, not frozen eval
  pages
- GPT-5.5 cropped supplement prelabels completed:
  `CloudHammer_v2/data/gpt55_crop_prelabels_small_corpus_supplement_20260502/README.md`
  with `150` processed, `49` nonempty provisional label files, and `101` empty
  provisional label files

Correction note: GPT-5.5 was first run against frozen full-page eval pages by
mistake. Those outputs are marked do-not-score. The follow-up action was to run
GPT-5.5 on the intended cropped supplement batch instead, which is now complete.
The frozen full-page eval pages have since been human-reviewed and consolidated
as eval truth; the cropped provisional labels remain a separate later review
task.

## Model-vs-Pipeline Audit Status

Audit policy exists at `CloudHammer_v2/docs/MODEL_VS_PIPELINE_AUDIT.md`.
Approved experiment lessons have been promoted into the audit and eval policy
docs. The read-only audit was completed on 2026-05-02:

`CloudHammer_v2/docs/MODEL_VS_PIPELINE_AUDIT_REPORT_2026_05_02.md`

The audit must separate:

- what the YOLOv8 model knows
- what the surrounding pipeline adds
- which pipeline lessons should become labels, hard negatives, or eval cases

Audit conclusion: the latest symbol/text hard-negative checkpoint is a
continuity checkpoint, not a promoted model. It was trained before the
source-controlled split became the active standard. It now has a human-audited
page-disjoint baseline and reviewed mismatch buckets for steering, but it is
still not promoted. The next practical work is postprocessing diagnostics before
any training or promotion decision.

## Legacy Manifest Superset Audit Status

Legacy manifest superset audit completed. The current touched registry is complete for training/review-stage contamination and should remain unchanged for now. Older manifests add weaker provenance only: delta marker detection, review-priority queue membership, and unreviewed candidate ROI generation. These may later become separate provenance fields without changing the binary `touched` guard.

Model/pipeline architecture and candidate-selection audit work is complete enough
for the next step. Human-audited baseline eval comparing `model_only_tiled` vs
`pipeline_full` on `page_disjoint_real` is complete, and mismatch review is
human-bucketed. Remaining work is postprocessing diagnostics, truth-followup
triage, and candidate-pool generation for the next loop.

## Weak provenance signals vs. binary `touched`

Weak provenance signals should stay separate from binary `touched`. Collapsing delta markers, review-priority queues, or unreviewed ROI generation into `touched` would invalidate all 17 frozen `page_disjoint_real` pages without a replacement pool.

## Experiments Retention Review Status

Report-only review completed:

`docs/archive_cleanup_audits/experiments_retention_review_2026_05_02.md`

Approved lessons were promoted into:

- `CloudHammer_v2/docs/MODEL_VS_PIPELINE_AUDIT.md`
- `CloudHammer_v2/docs/EVAL_POLICY.md`
- `CloudHammer_v2/docs/DECISIONS.md`

No experiment code was imported.

## Immediate Next Steps

1. Use the reviewed mismatch summary to design a postprocessing diagnostic on
   non-frozen data for merge/suppress/split/localization behavior.
2. Triage the two `truth_followup` rows as a separate frozen-truth recheck task;
   do not edit truth automatically from mismatch metadata.
3. Define and generate the candidate-pool manifests:
   `full_page_review_candidates_from_touched`,
   `mining_safe_hard_negative_candidates`,
   `synthetic_background_candidates`, and
   `future_training_expansion_candidates`.
4. Human-review `style_balance_diagnostic_real_touched_20260503`.
5. Human-review/correct the GPT-5.5 cropped supplement prelabels.
6. Convert any audited full-page eval corrections into frozen eval truth, not
   training data.
7. Decide the next training cycle only after postprocessing diagnostics and
   candidate-pool review clarify what should become training signal.
8. Implement `synthetic_diagnostic` only after the real baseline and candidate
   pools are trustworthy enough to serve as a diagnostic ruler.

## Do Not Touch

- Do not import old scripts without audit and `IMPORT_LOG.md` entry.
- Do not move existing data, model runs, or legacy outputs.
- Do not train on, mine from, relabel, tune against, or synthesize backgrounds
  from frozen real eval pages once selected.
- Do not tune postprocessing thresholds directly on frozen eval pages; use them
  as a measurement ruler after non-frozen diagnostics.
- Do not use marker/delta context as proof of a cloud.
- Do not blend real and synthetic eval metrics.
- Do not start synthetic generation before the real baseline has been audited
  enough to be trustworthy.
