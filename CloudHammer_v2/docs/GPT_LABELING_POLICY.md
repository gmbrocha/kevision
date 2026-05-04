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

For `page_disjoint_real`, do not treat GPT full-page labels as eval truth. The
frozen real eval pages should be human-reviewed directly. GPT output on those
pages is scratch/provisional only.

## Drift Guard

Avoid automated label drift. Repeated automated relabeling can reinforce early
mistakes, especially around faint clouds, non-cloud arcs, dense linework, and
partial/clipped regions.

## Stroke Style Review Guard

Stroke thickness may help identify a visual source-family or drawing-set style,
but it cannot by itself prove discipline, company/EOR, or that a mark is a
revision cloud. Track discipline, company/EOR, source family, and drawing set
separately where known. GPT and human review must confirm the actual repeated
scalloped `cloud_motif`.

Do not label dense dark linework, isolated arcs, symbols, door swings,
pipe/duct/conduit-like elements, rounded technical geometry, text, or annotation
clusters as clouds unless the revision-cloud motif is present.

## Mixed-Page Labeling Guard

Do not let GPT classify a full page as no-cloud merely because the most salient
region is a dense no-cloud false-positive trap. If any real revision cloud is
present anywhere on the full page, the full-page label remains positive and
must include that cloud.

Known mixed diagnostic candidate:

`F:\Desktop\m\projects\scopeLedger\CloudHammer\data\rasterized_pages\260313_-_VA_Biloxi_Rev_3_ff19da68_p0192.png`

This page has a real cloud in a sub-drawing and dense main-drawing linework,
estimated around the top `55%` of the page, that may be useful for future
no-cloud hard-negative crops. GPT or model-assisted crop proposals from that
main region must explicitly exclude the real sub-drawing cloud before they can
be reviewed as empty-label hard negatives.

Second known mixed diagnostic candidate:

`F:\Desktop\m\projects\scopeLedger\CloudHammer\data\rasterized_pages\260313_-_VA_Biloxi_Rev_3_ff19da68_p0196.png`

This page has a cloud-free upper/main drawing region and at least one real
cloud in the lower/sub-drawing region. GPT or model-assisted crop proposals for
the upper region may be reviewed later as no-cloud hard negatives only if they
exclude the lower cloud-containing region. Approximate crop guidance is from
the top of the page down to about `70%` page height, roughly the first `800 px`
of a `1170 px` displayed raster view.

## Disagreement Queues

- GPT and YOLO agree strongly: lower-priority or sample audit.
- GPT finds cloud YOLO missed: human review priority.
- YOLO finds cloud GPT rejects: human review priority.
- Both reject: likely negative, with sampled audit.
- Faint, partial, dense, or ambiguous cases: human review priority.

## Training Use

GPT-provisional labels may be used to accelerate the loop, but eval reporting
must identify whether truth is provisional or human-audited.
