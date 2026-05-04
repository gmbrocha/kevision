# Runs And Experiments Cleanup Audit - 2026-05-02

Status: report-only audit. No files were moved, deleted, renamed, or modified
outside this report.

Scope inspected:

- `runs/`
- `experiments/`
- `tests/`
- `CloudHammer/runs/`
- `CloudHammer/tests/`

## Summary

The repository has two large generated-artifact zones:

- root `runs/`: app workspaces, export outputs, app/server logs, and a small
  YOLO eval folder. Approx. `7,436.43 MB` across `1,162` files.
- legacy `CloudHammer/runs/`: YOLO training runs, full-page eval outputs,
  fragment-grouping outputs, whole-cloud candidate outputs, and source-audit
  reports. Approx. `22,374.60 MB` across `7,032` files.

Root `runs/` is ignored by `.gitignore` and has no tracked files. It still
contains the currently registered demo project workspace, so it should not be
blanket-moved.

`CloudHammer/runs/` is ignored by `.gitignore`, but `93` files are already
tracked. This matters: future cleanup may create large rename/delete diffs if
it is not planned carefully.

`tests/` and `CloudHammer/tests/` should remain in place. Only their
`__pycache__` folders are cleanup noise.

`experiments/` is mostly tracked historical exploratory work. It is not
currently referenced by active app code except as a generic module category in
docs. Treat it as legacy but valuable until a separate experiment-retention
decision is made.

## Reference Findings

Current references found outside `docs/archive/`:

- `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/...` appears
  in historical meeting notes and is also the active `demo-project` workspace
  in `runs/projects.json`.
- `backend/projects.py` stores project registry state in `projects.json` next
  to the seed workspace parent. With the current demo workspace, that means
  `runs/projects.json`.
- legacy CloudHammer configs reference:
  - `CloudHammer/runs/fullpage_eval_broad_deduped_20260428/outputs`
  - `CloudHammer/runs/fullpage_all_broad_deduped_20260428/outputs`
  - `CloudHammer/runs/fullpage_all_broad_deduped_lowconf_20260428/outputs`
  - `CloudHammer/runs/fullpage_eval_marker_fp_hn_20260502/outputs`
  - `CloudHammer/runs/fullpage_eval_symbol_text_fp_hn_20260502/outputs`
- legacy CloudHammer scripts reference:
  - `CloudHammer/runs/fullpage_eval_broad_deduped_20260428`
  - `CloudHammer/runs/whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428`
  - `CloudHammer/runs/whole_cloud_eval_marker_fp_hn_20260502`
  - `CloudHammer/runs/whole_cloud_eval_symbol_text_fp_hn_20260502`
- `CloudHammer_v2` docs do not reference specific legacy run folders. They say
  existing data/model runs should not be moved and legacy imports must be
  audited.

## Recommended Future Target Structure

Do not apply this structure yet. It is a future cleanup target after the
CloudHammer_v2 baseline ruler exists or after a human signs off on artifact
retention.

```text
runs/
  projects.json                  # only if still used by active app
  projects/                      # active app project registry support
  <active-workspace>/            # current app workspaces only

archive/
  generated_runs/
    2026_05_02/
      root_runs/
        app_exports/
        app_logs/
        yolo_eval/
      cloudhammer_legacy_runs/
        model_lineage/
        fullpage_eval/
        fragment_grouping/
        whole_cloud_candidates/
        whole_cloud_eval/
      experiments/
        2026_04_legacy/
```

If any legacy model checkpoint is needed by CloudHammer_v2, copy it into
`CloudHammer_v2/models/` only after audit and record it in
`CloudHammer_v2/IMPORT_LOG.md`. Do not move original checkpoints as part of an
import.

## Keep In Place

| Path | Type/category | Apparent purpose | Modified | Size | Referenced? | Recommended action |
|---|---|---|---:|---:|---|---|
| `runs/projects.json` | Active/current | App project registry; points `demo-project` at the corrected split workspace. | 2026-04-29 21:20 | ~0 MB | Yes, indirectly by `backend/projects.py` registry behavior. | Keep in place until demo workspace is retired. |
| `runs/projects/` | Active/current | App project workspace container. Currently empty. | 2026-04-29 21:20 | 0 MB | Indirect app convention. | Keep in place. |
| `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/` | Active/current | Registered demo workspace and latest corrected export set used in meeting references. | 2026-04-30 10:29 | 2,478.86 MB | Yes: `runs/projects.json`, meeting notes. | Keep in place until replacement demo workspace is created. |
| `tests/conftest.py` | Active/current | Root app pytest setup. | 2026-04-24 15:30 | ~0 MB | Yes, pytest convention. | Keep in place. |
| `tests/test_app.py` | Active/current | Root app tests. | 2026-04-30 20:10 | 0.05 MB | Yes, pytest convention. | Keep in place. |
| `tests/fixtures/` | Active/current | Expected test fixture data. | 2026-04-24 15:30 | ~0 MB | Yes, root tests. | Keep in place. |
| `CloudHammer/tests/test_cloudhammer.py` | Active/current | Legacy CloudHammer test suite. Recently modified; likely still relevant until v2 import decisions are made. | 2026-05-02 10:23 | 0.03 MB | Yes, pytest convention. | Keep in place. |
| `CloudHammer/runs/cloudhammer_roi-symbol-text-fp-hn-20260502/` | Active/current | Latest observed hard-negative training run/checkpoint lineage. | 2026-05-02 09:21 | 19.60 MB | Yes, checkpoint lineage; not directly from v2 docs. | Keep in place until CloudHammer_v2 model audit imports or retires it. |
| `CloudHammer/runs/cloudhammer_roi-marker-fp-hn-20260502/` | Active/current | Marker false-positive hard-negative training run; parent for symbol/text run. | 2026-05-02 02:12 | 19.60 MB | Yes, referenced by symbol/text run `args.yaml`. | Keep in place. |
| `CloudHammer/runs/cloudhammer_roi-broad-deduped-20260428/` | Active/current | Broad-deduped model baseline; parent for marker hard-negative run. | 2026-04-28 00:14 | 19.29 MB | Yes, referenced by marker run `args.yaml`. | Keep in place until lineage is documented. |
| `CloudHammer/runs/fullpage_eval_marker_fp_hn_20260502/` | Active/current | Marker hard-negative full-page eval output. | 2026-05-02 02:14 | 58.10 MB | Yes, legacy config references this output path. | Keep in place. |
| `CloudHammer/runs/fullpage_eval_symbol_text_fp_hn_20260502/` | Active/current | Symbol/text hard-negative full-page eval output. | 2026-05-02 09:22 | 56.16 MB | Yes, legacy config references this output path. | Keep in place. |
| `CloudHammer/runs/fragment_grouping_fullpage_eval_marker_fp_hn_20260502/` | Active/current | Grouping output paired to marker eval. | 2026-05-02 02:14 | 133.83 MB | Indirect, paired with eval run. | Keep in place. |
| `CloudHammer/runs/fragment_grouping_fullpage_eval_symbol_text_fp_hn_20260502/` | Active/current | Grouping output paired to symbol/text eval. | 2026-05-02 09:22 | 133.56 MB | Indirect, paired with eval run. | Keep in place. |
| `CloudHammer/runs/whole_cloud_eval_marker_fp_hn_20260502/` | Active/current | Whole-cloud candidate eval/review output for marker FP hard negatives. | 2026-05-02 09:01 | 154.61 MB | Yes, `launch_review_queue.ps1` and related scripts. | Keep in place. |
| `CloudHammer/runs/whole_cloud_eval_symbol_text_fp_hn_20260502/` | Active/current | Whole-cloud candidate eval/review output for symbol/text FP hard negatives. | 2026-05-02 09:22 | 149.59 MB | Yes, `build_balanced_expansion_review_batch.py`, `launch_review_queue.ps1`. | Keep in place. |
| `CloudHammer/runs/source_audit_small_corpus_20260502/` | Active/current | Source/page-family audit output for small-corpus pivot. | 2026-05-02 10:09 | 0.02 MB | Not directly referenced, but relevant to current pivot decisions. | Keep in place. |
| `CloudHammer/runs/whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428/` | Active/current but heavy | Latest broad candidate/crop run used by legacy review queue default. | 2026-05-02 01:42 | 8,428.48 MB | Yes, `launch_review_queue.ps1`. | Keep in place until review queue default changes or data is summarized. |

## Legacy But Valuable

| Path | Type/category | Apparent purpose | Modified | Size | Referenced? | Recommended action |
|---|---|---|---:|---:|---|---|
| `runs/detect/` | Legacy but valuable | YOLO validation/eval visual outputs under nested `runs/eval/human_204_on_combined_val`. | 2026-04-24 20:58 | 4.90 MB | No current references found. | Move to archive later under generated YOLO eval history. |
| `experiments/2026_04_delta_marker_detector/` | Legacy but valuable | Delta/marker detector exploratory code. | 2026-04-24 03:10 | 0.06 MB | No current references found. | Keep until experiment-retention review; then archive under `archive/experiments/`. |
| `experiments/2026_04_index_parser/` | Legacy but valuable | Index parser exploration and small CSV outputs. | 2026-04-24 03:10 | 0.07 MB | No current references found. | Archive later after confirming no lessons need promotion to docs/code. |
| `experiments/2026_04_stamp_finder/` | Legacy but valuable | Stamp/circle finding exploratory scripts. | 2026-04-24 15:30 | 0.03 MB | No current references found. | Archive later. |
| `experiments/delta_v3/` | Legacy but valuable | Denoising experiments with generated visual examples. | 2026-04-24 03:10 | 18.46 MB | No current references found. | Archive later; consider keeping only summary images if space matters. |
| `experiments/delta_v4/` | Legacy but valuable | Later delta detector exploration. | 2026-04-24 03:10 | 0.09 MB | No current references found. | Archive later. |
| `experiments/extract_changelog.py` | Legacy but valuable | Early changelog extraction script. | 2026-04-24 02:51 | ~0 MB | No current references found. | Human decision: archive or preserve until product extraction path is stable. |
| `experiments/preview_revision_changelog.py` | Legacy but valuable | Early workbook/preview generation script. | 2026-04-24 15:30 | ~0 MB | No current references found. | Human decision: archive or preserve until deliverable path is stable. |
| `CloudHammer/runs/cloudhammer_roi/` | Legacy but valuable | Early ROI YOLO training run/checkpoints. | 2026-04-24 15:45 | 18.17 MB | No direct current references found. | Move to model-lineage archive later after checkpoint decision. |
| `CloudHammer/runs/cloudhammer_roi-2/` | Legacy but valuable | Early ROI YOLO training run/checkpoints. | 2026-04-24 20:47 | 18.94 MB | No direct current references found. | Move to model-lineage archive later. |
| `CloudHammer/runs/cloudhammer_roi-3/` | Legacy but valuable | Early ROI YOLO training run/checkpoints. | 2026-04-24 23:23 | 19.45 MB | No direct current references found. | Move to model-lineage archive later. |
| `CloudHammer/runs/cloudhammer_roi-hardneg-20260427/` | Legacy but valuable | Earlier hard-negative model run/checkpoints. | 2026-04-27 18:47 | 19.37 MB | No direct current references found. | Move to model-lineage archive later after documenting lineage. |
| `CloudHammer/runs/fullpage_eval_broad_deduped_20260428/` | Legacy but valuable | Broad-deduped full-page eval output and audit summary. | 2026-04-28 03:21 | 62.34 MB | Yes, legacy config and `group_fragment_detections.py` default. | Keep until defaults change; archive later. |
| `CloudHammer/runs/fullpage_all_broad_deduped_20260428/` | Legacy but valuable | Full-page detections over all broad-deduped sources. | 2026-04-28 07:15 | 558.54 MB | Yes, legacy config references output path. | Archive later only after replacing configs/defaults. |
| `CloudHammer/runs/fullpage_all_broad_deduped_lowconf_20260428/` | Legacy but valuable | Low-confidence full-page all-source detections. | 2026-04-28 08:51 | 565.77 MB | Yes, legacy config references output path. | Archive later after summary/manifest preservation. |
| `CloudHammer/runs/large_cloud_context_audit_20260428/` | Legacy but valuable | Audit output for large cloud context cases. | 2026-04-28 06:59 | 5.34 MB | Not directly referenced, but useful failure-mode history. | Keep or archive later with eval/audit history. |
| `CloudHammer/runs/eval_broad_deduped_20260428_metrics.json` | Legacy but valuable | Broad-deduped eval metrics snapshot. | 2026-04-28 00:50 | ~0 MB | No direct current references found. | Keep with legacy eval history. |

## Generated / Runtime Noise

| Path | Type/category | Apparent purpose | Modified | Size | Referenced? | Recommended action |
|---|---|---|---:|---:|---|---|
| `runs/*.scan.log`, `runs/*.scan.err.log`, `runs/*.export.log`, `runs/*.export.err.log` | Generated/runtime noise | One-off scan/export command logs; many err logs are empty. | 2026-04-28 | ~0 MB | No current references found. | Move to archive later or delete after human approval. |
| `runs/kevision_webapp_5000.log` | Generated/runtime noise | Old webapp stdout log. | 2026-04-28 23:56 | ~0 MB | No current references found. | Archive/delete later. |
| `runs/kevision_webapp_5000.err.log` | Generated/runtime noise | Old webapp stderr log. | 2026-04-28 23:56 | ~0 MB | No current references found. | Archive/delete later. |
| `runs/scopeledger_webapp_5000.log` | Generated/runtime noise | Webapp stdout log. | 2026-04-30 02:15 | ~0 MB | No current references found. | Archive/delete later. |
| `runs/scopeledger_webapp_5000.err.log` | Generated/runtime noise | Webapp stderr log. | 2026-04-30 18:43 | 1.54 MB | No current references found. | Archive/delete later after checking for useful errors. |
| `tests/__pycache__/` | Generated/runtime noise | Python bytecode cache. | 2026-04-30 20:10 | 0.49 MB | No. | Clean later. |
| `CloudHammer/tests/__pycache__/` | Generated/runtime noise | Python bytecode cache. | 2026-05-02 10:23 | 0.24 MB | No. | Clean later. |
| `experiments/__pycache__/` | Generated/runtime noise | Python bytecode cache. | 2026-04-24 03:10 | 0.01 MB | No. | Clean later. |
| `CloudHammer/runs/tmp/` | Generated/runtime noise | Empty temp folder. | 2026-04-24 15:42 | 0 MB | No. | Remove later after approval. |

## Duplicate / Superseded Candidates

| Path | Type/category | Apparent purpose | Modified | Size | Referenced? | Recommended action |
|---|---|---|---:|---:|---|---|
| `runs/cloudhammer_real_export_v1/` | Duplicate/superseded | Empty/early export workspace with tiny `workspace.json`. | 2026-04-28 14:07 | 110.22 MB | No current references found. | Move to archive later or remove after preserving summary. |
| `runs/cloudhammer_real_export_v2/` | Duplicate/superseded | Early generated app workspace/export. | 2026-04-28 14:16 | 2,364.38 MB | No current references found. | Move to archive later; likely superseded by corrected split timestamped run. |
| `runs/cloudhammer_real_export_v3/` | Duplicate/superseded | Later early generated app workspace/export before corrected split. | 2026-04-28 14:24 | 2,364.72 MB | No current references found. | Move to archive later; likely superseded. |
| `runs/cloudhammer_real_export_corrected_split_v1/` | Duplicate/superseded | Non-timestamped corrected split workspace. | 2026-04-28 17:13 | 111.81 MB | No current references found. | Move to archive later if timestamped corrected split remains active. |
| `CloudHammer/runs/fragment_grouping_broad_deduped_20260428/` | Duplicate/superseded | Early grouping output. | 2026-04-28 07:05 | 136.89 MB | No current references found. | Archive later; superseded by split/split_v2 variants. |
| `CloudHammer/runs/fragment_grouping_broad_deduped_20260428_conservative/` | Duplicate/superseded | Conservative grouping variant. | 2026-04-28 07:06 | 136.91 MB | No current references found. | Archive later. |
| `CloudHammer/runs/fragment_grouping_broad_deduped_20260428_split/` | Duplicate/superseded | Split grouping variant. | 2026-04-28 07:09 | 133.34 MB | No current references found. | Archive later. |
| `CloudHammer/runs/fragment_grouping_broad_deduped_20260428_split_v2/` | Legacy latest in series | Later split grouping variant. | 2026-04-28 07:10 | 136.98 MB | No current references found. | Keep one summary, archive full artifacts later. |
| `CloudHammer/runs/fragment_grouping_fullpage_all_broad_deduped_20260428/` | Duplicate/superseded | Initial full-page all-source grouping. | 2026-04-28 07:17 | 1,343.49 MB | No direct current references found. | Archive later; likely superseded by lowconf/tuned variants. |
| `CloudHammer/runs/fragment_grouping_fullpage_all_broad_deduped_lowconf_20260428/` | Duplicate/superseded | Low-confidence grouping variant. | 2026-04-28 08:53 | 1,335.33 MB | No direct current references found. | Archive later. |
| `CloudHammer/runs/fragment_grouping_fullpage_all_broad_deduped_lowconf_tuned_20260428/` | Duplicate/superseded | Tuned low-confidence grouping variant. | 2026-04-28 12:10 | 1,336.40 MB | No direct current references found. | Archive later if lowfill tuned remains retained. |
| `CloudHammer/runs/fragment_grouping_fullpage_all_broad_deduped_lowconf_lowfill_tuned_20260428/` | Legacy latest in series | Low-confidence/low-fill tuned grouping variant. | 2026-04-28 12:15 | 1,335.39 MB | Indirectly paired with current broad candidate run. | Keep until broad candidate retention is decided. |
| `CloudHammer/runs/whole_cloud_candidates_broad_deduped_20260428/` | Duplicate/superseded | Early whole-cloud candidates. | 2026-04-28 08:46 | 1,416.37 MB | No current references found. | Archive later. |
| `CloudHammer/runs/whole_cloud_candidates_broad_deduped_lowconf_20260428/` | Duplicate/superseded | Low-confidence candidate expansion. | 2026-04-28 08:55 | 1,429.52 MB | No current references found. | Archive later. |
| `CloudHammer/runs/whole_cloud_candidates_broad_deduped_lowconf_context_20260428/` | Duplicate/superseded | Low-confidence candidates with context. | 2026-04-28 11:55 | 1,566.78 MB | No current references found. | Archive later. |
| `CloudHammer/runs/whole_cloud_candidates_broad_deduped_lowconf_tuned_20260428/` | Duplicate/superseded | Tuned low-confidence candidates. | 2026-04-28 12:13 | 1,492.93 MB | No current references found. | Archive later if lowfill tuned remains retained. |

## Unclear / Requires Human Decision

| Path | Type/category | Apparent purpose | Modified | Size | Referenced? | Recommended action |
|---|---|---|---:|---:|---|---|
| `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/conformed_preview.pdf` | Unclear / large active artifact | Large conformed preview PDF inside active demo workspace. | 2026-04-29 11:55 | ~2,358.82 MB | Not directly referenced by docs, but inside active workspace. | Human decision before moving; likely retain until demo workspace is retired. |
| `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog.xlsx` | Active deliverable artifact | Workbook referenced by meeting notes. | 2026-04-29 11:55 | 4.15 MB | Yes, meeting notes. | Keep while demo artifact is useful. |
| `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/outputs/revision_changelog_review_packet.html` | Active deliverable artifact | Review packet referenced by meeting notes. | 2026-04-30 09:45 | 0.39 MB | Yes, meeting notes. | Keep while demo artifact is useful. |
| `CloudHammer/runs/whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428/` | Unclear / huge current reference | Very large latest whole-cloud candidate set; default review queue source. | 2026-05-02 01:42 | 8,428.48 MB | Yes, `launch_review_queue.ps1`. | Needs human decision; do not move until review state is preserved and script default changes. |
| `CloudHammer/runs/fragment_grouping_fullpage_eval_broad_deduped_review_v1_20260502/` | Unclear | Eval grouping variant from 2026-05-02. | 2026-05-02 02:15 | 133.50 MB | Not directly referenced. | Human decision: keep if tied to current 14-page debug eval; otherwise archive later. |
| `CloudHammer/runs/fullpage_all_broad_deduped_20260428/` and `fullpage_all_broad_deduped_lowconf_20260428/` | Unclear because configs reference them | Large all-source detection outputs. | 2026-04-28 | 558.54 MB / 565.77 MB | Yes, legacy configs. | Do not move until configs are retired or copied into archive with paths preserved. |
| `CloudHammer/runs` tracked checkpoint/results files | Unclear / Git hygiene risk | `93` files under ignored `CloudHammer/runs/` are already tracked. | mixed | mixed | Yes, Git-tracked history. | Human decision: keep tracked, migrate to LFS, or intentionally archive/remove in a dedicated commit. |
| `experiments/extract_changelog.py` and `experiments/preview_revision_changelog.py` | Unclear | Early product/deliverable exploratory scripts. | 2026-04-24 | ~0 MB | No current references found. | Human decision after confirming no deliverable behavior only exists here. |

## Risks

- Moving root `runs/cloudhammer_real_export_corrected_split_v1_20260428_171246/`
  would break `runs/projects.json` and the current demo project registry.
- Moving root `runs/` wholesale would mix app-active workspace state with old
  generated output cleanup.
- Moving `CloudHammer/runs/whole_cloud_candidates_broad_deduped_lowconf_lowfill_tuned_20260428/`
  would break the current legacy review queue default.
- Moving recent 2026-05-02 CloudHammer eval/model runs would make it harder to
  audit the model-vs-pipeline pivot and the latest false-positive training
  history.
- `CloudHammer/runs/` is ignored but partially tracked. Cleanup here should be
  a deliberate Git hygiene task, not an incidental artifact move.
- Some archived/generated outputs are very large. Moving them inside the repo
  does not reduce disk usage; it only clarifies structure.
- Some current references are in uncommitted legacy CloudHammer configs/scripts.
  Treat them as current working-tree context until explicitly retired.

## Proposed Next Cleanup Task

Perform a narrow, approved cleanup step in this order:

1. Add an artifact-retention manifest listing the active demo workspace, recent
   2026-05-02 CloudHammer eval/model runs, and latest candidate run that must
   stay in place.
2. Archive or remove only obvious runtime noise:
   - `tests/**/__pycache__/`
   - `CloudHammer/tests/**/__pycache__/`
   - `experiments/**/__pycache__/`
   - empty `CloudHammer/runs/tmp/`
   - old root webapp/scan/export logs after preserving any useful error lines
3. Separately decide whether older root export workspaces
   `cloudhammer_real_export_v1`, `v2`, `v3`, and non-timestamped
   `corrected_split_v1` should move under `archive/generated_runs/`.
4. Defer all `CloudHammer/runs/` moves until after CloudHammer_v2 has a frozen
   real eval baseline and any needed checkpoint imports are logged.

## Commands Used

- `Get-ChildItem` for directory inventories and modified dates.
- recursive size/count summaries via PowerShell `Measure-Object`.
- `rg` for current reference searches, excluding `docs/archive/`.
- `git ls-files` to distinguish tracked vs ignored/generated areas.
- `git check-ignore` to confirm ignore rules for `runs/`, `CloudHammer/runs/`,
  and cache folders.
