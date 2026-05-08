from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
DEFAULT_DIAGNOSTIC_DIR = V2_ROOT / "outputs" / "postprocessing_diagnostic_non_frozen_20260504"
REVIEW_FIELDNAMES = [
    "review_item_id",
    "row_number",
    "diagnostic_id",
    "diagnostic_family",
    "source_page_key",
    "candidate_ids",
    "review_status",
    "review_decision",
    "target_candidate_ids",
    "corrected_bbox_xyxy",
    "review_notes",
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_csv_by_id(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["review_item_id"]: row for row in csv.DictReader(handle) if row.get("review_item_id")}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


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


def review_item_id(row: dict[str, Any], row_number: int) -> str:
    diagnostic_id = str(row.get("diagnostic_id") or "")
    if diagnostic_id:
        return diagnostic_id
    family = str(row.get("diagnostic_family") or "diagnostic")
    source_page_key = str(row.get("source_page_key") or "unknown_page")
    candidate_ids = "|".join(str(value) for value in row.get("candidate_ids", []))
    return f"{row_number}:{family}:{source_page_key}:{candidate_ids}"


def review_decision_options(diagnostic_family: str | None) -> list[str]:
    if diagnostic_family == "fragment_merge_candidate":
        return ["merge", "reject_merge", "split", "tighten", "ignore", "unclear"]
    if diagnostic_family == "duplicate_suppression_candidate":
        return ["suppress_duplicate", "reject_suppress", "ignore", "unclear"]
    if diagnostic_family == "overmerge_split_candidate":
        return ["split", "reject_split", "tighten", "tighten_adjust", "expand", "ignore", "unclear"]
    if diagnostic_family == "loose_localization_candidate":
        return ["tighten", "tighten_adjust", "reject_tighten", "expand", "split", "ignore", "unclear"]
    return ["ignore", "unclear"]


def build_review_rows(diagnostic_rows: list[dict[str, Any]], existing_rows: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    review_rows: list[dict[str, Any]] = []
    for index, row in enumerate(diagnostic_rows, start=1):
        item_id = review_item_id(row, index)
        saved = existing_rows.get(item_id, {})
        candidate_ids = [str(value) for value in row.get("candidate_ids", [])]
        review_rows.append(
            {
                "review_item_id": item_id,
                "row_number": index,
                "diagnostic_id": row.get("diagnostic_id") or "",
                "diagnostic_family": row.get("diagnostic_family") or "",
                "source_page_key": row.get("source_page_key") or "",
                "candidate_ids": " | ".join(candidate_ids),
                "review_status": saved.get("review_status", "unreviewed"),
                "review_decision": saved.get("review_decision", ""),
                "target_candidate_ids": saved.get("target_candidate_ids", ""),
                "corrected_bbox_xyxy": saved.get("corrected_bbox_xyxy", ""),
                "review_notes": saved.get("review_notes", ""),
            }
        )
    return review_rows


def attach_review_defaults(view_rows: list[dict[str, Any]], review_rows: list[dict[str, Any]]) -> None:
    by_id = {row["review_item_id"]: row for row in review_rows}
    for row in view_rows:
        item_id = review_item_id(row, int(row["row_number"]))
        row["review_item_id"] = item_id
        row["review_decision_options"] = review_decision_options(row.get("diagnostic_family"))
        row["review_defaults"] = by_id.get(item_id, {})


def html_document(rows: list[dict[str, Any]], summary: dict[str, Any], review_rows: list[dict[str, Any]]) -> str:
    payload = json.dumps({"rows": rows, "summary": summary, "reviewRows": review_rows}, ensure_ascii=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CloudHammer Postprocessing Diagnostic Reviewer</title>
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
    flex-wrap: wrap;
  }}
  button, select, textarea, input {{
    font-size: 13px;
    padding: 5px 7px;
    border: 1px solid var(--border);
    background: white;
  }}
  textarea {{
    box-sizing: border-box;
    width: 100%;
    min-height: 74px;
    font-family: Arial, sans-serif;
  }}
  input {{
    box-sizing: border-box;
    width: 100%;
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
  .rowButton.reviewed {{
    border-left: 5px solid #16a34a;
  }}
  .rowButton.followup {{
    border-left: 5px solid #d97706;
  }}
  .reviewPanel {{
    border: 1px solid var(--border);
    background: #f8fafc;
    padding: 10px;
    margin: 10px 0 14px;
  }}
  .reviewGrid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(180px, 1fr));
    gap: 8px;
  }}
  .reviewGrid label {{
    display: block;
    color: var(--muted);
    font-size: 12px;
  }}
  .reviewActions {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 8px;
  }}
  .statusPill {{
    display: inline-block;
    border: 1px solid var(--border);
    background: white;
    border-radius: 999px;
    padding: 2px 7px;
    font-size: 11px;
    color: var(--muted);
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
  .imageWrap {{
    position: relative;
    display: inline-block;
    max-width: 100%;
    margin-top: 8px;
  }}
  .imageWrap img {{
    max-width: 100%;
    max-height: 620px;
    display: block;
    border: 1px solid var(--border);
    background: #eee;
  }}
  .overlayBox {{
    position: absolute;
    box-sizing: border-box;
    border: 3px solid #e11d48;
    background: rgba(225, 29, 72, 0.08);
    pointer-events: none;
  }}
  .overlayBox.secondary {{
    border-color: #2563eb;
    background: rgba(37, 99, 235, 0.08);
  }}
  .overlayBox.tertiary {{
    border-color: #16a34a;
    background: rgba(22, 163, 74, 0.08);
  }}
  .overlayBox.other {{
    border-style: dashed;
    opacity: 0.78;
  }}
  .overlayBox.tight {{
    border: 2px dashed #f59e0b;
    background: rgba(245, 158, 11, 0.08);
  }}
  .overlayLabel {{
    position: absolute;
    left: -3px;
    top: -22px;
    padding: 2px 4px;
    background: rgba(17, 24, 39, 0.88);
    color: white;
    font-size: 11px;
    line-height: 1;
    white-space: nowrap;
  }}
  .legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
    font-size: 12px;
    color: var(--muted);
  }}
  .legendItem {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }}
  .swatch {{
    width: 14px;
    height: 10px;
    border: 2px solid #e11d48;
    display: inline-block;
  }}
  .swatch.secondary {{ border-color: #2563eb; }}
  .swatch.tertiary {{ border-color: #16a34a; }}
  .swatch.tight {{ border-color: #f59e0b; border-style: dashed; }}
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
    Reviewer controls write browser-local state and export a CSV review log only.
    This does not edit truth labels, eval manifests, predictions, model files,
    datasets, or training data.
  </div>
  <div class="toolbar">
    <button id="prevButton">Prev</button>
    <button id="nextButton">Next</button>
    <button id="nextUnreviewedButton">Next Unreviewed</button>
    <select id="familyFilter"></select>
  </div>
  <div class="toolbar">
    <button id="applyReviewLogButton">Apply Review Log Values</button>
    <button id="exportCsvButton">Export CSV</button>
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
const REVIEW_FIELDNAMES = {json.dumps(REVIEW_FIELDNAMES)};
const REVIEW_STATUSES = ["unreviewed", "reviewed", "needs_followup", "not_actionable"];
const STORAGE_KEY = "cloudhammer_postprocessing_diagnostic_review_v1";
let state = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}');
const embeddedReviewRows = Object.fromEntries((DATA.reviewRows || []).map(row => [row.review_item_id, row]));

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

function defaultsFor(row) {{
  return row.review_defaults || embeddedReviewRows[row.review_item_id] || {{}};
}}

function valueFor(row, field) {{
  return (state[row.review_item_id] && state[row.review_item_id][field]) || defaultsFor(row)[field] || '';
}}

function currentReview(row) {{
  return {{
    review_item_id: row.review_item_id,
    row_number: row.row_number,
    diagnostic_id: row.diagnostic_id || '',
    diagnostic_family: row.diagnostic_family || '',
    source_page_key: row.source_page_key || '',
    candidate_ids: (row.candidate_ids || []).join(' | '),
    review_status: valueFor(row, 'review_status') || 'unreviewed',
    review_decision: valueFor(row, 'review_decision') || '',
    target_candidate_ids: valueFor(row, 'target_candidate_ids') || '',
    corrected_bbox_xyxy: valueFor(row, 'corrected_bbox_xyxy') || '',
    review_notes: valueFor(row, 'review_notes') || '',
  }};
}}

function saveState() {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}}

function setRowReview(row, patch) {{
  const current = currentReview(row);
  state[row.review_item_id] = {{...current, ...patch}};
  saveState();
  renderSummary();
  renderList();
}}

function renderSummary() {{
  const summary = DATA.summary || {{}};
  const byFamily = summary.by_diagnostic_family || {{}};
  const reviewRows = rows.map(row => currentReview(row));
  const reviewedCount = reviewRows.filter(row => row.review_status && row.review_status !== 'unreviewed').length;
  const unreviewedCount = rows.length - reviewedCount;
  const fields = [
    ['rows', summary.diagnostic_rows],
    ['reviewed', reviewedCount],
    ['unreviewed', unreviewedCount],
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
    <button class="rowButton ${{index === currentIndex ? 'active' : ''}} ${{rowClass(row)}}" onclick="selectRow(${{index}})">
      <div class="family">${{esc(rowTitle(row))}}</div>
      <div><span class="statusPill">${{esc(currentReview(row).review_status || 'unreviewed')}}</span> <span class="statusPill">${{esc(currentReview(row).review_decision || 'no decision')}}</span></div>
      <div class="small">${{esc(row.source_page_key)}}</div>
      <div class="ids">${{esc((row.candidate_ids || []).join(' | '))}}</div>
    </button>
  `).join('');
}}

function rowClass(row) {{
  const status = currentReview(row).review_status || 'unreviewed';
  if (status === 'reviewed') return 'reviewed';
  if (status === 'needs_followup') return 'followup';
  return '';
}}

function metricGrid(metrics) {{
  return Object.entries(metrics || {{}}).map(([key, value]) =>
    `<div class="label">${{esc(key)}}</div><div><code>${{esc(Array.isArray(value) ? JSON.stringify(value) : value)}}</code></div>`
  ).join('');
}}

function shortCandidateId(candidateId) {{
  const value = fmt(candidateId);
  const wholeIndex = value.indexOf('_whole_');
  return wholeIndex >= 0 ? value.slice(wholeIndex + 1) : value;
}}

function validBox(box) {{
  return Array.isArray(box) && box.length === 4 && box.every(value => Number.isFinite(Number(value)));
}}

function intersectBox(box, clip) {{
  if (!validBox(box) || !validBox(clip)) return null;
  const x1 = Math.max(Number(box[0]), Number(clip[0]));
  const y1 = Math.max(Number(box[1]), Number(clip[1]));
  const x2 = Math.min(Number(box[2]), Number(clip[2]));
  const y2 = Math.min(Number(box[3]), Number(clip[3]));
  if (x2 <= x1 || y2 <= y1) return null;
  return [x1, y1, x2, y2];
}}

function overlayDiv(box, cropBox, label, className) {{
  const clipped = intersectBox(box, cropBox);
  if (!clipped) return '';
  const cropWidth = Number(cropBox[2]) - Number(cropBox[0]);
  const cropHeight = Number(cropBox[3]) - Number(cropBox[1]);
  if (cropWidth <= 0 || cropHeight <= 0) return '';
  const left = ((clipped[0] - Number(cropBox[0])) / cropWidth) * 100;
  const top = ((clipped[1] - Number(cropBox[1])) / cropHeight) * 100;
  const width = ((clipped[2] - clipped[0]) / cropWidth) * 100;
  const height = ((clipped[3] - clipped[1]) / cropHeight) * 100;
  return `
    <div class="overlayBox ${{esc(className)}}"
      style="left:${{left.toFixed(3)}}%;top:${{top.toFixed(3)}}%;width:${{width.toFixed(3)}}%;height:${{height.toFixed(3)}}%;">
      <span class="overlayLabel">${{esc(label)}}</span>
    </div>
  `;
}}

function candidateImage(candidate, row) {{
  if (!candidate.crop_href) return '';
  const cropBox = candidate.crop_box_xyxy;
  const palette = ['primary', 'secondary', 'tertiary'];
  const boxes = (row.candidates || []).map((other, index) => {{
    const colorClass = palette[index] || 'secondary';
    const activeClass = other.candidate_id === candidate.candidate_id ? colorClass : `${{colorClass}} other`;
    return overlayDiv(other.bbox_xyxy, cropBox, shortCandidateId(other.candidate_id), activeClass);
  }}).join('');
  const tightBox = validBox(row.metrics && row.metrics.tight_member_bbox_xyxy)
    ? overlayDiv(row.metrics.tight_member_bbox_xyxy, cropBox, 'tight member bbox', 'tight')
    : '';
  return `
    <div class="imageWrap">
      <img src="${{esc(candidate.crop_href)}}" alt="${{esc(candidate.candidate_id)}}">
      ${{boxes}}
      ${{tightBox}}
    </div>
    <div class="legend">
      <span class="legendItem"><span class="swatch"></span>candidate box</span>
      <span class="legendItem"><span class="swatch secondary"></span>other candidate box in this row</span>
      ${{tightBox ? '<span class="legendItem"><span class="swatch tight"></span>tight member bbox</span>' : ''}}
    </div>
  `;
}}

function candidateCard(candidate, row) {{
  const cropLink = candidate.crop_href
    ? `<a href="${{esc(candidate.crop_href)}}" target="_blank" rel="noreferrer">open crop</a>`
    : '<span class="small">no crop path</span>';
  const renderLink = candidate.render_href
    ? ` | <a href="${{esc(candidate.render_href)}}" target="_blank" rel="noreferrer">open page</a>`
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
      ${{candidateImage(candidate, row)}}
    </section>
  `;
}}

function renderReviewPanel(row) {{
  const review = currentReview(row);
  const decisionOptions = row.review_decision_options || [];
  const statusOptions = REVIEW_STATUSES.map(status =>
    `<option value="${{esc(status)}}" ${{status === review.review_status ? 'selected' : ''}}>${{esc(status)}}</option>`
  ).join('');
  const decisionSelectOptions = [''].concat(decisionOptions).map(decision =>
    `<option value="${{esc(decision)}}" ${{decision === review.review_decision ? 'selected' : ''}}>${{esc(decision || 'choose decision')}}</option>`
  ).join('');
  return `
    <section class="reviewPanel">
      <h2>Review Decision</h2>
      <div class="small">
        Export creates <code>postprocessing_diagnostic_review_log.reviewed.csv</code>.
        Decisions are metadata only until a separate dry-run or apply step consumes them.
      </div>
      <div class="reviewGrid">
        <div>
          <label for="reviewStatus">status</label>
          <select id="reviewStatus">${{statusOptions}}</select>
        </div>
        <div>
          <label for="reviewDecision">decision</label>
          <select id="reviewDecision">${{decisionSelectOptions}}</select>
        </div>
        <div>
          <label for="targetCandidateIds">target candidate ids</label>
          <input id="targetCandidateIds" value="${{esc(review.target_candidate_ids)}}" placeholder="optional; pipe-separated candidate ids">
        </div>
        <div>
          <label for="correctedBbox">corrected bbox xyxy</label>
          <input id="correctedBbox" value="${{esc(review.corrected_bbox_xyxy)}}" placeholder="optional; [x1,y1,x2,y2]">
        </div>
      </div>
      <label for="reviewNotes" class="small">notes</label>
      <textarea id="reviewNotes" placeholder="why this decision is correct">${{esc(review.review_notes)}}</textarea>
      <div class="reviewActions">
        <button id="saveReviewButton">Save Row</button>
        <button id="markReviewedButton">Mark Reviewed</button>
        <button id="clearReviewButton">Clear Row</button>
      </div>
    </section>
  `;
}}

function bindReviewPanel(row) {{
  byId('saveReviewButton').onclick = () => saveCurrentReview(row, false);
  byId('markReviewedButton').onclick = () => saveCurrentReview(row, true);
  byId('clearReviewButton').onclick = () => {{
    delete state[row.review_item_id];
    saveState();
    renderDetail();
    renderSummary();
    renderList();
  }};
}}

function saveCurrentReview(row, forceReviewed) {{
  const decision = byId('reviewDecision').value;
  let status = byId('reviewStatus').value || 'unreviewed';
  if (forceReviewed && status === 'unreviewed') status = 'reviewed';
  setRowReview(row, {{
    review_status: status,
    review_decision: decision,
    target_candidate_ids: byId('targetCandidateIds').value.trim(),
    corrected_bbox_xyxy: byId('correctedBbox').value.trim(),
    review_notes: byId('reviewNotes').value.trim(),
  }});
  renderDetail();
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
    ${{renderReviewPanel(row)}}
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
    <div class="candidateGrid">${{(row.candidates || []).map(candidate => candidateCard(candidate, row)).join('')}}</div>
  `;
  bindReviewPanel(row);
  renderList();
}}

function selectRow(index) {{
  currentIndex = index;
  renderDetail();
}}

function byId(id) {{
  return document.getElementById(id);
}}

function nextUnreviewed() {{
  const start = currentIndex + 1;
  const candidates = filteredRows.slice(start).concat(filteredRows.slice(0, start));
  const next = candidates.find(row => (currentReview(row).review_status || 'unreviewed') === 'unreviewed');
  if (!next) {{
    alert('No unreviewed rows remain in this filter.');
    return;
  }}
  currentIndex = filteredRows.indexOf(next);
  renderDetail();
}}

function csvEscape(value) {{
  const text = fmt(value);
  if (/[",\\n\\r]/.test(text)) return '"' + text.replace(/"/g, '""') + '"';
  return text;
}}

function exportCsv() {{
  const lines = [REVIEW_FIELDNAMES.join(',')];
  for (const row of rows) {{
    const review = currentReview(row);
    lines.push(REVIEW_FIELDNAMES.map(field => csvEscape(review[field])).join(','));
  }}
  const blob = new Blob([lines.join('\\n') + '\\n'], {{type: 'text/csv'}});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'postprocessing_diagnostic_review_log.reviewed.csv';
  link.click();
  URL.revokeObjectURL(url);
}}

function applyReviewLogValues() {{
  for (const row of rows) {{
    const defaults = defaultsFor(row);
    if (!defaults || !defaults.review_item_id) continue;
    const hasReview = defaults.review_status !== 'unreviewed' || defaults.review_decision || defaults.review_notes;
    if (!hasReview) continue;
    state[row.review_item_id] = {{...defaults}};
  }}
  saveState();
  renderSummary();
  renderList();
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
document.getElementById('nextUnreviewedButton').onclick = nextUnreviewed;
document.getElementById('exportCsvButton').onclick = exportCsv;
document.getElementById('applyReviewLogButton').onclick = applyReviewLogValues;

renderSummary();
renderFilter();
renderList();
renderDetail();
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a static reviewer for postprocessing diagnostic rows.")
    parser.add_argument("--diagnostic-dir", type=Path, default=DEFAULT_DIAGNOSTIC_DIR)
    parser.add_argument("--output-html", type=Path, default=None)
    parser.add_argument("--review-log", type=Path, default=None)
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
    review_log = args.review_log or diagnostic_dir / "postprocessing_diagnostic_review_log.csv"
    candidates_by_id = load_candidates(candidate_manifest)
    view_rows = build_view_rows(rows, candidates_by_id, output_html)
    review_rows = build_review_rows(rows, read_csv_by_id(review_log))
    attach_review_defaults(view_rows, review_rows)
    write_csv(review_log, review_rows, REVIEW_FIELDNAMES)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html_document(view_rows, summary, review_rows), encoding="utf-8")

    print("Postprocessing diagnostic reviewer")
    print(f"- rows: {len(view_rows)}")
    print(f"- candidate_manifest: {candidate_manifest}")
    print(f"- review_log: {review_log}")
    print(f"- output_html: {output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
