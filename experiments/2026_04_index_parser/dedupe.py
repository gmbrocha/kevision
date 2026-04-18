"""Dedupe per-revision CSVs into a single "current final revision" view.

For each sheet, keeps the row from the latest revision that touched it
(by revision_date). Adds a `revision_history` column listing every revision
that touched the sheet, oldest first.

Usage:
    python dedupe.py <csv1> [<csv2> ...] -o <output.csv>

Example:
    python dedupe.py \
        output/260309*__revision_1.csv \
        output/260309*__revision_2.csv \
        -o output/Rev2_final_current_state.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_date(value: str) -> tuple[int, int, int]:
    try:
        d = datetime.strptime((value or "").strip(), "%m/%d/%Y")
        return (d.year, d.month, d.day)
    except ValueError:
        return (0, 0, 0)


def expand_inputs(raw_inputs: list[str]) -> list[Path]:
    """Expand glob patterns since some shells (PowerShell) don't auto-glob."""
    out: list[Path] = []
    for token in raw_inputs:
        matches = glob.glob(token)
        if matches:
            out.extend(Path(m) for m in matches)
        else:
            out.append(Path(token))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Dedupe revision CSVs into one current-state view.")
    parser.add_argument("inputs", nargs="+", help="Input CSV paths (glob patterns allowed)")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output CSV path")
    args = parser.parse_args()

    input_paths = expand_inputs(args.inputs)
    missing = [p for p in input_paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"  not found: {p}")
        return 1

    all_rows: list[dict] = []
    fieldnames_in: list[str] = []
    for path in input_paths:
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames and not fieldnames_in:
                fieldnames_in = list(reader.fieldnames)
            for row in reader:
                row["_source_csv"] = path.name
                all_rows.append(row)

    if not all_rows:
        print("No rows to dedupe.")
        return 1

    # Group by sheet_number; for each, sort by date asc and pick the latest.
    by_sheet: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows:
        sheet = (row.get("sheet_number") or "").strip()
        if not sheet:
            continue
        by_sheet[sheet].append(row)

    out_rows: list[dict] = []
    for sheet, rows in by_sheet.items():
        rows_sorted = sorted(rows, key=lambda r: parse_date(r.get("revision_date", "")))
        history_parts = []
        seen_keys: set[tuple[str, str]] = set()
        for r in rows_sorted:
            key = (r.get("revision_label", ""), r.get("revision_date", ""))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            history_parts.append(f"{key[0]} ({key[1]})" if key[1] else key[0])
        latest = rows_sorted[-1]
        out_row = {k: latest.get(k, "") for k in fieldnames_in}
        out_row["revision_history"] = " -> ".join(history_parts)
        out_row["revision_count"] = str(len({(r.get("revision_label",""), r.get("revision_date","")) for r in rows_sorted}))
        out_rows.append(out_row)

    def sort_key(r: dict) -> tuple:
        rn = (r.get("row_number") or "").strip()
        try:
            return (0, int(rn), r.get("sheet_number", ""))
        except ValueError:
            return (1, 0, r.get("sheet_number", ""))

    out_rows.sort(key=sort_key)

    fieldnames_out = fieldnames_in + ["revision_count", "revision_history"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames_out)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {len(out_rows)} unique sheets to {args.output}")
    print(f"  inputs: {len(input_paths)} CSVs, {len(all_rows)} total rows in")
    multi_rev = sum(1 for r in out_rows if int(r["revision_count"]) > 1)
    print(f"  sheets touched by >1 revision: {multi_rev}")
    print(f"  first 8:")
    for r in out_rows[:8]:
        print(f"    row={r.get('row_number',''):>3}  {r.get('sheet_number',''):<10}  "
              f"latest={r.get('revision_label','')}  history='{r.get('revision_history','')}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
