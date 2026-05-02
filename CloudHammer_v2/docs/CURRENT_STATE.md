# CloudHammer_v2 Current State

Status: read this first for CloudHammer_v2 work.

## Active State

CloudHammer_v2 is a clean eval-pivot workspace. It contains docs and empty
scaffold folders only. No legacy code has been imported yet.

## Current Goal

Establish a real full-page eval baseline before more training or synthetic
generation.

Immediate order:

1. Build touched-page registry and freeze guards.
2. Freeze `page_disjoint_real`.
3. Generate GPT-provisional full-page labels.
4. Produce overlays/contact sheets for human audit.
5. Evaluate `model_only_tiled` and `pipeline_full`.
6. Start synthetic diagnostics only after the real baseline exists.

## Constraints

- `CloudHammer/` is legacy/reference only.
- Do not import old scripts without audit.
- Do not move existing data or model runs.
- Do not blend real and synthetic eval scores.
- GPT is approved for this current project, not automatically for future
  projects.
