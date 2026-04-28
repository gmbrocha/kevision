from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from backend.deliverables.excel_exporter import ExportBlockedError, Exporter
from backend.review import change_item_needs_attention
from backend.revision_state.tracker import RevisionScanner
from backend.workspace import WorkspaceStore
from webapp.app import create_app


def test_regression_fixture_metrics(workspace_copy):
    store = WorkspaceStore(workspace_copy).load()
    expected = json.loads((Path(__file__).parent / "fixtures" / "expected_workspace_metrics.json").read_text(encoding="utf-8"))
    actual = {
        "revision_sets": len(store.data.revision_sets),
        "documents": len(store.data.documents),
        "sheets": len(store.data.sheets),
        "clouds": len(store.data.clouds),
        "change_items": len(store.data.change_items),
        "preflight_issues": len(store.data.preflight_issues),
        "attention_items": len([item for item in store.data.change_items if change_item_needs_attention(item)]),
        "visual_methods": dict(
            Counter(
                item.provenance.get("extraction_method", "narrative")
                for item in store.data.change_items
                if item.provenance.get("source") == "visual-region"
            )
        ),
    }
    assert actual == expected


def test_scan_generates_supersedence_and_ae113(workspace_copy):
    store = WorkspaceStore(workspace_copy).load()
    assert len(store.data.revision_sets) == 2
    assert store.data.documents
    assert store.data.preflight_issues

    ae600_versions = [sheet for sheet in store.data.sheets if sheet.sheet_id == "AE600"]
    assert {sheet.status for sheet in ae600_versions} == {"active", "superseded"}

    assert store.data.clouds == []
    assert store.data.change_items
    assert {item.provenance["source"] for item in store.data.change_items} == {"narrative"}
    assert {item.sheet_id for item in store.data.change_items} >= {"AE107", "AE108", "AE109", "GI104"}


def test_export_does_not_block_without_attention_items(workspace_copy):
    store = WorkspaceStore(workspace_copy).load()
    outputs = Exporter(store).export()
    assert "revision_changelog_xlsx" in outputs


def test_export_only_approved_items_when_forced(workspace_copy):
    store = WorkspaceStore(workspace_copy).load()
    pending = next(item for item in store.data.change_items if item.status == "pending")
    store.update_change_item(pending.id, status="approved", reviewer_text="Verified approved scope")

    exporter = Exporter(store)
    outputs = exporter.export(force_attention=True)
    rows = json.loads((store.output_dir / "approved_changes.json").read_text(encoding="utf-8"))
    pricing_candidates = json.loads((store.output_dir / "pricing_change_candidates.json").read_text(encoding="utf-8"))
    pricing_log = json.loads((store.output_dir / "pricing_change_log.json").read_text(encoding="utf-8"))
    conformed_index = json.loads((store.output_dir / "conformed_sheet_index.json").read_text(encoding="utf-8"))
    diagnostics = json.loads((store.output_dir / "preflight_diagnostics.json").read_text(encoding="utf-8"))

    assert rows
    assert rows[0]["text"] == "Verified approved scope"
    assert pricing_candidates
    assert any(row["change_id"] == pending.id for row in pricing_candidates)
    assert pricing_log
    assert pricing_log[0]["pricing_status"] == "approved"
    assert pricing_log[0]["change_summary"] == "Verified approved scope"
    assert conformed_index
    assert any(row["latest_for_pricing"] for row in conformed_index)
    assert "conformed_preview_pdf" in outputs
    assert "pricing_change_candidates_csv" in outputs
    assert "pricing_change_log_csv" in outputs
    assert "conformed_sheet_index_csv" in outputs
    assert "preflight_diagnostics_csv" in outputs
    assert diagnostics["issues"]
    assert store.data.exports[-1]["forced_attention"] is True

    summary = exporter.last_summary
    assert summary["pricing_log_count"] == len(pricing_log)
    assert summary["pricing_candidate_count"] == len(pricing_candidates)
    assert summary["active_sheet_count"] == len([sheet for sheet in store.data.sheets if sheet.status == "active"])
    assert summary["superseded_sheet_count"] == len([sheet for sheet in store.data.sheets if sheet.status == "superseded"])
    assert summary["revision_set_count"] == len(store.data.revision_sets)
    assert store.data.exports[-1]["summary"] == summary


def test_revision_changelog_xlsx_matches_expected_layout(workspace_copy):
    """Smoke test that the revision changelog exporter preserves workbook shape."""
    from openpyxl import load_workbook

    from backend.deliverables.revision_changelog_excel import COLUMNS, ROWS_PER_GROUP

    store = WorkspaceStore(workspace_copy).load()
    first_pending, second_pending = store.data.change_items[:2]
    store.update_change_item(first_pending.id, status="approved", reviewer_text="Install gypsum board and corner bead")
    store.update_change_item(second_pending.id, status="approved", reviewer_text="Patch and repair masonry opening")

    outputs = Exporter(store).export(force_attention=True)
    xlsx_path = Path(outputs["revision_changelog_xlsx"])
    assert xlsx_path.exists(), "Revision changelog workbook should be written"
    assert xlsx_path.suffix == ".xlsx"

    wb = load_workbook(xlsx_path)
    ws = wb["Sheet1"]

    headers = [ws.cell(row=1, column=i).value for i in range(1, len(COLUMNS) + 1)]
    expected_headers = [header or None for header, _ in COLUMNS]
    assert headers == expected_headers, "Headers must mirror Kevin's mod_5_changelog.xlsx exactly (typo and trailing spaces preserved)"
    assert headers[9] == "Qoute Received?", "Preserve Kevin's typo verbatim until he renames the column"

    drawing_col_values = [ws.cell(row=r, column=2).value for r in range(2, ws.max_row + 1)]
    populated_drawings = [v for v in drawing_col_values if v]
    assert populated_drawings, "Should have at least one row of approved data"
    for value in populated_drawings:
        assert "-" in value, f"Drawing column should be hyphenated like AE-110, got {value!r}"

    correlations = [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1) if ws.cell(row=r, column=1).value]
    for corr in correlations:
        assert "." in corr, f"Correlation should be <sheet>.<seq>, got {corr!r}"

    detail_values = [ws.cell(row=r, column=4).value for r in range(2, ws.max_row + 1) if ws.cell(row=r, column=4).value]
    assert any("Cloud Only" in v or "Detail" in v for v in detail_values)

    assert ws.row_dimensions[2].height >= 16
    populated_row_count = sum(1 for v in drawing_col_values if v)
    assert (ws.max_row - 1) >= populated_row_count * ROWS_PER_GROUP - 1, "Each entry should reserve a vertical block for the embedded crop"

    assert ws.merged_cells.ranges, "Scope and Detail View columns should be merged within each block"
    assert not ws._images, "No embedded crop images are expected while CloudHammer inference is disconnected"


def test_pricing_outputs_filter_placeholder_revision_regions(workspace_copy):
    store = WorkspaceStore(workspace_copy).load()
    seed_item = next(item for item in store.data.change_items if item.status == "pending")
    placeholder_text = (
        f"Possible revision region near {seed_item.detail_ref}"
        if seed_item.detail_ref
        else "Possible revision region"
    )
    store.update_change_item(seed_item.id, status="approved", reviewer_text=placeholder_text)
    real_item = next(
        item
        for item in store.data.change_items
        if item.id != seed_item.id and item.status == "pending"
    )
    store.update_change_item(
        real_item.id,
        status="approved",
        reviewer_text="Patch and repair gypsum board, install new corner bead",
    )

    exporter = Exporter(store)
    exporter.export(force_attention=True)
    candidates = json.loads((store.output_dir / "pricing_change_candidates.json").read_text(encoding="utf-8"))
    log = json.loads((store.output_dir / "pricing_change_log.json").read_text(encoding="utf-8"))

    assert all(row["change_id"] != seed_item.id for row in candidates), "Placeholder rows should be filtered from candidates"
    assert all(row["change_id"] != seed_item.id for row in log), "Placeholder rows should never appear in the pricing log"
    assert any(row["change_id"] == real_item.id for row in log), "Real approved scope should still reach the pricing log"

    filtered = exporter.last_summary["filtered_by_reason"]
    assert filtered.get("placeholder-no-readable-scope", 0) >= 1


def test_pricing_relevance_filter_drops_label_locator_combos():
    exporter = Exporter.__new__(Exporter)
    cases = [
        ("AE113 First Floor Plan", ["ROOM", "RADIO"], "ROOM; RADIO", "visual-region", "pending"),
        ("AE125 Plan", ["AE600", "SEE DETAIL FOR"], "AE600; SEE DETAIL FOR", "visual-region", "pending"),
        ("AE125 Plan", ["WOMENS", "AE403"], "WOMENS; AE403", "visual-region", "pending"),
        ("AE125 Plan", ["FLOOR", "AE514"], "FLOOR; AE514", "visual-region", "pending"),
        ("AE125 Plan", ["SCHED", "GLAZING"], "SCHED; GLAZING", "visual-region", "pending"),
        ("AE125 Plan", ["5A127", "F-1"], "5A127; F-1", "visual-region", "pending"),
        ("AE125 Plan", ["5S/5NB-38"], "5S/5NB-38", "visual-region", "pending"),
    ]
    for title, scope_lines, combined, source_kind, status in cases:
        reason = exporter._pricing_relevance_reason(title, scope_lines, combined, source_kind, status)
        assert reason == "locator-only-text", f"expected locator filter for {scope_lines!r}, got {reason!r}"


def test_pricing_relevance_filter_keeps_real_pricing_scope():
    exporter = Exporter.__new__(Exporter)
    keep_cases = [
        ("AE113 Plan", ["FIRE CAULK ALL", "2 1/2\" MTL STUDS"], "FIRE CAULK ALL; 2 1/2\" MTL STUDS"),
        ("AE401 Plan", ["EXISTING", "CONC COLUMN"], "EXISTING; CONC COLUMN"),
        ("MP105 Plan", ["4\" CHWS", "SEE DETAIL"], "4\" CHWS; SEE DETAIL"),
        ("AE600 Plan", ["PLAN", "PARTITION PER CODE"], "PLAN; PARTITION PER CODE"),
        ("MP102 Plan", ["1\" HWR", "1\" HWS"], "1\" HWR; 1\" HWS"),
        ("MH104 Plan", ["HEPA FILTER RACK", "26X22 DOWN"], "HEPA FILTER RACK; 26X22 DOWN"),
    ]
    for title, scope_lines, combined in keep_cases:
        reason = exporter._pricing_relevance_reason(title, scope_lines, combined, "visual-region", "pending")
        assert reason == "likely-pricing-scope", f"expected keep for {scope_lines!r}, got {reason!r}"


def test_pricing_relevance_filter_drops_low_signal_text_without_scope_keywords():
    exporter = Exporter.__new__(Exporter)
    reason = exporter._pricing_relevance_reason(
        "AE125 Plan",
        ["6TH FLOOR 66'-0\""],
        "6TH FLOOR 66'-0\"",
        "visual-region",
        "pending",
    )
    assert reason in ("low-signal-no-scope-keyword", "locator-only-text")


def test_pricing_relevance_filter_trusts_reviewer_for_approved_items():
    exporter = Exporter.__new__(Exporter)
    reason = exporter._pricing_relevance_reason(
        "AE125 Plan",
        ["Approved scope per RFI"],
        "Approved scope per RFI",
        "visual-region",
        "approved",
    )
    assert reason == "reviewer-approved"


def test_pricing_relevance_filter_overrides_reviewer_for_placeholder_text():
    exporter = Exporter.__new__(Exporter)
    reason = exporter._pricing_relevance_reason(
        "AE113 Plan",
        ["Possible revision region near 3/AE113"],
        "Possible revision region near 3/AE113",
        "visual-region",
        "approved",
    )
    assert reason == "placeholder-no-readable-scope"


def test_cli_export_summary_is_human_readable():
    from backend.cli import format_export_summary

    summary = {
        "output_dir": "/tmp/workspace/outputs",
        "approved_count": 4,
        "pending_count": 2,
        "rejected_count": 1,
        "attention_pending_count": 1,
        "force_attention": True,
        "pricing_log_count": 3,
        "pricing_candidate_count": 5,
        "filtered_count": 9,
        "filtered_by_reason": {
            "placeholder-no-readable-scope": 6,
            "sheet-index-page": 3,
        },
        "active_sheet_count": 12,
        "superseded_sheet_count": 4,
        "revision_set_count": 2,
    }
    outputs = {
        "pricing_change_log_csv": "/tmp/workspace/outputs/pricing_change_log.csv",
        "pricing_change_candidates_csv": "/tmp/workspace/outputs/pricing_change_candidates.csv",
        "conformed_sheet_index_csv": "/tmp/workspace/outputs/conformed_sheet_index.csv",
        "conformed_preview_pdf": "/tmp/workspace/outputs/conformed_preview.pdf",
    }
    text = format_export_summary(summary, outputs, Path("/tmp/workspace"))

    assert "Pricing-ready rows" in text
    assert "3 items" in text
    assert "pricing_change_log.csv" in text
    assert "Conformed sheet set" in text
    assert "12 latest sheets" in text
    assert "Filtered out as noise" in text
    assert "clouded regions with no readable text" in text
    assert "WARNING" in text
    assert "python -m backend serve" in text


def test_web_routes_render_without_ai(workspace_copy):
    app = create_app(workspace_copy)
    client = app.test_client()

    assert client.get("/").status_code == 200
    assert client.get("/sheets").status_code == 200
    queue = client.get("/changes")
    assert queue.status_code == 200
    assert b"Bulk Action" in queue.data
    diagnostics = client.get("/diagnostics")
    assert diagnostics.status_code == 200
    assert b"Preflight Summary" in diagnostics.data
    settings = client.get("/settings")
    assert settings.status_code == 200
    assert b"archived" in settings.data


def test_dashboard_shows_pricing_readiness_panel(workspace_copy):
    app = create_app(workspace_copy)
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    body = response.data
    assert b"Pricing Readiness" in body
    assert b"Ready for Pricing" in body
    assert b"Candidates to Review" in body
    assert b"Conformed Sheets" in body
    assert b"Needs Attention" in body


def test_conformed_page_lists_revised_sheets_by_default(workspace_copy):
    app = create_app(workspace_copy)
    client = app.test_client()

    response = client.get("/conformed")
    assert response.status_code == 200
    body = response.data
    assert b"Conformed Sheet Set" in body
    assert b"Only sheets that were revised" in body
    assert b"latest" in body
    assert b"superseded" in body

    response_all = client.get("/conformed?show=all")
    assert response_all.status_code == 200
    assert response_all.data.count(b"conformed-card") >= response.data.count(b"conformed-card")


def test_navbar_includes_conformed_link(workspace_copy):
    app = create_app(workspace_copy)
    client = app.test_client()
    response = client.get("/")
    assert b'href="/conformed"' in response.data
    assert b">Conformed</a>" in response.data


def test_bulk_review_and_next_navigation(workspace_copy):
    app = create_app(workspace_copy)
    client = app.test_client()
    store = WorkspaceStore(workspace_copy).load()
    pending_items = [item for item in store.data.change_items if item.status == "pending"][:2]

    response = client.post(
        "/changes/bulk-review",
        data={"change_ids": [item.id for item in pending_items], "status": "approved", "redirect_to": "/changes?status=pending"},
    )
    assert response.status_code == 302

    refreshed = WorkspaceStore(workspace_copy).load()
    assert all(refreshed.get_change_item(item.id).status == "approved" for item in pending_items)

    remaining_pending = [item for item in refreshed.data.change_items if item.status == "pending"][:2]
    detail = client.get(f"/changes/{remaining_pending[0].id}?queue=pending")
    assert detail.status_code == 200
    assert b"Save + Next Pending" in detail.data

    advance = client.post(
        f"/changes/{remaining_pending[0].id}/review",
        data={
            "status": "approved",
            "reviewer_text": "Fast lane approval",
            "reviewer_notes": "",
            "queue_status": "pending",
            "search_query": "",
            "next_change_id": remaining_pending[1].id,
            "advance": "next",
        },
    )
    assert advance.status_code == 302
    assert advance.headers["Location"].endswith(f"/changes/{remaining_pending[1].id}?queue=pending&q=")

    reloaded = WorkspaceStore(workspace_copy).load()
    assert reloaded.get_change_item(remaining_pending[0].id).reviewer_text == "Fast lane approval"
    assert reloaded.get_change_item(remaining_pending[0].id).status == "approved"


def test_rescan_reuses_cache_and_preserves_review_state(workspace_copy):
    store = WorkspaceStore(workspace_copy).load()
    change = next(item for item in store.data.change_items if item.status == "pending")
    store.update_change_item(change.id, status="approved", reviewer_text="Preserved after rescan")
    render_path = Path(store.data.sheets[0].render_path)
    original_mtime = render_path.stat().st_mtime_ns
    input_dir = Path(store.data.input_dir)

    scanner = RevisionScanner(input_dir, workspace_copy)
    scanner.scan()

    reloaded = WorkspaceStore(workspace_copy).load()
    rescanned = reloaded.get_change_item(change.id)
    assert scanner.cache_hits == len(reloaded.data.documents)
    assert rescanned.status == "approved"
    assert rescanned.reviewer_text == "Preserved after rescan"
    assert render_path.stat().st_mtime_ns == original_mtime
    assert len(reloaded.data.scan_cache.get("documents", {})) == len(reloaded.data.documents)


def test_verify_endpoint_is_archived(workspace_copy):
    app = create_app(workspace_copy)
    client = app.test_client()
    store = WorkspaceStore(workspace_copy).load()
    change = store.data.change_items[0]

    response = client.post(f"/changes/{change.id}/verify")
    assert response.status_code == 400
    payload = response.get_json()
    assert "disabled" in payload["error"].lower() or "archived" in payload["error"].lower()
