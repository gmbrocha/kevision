# Whole Cloud Candidate Review Analysis

Manifest: `F:\Desktop\m\projects\scopeLedger\CloudHammer\runs\whole_cloud_eval_marker_fp_hn_20260502\whole_cloud_candidates_manifest.jsonl`
Review log: `F:\Desktop\m\projects\scopeLedger\CloudHammer\data\whole_cloud_candidate_reviews\whole_cloud_eval_marker_fp_hn_20260502.review.jsonl`

## Totals

- total candidates: `38`
- reviewed candidates: `38`
- accepted candidates: `21`
- rejected/issue candidates: `17`
- overall accept rate: `55.3%`

## Status Counts

| Status | Count |
| --- | ---: |
| `accept` | `21` |
| `false_positive` | `9` |
| `partial` | `6` |
| `overmerged` | `2` |

## By Confidence Tier

| confidence_tier | Total | Accept | Non-Accept | Accept Rate | Statuses |
| --- | ---: | ---: | ---: | ---: | --- |
| `high` | `29` | `21` | `8` | `72.4%` | `{"accept": 21, "false_positive": 4, "overmerged": 2, "partial": 2}` |
| `medium` | `8` | `0` | `8` | `0.0%` | `{"false_positive": 4, "partial": 4}` |
| `low` | `1` | `0` | `1` | `0.0%` | `{"false_positive": 1}` |

## By Size Bucket

| size_bucket | Total | Accept | Non-Accept | Accept Rate | Statuses |
| --- | ---: | ---: | ---: | ---: | --- |
| `small` | `16` | `11` | `5` | `68.8%` | `{"accept": 11, "false_positive": 4, "overmerged": 1}` |
| `medium` | `14` | `7` | `7` | `50.0%` | `{"accept": 7, "false_positive": 4, "partial": 3}` |
| `large` | `8` | `3` | `5` | `37.5%` | `{"accept": 3, "false_positive": 1, "overmerged": 1, "partial": 3}` |

## By Member Count

| member_count | Total | Accept | Non-Accept | Accept Rate | Statuses |
| --- | ---: | ---: | ---: | ---: | --- |
| `1` | `16` | `7` | `9` | `43.8%` | `{"accept": 7, "false_positive": 6, "overmerged": 1, "partial": 2}` |
| `2` | `10` | `7` | `3` | `70.0%` | `{"accept": 7, "false_positive": 1, "partial": 2}` |
| `3` | `6` | `3` | `3` | `50.0%` | `{"accept": 3, "false_positive": 1, "partial": 2}` |
| `7` | `2` | `1` | `1` | `50.0%` | `{"accept": 1, "overmerged": 1}` |
| `11` | `1` | `1` | `0` | `100.0%` | `{"accept": 1}` |
| `12` | `1` | `1` | `0` | `100.0%` | `{"accept": 1}` |
| `4` | `1` | `1` | `0` | `100.0%` | `{"accept": 1}` |
| `6` | `1` | `0` | `1` | `0.0%` | `{"false_positive": 1}` |

## By False Positive Reason

| false_positive_reason | Total | Accept | Non-Accept | Accept Rate | Statuses |
| --- | ---: | ---: | ---: | ---: | --- |
| `circular_symbol_fixture` | `5` | `0` | `5` | `0.0%` | `{"false_positive": 5}` |
| `text_glyph_arcs` | `4` | `0` | `4` | `0.0%` | `{"false_positive": 4}` |

## By Accept Reason

| accept_reason | Total | Accept | Non-Accept | Accept Rate | Statuses |
| --- | ---: | ---: | ---: | ---: | --- |
| `None` | `21` | `21` | `0` | `100.0%` | `{"accept": 21}` |

## Confidence Bins

| Confidence | Total | Accept | Non-Accept | Accept Rate | Statuses |
| --- | ---: | ---: | ---: | ---: | --- |
| `0.50-0.65` | `1` | `0` | `1` | `0.0%` | `{"false_positive": 1}` |
| `0.65-0.80` | `7` | `0` | `7` | `0.0%` | `{"false_positive": 4, "partial": 3}` |
| `0.80-0.90` | `10` | `5` | `5` | `50.0%` | `{"accept": 5, "false_positive": 3, "overmerged": 1, "partial": 1}` |
| `0.90-0.97` | `11` | `10` | `1` | `90.9%` | `{"accept": 10, "false_positive": 1}` |
| `0.97-1.01` | `9` | `6` | `3` | `66.7%` | `{"accept": 6, "overmerged": 1, "partial": 2}` |

## Output Manifests

- `reviewed_candidates.jsonl`: all candidates with latest review status attached
- `accepted_candidates.jsonl`: candidates marked `accept`
- `false_positive_candidates.jsonl`: candidates marked `false_positive`
- `overmerged_candidates.jsonl`: candidates marked `overmerged`
- `partial_candidates.jsonl`: candidates marked `partial`
- `issue_candidates.jsonl`: all non-accept reviewed candidates
