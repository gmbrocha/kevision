# Questions for Kevin

Running list of things we need from Kevin (the buddy / target user). Add as we discover them; check off as he answers. Keep an **anchor** with each question — example revision/sheet/screenshot — so we can re-show him the exact context if he needs a refresher.

## Conventions

- **Revision set** = the package (e.g., "Revision #1 - Drawing Changes")
- **Revision** = one row from the index = one revised sheet within this set
- **Change item** = the smallest unit, the actual thing to be built/ordered/removed
- **Drawing** = an individual page (a page can hold multiple drawings via drawing-label badges)

---

## Already confirmed (don't re-ask)

- [x] **Is pricing the deliverable?** — No. Pricing is a separate downstream step. The deliverable for this tool is a structured Excel of revisions and change items.
- [x] **Multiple identical clouds on the same sheet — split or combine?** — Split. Each instance is its own row, so the order list stays accurate (e.g., "we need 2 fire cabinets and 1 light", not "we need fire cabinet + light somewhere"). *(See `mod_5_changelog.xlsx` caveat below: he collapses duplicate callouts inside a single detail.)*
- [x] **Stakes** — Past human errors have cost $100k+. Tool ships with mandatory human review at first; low-confidence items always get human review.
- [x] **Row granularity** — ~~Full verbosity~~ **REVISED 4/21:** see `mod_5_changelog.xlsx` analysis below. He groups by cloud/detail, not by sub-item. One numbered `Scope Included` cell can hold 4+ bullets.
- [x] **Cross-sheet duplicates** — When the same change appears on multiple sheets, note every one (one row per sheet) for now. *(But see Mod-5 file: duplicates **inside the same detail** collapse with an annotation like "(note appears twice)".)*
- [x] **Header content** — Includes revision set + date + project name + contractor + architect + other relevant project metadata. (Most of these can probably be auto-extracted from the title block — confirm field list with him after first cut.)
- [x] **Real-world Excel template** — ~~There isn't one~~. **GOT IT 4/21:** `mod_5_changelog.xlsx`. Three rows + three embedded screenshot crops. Schema captured in `docs/kevin_changelog_format.md`.

---

## Confirmed from `mod_5_changelog.xlsx` (Kevin's in-progress template, received 4/21)

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

- [ ] **Transcript + audio** — He's already sending these.
- [ ] **What he wants as the deliverable, in his own words** — He's sending this too.
- [x] **The in-progress Excel he started** — **GOT IT 4/21:** `mod_5_changelog.xlsx`. See "Confirmed from mod_5_changelog.xlsx" section above.

## New questions raised by `mod_5_changelog.xlsx`

- [ ] **What is "Mod 5"?** Filename is `mod_5_changelog`. Hypothesis: Modification 5 / change order #5 — a wrapper above revision sets that bundles the priced changes for one owner-facing modification. Confirm. Does each Mod map to N revision sets, or N:N?
- [ ] **Sub-item rollup rule** — He puts 4 numbered sub-items in one row when they're in the same detail. Rule: "one row per cloud (or per detail when the cloud is on a plan and references a detail), bullets stacked inside `Scope Included`"? Or did he just do it that way for AE-110 because the detail had a tight legend? Affects `pricing_change_lines` granularity.
- [ ] **Duplicate-callout collapse** — Row 36 says `"(note appears twice)"`. So duplicates *inside the same detail* collapse. What about duplicates across multiple details on the same sheet? Across sheets?
- [ ] **Correlation ID** — Confirm the format `<sheet#>.<seq>` and that ordering is just "order he encountered them" (not "order on the sheet by location"). Are these stable across re-issues, or do they renumber if Rev 2 inserts a new change?
- [ ] **Detail-View crop dimensions** — He sized each embedded image to span ~14 rows × 2 cols. Is there a target pixel size / aspect ratio he wants, or is "fits the cell" good enough?
- [ ] **Two-row pattern for cloud → detail** — Confirm the convention: when a cloud on a plan encloses a detail callout, generate one `Cloud Only` row (anchoring to the plan) AND one `Detail N` row (carrying the scope). Or does he sometimes want just the detail row?
- [ ] **The empty downstream columns** — `Responsible Contractor`, `Cost?`, `Qoute Received?` — confirm we leave these blank for him / pricing team to fill, vs. trying to auto-suggest a contractor based on trade keywords in the scope.

## Excel deliverable shape (still open)

- [ ] **Order/build view** — Does he produce a separate rolled-up "what to order" view from the audit list, or is the audit list itself what people order from? (Verbose audit + optional rolled-up sheet is our current plan; confirm.)
- [ ] **Hand-off format for low-confidence items** — Same Excel with a "REVIEW" flag column, or a separate companion file?
- [ ] **Header field list** — Once we auto-extract from title blocks, confirm: project name, project number, architect, contractor, his name (manual), revision set, revision date — anything else? Anything to leave out?

## Workflow

- [ ] **First action when a revision package lands** — Bluebeam? Acrobat? File Explorer? Email attachment? Custom viewer (he mentioned one)?
- [ ] **What's the custom viewer he was using?** — Briefly mentioned during the call. Any chance the tool needs to integrate / export to it?
- [ ] **Iteration order** — Sheet-by-sheet down the index? By trade (architectural first, then mechanical)? Multiple revision sets at once or one at a time?
- [ ] **Today's manual capture mechanism** — Sticky notes? Bluebeam comments? Direct typing into Excel? Print-and-mark?
- [ ] **Build-plan / working-set update** — He also updates the current build plan drawings. Working assumption: it's just marking old sheets superseded and dropping the new ones in (essentially what our existing conformed-set output already does). Confirm — anything more involved (re-titling, re-numbering, manual annotation, separate file format)?
- [ ] **Standalone single-sheet PDFs in a revision-set folder** — Rev 2's folder contains both the main 29-page package AND two standalone single-sheet PDFs (`Drawing Rev2- Steel Grab Bars AE107.pdf` and `Drawing Rev2- Steel Grab Bars R1 AE107.1.pdf`). Both sheets are also pages 5 and 6 of the main PDF.
  - What does the `R1` in the second filename mean? Hypotheses: (A) just a versioning artifact, (B) "Revision 1 of (Rev 2's) AE107.1" — a micro-revision issued *after* the main package went out, superseding the main PDF's page 6, (C) something else.
  - The user noticed the standalone `R1 AE107.1.pdf` clouds a slightly *larger area* than the main PDF's AE107.1 (one or two more grab bars inside the cloud), suggesting (B) — the standalone supersedes the main package's copy for that one sheet.
  - If true, our parser must use the standalone PDF for AE107.1 cloud-content extraction, not the main package's page 6. Confirm the rule.
  - General: when both a standalone single-sheet PDF AND the main package contain the same sheet, which is the source of truth? Always the standalone (later)? Sometimes? Depends on filename markers like `R1`?
- [ ] **Other pain points we haven't touched** — Architect clarifications, sub coordination, RFIs, allowances, anything else eating his day?

## Specific revision items we need help interpreting

- [ ] **Row 14 / SF110 / 4TH FLOOR FRAMING PLAN** — Black-filled square inside the cloud, in a wall. No legend match found. Steel column? Beam end? Something else?
  - Anchor: `revision_cloud_example_2.png` and screenshots from the 4/14 conversation.
- [ ] *(add more rows here as we walk through them with him)*

## Edge cases / structural questions

- [ ] **Cloud contains only a leader, no symbol/text** — Just an arrow pointing at a wall or feature. How does he describe that change item in his Excel today?
- [ ] **Cloud contents are textual** — A dimension being changed (`16'-4"` → `16'-8"`), a note being added/edited. Each text edit its own change item? Same row format as symbol-based items?
- [ ] **Multiple drawings on one page** — AD104 carried both the 4th- and 5th-floor demo plans. Does he reference both drawings as separate locations, or just cite the sheet ID once?
- [ ] **Index title vs. drawing title** — Index says "ANALYSIS", drawing title block says "PLAN". Plan is to capture both verbatim, no reconciliation. Confirm that's right?
- [ ] **Index has a cloud on its own row (recursive case)** — Index page is technically a sheet that got revised. Should it appear as its own revision row with change items (the index rows that were added/changed in this revision), or do we treat the index specially?
- [ ] **Symbol that overlaps a cloud but isn't inside it** — The AD202 cross-reference arrow grazed the AD104 cloud. We're planning to use centroid-containment in the cloud polygon (not bounding-box overlap) to decide what's "in" the cloud. Confirm that matches his mental model.

## Confidence / quality bar

- [ ] **Acceptable miss rate** — Tolerance for missed changes vs. over-flagging items for review? Helps calibrate the "needs review" threshold.
- [ ] **Confidence display** — Does he want to see numeric confidence per change item, or just a binary "auto / review me" flag?
- [ ] **What "human review" looks like in his world** — The Excel arrives with N items flagged. Does he want them inline (highlighted rows in the audit Excel), or in a side queue (a GUI, like the one we already have)?

## Notes / observations to verify with him

- [ ] **Pricing module is dead** — He's confirmed pricing isn't part of this scope. Sanity-check we're not throwing out anything he secretly wanted.
- [ ] **Δ-marker + X-column + cloud** — These three signals should agree on "this row is in this revision". Disagreement = flag. Confirm he expects these to always agree in practice (otherwise we calibrate the flag threshold).
