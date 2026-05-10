from __future__ import annotations

import io
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import fitz
import pytest

import backend.cli as cli_module
from backend.cli import approve_cloudhammer_detections, main as cli_main
from backend.cloudhammer_client.inference import ManifestCloudInferenceClient
from backend.cloudhammer_client.live_pipeline import CloudHammerRunResult
from backend.cloudhammer_client.schemas import CloudDetection
from backend.deliverables.excel_exporter import ExportBlockedError, Exporter
from backend.deliverables.review_packet import build_review_packet
from backend.projects import ProjectRecord, ProjectRegistry
from backend.revision_state.models import ChangeItem, CloudCandidate, NarrativeEntry, RevisionSet, SheetVersion
from backend.revision_state.page_classification import sheet_is_index_like
from backend.review import change_item_needs_attention
from backend.revision_state.tracker import RevisionScanner
from backend.scope_extraction import enrich_workspace_scope_text, extract_cloud_scope_text
from backend.utils import choose_best_sheet_id, parse_detail_ref
from backend.workspace import WorkspaceStore
from webapp.app import create_app, discipline_for_sheet


def write_minimal_drawing_pdf(path: Path, *, scope_text: str = "PROVIDE NEW GRAB BAR BLOCKING") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((60, 80), f"AE101 FIRST FLOOR PLAN {scope_text}", fontsize=12)
    page.insert_text((430, 720), "AE101", fontsize=14)
    page.insert_text((430, 742), "FIRST FLOOR PLAN", fontsize=10)
    document.save(path)
    document.close()


def register_workspace_project(workspace_dir: Path, *, name: str = "Test Project") -> None:
    store = WorkspaceStore(workspace_dir).load()
    registry = ProjectRegistry(workspace_dir).load()
    registry.projects = [
        ProjectRecord(
            id="test-project",
            name=name,
            workspace_dir=str(workspace_dir.resolve()),
            input_dir=store.data.input_dir,
            status="active",
            created_at=store.data.created_at,
        )
    ]
    registry.save()


def csrf_token_from(response) -> str:
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    if not match:
        match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', response.data)
    assert match
    return match.group(1).decode("utf-8")


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


def test_attention_helper_tolerates_malformed_extraction_signal():
    item = ChangeItem(
        id="change-1",
        sheet_version_id="sheet-1",
        cloud_candidate_id="cloud-1",
        sheet_id="AE101",
        detail_ref="Detail 1",
        raw_text="Scope",
        normalized_text="scope",
        provenance={"source": "visual-region", "extraction_signal": "not-a-number"},
    )

    assert not change_item_needs_attention(item)


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


def test_manifest_cloudhammer_client_returns_scaled_detections(tmp_path: Path):
    crop_path = tmp_path / "crop.png"
    crop_path.write_bytes(b"png")
    pdf_path = tmp_path / "revision.pdf"
    pdf_path.write_bytes(b"%PDF")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "candidate_id": "cand-1",
                "pdf_path": str(pdf_path),
                "page_number": 2,
                "page_width": 1000,
                "page_height": 500,
                "tight_crop_image_path": str(crop_path),
                "bbox_page_xywh": [100, 50, 200, 100],
                "whole_cloud_confidence": 0.91,
                "policy_bucket": "auto_deliverable_candidate",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sheet = SheetVersion(
        id="sheet-1",
        revision_set_id="rev-1",
        source_pdf=str(pdf_path),
        page_number=2,
        sheet_id="AE101",
        sheet_title="Preview",
        issue_date=None,
        render_path=str(tmp_path / "page.png"),
        width=500,
        height=250,
    )

    detections = ManifestCloudInferenceClient(manifest).detect(page=None, sheet=sheet)  # type: ignore[arg-type]

    assert len(detections) == 1
    assert detections[0].bbox == [50, 25, 100, 50]
    assert detections[0].image_path == str(crop_path.resolve())
    assert detections[0].extraction_method == "cloudhammer_manifest"


def test_manifest_cloudhammer_client_filters_release_and_bbox_noise(tmp_path: Path):
    pdf_path = tmp_path / "revision.pdf"
    pdf_path.write_bytes(b"%PDF")
    rows = [
        {
            "candidate_id": "valid",
            "pdf_path": str(pdf_path),
            "page_number": 1,
            "page_width": 100,
            "page_height": 50,
            "bbox_page_xyxy": [90, 40, 120, 80],
            "whole_cloud_confidence": 0.88,
            "policy_bucket": "auto_deliverable_candidate",
        },
        {
            "candidate_id": "rejected",
            "pdf_path": str(pdf_path),
            "page_number": 1,
            "page_width": 100,
            "page_height": 50,
            "bbox_page_xywh": [10, 10, 20, 20],
            "policy_bucket": "false_positive",
        },
        {
            "candidate_id": "invalid",
            "pdf_path": str(pdf_path),
            "page_number": 1,
            "page_width": 100,
            "page_height": 50,
            "bbox_page_xywh": [10, 10, -5, 20],
        },
        {
            "candidate_id": "missing-page",
            "pdf_path": str(pdf_path),
            "bbox_page_xywh": [10, 10, 20, 20],
        },
    ]
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    sheet = SheetVersion(
        id="sheet-1",
        revision_set_id="rev-1",
        source_pdf=str(pdf_path),
        page_number=1,
        sheet_id="AE101",
        sheet_title="Preview",
        issue_date=None,
        render_path=str(tmp_path / "page.png"),
        width=200,
        height=100,
    )

    client = ManifestCloudInferenceClient(manifest)
    detections = client.detect(page=None, sheet=sheet)  # type: ignore[arg-type]

    assert [item.metadata["cloudhammer_candidate_id"] for item in detections] == ["valid"]
    assert detections[0].bbox == [180, 80, 20, 20]
    assert client.stats["total_rows"] == 4
    assert client.stats["indexed_rows"] == 1
    assert client.stats["skipped_policy"] == 1
    assert client.stats["skipped_invalid_bbox"] == 1
    assert client.stats["skipped_missing_pdf_page"] == 1


def test_scan_reprocesses_cache_when_cloudhammer_manifest_changes(tmp_path: Path):
    input_dir = tmp_path / "input"
    workspace_dir = tmp_path / "workspace"
    pdf_path = input_dir / "Revision #1 - Test" / "drawing.pdf"
    write_minimal_drawing_pdf(pdf_path)

    initial = RevisionScanner(input_dir, workspace_dir).scan()
    assert initial.data.clouds == []

    crop_path = tmp_path / "crop.png"
    crop_path.write_bytes(b"png")
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "candidate_id": "live-1",
                "pdf_path": str(pdf_path),
                "page_number": 1,
                "bbox_page_xywh": [70, 70, 120, 80],
                "whole_cloud_confidence": 0.93,
                "policy_bucket": "auto_deliverable_candidate",
                "crop_image_path": str(crop_path),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    scanner = RevisionScanner(input_dir, workspace_dir, cloud_inference_client=ManifestCloudInferenceClient(manifest))
    refreshed = scanner.scan()

    assert scanner.cache_hits == 0
    assert len(refreshed.data.clouds) == 1
    assert refreshed.data.change_items[0].provenance["extraction_method"] == "cloudhammer_manifest"


def test_scan_records_invalid_pdf_as_diagnostic_without_crashing(tmp_path: Path):
    input_dir = tmp_path / "input"
    workspace_dir = tmp_path / "workspace"
    bad_pdf = input_dir / "Revision #1 - Bad Package" / "not-really.pdf"
    bad_pdf.parent.mkdir(parents=True)
    bad_pdf.write_bytes(b"not a valid pdf")

    store = RevisionScanner(input_dir, workspace_dir).scan()

    assert len(store.data.documents) == 1
    assert store.data.documents[0].page_count == 0
    assert store.data.documents[0].max_severity == "high"
    assert any(issue.code == "pdf_open_failed" for issue in store.data.preflight_issues)


def test_sheet_id_parser_prefers_repeated_plumbing_sheet_over_late_arch_reference():
    text = (
        "Drawing Number PL302 Existing 1st Floor Med Gas PL302 "
        "Refer to PL601 for symbols. Refer to drawing AE102 for phasing."
    )

    assert choose_best_sheet_id(text, preferred_prefixes=("PL", "P", "MP"), prefer_repeated=True) == "PL302"


def test_sheet_id_parser_supports_plain_plumbing_prefix():
    assert choose_best_sheet_id("Drawing Number P101 P101 Refer to AE102", preferred_prefixes=("PL", "P", "MP"), prefer_repeated=True) == "P101"
    assert parse_detail_ref("See 4/P101 for plumbing scope") == "4/P101"
    assert discipline_for_sheet("P101") == "Plumbing"


def test_plumbing_pdf_metadata_does_not_choose_late_arch_reference():
    pdf_path = Path.cwd() / "revision_sets" / "Revision #4 - Dental Air" / "260219 - VA Biloxi Rev 4_Plumbing 1.pdf"
    scanner = RevisionScanner.__new__(RevisionScanner)
    document = fitz.open(pdf_path)
    try:
        page = document[0]
        metadata = scanner._extract_sheet_metadata(page, page.get_text("text"), pdf_path)
    finally:
        document.close()

    assert metadata["sheet_id"] == "PL302"


def test_approve_cloudhammer_detections_only_marks_manifest_visual_items(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "workspace").create(tmp_path)
    store.data.change_items = [
        ChangeItem(
            id="cloud",
            sheet_version_id="s1",
            cloud_candidate_id="c1",
            sheet_id="AE101",
            detail_ref=None,
            raw_text="CloudHammer detected revision cloud",
            normalized_text="cloudhammer detected revision cloud",
            provenance={"source": "visual-region", "extraction_method": "cloudhammer_manifest"},
        ),
        ChangeItem(
            id="narrative",
            sheet_version_id="s1",
            cloud_candidate_id=None,
            sheet_id="AE101",
            detail_ref=None,
            raw_text="Narrative item",
            normalized_text="narrative item",
            provenance={"source": "narrative"},
        ),
    ]

    changed = approve_cloudhammer_detections(store)

    assert changed == 1
    assert store.data.change_items[0].status == "approved"
    assert store.data.change_items[1].status == "pending"


def test_workspace_persists_portable_relative_paths(tmp_path: Path):
    workspace_dir = tmp_path / "workspace"
    input_dir = workspace_dir / "input"
    input_dir.mkdir(parents=True)
    store = WorkspaceStore(workspace_dir).create(input_dir)
    project_pdf = Path.cwd() / "revision_sets" / "Revision #1 - Drawing Changes" / "Revision #1 - Drawing Changes.pdf"
    render_path = store.page_path("sheet-1")
    render_path.write_bytes(b"png")
    crop_path = store.crop_path("crop-1")
    crop_path.write_bytes(b"png")
    store.data.revision_sets = [
        RevisionSet(
            id="rev-1",
            label="Revision #1 - Drawing Changes",
            source_dir=str(project_pdf.parent),
            set_number=1,
            set_date=None,
            pdf_paths=[str(project_pdf)],
        )
    ]
    store.data.sheets = [
        SheetVersion(
            id="sheet-1",
            revision_set_id="rev-1",
            source_pdf=str(project_pdf),
            page_number=1,
            sheet_id="AE101",
            sheet_title="Plan",
            issue_date=None,
            render_path=str(render_path),
        )
    ]
    store.data.clouds = [
        CloudCandidate(
            id="cloud-1",
            sheet_version_id="sheet-1",
            bbox=[0, 0, 10, 10],
            image_path=str(crop_path),
            page_image_path=str(render_path),
            confidence=0.9,
            extraction_method="test",
            nearby_text="",
            detail_ref=None,
        )
    ]

    store.save()

    raw = store.data_path.read_text(encoding="utf-8")
    assert str(tmp_path) not in raw
    assert str(Path.cwd()) not in raw
    assert "revision_sets/" in raw
    assert "assets/pages/sheet-1.png" in raw
    assert "input" in raw

    loaded = WorkspaceStore(workspace_dir).load()
    assert Path(loaded.data.input_dir).resolve() == input_dir.resolve()
    assert Path(loaded.data.sheets[0].source_pdf).resolve() == project_pdf.resolve()
    assert Path(loaded.data.sheets[0].render_path).resolve() == render_path.resolve()
    assert Path(loaded.data.clouds[0].image_path).resolve() == crop_path.resolve()


def test_visual_region_signal_score_handles_cloudhammer_placeholder():
    scanner = RevisionScanner.__new__(RevisionScanner)
    sheet = SheetVersion(
        id="sheet-1",
        revision_set_id="rev-1",
        source_pdf="revision.pdf",
        page_number=1,
        sheet_id="AE101",
        sheet_title="Preview",
        issue_date=None,
    )

    score = scanner._signal_score("CloudHammer detected revision cloud. OCR/scope extraction is not wired yet.", sheet)

    assert score > 0.5


def test_scope_extraction_reads_pdf_text_near_cloud():
    document = fitz.open()
    page = document.new_page(width=300, height=200)
    page.insert_text((82, 95), "PROVIDE NEW GRAB BAR BLOCKING", fontsize=10)
    sheet = SheetVersion(
        id="sheet-1",
        revision_set_id="rev-1",
        source_pdf="revision.pdf",
        page_number=1,
        sheet_id="AE101",
        sheet_title="Preview",
        issue_date=None,
        width=300,
        height=200,
    )

    result = extract_cloud_scope_text(page, sheet, [70, 70, 95, 55])

    document.close()
    assert result.reason == "text-layer-near-cloud"
    assert result.signal > 0.7
    assert "PROVIDE NEW GRAB BAR BLOCKING" in result.text


def test_scope_extraction_keeps_nearby_text_local_to_cloud():
    document = fitz.open()
    page = document.new_page(width=300, height=220)
    page.insert_text((82, 95), "PROVIDE NEW GRAB BAR BLOCKING", fontsize=10)
    page.insert_text((10, 185), "REMOVE EXISTING FLOOR FINISH THROUGHOUT CORRIDOR AND PATCH WALLS", fontsize=10)
    sheet = SheetVersion(
        id="sheet-1",
        revision_set_id="rev-1",
        source_pdf="revision.pdf",
        page_number=1,
        sheet_id="AE101",
        sheet_title="Preview",
        issue_date=None,
        width=300,
        height=220,
    )

    result = extract_cloud_scope_text(page, sheet, [70, 70, 95, 55])

    document.close()
    assert "PROVIDE NEW GRAB BAR BLOCKING" in result.text
    assert "REMOVE EXISTING FLOOR FINISH" not in result.text
    assert result.context_bbox[1] > 40
    assert result.context_bbox[3] < 130


def test_scope_extraction_flags_cloud_without_readable_text():
    document = fitz.open()
    page = document.new_page(width=300, height=200)
    sheet = SheetVersion(
        id="sheet-1",
        revision_set_id="rev-1",
        source_pdf="revision.pdf",
        page_number=1,
        sheet_id="AE101",
        sheet_title="Preview",
        issue_date=None,
        width=300,
        height=200,
    )

    result = extract_cloud_scope_text(page, sheet, [70, 70, 95, 55])

    document.close()
    assert result.reason == "no-readable-text"
    assert result.signal < 0.3
    assert "No readable scope text" in result.text


def test_enrich_workspace_scope_text_updates_existing_cloud_items(tmp_path: Path):
    input_dir = tmp_path / "input"
    workspace_dir = tmp_path / "workspace"
    input_dir.mkdir()
    pdf_path = input_dir / "Revision #1" / "drawing.pdf"
    pdf_path.parent.mkdir()
    document = fitz.open()
    page = document.new_page(width=300, height=200)
    page.insert_text((82, 95), "PROVIDE NEW GRAB BAR BLOCKING", fontsize=10)
    document.save(pdf_path)
    document.close()
    store = WorkspaceStore(workspace_dir).create(input_dir)
    sheet = SheetVersion(
        id="sheet-1",
        revision_set_id="rev-1",
        source_pdf=str(pdf_path),
        page_number=1,
        sheet_id="AE101",
        sheet_title="Preview",
        issue_date=None,
        width=300,
        height=200,
    )
    cloud = CloudCandidate(
        id="cloud-1",
        sheet_version_id=sheet.id,
        bbox=[70, 70, 95, 55],
        image_path="crop.png",
        page_image_path="page.png",
        confidence=0.91,
        extraction_method="cloudhammer_manifest",
        nearby_text="Cloud Only - CloudHammer detected revision cloud.",
        detail_ref=None,
        metadata={"cloudhammer_candidate_id": "cand-1"},
    )
    item = ChangeItem(
        id="change-1",
        sheet_version_id=sheet.id,
        cloud_candidate_id=cloud.id,
        sheet_id=sheet.sheet_id,
        detail_ref=None,
        raw_text=cloud.nearby_text,
        normalized_text=cloud.nearby_text.lower(),
        reviewer_text=cloud.nearby_text,
        provenance={"source": "visual-region", "extraction_method": "cloudhammer_manifest"},
    )
    store.data.sheets = [sheet]
    store.data.clouds = [cloud]
    store.data.change_items = [item]
    store.save()

    changed = enrich_workspace_scope_text(store)

    assert changed == 1
    assert store.data.clouds[0].scope_reason == "text-layer-near-cloud"
    assert "PROVIDE NEW GRAB BAR BLOCKING" in store.data.change_items[0].raw_text
    assert store.data.change_items[0].reviewer_text == store.data.change_items[0].raw_text
    assert store.data.change_items[0].provenance["cloudhammer_candidate_id"] == "cand-1"


def test_export_refreshes_ocr_scope_text_before_workbook(tmp_path: Path):
    from openpyxl import load_workbook
    from PIL import Image

    input_dir = tmp_path / "input"
    workspace_dir = tmp_path / "workspace"
    pdf_path = input_dir / "Revision #1 - Drawing Changes" / "drawing.pdf"
    pdf_path.parent.mkdir(parents=True)
    document = fitz.open()
    page = document.new_page(width=300, height=200)
    page.insert_text((82, 95), "PROVIDE NEW GRAB BAR BLOCKING", fontsize=10)
    document.save(pdf_path)
    document.close()

    store = WorkspaceStore(workspace_dir).create(input_dir)
    render_path = store.page_path("sheet-1")
    crop_path = store.crop_path("cloud-1")
    Image.new("RGB", (300, 200), "white").save(render_path)
    Image.new("RGB", (120, 80), "white").save(crop_path)
    store.data.revision_sets = [
        RevisionSet(
            id="rev-1",
            label="Revision #1 - Drawing Changes",
            source_dir=str(pdf_path.parent),
            set_number=1,
            set_date="04/28/2026",
            pdf_paths=[str(pdf_path)],
        )
    ]
    store.data.sheets = [
        SheetVersion(
            id="sheet-1",
            revision_set_id="rev-1",
            source_pdf=str(pdf_path),
            page_number=1,
            sheet_id="AE101",
            sheet_title="Preview",
            issue_date="04/28/2026",
            render_path=str(render_path),
            width=300,
            height=200,
            status="active",
        )
    ]
    placeholder = "Cloud Only - CloudHammer detected revision cloud. OCR/scope extraction is not wired yet."
    store.data.clouds = [
        CloudCandidate(
            id="cloud-1",
            sheet_version_id="sheet-1",
            bbox=[70, 70, 95, 55],
            image_path=str(crop_path),
            page_image_path=str(render_path),
            confidence=0.91,
            extraction_method="cloudhammer_manifest",
            nearby_text=placeholder,
            detail_ref=None,
        )
    ]
    store.data.change_items = [
        ChangeItem(
            id="change-1",
            sheet_version_id="sheet-1",
            cloud_candidate_id="cloud-1",
            sheet_id="AE101",
            detail_ref=None,
            raw_text=placeholder,
            normalized_text=placeholder.lower(),
            provenance={"source": "visual-region", "extraction_method": "cloudhammer_manifest"},
            status="approved",
            reviewer_text=placeholder,
        )
    ]
    store.save()

    exporter = Exporter(store)
    outputs = exporter.export(force_attention=True)

    assert exporter.last_scope_enrichment_count >= 1
    assert "PROVIDE NEW GRAB BAR BLOCKING" in store.data.change_items[0].raw_text
    approved = json.loads((store.output_dir / "approved_changes.json").read_text(encoding="utf-8"))
    assert "PROVIDE NEW GRAB BAR BLOCKING" in approved[0]["text"]
    wb = load_workbook(outputs["revision_changelog_xlsx"])
    assert "PROVIDE NEW GRAB BAR BLOCKING" in wb["Sheet1"].cell(row=2, column=5).value
    assert "Review Flags" in wb.sheetnames
    flags = wb["Review Flags"]
    assert "PROVIDE NEW GRAB BAR BLOCKING" in flags.cell(row=2, column=15).value
    assert flags.cell(row=2, column=12).value == "text-layer-near-cloud"


def test_cloudhammer_manifest_clouds_get_visual_items_even_with_narratives():
    scanner = RevisionScanner.__new__(RevisionScanner)
    narrative = NarrativeEntry(
        id="narrative-1",
        revision_set_id="rev-1",
        source_pdf="revision.pdf",
        page_number=1,
        sheet_id="AE101",
        heading="Revision narrative",
        summary="Replace existing fixture.",
    )
    sheet = SheetVersion(
        id="sheet-1",
        revision_set_id="rev-1",
        source_pdf="revision.pdf",
        page_number=1,
        sheet_id="AE101",
        sheet_title="Preview",
        issue_date=None,
        narrative_entry_ids=[narrative.id],
    )
    clouds = [
        CloudCandidate(
            id="cloud-1",
            sheet_version_id=sheet.id,
            bbox=[0, 0, 10, 10],
            image_path="crop-1.png",
            page_image_path="page.png",
            confidence=0.9,
            extraction_method="cloudhammer_manifest",
            nearby_text="Cloud Only - CloudHammer detected revision cloud. candidate=c1",
            detail_ref=None,
        ),
        CloudCandidate(
            id="cloud-2",
            sheet_version_id=sheet.id,
            bbox=[20, 20, 10, 10],
            image_path="crop-2.png",
            page_image_path="page.png",
            confidence=0.8,
            extraction_method="cloudhammer_manifest",
            nearby_text="Cloud Only - CloudHammer detected revision cloud. candidate=c2",
            detail_ref=None,
        ),
    ]

    items = scanner._generate_change_items([narrative], [sheet], clouds)

    assert len(items) == 3
    assert Counter(item.provenance["source"] for item in items) == {"narrative": 1, "visual-region": 2}
    assert {item.cloud_candidate_id for item in items if item.provenance["source"] == "visual-region"} == {"cloud-1", "cloud-2"}


def test_review_state_restores_by_cloud_id_when_extracted_text_changes():
    scanner = RevisionScanner.__new__(RevisionScanner)
    scanner.previous_change_items = [
        ChangeItem(
            id="old",
            sheet_version_id="sheet-1",
            cloud_candidate_id="cloud-1",
            sheet_id="AE101",
            detail_ref=None,
            raw_text="CloudHammer detected revision cloud",
            normalized_text="cloudhammer detected revision cloud",
            status="approved",
            reviewer_text="Preserved reviewer edit",
        )
    ]
    new_item = ChangeItem(
        id="new",
        sheet_version_id="sheet-1",
        cloud_candidate_id="cloud-1",
        sheet_id="AE101",
        detail_ref=None,
        raw_text="Cloud Only - PROVIDE NEW GRAB BAR BLOCKING",
        normalized_text="cloud only - provide new grab bar blocking",
    )

    restored = scanner._restore_review_state([new_item])[0]

    assert restored.status == "approved"
    assert restored.reviewer_text == "Preserved reviewer edit"
    assert restored.raw_text == new_item.raw_text


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
    assert wb.sheetnames[:2] == ["Summary", "Sheet1"]
    assert "Review Flags" in wb.sheetnames
    summary_ws = wb["Summary"]
    assert summary_ws["A1"].value == "ScopeLedger Revision Review"
    assert summary_ws["B8"].value == "Revision Sets"
    assert summary_ws["B9"].value == len(store.data.revision_sets)
    ws = wb["Sheet1"]

    headers = [ws.cell(row=1, column=i).value for i in range(1, len(COLUMNS) + 1)]
    expected_headers = [header or None for header, _ in COLUMNS]
    assert headers == expected_headers, "Headers must mirror Kevin's mod_5_changelog.xlsx exactly (typo and trailing spaces preserved)"
    assert headers[9] == "Qoute Received?", "Preserve Kevin's typo verbatim until he renames the column"
    assert ws.freeze_panes == "A2"
    assert ws.sheet_view.showGridLines is False
    assert ws.cell(row=1, column=1).fill.fgColor.rgb.endswith("111827")

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
    review_ws = wb["Review Flags"]
    review_headers = [review_ws.cell(row=1, column=i).value for i in range(1, 16)]
    assert review_headers[:4] == ["Change ID", "Status", "Needs Review", "Review Reason"]
    assert review_ws.freeze_panes == "A2"


def test_crop_comparison_uses_previous_sheet_area(tmp_path: Path):
    from PIL import Image, ImageStat

    from backend.deliverables.crop_comparison import build_cloud_comparison_image, find_previous_sheet_version

    def write_color_pdf(path: Path, fill: tuple[float, float, float]) -> None:
        document = fitz.open()
        page = document.new_page(width=300, height=200)
        page.draw_rect(page.rect, color=fill, fill=fill)
        document.save(path)
        document.close()

    input_dir = tmp_path / "input"
    workspace_dir = tmp_path / "workspace"
    input_dir.mkdir()
    previous_pdf = input_dir / "previous.pdf"
    current_pdf = input_dir / "current.pdf"
    write_color_pdf(previous_pdf, (1, 0, 0))
    write_color_pdf(current_pdf, (0, 0, 1))

    store = WorkspaceStore(workspace_dir).create(input_dir)
    previous_sheet = SheetVersion(
        id="sheet-prev",
        revision_set_id="rev-1",
        source_pdf=str(previous_pdf),
        page_number=1,
        sheet_id="AE101",
        sheet_title="Plan",
        issue_date="04/01/2026",
        width=300,
        height=200,
    )
    current_sheet = SheetVersion(
        id="sheet-current",
        revision_set_id="rev-2",
        source_pdf=str(current_pdf),
        page_number=1,
        sheet_id="AE101",
        sheet_title="Plan",
        issue_date="04/15/2026",
        width=300,
        height=200,
    )
    store.data.revision_sets = [
        RevisionSet(id="rev-1", label="Revision #1", source_dir=str(input_dir), set_number=1, set_date="04/01/2026"),
        RevisionSet(id="rev-2", label="Revision #2", source_dir=str(input_dir), set_number=2, set_date="04/15/2026"),
    ]
    store.data.sheets = [previous_sheet, current_sheet]
    cloud = CloudCandidate(
        id="cloud-1",
        sheet_version_id=current_sheet.id,
        bbox=[80, 60, 80, 60],
        image_path="",
        page_image_path="",
        confidence=0.9,
        extraction_method="cloudhammer_manifest",
        nearby_text="",
        detail_ref=None,
    )

    previous = find_previous_sheet_version(
        current_sheet,
        store.data.sheets,
        {revision_set.id: revision_set for revision_set in store.data.revision_sets},
    )
    output = build_cloud_comparison_image(
        store,
        cloud=cloud,
        current_sheet=current_sheet,
        previous_sheet=previous,
        output_path=tmp_path / "comparison.png",
    )

    assert output and output.exists()
    with Image.open(output) as image:
        left_mean = ImageStat.Stat(image.crop((20, 60, image.width // 2 - 20, image.height - 20))).mean
        right_mean = ImageStat.Stat(image.crop((image.width // 2 + 20, 60, image.width - 20, image.height - 20))).mean
    assert left_mean[0] > left_mean[2], "previous panel should use the red previous PDF"
    assert right_mean[2] > right_mean[0], "current panel should use the blue current PDF"


def test_crop_comparison_requires_prior_real_revision_set():
    from backend.deliverables.crop_comparison import find_previous_sheet_version

    current_rev1 = SheetVersion(
        id="current-rev1",
        revision_set_id="rev-1",
        source_pdf="current.pdf",
        page_number=4,
        sheet_id="AE102",
        sheet_title="Second Floor Plan",
        issue_date="10/10/2025",
    )
    same_package_index = SheetVersion(
        id="index-rev1",
        revision_set_id="rev-1",
        source_pdf="current.pdf",
        page_number=1,
        sheet_id="AE102",
        sheet_title="SHEET INDEX - CONFORMED SET PAGE NO. SHEET NO. SHEET NAME AE102 2ND FLOOR PLAN X",
        issue_date="10/10/2025",
    )
    previous_real = SheetVersion(
        id="real-rev1",
        revision_set_id="rev-1",
        source_pdf="previous.pdf",
        page_number=4,
        sheet_id="AE102",
        sheet_title="Second Floor Plan",
        issue_date="08/15/2025",
    )
    current_rev2 = SheetVersion(
        id="current-rev2",
        revision_set_id="rev-2",
        source_pdf="current-rev2.pdf",
        page_number=4,
        sheet_id="AE102",
        sheet_title="Second Floor Plan",
        issue_date="10/10/2025",
    )
    revision_sets = {
        "rev-1": RevisionSet(id="rev-1", label="Revision #1", source_dir="", set_number=1, set_date="10/10/2025"),
        "rev-2": RevisionSet(id="rev-2", label="Revision #2", source_dir="", set_number=2, set_date="10/17/2025"),
    }

    assert find_previous_sheet_version(current_rev1, [same_package_index, current_rev1], revision_sets) is None

    previous = find_previous_sheet_version(current_rev2, [same_package_index, previous_real, current_rev2], revision_sets)

    assert previous == previous_real


def test_scanner_treats_revision_set_upload_as_rev1_and_skips_index_clouds(tmp_path: Path):
    class FakeCloudClient:
        name = "fake_clouds"
        cache_key = "fake_clouds"

        def detect(self, *, page, sheet):
            return [
                CloudDetection(
                    bbox=[60, 60, 120, 80],
                    confidence=0.95,
                    extraction_method="cloudhammer_manifest",
                    nearby_text="Detected revision region",
                )
            ]

    input_dir = tmp_path / "input"
    workspace_dir = tmp_path / "workspace"
    pdf_path = input_dir / "Revision Set 1" / "package.pdf"
    pdf_path.parent.mkdir(parents=True)
    document = fitz.open()
    index_page = document.new_page(width=600, height=800)
    index_page.insert_text((60, 80), "SHEET INDEX - CONFORMED SET PAGE NO. SHEET NO. SHEET NAME AE102 2ND FLOOR PLAN X", fontsize=10)
    index_page.insert_text((430, 720), "AE102", fontsize=14)
    real_page = document.new_page(width=600, height=800)
    real_page.insert_text((60, 80), "AE102 SECOND FLOOR PLAN PROVIDE NEW WALL PATCHING", fontsize=12)
    real_page.insert_text((430, 720), "AE102", fontsize=14)
    real_page.insert_text((430, 742), "SECOND FLOOR PLAN", fontsize=10)
    document.save(pdf_path)
    document.close()

    store = RevisionScanner(input_dir, workspace_dir, cloud_inference_client=FakeCloudClient()).scan()

    assert store.data.revision_sets[0].label == "Revision Set 1"
    assert store.data.revision_sets[0].set_number == 1
    assert len(store.data.sheets) == 2
    index_sheet = next(sheet for sheet in store.data.sheets if sheet_is_index_like(sheet))
    real_sheet = next(sheet for sheet in store.data.sheets if sheet.id != index_sheet.id)
    assert index_sheet.status == "superseded"
    assert real_sheet.status == "active"
    assert len(store.data.clouds) == 1
    assert store.data.clouds[0].sheet_version_id == real_sheet.id
    assert {item.sheet_version_id for item in store.data.change_items} == {real_sheet.id}


def test_revision_changelog_stacks_multiple_items_in_same_cloud(tmp_path: Path):
    """Kevin confirmed same-cloud scope items can share one row if listed."""
    from openpyxl import load_workbook
    from PIL import Image

    from backend.deliverables.revision_changelog_excel import ROWS_PER_GROUP, write_revision_changelog

    store = WorkspaceStore(tmp_path / "workspace").create(tmp_path / "input")
    crop_path = tmp_path / "same_cloud.png"
    Image.new("RGB", (180, 100), "white").save(crop_path)
    store.data.revision_sets = [
        RevisionSet(
            id="rev-1",
            label="Revision #1 - Drawing Changes",
            source_dir=str(tmp_path),
            set_number=1,
            set_date="04/28/2026",
        )
    ]
    store.data.sheets = [
        SheetVersion(
            id="sheet-1",
            revision_set_id="rev-1",
            source_pdf=str(tmp_path / "revision.pdf"),
            page_number=1,
            sheet_id="AE101",
            sheet_title="Plan",
            issue_date="04/28/2026",
        )
    ]
    store.data.clouds = [
        CloudCandidate(
            id="cloud-1",
            sheet_version_id="sheet-1",
            bbox=[10, 20, 180, 100],
            image_path=str(crop_path),
            page_image_path="",
            confidence=0.9,
            extraction_method="test",
            nearby_text="",
            detail_ref=None,
        )
    ]
    store.data.change_items = [
        ChangeItem(
            id="item-1",
            sheet_version_id="sheet-1",
            cloud_candidate_id="cloud-1",
            sheet_id="AE101",
            detail_ref=None,
            raw_text="Install grab bar blocking",
            normalized_text="install grab bar blocking",
            status="approved",
            reviewer_text="Install grab bar blocking",
        ),
        ChangeItem(
            id="item-2",
            sheet_version_id="sheet-1",
            cloud_candidate_id="cloud-1",
            sheet_id="AE101",
            detail_ref=None,
            raw_text="Patch wall tile",
            normalized_text="patch wall tile",
            status="approved",
            reviewer_text="Patch wall tile",
        ),
    ]

    output_path = write_revision_changelog(store, tmp_path / "revision_changelog.xlsx")

    wb = load_workbook(output_path)
    assert wb.sheetnames[:2] == ["Summary", "Sheet1"]
    assert wb["Summary"]["B9"].value == 1
    ws = wb["Sheet1"]
    populated_drawings = [
        ws.cell(row=row, column=2).value
        for row in range(2, ws.max_row + 1)
        if ws.cell(row=row, column=2).value
    ]
    assert populated_drawings == ["AE-101"]
    assert ws.max_row == 1 + ROWS_PER_GROUP
    assert ws.cell(row=2, column=4).value == "N/A - Cloud Only "
    assert ws.cell(row=2, column=5).value == "1) Install grab bar blocking\n2) Patch wall tile"
    assert len(ws._images) == 1


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


def test_empty_project_registry_starts_without_demo(tmp_path: Path):
    app = create_app(tmp_path / "empty-seed-workspace")
    client = app.test_client()

    projects = client.get("/projects")
    assert projects.status_code == 200
    assert b"Demo Project" not in projects.data
    assert b"No active projects." in projects.data
    assert b"No project selected" in projects.data

    overview = client.get("/overview")
    assert overview.status_code == 200
    assert b"No project selected" in overview.data
    assert b"No revision packages have been loaded." in overview.data
    assert b"Choose PDF(s)" not in overview.data

    for path, expected in [
        ("/sheets", b"No drawings match the current filters."),
        ("/changes", b"No changes match the current filters."),
        ("/conformed", b"No sheets match the current filter."),
        ("/export", b"No project workspace is selected."),
        ("/diagnostics", b"No PDFs have been scanned."),
        ("/settings", b"No historical review-assist records were found"),
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert expected in response.data

    populate = client.post("/workspace/populate")
    assert populate.status_code == 302
    assert populate.headers["Location"].endswith("/projects")


def test_production_app_requires_secret(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("SCOPELEDGER_WEBAPP_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="SCOPELEDGER_WEBAPP_SECRET"):
        create_app(tmp_path / "seed-workspace", production=True)


def test_cli_production_serve_requires_secret(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys):
    monkeypatch.delenv("SCOPELEDGER_WEBAPP_SECRET", raising=False)

    result = cli_main(["serve", str(tmp_path / "seed-workspace"), "--production"])

    captured = capsys.readouterr()
    assert result == 1
    assert "SCOPELEDGER_WEBAPP_SECRET" in captured.out


def test_cli_production_serve_uses_waitress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls = {}

    def fake_serve(app, *, host: str, port: int) -> None:
        calls["host"] = host
        calls["port"] = port
        calls["secret"] = app.secret_key
        calls["production"] = app.config["SCOPELEDGER_PRODUCTION"]

    monkeypatch.setenv("SCOPELEDGER_WEBAPP_SECRET", "test-production-secret")
    monkeypatch.setattr(cli_module, "serve_production_app", fake_serve)

    result = cli_main(["serve", str(tmp_path / "seed-workspace"), "--host", "127.0.0.1", "--port", "5055", "--production"])

    assert result == 0
    assert calls == {
        "host": "127.0.0.1",
        "port": 5055,
        "secret": "test-production-secret",
        "production": True,
    }


def test_cli_production_serve_rejects_public_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys):
    monkeypatch.setenv("SCOPELEDGER_WEBAPP_SECRET", "test-production-secret")

    result = cli_main(["serve", str(tmp_path / "seed-workspace"), "--host", "0.0.0.0", "--production"])

    captured = capsys.readouterr()
    assert result == 1
    assert "loopback host" in captured.out


def test_production_app_sets_release_cookie_and_security_headers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SCOPELEDGER_WEBAPP_SECRET", "test-production-secret")

    app = create_app(tmp_path / "seed-workspace", production=True)
    client = app.test_client()
    response = client.get("/projects")

    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert response.headers["Cache-Control"] == "no-store"


def test_production_post_requires_csrf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SCOPELEDGER_WEBAPP_SECRET", "test-production-secret")

    app = create_app(tmp_path / "seed-workspace", production=True)
    client = app.test_client()
    response = client.post("/projects", data={"name": "Blocked Project"})

    assert response.status_code == 400
    assert ProjectRegistry(tmp_path / "seed-workspace").load().projects == []


def test_production_project_creation_disables_custom_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SCOPELEDGER_WEBAPP_SECRET", "test-production-secret")
    app = create_app(tmp_path / "seed-workspace", production=True)
    client = app.test_client()
    projects = client.get("/projects")
    token = csrf_token_from(projects)
    assert b"Browse folder" not in projects.data

    response = client.post(
        "/projects",
        data={"name": "Unsafe Path", "workspace_dir": str(tmp_path / "elsewhere"), "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Custom workspace paths are disabled" in response.data
    assert ProjectRegistry(tmp_path / "seed-workspace").load().projects == []


def test_cli_reset_projects_clears_registry_without_deleting_workspace(tmp_path: Path):
    input_dir = tmp_path / "input"
    workspace_dir = tmp_path / "workspace"
    input_dir.mkdir()
    WorkspaceStore(workspace_dir).create(input_dir)
    register_workspace_project(workspace_dir)

    result = cli_main(["reset-projects", str(workspace_dir)])

    assert result == 0
    assert (workspace_dir / "workspace.json").exists()
    assert ProjectRegistry(workspace_dir).load().projects == []


def test_web_routes_render_without_ai(workspace_copy):
    app = create_app(workspace_copy)
    client = app.test_client()

    assert client.get("/").status_code == 302
    projects = client.get("/projects")
    assert projects.status_code == 200
    assert b"Project archive" in projects.data
    assert b"Workspace folder" in projects.data
    assert b"Browse folder" in projects.data
    assert b"Project name" in projects.data
    assert b"Initial package" not in projects.data
    assert b"Manual source path" not in projects.data
    assert b"Input folder" not in projects.data
    assert client.get("/overview").status_code == 200
    assert client.get("/sheets").status_code == 200
    queue = client.get("/changes")
    assert queue.status_code == 200
    assert b"Accept selected" in queue.data
    diagnostics = client.get("/diagnostics")
    assert diagnostics.status_code == 200
    assert b"Ingested PDF files" in diagnostics.data
    settings = client.get("/settings")
    assert settings.status_code == 200
    assert b"archived" in settings.data


def test_import_revision_sets_root_preserves_child_packages(tmp_path: Path):
    def write_pdf(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open()
        document.new_page(width=300, height=200)
        document.save(path)
        document.close()

    source_root = tmp_path / "revision_sets"
    write_pdf(source_root / "Revision #1 - Alpha" / "alpha.pdf")
    write_pdf(source_root / "Revision #2 - Beta" / "beta.pdf")

    app = create_app(tmp_path / "seed-workspace")
    client = app.test_client()
    created = client.post("/projects", data={"name": "Fresh Project"})
    assert created.status_code == 302

    imported = client.post("/packages/import", data={"source_path": str(source_root), "package_label": ""})
    assert imported.status_code == 302

    input_dir = tmp_path / "projects" / "fresh-project" / "input"
    assert (input_dir / "Revision #1 - Alpha" / "alpha.pdf").exists()
    assert (input_dir / "Revision #2 - Beta" / "beta.pdf").exists()
    assert not (input_dir / "revision_sets" / "Revision #1 - Alpha" / "alpha.pdf").exists()


def test_production_manual_import_allows_configured_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source_root = tmp_path / "revision_sets"
    write_minimal_drawing_pdf(source_root / "Revision #1 - Alpha" / "alpha.pdf")
    write_minimal_drawing_pdf(source_root / "Revision #2 - Beta" / "beta.pdf")
    monkeypatch.setenv("SCOPELEDGER_WEBAPP_SECRET", "test-production-secret")
    monkeypatch.setenv("SCOPELEDGER_ALLOWED_IMPORT_ROOTS", str(source_root))

    app = create_app(tmp_path / "seed-workspace", production=True)
    client = app.test_client()
    token = csrf_token_from(client.get("/projects"))
    created = client.post("/projects", data={"name": "Fresh Project", "csrf_token": token})
    assert created.status_code == 302

    imported = client.post("/packages/import", data={"source_path": str(source_root), "package_label": "", "csrf_token": token})

    assert imported.status_code == 302
    input_dir = tmp_path / "projects" / "fresh-project" / "input"
    assert (input_dir / "Revision #1 - Alpha" / "alpha.pdf").exists()
    assert (input_dir / "Revision #2 - Beta" / "beta.pdf").exists()


def test_production_manual_import_rejects_outside_allowed_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    allowed_root = tmp_path / "allowed_revision_sets"
    source_root = tmp_path / "outside_revision_sets"
    allowed_root.mkdir()
    write_minimal_drawing_pdf(source_root / "Revision #1 - Outside" / "outside.pdf")
    monkeypatch.setenv("SCOPELEDGER_WEBAPP_SECRET", "test-production-secret")
    monkeypatch.setenv("SCOPELEDGER_ALLOWED_IMPORT_ROOTS", str(allowed_root))

    app = create_app(tmp_path / "seed-workspace", production=True)
    client = app.test_client()
    token = csrf_token_from(client.get("/projects"))
    created = client.post("/projects", data={"name": "Fresh Project", "csrf_token": token})
    assert created.status_code == 302

    imported = client.post(
        "/packages/import",
        data={"source_path": str(source_root), "package_label": "", "csrf_token": token},
        follow_redirects=True,
    )

    assert imported.status_code == 200
    assert b"outside the configured production import allowlist" in imported.data
    input_dir = tmp_path / "projects" / "fresh-project" / "input"
    assert not (input_dir / "Revision #1 - Outside" / "outside.pdf").exists()


def test_chunked_browser_import_reconstructs_pdf_package(tmp_path: Path):
    payload = b"%PDF-1.7\n" + (b"0" * (8 * 1024 * 1024)) + b"\n%%EOF"
    app = create_app(tmp_path / "seed-workspace")
    client = app.test_client()
    created = client.post("/projects", data={"name": "Fresh Project"})
    assert created.status_code == 302

    init = client.post(
        "/uploads/chunked/init",
        json={
            "purpose": "import_package",
            "package_label": "Chunked Package",
            "files": [{"name": "large_package.pdf", "relative_path": "large_package.pdf", "size": len(payload)}],
        },
    )
    assert init.status_code == 200
    upload_id = init.get_json()["upload_id"]

    first_chunk = payload[: 8 * 1024 * 1024]
    second_chunk = payload[8 * 1024 * 1024 :]
    for index, chunk in enumerate([first_chunk, second_chunk]):
        response = client.post(
            "/uploads/chunked/chunk",
            data={
                "upload_id": upload_id,
                "file_index": "0",
                "chunk_index": str(index),
                "chunk": (io.BytesIO(chunk), f"chunk-{index}.part"),
            },
            content_type="multipart/form-data",
        )
        assert response.status_code == 200

    complete = client.post("/uploads/chunked/complete", json={"upload_id": upload_id})

    assert complete.status_code == 200
    input_dir = tmp_path / "projects" / "fresh-project" / "input"
    assert (input_dir / "Chunked Package" / "large_package.pdf").read_bytes() == payload
    assert not (tmp_path / "projects" / "fresh-project" / ".chunked_uploads" / upload_id).exists()


def test_chunked_upload_rejects_non_pdf(tmp_path: Path):
    app = create_app(tmp_path / "seed-workspace")
    client = app.test_client()
    created = client.post("/projects", data={"name": "Fresh Project"})
    assert created.status_code == 302

    response = client.post(
        "/uploads/chunked/init",
        json={
            "purpose": "import_package",
            "files": [{"name": "notes.txt", "relative_path": "notes.txt", "size": 10}],
        },
    )

    assert response.status_code == 400
    assert "Only PDF files" in response.get_json()["error"]


def test_production_chunked_upload_requires_csrf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SCOPELEDGER_WEBAPP_SECRET", "test-production-secret")
    app = create_app(tmp_path / "seed-workspace", production=True)
    client = app.test_client()
    token = csrf_token_from(client.get("/projects"))
    created = client.post("/projects", data={"name": "Fresh Project", "csrf_token": token})
    assert created.status_code == 302

    response = client.post(
        "/uploads/chunked/init",
        json={
            "purpose": "import_package",
            "files": [{"name": "drawing.pdf", "relative_path": "drawing.pdf", "size": 12}],
        },
    )

    assert response.status_code == 400
    assert "form token" in response.get_json()["error"]


def test_chunked_upload_respects_configured_size_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SCOPELEDGER_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))
    app = create_app(tmp_path / "seed-workspace")
    client = app.test_client()
    created = client.post("/projects", data={"name": "Fresh Project"})
    assert created.status_code == 302

    response = client.post(
        "/uploads/chunked/init",
        json={
            "purpose": "import_package",
            "files": [{"name": "huge.pdf", "relative_path": "huge.pdf", "size": 21 * 1024 * 1024}],
        },
    )

    assert response.status_code == 413
    assert "upload limit" in response.get_json()["error"]


def test_production_workspace_folder_dialog_is_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SCOPELEDGER_WEBAPP_SECRET", "test-production-secret")
    app = create_app(tmp_path / "seed-workspace", production=True)
    client = app.test_client()

    response = client.get("/system/dialog/workspace-folder")

    assert response.status_code == 404
    assert "disabled" in response.get_json()["error"]


def test_chunked_upload_abort_removes_temp_session(tmp_path: Path):
    payload = b"%PDF-1.7\n%%EOF"
    app = create_app(tmp_path / "seed-workspace")
    client = app.test_client()
    created = client.post("/projects", data={"name": "Fresh Project"})
    assert created.status_code == 302

    init = client.post(
        "/uploads/chunked/init",
        json={
            "purpose": "import_package",
            "files": [{"name": "cancel_me.pdf", "relative_path": "cancel_me.pdf", "size": len(payload)}],
        },
    )
    assert init.status_code == 200
    upload_id = init.get_json()["upload_id"]
    chunk = client.post(
        "/uploads/chunked/chunk",
        data={
            "upload_id": upload_id,
            "file_index": "0",
            "chunk_index": "0",
            "chunk": (io.BytesIO(payload), "cancel.part"),
        },
        content_type="multipart/form-data",
    )
    assert chunk.status_code == 200
    upload_dir = tmp_path / "projects" / "fresh-project" / ".chunked_uploads" / upload_id
    assert upload_dir.exists()

    abort = client.post("/uploads/chunked/abort", json={"upload_id": upload_id})

    assert abort.status_code == 200
    assert abort.get_json()["deleted"] is True
    assert not upload_dir.exists()


def test_chunked_upload_init_cleans_stale_temp_sessions(tmp_path: Path):
    app = create_app(tmp_path / "seed-workspace")
    client = app.test_client()
    created = client.post("/projects", data={"name": "Fresh Project"})
    assert created.status_code == 302
    upload_root = tmp_path / "projects" / "fresh-project" / ".chunked_uploads"
    stale_dir = upload_root / ("a" * 32)
    current_dir = upload_root / ("b" * 32)
    stale_dir.mkdir(parents=True)
    current_dir.mkdir(parents=True)
    (stale_dir / "metadata.json").write_text("{}", encoding="utf-8")
    (current_dir / "metadata.json").write_text("{}", encoding="utf-8")
    old_time = time.time() - (7 * 60 * 60)
    os.utime(stale_dir, (old_time, old_time))

    init = client.post(
        "/uploads/chunked/init",
        json={
            "purpose": "import_package",
            "files": [{"name": "fresh.pdf", "relative_path": "fresh.pdf", "size": 12}],
        },
    )

    assert init.status_code == 200
    assert not stale_dir.exists()
    assert current_dir.exists()


def test_chunked_browser_append_reconstructs_pdf(tmp_path: Path):
    input_dir = tmp_path / "input"
    workspace_dir = tmp_path / "workspace"
    revision_source_dir = input_dir / "Revision #1 - Base"
    write_minimal_drawing_pdf(revision_source_dir / "base.pdf", scope_text="BASE PACKAGE")
    store = WorkspaceStore(workspace_dir).create(input_dir)
    revision_set = RevisionSet(
        id="rev-1",
        label="Revision #1 - Base",
        source_dir=str(revision_source_dir),
        set_number=1,
        set_date="05/09/2026",
    )
    store.data.revision_sets = [revision_set]
    store.save()
    register_workspace_project(workspace_dir)

    app = create_app(workspace_dir)
    client = app.test_client()
    appended_source = tmp_path / "appendix.pdf"
    write_minimal_drawing_pdf(appended_source, scope_text="APPENDED VALID PDF")
    payload = appended_source.read_bytes()

    init = client.post(
        "/uploads/chunked/init",
        json={
            "purpose": "append_file",
            "revision_set_id": revision_set.id,
            "files": [{"name": "appendix.pdf", "relative_path": "appendix.pdf", "size": len(payload)}],
        },
    )
    assert init.status_code == 200
    upload_id = init.get_json()["upload_id"]
    chunk = client.post(
        "/uploads/chunked/chunk",
        data={
            "upload_id": upload_id,
            "file_index": "0",
            "chunk_index": "0",
            "chunk": (io.BytesIO(payload), "appendix.part"),
        },
        content_type="multipart/form-data",
    )
    assert chunk.status_code == 200

    complete = client.post("/uploads/chunked/complete", json={"upload_id": upload_id})

    assert complete.status_code == 200
    destination = WorkspaceStore(workspace_dir).load().resolve_path(revision_set.source_dir) / "appendix.pdf"
    assert destination.read_bytes() == payload


def test_manual_import_rejects_folder_without_pdfs(tmp_path: Path):
    source_root = tmp_path / "not-a-package"
    source_root.mkdir()
    (source_root / "notes.txt").write_text("not a drawing", encoding="utf-8")

    app = create_app(tmp_path / "seed-workspace")
    client = app.test_client()
    created = client.post("/projects", data={"name": "Fresh Project"})
    assert created.status_code == 302

    imported = client.post("/packages/import", data={"source_path": str(source_root), "package_label": ""})

    assert imported.status_code == 302
    input_dir = tmp_path / "projects" / "fresh-project" / "input"
    assert not (input_dir / "not-a-package" / "notes.txt").exists()


def test_populate_workspace_runs_cloudhammer_manifest_from_ui(tmp_path: Path):
    class FakeCloudHammerRunner:
        name = "fake_cloudhammer_live"

        def run(self, *, input_dir: Path, workspace_dir: Path) -> CloudHammerRunResult:
            pdf_path = next(input_dir.rglob("*.pdf"))
            run_dir = workspace_dir / "outputs" / "cloudhammer_live" / "fake"
            run_dir.mkdir(parents=True, exist_ok=True)
            crop_path = run_dir / "crop.png"
            crop_path.write_bytes(b"png")
            pages_manifest = run_dir / "pages_manifest.jsonl"
            pages_manifest.write_text(
                json.dumps(
                    {
                        "page_kind": "drawing",
                        "pdf_path": str(pdf_path),
                        "pdf_stem": pdf_path.stem,
                        "page_index": 0,
                        "page_number": 1,
                        "render_path": str(run_dir / "render.png"),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            candidate_manifest = run_dir / "whole_cloud_candidates_manifest.jsonl"
            candidate_manifest.write_text(
                json.dumps(
                    {
                        "candidate_id": "fake-live-1",
                        "pdf_path": str(pdf_path),
                        "page_number": 1,
                        "bbox_page_xywh": [70, 70, 120, 80],
                        "whole_cloud_confidence": 0.91,
                        "policy_bucket": "auto_deliverable_candidate",
                        "crop_image_path": str(crop_path),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return CloudHammerRunResult(
                run_dir=run_dir,
                pages_manifest=pages_manifest,
                candidate_manifest=candidate_manifest,
                page_count=1,
                candidate_count=1,
            )

    app = create_app(tmp_path / "seed-workspace", cloudhammer_runner=FakeCloudHammerRunner())
    client = app.test_client()
    created = client.post("/projects", data={"name": "Fresh Project"})
    assert created.status_code == 302

    input_dir = tmp_path / "projects" / "fresh-project" / "input"
    write_minimal_drawing_pdf(input_dir / "Revision #1 - Test" / "drawing.pdf")

    populated = client.post("/workspace/populate")

    assert populated.status_code == 302
    store = WorkspaceStore(tmp_path / "projects" / "fresh-project").load()
    assert len(store.data.clouds) == 1
    assert any(item.provenance.get("extraction_method") == "cloudhammer_manifest" for item in store.data.change_items)
    assert store.data.populate_status["cloudhammer_page_count"] == 1
    assert store.data.populate_status["cloudhammer_candidate_count"] == 1


def test_populate_status_endpoint_reports_staged_and_live_artifacts(tmp_path: Path):
    app = create_app(tmp_path / "seed-workspace")
    client = app.test_client()
    created = client.post("/projects", data={"name": "Fresh Project"})
    assert created.status_code == 302

    workspace_dir = tmp_path / "projects" / "fresh-project"
    input_dir = workspace_dir / "input"
    write_minimal_drawing_pdf(input_dir / "Revision #1 - Test" / "drawing.pdf")
    run_dir = workspace_dir / "outputs" / "cloudhammer_live" / "run_test"
    run_dir.mkdir(parents=True)
    (run_dir / "pages_manifest.jsonl").write_text(json.dumps({"page_kind": "drawing"}) + "\n", encoding="utf-8")
    candidates_dir = run_dir / "whole_cloud_candidates"
    candidates_dir.mkdir()
    (candidates_dir / "whole_cloud_candidates_manifest.jsonl").write_text(json.dumps({"candidate_id": "c1"}) + "\n", encoding="utf-8")
    store = WorkspaceStore(workspace_dir).load()
    store.update_populate_status(
        state="running",
        stage="drawing_analysis",
        message="Analyzing staged drawing packages.",
    )

    response = client.get("/workspace/populate/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state"] == "running"
    assert payload["staged_pdf_count"] == 1
    assert payload["staged_package_count"] == 1
    assert payload["live_artifact_count"] == 2
    assert payload["inferred_cloudhammer_page_count"] == 1
    assert payload["inferred_cloudhammer_candidate_count"] == 1


def test_dashboard_exposes_populate_polling_hooks(tmp_path: Path):
    app = create_app(tmp_path / "seed-workspace")
    client = app.test_client()
    created = client.post("/projects", data={"name": "Fresh Project"})
    assert created.status_code == 302

    response = client.get("/overview")

    assert response.status_code == 200
    assert b"js-populate-form" in response.data
    assert b'data-status-url="/workspace/populate/status"' in response.data
    assert b'data-populate-status-url="/workspace/populate/status"' in response.data
    assert b"Staged PDFs" in response.data
    assert b"Live artifacts" in response.data


def test_review_routes_reject_invalid_status_and_external_redirect(workspace_copy):
    app = create_app(workspace_copy)
    client = app.test_client()
    store = WorkspaceStore(workspace_copy).load()
    item = next(item for item in store.data.change_items if item.status == "pending")

    response = client.post(
        f"/changes/{item.id}/review",
        data={
            "status_override": "surprise",
            "reviewer_text": item.raw_text,
            "reviewer_notes": "",
            "redirect_to": "https://example.com/owned",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/changes/{item.id}")
    refreshed = WorkspaceStore(workspace_copy).load()
    assert refreshed.get_change_item(item.id).status == "pending"

    bulk = client.post(
        "/changes/bulk-review",
        data={"change_ids": [item.id], "status": "approved", "redirect_to": "https://example.com/owned"},
    )
    assert bulk.status_code == 302
    assert bulk.headers["Location"].endswith("/changes")


def test_project_asset_route_blocks_non_generated_files(workspace_copy):
    app = create_app(workspace_copy)
    client = app.test_client()

    response = client.get("/project-assets/docs/CURRENT_STATE.md")

    assert response.status_code == 404


def test_change_detail_uses_previous_current_comparison_asset(tmp_path: Path):
    def write_color_pdf(path: Path, fill: tuple[float, float, float]) -> None:
        document = fitz.open()
        page = document.new_page(width=300, height=200)
        page.draw_rect(page.rect, color=fill, fill=fill)
        document.save(path)
        document.close()

    input_dir = tmp_path / "input"
    workspace_dir = tmp_path / "workspace"
    input_dir.mkdir()
    previous_pdf = input_dir / "previous.pdf"
    current_pdf = input_dir / "current.pdf"
    write_color_pdf(previous_pdf, (1, 0, 0))
    write_color_pdf(current_pdf, (0, 0, 1))
    store = WorkspaceStore(workspace_dir).create(input_dir)
    store.data.revision_sets = [
        RevisionSet(id="rev-1", label="Revision #1", source_dir=str(input_dir), set_number=1, set_date="04/01/2026"),
        RevisionSet(id="rev-2", label="Revision #2", source_dir=str(input_dir), set_number=2, set_date="04/15/2026"),
    ]
    previous_sheet = SheetVersion(
        id="sheet-prev",
        revision_set_id="rev-1",
        source_pdf=str(previous_pdf),
        page_number=1,
        sheet_id="AE101",
        sheet_title="Plan",
        issue_date="04/01/2026",
        width=300,
        height=200,
        status="superseded",
    )
    current_sheet = SheetVersion(
        id="sheet-current",
        revision_set_id="rev-2",
        source_pdf=str(current_pdf),
        page_number=1,
        sheet_id="AE101",
        sheet_title="Plan",
        issue_date="04/15/2026",
        width=300,
        height=200,
        status="active",
    )
    cloud = CloudCandidate(
        id="cloud-1",
        sheet_version_id=current_sheet.id,
        bbox=[80, 60, 80, 60],
        image_path="",
        page_image_path="",
        confidence=0.9,
        extraction_method="cloudhammer_manifest",
        nearby_text="Cloud Only",
        detail_ref=None,
    )
    store.data.sheets = [previous_sheet, current_sheet]
    store.data.clouds = [cloud]
    store.data.change_items = [
        ChangeItem(
            id="change-1",
            sheet_version_id=current_sheet.id,
            cloud_candidate_id=cloud.id,
            sheet_id=current_sheet.sheet_id,
            detail_ref=None,
            raw_text="Cloud Only",
            normalized_text="cloud only",
            provenance={"source": "visual-region", "extraction_method": "cloudhammer_manifest"},
        )
    ]
    store.save()
    register_workspace_project(workspace_dir)

    app = create_app(workspace_dir)
    client = app.test_client()
    response = client.get("/changes/change-1")
    assert response.status_code == 200
    assert b"/workspace-assets/cloud-comparisons/cloud-1.png" in response.data

    image_response = client.get("/workspace-assets/cloud-comparisons/cloud-1.png")
    assert image_response.status_code == 200
    assert image_response.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_dashboard_shows_pricing_readiness_panel(workspace_copy):
    store = WorkspaceStore(workspace_copy).load()
    store.update_populate_status(
        state="done",
        stage="complete",
        message="Workspace is populated and ready for review.",
        package_count=2,
        document_count=2,
        sheet_count=len(store.data.sheets),
        cloud_count=len(store.data.clouds),
        change_item_count=len(store.data.change_items),
        cache_hits=2,
    )
    app = create_app(workspace_copy)
    client = app.test_client()
    response = client.get("/overview")
    assert response.status_code == 200
    body = response.data
    assert b"Revision packages" in body
    assert b"Export readiness" in body
    assert b"Pending review" in body
    assert b"Accepted" in body
    assert b"Needs check" in body
    assert b"Project Files and Packages" in body
    assert b"Choose PDF(s)" in body
    assert b"Choose folder" in body
    assert b"Manual server path" in body
    assert b'name="package_files"' in body
    assert b'name="append_files"' in body
    assert b"Populate Workspace" in body
    assert b"Populate status" in body
    assert b"Workspace is populated and ready for review." in body
    assert b"Cache hits" in body


def test_dashboard_and_export_link_generated_artifacts(workspace_copy):
    store = WorkspaceStore(workspace_copy).load()
    Exporter(store).export(force_attention=True)
    packet = build_review_packet(store)

    app = create_app(workspace_copy)
    client = app.test_client()

    dashboard = client.get("/overview")
    assert dashboard.status_code == 200
    assert b"Open Workbook" not in dashboard.data
    assert b"Open Review Packet" not in dashboard.data

    export = client.get("/export")
    assert export.status_code == 200
    assert b"Open Workbook" in export.data
    assert b'href="/outputs/revision_changelog.xlsx"' in export.data
    assert b"Re-generate workbook" in export.data
    assert b"Open Review Packet" in export.data
    assert b'href="/outputs/revision_changelog_review_packet.html"' in export.data
    assert b"Refresh Review Packet" in export.data
    assert b"Open Google Drive Folder" in export.data

    workbook_response = client.get("/outputs/revision_changelog.xlsx")
    assert workbook_response.status_code == 200
    assert workbook_response.data[:2] == b"PK"

    packet_response = client.get(f"/outputs/{packet.html_path.name}")
    assert packet_response.status_code == 200
    assert b"ScopeLedger Review Packet" in packet_response.data


def test_conformed_page_lists_revised_sheets_by_default(workspace_copy):
    app = create_app(workspace_copy)
    client = app.test_client()

    response = client.get("/conformed")
    assert response.status_code == 200
    body = response.data
    assert b"Latest Set" in body
    assert b"Revised only" in body
    assert b"Revised" in body

    response_all = client.get("/conformed?show=all")
    assert response_all.status_code == 200
    assert response_all.data.count(b"conformed-card") >= response.data.count(b"conformed-card")


def test_navbar_includes_conformed_link(workspace_copy):
    app = create_app(workspace_copy)
    client = app.test_client()
    response = client.get("/projects")
    assert b'href="/conformed"' in response.data
    assert b"Latest Set" in response.data


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
    assert b"Save + Next" in detail.data

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
