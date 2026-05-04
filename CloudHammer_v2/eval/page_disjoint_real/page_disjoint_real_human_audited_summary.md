# page_disjoint_real Human-Audited Truth Summary

Generated: `2026-05-03T22:16:11.281700+00:00`

Human-audited manifest: `F:/Desktop/m/projects/scopeLedger/CloudHammer_v2/eval/page_disjoint_real/page_disjoint_real_manifest.human_audited.jsonl`
Review queue manifest: `F:/Desktop/m/projects/scopeLedger/CloudHammer_v2/eval/page_disjoint_real_human_review/manifest.jsonl`
Labels directory: `F:/Desktop/m/projects/scopeLedger/CloudHammer_v2/eval/page_disjoint_real_human_review/labels`

## Counts

- Pages: `17`
- Pages with review markers: `17`
- Total cloud boxes: `26`
- Pages with cloud boxes: `16`
- Empty truth pages: `1`
- Missing review markers: `0`
- Missing labels: `0`

## Discipline Guess From Sheet Metadata

- `architectural_or_likely_architectural`: `1`
- `electrical_or_likely_electrical`: `2`
- `plumbing_or_likely_plumbing`: `12`
- `structural_or_likely_structural`: `2`

These discipline guesses are heuristic metadata only. They are not YOLO classes and are not style truth.

## Notes

- This manifest points at the actual LabelImg-saved raster-stem label files.
- `style_discipline_bucket` remains `unassigned` until explicitly audited.
- The labels are frozen eval truth only and must not enter training, mining, threshold tuning, synthetic backgrounds, or GPT/model relabel loops.
