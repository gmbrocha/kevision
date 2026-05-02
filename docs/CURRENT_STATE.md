# Current State

Status: read this first before changing ScopeLedger or CloudHammer_v2.

## Active Branch And Workspace

- Branch: `cloudhammer-v2-eval-pivot`
- Active detection workspace: `CloudHammer_v2/`
- Legacy detection workspace: `CloudHammer/` reference only
- Product entrypoint: `README.md`
- CloudHammer subsystem entrypoints: `README.md#cloudhammer-subsystem` and
  `CloudHammer_v2/README.md`

## Current Pivot

The project is freezing an evaluation-first CloudHammer_v2 workspace. The next
technical blocker is not more training; it is establishing the full-page eval
ruler.

Immediate order:

1. Build touched-page registry and freeze guards.
2. Freeze `page_disjoint_real`.
3. Generate GPT-provisional full-page labels.
4. Produce overlays/contact sheets for audit.
5. Evaluate `model_only_tiled` and `pipeline_full`.
6. Start synthetic diagnostics only after the real baseline exists.

## Do Not Touch Yet

- Do not reorganize source code or data.
- Do not move datasets, model runs, or legacy CloudHammer artifacts.
- Do not import old CloudHammer scripts into CloudHammer_v2 without audit.
- Do not blend real and synthetic eval scores.
- Do not treat the current GPT/API approval as future-project approval.
- Do not use removed root pointer docs as active source-of-truth files.
