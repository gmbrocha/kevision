"""Quick tabular dump of a pairs JSON for eyeballing."""

import json
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("usage: inspect_pairs.py <pairs.json>")
    raise SystemExit(1)

path = Path(sys.argv[1]).resolve()
data = json.loads(path.read_text(encoding="utf-8"))
pairs = data["pairs"]
print(f"{len(pairs)} pairs in {path.name}")
print(f"{'#':>3}  {'big_cx':>6} {'big_cy':>6} {'r_big':>5}   {'sm_cx':>6} {'sm_cy':>6} {'r_sm':>5}   {'ratio':>5} {'d/rb':>5}  {'edge':>4}")
for i, p in enumerate(pairs):
    b, s = p["big"], p["small"]
    print(
        f"{i:>3}  {b['cx']:>6.1f} {b['cy']:>6.1f} {b['r']:>5.2f}   "
        f"{s['cx']:>6.1f} {s['cy']:>6.1f} {s['r']:>5.2f}   "
        f"{p['ratio']:>5.2f} {p['dist_over_rbig']:>5.2f}  {p.get('edge_support_total', 0):>4.2f}"
    )
