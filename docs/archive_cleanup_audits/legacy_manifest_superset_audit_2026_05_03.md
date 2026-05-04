# Legacy Manifest Superset Audit - 2026-05-03

Status: report-only audit. No code, labels, manifests, datasets, model files,
eval files, or existing docs were modified. This file is the only intended
deliverable.

Scope: verify whether the touched-page registry's four-manifest source list
is complete enough, or whether older/superseded manifests under
`CloudHammer/data/manifests/` contain `source_page_key` values that are not
present in the consolidated current touched manifest
`reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`.

Reference: `docs/archive_cleanup_audits/touched_definition_audit_2026_05_03.md`
(open question 1 in that report's "Risks or unresolved questions" section).

## Executive Summary

The four-manifest current touched list **is complete with respect to model
training and review-stage human labeling**. Every page key in any
`reviewed_batch_*` manifest, in `reviewed_plus_marker_fp_hard_negatives_*`,
in `marker_fp_hard_negatives_*`, in `eval_symbol_text_fp_hard_negatives_*`,
in `cloud_roi_broad_candidates_*`, and in `large_cloud_context_stress_*`
already appears in the consolidated training manifest. Those manifests are
**genuine subsets** of the consolidated one; ignoring them silently does not
miss any training-touched page.

However, the four-manifest list **does miss three weaker classes of
"touch"**:

1. Algorithmic delta-marker detection coverage
   (`delta_manifest.jsonl`) — 168 page keys not in consolidated.
2. Page-level review-queue priority enumeration
   (`large_cloud_context_revision1_pages_20260428.jsonl`) — 7 page keys not
   in consolidated.
3. Candidate ROI generation that did not survive into reviewed/training
   (`cloud_roi_broad_allmarkers_20260427.jsonl`,
   `cloud_roi_manifest.jsonl`, `roi_manifest.jsonl`,
   `roi_manifest_resolved_20260427.jsonl`) — between 2 and 12 page keys not
   in consolidated, depending on manifest.

After cross-referencing, **17 page keys are present in at least one
non-current-touched manifest but absent from all four current touched
manifests, and are eligible standard drawings**. Those 17 keys are
**exactly** the 17 frozen `page_disjoint_real` pages.

So the answer is:

- **Does the current registry miss any training-touched pages?** No. All
  training/review-stage touches are captured by the four current manifests.
- **Does the current registry miss any other kind of touch on the 17 frozen
  page_disjoint_real pages?** Yes. All 17 had algorithmic delta markers
  detected, 7 of 17 were enumerated in a manual review-priority queue for
  Revision 1 large-cloud context, and 2 of 17 had candidate ROIs generated
  that never made it into reviewed/training.
- **Does that change page_disjoint_real eval validity?** No. None of those
  weaker touches imply model training contamination, and human full-page
  review on those 17 pages is now the source of eval truth.
- **Should the registry be extended?** Recommended yes, as a diagnostic
  provenance enrichment, not as a stricter eval-eligibility guard. The
  refined-policy guards proposed in the touched-definition audit should
  consume this provenance with explicit per-source semantics.

## Files Inspected

- `docs/archive_cleanup_audits/touched_definition_audit_2026_05_03.md`
- `CloudHammer_v2/scripts/build_touched_page_registry.py` (helpers imported,
  read-only)
- `CloudHammer_v2/outputs/touched_page_registry_20260502/touched_page_registry.jsonl`
- All 25 `*.jsonl` files under `CloudHammer/data/manifests/`:
  - `cloud_roi_broad_allmarkers_20260427.jsonl`
  - `cloud_roi_broad_candidates_20260427.jsonl`
  - `cloud_roi_manifest.jsonl`
  - `delta_manifest.jsonl`
  - `eval_symbol_text_fp_hard_negatives_20260502.jsonl`
  - `fullpage_eval_sample_broad_deduped_20260428.jsonl`
  - `large_cloud_context_revision1_pages_20260428.jsonl`
  - `large_cloud_context_stress_pages_20260428.jsonl`
  - `marker_fp_hard_negatives_20260502.jsonl`
  - `pages.jsonl`
  - `pages_standard_drawings_no_index_20260427.jsonl`
  - `reviewed_batch_001_002_004partial_plus_broad_deduped_20260428.jsonl`
  - `reviewed_batch_001_002_plus_004partial.jsonl`
  - `reviewed_batch_001_002_plus_004partial_current_20260427.jsonl`
  - `reviewed_batch_001_plus_002.jsonl`
  - `reviewed_batch_001_priority_train.jsonl`
  - `reviewed_batch_004_hard_negatives_partial_001_325.jsonl`
  - `reviewed_plus_marker_fp_hard_negatives_20260502.jsonl`
  - `reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`
    (CONSOLIDATED)
  - `roi_manifest.jsonl`
  - `roi_manifest_resolved_20260427.jsonl`
  - `smoke_blueprint_pages.jsonl`
  - `smoke_pages.jsonl`
  - `source_controlled_small_corpus_20260502.jsonl`
    (current touched)
  - `source_controlled_small_corpus_20260502.quasi_holdout.jsonl`
    (current touched)

Companion `*.summary.json` files were noted but not parsed; they describe
runs, not page-key contents.

## Methodology

To make the comparison apples-to-apples with the registry script, this audit
imported `read_jsonl`, `source_page_key_for_row`, `source_id_for_row`, and
`page_index_for_row` from
`CloudHammer_v2/scripts/build_touched_page_registry.py` and applied them
unchanged to every manifest row. No registry code was modified.

For each `*.jsonl` manifest the audit extracted the set of resolvable
`source_page_key` values (e.g. `Revision_1_-_Drawing_Changes:p0003`),
counted `unresolved` rows where the helper returned `None`, and compared
against the consolidated key set.

The "silently untouched" set was computed as:

- the union of page keys appearing in **any** non-consolidated manifest,
- minus the union of page keys present in **any** of the four current
  touched manifests.

That set was then intersected with the 115 eligible standard drawing page
keys and with the registry's "untouched eligible" set, to identify pages
where the four-manifest list is materially incomplete from an eligibility
point of view.

## Per-Manifest Page-Key Comparison

Total `*.jsonl` manifests inspected: `25`. Consolidated manifest:
`reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`
(`931` rows, `102` unique page keys, `0` unresolved).

Reading the table below:

- "rows" = total rows in the manifest.
- "page keys" = unique resolved `source_page_key` values.
- "shared" = page keys also in the consolidated manifest.
- "only here" = page keys present in this manifest but not in the
  consolidated manifest.
- "unresolved" = rows whose `source_page_key` could not be derived (always
  `0` in this corpus).

| Manifest | Role today | rows | page keys | shared | only here |
| --- | --- | ---: | ---: | ---: | ---: |
| `reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl` | CONSOLIDATED, current touched (`continuity_training`) | 931 | 102 | 102 | 0 |
| `source_controlled_small_corpus_20260502.jsonl` | current touched (`source_controlled_train_val`) | 502 | 85 | 85 | 0 |
| `source_controlled_small_corpus_20260502.quasi_holdout.jsonl` | current touched (`quasi_holdout`) | 30 | 7 | 7 | 0 |
| `fullpage_eval_sample_broad_deduped_20260428.jsonl` | current touched (`debug_eval`) | 14 | 14 | 14 | 0 |
| `reviewed_plus_marker_fp_hard_negatives_20260502.jsonl` | superseded by consolidated | 922 | 101 | 101 | 0 |
| `marker_fp_hard_negatives_20260502.jsonl` | superseded subset | 29 | 18 | 18 | 0 |
| `eval_symbol_text_fp_hard_negatives_20260502.jsonl` | superseded subset | 9 | 6 | 6 | 0 |
| `reviewed_batch_001_002_004partial_plus_broad_deduped_20260428.jsonl` | superseded reviewed batch | 893 | 101 | 101 | 0 |
| `reviewed_batch_001_002_plus_004partial_current_20260427.jsonl` | superseded reviewed batch | 723 | 76 | 76 | 0 |
| `reviewed_batch_001_002_plus_004partial.jsonl` | superseded reviewed batch | 624 | 76 | 76 | 0 |
| `reviewed_batch_004_hard_negatives_partial_001_325.jsonl` | superseded reviewed batch | 325 | 65 | 65 | 0 |
| `reviewed_batch_001_plus_002.jsonl` | superseded reviewed batch | 299 | 58 | 58 | 0 |
| `reviewed_batch_001_priority_train.jsonl` | superseded reviewed batch | 204 | 49 | 49 | 0 |
| `cloud_roi_broad_candidates_20260427.jsonl` | candidate-stage ROIs (subset) | 2143 | 75 | 75 | 0 |
| `large_cloud_context_stress_pages_20260428.jsonl` | context priority list (subset) | 14 | 14 | 14 | 0 |
| `cloud_roi_broad_allmarkers_20260427.jsonl` | candidate-stage ROIs | 2741 | 84 | 82 | 2 |
| `cloud_roi_manifest.jsonl` | legacy candidate-stage ROIs | 2185 | 81 | 79 | 2 |
| `roi_manifest.jsonl` | legacy candidate-stage ROIs | 458 | 99 | 87 | 12 |
| `roi_manifest_resolved_20260427.jsonl` | legacy candidate-stage ROIs (re-resolved) | 458 | 99 | 87 | 12 |
| `large_cloud_context_revision1_pages_20260428.jsonl` | manual review-priority page list | 49 | 49 | 42 | 7 |
| `delta_manifest.jsonl` | algorithmic delta-marker detection | 270 | 270 | 102 | 168 |
| `pages.jsonl` | master page index (all pages, all kinds) | 332 | 332 | 102 | 230 |
| `pages_standard_drawings_no_index_20260427.jsonl` | eligible-page filter | 115 | 115 | 98 | 17 |
| `smoke_blueprint_pages.jsonl` | smoke-test page (subset) | 1 | 1 | 1 | 0 |
| `smoke_pages.jsonl` | smoke-test page | 1 | 1 | 0 | 1 |

Observations:

- All `reviewed_batch_*` manifests are **proper subsets** of the
  consolidated manifest. Ignoring them as touch sources is correct.
- `reviewed_plus_marker_fp_hard_negatives_20260502.jsonl`,
  `marker_fp_hard_negatives_20260502.jsonl`, and
  `eval_symbol_text_fp_hard_negatives_20260502.jsonl` are also subsets of
  consolidated. Their hard-negative page keys are already counted.
- `cloud_roi_broad_candidates_20260427.jsonl` is a strict subset (75 of 75
  shared). `cloud_roi_broad_allmarkers_20260427.jsonl` is a near-subset
  with 2 candidate-only pages that did not survive review.
- `roi_manifest.jsonl` and `roi_manifest_resolved_20260427.jsonl` are
  identical at the page-key level and contribute 12 candidate-only pages
  that did not survive review.
- `cloud_roi_manifest.jsonl` contributes 2 candidate-only pages.
- `large_cloud_context_revision1_pages_20260428.jsonl` is a manually
  curated 49-page list flagged
  `large_cloud_context_priority.source = "manual_revision1_large_cloud_review"`,
  `reason = "user_requested_revision_set_1_full_standard_non_index_pages"`.
  7 of those 49 are not in consolidated.
- `delta_manifest.jsonl` contains an `active_deltas` array per page (no
  labels, no review). 168 of its 270 page keys are not in consolidated;
  this is the largest source of "uncovered" pages, but only as algorithmic
  triangle detection coverage.
- `pages.jsonl` has 230 keys outside consolidated; nearly all are
  non-drawing pages (specifications, narratives, indexes) that are not
  eligible standard drawings.
- `smoke_pages.jsonl` is a single smoke-test entry for
  `Revision_1_-_Drawing_Changes:p0000`, which is also flagged in the
  registry as a non-eligible standard drawing.

## Aggregate Findings

Across all non-consolidated manifests:

- Page keys present in any non-consolidated manifest but absent from
  consolidated: `230`.
- Page keys also absent from **all four** current touched manifests
  ("silently untouched"): `230`.
- Of those, eligible standard drawings: `17`.
- Of those, currently classified by the registry as untouched-eligible
  (i.e., currently selectable into `page_disjoint_real`): `17`.

The 17 "silently untouched eligible" page keys are exactly the 17 frozen
`page_disjoint_real` pages.

### Provenance Of The 17 Silently Untouched Eligible Pages

For each of the 17 frozen `page_disjoint_real` pages, the table below
shows which **non-current-touched** manifests contain the page key.
"Master" includes `pages.jsonl` and
`pages_standard_drawings_no_index_20260427.jsonl`, which are not "touch"
sources (master index and eligibility filter), so they are intentionally
omitted from the meaningful-touch column.

| Page key | Algorithmic markers (`delta_manifest`) | Review-queue list (`large_cloud_context_revision1_pages_*`) | Candidate ROIs (`cloud_roi_broad_allmarkers_*`, `roi_manifest*`) |
| --- | :---: | :---: | :---: |
| `Revision_1_-_Drawing_Changes:p0003` | yes | yes | no |
| `Revision_1_-_Drawing_Changes:p0032` | yes | yes | no |
| `Revision_1_-_Drawing_Changes:p0033` | yes | yes | no |
| `Revision_1_-_Drawing_Changes:p0034` | yes | yes | no |
| `Revision_1_-_Drawing_Changes:p0036` | yes | yes | no |
| `Revision_1_-_Drawing_Changes:p0037` | yes | yes | no |
| `Revision_1_-_Drawing_Changes:p0041` | yes | yes | no |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0014` | yes | no | no |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0020` | yes | no | no |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0022` | yes | no | no |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0025` | yes | no | no |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0026` | yes | no | no |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0027` | yes | no | no |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0028` | yes | no | no |
| `260303-VA_Biloxi_Rev_5_RFI-126:p0007` | yes | no | no |
| `260313_-_VA_Biloxi_Rev_3:p0188` | yes | no | yes (`cloud_roi_broad_allmarkers_20260427.jsonl`, `roi_manifest.jsonl`, `roi_manifest_resolved_20260427.jsonl`) |
| `260313_-_VA_Biloxi_Rev_3:p0197` | yes | no | yes (`cloud_roi_broad_allmarkers_20260427.jsonl`, `roi_manifest.jsonl`, `roi_manifest_resolved_20260427.jsonl`) |

Summary:

- All 17 had algorithmic delta-marker triangles detected
  (`active_deltas` non-empty in `delta_manifest.jsonl`).
- 7 of 17 were enumerated in the manual Revision-1 review-priority page
  list (no labels recorded; the row only carries page metadata plus a
  `large_cloud_context_priority` flag).
- 2 of 17 (`260313_-_VA_Biloxi_Rev_3:p0188` and `:p0197`) had candidate
  ROIs generated in the broad-allmarkers and ROI manifests, but none of
  those crops survived into the consolidated reviewed manifest.

### Other Pages With Only-Outside-Consolidated Provenance

Beyond the 17 eligible standard drawings, the remaining 213 silently-only
page keys are:

- non-drawing or index pages (specifications, narratives), captured by
  `pages.jsonl` but excluded from
  `pages_standard_drawings_no_index_20260427.jsonl`. These are correctly
  ineligible regardless of touch state.
- non-eligible standard drawings (e.g.
  `260219_-_VA_Biloxi_Rev_4_Architectural_1:p0000`,
  `Revision_Set_7:p0001`) that exist in the master and ROI manifests but
  are not in the eligibility filter for other reasons (file naming, index
  classification, etc.). They are not candidates for `page_disjoint_real`
  today.

None of these affect the current `page_disjoint_real` selection.

## Does The Current Touched Registry Undercount Touched Pages?

Mixed answer, depending on what "touch" means.

### What The Registry Does Not Undercount

If "touch" means **the model trained on or human-reviewed a crop from this
page**, the answer is **no, the registry is complete**. Every reviewed
batch and hard-negative manifest is already either the consolidated
manifest or a subset of it; every page key they reference is covered.

Specifically:

- All 102 page keys in
  `reviewed_plus_marker_fp_hn_plus_eval_symbol_text_fp_hn_20260502.jsonl`
  are present.
- Subsets `reviewed_plus_marker_fp_hard_negatives_20260502.jsonl`,
  `marker_fp_hard_negatives_20260502.jsonl`,
  `eval_symbol_text_fp_hard_negatives_20260502.jsonl`, and the
  `reviewed_batch_*` manifests contribute zero additional page keys.
- Subset `cloud_roi_broad_candidates_20260427.jsonl` contributes zero.
- Subset `large_cloud_context_stress_pages_20260428.jsonl` contributes
  zero.

### What The Registry Does Undercount

If "touch" includes weaker provenance (algorithmic detection only, page
queued for priority review only, candidate ROI generated but never
reviewed), then the registry is **incomplete in three specific ways**:

1. **Algorithmic delta-marker detection is not a touch source.**
   `delta_manifest.jsonl` was the input to candidate ROI generation. Its
   270 entries cover every page where revision-marker triangles were
   detected, including all 17 currently untouched-eligible pages and 168
   non-consolidated pages overall. The registry has no signal that a page
   had algorithmic markers detected.

2. **The Revision-1 manual large-cloud-context review-priority page list
   is not a touch source.** `large_cloud_context_revision1_pages_20260428.jsonl`
   carries a `large_cloud_context_priority` flag identifying 49 pages a
   human curator wanted reviewed for large clouds in Revision 1. 7 of
   those are currently in `page_disjoint_real`. Whether they were ever
   actually reviewed is not encoded in the manifest itself.

3. **Candidate ROI manifests where crops did not survive review are not
   touch sources.** `cloud_roi_broad_allmarkers_20260427.jsonl`,
   `cloud_roi_manifest.jsonl`, `roi_manifest.jsonl`, and
   `roi_manifest_resolved_20260427.jsonl` collectively contribute up to
   12 page keys whose candidate ROIs were generated but never appeared
   in the consolidated reviewed manifest. Two of those 12 are in the
   current `page_disjoint_real` set.

In the categories from the touched-definition audit, these are
`model_inferred`, `candidate_manifest_only`, and `crop_generated`
respectively. They were intentionally excluded from the registry's
binary `touched` flag, but the registry also does not surface them as
diagnostic provenance.

### Does This Affect `page_disjoint_real` Eligibility?

No, in any reasonable policy.

- **Strict pristine `gold_source_family_clean_real`**: this is the only
  policy where one might argue that algorithmic-marker detection or
  manual review-queue queueing should disqualify a page. Even there, the
  17 affected pages are already eval-frozen by separate eval policy and
  are now human-reviewed full-page truth, so re-classifying them as
  "touched" would not improve eval purity.
- **Practical `page_disjoint_real`**: model never trained on these
  pages, and they were just human-reviewed for full-page truth. They
  are valid eval truth.
- **Hard-negative mining, training expansion, synthetic background
  selection**: these pages are eval-frozen and would be excluded from
  mining/synthesis under the eval-policy frozen-page rule regardless of
  their delta-marker history.
- **Manual full-page review**: already done.

### Does This Suggest An Implementation Change?

The current registry is correct as a **training-contamination guard**.
It is missing **diagnostic provenance** that would help the refined-policy
guards proposed in the touched-definition audit:

- A page with `model_inferred` delta markers is qualitatively different
  from a page with no detected markers. For hard-negative mining or
  training-expansion candidate ranking, knowing where markers were
  detected is useful.
- A page that was on a `large_cloud_context` priority review list is a
  signal that a curator considered it interesting; that informs eval
  selection priorities.
- A page with generated-but-unreviewed candidate ROIs is a signal that
  the page is the same source family as reviewed pages and that the
  pipeline considered crops there.

A future, non-blocking enrichment would add these as separate per-row
provenance fields in the registry (e.g.
`delta_marker_detected`, `was_in_large_cloud_context_priority`,
`had_unreviewed_candidate_rois`) without changing the binary
`touched` guard. This audit does not implement that change.

## Sanity Notes

- All 25 manifests resolved every row to a `source_page_key` (zero
  unresolved across the corpus). The registry's key-derivation logic is
  robust on the current data shapes.
- `roi_manifest.jsonl` and `roi_manifest_resolved_20260427.jsonl` have
  identical 458-row, 99-key, 12-only-here profiles. They are functionally
  the same manifest under two filenames; either could be ignored without
  loss.
- `cloud_roi_broad_allmarkers_20260427.jsonl` (`only_in_this = 2`) and
  `cloud_roi_broad_candidates_20260427.jsonl` (`only_in_this = 0`) are
  the input candidate set and the deduped subset that fed the broad GPT
  review queue. The 2-key difference is the dedup drop.
- `pages.jsonl` (332 rows) and `pages_standard_drawings_no_index_20260427.jsonl`
  (115 rows) are not "touch" sources. They are the master page index and
  the eligibility filter, respectively. The numbers in the
  per-manifest table are reported for completeness.
- `delta_manifest.jsonl` row paths reference a foreign workspace prefix
  (`F:\Desktop\m\projects\drawing_revision\...`) rather than the current
  `scopeLedger` path. This does not affect key derivation, but it
  signals that the manifest was generated under a different repo layout.
  Worth noting for any future refresh.

## Recommendation

**Do not change the registry policy yet.** The four-manifest list is
correct for the training-contamination guard that the registry's
single boolean `touched` flag implements today. Extending the manifest
list with `delta_manifest.jsonl`,
`large_cloud_context_revision1_pages_20260428.jsonl`,
`cloud_roi_broad_allmarkers_20260427.jsonl`, and the legacy ROI
manifests would inflate `touched` without distinguishing between
training contamination and weaker provenance, and it would mark all
17 currently frozen `page_disjoint_real` pages as `touched`, which is
not the intent of the eval-frozen rule.

The right destination for these weaker provenance signals is the
refined-policy enrichment proposed in
`docs/archive_cleanup_audits/touched_definition_audit_2026_05_03.md`:
emit per-row provenance fields, then compose per-use-case filters
(`strict_pristine`, `practical_page_disjoint`, `mining_safe`,
`training_expand_safe`, `synthetic_bg_safe`) over those fields rather
than collapse everything into one binary touch flag.

## Recommended Next Step

When/if the touched-definition refinement is implemented (currently
deferred per the prior audit's "Recommended next step"), include three
named provenance fields on each registry row:

- `delta_marker_detected` (bool, derived from `delta_manifest.jsonl`).
- `was_in_review_priority_queue` (set of queue-name strings, derived
  from `large_cloud_context_*` manifests).
- `had_unreviewed_candidate_rois` (set of candidate-manifest names,
  derived from `cloud_roi_broad_allmarkers_*`, `cloud_roi_manifest.jsonl`,
  `roi_manifest.jsonl`, `roi_manifest_resolved_*`).

These would supplement, not replace, the four current touch roles and
preserve the current binary `touched` semantics. The refined per-use-case
guards proposed in the prior audit can then read these fields explicitly.

Until that refinement is taken on, no registry change is required.

---

## Final Report

- **Report path**:
  `docs/archive_cleanup_audits/legacy_manifest_superset_audit_2026_05_03.md`
- **Number of manifests inspected**: `25` `*.jsonl` manifests under
  `CloudHammer/data/manifests/`, plus the registry output and the
  consolidated touched manifest cross-checked against them.
- **Whether any older manifests contain page keys missing from the
  consolidated manifest**: yes, but with important qualifiers.
  - `delta_manifest.jsonl` contributes `168` page keys absent from
    consolidated (algorithmic marker detection only).
  - `large_cloud_context_revision1_pages_20260428.jsonl` contributes
    `7` (manual Revision-1 review-priority queue, no labels).
  - `cloud_roi_broad_allmarkers_20260427.jsonl` contributes `2`,
    `cloud_roi_manifest.jsonl` contributes `2`, and
    `roi_manifest.jsonl` / `roi_manifest_resolved_20260427.jsonl` each
    contribute `12` (candidate ROIs generated but never reviewed).
  - Across all sources, `230` page keys are present outside consolidated
    and in no current touched manifest. Of those, `17` are eligible
    standard drawings, and they are exactly the `17` frozen
    `page_disjoint_real` pages.
- **Whether the current touched registry undercounts any touched pages**:
  - **No** for training/review-stage touches. All such page keys are
    already in the consolidated manifest.
  - **Yes** for weaker provenance: algorithmic-marker detection, manual
    review-priority page enumeration, and unreviewed candidate ROIs are
    not represented in the registry. The 17 silently-untouched eligible
    pages each have at least one such weaker signal, but none of those
    signals imply training contamination, and all 17 pages are already
    eval-frozen by separate policy.
- **Recommended next step**: keep the current touched registry policy
  unchanged for now. When the refined per-use-case touch policy from
  the prior audit is implemented, add three named provenance fields
  (`delta_marker_detected`, `was_in_review_priority_queue`,
  `had_unreviewed_candidate_rois`) to enrich registry rows, without
  altering the binary `touched` guard or the current `page_disjoint_real`
  freeze selection.
