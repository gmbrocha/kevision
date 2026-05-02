# CloudHammer Source Audit

- Rows: 931
- Source families: 12
- Source pages: 157
- Mixed train/val/test source families: 6
- Mixed train/val/test source pages: 47
- Eval rows: 14
- Eval source-family overlap with training rows: 6
- Eval source-page overlap with training rows: 12

## Revision Concentration

| Key | Rows |
| --- | ---: |
| `Revision #1 - Drawing Changes` | 613 |
| `Revision #2 - Mod 5 grab bar supports` | 129 |
| `Revision #3 - EHRM Drawings` | 105 |
| `Revision #4 - Dental Air` | 54 |
| `Revision #5 - RFI 126 - Concrete Repairs` | 15 |
| `Revision #7 - RFI 141 - Deteriorated Attic Wood` | 15 |

## Top Source Families

| Key | Rows |
| --- | ---: |
| `Revision_1_-_Drawing_Changes_6cbee960` | 545 |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3` | 86 |
| `Revision_1_-_Drawing_Changes` | 68 |
| `260313_-_VA_Biloxi_Rev_3_ff19da68` | 59 |
| `260313_-_VA_Biloxi_Rev_3` | 46 |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars` | 38 |
| `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137` | 28 |
| `260219_-_VA_Biloxi_Rev_4_Plumbing_1` | 26 |
| `260303-VA_Biloxi_Rev_5_RFI-126` | 15 |
| `Revision_Set_7` | 15 |
| `Drawing_Rev2-_Steel_Grab_Bars_R1_AE107.1_9b6a81f4` | 4 |
| `Drawing_Rev2-_Steel_Grab_Bars_AE107_e23b5995` | 1 |

## Top Source Pages

| Key | Rows |
| --- | ---: |
| `Revision_1_-_Drawing_Changes_6cbee960:p0029` | 57 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0017` | 46 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0030` | 37 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0028` | 36 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0024` | 32 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0018` | 31 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0031` | 29 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0011` | 25 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0007` | 21 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0012` | 21 |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0012` | 18 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0048` | 18 |
| `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0004` | 16 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0010` | 16 |
| `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137:p0004` | 15 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0040` | 15 |
| `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137:p0001` | 13 |
| `Revision_1_-_Drawing_Changes_6cbee960:p0019` | 13 |
| `Revision_Set_7:p0003` | 12 |
| `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0004` | 12 |

## Split Leakage: Source Families

- `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137`: {'train': 23, 'val': 5}
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3`: {'train': 71, 'val': 15}
- `260313_-_VA_Biloxi_Rev_3_ff19da68`: {'train': 56, 'val': 3}
- `Drawing_Rev2-_Steel_Grab_Bars_R1_AE107.1_9b6a81f4`: {'train': 3, 'val': 1}
- `Revision_1_-_Drawing_Changes`: {'train': 23, 'val': 45}
- `Revision_1_-_Drawing_Changes_6cbee960`: {'train': 424, 'val': 121}

## Split Leakage: Source Pages

- `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137:p0001`: {'train': 11, 'val': 2}
- `260219_-_VA_Biloxi_Rev_4_Plumbing_1_bed93137:p0004`: {'train': 12, 'val': 3}
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0004`: {'train': 15, 'val': 1}
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0008`: {'train': 1, 'val': 1}
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0009`: {'train': 4, 'val': 2}
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0011`: {'train': 5, 'val': 1}
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0012`: {'train': 16, 'val': 2}
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0013`: {'train': 5, 'val': 2}
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0016`: {'train': 3, 'val': 1}
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0017`: {'train': 3, 'val': 2}
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0018`: {'train': 1, 'val': 2}
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars_75d983f3:p0023`: {'train': 2, 'val': 1}
- `260313_-_VA_Biloxi_Rev_3_ff19da68:p0177`: {'train': 4, 'val': 2}
- `260313_-_VA_Biloxi_Rev_3_ff19da68:p0180`: {'train': 10, 'val': 1}
- `Drawing_Rev2-_Steel_Grab_Bars_R1_AE107.1_9b6a81f4:p0000`: {'train': 3, 'val': 1}
- `Revision_1_-_Drawing_Changes_6cbee960:p0001`: {'train': 10, 'val': 1}
- `Revision_1_-_Drawing_Changes_6cbee960:p0005`: {'train': 2, 'val': 1}
- `Revision_1_-_Drawing_Changes_6cbee960:p0007`: {'train': 18, 'val': 3}
- `Revision_1_-_Drawing_Changes_6cbee960:p0009`: {'train': 3, 'val': 1}
- `Revision_1_-_Drawing_Changes_6cbee960:p0010`: {'train': 14, 'val': 2}
- `Revision_1_-_Drawing_Changes_6cbee960:p0011`: {'train': 18, 'val': 7}
- `Revision_1_-_Drawing_Changes_6cbee960:p0012`: {'train': 17, 'val': 4}
- `Revision_1_-_Drawing_Changes_6cbee960:p0013`: {'train': 2, 'val': 4}
- `Revision_1_-_Drawing_Changes_6cbee960:p0015`: {'train': 4, 'val': 1}
- `Revision_1_-_Drawing_Changes_6cbee960:p0017`: {'train': 37, 'val': 9}
- `Revision_1_-_Drawing_Changes_6cbee960:p0018`: {'train': 27, 'val': 4}
- `Revision_1_-_Drawing_Changes_6cbee960:p0019`: {'train': 9, 'val': 4}
- `Revision_1_-_Drawing_Changes_6cbee960:p0020`: {'train': 2, 'val': 3}
- `Revision_1_-_Drawing_Changes_6cbee960:p0021`: {'train': 4, 'val': 1}
- `Revision_1_-_Drawing_Changes_6cbee960:p0022`: {'train': 6, 'val': 2}
- `Revision_1_-_Drawing_Changes_6cbee960:p0024`: {'train': 24, 'val': 8}
- `Revision_1_-_Drawing_Changes_6cbee960:p0026`: {'train': 8, 'val': 1}
- `Revision_1_-_Drawing_Changes_6cbee960:p0028`: {'train': 29, 'val': 7}
- `Revision_1_-_Drawing_Changes_6cbee960:p0029`: {'train': 42, 'val': 15}
- `Revision_1_-_Drawing_Changes_6cbee960:p0030`: {'train': 25, 'val': 12}
- `Revision_1_-_Drawing_Changes_6cbee960:p0031`: {'train': 25, 'val': 4}
- `Revision_1_-_Drawing_Changes_6cbee960:p0035`: {'train': 8, 'val': 3}
- `Revision_1_-_Drawing_Changes_6cbee960:p0038`: {'train': 7, 'val': 1}
- `Revision_1_-_Drawing_Changes_6cbee960:p0039`: {'train': 5, 'val': 2}
- `Revision_1_-_Drawing_Changes_6cbee960:p0040`: {'train': 12, 'val': 3}
- `Revision_1_-_Drawing_Changes_6cbee960:p0043`: {'train': 5, 'val': 2}
- `Revision_1_-_Drawing_Changes_6cbee960:p0044`: {'train': 2, 'val': 2}
- `Revision_1_-_Drawing_Changes_6cbee960:p0045`: {'train': 9, 'val': 2}
- `Revision_1_-_Drawing_Changes_6cbee960:p0046`: {'train': 6, 'val': 2}
- `Revision_1_-_Drawing_Changes_6cbee960:p0048`: {'train': 14, 'val': 4}
- `Revision_1_-_Drawing_Changes_6cbee960:p0049`: {'train': 5, 'val': 2}
- `Revision_1_-_Drawing_Changes_6cbee960:p0050`: {'train': 3, 'val': 4}

## Eval Source-Page Overlap

- `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0000`
- `260219_-_VA_Biloxi_Rev_4_Plumbing_1:p0001`
- `260303-VA_Biloxi_Rev_5_RFI-126:p0002`
- `260303-VA_Biloxi_Rev_5_RFI-126:p0003`
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0004`
- `260309_-_Drawing_Rev2-_Steel_Grab_Bars:p0005`
- `260313_-_VA_Biloxi_Rev_3:p0172`
- `260313_-_VA_Biloxi_Rev_3:p0173`
- `Revision_1_-_Drawing_Changes:p0001`
- `Revision_1_-_Drawing_Changes:p0002`
- `Revision_Set_7:p0002`
- `Revision_Set_7:p0003`
