"""Extract everything useful from Kevin's mod_5_changelog.xlsx.

- Full text of every non-empty cell, with merge info.
- Embedded images dumped to disk (for visual reference of what crops he pairs with each row).
"""
import openpyxl
import zipfile
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
XLSX = REPO_ROOT / "docs" / "anchors" / "mod_5_changelog.xlsx"
OUT = REPO_ROOT / "experiments" / "mod_5_changelog_dump"
OUT.mkdir(parents=True, exist_ok=True)

# 1. Pull out embedded images directly from the .xlsx zip (cleanest way).
img_dir = OUT / "images"
img_dir.mkdir(exist_ok=True)
with zipfile.ZipFile(XLSX) as z:
    for name in z.namelist():
        if name.startswith("xl/media/"):
            target = img_dir / Path(name).name
            with z.open(name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            print(f"extracted {name} -> {target}")

# 2. Map images to anchored rows so we know which crop belongs to which row group.
wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb["Sheet1"]

print("\nImage anchors (1-based row/col for sanity):")
for i, img in enumerate(ws._images):
    frm = img.anchor._from
    to = getattr(img.anchor, "to", None)
    frm_str = f"row={frm.row+1} col={chr(65+frm.col)}"
    to_str = f"row={to.row+1} col={chr(65+to.col)}" if to else "?"
    print(f"  img{i}: from {frm_str}  to {to_str}")

# 3. Dump full unfiltered cell text (no truncation) for non-empty rows.
print("\n=== FULL TEXT DUMP ===")
out_lines = []
for row in ws.iter_rows(values_only=False):
    vals = [(c.coordinate, c.value) for c in row]
    if any(v is not None and str(v).strip() for _, v in vals):
        out_lines.append(f"--- row {row[0].row} ---")
        for coord, v in vals:
            if v is not None and str(v).strip():
                out_lines.append(f"  {coord}: {v!r}")
out_text = "\n".join(out_lines)
print(out_text)
(OUT / "text_dump.txt").write_text(out_text, encoding="utf-8")
print(f"\nWrote {OUT / 'text_dump.txt'}")
