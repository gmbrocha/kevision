# Cleanup Audit — 2026-04-21

Snapshot of cruft, dead code, and structural decisions outstanding after the
Kevin-changelog work landed. Written immediately after pushing commits
`2de2613` (feature) and `8d95bf7` (housekeeping).

Each finding is tagged:

- **EXECUTE** — done in this audit pass.
- **PROPOSE** — recommended action; awaiting sign-off before doing it.
- **OBSERVE** — noted for awareness; no action proposed yet.

Most findings reuse the per-file disposition already drafted in
[`rebuild_plan.md`](rebuild_plan.md). This audit only adds (a) the *current*
state vs. the plan, and (b) sequencing recommendations.

---

## 1. Generated artifacts in version control — partially fixed

**EXECUTE / OBSERVE.**

The housekeeping commit added these new gitignore entries:

```
.cursor/
experiments/kevin_changelog_preview.xlsx
experiments/**/output/
*.tmp
```

That stops the bleeding for new artifacts. **35 files in `experiments/**/output/`
are still tracked** because gitignore does not retroactively untrack:

| Experiment | Tracked output files |
|---|---|
| `2026_04_cloud_detector/` | 5 overlay PNGs |
| `2026_04_cloud_detector_v2/` | 22 stage-overlay PNGs + 1 inner `.gitignore` |
| `2026_04_delta_marker_detector/` | 4 overlay PNGs |
| `2026_04_index_parser/` | 4 CSVs (the actual deliverable) |

Index-parser CSVs are arguably *not* generated cruft — they are
hand-verified output that downstream consumers (and this audit doc itself)
reference. Cloud/delta overlay PNGs are diagnostic artifacts that get
regenerated every run.

**PROPOSE:** keep index-parser CSVs tracked; `git rm --cached` the overlay
PNGs in the three detector experiments. Saves ~couple MB; doesn't lose
information that can't be regenerated. Defer until detector experiments are
archived (see finding 4).

---

## 2. Dead production code — `revision_tool/`

**PROPOSE.**

Per [`rebuild_plan.md`](rebuild_plan.md) audit, all of the following are
KILL or REWRITE candidates *and* none of them participate in the new
Kevin-changelog deliverable:

### Whole files

- [`revision_tool/verification.py`](../revision_tool/verification.py) — KILL per rebuild plan. Manual AI verification of change items. Last used pre-Kevin pivot. Still imported by `web.py` (`/changes/<id>/verify` route) and `test_app.py` (`test_verify_endpoint_with_mock_provider`).
- [`revision_tool/review.py`](../revision_tool/review.py) — KILL per rebuild plan. The `change_item_needs_attention` heuristic is for old `ChangeItem`s. Imported by `exporter.py`, `web.py`, `cli.py`, `test_app.py`.

### Templates

- [`revision_tool/templates/changes.html`](../revision_tool/templates/changes.html) — KILL per rebuild plan. Pricing-era review queue UI.
- [`revision_tool/templates/change_detail.html`](../revision_tool/templates/change_detail.html) — KILL per rebuild plan. Companion to above.
- [`revision_tool/templates/settings.html`](../revision_tool/templates/settings.html) — DEFER per rebuild plan; will become KILL once `verification.py` goes.

### Dead code inside `revision_tool/exporter.py`

The pricing-relevance machinery — ~300 lines that classify whether a change
item is "pricing-relevant" — is meaningful only for the dead pricing
deliverable, not Kevin's changelog:

- Module-level: `PLACEHOLDER_SCOPE_PATTERN`, `LABEL_ONLY_TOKENS`, `LOCATOR_TOKEN_PATTERN`, `EXTRA_PRICING_SCOPE_TOKENS`.
- Methods: `_pricing_relevance_reason`, `_is_placeholder_scope`, `_looks_like_sheet_index_title`, `_is_likely_locator_text`, `_token_is_locator_or_label`, `_contains_pricing_scope_signal`, `_extract_scope_lines`, `_build_change_summary`, `_display_sheet_title`, `_pricing_candidate_rows`, `_pricing_log_rows`, `_write_pricing_change_candidates_csv`, `_write_pricing_change_candidates_json`, `_write_pricing_change_log_csv`, `_write_pricing_change_log_json`, `_all_pricing_rows`.
- Output files: `pricing_change_candidates.{csv,json}`, `pricing_change_log.{csv,json}`, the entire `_build_summary` pricing-readiness counters, and the corresponding tiles in `templates/dashboard.html`.

**Recommended order if accepted:**

1. Delete `verification.py` + remove its routes from `web.py` + drop the verify test.
2. Delete pricing-relevance machinery in `exporter.py` + drop the 6 pricing-filter tests.
3. Delete `review.py` + replace `change_item_needs_attention` callers with a stub or per-detector confidence check.
4. Delete `changes.html` / `change_detail.html` + remove their routes + drop bulk-review tests.
5. Delete `settings.html` + simplify nav.

This collapses ~600 lines of code + ~250 lines of tests + 5 templates without
touching any code that Kevin's changelog or the index parser depends on.

---

## 3. Dead docs — `docs/`

**PROPOSE.**

- [`docs/pricing_deliverable_schema.md`](pricing_deliverable_schema.md) — KILL per rebuild plan. Stale spec from the wrong target (pricing). 180 lines.
- [`docs/pricing_deliverable_schema.sql`](pricing_deliverable_schema.sql) — KILL per rebuild plan. SQLite version of the same.
- [`docs/demo_script.md`](demo_script.md) — KEEP (frozen) per rebuild plan. Snapshot of pre-pivot state. Don't update; flag for replacement after rebuild.

`pricing_deliverable_schema.md` is partially superseded by
[`docs/kevin_changelog_format.md`](kevin_changelog_format.md), but the
"why JSON, not SQLite, yet" rationale in §2 of the pricing schema is still
useful guidance. Recommend extracting that single section into a new
`docs/storage_decision.md` before deleting.

---

## 4. Superseded experiments — `experiments/`

**PROPOSE.** *(corrected 2026-04-21 after gmbrocha pointed out the delta lineage was inverted in the original audit; chronological order is `2026_04_delta_marker_detector` → `delta_v2` → `delta_v3`, not the other way around.)*

Status check on the seven experiment folders:

| Folder | Status | Last commit | Recommendation |
|---|---|---|---|
| `2026_04_cloud_detector/` | Iter 1, plateaued; superseded by v2 per its own README | `ae67713` | Move to `experiments/archive/2026_04_cloud_detector_iter1/` |
| `2026_04_cloud_detector_v2/` | Paused at stage 3; documented next step | `6a30db5` | Keep in place; still active |
| `2026_04_delta_marker_detector/` | First Δ attempt (contour + hull + PDF-text-digit). Superseded by the v2 → v3 line, which pursued a different (denoise-first) approach | `263a541` | Move to `experiments/archive/2026_04_delta_marker_detector/` |
| `2026_04_index_parser/` | Done & verified — data spine for the Kevin changelog | `7c6ead4` | **Keep in place permanently.** This is the cheapest source for 4 of the 6 changelog columns. |
| `delta_v2/` | Tier 2 digit-anchored detection + early denoise. Fed denoise ideas into v3 | `43a1543` | Move to `experiments/archive/delta_v2/` |
| `delta_v3/` | **Active** — denoise pipeline kept (`denoise_2.png` is canonical pre-detection input); detection scripts scrapped 2026-04-21 (recursive-triangle apocalypse) | `8d95bf7` (and a follow-up scrap commit) | Keep in place. Restart detection from scratch in a future session, consuming `denoise_2.png`. |
| (root) `extract_changelog.py`, `inspect_changelog.py`, `preview_kevin_changelog.py`, `mod_5_changelog_dump/` | Active | `2de2613` | Keep |

Once the three folders move to `experiments/archive/`, also `git rm --cached`
their `output/` overlay PNGs (per finding 1).

---

## 5. Tests aligned with dead features — `tests/test_app.py`

**PROPOSE.**

Of the 19 tests in `test_app.py`, the following are tied to features
proposed for deletion in finding 2:

| Test | Tied to |
|---|---|
| `test_export_blocks_pending_attention_items` | `change_item_needs_attention` (review.py) |
| `test_pricing_outputs_filter_placeholder_revision_regions` | pricing machinery |
| `test_pricing_relevance_filter_drops_label_locator_combos` | pricing machinery |
| `test_pricing_relevance_filter_keeps_real_pricing_scope` | pricing machinery |
| `test_pricing_relevance_filter_drops_low_signal_text_without_scope_keywords` | pricing machinery |
| `test_pricing_relevance_filter_trusts_reviewer_for_approved_items` | pricing machinery |
| `test_pricing_relevance_filter_overrides_reviewer_for_placeholder_text` | pricing machinery |
| `test_cli_export_summary_is_human_readable` | pricing-readiness summary text |
| `test_dashboard_shows_pricing_readiness_panel` | pricing tiles in dashboard |
| `test_bulk_review_and_next_navigation` | dead `/changes/bulk-review` route |
| `test_verify_endpoint_with_mock_provider` | dead `/changes/<id>/verify` route |

11 of 19 tests die when finding 2 is executed. The survivors that matter
for the new pipeline:

- `test_regression_fixture_metrics` — regression baseline (will need a new fixture).
- `test_scan_generates_supersedence_and_ae113` — scanner sanity.
- `test_export_only_approved_items_when_forced` — partially survives; needs trim.
- `test_kevin_changelog_xlsx_matches_kevin_layout` — new, just landed.
- `test_web_routes_render_without_ai` — partially survives; route list will shrink.
- `test_conformed_page_lists_revised_sheets_by_default` — survives.
- `test_navbar_includes_conformed_link` — survives.
- `test_rescan_reuses_cache_and_preserves_review_state` — survives (caching pattern is keeping-quality per rebuild plan).

---

## 6. Top-level cruft

**PROPOSE.**

The repo root has 11 files. Sorted by what should live there:

| File | Status | Recommendation |
|---|---|---|
| `.gitattributes`, `.gitignore` | git plumbing | Keep |
| `README.md`, `requirements.txt` | standard project | Keep |
| `KEVIN_QUESTIONS.md` | active live doc | Keep at root or move to `docs/` |
| `mod_5_changelog.xlsx` | Kevin's source file (canonical reference) | Move to `docs/anchors/mod_5_changelog.xlsx` |
| `revision.png` | Image anchor for Kevin's email — referenced by `email_context_instructions.txt` | Move to `docs/anchors/revision.png` |
| `revision_cloud_example_2.png` | Image anchor — referenced by `KEVIN_QUESTIONS.md` row 14 | Move to `docs/anchors/revision_cloud_example_2.png` |
| `email_context_instructions.txt` | Provenance: Kevin's email content | Move to `docs/anchors/kevin_email.txt` |
| `scratch_thoughts.txt`, `scratch_thoughts_archive.txt` | Personal scratch | Keep at root for now (visibility); archive to `notes/` once stale |

If accepted, update the references in `KEVIN_QUESTIONS.md` and
`email_context_instructions.txt` accordingly.

---

## 7. Documentation rot — `docs/rebuild_plan.md`

**EXECUTE** (banner added in this audit pass; see commit 3).

The file is a 200+ line pre-rebuild planning doc dated before the index
parser and Kevin changelog landed. Without a status banner a reader can't
tell which parts are still pending vs. shipped vs. superseded.

The banner added at the top of the file is a reading guide:

- **Shipped:** index parser (extracted to `experiments/2026_04_index_parser/`, hand-verified), Kevin-shaped Excel exporter (`revision_tool/kevin_changelog.py`, tested).
- **In progress:** delta marker detector (`experiments/2026_04_delta_marker_detector/`).
- **Paused with next step:** cloud detector v2 (`experiments/2026_04_cloud_detector_v2/`, blocked on scallop repair before stage 3).
- **Pending:** the full per-file disposition pass that the rest of the doc describes.

---

## 8. Confidentiality posture — Kevin's source material

**RESOLVED 2026-04-21.** Repo is private (confirmed by gmbrocha). Kevin's
source material (`mod_5_changelog.xlsx`, `experiments/mod_5_changelog_dump/`)
stays in tree as-is. No `git rm --cached`, no history rewrite, no
visibility change needed.

---

## 9. Duplicate analysis tooling — `experiments/`

**PROPOSE.**

[`experiments/inspect_changelog.py`](../experiments/inspect_changelog.py)
(36 lines) is largely subsumed by
[`experiments/extract_changelog.py`](../experiments/extract_changelog.py)
(46 lines, plus image extraction). I wrote `inspect_changelog.py` first,
then realized I needed image extraction and wrote `extract_changelog.py`.

Recommend folding into one file with an `--inspect-only` flag, or just
deleting `inspect_changelog.py` since `extract_changelog.py`'s
`text_dump.txt` output covers the same need.

---

## Summary — what would happen if every PROPOSE is accepted

Net change to the repo:

- ~600 LOC of dead production code removed.
- ~250 LOC of dead tests removed.
- ~5 templates removed.
- 3 superseded experiment folders archived; ~31 generated PNG files untracked.
- ~180 LOC of dead docs removed (one section salvaged into `docs/storage_decision.md`).
- Top-level files reduced from 11 to 7.

Net new test count goes from 19 → ~8, but those 8 test the actual
deliverables (Kevin changelog, index parser when promoted, conformed sheet
set, scanner caching). The drop is healthy: tests for things that exist,
nothing for things that don't.

---

## Recommended order of operations for the next session

If you decide to act on any of this, this order avoids cascading test
breakage:

1. Run finding 2's deletions in the listed sub-order (each step keeps tests green by also removing the test that referenced the deleted code).
2. Then finding 5: any pricing/verify/bulk tests that survived step 1.
3. Then finding 3: dead docs.
4. Then finding 9: dedupe analysis tooling.
5. Then finding 4: archive experiments + finding 1 follow-up `git rm --cached` of overlay PNGs.
6. Then finding 6: top-level cruft to `docs/anchors/`.
7. Finally finding 8: confidentiality decision (independent of the rest).
