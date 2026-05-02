# ScopeLedger Roadmap

Status: canonical application roadmap as of 2026-05-02.

Detailed application docs live in `docs/`. Cloud detection details live in
`CloudHammer_v2/`.

## Active Pivot

The active blocker is the CloudHammer v2 eval pivot: establish a frozen
full-page evaluation ruler before more detector training or synthetic data
generation.

Priority:

1. Build touched-page registry and freeze guards.
2. Freeze `page_disjoint_real` from eligible full pages.
3. Generate GPT-provisional full-page labels.
4. Produce overlays/contact sheets for audit.
5. Evaluate `model_only_tiled` and `pipeline_full` against the same labels.
6. Implement synthetic diagnostics only after the real eval baseline exists.

## Product Sequence

1. **Demo-grade workbook path:** already proven as a rough end-to-end flow from
   CloudHammer candidates into backend/export workbook output.
2. **First-pass text/OCR extraction:** exists as review scaffolding, but not as
   solved scope understanding.
3. **CloudHammer_v2 eval/reliability pivot:** current work; build trustworthy
   full-page eval and clarify model-vs-pipeline behavior.
4. **CloudHammer_v2 training improvement:** resume only after the frozen real
   eval baseline exists.
5. **Detail extraction:** improve itemized/detail extraction from accepted
   cloud regions after detection/crop trust improves.
6. **Client workflow integration:** align output with Kevin's pricing/review
   workflow and modification/RFI context.
7. **Production hardening:** repeatable runs, artifact hygiene, deployment
   notes, and project-specific security gates.

## Near-Term Exit Criteria

- Frozen real eval pages are protected by guards.
- Full-page ground truth labels exist with label status recorded.
- `model_only_tiled` and `pipeline_full` are reported separately.
- Synthetic diagnostics remain deferred until real eval baseline exists.
- Root docs and `CloudHammer_v2` docs stay separated by responsibility.

## Current Non-Goals

- Do not reorganize source code or data while creating the eval pivot.
- Do not move existing datasets, model runs, or legacy `CloudHammer/` assets.
- Do not blend synthetic diagnostic scores with real eval scores.
- Do not treat future-project GPT approval as implied by the current project
  exception.
