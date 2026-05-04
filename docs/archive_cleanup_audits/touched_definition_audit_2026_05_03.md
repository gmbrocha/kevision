# Touched-Page Definition Audit - 2026-05-03

Status: report-only audit. No code, labels, manifests, datasets, model files,
eval files, or existing docs were modified. This file is the only intended
deliverable.

Scope: explain exactly what "touched" currently means in the page/source
registry, why only ~12-17 of ~115 eligible standard drawing pages survive as
non-touched, and whether all touch types should be treated equally for eval
selection, training expansion, hard-negative mining, manual full-page review,
and synthetic background use.

## Executive Summary

The current touched-page policy is correct as a **strict pristine-holdout
filter**, but it is **overly conservative for every other use case** because it
treats four very different signals as equivalent "touched":

1. crops that went into model training,
2. crops that went into source-controlled train/val,
3. crops that were quasi-held-out from training,
4. pages that appeared in an older debug full-page eval sample.

A page is currently marked "touched" if any one row in any of four legacy
manifests references it. That row may be a single random standard-drawing crop
that GPT-tagged at high confidence, a single marker-neighborhood hard-negative
crop, or a single page-metadata row in an older debug eval list. None of these
imply that the **full page** was ever reviewed for revision clouds, so the
current "touched" set systematically over-excludes pages that may still contain
undiscovered natural clouds and that would be perfectly safe for hard-negative
mining, training expansion, or future eval growth.

Top driver of the small non-touched pool: the consolidated training manifest
`reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`
(`continuity_training` role, 931 rows) touches every single one of the 98
"touched eligible" pages. The strict pool is exhausted because this single
manifest is treated as a page-level kill switch.

The recommended refined policy splits "touched" into separate per-use-case
exclusion rules. Strict pristine holdout keeps the current behavior. Practical
`page_disjoint_real` eval may keep it too. Hard-negative mining, training
expansion, manual full-page review, and synthetic background use should use
narrower exclusion sets driven by **what was actually trained on at the
crop/page level**, not by "did any row anywhere mention this page."

## Files Inspected

- `AGENTS.md`
- `docs/CURRENT_STATE.md`
- `docs/NEXT_ACTIONS.md`
- `CloudHammer_v2/README.md`
- `CloudHammer_v2/PIVOT_PLAN.md`
- `CloudHammer_v2/docs/CURRENT_STATE.md`
- `CloudHammer_v2/docs/EVAL_POLICY.md`
- `CloudHammer_v2/scripts/build_touched_page_registry.py`
- `CloudHammer_v2/outputs/touched_page_registry_20260502/touched_page_registry.jsonl`
- `CloudHammer_v2/outputs/touched_page_registry_20260502/touched_page_registry_summary.md`
- `CloudHammer_v2/outputs/touched_page_registry_20260502/touched_page_registry_summary.json`
- `CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/README.md`
- `CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/selection_summary.json`
- `CloudHammer/data/manifests/pages.jsonl` (sampled)
- `CloudHammer/data/manifests/pages_standard_drawings_no_index_20260427.jsonl` (sampled)
- `CloudHammer/data/manifests/reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`
  (full schema scan)
- `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.jsonl`
  (full schema scan)
- `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.quasi_holdout.jsonl`
  (full schema scan)
- `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.summary.json`
- `CloudHammer/data/manifests/fullpage_eval_sample_broad_deduped_20260428.jsonl`
  (full schema scan)
- Directory listing of `CloudHammer/data/manifests/` for non-included manifests
- `docs/archive_cleanup_audits/roi_candidate_selection_audit_2026_05_03.md`
  (for prior context)

## Checks Run

- Read all required orientation docs before any analysis (per AGENTS.md).
- Loaded `touched_page_registry.jsonl` (`332` rows) and the four touched
  manifests; counted role distributions, role-set distributions, touch totals,
  and per-revision breakdowns.
- Verified the touched-page summary numbers against the registry rows
  (`98` touched eligible standard-drawing pages, `17` non-touched eligible).
- Inspected schema fields and value distributions in each touched manifest to
  classify each row by what it actually represents (crop vs page vs label
  status).
- Listed all manifests under `CloudHammer/data/manifests/` to identify legacy
  manifests that the registry does **not** currently consider as touch
  sources.
- No code, labels, manifests, datasets, model files, or eval files were
  modified.
- This audit creates only this report file.

## 1. Where Is "Touched" Defined?

There is one canonical implementation, plus one downstream consumer.

### 1.1 Canonical Definition

`CloudHammer_v2/scripts/build_touched_page_registry.py`

Key entry points:

- `DEFAULT_TOUCHED_MANIFESTS` (lines 20-28): hardcoded list of four manifest
  paths under legacy `CloudHammer/data/manifests/`.
- `role_for_manifest(path)` (lines 177-187): hardcoded mapping from manifest
  filename substring to a touch-role label (`quasi_holdout`,
  `source_controlled_train_val`, `debug_eval`, `continuity_training`, else
  filename stem).
- `build_touch_index(paths)` (lines 190-201): for every row in every touched
  manifest, derive a `source_page_key` (e.g. `Revision_1_-_Drawing_Changes:p0003`)
  via `source_page_key_for_row` and increment a `Counter[role]` per page.
- `page_registry_row(...)` (lines 204-242): adds the `freeze_guard_reasons`
  list. The relevant guard is hardcoded as a single boolean check:

  ```python
  if key and touches.get(key):
      guards.append("already_touched_by_training_or_eval")
  ```

  i.e. **any** non-zero touch count from **any** of the four manifests marks
  the page as touched.
- `eligible_for_page_disjoint_real` is `True` only if `freeze_guard_reasons`
  is empty.

There is no per-role weighting, no per-row-type filtering, and no signal-type
classification. The script does not look at the row's `has_cloud`, `split`,
`training_source`, `candidate_source`, `review_bucket`, `is_excluded`, or
`reason_for_selection` fields.

### 1.2 Downstream Consumer

The style-balance diagnostic queue
(`CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/`)
reads the registry's `touched` boolean and the per-page `touch_roles` counter
to select **low-touch touched pages** for diagnostic-only review. It does not
redefine "touched"; it inverts the filter and uses raw role-counts as a
proxy for "lightly used" vs "heavily used" pages.

### 1.3 Where "Touched" Is Used For Decisions

- `page_disjoint_real` selection: only pages where
  `eligible_for_page_disjoint_real == True` enter the candidate pool. With no
  argument override, all 17 untouched eligible pages were frozen.
- `style_balance_diagnostic_real_touched_20260503`: explicitly opted into
  touched-real pages, prioritizing low touch-totals.
- Documented in `CloudHammer_v2/docs/EVAL_POLICY.md` and
  `CloudHammer_v2/docs/CURRENT_STATE.md` as the "strict registry" that
  exhausted the page-disjoint pool.

### 1.4 Configs / Hardcoded Logic

- The four touched-manifest paths are hardcoded in
  `DEFAULT_TOUCHED_MANIFESTS`. The CLI `--touched-manifest` flag overrides them
  but was not used in the recorded run.
- The role mapping in `role_for_manifest` is hardcoded by filename substring.
- The eligible-page filter is the static manifest
  `pages_standard_drawings_no_index_20260427.jsonl`. Pages outside that list
  are flagged `not_eligible_standard_drawing`, which is a separate guard from
  "touched."

There is no separate "touched" config file, no JSON/YAML policy, and no
manifest-level metadata declaring "this row counts as a training touch versus
a candidate-only touch." The role label is derived purely from the manifest
filename.

## 2. What Sources Mark A Page As Touched?

There are exactly four sources today.

### 2.1 `continuity_training`

- Path: `CloudHammer/data/manifests/reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`
- Rows: `931`
- Page-matching: by parsing `roi_image_path` /`cloud_roi_id` filename for
  `_p\d{4}` and using the source-id slug. Crop-level rows; the script collapses
  them to `source_page_key`.
- Granularity: **crop-level**.
- What it actually represents: the consolidated training+val crop manifest,
  combining (per `source_batch` field):
  - `batch_001_priority_train`: 204 priority training crops
  - `batch_002_thin_faint`: 95 thin/faint training crops
  - `batch_004_hard_negatives`: 424 marker-neighborhood hard-negative crops
    (`reason_for_selection = marker_neighborhood_negative_no_cloud`)
  - `broad_gpt_20260427_deduped`: 170 GPT-deduped review-queue crops
  - `marker_fp_hard_negatives_20260502`: 29 marker false-positive hard
    negatives
  - `eval_symbol_text_fp_hard_negatives_20260502`: 9 symbol/text false-positive
    hard negatives
- Manual-review status: rows have a `label_path` under `cloud_labels_reviewed/`,
  so the **crop** was human-reviewed. The **full page** was not reviewed by
  these rows; they only saw the crop window.
- 639/931 (`has_cloud = true`); 292/931 (`has_cloud = false`).
- All 931 rows are `is_excluded = false`.
- Touches all 98 "touched eligible" pages (every touched page has at least
  this role).

### 2.2 `source_controlled_train_val`

- Path: `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.jsonl`
- Rows: `502`
- Granularity: **crop-level**, derived from the same crops as
  `continuity_training` after applying source-disjoint splitting and
  per-source caps (max 150 rows/source, 15 rows/source-page; `dropped_by_source_caps = 399`).
- What it actually represents: the **active** training+val split under the
  source-controlled policy (`source_disjoint_v1`). Splits: `train=397`, `val=105`.
- Manual-review status: same as `continuity_training` (the rows are a subset
  of those reviewed crops).
- Touches 81 of 98 touched eligible pages (all `continuity_training` overlap
  except where source caps dropped the page entirely).

### 2.3 `quasi_holdout`

- Path: `CloudHammer/data/manifests/source_controlled_small_corpus_20260502.quasi_holdout.jsonl`
- Rows: `30`
- Granularity: **crop-level**, drawn from the broad GPT review queue and a
  small symbol/text FP set.
- What it actually represents: a deferred-evaluation crop pool that was
  **deliberately excluded from training** in the source-disjoint split. By
  design, these crops were sampled and labeled but the model never trained on
  them.
- Manual-review status: crops have labels in
  `review_queues/.../labels/`. Full-page never reviewed.
- Touches 7 of 98 touched eligible pages.

### 2.4 `debug_eval`

- Path: `CloudHammer/data/manifests/fullpage_eval_sample_broad_deduped_20260428.jsonl`
- Rows: `14`
- Granularity: **page-level**. Each row is a page metadata record
  (`pdf_path`, `render_path`, `sheet_id`, `sheet_title`, page geometry).
- What it actually represents: an older full-page debug eval sample. There is
  no label data in this manifest. Whether the pages were ever fully labeled
  for cloud truth is not encoded in the row schema; the file is a list of
  page identifiers used in a previous full-page eval pass.
- Manual-review status: **unverified at the row schema level**. The manifest
  carries no label paths or label-status field. Practical assumption: these
  pages received some human eyes during prior debug eval, but the depth of
  that review is not recorded.
- Touches 14 of 98 touched eligible pages.

### 2.5 What Is **Not** Currently Counted As Touched

Per `CloudHammer/data/manifests/`, the following manifests exist but are **not**
in `DEFAULT_TOUCHED_MANIFESTS`:

- `eval_symbol_text_fp_hard_negatives_20260502.jsonl`
- `reviewed_plus_marker_fp_hard_negatives_20260502.jsonl`
- `marker_fp_hard_negatives_20260502.jsonl`
- `large_cloud_context_revision1_pages_20260428.jsonl`
- `large_cloud_context_stress_pages_20260428.jsonl`
- `reviewed_batch_001_002_004partial_plus_broad_deduped_20260428.jsonl`
- `cloud_roi_broad_allmarkers_20260427.jsonl`
- `cloud_roi_broad_candidates_20260427.jsonl`
- `roi_manifest_resolved_20260427.jsonl`
- `reviewed_batch_001_002_plus_004partial_current_20260427.jsonl`
- `reviewed_batch_001_002_plus_004partial.jsonl`
- `reviewed_batch_004_hard_negatives_partial_001_325.jsonl`
- `reviewed_batch_001_plus_002.jsonl`
- `reviewed_batch_001_priority_train.jsonl`
- `cloud_roi_manifest.jsonl`
- `roi_manifest.jsonl`
- `delta_manifest.jsonl`
- `smoke_blueprint_pages.jsonl`
- `smoke_pages.jsonl`

Most of these are believed to be **superseded** by the consolidated
`reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`
manifest, in which case ignoring them is correct. However, this is **not
verified** by the registry script. If any older manifest references a page
that did **not** survive into the current consolidated manifest (e.g. dropped
during dedup), that page is silently classified as untouched today.

Also not counted:

- `CloudHammer/data/api_cloud_labels_unreviewed/` (the GPT-labeled, not-yet-
  reviewed text label files seen in the working tree). These represent newer
  GPT crop labels that have not yet been folded into a manifest. They probably
  do not change page-level touch state because they are crop labels, but they
  would qualify as `gpt_labeled` if/when a registry refresh enumerates them.
- `CloudHammer_v2/data/gpt55_crop_prelabels_small_corpus_supplement_20260502/review_manifest.gpt_provisional.jsonl`
  (provisional GPT-5.5 crop prelabels). Same situation.
- `CloudHammer_v2/eval/page_disjoint_real_human_review/` (the new full-page
  eval truth, intentionally **kept out** of the touch list because those pages
  are eval-frozen by other policy, not by training).

## 3. Touch-Type Classification

Mapping current `touch_roles` plus row-level fields to the categories
specified in the prompt:

| Current touch role | Best-fit categories | Granularity | Manually reviewed full page? |
| --- | --- | --- | --- |
| `continuity_training` (general row) | `training_used` (if `split=train`), `validation_used` (if `split=val`), plus `manual_reviewed_crop` | crop | No |
| `continuity_training` row with `source_batch=batch_004_hard_negatives` or `marker_fp_hard_negatives_20260502` or `eval_symbol_text_fp_hard_negatives_20260502` | `hard_negative_mined` + `manual_reviewed_crop` + `training_used`/`validation_used` | crop | No |
| `continuity_training` row with `training_source=review_queue` | `gpt_labeled` (initial pass) + `manual_reviewed_crop` + `training_used`/`validation_used` | crop | No |
| `source_controlled_train_val` row | `training_used` (if `source_control_split=train`), `validation_used` (if `source_control_split=val`); same crop-level review status | crop | No |
| `quasi_holdout` row | `candidate_manifest_only` + `manual_reviewed_crop`; explicitly **not** `training_used` and **not** `validation_used` (held out from training) | crop | No |
| `debug_eval` row | `eval_used` (older debug eval), with **unknown** full-page review depth | page metadata | Unverified |

Categories not currently emitted by the registry but present in the
underlying data:

- `manual_reviewed_full_page`: would apply to the new
  `page_disjoint_real_human_review` set, which is intentionally excluded from
  the touch sources.
- `model_inferred`: e.g. YOLO tiled prediction artifacts. Not in the touch
  sources today.
- `crop_generated`: many `random_standard_drawing_crop` and
  `target_marker_neighborhood` rows are essentially "this crop was generated
  and pushed into a queue." Currently bundled under the same role as the
  reviewed/used outcome.
- `export_processed`, `debug_artifact_only`: not represented; the legacy
  pipeline's release/export artifacts are not in any touched manifest.
- `source_family_touched`: not represented; the registry is page-level, not
  source-family-level. This matters because pages from the same source PDF
  are often visually related, so a clean page-disjoint holdout can still
  leak source style if the rest of that source is heavily trained.
- `unknown`: the registry counted `0` rows whose page key could not be
  resolved (`unknown_touch_rows: 0`).

Important: in the current registry, **all four roles are treated as a single
binary "touched"**. The role labels survive in `touch_roles`, but the
freeze guard logic does not differentiate between them.

## 4. Why So Few Pages Are Considered Non-Touched

Numbers from the dry run summary:

- Registry pages total: `332`
- Eligible standard drawing pages: `115`
- Touched eligible pages: `98`
- Page-disjoint candidates: `17`
- Frozen `page_disjoint_real`: `17`

Per-revision view of the eligible pool:

| Revision | Eligible | Touched | Untouched |
| --- | ---: | ---: | ---: |
| Revision #1 - Drawing Changes | 49 | 42 | 7 |
| Revision #2 - Mod 5 grab bar supports | 27 | 20 | 7 |
| Revision #3 - EHRM Drawings | 26 | 24 | 2 |
| Revision #5 - RFI 126 - Concrete Repairs | 6 | 5 | 1 |
| Revision #4 - Dental Air | 5 | 5 | 0 |
| Revision #7 - RFI 141 - Deteriorated Attic Wood | 2 | 2 | 0 |

Top reasons for the small non-touched pool, in descending impact:

1. **`continuity_training` is dominant and page-level binary.** All 98 touched
   eligible pages are touched by `continuity_training`. A single crop in the
   931-row consolidated training manifest is enough to disqualify a page.
2. **Heavy training reuse on a few pages, but broad page coverage.** Eight
   pages have 30+ touch rows (top: `Revision_1_-_Drawing_Changes:p0017` with
   `67` rows; `:p0029` with `59`; `:p0007` with `54`). These are clearly
   "trained on" and should be excluded from eval. But the same manifest also
   marks many pages as touched with only 2-3 rows total (e.g.
   `260313_-_VA_Biloxi_Rev_3:p0175..p0196` are each touched by exactly one
   `continuity_training` + one `source_controlled_train_val` row, total 2).
   These "lightly touched" pages are being treated identically to the heavily
   trained pages.
3. **Hard-negative crops count the same as positive training crops.** 424 of
   the 931 `continuity_training` rows are `marker_neighborhood_negative_no_cloud`
   hard negatives. Seeing one no-cloud crop window from a page does not
   meaningfully bias YOLO toward "knowing" the rest of that page, but it
   currently disqualifies it from eval freezing the same way a full positive
   training crop would.
4. **Quasi-holdout disqualifies pages from `page_disjoint_real` even though
   the model never trained on them.** 7 pages were touched by
   `quasi_holdout`. Those crops are deliberately held out from training, so
   the page is **not** training-contaminated; yet it is excluded from the
   page-disjoint pool by the same guard.
5. **`debug_eval` 14-page page-metadata-only manifest disqualifies 14
   eligible pages on the basis of being mentioned in an older eval sample,
   regardless of whether labels were ever produced.**
6. **No source-family or per-row weighting.** The script does not consider
   that a page might appear once in a hard-negative manifest and never as
   training truth, nor that a `random_standard_drawing_crop` may be unrelated
   to revision-cloud bias.

The style-balance diagnostic set was specifically built around items 2 and 3
above by selecting low-touch touched pages (`touch_total` 2-6). Per its
selection summary, the chosen `12` pages are exactly the kind of "touched but
likely safe" pages this audit is identifying.

## 5. Per-Use-Case Assessment Of The Current Touched Policy

For each touch type currently in the registry, this is whether it should
exclude a page from each downstream use. "Yes" = current policy is correct.
"Conservative" = current policy is too strict for that use. "Depends" =
needs row-level signal beyond the role label.

### 5.1 Strict Pristine `gold_source_family_clean_real`

| Touch type | Exclude? | Reasoning |
| --- | --- | --- |
| `continuity_training` (any row) | **Yes** | Pristine set must exclude any source family the model has trained on. |
| `source_controlled_train_val` | **Yes** | Same as above. |
| `quasi_holdout` | **Yes** | Same source family was sampled; treat as related. |
| `debug_eval` | **Yes** | Pristine means never previously evaluated. |
| `gpt_labeled` (not currently a role) | **Yes** | GPT-labeled crops imply at least one pass over the page family. |

Recommendation: for pristine, escalate to **source-family-level** exclusion
rather than page-level, because the same source PDF's other pages share
style. Currently the registry is page-level only.

### 5.2 Practical `page_disjoint_real`

| Touch type | Exclude? | Reasoning |
| --- | --- | --- |
| `continuity_training` with `training_source=base_manifest` and `split=train` (i.e. a true training crop, especially `has_cloud=true`) | **Yes** | Direct training contamination. |
| `continuity_training` with `split=val` | **Yes** | Already used to validate the model. |
| `continuity_training` with `source_batch in {batch_004_hard_negatives, marker_fp_hard_negatives_20260502, eval_symbol_text_fp_hard_negatives_20260502}` (no-cloud hard negatives) | **Conservative** | The model saw a small no-cloud crop, not the full page; using the full page for eval still meaningfully measures full-page detection on previously unscored content. |
| `continuity_training` with `training_source=review_queue` (GPT review queue crops) | **Yes** | These crops were used in training. |
| `source_controlled_train_val` (train) | **Yes** | Same as `continuity_training` train. |
| `source_controlled_train_val` (val) | **Yes** | Used as held-out validation; should not be reused as eval truth. |
| `quasi_holdout` | **Conservative** | Deliberately not trained on. Could be promoted to eval truth after human full-page review. Currently disqualifies pages unnecessarily. |
| `debug_eval` | **Conservative** | Page metadata only; no recorded labels. Can be re-used as eval if re-labeled by current policy, but should be marked `previously_evaluated_unverified_label_status`. |

### 5.3 Future Training Expansion

| Touch type | Exclude? | Reasoning |
| --- | --- | --- |
| `continuity_training` train | No | Already in training; expansion can simply not duplicate. |
| `continuity_training` val | **Yes** | Don't pull val into train without conscious decision. |
| `source_controlled_train_val` val | **Yes** | Same. |
| `quasi_holdout` | No (review-gated) | Held out specifically so it can be promoted later. |
| `debug_eval` | **Depends** | If later promoted to frozen eval, exclude. If retired, allowed. |
| `page_disjoint_real` (frozen) | **Yes** (already enforced separately by eval policy) | Eval-frozen rule. |
| Untouched pages | No | These are the natural expansion target. |

### 5.4 Hard-Negative Mining

| Touch type | Exclude? | Reasoning |
| --- | --- | --- |
| `continuity_training` train (hard-neg already mined) | **Conservative** | Page already trained on, but mining new crops from the same page is normal continuation; the policy should be **"do not double-mine the same crop"**, not "do not mine the page." |
| `continuity_training` train (positive crops) | **Conservative** | Same page can yield additional unrelated hard-negative regions outside the positive crop windows. |
| `continuity_training` val | **Yes** | Don't move val pages into training as hard negatives. |
| `quasi_holdout` | **Yes (until promotion decision)** | Treat as eval candidate, not mining substrate. |
| `debug_eval` | **Yes (until label status known)** | Risk of leaking eval pages into training. |
| `page_disjoint_real` (frozen) | **Yes** (already enforced by eval policy). |

### 5.5 Manual Full-Page Review

| Touch type | Exclude? | Reasoning |
| --- | --- | --- |
| Any | No | Manual full-page review of any "touched" page **adds** information that did not exist before; touched roles describe crop coverage, not full-page review. The current policy implicitly conflates "had a crop reviewed" with "page is reviewed," which is wrong. |
| `page_disjoint_real` (frozen, already reviewed) | No (target) | Already the explicit eval-truth target. |

### 5.6 Synthetic Background Use

| Touch type | Exclude? | Reasoning |
| --- | --- | --- |
| `continuity_training` train/val | **Conservative** | Synthetic generation can paint clouds onto background pages; using a page that the model has seen as background is acceptable as long as the synthetic clouds are placed somewhere the model has not seen, and provenance is recorded. Eval policy already separates real vs synthetic scoring. |
| `quasi_holdout` | **Conservative** | Same logic. |
| `debug_eval` | **Yes (until label status known)** | Avoid using a page that may be in eval. |
| `page_disjoint_real` (frozen) | **Yes** (already enforced). |

## 6. Important Distinction: Touch Types Are Not Equally Meaningful

This is the core finding the prompt asked us to verify, and the data
supports it.

What "touched" currently encodes:

- `continuity_training`: someone took a crop from this page, GPT-classified
  or marker-detected it, then a human reviewed the **crop**. The full page
  was not necessarily looked at for missed clouds.
- `source_controlled_train_val`: same crops, post-split.
- `quasi_holdout`: same crops, but excluded from training.
- `debug_eval`: page was named in an older debug eval sample. No label data
  recorded in the row.

What "touched" does **not** encode:

- whether the **full page** was scanned for natural clouds,
- whether any candidate cloud on the page was missed,
- whether labels are GPT-provisional, human-audited, or human-corrected,
- whether the page is the same source family as a heavy training source,
- whether the touch was a positive crop or a no-cloud hard negative,
- whether the touch came from `random_standard_drawing_crop` (likely no cloud
  signal) versus `target_marker_neighborhood` (likely near a real revision).

The roi_candidate_selection_audit (2026-05-03) already established that prior
human review is candidate-conditioned: marker-driven, GPT-confidence-driven,
random-crop-driven. That audit's bottom-line ("prior human review was likely
biased by ROI selection, model confidence, delta logic, marker/triangle
proximity, and duplicate-heavy source selection") directly implies that
"touched-by-crop" pages may still have undiscovered natural clouds.

Therefore: a page that only had crop-level work (especially a single hard
negative or a single random crop) and was never full-page reviewed should
**not** be treated identically to a page that contributed dozens of positive
training crops. The current touched-page registry treats both as equivalent.

## 7. Recommended Refined Touch Policy

The recommendation is to **keep the existing strict registry as one
specific exclusion mode**, and add narrower exclusion modes for each
downstream use case. Each mode operates on the same underlying touch index,
but applies different filters.

### 7.1 Strict Pristine / Gold Holdout

Exclude a page if **any** of the following is true:

- any `continuity_training` row references the page,
- any `source_controlled_train_val` row references the page,
- any `quasi_holdout` row references the page,
- any `debug_eval` row references the page,
- any **other source-family page** is heavily touched (recommend defining
  this as "any page with a non-zero touch count from the same `source_id`,"
  i.e. extend the guard from page-level to source-family-level).

This is strictly more conservative than the current registry. It is the
right setting for `gold_source_family_clean_real`.

### 7.2 Practical `page_disjoint_real` Eval

Exclude a page if any of:

- any positive training crop touches the page (i.e.
  `training_source=base_manifest` and `has_cloud=true`, or any
  `source_control_split=train` with `has_cloud=true`),
- any val crop touches the page (`split=val` or `source_control_split=val`),
- any GPT-review-queue training crop touches the page
  (`training_source=review_queue` rows that are in `split=train` or `val`),
- any `debug_eval` row references the page **and** there is recorded
  label content.

Allow re-eligibility (with recorded provisional status) for pages whose
only touch is:

- hard-negative-only crop mining (e.g. `batch_004_hard_negatives`,
  `marker_fp_hard_negatives_20260502`,
  `eval_symbol_text_fp_hard_negatives_20260502`) **provided** human full-page
  re-review confirms no positive truth was missed,
- `quasi_holdout`-only,
- `debug_eval`-only with no label payload.

Mark each re-admitted page with a status flag like
`previously_touched_hardneg_only_reviewed_full_page` so the eval manifest
preserves provenance. Do not silently treat them as pristine.

### 7.3 Natural Data Mining (Hard-Negative Mining + Diagnostic Crops)

Exclude a page only if:

- it is in the active frozen `page_disjoint_real` set (eval-frozen),
- it is in `gold_source_family_clean_real` (eval-frozen),
- it is the same crop window already used (de-dup at the **crop** level, not
  page level).

Allow mining from any `continuity_training` page, any `quasi_holdout`-only
page (with awareness), and any `debug_eval`-only page once its eval status
is decided. The current registry blocks all of these unnecessarily.

### 7.4 Training Expansion

Exclude a page if:

- it is eval-frozen (`page_disjoint_real`, `gold_source_family_clean_real`,
  `style_balance_diagnostic_real_touched` while in active review),
- it is a `quasi_holdout` page that has not been promotion-decided,
- it is a `val`-split page (don't move val into train without explicit
  decision).

Allow expansion onto `continuity_training` `train`-split pages (these are
already in training; the question is which **new** crops to mine), and onto
fully untouched pages.

### 7.5 Synthetic Background Selection

Exclude a page if:

- it is eval-frozen (any frozen eval set),
- it has **positive** training crops that the synthetic placer might overlap
  with (operationally: avoid pasting synthetic clouds inside or adjacent to
  any training-positive crop bbox; the page itself is OK as background as
  long as overlap is avoided).

Allow:

- `continuity_training` pages whose only touches are no-cloud hard negatives,
- `quasi_holdout`-only pages,
- `debug_eval`-only pages with no eval label payload,
- fully untouched pages.

### 7.6 Implementation Sketch (Not Implemented Here)

To keep this report-only, this audit does not modify code. A future change
would:

- Extend `page_registry_row` to emit per-row provenance (e.g. counts of
  positive training rows, val rows, hard-neg-only rows, GPT-review rows,
  `debug_eval` rows separately) rather than only role-aggregated counters.
- Replace the single `already_touched_by_training_or_eval` guard with a set
  of named guards (`positive_train_used`, `val_used`, `quasi_held_out`,
  `debug_eval_seen`, `hard_neg_only`, `same_source_family_heavily_trained`).
- Expose explicit policy modes (`strict_pristine`, `practical_page_disjoint`,
  `mining_safe`, `training_expand_safe`, `synthetic_bg_safe`) that consume
  those guards.
- Optionally extend the touched-manifest list to cover any superseded
  manifests that may contain a page **not** in the consolidated current
  manifest, to prevent silent under-counting.

## 8. Recommended Next Step

The smallest concrete next step that does not modify the registry yet:

1. **Verify the legacy-manifest superset assumption.** Run a one-off audit
   script that compares the page-key set of every manifest in
   `CloudHammer/data/manifests/` to the page-key set of
   `reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`
   and reports any pages that only appear in superseded manifests. If empty,
   the current four-manifest list is complete. If non-empty, those pages are
   currently silently classified as untouched.
2. **Decide whether to refine the touched policy.** The two candidate
   directions are:
   - keep the current strict definition for `page_disjoint_real` and
     `gold_source_family_clean_real`, and introduce **separate, named
     touch-aware filters** for hard-negative mining, training expansion,
     full-page review queue selection, and synthetic background selection;
   - or relax the `page_disjoint_real` guard to allow re-admission of
     hard-neg-only and `quasi_holdout`-only pages after human full-page
     re-review.

Either direction implies code changes; this report does not implement them.

---

## Final Report

- **Report path**:
  `docs/archive_cleanup_audits/touched_definition_audit_2026_05_03.md`
- **Current definition of touched**: any non-zero row count from any of four
  hardcoded legacy manifests (`continuity_training`,
  `source_controlled_train_val`, `quasi_holdout`, `debug_eval`), aggregated to
  `source_page_key`. Implementation: single boolean guard
  `already_touched_by_training_or_eval` in
  `CloudHammer_v2/scripts/build_touched_page_registry.py`.
- **Top reasons pages are marked touched**:
  1. The 931-row `continuity_training` manifest covers all 98 touched
     eligible pages; no per-role weighting is applied.
  2. Hard-negative crops (no-cloud, marker-neighborhood, symbol/text)
     contribute 424+ of those rows and disqualify pages identically to
     positive training crops.
  3. `source_controlled_train_val` overlaps `continuity_training` for 81
     pages.
  4. `quasi_holdout` (deliberately not trained on) and `debug_eval` (page
     metadata only, no recorded labels) each block additional pages despite
     being weaker forms of "touched."
  5. The registry is page-level only; source-family proximity is not
     considered.
- **Whether current policy is overly conservative**: yes, for every use
  case **except** strict pristine `gold_source_family_clean_real` (where it
  is in fact arguably **too lenient** because it does not extend to
  source-family-level exclusion). For practical `page_disjoint_real`,
  hard-negative mining, training expansion, manual full-page review, and
  synthetic background use, the current guard is too strict.
- **Recommended refined touch policy**: keep the current strict mode as one
  named mode; add separate guards for positive training, val, hard-neg-only,
  GPT-review-only, quasi-holdout, debug-eval-without-labels, and
  same-source-family-heavily-trained; expose per-use-case policy modes
  (`strict_pristine`, `practical_page_disjoint`, `mining_safe`,
  `training_expand_safe`, `synthetic_bg_safe`) that compose those guards.
- **Files inspected**: see "Files Inspected" section above.
- **Checks run**: see "Checks Run" section above.
- **Recommended next step**: verify the legacy-manifest superset assumption
  (no page is silently untouched because it only appears in a superseded
  manifest) before deciding whether to refine the touched policy or relax
  `page_disjoint_real` re-admission rules.
