from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from build_postprocessing_dry_run_plan import project_path, read_jsonl, write_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CROP_REGEN_DIR = (
    PROJECT_ROOT
    / "CloudHammer_v2"
    / "outputs"
    / "postprocessing_diagnostic_non_frozen_20260504"
    / "dry_run_postprocessor_20260505"
    / "postprocessing_apply_non_frozen_20260505"
    / "crop_regeneration_20260508"
)
DEFAULT_MANIFEST = DEFAULT_CROP_REGEN_DIR / "postprocessed_non_frozen_candidates_manifest.regenerated_crops.jsonl"
INSPECTION_FIELDNAMES = [
    "inspection_item_id",
    "row_number",
    "candidate_id",
    "source_page_key",
    "postprocessing_action",
    "crop_status",
    "gpt_status",
    "gpt_decision",
    "gpt_confidence",
    "gpt_tags",
    "recommended_next_step",
    "gpt_notes",
]


def read_csv_by_id(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            str(row.get("inspection_item_id") or ""): row
            for row in csv.DictReader(handle)
            if row.get("inspection_item_id")
        }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INSPECTION_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def project_relative(path: Path | None, output_html: Path) -> str:
    if path is None:
        return ""
    try:
        return Path(path).resolve().relative_to(output_html.parent.resolve()).as_posix()
    except ValueError:
        try:
            return Path(path).resolve().relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return Path(path).resolve().as_posix()


def inspection_item_id(row: dict[str, Any]) -> str:
    return str(row.get("candidate_id") or "")


def default_inspection_row(row: dict[str, Any], row_number: int, saved: dict[str, str] | None = None) -> dict[str, Any]:
    saved = saved or {}
    return {
        "inspection_item_id": inspection_item_id(row),
        "row_number": row_number,
        "candidate_id": row.get("candidate_id") or "",
        "source_page_key": row.get("source_page_key") or "",
        "postprocessing_action": row.get("postprocessing_action") or "",
        "crop_status": row.get("crop_status") or "",
        "gpt_status": saved.get("gpt_status", "unreviewed"),
        "gpt_decision": saved.get("gpt_decision", ""),
        "gpt_confidence": saved.get("gpt_confidence", ""),
        "gpt_tags": saved.get("gpt_tags", ""),
        "recommended_next_step": saved.get("recommended_next_step", ""),
        "gpt_notes": saved.get("gpt_notes", ""),
    }


def build_view_rows(manifest_rows: list[dict[str, Any]], review_rows: list[dict[str, Any]], output_html: Path) -> list[dict[str, Any]]:
    review_by_id = {str(row["inspection_item_id"]): row for row in review_rows}
    view_rows: list[dict[str, Any]] = []
    for index, row in enumerate(manifest_rows, start=1):
        crop_path = project_path(row.get("crop_image_path"))
        render_path = project_path(row.get("render_path"))
        view = dict(row)
        view["row_number"] = index
        view["inspection_item_id"] = inspection_item_id(row)
        view["crop_href"] = project_relative(crop_path, output_html)
        view["render_href"] = project_relative(render_path, output_html)
        view["inspection_defaults"] = review_by_id.get(view["inspection_item_id"], {})
        view_rows.append(view)
    return view_rows


def summarize(rows: list[dict[str, Any]], review_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_action: dict[str, int] = {}
    by_crop_status: dict[str, int] = {}
    by_gpt_decision: dict[str, int] = {}
    by_gpt_status: dict[str, int] = {}
    for row in rows:
        by_action[str(row.get("postprocessing_action") or "")] = by_action.get(str(row.get("postprocessing_action") or ""), 0) + 1
        by_crop_status[str(row.get("crop_status") or "")] = by_crop_status.get(str(row.get("crop_status") or ""), 0) + 1
    for row in review_rows:
        by_gpt_status[str(row.get("gpt_status") or "unreviewed")] = by_gpt_status.get(str(row.get("gpt_status") or "unreviewed"), 0) + 1
        decision = str(row.get("gpt_decision") or "")
        if decision:
            by_gpt_decision[decision] = by_gpt_decision.get(decision, 0) + 1
    return {
        "schema": "cloudhammer_v2.postprocessed_crop_inspection_summary.v1",
        "candidate_count": len(rows),
        "inspection_rows": len(review_rows),
        "by_postprocessing_action": dict(sorted(by_action.items())),
        "by_crop_status": dict(sorted(by_crop_status.items())),
        "by_gpt_status": dict(sorted(by_gpt_status.items())),
        "by_gpt_decision": dict(sorted(by_gpt_decision.items())),
        "guardrails": [
            "inspection_metadata_only",
            "non_frozen_derived_manifest_only",
            "no_source_candidate_manifest_edits",
            "no_truth_label_edits",
            "no_eval_manifest_edits",
            "no_prediction_file_edits",
            "no_model_file_edits",
            "no_dataset_or_training_data_writes",
            "not_threshold_tuning",
        ],
    }


def html_document(rows: list[dict[str, Any]], summary: dict[str, Any], review_rows: list[dict[str, Any]]) -> str:
    payload = json.dumps({"rows": rows, "summary": summary, "inspectionRows": review_rows}, ensure_ascii=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CloudHammer Postprocessed Crop Inspection</title>
<style>
  :root {{
    color-scheme: light;
    --border: #d9dee7;
    --muted: #64748b;
    --active: #fef3c7;
    --good: #dcfce7;
    --warn: #ffedd5;
    --bad: #fee2e2;
  }}
  body {{ margin: 0; font-family: Arial, sans-serif; background: #f8fafc; color: #111827; }}
  main {{ display: grid; grid-template-columns: 360px 1fr; min-height: 100vh; }}
  aside {{ border-right: 1px solid var(--border); background: white; padding: 12px; overflow-y: auto; max-height: 100vh; }}
  section.detail {{ padding: 16px 20px; overflow-y: auto; max-height: 100vh; }}
  h1 {{ font-size: 18px; margin: 0 0 8px; }}
  h2 {{ font-size: 14px; margin: 16px 0 8px; }}
  button, select {{ font-size: 13px; padding: 5px 7px; border: 1px solid var(--border); background: white; }}
  .toolbar {{ display: flex; gap: 6px; flex-wrap: wrap; margin: 10px 0; }}
  .summaryGrid, .metaGrid {{ display: grid; grid-template-columns: 160px 1fr; gap: 4px 8px; font-size: 13px; }}
  .label, .small {{ color: var(--muted); font-size: 12px; }}
  .rowButton {{ width: 100%; text-align: left; margin: 0 0 6px; border: 1px solid var(--border); background: white; padding: 8px; }}
  .rowButton.active {{ background: var(--active); }}
  .rowButton.accept {{ border-left: 5px solid #16a34a; }}
  .rowButton.followup {{ border-left: 5px solid #d97706; }}
  .rowButton.reject {{ border-left: 5px solid #dc2626; }}
  .pill {{ display: inline-block; border: 1px solid var(--border); border-radius: 999px; padding: 2px 7px; font-size: 11px; color: var(--muted); background: white; margin-right: 4px; }}
  .panel {{ border: 1px solid var(--border); background: white; padding: 10px; margin: 12px 0; }}
  img {{ display: block; max-width: 100%; max-height: 760px; border: 1px solid var(--border); background: #eee; }}
  code {{ font-family: Consolas, monospace; font-size: 12px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  td, th {{ border-bottom: 1px solid var(--border); padding: 4px 6px; text-align: left; vertical-align: top; }}
</style>
</head>
<body>
<main>
<aside>
  <h1>Crop Inspection</h1>
  <div class="small">GPT-5.5 precheck metadata only. This viewer does not edit source manifests, labels, eval truth, predictions, model files, datasets, training data, or tuning inputs.</div>
  <div class="toolbar">
    <button id="prevButton">Prev</button>
    <button id="nextButton">Next</button>
    <select id="decisionFilter"></select>
  </div>
  <div id="summary" class="summaryGrid"></div>
  <h2>Rows</h2>
  <div id="rowList"></div>
</aside>
<section class="detail" id="detail"></section>
</main>
<script>
const DATA = {payload};
const rows = DATA.rows || [];
const inspectionRows = Object.fromEntries((DATA.inspectionRows || []).map(row => [row.inspection_item_id, row]));
let filteredRows = rows;
let currentIndex = 0;

function esc(value) {{
  return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}}[ch]));
}}

function fmt(value) {{
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}}

function inspection(row) {{
  return inspectionRows[row.inspection_item_id] || row.inspection_defaults || {{}};
}}

function rowClass(row) {{
  const decision = inspection(row).gpt_decision || '';
  if (decision === 'accept_crop') return 'accept';
  if (decision.startsWith('reject_')) return 'reject';
  if (decision) return 'followup';
  return '';
}}

function renderSummary() {{
  const summary = DATA.summary || {{}};
  const fields = [
    ['candidates', summary.candidate_count],
    ['inspection rows', summary.inspection_rows],
    ['gpt decisions', JSON.stringify(summary.by_gpt_decision || {{}})],
    ['crop status', JSON.stringify(summary.by_crop_status || {{}})],
  ];
  document.getElementById('summary').innerHTML = fields.map(([k, v]) => `<div class="label">${{esc(k)}}</div><div><code>${{esc(fmt(v))}}</code></div>`).join('');
}}

function renderFilter() {{
  const select = document.getElementById('decisionFilter');
  const decisions = Array.from(new Set(rows.map(row => inspection(row).gpt_decision || 'unreviewed'))).sort();
  select.innerHTML = ['all'].concat(decisions).map(value => `<option value="${{esc(value)}}">${{esc(value)}}</option>`).join('');
  select.onchange = () => {{
    const value = select.value;
    filteredRows = value === 'all' ? rows : rows.filter(row => (inspection(row).gpt_decision || 'unreviewed') === value);
    currentIndex = 0;
    renderList();
    renderDetail();
  }};
}}

function renderList() {{
  const list = document.getElementById('rowList');
  list.innerHTML = filteredRows.map((row, index) => {{
    const item = inspection(row);
    return `<button class="rowButton ${{index === currentIndex ? 'active' : ''}} ${{rowClass(row)}}" onclick="selectRow(${{index}})">
      <div><strong>${{esc(row.row_number)}}. ${{esc(row.postprocessing_action)}}</strong></div>
      <div><span class="pill">${{esc(item.gpt_status || 'unreviewed')}}</span><span class="pill">${{esc(item.gpt_decision || 'no decision')}}</span></div>
      <div class="small">${{esc(row.source_page_key)}}</div>
      <div class="small">${{esc(row.candidate_id)}}</div>
    </button>`;
  }}).join('');
}}

function metaGrid(row) {{
  const fields = [
    ['candidate_id', row.candidate_id],
    ['source_page_key', row.source_page_key],
    ['postprocessing_action', row.postprocessing_action],
    ['postprocessing_label', row.postprocessing_label],
    ['crop_status', row.crop_status],
    ['confidence', row.whole_cloud_confidence || row.confidence],
    ['bbox_page_xyxy', row.bbox_page_xyxy],
    ['crop_box_page_xyxy', row.crop_box_page_xyxy],
    ['crop_image_path', row.crop_image_path],
  ];
  return fields.map(([k, v]) => `<div class="label">${{esc(k)}}</div><div><code>${{esc(fmt(v))}}</code></div>`).join('');
}}

function renderDetail() {{
  const detail = document.getElementById('detail');
  const row = filteredRows[currentIndex];
  if (!row) {{
    detail.innerHTML = '<h1>No rows</h1>';
    return;
  }}
  const item = inspection(row);
  detail.innerHTML = `
    <h1>${{esc(row.row_number)}}. ${{esc(row.postprocessing_action)}} <span class="pill">${{esc(item.gpt_decision || 'no decision')}}</span></h1>
    <div class="panel">
      <h2>GPT-5.5 Precheck</h2>
      <div class="metaGrid">
        <div class="label">status</div><div><code>${{esc(item.gpt_status || '')}}</code></div>
        <div class="label">decision</div><div><code>${{esc(item.gpt_decision || '')}}</code></div>
        <div class="label">confidence</div><div><code>${{esc(item.gpt_confidence || '')}}</code></div>
        <div class="label">tags</div><div><code>${{esc(item.gpt_tags || '')}}</code></div>
        <div class="label">next step</div><div><code>${{esc(item.recommended_next_step || '')}}</code></div>
      </div>
      <p>${{esc(item.gpt_notes || '')}}</p>
    </div>
    <div class="panel">
      <h2>Crop</h2>
      ${{row.crop_href ? `<img src="${{esc(row.crop_href)}}" alt="${{esc(row.candidate_id)}}">` : '<div class="small">missing crop path</div>'}}
      <div class="small">${{row.render_href ? `<a href="${{esc(row.render_href)}}" target="_blank" rel="noreferrer">open page render</a>` : ''}}</div>
    </div>
    <div class="panel">
      <h2>Metadata</h2>
      <div class="metaGrid">${{metaGrid(row)}}</div>
    </div>
  `;
  renderList();
}}

function selectRow(index) {{
  currentIndex = index;
  renderDetail();
}}

document.getElementById('prevButton').onclick = () => {{
  currentIndex = Math.max(0, currentIndex - 1);
  renderDetail();
}};
document.getElementById('nextButton').onclick = () => {{
  currentIndex = Math.min(filteredRows.length - 1, currentIndex + 1);
  renderDetail();
}};

renderSummary();
renderFilter();
renderList();
renderDetail();
</script>
</body>
</html>
"""


def markdown_summary(summary: dict[str, Any], output_dir: Path, manifest: Path, inspection_csv: Path, output_html: Path) -> str:
    lines = [
        "# Postprocessed Crop Inspection Packet",
        "",
        "Status: GPT-prefillable inspection packet for the crop-ready regenerated non-frozen manifest.",
        "",
        "Safety: inspection metadata only. This does not edit source manifests, labels, eval truth, predictions, model files, datasets, training data, or threshold-tuning inputs.",
        "",
        f"- manifest: `{manifest}`",
        f"- inspection CSV: `{inspection_csv}`",
        f"- viewer: `{output_html}`",
        "",
        "## Counts",
        "",
        f"- candidates: `{summary['candidate_count']}`",
        f"- inspection rows: `{summary['inspection_rows']}`",
        "",
        "## Crop Status",
        "",
    ]
    for key, value in summary["by_crop_status"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## GPT Decisions", ""])
    if summary["by_gpt_decision"]:
        for key, value in summary["by_gpt_decision"].items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- none yet")
    lines.extend(["", "## Artifacts", ""])
    lines.append(f"- `{output_dir / 'postprocessed_crop_inspection_summary.json'}`")
    lines.append(f"- `{output_dir / 'postprocessed_crop_inspection_summary.md'}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a static inspection viewer for regenerated postprocessed crops.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_CROP_REGEN_DIR / "crop_inspection_20260508")
    parser.add_argument("--inspection-csv", type=Path, default=None)
    parser.add_argument("--output-html", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.output_dir
    inspection_csv = args.inspection_csv or output_dir / "postprocessed_crop_inspection.csv"
    output_html = args.output_html or output_dir / "postprocessed_crop_inspection_viewer.html"
    manifest_rows = read_jsonl(args.manifest)
    saved_rows = read_csv_by_id(inspection_csv)
    inspection_rows = [
        default_inspection_row(row, index, saved_rows.get(inspection_item_id(row)))
        for index, row in enumerate(manifest_rows, start=1)
    ]
    view_rows = build_view_rows(manifest_rows, inspection_rows, output_html)
    summary = summarize(manifest_rows, inspection_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(inspection_csv, inspection_rows)
    output_html.write_text(html_document(view_rows, summary, inspection_rows), encoding="utf-8")
    write_json(output_dir / "postprocessed_crop_inspection_summary.json", summary)
    (output_dir / "postprocessed_crop_inspection_summary.md").write_text(
        markdown_summary(summary, output_dir, args.manifest, inspection_csv, output_html),
        encoding="utf-8",
    )

    print("Postprocessed crop inspection viewer")
    print(f"- rows: {len(inspection_rows)}")
    print(f"- inspection_csv: {inspection_csv}")
    print(f"- output_html: {output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
