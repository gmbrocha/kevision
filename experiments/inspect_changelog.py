"""Quick inspection of Kevin's mod_5_changelog.xlsx."""
import openpyxl
from pathlib import Path

XLSX = Path(r"F:\Desktop\m\projects\drawing_revision\mod_5_changelog.xlsx")

wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb["Sheet1"]

print("Images in sheet:", len(ws._images))
for i, img in enumerate(ws._images):
    a = img.anchor
    try:
        frm = a._from
        to = getattr(a, "to", None)
        frm_str = f"col={frm.col} row={frm.row}"
        to_str = f"col={to.col} row={to.row}" if to else "?"
    except Exception as e:
        frm_str, to_str = repr(a), str(e)
    print(f"  img{i}: from={frm_str} to={to_str}")

print()
print("Merged cells (first 40):")
for mr in list(ws.merged_cells.ranges)[:40]:
    print(" ", mr)

print()
print("--- Non-empty rows ---")
for row in ws.iter_rows(values_only=False):
    vals = [c.value for c in row]
    if any(v is not None and str(v).strip() for v in vals):
        coord = row[0].row
        rendered = " | ".join(
            f"{chr(65+i)}={repr(v)[:120]}" for i, v in enumerate(vals) if v is not None
        )
        print(f"R{coord}: {rendered}")
