Status: historical stakeholder Q&A. Current product rules live in
`../../PRODUCT_AND_DELIVERY.md`; current sequencing lives in
`../../ROADMAP.md`.

1. For the Excel deliverable, is a slightly loose but legible crop acceptable, or does each crop need to be tightly framed around only the clouded area?
- Michael answer (kevin not needed): we will strive to get as good of a crop as possible. We will continue until we hit diminishing returns with this. Not going to even ask Kevin.

2. Should index-page clouded changes ever become deliverable rows, or should index pages only help identify revised sheets?
- Michael answer: didn't we already talk about this? I'm fairly sure they would never become deliverable rows. However, they can provide us a parsable index for where clouds actually are (sheet name)
as well as what the revision is going to entail? Right?

3. Should the first version prioritize "find every plausible cloud and flag for review," or "only export high-confidence clouds and risk missing some"?
- Michael answer - we will not ask him this. We are going to iterate until we have cloud detection completely solved, or damn near it. And we'll find every cloud, and we'll do it with high-confidence.

4. What is the acceptable review burden for a mod package? Example: if the tool finds 280 candidates and 40 are false positives, is that still useful?
- Michael answer - not asking him this either. There is no large amount of acceptable false positives. We will iterate until they become rare.

5. For the demo benchmark, what exact manual workflow should we compare against: finding latest sheets, identifying clouded changes, building the workbook, or all of it end-to-end?
- For our first demo, we want an end-to-end run, full deliverable, as good as we have at the time we run it.

Further questions. Hopefully this isn't too tedious. The app is getting very interesting.

1. If one clouded region contains multiple scope items, should that be one workbook row with stacked items, or multiple rows sharing the same drawing/detail/crop?

2. If multiple small clouds are near each other but clearly separate, should each become its own deliverable row even when the note text is similar?

3. If a cloud contains only a leader arrow or points to a detail without text inside, how should Scope Included be written?

4. When a standalone sheet PDF and a package PDF both contain the same sheet but differ slightly, which source should win?
In Rev #2, we have AE107, and then a standalone file for AE107 (and AE107.1) and I cannot tell the difference between AE107 in the package vs. the standalone file.

5. What do you expect for pages with multiple drawings/details on one sheet: reference the sheet only, or identify the specific detail/drawing area too?

Thanks,
Michael

Kevin Plash
4:28 PM (18 minutes ago)
to me

If it  is in the same cloud it can be same, as long as there is a list of items included in the specific cloud
Yes.  Separate Details
See Detail # on page xxx for scope, then have a reference of what # deliverable it is.
I would say duplicate them and let the reviewer check out both to ensure they aren’t different
If a sheet has multiple details, the each detail needs to be listed out separately.
