from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "CloudHammer_v2"
DEFAULT_DIAGNOSTIC_DIR = V2_ROOT / "outputs" / "postprocessing_diagnostic_non_frozen_20260504"
DEFAULT_DRY_RUN_DIR = DEFAULT_DIAGNOSTIC_DIR / "dry_run_postprocessor_20260505"
GEOMETRY_FIELDNAMES = [
    "geometry_item_id",
    "item_type",
    "source_row_numbers",
    "source_candidate_ids",
    "review_status",
    "geometry_decision",
    "corrected_bbox_xyxy",
    "child_bboxes_json",
    "target_candidate_ids",
    "review_notes",
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_csv_by_id(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["geometry_item_id"]: row for row in csv.DictReader(handle) if row.get("geometry_item_id")}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GEOMETRY_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def split_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]


def join_ids(values: list[str]) -> str:
    return " | ".join(str(value) for value in values if str(value))


def normalize_xyxy(values: list[Any] | None) -> list[float]:
    if not isinstance(values, list) or len(values) != 4:
        return []
    x1, y1, x2, y2 = [float(value) for value in values]
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def round_box(values: list[Any] | None) -> list[float]:
    return [round(value, 3) for value in normalize_xyxy(values)]


def short_id(value: str) -> str:
    marker = "_whole_"
    index = value.find(marker)
    return value[index + 1 :] if index >= 0 else value[-28:]


def load_candidates(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("candidate_id")): row for row in read_jsonl(path) if row.get("candidate_id")}


def candidate_payload(candidate: dict[str, Any], html_path: Path) -> dict[str, Any]:
    return {
        "candidate_id": candidate.get("candidate_id"),
        "short_id": short_id(str(candidate.get("candidate_id") or "")),
        "bbox_page_xyxy": round_box(candidate.get("bbox_page_xyxy")),
        "crop_box_page_xyxy": round_box(candidate.get("crop_box_page_xyxy")),
        "member_boxes_page_xyxy": [round_box(box) for box in candidate.get("member_boxes_page_xyxy", [])],
        "confidence": candidate.get("whole_cloud_confidence") or candidate.get("confidence"),
        "size_bucket": candidate.get("size_bucket"),
        "member_count": candidate.get("member_count"),
        "group_fill_ratio": candidate.get("group_fill_ratio"),
        "crop_image_path": candidate.get("crop_image_path"),
        "crop_href": browser_path(candidate.get("crop_image_path"), html_path),
        "render_href": browser_path(candidate.get("render_path"), html_path),
        "render_path": candidate.get("render_path"),
        "pdf_path": candidate.get("pdf_path"),
    }


def plan_item_type(row: dict[str, Any]) -> str | None:
    schema = str(row.get("schema") or "")
    if schema.endswith("component_action.v1") and row.get("requires_manual_geometry"):
        return "merge_component_geometry"
    if not schema.endswith("row_action.v1"):
        return None
    action = row.get("proposed_action")
    if action == "manual_geometry_required":
        decision = row.get("review_decision")
        if decision == "tighten_adjust":
            return "tighten_adjust_geometry"
        return "expand_geometry"
    if action == "manual_split_required":
        return "split_geometry"
    return None


def geometry_decision_options(item_type: str) -> list[str]:
    if item_type == "merge_component_geometry":
        return ["component_bbox", "component_needs_split", "component_not_actionable", "unclear"]
    if item_type == "expand_geometry":
        return ["corrected_bbox", "merge_with_component", "not_actionable", "unclear"]
    if item_type == "tighten_adjust_geometry":
        return ["corrected_bbox", "not_actionable", "unclear"]
    if item_type == "split_geometry":
        return ["child_bboxes", "split_by_existing_candidates", "not_actionable", "unclear"]
    return ["not_actionable", "unclear"]


def geometry_item_id(item_type: str, row: dict[str, Any]) -> str:
    if item_type == "merge_component_geometry":
        return str(row.get("component_id"))
    return f"row_{int(row.get('row_number') or 0):03d}_{item_type}"


def source_row_numbers(item_type: str, row: dict[str, Any]) -> list[int]:
    if item_type == "merge_component_geometry":
        return [int(value) for value in row.get("review_row_numbers", [])] + [
            int(value) for value in row.get("blocking_or_followup_row_numbers", [])
        ]
    return [int(row.get("row_number") or 0)]


def source_candidate_ids(row: dict[str, Any]) -> list[str]:
    return [str(value) for value in row.get("source_candidate_ids") or row.get("candidate_ids") or []]


def build_geometry_items(
    plan_rows: list[dict[str, Any]],
    candidates: dict[str, dict[str, Any]],
    existing_log: dict[str, dict[str, str]],
    html_path: Path,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in plan_rows:
        item_type = plan_item_type(row)
        if item_type is None:
            continue
        item_id = geometry_item_id(item_type, row)
        saved = existing_log.get(item_id, {})
        candidate_ids = source_candidate_ids(row)
        source_rows = sorted(set(source_row_numbers(item_type, row)))
        candidate_rows = [candidate_payload(candidates[cid], html_path) for cid in candidate_ids if cid in candidates]
        default_bbox = row.get("proposed_bbox_xyxy") if item_type == "merge_component_geometry" else row.get("proposed_bbox_xyxy")
        items.append(
            {
                "geometry_item_id": item_id,
                "item_type": item_type,
                "source_row_numbers": source_rows,
                "source_candidate_ids": candidate_ids,
                "review_status": saved.get("review_status", "unreviewed"),
                "geometry_decision": saved.get("geometry_decision", ""),
                "corrected_bbox_xyxy": saved.get("corrected_bbox_xyxy", ""),
                "child_bboxes_json": saved.get("child_bboxes_json", ""),
                "target_candidate_ids": saved.get("target_candidate_ids", join_ids(candidate_ids)),
                "review_notes": saved.get("review_notes", ""),
                "decision_options": geometry_decision_options(item_type),
                "proposed_bbox_xyxy": round_box(default_bbox),
                "dry_run_notes": row.get("notes") or row.get("review_notes") or "",
                "blocked_reason": row.get("blocked_reason") or "",
                "geometry_status": row.get("geometry_status") or "",
                "review_decision": row.get("review_decision") or row.get("proposed_action") or "",
                "candidates": candidate_rows,
            }
        )
    return sorted(items, key=lambda item: (item["item_type"], item["source_row_numbers"], item["geometry_item_id"]))


def geometry_log_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append(
            {
                "geometry_item_id": item["geometry_item_id"],
                "item_type": item["item_type"],
                "source_row_numbers": " | ".join(str(value) for value in item["source_row_numbers"]),
                "source_candidate_ids": join_ids(item["source_candidate_ids"]),
                "review_status": item["review_status"],
                "geometry_decision": item["geometry_decision"],
                "corrected_bbox_xyxy": item["corrected_bbox_xyxy"],
                "child_bboxes_json": item["child_bboxes_json"],
                "target_candidate_ids": item["target_candidate_ids"],
                "review_notes": item["review_notes"],
            }
        )
    return rows


def summarize(items: list[dict[str, Any]], output_dir: Path, source_plan: Path, review_log: Path) -> dict[str, Any]:
    return {
        "schema": "cloudhammer_v2.postprocessing_geometry_reviewer_summary.v1",
        "geometry_items": len(items),
        "by_item_type": dict(sorted(Counter(item["item_type"] for item in items).items())),
        "by_review_status": dict(sorted(Counter(item["review_status"] for item in items).items())),
        "source_dry_run_plan": str(source_plan),
        "source_review_log": str(review_log),
        "output_dir": str(output_dir),
        "guardrails": [
            "review_artifact_only",
            "no_source_candidate_manifest_edits",
            "no_truth_label_edits",
            "no_eval_manifest_edits",
            "no_prediction_file_edits",
            "no_model_file_edits",
            "no_dataset_or_training_data_writes",
            "not_threshold_tuning",
        ],
    }


def markdown_summary(summary: dict[str, Any], html_path: Path, review_log: Path) -> str:
    lines = [
        "# Postprocessing Blocked-Geometry Reviewer",
        "",
        "Status: review artifact only. This viewer is seeded from the dry-run postprocessing plan and captures explicit geometry decisions for blocked expand, split, and merge-component cases.",
        "",
        "Safety: no source candidate manifest, labels, eval manifests, predictions, model files, datasets, training data, or threshold-tuning inputs are edited.",
        "",
        "## Queue",
        "",
        f"- geometry items: `{summary['geometry_items']}`",
    ]
    for key, value in summary["by_item_type"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "Review fatigue guardrail: queue size is between `10` and `50`; GPT-5.5 geometry prefill may be considered, but any geometry remains provisional until human accepted.",
            "",
            "## Artifacts",
            "",
            f"- viewer: `{html_path}`",
            f"- review log: `{review_log}`",
            f"- source dry-run plan: `{summary['source_dry_run_plan']}`",
            "",
            "Export reviewed geometry as `postprocessing_geometry_review.reviewed.csv` beside the template log.",
            "",
        ]
    )
    return "\n".join(lines)


def html_document(items: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    payload = json.dumps({"items": items, "summary": summary}, ensure_ascii=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CloudHammer Blocked Geometry Reviewer</title>
<style>
  :root {{
    font-family: Arial, sans-serif;
    color: #111;
    --border: #c8cdd3;
    --muted: #5b6570;
    --panel: #f6f7f9;
    --active: #fff4bf;
  }}
  body {{
    margin: 0;
    height: 100vh;
    display: grid;
    grid-template-columns: 360px 1fr;
    overflow: hidden;
  }}
  aside {{
    border-right: 1px solid var(--border);
    overflow: auto;
    background: var(--panel);
  }}
  main {{
    overflow: auto;
    padding: 18px;
  }}
  .toolbar {{
    position: sticky;
    top: 0;
    z-index: 2;
    display: flex;
    gap: 8px;
    align-items: center;
    padding: 10px;
    border-bottom: 1px solid var(--border);
    background: white;
  }}
  button, select, input, textarea {{
    font: inherit;
  }}
  button {{
    border: 1px solid #9199a3;
    background: white;
    padding: 6px 9px;
    cursor: pointer;
  }}
  .item {{
    padding: 10px;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    background: white;
  }}
  .item.active {{
    background: var(--active);
  }}
  .item .id {{
    font-family: Consolas, monospace;
    font-size: 11px;
    word-break: break-all;
  }}
  .pill {{
    display: inline-block;
    padding: 2px 5px;
    margin-right: 4px;
    border: 1px solid var(--border);
    background: #fff;
    font-size: 11px;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
    gap: 12px;
  }}
  .panel {{
    border: 1px solid var(--border);
    padding: 10px;
    background: white;
  }}
  .crop {{
    position: relative;
    max-height: 520px;
    overflow: auto;
    border: 1px solid var(--border);
    background: #fafafa;
  }}
  .crop-image-wrap {{
    position: relative;
    width: 100%;
  }}
  .crop img {{
    width: 100%;
    display: block;
  }}
  .overlay-box {{
    position: absolute;
    box-sizing: border-box;
    pointer-events: none;
    min-width: 5px;
    min-height: 5px;
  }}
  .overlay-label {{
    position: absolute;
    left: -1px;
    top: -18px;
    padding: 2px 4px;
    color: white;
    font: 11px Consolas, monospace;
    white-space: nowrap;
    background: var(--box-color);
  }}
  .box-active {{
    --box-color: #e11d48;
    border: 3px solid var(--box-color);
    background: rgba(225, 29, 72, 0.08);
  }}
  .box-other {{
    --box-color: #2563eb;
    border: 3px dashed var(--box-color);
    background: rgba(37, 99, 235, 0.06);
  }}
  .box-member {{
    --box-color: #f59e0b;
    border: 2px dashed var(--box-color);
  }}
  .box-proposed {{
    --box-color: #7c3aed;
    border: 3px dashed var(--box-color);
    background: rgba(124, 58, 237, 0.07);
  }}
  .box-corrected {{
    --box-color: #16a34a;
    border: 4px solid var(--box-color);
    background: rgba(22, 163, 74, 0.08);
  }}
  .box-child {{
    --box-color: #0891b2;
    border: 3px solid var(--box-color);
    background: rgba(8, 145, 178, 0.08);
  }}
  .legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 6px 0;
    font-size: 12px;
  }}
  .legend span {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }}
  .swatch {{
    width: 14px;
    height: 10px;
    border: 2px solid currentColor;
  }}
  .swatch.dashed {{
    border-style: dashed;
  }}
  .kv {{
    display: grid;
    grid-template-columns: 150px 1fr;
    gap: 4px 8px;
    font-size: 12px;
  }}
  .kv .label {{
    color: var(--muted);
  }}
  code {{
    font-family: Consolas, monospace;
    font-size: 11px;
  }}
  textarea {{
    width: 100%;
    min-height: 90px;
  }}
  input[type="text"] {{
    width: 100%;
    box-sizing: border-box;
  }}
  .form {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 10px;
    margin: 12px 0;
  }}
  .form label {{
    display: block;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 3px;
  }}
  .note {{
    color: var(--muted);
    font-size: 12px;
  }}
</style>
</head>
<body>
<aside>
  <div class="toolbar">
    <button id="exportBtn">Export CSV</button>
    <button id="clearBtn">Clear Local</button>
  </div>
  <div id="list"></div>
</aside>
<main id="detail"></main>
<script>
const DATA = {payload};
const STORAGE_KEY = "cloudhammer_postprocessing_geometry_review_v2:" + (DATA.summary.source_review_log || window.location.pathname);
const STATUSES = ["unreviewed", "gpt_prefilled", "reviewed", "needs_followup", "not_actionable"];
let activeIndex = 0;
let state = loadState();

function loadState() {{
  try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{{}}"); }}
  catch (_) {{ return {{}}; }}
}}
function saveState() {{
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}}
function esc(value) {{
  return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
}}
function current(item) {{
  return Object.assign({{
    geometry_item_id: item.geometry_item_id,
    item_type: item.item_type,
    source_row_numbers: (item.source_row_numbers || []).join(' | '),
    source_candidate_ids: (item.source_candidate_ids || []).join(' | '),
    review_status: item.review_status || 'unreviewed',
    geometry_decision: item.geometry_decision || '',
    corrected_bbox_xyxy: item.corrected_bbox_xyxy || '',
    child_bboxes_json: item.child_bboxes_json || '',
    target_candidate_ids: item.target_candidate_ids || '',
    review_notes: item.review_notes || ''
  }}, state[item.geometry_item_id] || {{}});
}}
function shortText(value, n=86) {{
  value = String(value || '');
  return value.length > n ? value.slice(0, n - 1) + '...' : value;
}}
function validBox(box) {{
  return Array.isArray(box) && box.length === 4 && box.every(value => Number.isFinite(Number(value)));
}}
function normalizeBox(box) {{
  const values = box.map(Number);
  return [Math.min(values[0], values[2]), Math.min(values[1], values[3]), Math.max(values[0], values[2]), Math.max(values[1], values[3])];
}}
function parseBoxText(value) {{
  if (!value) return [];
  try {{
    const parsed = JSON.parse(value);
    return validBox(parsed) ? normalizeBox(parsed) : [];
  }} catch (_) {{
    const matches = String(value).match(/-?\\d+(?:\\.\\d+)?/g) || [];
    if (matches.length < 4) return [];
    return normalizeBox(matches.slice(0, 4).map(Number));
  }}
}}
function parseChildBoxes(value) {{
  if (!value) return [];
  try {{
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(child => child && validBox(child.bbox_xyxy)).map((child, index) => ({{
      label: child.label || `child_${{index + 1}}`,
      bbox_xyxy: normalizeBox(child.bbox_xyxy)
    }}));
  }} catch (_) {{
    return [];
  }}
}}
function boxToStyle(box, cropBox) {{
  if (!validBox(box) || !validBox(cropBox)) return '';
  const b = normalizeBox(box);
  const c = normalizeBox(cropBox);
  const x1 = Math.max(b[0], c[0]);
  const y1 = Math.max(b[1], c[1]);
  const x2 = Math.min(b[2], c[2]);
  const y2 = Math.min(b[3], c[3]);
  const cropWidth = c[2] - c[0];
  const cropHeight = c[3] - c[1];
  if (x2 <= x1 || y2 <= y1 || cropWidth <= 0 || cropHeight <= 0) return '';
  return `left:${{((x1 - c[0]) / cropWidth) * 100}}%;top:${{((y1 - c[1]) / cropHeight) * 100}}%;width:${{((x2 - x1) / cropWidth) * 100}}%;height:${{((y2 - y1) / cropHeight) * 100}}%;`;
}}
function overlayBox(box, cropBox, className, label) {{
  const style = boxToStyle(box, cropBox);
  if (!style) return '';
  return `<div class="overlay-box ${{esc(className)}}" style="${{esc(style)}}"><span class="overlay-label">${{esc(label)}}</span></div>`;
}}
function renderList() {{
  const list = document.getElementById('list');
  list.innerHTML = DATA.items.map((item, index) => {{
    const review = current(item);
    return `<div class="item ${{index === activeIndex ? 'active' : ''}}" data-index="${{index}}">
      <div><span class="pill">${{esc(item.item_type)}}</span><span class="pill">${{esc(review.review_status)}}</span></div>
      <div class="id">${{esc(item.geometry_item_id)}}</div>
      <div class="note">rows ${{esc((item.source_row_numbers || []).join(', '))}}</div>
      <div class="note">${{esc(shortText(review.geometry_decision || 'no decision'))}}</div>
    </div>`;
  }}).join('');
  list.querySelectorAll('.item').forEach(node => {{
    node.addEventListener('click', () => {{
      activeIndex = Number(node.dataset.index);
      render();
    }});
  }});
}}
function candidatePanel(item, review, candidate, candidateIndex) {{
  const cropBox = candidate.crop_box_page_xyxy || [];
  const overlays = [];
  (item.candidates || []).forEach((other, otherIndex) => {{
    const isActive = other.candidate_id === candidate.candidate_id;
    overlays.push(overlayBox(other.bbox_page_xyxy, cropBox, isActive ? 'box-active' : 'box-other', isActive ? 'active' : (other.short_id || `other_${{otherIndex + 1}}`)));
  }});
  (candidate.member_boxes_page_xyxy || []).forEach((box, memberIndex) => {{
    overlays.push(overlayBox(box, cropBox, 'box-member', `member_${{memberIndex + 1}}`));
  }});
  if (validBox(item.proposed_bbox_xyxy || [])) {{
    overlays.push(overlayBox(item.proposed_bbox_xyxy, cropBox, 'box-proposed', 'proposed'));
  }}
  const correctedBox = parseBoxText(review.corrected_bbox_xyxy);
  if (validBox(correctedBox)) {{
    overlays.push(overlayBox(correctedBox, cropBox, 'box-corrected', 'review bbox'));
  }}
  parseChildBoxes(review.child_bboxes_json).forEach((child, childIndex) => {{
    overlays.push(overlayBox(child.bbox_xyxy, cropBox, 'box-child', child.label || `child_${{childIndex + 1}}`));
  }});
  const imageHtml = candidate.crop_href
    ? `<div class="crop-image-wrap"><img src="${{esc(candidate.crop_href)}}" alt="${{esc(candidate.candidate_id)}}">${{overlays.join('')}}</div>`
    : 'missing crop';
  return `<div class="panel">
    <div><strong>${{esc(candidate.short_id)}}</strong> <span class="note">crop ${{candidateIndex + 1}}</span></div>
    <div class="crop">${{imageHtml}}</div>
    <div class="kv">
      <div class="label">candidate_id</div><div><code>${{esc(candidate.candidate_id)}}</code></div>
      <div class="label">bbox_xyxy</div><div><code>${{esc(JSON.stringify(candidate.bbox_page_xyxy))}}</code></div>
      <div class="label">crop_box</div><div><code>${{esc(JSON.stringify(candidate.crop_box_page_xyxy))}}</code></div>
      <div class="label">member_count</div><div>${{esc(candidate.member_count)}}</div>
      <div class="label">fill_ratio</div><div>${{esc(candidate.group_fill_ratio)}}</div>
      <div class="label">render</div><div>${{candidate.render_href ? `<a href="${{esc(candidate.render_href)}}" target="_blank">open page render</a>` : ''}}</div>
    </div>
  </div>`;
}}
function saveActive() {{
  const item = DATA.items[activeIndex];
  state[item.geometry_item_id] = {{
    geometry_item_id: item.geometry_item_id,
    item_type: item.item_type,
    source_row_numbers: (item.source_row_numbers || []).join(' | '),
    source_candidate_ids: (item.source_candidate_ids || []).join(' | '),
    review_status: document.getElementById('reviewStatus').value,
    geometry_decision: document.getElementById('geometryDecision').value,
    corrected_bbox_xyxy: document.getElementById('correctedBbox').value.trim(),
    child_bboxes_json: document.getElementById('childBboxes').value.trim(),
    target_candidate_ids: document.getElementById('targetCandidateIds').value.trim(),
    review_notes: document.getElementById('reviewNotes').value.trim()
  }};
  saveState();
  renderList();
}}
function renderDetail() {{
  const item = DATA.items[activeIndex];
  const review = current(item);
  const statusOptions = STATUSES.map(status => `<option value="${{esc(status)}}" ${{status === review.review_status ? 'selected' : ''}}>${{esc(status)}}</option>`).join('');
  const decisionOptions = [''].concat(item.decision_options || []).map(decision => `<option value="${{esc(decision)}}" ${{decision === review.geometry_decision ? 'selected' : ''}}>${{esc(decision || 'choose decision')}}</option>`).join('');
  document.getElementById('detail').innerHTML = `
    <h2>${{esc(item.item_type)}} <code>${{esc(item.geometry_item_id)}}</code></h2>
    <div class="kv">
      <div class="label">source rows</div><div><code>${{esc((item.source_row_numbers || []).join(' | '))}}</code></div>
      <div class="label">source candidates</div><div><code>${{esc((item.source_candidate_ids || []).join(' | '))}}</code></div>
      <div class="label">dry-run status</div><div><code>${{esc(item.geometry_status)}}</code></div>
      <div class="label">review decision</div><div><code>${{esc(item.review_decision)}}</code></div>
      <div class="label">proposed bbox</div><div><code>${{esc(JSON.stringify(item.proposed_bbox_xyxy || []))}}</code></div>
      <div class="label">blocked reason</div><div><code>${{esc(item.blocked_reason)}}</code></div>
    </div>
    <div class="form">
      <div><label>status</label><select id="reviewStatus">${{statusOptions}}</select></div>
      <div><label>geometry decision</label><select id="geometryDecision">${{decisionOptions}}</select></div>
      <div><label>corrected_bbox_xyxy</label><input id="correctedBbox" type="text" value="${{esc(review.corrected_bbox_xyxy)}}" placeholder="[x1, y1, x2, y2]"></div>
      <div><label>target_candidate_ids</label><input id="targetCandidateIds" type="text" value="${{esc(review.target_candidate_ids)}}" placeholder="pipe-separated ids"></div>
    </div>
    <div><label class="note">child_bboxes_json</label><textarea id="childBboxes" placeholder='[{{"label":"child_1","bbox_xyxy":[x1,y1,x2,y2]}}]'>${{esc(review.child_bboxes_json)}}</textarea></div>
    <div><label class="note">review_notes</label><textarea id="reviewNotes">${{esc(review.review_notes || item.dry_run_notes || '')}}</textarea></div>
    <p><button id="saveBtn">Save Item</button> <span class="note">Export when done; local save is browser-only.</span></p>
    <h3>Candidate Crops</h3>
    <div class="legend">
      <span style="color:#e11d48"><i class="swatch"></i>active candidate</span>
      <span style="color:#2563eb"><i class="swatch dashed"></i>other candidate in item</span>
      <span style="color:#f59e0b"><i class="swatch dashed"></i>member detector box</span>
      <span style="color:#7c3aed"><i class="swatch dashed"></i>dry-run proposed</span>
      <span style="color:#16a34a"><i class="swatch"></i>review/GPT bbox</span>
      <span style="color:#0891b2"><i class="swatch"></i>review/GPT child box</span>
    </div>
    <div class="grid">${{(item.candidates || []).map((candidate, candidateIndex) => candidatePanel(item, review, candidate, candidateIndex)).join('')}}</div>
  `;
  ['reviewStatus','geometryDecision','correctedBbox','targetCandidateIds','childBboxes','reviewNotes'].forEach(id => {{
    document.getElementById(id).addEventListener('change', saveActive);
  }});
  document.getElementById('saveBtn').addEventListener('click', saveActive);
}}
function csvEscape(value) {{
  value = String(value ?? '');
  if (/[",\\r\\n]/.test(value)) return '"' + value.replace(/"/g, '""') + '"';
  return value;
}}
function exportCsv() {{
  const fields = {json.dumps(GEOMETRY_FIELDNAMES)};
  const rows = DATA.items.map(item => current(item));
  const csv = [fields.join(',')].concat(rows.map(row => fields.map(field => csvEscape(row[field])).join(','))).join('\\n') + '\\n';
  const blob = new Blob([csv], {{type: 'text/csv'}});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'postprocessing_geometry_review.reviewed.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}
function render() {{
  renderList();
  renderDetail();
}}
document.getElementById('exportBtn').addEventListener('click', exportCsv);
document.getElementById('clearBtn').addEventListener('click', () => {{
  if (confirm('Clear browser-local geometry review state?')) {{
    state = {{}};
    saveState();
    render();
  }}
}});
render();
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a static reviewer for blocked postprocessing geometry cases.")
    parser.add_argument("--diagnostic-dir", type=Path, default=DEFAULT_DIAGNOSTIC_DIR)
    parser.add_argument("--dry-run-dir", type=Path, default=DEFAULT_DRY_RUN_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--review-log", type=Path, default=None)
    parser.add_argument("--output-html", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.output_dir or args.dry_run_dir / "blocked_geometry_review"
    output_html = args.output_html or output_dir / "postprocessing_geometry_reviewer.html"
    review_log = args.review_log or output_dir / "postprocessing_geometry_review.csv"

    diagnostic_summary = read_json(args.diagnostic_dir / "postprocessing_diagnostic_summary.json")
    candidate_manifest = project_path(diagnostic_summary.get("source_candidate_manifest"))
    if candidate_manifest is None or not candidate_manifest.exists():
        raise FileNotFoundError(f"Candidate manifest not found: {diagnostic_summary.get('source_candidate_manifest')}")
    candidates = load_candidates(candidate_manifest)

    dry_run_plan = args.dry_run_dir / "postprocessing_dry_run_plan.jsonl"
    plan_rows = read_jsonl(dry_run_plan)
    existing_log = read_csv_by_id(review_log)
    items = build_geometry_items(plan_rows, candidates, existing_log, output_html)
    summary = summarize(items, output_dir, dry_run_plan, review_log)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(review_log, geometry_log_rows(items))
    write_json(output_dir / "postprocessing_geometry_reviewer_summary.json", summary)
    (output_dir / "postprocessing_geometry_reviewer_summary.md").write_text(
        markdown_summary(summary, output_html, review_log),
        encoding="utf-8",
    )
    output_html.write_text(html_document(items, summary), encoding="utf-8")

    print("Postprocessing blocked-geometry reviewer")
    print(f"- geometry_items: {len(items)}")
    print(f"- review_log: {review_log}")
    print(f"- output_html: {output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
