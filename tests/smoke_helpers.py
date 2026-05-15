from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from backend.cloudhammer_client.live_pipeline import CloudHammerRunResult
from backend.package_runs import build_package_run_record, cloudhammer_pipeline_fingerprint, package_pdf_fingerprints
from backend.projects import ProjectRecord, ProjectRegistry
from backend.revision_state.models import ChangeItem, CloudCandidate, RevisionSet, SheetVersion, StagedPackage
from backend.workspace import WorkspaceStore


@dataclass(frozen=True)
class SmokeWorkspace:
    app_data_dir: Path
    project: ProjectRecord
    store: WorkspaceStore


def write_smoke_pdf(path: Path, *, sheet_id: str = "PL505", title: str = "OVERALL SANITARY RISER") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page(width=400, height=240)
    page.insert_text((290, 200), sheet_id, fontsize=10)
    page.insert_text((180, 205), title, fontsize=9)
    page.draw_rect(fitz.Rect(80, 40, 200, 120), color=(0, 0, 0), width=1)
    document.save(path)
    document.close()


def build_smoke_workspace(app_data_dir: Path) -> SmokeWorkspace:
    registry = ProjectRegistry(app_data_dir).load()
    project = registry.create_project("Smoke Project")
    store = WorkspaceStore(project.workspace_dir).load()
    input_dir = Path(store.data.input_dir)

    revision_sets: list[RevisionSet] = []
    packages: list[StagedPackage] = []
    sheets: list[SheetVersion] = []
    clouds: list[CloudCandidate] = []
    changes: list[ChangeItem] = []

    for revision_number in (1, 2):
        package_id = f"pkg-r{revision_number}"
        revision_id = f"rev-{revision_number}"
        sheet_id = f"sheet-r{revision_number}"
        cloud_id = f"cloud-r{revision_number}"
        change_id = f"change-r{revision_number}"
        package_dir = input_dir / f"Revision #{revision_number} - Smoke"
        pdf_path = package_dir / f"smoke-r{revision_number}.pdf"
        write_smoke_pdf(pdf_path)

        render_path = store.page_path(sheet_id)
        crop_path = store.crop_path(cloud_id)
        _write_page_image(render_path, label=f"R{revision_number} PL505")
        _write_crop_image(crop_path, label=f"Cloud R{revision_number}")

        packages.append(
            StagedPackage(
                id=package_id,
                folder_name=package_dir.name,
                source_dir=str(package_dir),
                label=package_dir.name,
                revision_number=revision_number,
                created_at=_timestamp(),
                updated_at=_timestamp(),
            )
        )
        revision_sets.append(
            RevisionSet(
                id=revision_id,
                label=f"Revision #{revision_number} - Smoke",
                source_dir=str(package_dir),
                set_number=revision_number,
                set_date=f"05/{10 + revision_number:02d}/2026",
                pdf_paths=[str(pdf_path)],
            )
        )
        sheets.append(
            SheetVersion(
                id=sheet_id,
                revision_set_id=revision_id,
                source_pdf=str(pdf_path),
                page_number=1,
                sheet_id="PL505",
                sheet_title="OVERALL SANITARY RISER",
                issue_date=f"05/{10 + revision_number:02d}/2026",
                render_path=str(render_path),
                width=400,
                height=240,
                status="active",
            )
        )
        clouds.append(
            CloudCandidate(
                id=cloud_id,
                sheet_version_id=sheet_id,
                bbox=[80, 40, 120, 80],
                image_path=str(crop_path),
                page_image_path=str(render_path),
                confidence=0.91,
                extraction_method="cloudhammer_manifest",
                nearby_text=f"Cloud Only - Smoke scope revision {revision_number}",
                detail_ref=None,
                scope_text=f"Cloud Only - Smoke scope revision {revision_number}",
                scope_reason="smoke-fixture",
                scope_signal=0.9,
                scope_method="fixture",
                metadata={
                    "bbox_page_xywh": [80, 40, 120, 80],
                    "crop_box_page_xywh": [40, 20, 240, 160],
                    "page_width": 400,
                    "page_height": 240,
                },
            )
        )
        changes.append(
            ChangeItem(
                id=change_id,
                sheet_version_id=sheet_id,
                cloud_candidate_id=cloud_id,
                sheet_id="PL505",
                detail_ref=None,
                raw_text=f"Cloud Only - Smoke scope revision {revision_number}",
                normalized_text=f"cloud only - smoke scope revision {revision_number}",
                provenance={
                    "source": "visual-region",
                    "extraction_method": "cloudhammer_manifest",
                    "cloudhammer_candidate_id": cloud_id,
                },
                queue_order=float(revision_number),
            )
        )

    store.data.staged_packages = packages
    store.data.revision_sets = revision_sets
    store.data.sheets = sheets
    store.data.clouds = clouds
    store.data.change_items = changes
    store.data.populate_status = {"state": "done", "stage": "complete", "message": "Smoke workspace ready."}
    store.save()
    return SmokeWorkspace(app_data_dir=app_data_dir, project=project, store=store)


def mark_package_runs_complete(store: WorkspaceStore, runner: object) -> None:
    fingerprint = cloudhammer_pipeline_fingerprint(runner)
    package_runs = {}
    for package in store.data.staged_packages:
        run_dir = Path(store.workspace_dir) / "outputs" / "cloudhammer_live" / f"smoke_{package.id}"
        pages_manifest = run_dir / "pages_manifest.jsonl"
        candidate_manifest = run_dir / "whole_cloud_candidates" / "whole_cloud_candidates_manifest.jsonl"
        candidate_manifest.parent.mkdir(parents=True, exist_ok=True)
        pages_manifest.parent.mkdir(parents=True, exist_ok=True)
        pages_manifest.write_text(json.dumps({"package_id": package.id, "page_number": 1}) + "\n", encoding="utf-8")
        candidate_manifest.write_text(json.dumps({"package_id": package.id, "candidate_id": f"{package.id}-cloud"}) + "\n", encoding="utf-8")
        result = CloudHammerRunResult(
            run_dir=run_dir,
            pages_manifest=pages_manifest,
            candidate_manifest=candidate_manifest,
            page_count=1,
            candidate_count=1,
        )
        package_runs[package.id] = {
            **build_package_run_record(
                package,
                result,
                pdf_fingerprints=package_pdf_fingerprints(package),
                pipeline_fingerprint=fingerprint,
            ),
            "last_action": "reused",
        }
    store.data.package_runs = package_runs
    store.save()


def _write_page_image(path: Path, *, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (400, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 40, 200, 120), outline=(0, 0, 0), width=3)
    draw.text((12, 12), label, fill=(0, 0, 0))
    image.save(path)


def _write_crop_image(path: Path, *, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (200, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((35, 20, 165, 95), outline=(0, 0, 0), width=3)
    draw.text((12, 12), label, fill=(0, 0, 0))
    image.save(path)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
