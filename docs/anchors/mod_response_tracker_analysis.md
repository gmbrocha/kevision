# Biloxi RFP And Undefinitized Mod Response Tracker

Source file:

- `Biloxi RFP and Undefinitized Mod response tracker.xlsx`

Received / inspected:

- 2026-04-24

## What This Appears To Be

This is Kevin's higher-level modification/RFP tracking workbook.

It is not the detailed cloud/change-item workbook we are building. It is the
shared-file style tracker Kevin described: a job-level log for RFPs,
undefinitized modifications, response dates, estimates, submitted/final costs,
commitments, and action history.

In plain English:

- our workbook answers: "what changed on the drawings?"
- this workbook answers: "what RFPs/mods exist, what is their status, cost, and response history?"

## Workbook Sheets

### `Mod Log`

Purpose:

- tracks undefinitized mods and formal mods.

Important columns:

- `RFP/Mod Number`
- `Date Received`
- `Description`
- `Date Response Required`
- `Date Response Received`
- `Days Outstanding`
- `Days open`
- `Open /Closed`
- `30 Day Response Date`
- `MOD Type`
- `MOD Costs`
- `MOD Projections`
- `MOD Actuals`
- `Submitted MOD Cost`
- `Final MOD Cost`
- `Correspondence provided`
- `Revised`
- `Notes/How resolved (Mod, etc)`
- `Fragnet status`

Examples:

- `Undefinitized Mod P00003` / `P00003`
- `Undefinitized Mod P00005` / `P00005`
- descriptions such as `Conformed drawings set`, `Automatic Transfer Switches`

### `RFP Log`

Purpose:

- tracks RFPs and quote/response dates.

Important columns:

- `RFP/Mod Number`
- `Date Received`
- `Description`
- `Date Response Required`
- `Date Response Received`
- `Days Outstanding`
- `Days open`
- `Open /Closed`
- `30 Day Response Date`
- `Projections`
- `Date Quote Provided`
- `Final RFP Price`
- `Correspondence provided`
- `Notes/How resolved (Mod, etc)`
- `Fragnet status`

Examples:

- `1`
- `2`
- `2R1`
- `2R2`
- `3R2`

The `R1`, `R2`, etc. suffix appears to mean resubmission/revision of the RFP
response, not necessarily a drawing revision.

### `Committed Cost Tracker`

Purpose:

- tracks committed subcontractor/vendor cost against a unilateral mod estimate.

Important columns:

- `Unilateral MOD Estimate`
- `Committed Sub and Type`
- `Commitments`
- `Variance`
- `Final MOD Value`

Examples:

- `OHC - PSA`
- `OHC - CO#1`
- `Alloy - CO#4`

### `Action Log`

Purpose:

- dated activity/history log.

Columns:

- `Date`
- `Who`
- `Action`

Examples:

- RFI submitted
- pricing submitted
- questions from Government/owner
- resubmissions

## Product Meaning

This workbook confirms Kevin's 2026-04-24 answers:

- Excel is central to the workflow.
- A modification is tracked above the drawing/package level.
- RFP/mod status, response dates, quote dates, and costs live in a separate
  management tracker.
- The detailed drawing-change workbook should feed or support this process, but
  should not try to replace the whole tracker in v1.

## V1 Demo Implications

Do:

- generate the detailed drawing-change workbook as planned;
- include enough header/context to connect it to a Mod/RFP tracker item;
- leave downstream pricing/contract columns blank or reviewable;
- support `Needs Review` / `Review Reason` in Excel;
- make it easy for a user to connect a revision package to `P00005`, `RFP 7`,
  etc.

Do not:

- turn the cloud/change workbook into this full response tracker for v1;
- infer Mod/RFP grouping from filenames only;
- auto-fill committed costs or subcontractor pricing fields;
- treat `R1` / `R2` suffixes in this tracker as drawing revision numbers without
  context.

## Possible Future Integration

Later, the app could import or reference this tracker to:

- select a Mod/RFP as the job context;
- prefill workbook header fields;
- attach drawing-change output to a tracker row;
- update status fields or add action-log entries.

For v1, manual association is enough.
