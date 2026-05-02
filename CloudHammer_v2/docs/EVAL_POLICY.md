# Eval Policy

Status: canonical CloudHammer_v2 eval policy.

## Eval Subsets

Use separate named subsets:

- `page_disjoint_real`: main steering eval for this cycle
- `gold_source_family_clean_real`: tiny pristine sanity check if available
- `synthetic_diagnostic`: controlled diagnostic wind tunnel, not proof of
  real-world performance

Do not blend scores across subsets.

## Full-Page Truth

Full-page labels are the source of truth. Inference may tile/crop internally,
but predictions must map back to full-page coordinates for scoring.

Empty labels are required for true no-cloud pages.

## Frozen Real Page Rules

No frozen real eval page may enter:

- training
- crop extraction
- hard-negative mining
- synthetic backgrounds
- threshold tuning
- GPT/model relabel loops
- future mining

## Label Status

Labels must track status:

- `gpt_provisional`
- `human_audited`
- `human_corrected`

Reports must state label status.

## Baseline Paths

- `model_only_tiled`: YOLOv8 tiled full-page inference with NMS and coordinate
  mapping only
- `pipeline_full`: full CloudHammer pipeline behavior

Both must evaluate against the same frozen labels.
