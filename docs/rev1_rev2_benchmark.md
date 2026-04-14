# Rev 1 / Rev 2 Benchmark

## Goal

Measure whether the tool is meaningfully faster than the current manual workflow for:

1. building a conformed set
2. producing a pricing-ready list of clouded changes

The benchmark should answer:

- Is the tool faster?
- Is the output accurate enough to trust?
- Where is time being spent?

## What To Compare

Run the same small job two ways:

1. Manual workflow
2. Tool-assisted workflow

Use only:

- `Revision #1 - Drawing Changes`
- `Revision #2 - Mod 5 grab bar supports`

Those are the exact sets mentioned in the email and are the right first benchmark.

## Manual Workflow Benchmark

Have your friend do the task the normal way.

Start timer when they begin opening / comparing files.

Stop timer when they have:

- identified the latest drawing version per affected sheet
- marked or noted superseded sheets
- produced a pricing list of clouded changes

Record:

- total elapsed minutes
- number of final pricing items
- number of affected sheets
- notes on where time was spent

## Tool-Assisted Workflow Benchmark

Use the current app with a freshly scanned workspace.

Suggested run:

```powershell
python -m revision_tool scan revision_sets workspace_demo_accuracy
python -m revision_tool serve workspace_demo_accuracy --port 5000
```

Start timer when review begins in the app.

Stop timer when the reviewer has:

- reviewed enough change items to produce a usable pricing list
- identified latest sheets through the conformed/superseded view
- exported the resulting artifacts

Record:

- total elapsed minutes
- number of reviewed queue items
- number approved
- number rejected
- number still pending
- number of final pricing items
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

- `queue_items_seen`
- `queue_items_approved`
- `queue_items_rejected`
- `approval_rate`

Formula:

- `approval_rate = queue_items_approved / queue_items_seen`

This tells you whether the queue is mostly useful or mostly noise.

### Accuracy / Completeness

After both workflows, compare outputs.

Record:

- `manual_pricing_item_count`
- `tool_pricing_item_count`
- `matching_items`
- `manual_only_items`
- `tool_only_items`

This tells you whether the tool is missing important scope or inventing junk.

### Conformed Set Quality

Record:

- `affected_sheet_count`
- `sheets_correctly_marked_superseded`
- `sheets_with_wrong_latest_version`

This is important because the email says the biggest pain is avoiding outdated revisions.

## Minimum Useful Benchmark

You do not need a huge study.

One useful benchmark pass is:

1. Your friend does Rev 1 + Rev 2 manually and notes the time.
2. The same material is done using the app.
3. Compare:
   - total time
   - number of usable pricing items
   - number of missed / extra items
   - whether latest sheets were correctly identified

## Recommended Benchmark Sheet

Use one row for the overall run, plus optional per-phase timing.

### Overall run columns

- `run_date`
- `reviewer`
- `workflow`
- `revision_scope`
- `elapsed_minutes`
- `affected_sheet_count`
- `final_pricing_item_count`
- `queue_items_seen`
- `queue_items_approved`
- `queue_items_rejected`
- `queue_items_pending`
- `matching_items`
- `manual_only_items`
- `tool_only_items`
- `wrong_latest_sheet_count`
- `notes`

### Workflow values

- `manual`
- `tool-assisted`

### Revision scope value

- `Rev1+Rev2`

## Phase Timing

If you want more detail, split elapsed time into:

- `time_identify_latest_sheets_minutes`
- `time_find_clouded_changes_minutes`
- `time_write_pricing_list_minutes`
- `time_cleanup_minutes`

This is useful because the app may save time in one phase but not another.

## What Good Looks Like

The tool is worth continuing if it can do all of the following:

- reduce total time by at least 30 to 50 percent
- correctly identify latest sheet versions
- avoid missing major clouded pricing items
- keep reviewer cleanup manageable

If the tool saves little time or creates too much cleanup, the next work should focus on queue quality and export shape before any larger architecture changes.

## Next Step After Benchmark

If the benchmark is promising:

- add `pricing_change_log.csv/json`
- optimize queue quality
- improve dedupe across revision sets

If the benchmark is poor:

- measure where the time went
- fix the biggest bottleneck first

Likely bottlenecks:

- too many noisy `visual-region` items
- weak scope summaries
- export not shaped for pricing
