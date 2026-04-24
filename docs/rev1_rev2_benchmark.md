# Rev 1 / Rev 2 Benchmark

## Goal

Measure whether the tool is meaningfully better than the current manual
workflow for:

1. building a conformed set of the latest drawings
2. surfacing clouded revisions on the correct sheets
3. producing a clear reviewable deliverable for downstream pricing/review

The benchmark should answer:

- Is the tool faster?
- Is the latest-sheet identification correct?
- Is the cloud/change output useful enough to review rather than rewrite?
- Where is time being spent?

## What To Compare

Run the same small job two ways:

1. Manual workflow
2. Tool-assisted workflow

Use only:

- `Revision #1 - Drawing Changes`
- `Revision #2 - Mod 5 grab bar supports`

Those are the exact sets called out in Kevin's email and remain the right first
benchmark scope.

## Manual Workflow Benchmark

Have Kevin or another domain reviewer do the task the normal way.

Start the timer when they begin opening/comparing files.

Stop the timer when they have:

- identified the latest drawing version per affected sheet
- marked or noted superseded sheets
- produced a usable list/report of clouded revisions or deliverable rows

Record:

- total elapsed minutes
- number of final deliverable rows
- number of affected sheets
- notes on where time was spent

## Tool-Assisted Workflow Benchmark

Use the tool on a freshly scanned workspace.

Current suggested run:

```powershell
python -m revision_tool scan revision_sets workspace_demo_accuracy
python -m revision_tool serve workspace_demo_accuracy --port 5000
```

If a later CloudHammer-assisted flow exists, run the same benchmark again with
that version and store it as a separate tool-assisted run.

Start the timer when review begins in the tool.

Stop the timer when the reviewer has:

- identified the latest sheets through the conformed/superseded output
- reviewed enough candidate regions/items to produce a usable deliverable
- exported or finalized the resulting artifacts

Record:

- total elapsed minutes
- number of review items seen
- number accepted
- number rejected
- number still pending
- number of final deliverable rows
- notes on what slowed things down

## Suggested Success Metrics

### Speed

- `manual_total_minutes`
- `tool_total_minutes`
- `minutes_saved`
- `percent_time_reduction`

Formula:

- `minutes_saved = manual_total_minutes - tool_total_minutes`
- `percent_time_reduction = minutes_saved / manual_total_minutes`

### Review Efficiency

- `review_items_seen`
- `review_items_accepted`
- `review_items_rejected`
- `review_items_pending`
- `acceptance_rate`

Formula:

- `acceptance_rate = review_items_accepted / review_items_seen`

This tells you whether the review queue is mostly useful or mostly noise.

### Accuracy / Completeness

After both workflows, compare outputs.

Record:

- `manual_deliverable_row_count`
- `tool_deliverable_row_count`
- `matching_rows`
- `manual_only_rows`
- `tool_only_rows`
- `unclear_rows_requiring_rewrite`

This tells you whether the tool is missing important scope, inventing junk, or
creating rows that still need heavy cleanup.

### Conformed Set Quality

Record:

- `affected_sheet_count`
- `sheets_correctly_marked_superseded`
- `sheets_with_wrong_latest_version`

This remains one of the most important measurements because Kevin's email
explicitly calls out the pain of accidentally working from outdated revisions.

## Minimum Useful Benchmark

You do not need a huge study.

One useful pass is:

1. Do Rev 1 + Rev 2 manually and record the time.
2. Do the same scope with the tool.
3. Compare:
   - total time
   - number of usable deliverable rows
   - number of missed / extra rows
   - whether latest sheets were correctly identified
   - how much cleanup/rewrite was still needed

## Recommended Benchmark Sheet

Use one row for the overall run, plus optional per-phase timing.

### Overall Run Columns

- `run_date`
- `reviewer`
- `workflow`
- `revision_scope`
- `elapsed_minutes`
- `affected_sheet_count`
- `final_deliverable_row_count`
- `review_items_seen`
- `review_items_accepted`
- `review_items_rejected`
- `review_items_pending`
- `matching_rows`
- `manual_only_rows`
- `tool_only_rows`
- `wrong_latest_sheet_count`
- `unclear_rows_requiring_rewrite`
- `notes`

### Workflow Values

- `manual`
- `tool-assisted`
- `tool-assisted-cloudhammer`

Use `tool-assisted-cloudhammer` only after CloudHammer is integrated enough to
affect the deliverable flow.

### Revision Scope Value

- `Rev1+Rev2`

## Phase Timing

If you want more detail, split elapsed time into:

- `time_identify_latest_sheets_minutes`
- `time_find_clouded_changes_minutes`
- `time_build_deliverable_minutes`
- `time_cleanup_minutes`

This is useful because the tool may save time in one phase but still create
cleanup in another.

## What Good Looks Like

The tool is worth continuing if it can do all of the following:

- reduce total time by at least 30 to 50 percent
- correctly identify latest sheet versions
- avoid missing major clouded changes
- keep reviewer cleanup manageable
- produce a deliverable that is mostly review/edit, not rewrite-from-scratch

If the tool saves little time or creates too much cleanup, the next work
should focus on queue quality, cloud quality, and deliverable clarity before
any larger architecture changes.

## Next Step After Benchmark

If the benchmark is promising:

- tighten the review flow around the strongest artifacts
- improve clarity of exported deliverable rows
- rerun the benchmark after CloudHammer is integrated

If the benchmark is poor:

- measure where the time went
- fix the biggest bottleneck first

Likely bottlenecks:

- too many noisy candidate regions
- weak cloud detection
- unclear scope rows
- too much reviewer cleanup
- wrong latest-sheet resolution
