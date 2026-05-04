from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
DEFAULT_DIAGNOSTIC_DIR = V2_ROOT / "outputs" / "postprocessing_diagnostic_non_frozen_20260504"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def project_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    candidate = Path(str(value))
    if candidate.exists():
        return candidate.resolve()
    parts = candidate.parts
    for anchor, root in (("CloudHammer", PROJECT_ROOT / "CloudHammer"), ("CloudHammer_v2", V2_ROOT)):
        for index, part in enumerate(parts):
            if part.lower() == anchor.lower():
                relocated = root.joinpath(*parts[index + 1 :])
                if relocated.exists():
                    return relocated.resolve()
    return candidate


def browser_path(path_value: str | Path | None, html_path: Path) -> str:
    path = project_path(path_value)
    if path is None:
        return ""
    try:
        relative = os.path.relpath(path, start=html_path.parent).replace("\\", "/")
        return quote(relative, safe="/")
    except ValueError:
        return quote(str(path).replace("\\", "/"), safe="/:")


def load_candidates(manifest_path: Path) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(manifest_path):
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id:
            by_id[candidate_id] = row
    return by_id


def compact_candidate(candidate: dict[str, Any], html_path: Path) -> dict[str, Any]:
    return {
        "candidate_id": candidate.get("candidate_id"),
        "confidence": candidate.get("whole_cloud_confidence") or candidate.get("confidence"),
        "confidence_tier": candidate.get("confidence_tier"),
        "size_bucket": candidate.get("size_bucket"),
        "member_count": candidate.get("member_count"),
        "group_fill_ratio": candidate.get("group_fill_ratio"),
        "bbox_xyxy": candidate.get("bbox_page_xyxy"),
        "crop_box_xyxy": candidate.get("crop_box_page_xyxy"),
        "crop_image_path": candidate.get("crop_image_path"),
        "crop_href": browser_path(candidate.get("crop_image_path"), html_path),
        "render_path": candidate.get("render_path"),
        "render_href": browser_path(candidate.get("render_path"), html_path),
    }


def build_view_rows(
    diagnostic_rows: list[dict[str, Any]],
    candidates_by_id: dict[str, dict[str, Any]],
    html_path: Path,
) -> list[dict[str, Any]]:
    view_rows: list[dict[str, Any]] = []
    for index, row in enumerate(diagnostic_rows, start=1):
        candidate_ids = [str(value) for value in row.get("candidate_ids", [])]
        candidates = [
            compact_candidate(candidates_by_id[candidate_id], html_path)
            for candidate_id in candidate_ids
            if candidate_id in candidates_by_id
        ]
        view_rows.append(
            {
                "row_number": index,
                "diagnostic_id": row.get("diagnostic_id"),
                "diagnostic_family": row.get("diagnostic_family"),
                "source_page_key": row.get("source_page_key"),
                "candidate_ids": candidate_ids,
                "reason": row.get("reason"),
                "suggested_review_focus": row.get("suggested_review_focus"),
                "metrics": row.get("metrics") or {},
                "render_path": row.get("render_path"),
                "render_href": browser_path(row.get("render_path"), html_path),
                "pdf_path": row.get("pdf_path"),
                "candidates": candidates,
            }
        )
    return view_rows


def html_document(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    payload = json.dumps({"rows": rows, "summary": summary}, ensure_ascii=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CloudHammer Postprocessing Diagnostic Viewer</title>
<style>
  :root {{
    color-scheme: light;
    font-family: Arial, sans-serif;
    --border: #c7cbd1;
    --muted: #5c6672;
    --panel: #f6f7f9;
    --active: #fff4bf;
  }}
  body {{
    margin: 0;
    display: grid;
    grid-template-columns: 360px 1fr;
    height: 100vh;
    overflow: hidden;
    background: white;
    color: #111;
  }}
  aside {{
    border-right: 1px solid var(--border);
    overflow: auto;
    background: var(--panel);
    padding: 10px;
  }}
  main {{
    overflow: auto;
    padding: 14px;
  }}
  h1 {{
    font-size: 18px;
    margin: 0 0 8px;
  }}
  h2 {{
    font-size: 16px;
    margin: 14px 0 8px;
  }}
  .small {{
    color: var(--muted);
    font-size: 12px;
    line-height: 1.35;
  }}
  .toolbar {{
    display: flex;
    gap: 6px;
    align-items: center;
    margin: 10px 0;
  }}
  button, select {{
    font-size: 13px;
    padding: 5px 7px;
    border: 1px solid var(--border);
    background: white;
  }}
  .rowButton {{
    width: 100%;
    text-align: left;
    margin: 4px 0;
    padding: 7px;
    border: 1px solid var(--border);
    background: white;
    cursor: pointer;
  }}
  .rowButton.active {{
    background: var(--active);
    border-color: #d2a900;
  }}
  .family {{
    font-weight: 700;
    font-size: 12px;
  }}
  .ids {{
    font-size: 11px;
    color: var(--muted);
    overflow-wrap: anywhere;
  }}
  .summaryGrid, .metaGrid {{
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 5px 12px;
    font-size: 13px;
  }}
  .label {{
    color: var(--muted);
  }}
  .candidateGrid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 12px;
    margin-top: 10px;
  }}
  .candidate {{
    border: 1px solid var(--border);
    padding: 8px;
    background: white;
  }}
  .candidate img {{
    max-width: 100%;
    max-height: 620px;
    display: block;
    margin-top: 8px;
    border: 1px solid var(--border);
    background: #eee;
  }}
  code {{
    font-family: Consolas, monospace;
    font-size: 12px;
  }}
  pre {{
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    background: #f3f4f6;
    border: 1px solid var(--border);
    padding: 8px;
    font-size: 12px;
  }}
  a {{
    color: #0645ad;
  }}
</style>
</head>
<body>
<aside>
  <h1>Postprocessing Diagnostic</h1>
  <div class="small">
    Read-only viewer. This does not edit truth labels, eval manifests, predictions,
    model files, datasets, or training data.
  </div>
  <div class="toolbar">
    <button id="prevButton">Prev</button>
    <button id="nextButton">Next</button>
    <select id="familyFilter"></select>
  </div>
  <div id="summary" class="summaryGrid"></div>
  <h2>Rows</h2>
  <div id="rowList"></div>
</aside>
<main>
  <div id="detail"></div>
</main>
<script>
const DATA = {payload};
let rows = DATA.rows;
let filteredRows = rows;
let currentIndex = 0;

function fmt(value) {{
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value);
}}

function esc(value) {{
  return fmt(value).replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
}}

function rowTitle(row) {{
  return `${{row.row_number}}. ${{row.diagnostic_family}}`;
}}

function renderSummary() {{
  const summary = DATA.summary || {{}};
  const byFamily = summary.by_diagnostic_family || {{}};
  const fields = [
    ['rows', summary.diagnostic_rows],
    ['input candidates', summary.input_candidates],
    ['analyzed candidates', summary.analyzed_candidates],
    ['excluded frozen', summary.excluded_frozen_candidates],
    ['merge', byFamily.fragment_merge_candidate],
    ['duplicate', byFamily.duplicate_suppression_candidate],
    ['split', byFamily.overmerge_split_candidate],
    ['loose', byFamily.loose_localization_candidate],
  ];
  document.getElementById('summary').innerHTML = fields.map(([k, v]) =>
    `<div class="label">${{esc(k)}}</div><div><code>${{esc(v)}}</code></div>`
  ).join('');
}}

function renderFilter() {{
  const families = [...new Set(rows.map(row => row.diagnostic_family))].sort();
  const select = document.getElementById('familyFilter');
  select.innerHTML = '<option value="">all families</option>' + families.map(family =>
    `<option value="${{esc(family)}}">${{esc(family)}}</option>`
  ).join('');
  select.onchange = () => {{
    const value = select.value;
    filteredRows = value ? rows.filter(row => row.diagnostic_family === value) : rows;
    currentIndex = 0;
    renderList();
    renderDetail();
  }};
}}

function renderList() {{
  const list = document.getElementById('rowList');
  list.innerHTML = filteredRows.map((row, index) => `
    <button class="rowButton ${{index === currentIndex ? 'active' : ''}}" onclick="selectRow(${{index}})">
      <div class="family">${{esc(rowTitle(row))}}</div>
      <div class="small">${{esc(row.source_page_key)}}</div>
      <div class="ids">${{esc((row.candidate_ids || []).join(' | '))}}</div>
    </button>
  `).join('');
}}

function metricGrid(metrics) {{
  return Object.entries(metrics || {{}}).map(([key, value]) =>
    `<div class="label">${{esc(key)}}</div><div><code>${{esc(Array.isArray(value) ? JSON.stringify(value) : value)}}</code></div>`
  ).join('');
}}

function candidateCard(candidate) {{
  const cropLink = candidate.crop_href
    ? `<a href="${{esc(candidate.crop_href)}}" target="_blank" rel="noreferrer">open crop</a>`
    : '<span class="small">no crop path</span>';
  const renderLink = candidate.render_href
    ? ` | <a href="${{esc(candidate.render_href)}}" target="_blank" rel="noreferrer">open page</a>`
    : '';
  const image = candidate.crop_href
    ? `<img src="${{esc(candidate.crop_href)}}" alt="${{esc(candidate.candidate_id)}}">`
    : '';
  const fields = [
    ['candidate_id', candidate.candidate_id],
    ['confidence', candidate.confidence],
    ['tier', candidate.confidence_tier],
    ['size', candidate.size_bucket],
    ['member_count', candidate.member_count],
    ['fill_ratio', candidate.group_fill_ratio],
    ['bbox_xyxy', JSON.stringify(candidate.bbox_xyxy || '')],
  ];
  return `
    <section class="candidate">
      <div><strong>${{esc(candidate.candidate_id)}}</strong></div>
      <div class="small">${{cropLink}}${{renderLink}}</div>
      <div class="metaGrid">${{fields.map(([k, v]) => `<div class="label">${{esc(k)}}</div><div><code>${{esc(v)}}</code></div>`).join('')}}</div>
      ${{image}}
    </section>
  `;
}}

function renderDetail() {{
  const detail = document.getElementById('detail');
  const row = filteredRows[currentIndex];
  if (!row) {{
    detail.innerHTML = '<p>No rows.</p>';
    return;
  }}
  const renderLink = row.render_href
    ? `<a href="${{esc(row.render_href)}}" target="_blank" rel="noreferrer">open source page</a>`
    : '';
  detail.innerHTML = `
    <h1>${{esc(rowTitle(row))}}</h1>
    <div class="small"><code>${{esc(row.diagnostic_id)}}</code></div>
    <h2>What To Check</h2>
    <p>${{esc(row.reason)}}</p>
    <p><strong>${{esc(row.suggested_review_focus)}}</strong></p>
    <div class="metaGrid">
      <div class="label">source_page_key</div><div><code>${{esc(row.source_page_key)}}</code></div>
      <div class="label">candidate_ids</div><div><code>${{esc((row.candidate_ids || []).join(' | '))}}</code></div>
      <div class="label">source page</div><div>${{renderLink}}</div>
      <div class="label">pdf_path</div><div><code>${{esc(row.pdf_path)}}</code></div>
    </div>
    <h2>Metrics</h2>
    <div class="metaGrid">${{metricGrid(row.metrics)}}</div>
    <h2>Candidate Crops</h2>
    <div class="candidateGrid">${{(row.candidates || []).map(candidateCard).join('')}}</div>
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a static viewer for postprocessing diagnostic rows.")
    parser.add_argument("--diagnostic-dir", type=Path, default=DEFAULT_DIAGNOSTIC_DIR)
    parser.add_argument("--output-html", type=Path, default=None)
    args = parser.parse_args()

    diagnostic_dir = args.diagnostic_dir
    summary_path = diagnostic_dir / "postprocessing_diagnostic_summary.json"
    rows_path = diagnostic_dir / "postprocessing_diagnostic_candidates.jsonl"
    summary = read_json(summary_path)
    rows = read_jsonl(rows_path)
    candidate_manifest = project_path(summary.get("source_candidate_manifest"))
    if candidate_manifest is None or not candidate_manifest.exists():
        raise FileNotFoundError(f"Candidate manifest not found: {summary.get('source_candidate_manifest')}")

    output_html = args.output_html or diagnostic_dir / "postprocessing_diagnostic_viewer.html"
    candidates_by_id = load_candidates(candidate_manifest)
    view_rows = build_view_rows(rows, candidates_by_id, output_html)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html_document(view_rows, summary), encoding="utf-8")

    print("Postprocessing diagnostic viewer")
    print(f"- rows: {len(view_rows)}")
    print(f"- candidate_manifest: {candidate_manifest}")
    print(f"- output_html: {output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
