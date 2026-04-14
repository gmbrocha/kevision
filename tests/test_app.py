from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from revision_tool.exporter import ExportBlockedError, Exporter
from revision_tool.review import change_item_needs_attention
from revision_tool.scanner import RevisionScanner
from revision_tool.verification import VerificationProvider
from revision_tool.web import create_app
from revision_tool.workspace import WorkspaceStore


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

    ae113_items = [item for item in store.data.change_items if item.sheet_id == "AE113"]
    assert ae113_items
    assert any(item.cloud_candidate_id for item in ae113_items)
    visual_item = next(item for item in store.data.change_items if item.provenance["source"] == "visual-region")
    assert visual_item.provenance["extraction_method"].startswith("opencv-contour")
    assert visual_item.provenance["extraction_signal"] >= 0.0


def test_export_blocks_pending_attention_items(workspace_copy):
    store = WorkspaceStore(workspace_copy).load()
    with pytest.raises(ExportBlockedError):
        Exporter(store).export()


def test_export_only_approved_items_when_forced(workspace_copy):
    store = WorkspaceStore(workspace_copy).load()
    pending = next(item for item in store.data.change_items if item.status == "pending")
    store.update_change_item(pending.id, status="approved", reviewer_text="Verified approved scope")

    outputs = Exporter(store).export(force_attention=True)
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
    assert b"disabled" in settings.data


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


def test_verify_endpoint_with_mock_provider(workspace_copy):
    class MockProvider(VerificationProvider):
        def __init__(self):
            super().__init__(name="mock-openai")
            self.last_context = None

        @property
        def enabled(self) -> bool:
            return True

        def verify_change(self, change_item_id, context_bundle):
            self.last_context = context_bundle
            return {
                "verdict": "clarified",
                "corrected_text": "Reviewer-ready corrected text",
                "reasoning": "The candidate was clarified from the provided crop and narrative.",
                "confidence": 0.84,
                "warnings": [],
                "request_payload": {"mock": True},
            }

    provider = MockProvider()
    app = create_app(workspace_copy, verification_provider=provider)
    client = app.test_client()
    store = WorkspaceStore(workspace_copy).load()
    change = store.data.change_items[0]

    response = client.post(f"/changes/{change.id}/verify")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["verification"]["corrected_text"] == "Reviewer-ready corrected text"
    assert provider.last_context["change_item_id"] == change.id

    refreshed = WorkspaceStore(workspace_copy).load()
    record = refreshed.change_verifications(change.id)[0]
    apply_response = client.post(f"/changes/{change.id}/apply-verification/{record.id}")
    assert apply_response.status_code == 302

    reloaded = WorkspaceStore(workspace_copy).load()
    updated = reloaded.get_change_item(change.id)
    assert updated.reviewer_text == "Reviewer-ready corrected text"
    assert updated.status == "approved"
