# Non-Frozen Postprocessing Diagnostic

This report is a read-only geometry diagnostic. It does not modify labels,
eval manifests, prediction files, model files, datasets, or training data.

Source candidate manifest: `F:\Desktop\m\projects\scopeLedger\CloudHammer\runs\whole_cloud_eval_symbol_text_fp_hn_20260502\whole_cloud_candidates_manifest.jsonl`
Output rows: `44`
Input candidates: `34`
Analyzed candidates: `34`
Excluded frozen-page candidates: `0`

## Diagnostic Families

- `fragment_merge_candidate`: `19`
- `duplicate_suppression_candidate`: `0`
- `overmerge_split_candidate`: `1`
- `loose_localization_candidate`: `24`

## Baseline Mismatch Context

- Reviewed mismatch rows: `77`
- Dominant reviewed buckets are fragments, duplicates, overmerges, split fragments, and localization.
- `crossing_line_x_patterns`: `4` (tracked for later hard-negative/training-family review, not the primary blocker).

## Interpretation

- `fragment_merge_candidate`: nearby or weakly overlapping candidates that may need merge review.
- `duplicate_suppression_candidate`: overlapping/contained candidates that may need duplicate suppression.
- `overmerge_split_candidate`: one candidate with separated member components that may need split review.
- `loose_localization_candidate`: one candidate whose box is materially looser than its member detections.

These are candidate rows for postprocessing diagnosis only. Do not treat them as truth labels.

## Top Rows

- `loose_localization_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0000_whole_001` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0000`: Candidate bbox is materially larger than the tight box around its member detections.
- `fragment_merge_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_001, 260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_006` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate boxes are adjacent or weakly overlapping and may be fragments of one cloud.
- `fragment_merge_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_001, 260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_007` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate boxes are adjacent or weakly overlapping and may be fragments of one cloud.
- `fragment_merge_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_001, 260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_008` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate boxes are adjacent or weakly overlapping and may be fragments of one cloud.
- `fragment_merge_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_002, 260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_003` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate boxes are adjacent or weakly overlapping and may be fragments of one cloud.
- `fragment_merge_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_003, 260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_004` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate boxes are adjacent or weakly overlapping and may be fragments of one cloud.
- `fragment_merge_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_004, 260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_005` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate boxes are adjacent or weakly overlapping and may be fragments of one cloud.
- `fragment_merge_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_007, 260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_008` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate boxes are adjacent or weakly overlapping and may be fragments of one cloud.
- `overmerge_split_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_001` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: One candidate contains multiple separated member-box components.
- `loose_localization_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_001` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate bbox is materially larger than the tight box around its member detections.
- `loose_localization_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_002` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate bbox is materially larger than the tight box around its member detections.
- `loose_localization_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_003` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate bbox is materially larger than the tight box around its member detections.
- `loose_localization_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_004` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate bbox is materially larger than the tight box around its member detections.
- `loose_localization_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_005` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate bbox is materially larger than the tight box around its member detections.
- `loose_localization_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_006` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate bbox is materially larger than the tight box around its member detections.
- `loose_localization_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_007` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate bbox is materially larger than the tight box around its member detections.
- `loose_localization_candidate` `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137_p0001_whole_008` on `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`: Candidate bbox is materially larger than the tight box around its member detections.
- `fragment_merge_candidate` `260303-VA_Biloxi_Rev_5_RFI-126_56f520d9_p0002_whole_001, 260303-VA_Biloxi_Rev_5_RFI-126_56f520d9_p0002_whole_002` on `260303-VA_Biloxi_Rev_5_RFI-126:p0002`: Candidate boxes are adjacent or weakly overlapping and may be fragments of one cloud.
- `fragment_merge_candidate` `260303-VA_Biloxi_Rev_5_RFI-126_56f520d9_p0002_whole_001, 260303-VA_Biloxi_Rev_5_RFI-126_56f520d9_p0002_whole_005` on `260303-VA_Biloxi_Rev_5_RFI-126:p0002`: Candidate boxes are adjacent or weakly overlapping and may be fragments of one cloud.
- `fragment_merge_candidate` `260303-VA_Biloxi_Rev_5_RFI-126_56f520d9_p0002_whole_002, 260303-VA_Biloxi_Rev_5_RFI-126_56f520d9_p0002_whole_004` on `260303-VA_Biloxi_Rev_5_RFI-126:p0002`: Candidate boxes are adjacent or weakly overlapping and may be fragments of one cloud.
