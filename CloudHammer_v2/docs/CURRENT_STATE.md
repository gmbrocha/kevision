# CloudHammer_v2 Current State

Status: read this first for CloudHammer_v2 work.

## Pivot Status

CloudHammer_v2 is the active eval-pivot workspace for revision-cloud detection.
The old `CloudHammer/` folder is legacy/reference only. No legacy scripts have
been copied wholesale into CloudHammer_v2; adapted helpers and audited legacy
execution are logged in `CloudHammer_v2/IMPORT_LOG.md`.

The immediate objective was to establish the real full-page eval baseline before
more training, synthetic generation, or pipeline tuning. A first provisional
baseline now exists and needs human audit before it is used for steering.

## Eval Baseline Status

- `model_only_tiled`: first provisional baseline completed on 2026-05-02
- `pipeline_full`: first provisional baseline completed on 2026-05-02
- Baseline report:
  `CloudHammer_v2/docs/BASELINE_EVAL_REPORT_2026_05_02.md`
- Current blocker: the first baseline must be rerun against the consolidated
  human-audited `page_disjoint_real` truth. The provisional GPT full-page labels
  are scaffolding/scratch only and must not drive model selection, training
  decisions, threshold tuning, or promotion claims.

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
  provisional real baseline is audited enough to be a trustworthy ruler

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
The frozen full-page eval pages are now queued for direct human review, and the
cropped provisional labels remain a separate later review task.

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
source-controlled split became the active standard. It now has a first
GPT-provisional page-disjoint baseline, but still has not passed human-audited
frozen full-page eval.

## Legacy Manifest Superset Audit Status

Legacy manifest superset audit completed. The current touched registry is complete for training/review-stage contamination and should remain unchanged for now. Older manifests add weaker provenance only: delta marker detection, review-priority queue membership, and unreviewed candidate ROI generation. These may later become separate provenance fields without changing the binary `touched` guard.

Model/pipeline architecture and candidate-selection audit work is complete enough for the next step. Remaining work is the actual baseline eval comparing `model_only_tiled` vs `pipeline_full` on `page_disjoint_real`.

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

1. Run/rerun `model_only_tiled` and `pipeline_full` scoring against:
   `CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.human_audited.jsonl`
2. Human-review `style_balance_diagnostic_real_touched_20260503`.
3. Human-review/correct the GPT-5.5 cropped supplement prelabels.
4. Human-audit `model_only_tiled` and `pipeline_full` mismatch cases after the
   human-audited baseline is rerun.
5. Convert audited full-page eval corrections into frozen eval truth, not
   training data.
6. Bucket false positives and misses by error family.
7. Decide the next training cycle only after the audited baseline is credible.
8. Implement `synthetic_diagnostic` after the real baseline is audited enough to
   serve as a trustworthy ruler.

## Do Not Touch

- Do not import old scripts without audit and `IMPORT_LOG.md` entry.
- Do not move existing data, model runs, or legacy outputs.
- Do not train on, mine from, relabel, tune against, or synthesize backgrounds
  from frozen real eval pages once selected.
- Do not use marker/delta context as proof of a cloud.
- Do not blend real and synthetic eval metrics.
- Do not start synthetic generation before the real baseline has been audited
  enough to be trustworthy.