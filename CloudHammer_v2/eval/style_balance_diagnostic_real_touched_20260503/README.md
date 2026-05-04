# style_balance_diagnostic_real_touched 20260503

This is a diagnostic-only touched-real review set. It is not promotion-clean.

Pages: `12`
Manifest: `F:/Desktop/m/projects/scopeLedger/CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/manifest.jsonl`
Labels: `F:/Desktop/m/projects/scopeLedger/CloudHammer_v2/eval/style_balance_diagnostic_real_touched_20260503/labels`

## Why This Exists

The strict untouched `page_disjoint_real` pool is exhausted and is plumbing-heavy. This supplement adds low-use touched pages with more architectural, electrical, mechanical, structural, and limited plumbing comparison coverage.

Use this for style and error-family diagnostics only. Do not blend its metrics with `page_disjoint_real` and do not use it for promotion claims.

## Selection Summary

- Touch total range: `2` to `6`

### Discipline Counts

- `arch`: `4`
- `electrical`: `3`
- `mechanical`: `2`
- `plumbing`: `2`
- `structural`: `1`

## Pages

| Source Page | Discipline | Touch Total | Sheet | Title | Touch Roles |
| --- | --- | ---: | --- | --- | --- |
| `Revision_1_-_Drawing_Changes:p0025` | `arch` | `2` | `AE514` | ALUMINUM WINDOW | `{"continuity_training": 2}` |
| `Revision_1_-_Drawing_Changes:p0023` | `arch` | `3` | `AE600` | INTERIOR PARTITION DETAILS | `{"continuity_training": 3}` |
| `Revision_1_-_Drawing_Changes:p0027` | `arch` | `4` | `AE612` | DOOR AND WINDOW DETAILS | `{"continuity_training": 3, "source_controlled_train_val": 1}` |
| `Revision_1_-_Drawing_Changes:p0014` | `arch` | `6` | `AE403` | SHIPPING/ | `{"continuity_training": 3, "source_controlled_train_val": 3}` |
| `260313_-_VA_Biloxi_Rev_3:p0189` | `electrical` | `2` | `E402` | PANEL SCHEDULES - ELECTRICAL | `{"continuity_training": 1, "source_controlled_train_val": 1}` |
| `260313_-_VA_Biloxi_Rev_3:p0192` | `electrical` | `2` | `EP101` | GFI | `{"continuity_training": 1, "source_controlled_train_val": 1}` |
| `260313_-_VA_Biloxi_Rev_3:p0196` | `electrical` | `2` | `E001` | SYMBOLS  LIST. | `{"continuity_training": 1, "source_controlled_train_val": 1}` |
| `Revision_1_-_Drawing_Changes:p0042` | `mechanical` | `2` | `MH302` | TRANSITION UP | `{"continuity_training": 1, "source_controlled_train_val": 1}` |
| `260313_-_VA_Biloxi_Rev_3:p0183` | `mechanical` | `6` | `MH501` | DETAILS - HVAC | `{"continuity_training": 3, "source_controlled_train_val": 3}` |
| `Revision_1_-_Drawing_Changes:p0004` | `structural` | `2` | `S140` | FOURTH FLOOR GENERAL NOTES: | `{"continuity_training": 1, "source_controlled_train_val": 1}` |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0021` | `plumbing` | `2` | `P-418` | FD-C | `{"continuity_training": 1, "source_controlled_train_val": 1}` |
| `260313_-_VA_Biloxi_Rev_3:p0175` | `plumbing` | `2` | `P-418` | EXISTING 4" SS DN | `{"continuity_training": 1, "source_controlled_train_val": 1}` |

## Review Rules

- Class: `cloud_motif`
- Draw tight boxes around visible revision cloud contours only.
- Leave true no-cloud pages empty and save/review them.
- Do not include marker triangles unless they naturally fall inside the tight cloud box.
- Keep this set diagnostic-only.

## Working Launch Command

```powershell
$imageList = Resolve-Path CloudHammer_v2\eval\style_balance_diagnostic_real_touched_20260503\images_resolved.txt
$startImage = Get-Content CloudHammer_v2\eval\style_balance_diagnostic_real_touched_20260503\images_resolved.txt -TotalCount 1
$imageDir = Split-Path -Parent $startImage
$env:LABELIMG_IMAGE_LIST = $imageList
$env:LABELIMG_START_IMAGE = $startImage
.\.venv\Scripts\python.exe .\.venv\Lib\site-packages\labelImg\labelImg.py $imageDir (Resolve-Path CloudHammer_v2\eval\style_balance_diagnostic_real_touched_20260503\labels\classes.txt) (Resolve-Path CloudHammer_v2\eval\style_balance_diagnostic_real_touched_20260503\labels)
```
