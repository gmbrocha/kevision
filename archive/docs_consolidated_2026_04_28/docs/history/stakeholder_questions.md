# Questions for Kevin

Status: `Current live question tracker.`

Running list of things we still need from Kevin. Add to it as new unknowns show up, and check items off as they get answered. Keep an **anchor** with each question — example revision/sheet/screenshot — so we can re-show him the exact context if he needs a refresher.

## Conventions

- **Revision set** = the package (e.g., "Revision #1 - Drawing Changes")
- **Revision** = one row from the index = one revised sheet within this set
- **Change item** = the smallest unit, the actual thing to be built/ordered/removed
- **Drawing** = an individual page (a page can hold multiple drawings via drawing-label badges)

## Guiding principle (Kevin, 4/22, paraphrased)

> "As long as we have all the information, and it's legible."

**Completeness + legibility wins; format is ours.** Use this to default any open formatting question instead of pinging him. Auto-filling a field we can't verify (e.g., guessing a contractor) violates completeness-when-correct, so prefer "leave blank for human" over "guess." Dropping any row that anchors location/context (e.g., the `Cloud Only` row when a plan-cloud encloses a detail callout) violates completeness, so prefer "emit both" over "deduplicate aggressively."

---

## Already confirmed (don't re-ask)

- [x] **Is pricing the deliverable?** — No. Pricing is a separate downstream step. The deliverable for this tool is a structured Excel of revisions and change items.
- [x] **Multiple identical clouds on the same sheet — split or combine?** — Split. Each instance is its own row, so the order list stays accurate (e.g., "we need 2 fire cabinets and 1 light", not "we need fire cabinet + light somewhere"). *(See `docs/anchors/mod_5_changelog.xlsx` caveat below: he collapses duplicate callouts inside a single detail.)*
- [x] **Stakes** — Past human errors have cost $100k+. Tool ships with mandatory human review at first; low-confidence items always get human review.
- [x] **Row granularity** — ~~Full verbosity~~ **REVISED 4/21:** see `docs/anchors/mod_5_changelog.xlsx` analysis below. He groups by cloud/detail, not by sub-item. One numbered `Scope Included` cell can hold 4+ bullets.
- [x] **Cross-sheet duplicates** — When the same change appears on multiple sheets, note every one (one row per sheet) for now. *(But see Mod-5 file: duplicates **inside the same detail** collapse with an annotation like "(note appears twice)".)*
- [x] **Header content** — Includes revision set + date + project name + contractor + architect + other relevant project metadata. (Most of these can probably be auto-extracted from the title block — confirm field list with him after first cut.)
- [x] **Real-world Excel template** — ~~There isn't one~~. **GOT IT 4/21:** `docs/anchors/mod_5_changelog.xlsx`. Three rows + three embedded screenshot crops. Schema captured in `docs/revision_changelog_format.md`.

---

## Confirmed 4/24 (stakeholder answers in `docs/history/stakeholder_answers_pt_2.md`)

- **Project conventions are consistent within a project, not universal.** Old changes are not re-clouded in the current Architect's revision sets, but a revision indicator remains near the changed area. A new project or new Architect may vary.
- **Mod/revision package grouping is manual today.** The shared file, Government letter, and modification log are the likely source of truth. Do not rely on filenames alone.
- **Duplicate sheet PDFs are safe when dates match.** If a standalone PDF and full-package sheet have the same bottom-left revision date and that date is latest, both can be trusted. If dates differ, prefer latest and flag for review.
- **Excel is the v1 review surface.** Kevin's team can work through review questions in Excel. App review can be optional later, but the workbook must carry the questions/flags.
- **Use a simple `Needs Review` flag.** Numeric confidence is useful internally, but Kevin wants a review flag because confidence does not obviously equal correctness.
- **Bias toward catching more relevant items.** Missed small changes can cost money later. Extra review is acceptable when items are relevant; random noisy catches are not.
- **Detailed workbook first.** Kevin needs to see examples before deciding whether a simpler summary is useful.
- **Workbook header is task-aware.** For Mod work, include a title such as `Modification 5` plus revision date or mod issuance date when available.
- **No custom viewer requirement for v1.** Kevin was not sure what that referred to.
- **Current workflow is mixed but shared-file centered.** Excel Modification Log, Bluebeam notes, Word/Excel/handwritten notes, quotes, Government mod letters, schedule info, ESA estimate templates, and VA forms live in the shared file.
- **Current drawing set update is more than sheet replacement.** RFI information, ESA notes, and comments from superseded sheets need to carry forward to the latest sheets.

## Confirmed 4/22 (stakeholder answers in `docs/history/stakeholder_answers_pt_1.txt`)

- **Mod ↔ Revision Set is 1:N, not 1:1.** A Mod typically has one revision set, but additional revision sets can be added under the same Mod. **Critical:** when a Mod has multiple revision sets, the *later* revision sets do **not** re-cloud the earlier revision's changes — only the Δ keynote near the detail indicates "something changed in the earlier revision here." That earlier revision still needs pricing.
  - **Pipeline implication:** cloud detection alone is insufficient at the Mod level. Need a Mod-level reconciler that walks Δ keynotes on the later revision sets' sheets and matches them to prior revision sets' changelogs to produce the unified Mod changelog.
- **Duplicate-callout collapse rules:**
  - Same note **inside the same detail** → collapse to one row, no annotation needed (the cloud already draws attention).
  - Same note in **different details on the same sheet** → separate rows (different work locations).
  - Same note across sheets that reference one master detail → use phrasing like `"See XX Detail for reference"` so it's still called out and checked.
- **Correlation ID format is free.** `<page>.<detail>` was just convenient. Don't enforce a schema; pick something readable that ties related rows together.
- **Detail-View crop size is "whatever's legible."** No target dimensions. Kevin floated a layout that puts only 2 changes per page so detail + notes stay readable — worth supporting as a "report mode" alongside the dense audit Excel.

## Confirmed from `docs/anchors/mod_5_changelog.xlsx` (Kevin's in-progress template, received 4/21)

His real format, reverse-engineered:

- **Columns:** `Correlation`, `Drawing #`, `Revision #`, `Detail #`, `Scope Included`, `Detail View` (embedded PNG), `Responsible Contractor`, `Cost?`, `Qoute Received?` *(typo — preserve verbatim).*
- **`Correlation` = stable per-sheet ID** in the form `<sheet_number_no_letters>.<sequence>` (e.g., `105.1` = first change on AD-105; `110.4` = fourth on AE-110). Decimal-sort caveat: `1.10` < `1.2` as floats, but he's using it as a label, not a sort key.
- **Detail # field uses `Cloud Only` / `N/A - Cloud Only` / `Detail <n>`** to distinguish (a) cloud sitting bare on a plan, vs. (b) cloud enclosing a detail-callout bubble, vs. (c) the detail's own contents.
- **Cloud → detail indirection:** When a plan-level cloud encloses a detail callout, he creates **two rows**: the `Cloud Only` row pointing at the detail (`"Scope Included in Detail 4 - AE-110"`) and the `Detail 4` row carrying the actual numbered scope. Our parser needs to model both anchors.
- **Sub-item grouping:** A single `Scope Included` cell can carry numbered sub-items `1)`, `2)`, `3)`, `4)` in stacked merged cells. So `pricing_changes` ↔ `pricing_change_lines` from `docs/pricing_deliverable_schema.md` is the right shape.
- **Embedded crops:** `Detail View` column holds a cropped PNG screenshot of the cloud area, sized to span ~14 rows. Our existing cloud-mask crops should drop straight in. (The fallback idea in `scratch_thoughts.txt` is now the **primary** visual deliverable.)
- **Three downstream-empty columns** he leaves for the pricing pass: `Responsible Contractor`, `Cost?`, `Qoute Received?`. We generate them empty.
- **Symbology cross-check (his own annotations in column G):**
  - `"Triangle with #1 indicates Revision #"`
  - `"Circular Symbol with drawing # and #4 above indicates the detail below is looking at that wall"`
  - Confirms Δ-marker = revision number; detail callouts are circles with `detail# / sheet#`.

---

## Highest-priority asks

- [x] **Transcript + audio** — Already being sent; no follow-up needed unless the handoff stalls.
- [ ] **What he wants as the deliverable, in his own words** — Useful as a sanity-check summary, but no longer a blocker if the workbook/output shape is already clear from the latest call.
- [x] **The in-progress Excel he started** — **GOT IT 4/21:** `docs/anchors/mod_5_changelog.xlsx`. See the section above.

## Open from `docs/anchors/mod_5_changelog.xlsx` (still need answers)

- [x] ~~**What is "Mod 5"?**~~ — answered 4/22, see Confirmed section. Mod = N revision sets (typically 1).
- [x] ~~**Sub-item rollup rule**~~ — verbal answer 4/22: "doesn't really matter." Implementation freedom. **Default:** one row per cloud, bullets stacked in `Scope Included` (matches what he did in `mod_5_changelog.xlsx` for AE-110). Dedup rule still runs *inside* that single row's bullet list.
- [x] ~~**Duplicate-callout collapse**~~ — answered 4/22, see Confirmed section.
- [x] ~~**Correlation ID**~~ — answered 4/22 ("doesn't matter, just legible/convenient").
- [x] ~~**Detail-View crop dimensions**~~ — answered 4/22 ("doesn't matter, legibility is the bar"). New ask raised: support a "report mode" with ~2 changes per page for max legibility.
- [x] ~~**Two-row pattern for cloud → detail**~~ — closed by the completeness principle 4/22. **Default:** always emit both rows when a plan-level cloud encloses a detail callout. Dropping the `Cloud Only` row loses the plan-level anchor.
- [x] ~~**Empty downstream columns**~~ — closed by the completeness principle 4/22. **Default:** leave `Responsible Contractor`, `Cost?`, `Qoute Received?` blank. Pricing team fills.

## New questions raised by Kevin's 4/22 answers

- [x] ~~**Mod-level Δ-keynote reconciliation**~~ — answered 4/24. In this Architect's current sets, old changes are not re-clouded but a revision indicator remains near the changed area. Same-project conventions are usually consistent; new Architect/new project may vary.
- [x] ~~**Mod artifact**~~ — answered 4/24. Shared file, Government letter, and modification log are the likely grouping source; files may still arrive separately. Support manual grouping/confirmation.
- [x] ~~**"See XX Detail for reference" phrasing**~~ — closed by the legibility principle 4/22. Use his literal phrase as the default template string; it's clear and they're his words.

## Excel deliverable shape (still open)

- [ ] **Order/build view** — Kevin needs to see examples before deciding whether a simpler summary is useful. Default for demo: detailed workbook first; optional simple summary tab/example if cheap.
- [x] ~~**Hand-off format for low-confidence items**~~ — answered 4/24. Excel is the safe review surface. Use inline `Needs Review` / `Review Reason` columns.
- [ ] **Header field list** — partially answered 4/24. Header depends on task. For Mod work, include `Modification 5` style title plus revision date / mod issuance date when available. Confirm final exact field list after first example.

## RFI handling (backlog feature — see `docs/backlog.md`)

Two future sub-features are still possible here: (1) auto-clouding RFI context areas when the architect did not draw one, and (2) documenting RFIs that have no drawing changes at all. These are backlog questions, not current blockers.

- [ ] **Real RFI examples** — could he send a few representative RFI PDFs? Mix of "produced drawing changes" vs. "pure Q&A clarification"?
- [ ] **Anchor mechanism** — how does an RFI reference its drawing today? Text reference (`"see AE-110 detail 4"`), drawn marker on the sheet, RFI number embedded somewhere in the drawing, or all of the above?
- [ ] **Ownership** — who issues the RFI (sub-contractor → architect)? Who archives the response? Where does the answered RFI live in his workflow today (folder, email thread, custom system)?
- [ ] **Volume** — how many RFIs typically per project? Per Mod? Helps decide whether RFI handling is a side-feature or a peer to the revision-set pipeline.

## Workflow

- [x] ~~**First action when a revision package lands**~~ — answered 4/24. Ideally Owner sends a Scope of Work letter showing changed plans. Kevin reviews changed plans, sends to subs, refines exact scope, determines affected subs, and follows up.
- [x] ~~**What's the custom viewer he was using?**~~ — answered 4/24. Kevin was not sure what this referred to. No v1 integration requirement.
- [ ] **Iteration order** — Sheet-by-sheet down the index? By trade (architectural first, then mechanical)? Multiple revision sets at once or one at a time?
- [x] ~~**Today's manual capture mechanism**~~ — answered 4/24. Mixed workflow: Excel Modification Log, Bluebeam notes, Word/Excel/handwritten tracking, shared file with quotes, Gov mod letter, schedule info, ESA/VA templates.
- [x] ~~**Build-plan / working-set update**~~ — answered 4/24. More than swapping sheets: RFI information, ESA notes, and comments from superseded pages must carry forward to latest sheets.
- [ ] **Standalone single-sheet PDFs in a revision-set folder** — Rev 2's folder contains both the main 29-page package AND two standalone single-sheet PDFs (`Drawing Rev2- Steel Grab Bars AE107.pdf` and `Drawing Rev2- Steel Grab Bars R1 AE107.1.pdf`). Both sheets are also pages 5 and 6 of the main PDF.
  - What does the `R1` in the second filename mean? Hypotheses: (A) just a versioning artifact, (B) "Revision 1 of (Rev 2's) AE107.1" — a micro-revision issued *after* the main package went out, superseding the main PDF's page 6, (C) something else.
  - The user noticed the standalone `R1 AE107.1.pdf` clouds a slightly *larger area* than the main PDF's AE107.1 (one or two more grab bars inside the cloud), suggesting (B) — the standalone supersedes the main package's copy for that one sheet.
  - If true, our parser must use the standalone PDF for AE107.1 cloud-content extraction, not the main package's page 6. Confirm the rule.
  - General: when both a standalone single-sheet PDF AND the main package contain the same sheet, which is the source of truth? Always the standalone (later)? Sometimes? Depends on filename markers like `R1`?
- [ ] **Other pain points we haven't touched** — Architect clarifications, sub coordination, RFIs, allowances, anything else eating his day?

## Specific revision items we need help interpreting

- [ ] **Row 14 / SF110 / 4TH FLOOR FRAMING PLAN** — Black-filled square inside the cloud, in a wall. No legend match found. Steel column? Beam end? Something else?
  - Anchor: `docs/anchors/revision_cloud_example_2.png` and screenshots from the 4/14 conversation.
- [ ] *(add more rows here as we walk through them with him)*

## Edge cases / structural questions

- [ ] **Cloud contains only a leader, no symbol/text** — Just an arrow pointing at a wall or feature. How does he describe that change item in his Excel today?
- [ ] **Cloud contents are textual** — A dimension being changed (`16'-4"` → `16'-8"`), a note being added/edited. Each text edit its own change item? Same row format as symbol-based items?
- [ ] **Multiple drawings on one page** — AD104 carried both the 4th- and 5th-floor demo plans. Does he reference both drawings as separate locations, or just cite the sheet ID once?
- [ ] **Index title vs. drawing title** — Index says "ANALYSIS", drawing title block says "PLAN". Plan is to capture both verbatim, no reconciliation. Confirm that's right?
- [ ] **Index has a cloud on its own row (recursive case)** — Index page is technically a sheet that got revised. Should it appear as its own revision row with change items (the index rows that were added/changed in this revision), or do we treat the index specially?
- [ ] **Symbol that overlaps a cloud but isn't inside it** — The AD202 cross-reference arrow grazed the AD104 cloud. We're planning to use centroid-containment in the cloud polygon (not bounding-box overlap) to decide what's "in" the cloud. Confirm that matches his mental model.

## Confidence / quality bar

- [x] ~~**Acceptable miss rate**~~ — answered 4/24 directionally. Catch more relevant information because misses can cost large amounts later; avoid random noise that increases review time.
- [x] ~~**Confidence display**~~ — answered 4/24. Use `Needs Review`, not numeric confidence, in the user-facing workbook.
- [x] ~~**What "human review" looks like in his world**~~ — answered 4/24. Excel is the safe v1 review surface; app review can be optional/future.

## Notes / observations to verify with him

- [x] **Pricing module is dead** — Closed. Pricing is downstream; this tool's deliverable is the structured revision workbook.
- [ ] **Δ-marker + X-column + cloud** — These three signals should agree on "this row is in this revision". Disagreement = flag. Confirm he expects these to always agree in practice (otherwise we calibrate the flag threshold).
