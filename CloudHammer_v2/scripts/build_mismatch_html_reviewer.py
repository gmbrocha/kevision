from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
DEFAULT_PACKET_DIR = (
    V2_ROOT / "outputs" / "baseline_human_audited_mismatch_review_20260504" / "overlay_packet"
)

APPROVED_ERROR_BUCKETS = [
    "",
    "marker_neighborhood_no_cloud_regions",
    "historical_or_nonmatching_revision_marker_context",
    "isolated_arcs_and_scallop_fragments",
    "fixture_circles_and_symbol_circles",
    "glyph_text_arcs",
    "crossing_line_x_patterns",
    "index_table_x_marks",
    "dense_linework_near_valid_clouds",
    "thick_dark_cloud_false_positive_context",
    "thin_light_cloud_low_contrast_miss",
    "no_cloud_dense_dark_linework",
    "no_cloud_door_swing_arc_false_positive_trap",
    "mixed_cloud_with_dense_false_positive_regions",
    "overmerged_grouping",
    "split_fragment",
    "localization_too_loose",
    "localization_too_tight",
    "truth_needs_recheck",
    "other",
]

REVIEW_STATUSES = ["unreviewed", "bucketed", "needs_second_look", "truth_needs_recheck", "not_actionable"]

Image.MAX_IMAGE_PIXELS = None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_csv_by_id(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["review_item_id"]: row for row in csv.DictReader(handle)}


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.replace(":", "_")).strip("_")


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def html_relative(path: Path, base_dir: Path) -> str:
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def box_from_row(row: dict[str, Any]) -> list[float] | None:
    box = row.get("bbox_xyxy")
    if isinstance(box, list) and len(box) == 4:
        return [float(value) for value in box]
    return None


def truth_box_from_row(row: dict[str, Any]) -> list[float] | None:
    box = row.get("truth_bbox_xyxy")
    if isinstance(box, list) and len(box) == 4:
        return [float(value) for value in box]
    return None


def union_box(boxes: list[list[float]]) -> list[float]:
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def padded_crop_box(
    box: list[float],
    image_size: tuple[int, int],
    padding: int,
    min_side: int,
    max_side: int,
) -> tuple[int, int, int, int]:
    width, height = image_size
    cx = (box[0] + box[2]) / 2.0
    cy = (box[1] + box[3]) / 2.0
    crop_w = max(min_side, (box[2] - box[0]) + padding * 2)
    crop_h = max(min_side, (box[3] - box[1]) + padding * 2)
    crop_w = min(crop_w, max_side, width)
    crop_h = min(crop_h, max_side, height)
    x1 = max(0, min(width - crop_w, cx - crop_w / 2.0))
    y1 = max(0, min(height - crop_h, cy - crop_h / 2.0))
    x2 = min(width, x1 + crop_w)
    y2 = min(height, y1 + crop_h)
    return int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))


def translate_box(box: list[float], crop_box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, _, _ = crop_box
    return (
        int(round(box[0] - x1)),
        int(round(box[1] - y1)),
        int(round(box[2] - x1)),
        int(round(box[3] - y1)),
    )


def draw_label(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, color: str) -> None:
    text_width = max(70, len(text) * 8)
    draw.rectangle((x, max(0, y - 18), x + text_width, max(16, y)), fill="white")
    draw.text((x + 3, max(1, y - 16)), text, fill=color)


def draw_box(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], color: str, width: int, text: str) -> None:
    draw.rectangle(box, outline=color, width=width)
    draw_label(draw, text, box[0] + 4, box[1], color)


def row_colors(row: dict[str, Any]) -> tuple[str | None, str | None, str, str]:
    mismatch_type = str(row.get("mismatch_type") or "")
    best_iou = float(row.get("best_iou") or 0.0)
    if mismatch_type == "false_negative":
        return "orange", None, "missed truth", ""
    if mismatch_type == "localization_low_iou":
        pred_color = "purple" if best_iou >= 0.25 else "red"
        return "lime", pred_color, "matched truth", "low-IoU prediction"
    if mismatch_type == "false_positive":
        return "lime" if best_iou >= 0.25 else None, "red", "nearest truth", "false positive"
    return "lime", "red", "truth", "prediction"


def make_review_crop(
    row: dict[str, Any],
    output_path: Path,
    html_base_dir: Path,
    mode: str,
    padding: int,
    min_side: int,
    max_side: int,
) -> dict[str, Any]:
    render_path = Path(str(row["render_path"]))
    issue_box = box_from_row(row)
    truth_box = truth_box_from_row(row)
    boxes = [box for box in (issue_box, truth_box) if box is not None]
    if not boxes:
        raise ValueError(f"row has no drawable boxes: {row.get('review_item_id')}")
    focus_box = union_box(boxes)
    with Image.open(render_path) as image:
        image = image.convert("RGB")
        crop_box = padded_crop_box(focus_box, image.size, padding=padding, min_side=min_side, max_side=max_side)
        crop = image.crop(crop_box)
    draw = ImageDraw.Draw(crop)
    truth_color, pred_color, truth_label, pred_label = row_colors(row)
    line_width = 5 if mode == "local" else 4
    if truth_box is not None and truth_color:
        draw_box(draw, translate_box(truth_box, crop_box), truth_color, line_width, truth_label)
    if issue_box is not None and pred_color:
        pred_text = pred_label
        confidence = row.get("confidence")
        best_iou = row.get("best_iou")
        if confidence not in (None, ""):
            pred_text += f" conf {float(confidence):.2f}"
        if best_iou not in (None, ""):
            pred_text += f" IoU {float(best_iou):.2f}"
        draw_box(draw, translate_box(issue_box, crop_box), pred_color, line_width, pred_text)
    title = f"{row.get('eval_mode')} | {row.get('mismatch_type')} | {row.get('source_page_key')}"
    draw.rectangle((0, 0, min(crop.width, len(title) * 8 + 20), 26), fill="white")
    draw.text((8, 7), title, fill="black")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(output_path)
    return {
        "path": html_relative(output_path, html_base_dir),
        "crop_box": crop_box,
        "width": crop.width,
        "height": crop.height,
    }


def csv_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    if any(char in text for char in [",", '"', "\n", "\r"]):
        return '"' + text.replace('"', '""') + '"'
    return text


def html_document(items_json: str, buckets_json: str, statuses_json: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>CloudHammer Mismatch Reviewer</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f5f5f2; color: #1e1e1c; }}
    header {{ display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: #202124; color: white; position: sticky; top: 0; z-index: 10; }}
    button, select, textarea, input {{ font: inherit; }}
    button {{ border: 1px solid #888; background: white; padding: 6px 10px; cursor: pointer; }}
    button.primary {{ background: #2457d6; color: white; border-color: #2457d6; }}
    main {{ display: grid; grid-template-columns: minmax(360px, 1fr) 380px; gap: 12px; padding: 12px; }}
    .viewer {{ background: white; border: 1px solid #d0d0ca; padding: 10px; min-width: 0; }}
    .panel {{ background: white; border: 1px solid #d0d0ca; padding: 12px; }}
    .meta {{ display: grid; grid-template-columns: 120px 1fr; gap: 4px 8px; font-size: 13px; margin-bottom: 10px; }}
    .meta div:nth-child(odd) {{ color: #595954; }}
    .crop-wrap {{ overflow: auto; max-height: calc(100vh - 180px); border: 1px solid #ccc; background: #111; }}
    img {{ image-rendering: auto; max-width: none; display: block; }}
    .tabs {{ display: flex; gap: 8px; margin-bottom: 8px; }}
    .tabs button.active {{ background: #222; color: white; }}
    label {{ display: block; margin-top: 10px; font-weight: 700; font-size: 13px; }}
    select, textarea {{ width: 100%; box-sizing: border-box; margin-top: 4px; }}
    textarea {{ min-height: 120px; resize: vertical; }}
    .legend span {{ display: inline-block; margin: 3px 8px 3px 0; }}
    .swatch {{ width: 12px; height: 12px; border: 1px solid #333; vertical-align: -2px; }}
    .statusline {{ margin-left: auto; font-size: 13px; color: #ddd; }}
    .small {{ font-size: 12px; color: #555; }}
    .rowlist {{ max-height: 180px; overflow: auto; border: 1px solid #ddd; margin-top: 8px; }}
    .rowlist button {{ display: block; width: 100%; text-align: left; border: 0; border-bottom: 1px solid #eee; }}
    .rowlist button.current {{ background: #fff2b3; }}
  </style>
</head>
<body>
  <header>
    <button id="prev">Prev</button>
    <button id="next">Next</button>
    <button id="nextOpen" class="primary">Next Open</button>
    <span id="position"></span>
    <span class="statusline" id="savedState"></span>
  </header>
  <main>
    <section class="viewer">
      <div class="tabs">
        <button id="localTab" class="active">Local PNG Crop</button>
        <button id="wideTab">Wide PNG Crop</button>
      </div>
      <div class="crop-wrap"><img id="cropImage" alt="Mismatch crop"></div>
    </section>
    <aside class="panel">
      <div class="legend">
        <span><span class="swatch" style="background:lime"></span> matched truth</span>
        <span><span class="swatch" style="background:orange"></span> missed truth</span>
        <span><span class="swatch" style="background:red"></span> false positive</span>
        <span><span class="swatch" style="background:dodgerblue"></span> IoU >= 0.50</span>
        <span><span class="swatch" style="background:purple"></span> 0.25 <= IoU < 0.50</span>
      </div>
      <div class="meta" id="meta"></div>
      <label for="bucket">human_error_bucket</label>
      <select id="bucket"></select>
      <label for="reviewStatus">human_review_status</label>
      <select id="reviewStatus"></select>
      <label for="notes">human_notes</label>
      <textarea id="notes"></textarea>
      <div style="display:flex; gap:8px; margin-top:10px;">
        <button id="save" class="primary">Save Row</button>
        <button id="exportCsv">Export Reviewed CSV</button>
      </div>
      <p class="small">This page stores edits in browser localStorage and exports a CSV. It does not modify truth labels, eval manifests, predictions, or training data.</p>
      <div class="rowlist" id="rowlist"></div>
    </aside>
  </main>
  <script>
    const ITEMS = {items_json};
    const BUCKETS = {buckets_json};
    const STATUSES = {statuses_json};
    const STORAGE_KEY = 'cloudhammer_mismatch_review_20260504';
    let index = 0;
    let cropMode = 'local';
    let state = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');

    function byId(id) {{ return document.getElementById(id); }}
    function current() {{ return ITEMS[index]; }}
    function valueFor(item, field) {{ return (state[item.review_item_id] && state[item.review_item_id][field]) ?? item[field] ?? ''; }}
    function saveState() {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }}
    function optionList(el, values) {{
      el.innerHTML = '';
      values.forEach(v => {{
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v || '(blank)';
        el.appendChild(opt);
      }});
    }}
    function render() {{
      const item = current();
      byId('position').textContent = `${{index + 1}} / ${{ITEMS.length}}`;
      byId('cropImage').src = cropMode === 'local' ? item.local_crop_path : item.wide_crop_path;
      byId('localTab').classList.toggle('active', cropMode === 'local');
      byId('wideTab').classList.toggle('active', cropMode === 'wide');
      byId('bucket').value = valueFor(item, 'human_error_bucket');
      byId('reviewStatus').value = valueFor(item, 'human_review_status') || 'unreviewed';
      byId('notes').value = valueFor(item, 'human_notes');
      const meta = [
        ['page', item.source_page_key],
        ['mode', item.eval_mode],
        ['type', item.mismatch_type],
        ['confidence', item.confidence ?? ''],
        ['best_iou', item.best_iou ?? ''],
        ['truth_id', item.truth_id ?? ''],
        ['prediction_id', item.prediction_id ?? ''],
        ['review_item_id', item.review_item_id],
        ['bbox_xyxy', item.bbox_xyxy],
        ['truth_bbox_xyxy', item.truth_bbox_xyxy],
      ];
      byId('meta').innerHTML = meta.map(([k, v]) => `<div>${{k}}</div><div>${{Array.isArray(v) ? v.map(n => Number(n).toFixed(1)).join(', ') : v}}</div>`).join('');
      byId('savedState').textContent = `${{Object.keys(state).length}} saved rows in browser`;
      renderRowList();
    }}
    function saveCurrent() {{
      const item = current();
      state[item.review_item_id] = {{
        human_error_bucket: byId('bucket').value,
        human_review_status: byId('reviewStatus').value,
        human_notes: byId('notes').value,
      }};
      saveState();
      render();
    }}
    function goto(nextIndex) {{
      saveCurrent();
      index = Math.max(0, Math.min(ITEMS.length - 1, nextIndex));
      render();
    }}
    function nextOpen() {{
      saveCurrent();
      for (let offset = 1; offset <= ITEMS.length; offset++) {{
        const candidate = ITEMS[(index + offset) % ITEMS.length];
        const status = valueFor(candidate, 'human_review_status') || 'unreviewed';
        if (status === 'unreviewed') {{
          index = (index + offset) % ITEMS.length;
          render();
          return;
        }}
      }}
      alert('No unreviewed rows remain in browser state.');
    }}
    function csvEscape(v) {{
      const s = v === null || v === undefined ? '' : String(v);
      return /[",\\n\\r]/.test(s) ? '"' + s.replaceAll('"', '""') + '"' : s;
    }}
    function exportCsv() {{
      saveCurrent();
      const fields = ['review_item_id','source_page_key','eval_mode','mismatch_type','truth_id','prediction_id','confidence','iou_25','best_iou','human_error_bucket','human_review_status','human_notes','overlay_path','crop_path'];
      const lines = [fields.join(',')];
      ITEMS.forEach(item => {{
        const saved = state[item.review_item_id] || {{}};
        const row = {{...item, ...saved}};
        lines.push(fields.map(f => csvEscape(row[f])).join(','));
      }});
      const blob = new Blob([lines.join('\\n') + '\\n'], {{type: 'text/csv'}});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'mismatch_review_log.reviewed.csv';
      a.click();
      URL.revokeObjectURL(a.href);
    }}
    function renderRowList() {{
      const list = byId('rowlist');
      list.innerHTML = '';
      ITEMS.forEach((item, i) => {{
        const btn = document.createElement('button');
        btn.className = i === index ? 'current' : '';
        const status = valueFor(item, 'human_review_status') || 'unreviewed';
        btn.textContent = `${{i + 1}}. ${{status}} | ${{item.eval_mode}} | ${{item.mismatch_type}} | ${{item.source_page_key}}`;
        btn.onclick = () => goto(i);
        list.appendChild(btn);
      }});
    }}
    optionList(byId('bucket'), BUCKETS);
    optionList(byId('reviewStatus'), STATUSES);
    byId('prev').onclick = () => goto(index - 1);
    byId('next').onclick = () => goto(index + 1);
    byId('nextOpen').onclick = nextOpen;
    byId('save').onclick = saveCurrent;
    byId('exportCsv').onclick = exportCsv;
    byId('localTab').onclick = () => {{ cropMode = 'local'; render(); }};
    byId('wideTab').onclick = () => {{ cropMode = 'wide'; render(); }};
    window.addEventListener('keydown', e => {{
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === 'ArrowRight') goto(index + 1);
      if (e.key === 'ArrowLeft') goto(index - 1);
    }});
    render();
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a static HTML mismatch reviewer with crisp PNG crops.")
    parser.add_argument("--packet-dir", type=Path, default=DEFAULT_PACKET_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_PACKET_DIR / "mismatch_manifest.jsonl")
    parser.add_argument("--review-log", type=Path, default=DEFAULT_PACKET_DIR / "mismatch_review_log.csv")
    parser.add_argument("--output-html", type=Path, default=DEFAULT_PACKET_DIR / "mismatch_reviewer.html")
    parser.add_argument("--local-padding", type=int, default=360)
    parser.add_argument("--wide-padding", type=int, default=1300)
    args = parser.parse_args()

    rows = read_jsonl(args.manifest)
    review_rows = read_csv_by_id(args.review_log)
    reviewer_dir = args.packet_dir / "reviewer_crops"
    items: list[dict[str, Any]] = []
    for row in rows:
        review_item_id = str(row["review_item_id"])
        saved = review_rows.get(review_item_id, {})
        item_stem = safe_stem(review_item_id)
        local_info = make_review_crop(
            row,
            reviewer_dir / "local" / f"{item_stem}_local.png",
            html_base_dir=args.output_html.parent,
            mode="local",
            padding=args.local_padding,
            min_side=900,
            max_side=2600,
        )
        wide_info = make_review_crop(
            row,
            reviewer_dir / "wide" / f"{item_stem}_wide.png",
            html_base_dir=args.output_html.parent,
            mode="wide",
            padding=args.wide_padding,
            min_side=2200,
            max_side=5200,
        )
        item = {
            **row,
            "human_error_bucket": saved.get("human_error_bucket", row.get("human_error_bucket", "")),
            "human_review_status": saved.get("human_review_status", row.get("human_review_status", "unreviewed")),
            "human_notes": saved.get("human_notes", row.get("human_notes", "")),
            "local_crop_path": local_info["path"],
            "wide_crop_path": wide_info["path"],
            "local_crop_box": local_info["crop_box"],
            "wide_crop_box": wide_info["crop_box"],
            "overlay_path": project_relative(Path(str(row.get("overlay_path")))),
            "crop_path": project_relative(Path(str(row.get("crop_path")))) if row.get("crop_path") else "",
        }
        items.append(item)

    args.output_html.write_text(
        html_document(
            json.dumps(items),
            json.dumps(APPROVED_ERROR_BUCKETS),
            json.dumps(REVIEW_STATUSES),
        ),
        encoding="utf-8",
    )
    summary = {
        "schema": "cloudhammer_v2.static_mismatch_reviewer.v1",
        "reviewer_html": project_relative(args.output_html),
        "items": len(items),
        "local_crops_dir": project_relative(reviewer_dir / "local"),
        "wide_crops_dir": project_relative(reviewer_dir / "wide"),
        "writes": "Browser localStorage and exported mismatch_review_log.reviewed.csv only.",
    }
    (args.packet_dir / "mismatch_reviewer_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
