# CloudHammer_v2 Decisions

## 2026-05-02 - Eval-Pivot Workspace

`CloudHammer_v2/` is the active workspace for detection/eval/training policy.
The old `CloudHammer/` folder is legacy/reference.

## 2026-05-02 - Baseline Before Training

Freeze real full-page eval and run baseline comparisons before further detector
training.

## 2026-05-02 - Model vs Pipeline Split

Evaluate `model_only_tiled` and `pipeline_full` separately against the same
frozen labels.

## 2026-05-02 - Separate Eval Subsets

Use separate named subsets: `page_disjoint_real`,
`gold_source_family_clean_real`, and `synthetic_diagnostic`. Do not blend
scores.

## 2026-05-02 - GPT Labeling Exception

GPT may be used heavily for this current project. Label status must distinguish
GPT-provisional output from human-audited or human-corrected truth.

## 2026-05-02 - Synthetic Deferred

Write grammar/spec stubs now, but do not implement synthetic generation until
the real full-page eval baseline exists.
