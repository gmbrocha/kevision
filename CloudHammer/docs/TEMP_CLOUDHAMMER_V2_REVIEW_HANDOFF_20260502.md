# CloudHammer V2 Review Handoff - 2026-05-02

Status: temporary handoff note for the current CloudHammer V2 training cycle.

## Current Step

The next/current step is human review in LabelImg. Do not train the next models
until the review batches below are saved as human-reviewed labels or reviewed
empty labels.

## Why

The current objective is maximum company-specific reliability from revision sets
1-7. The 14-page full-page eval is now treated as a debug regression set because
it overlaps training source pages on `12 / 14` pages. We need source-controlled
training/eval material and more hard negatives before promoting another model.

## Review Queues

Primary 300-crop expansion:

```powershell
cd F:\Desktop\m\projects\scopeLedger\CloudHammer
..\.venv\Scripts\python.exe scripts\launch_labelimg_batch.py small_corpus_expansion_20260502
```

Supplemental 150-crop expansion:

```powershell
cd F:\Desktop\m\projects\scopeLedger\CloudHammer
..\.venv\Scripts\python.exe scripts\launch_labelimg_batch.py small_corpus_expansion_supplement_20260502
```

Both batches are GPT-seeded for review only. Seed labels preserve API mtimes, so
they should not count as reviewed training truth until a human saves them or
adds review markers.

## Batch Contents

Primary batch:

- path: `CloudHammer/data/review_batches/small_corpus_expansion_20260502`
- rows: `300`
- mix: `131` normal hard negatives, `153` weird/faint/partial-style candidates,
  `16` large/dense-context candidates
- GPT prelabels: `166` new calls, `134` skipped existing API labels, `0`
  failures
- seed safety check: `0 / 300` labels newer than API labels

Supplemental batch:

- path:
  `CloudHammer/data/review_batches/small_corpus_expansion_supplement_20260502`
- rows: `150`
- excludes current reviewed manifest IDs, the first 300-crop expansion batch,
  and already API-labeled IDs
- mix: `87` normal hard negatives, `60` weird/faint/partial-style candidates,
  `3` large/dense-context candidates
- revision mix: Rev 1 `35`, Rev 2 `38`, Rev 3 `62`, Rev 4 `15`
- GPT prelabels: `150` new calls, `0` skipped, `0` failures
- seed safety check: `0 / 150` labels newer than API labels

## Source-Control Artifacts

- source audit:
  `CloudHammer/runs/source_audit_small_corpus_20260502/source_audit_summary.md`
- source-controlled train/val manifest:
  `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.jsonl`
- quasi-holdout manifest:
  `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.quasi_holdout.jsonl`

Key audit findings:

- reviewed manifest: `931` rows, `12` source families, `157` source pages
- source-controlled split: `397` train, `105` val
- quasi-holdout: `30` reviewed rows, currently Rev 5 / Rev 7
- cap effect: `399` rows dropped from the source-controlled training manifest
  to reduce Rev 1/source-page dominance

## After Review

After human review, rebuild reviewed manifests from the reviewed queues, then
train two models:

- source-controlled fresh/clean baseline
- fine-tuned continuity model from the current best checkpoint

Compare both against the current best using:

- marker hard-negative eval
- symbol/text hard-negative eval
- debug full-page eval
- source-disjoint val eval
- quasi-holdout eval

Promotion rule: do not promote a model that reduces false positives by quietly
losing large clouds or previously accepted real clouds.
