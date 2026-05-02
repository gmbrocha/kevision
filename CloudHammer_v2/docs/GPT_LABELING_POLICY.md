# GPT Labeling Policy

Status: current-project CloudHammer_v2 GPT labeling policy.

## Current Project Approval

GPT-5.5 may prelabel crops and full pages for this current project under the
project-specific approval exception.

This is not automatic approval for future projects.

## Label Status

Every label set should track:

- `gpt_provisional`
- `human_audited`
- `human_corrected`

GPT labels can accelerate training, but frozen real holdouts validate progress.

## Drift Guard

Avoid automated label drift. Repeated automated relabeling can reinforce early
mistakes, especially around faint clouds, non-cloud arcs, dense linework, and
partial/clipped regions.

## Disagreement Queues

- GPT and YOLO agree strongly: lower-priority or sample audit.
- GPT finds cloud YOLO missed: human review priority.
- YOLO finds cloud GPT rejects: human review priority.
- Both reject: likely negative, with sampled audit.
- Faint, partial, dense, or ambiguous cases: human review priority.

## Training Use

GPT-provisional labels may be used to accelerate the loop, but eval reporting
must identify whether truth is provisional or human-audited.
