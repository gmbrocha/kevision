# CloudHammer_v2 Import Log

Use this file to track anything copied, adapted, or conceptually imported from
legacy `CloudHammer/`.

Do not import old code until the relevant behavior has been audited.

## Template

```markdown
## YYYY-MM-DD - Import Title

- Date:
- Imported from old path:
- Imported to new path:
- Reason:
- Modified or copied unchanged:
- Dependencies:
- Notes:
- Follow-up tests:
```

## Entries

## 2026-05-02 - Source/Page Registry Helpers

- Date: 2026-05-02
- Imported from old path: `CloudHammer/cloudhammer/data/source_control.py`
- Imported to new path: `CloudHammer_v2/scripts/build_touched_page_registry.py`
- Reason: normalize source/page keys, detect touched pages, and freeze
  `page_disjoint_real`
- Modified or copied unchanged: adapted conceptually into a standalone v2 script
- Dependencies: Python standard library only
- Notes: strips raster hash suffixes so page manifests and crop manifests map to
  the same source-page key
- Follow-up tests: `py_compile`; registry dry run completed with zero unknown
  touch rows

## 2026-05-02 - GPT Full-Page Labeling Flow

- Date: 2026-05-02
- Imported from old path: `CloudHammer/cloudhammer/prelabel/openai_clouds.py`
- Imported to new path: `CloudHammer_v2/scripts/generate_gpt_fullpage_labels.py`
- Reason: originally generated GPT-provisional full-page labels for frozen eval
  pages; later corrected to scratch-only for `page_disjoint_real`
- Modified or copied unchanged: adapted conceptually from crop prelabeling to
  full-page eval labeling
- Dependencies: OpenAI Python SDK, PIL
- Notes: corrected later on 2026-05-02. `page_disjoint_real` should be
  human-reviewed directly; GPT full-page outputs are scratch/provisional only,
  and GPT-5.5 full-page outputs are marked do-not-score.
- Follow-up tests: `py_compile`; dry run and 17-page GPT pass completed

## 2026-05-02 - GPT-5.5 Cropped Supplement Prelabel Run

- Date: 2026-05-02
- Imported from old path: `CloudHammer/scripts/prelabel_cloud_rois_openai.py`
- Imported to new path: not copied; executed in place with
  `CloudHammer_v2/configs/gpt55_crop_prelabel_small_corpus_supplement_20260502.yaml`
- Reason: prelabel cropped training/review candidates, not frozen eval pages
- Modified or copied unchanged: legacy script executed unchanged; v2 config added
- Dependencies: legacy `CloudHammer/cloudhammer/prelabel/openai_clouds.py`,
  OpenAI Python SDK, PIL
- Notes: source manifest
  `CloudHammer/data/review_batches/small_corpus_expansion_supplement_20260502/prelabel_manifest.jsonl`;
  outputs under
  `CloudHammer_v2/data/gpt55_crop_prelabels_small_corpus_supplement_20260502/`;
  label status `gpt_provisional`
- Follow-up tests: 150 processed, 0 skipped, 0 failed; 49 nonempty provisional
  label files, 101 empty provisional label files

## 2026-05-02 - Audited Legacy Baseline Execution

- Date: 2026-05-02
- Imported from old path:
  `CloudHammer/scripts/infer_pages.py`,
  `CloudHammer/scripts/group_fragment_detections.py`,
  `CloudHammer/scripts/export_whole_cloud_candidates.py`
- Imported to new path: not copied; executed in place as audited legacy behavior
- Reason: run first `model_only_tiled` and `pipeline_full` baselines without
  prematurely importing legacy code
- Modified or copied unchanged: executed unchanged
- Dependencies: legacy `CloudHammer/cloudhammer/*`, Ultralytics, cv2
- Notes: outputs were written under `CloudHammer_v2/outputs/`
- Follow-up tests: baseline eval completed and scored with
  `CloudHammer_v2/scripts/evaluate_fullpage_detections.py`

## 2026-05-05 - GPT Postprocessing Review Prefill Flow

- Date: 2026-05-05
- Imported from old path:
  `CloudHammer/cloudhammer/prelabel/openai_clouds.py` and
  `CloudHammer_v2/scripts/generate_gpt_fullpage_labels.py`
- Imported to new path:
  `CloudHammer_v2/scripts/prefill_postprocessing_review_gpt.py`
- Reason: prefill non-frozen postprocessing diagnostic review metadata with
  GPT-5.5 suggestions before human confirmation.
- Modified or copied unchanged: adapted conceptually into a purpose-specific v2
  script that writes review CSV/JSONL metadata, not YOLO labels.
- Dependencies: OpenAI Python SDK, PIL
- Notes: outputs stay under
  `CloudHammer_v2/outputs/postprocessing_diagnostic_non_frozen_20260504/` and
  are provisional review metadata only.
- Follow-up tests: `py_compile`, dry-run overlay generation, one-row GPT probe,
  full 44-row GPT-5.5 run, and companion reviewer syntax check completed.
