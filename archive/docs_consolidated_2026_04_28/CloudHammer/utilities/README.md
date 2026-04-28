# CloudHammer Utilities

## Large Cloud Context Labeler

Launch:

```powershell
cd F:\Desktop\m\projects\kevision\CloudHammer
..\.venv\Scripts\python.exe utilities\large_cloud_context_labeler.py --manifest data\manifests\pages_standard_drawings_no_index_20260427.jsonl
```

Default outputs:

- sidecar JSON:
  `CloudHammer/data/large_cloud_context_labels/*.largecloud.json`
- exported region crops:
  `CloudHammer/data/large_cloud_context_crops/*.png`

Controls:

- `B`: draw whole-cloud label boxes in the active region
- `R`: draw the active region context crop; crop boxes are squared automatically
- `A`: auto-create a square crop around the active region's labels
- `Ctrl+R`: create a new region on the same page
- `Delete`: remove the selected label box or crop box
- `Ctrl+Delete`: remove the active region
- `Ctrl+S`: save
- `Ctrl+N`: save and advance to the next page
- `N` / `P`: next / previous page
- `F`: fit page to window
- mouse wheel: zoom
- right or middle mouse drag: pan
- `H`: show in-app help

Recommended workflow:

1. Start in label mode (`B`) and drag one or more boxes around whole visible
   clouds in the active region.
2. Press `A` to auto-create the square context crop around those label boxes.
3. Press `Ctrl+S` to save, or `Ctrl+N` to save and advance.
4. Use `Ctrl+R` before labeling when the same page has another unrelated large
   cloud that should become a separate context crop.

Each region stores one context crop plus zero or more whole-cloud label boxes in
source rendered-page pixel coordinates. When a crop is present, the utility also
exports the cropped image and writes crop-local label coordinates into the
sidecar JSON.
