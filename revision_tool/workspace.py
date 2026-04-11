from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .models import ChangeItem, CloudCandidate, PreflightIssue, SheetVersion, SourceDocument, VerificationRecord, WorkspaceData
from .utils import ensure_dir, json_dumps


class WorkspaceStore:
    def __init__(self, workspace_dir: Path | str):
        self.workspace_dir = Path(workspace_dir)
        self.assets_dir = ensure_dir(self.workspace_dir / "assets")
        self.page_dir = ensure_dir(self.assets_dir / "pages")
        self.crop_dir = ensure_dir(self.assets_dir / "crops")
        self.output_dir = ensure_dir(self.workspace_dir / "outputs")
        self.data_path = self.workspace_dir / "workspace.json"
        self.data = WorkspaceData()

    def create(self, input_dir: Path) -> "WorkspaceStore":
        ensure_dir(self.workspace_dir)
        self.data = WorkspaceData(
            input_dir=str(input_dir.resolve()),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.save()
        return self

    def load(self) -> "WorkspaceStore":
        if not self.data_path.exists():
            raise FileNotFoundError(f"Workspace not found at {self.data_path}")
        self.data = WorkspaceData.from_dict(__import__("json").loads(self.data_path.read_text(encoding="utf-8")))
        return self

    def save(self) -> None:
        self.data_path.write_text(json_dumps(self.data.to_dict()), encoding="utf-8")

    def page_path(self, stem: str) -> Path:
        return self.page_dir / f"{stem}.png"

    def crop_path(self, stem: str) -> Path:
        return self.crop_dir / f"{stem}.png"

    def get_sheet(self, sheet_version_id: str) -> SheetVersion:
        for sheet in self.data.sheets:
            if sheet.id == sheet_version_id:
                return sheet
        raise KeyError(sheet_version_id)

    def get_cloud(self, cloud_id: str) -> CloudCandidate:
        for cloud in self.data.clouds:
            if cloud.id == cloud_id:
                return cloud
        raise KeyError(cloud_id)

    def get_change_item(self, change_id: str) -> ChangeItem:
        for item in self.data.change_items:
            if item.id == change_id:
                return item
        raise KeyError(change_id)

    def sheet_clouds(self, sheet_version_id: str) -> list[CloudCandidate]:
        return [cloud for cloud in self.data.clouds if cloud.sheet_version_id == sheet_version_id]

    def sheet_changes(self, sheet_version_id: str) -> list[ChangeItem]:
        return [item for item in self.data.change_items if item.sheet_version_id == sheet_version_id]

    def change_verifications(self, change_id: str) -> list[VerificationRecord]:
        return [record for record in self.data.verifications if record.change_item_id == change_id]

    def get_document(self, document_id: str) -> SourceDocument:
        for document in self.data.documents:
            if document.id == document_id:
                return document
        raise KeyError(document_id)

    def document_issues(self, document_id: str) -> list[PreflightIssue]:
        return [issue for issue in self.data.preflight_issues if issue.document_id == document_id]

    def update_change_item(self, change_id: str, **changes) -> ChangeItem:
        updated: ChangeItem | None = None
        new_items: list[ChangeItem] = []
        for item in self.data.change_items:
            if item.id == change_id:
                updated = replace(item, **changes)
                new_items.append(updated)
            else:
                new_items.append(item)
        if updated is None:
            raise KeyError(change_id)
        self.data.change_items = new_items
        self.save()
        return updated

    def update_verification(self, verification_id: str, **changes) -> VerificationRecord:
        updated: VerificationRecord | None = None
        new_records: list[VerificationRecord] = []
        for record in self.data.verifications:
            if record.id == verification_id:
                updated = replace(record, **changes)
                new_records.append(updated)
            else:
                new_records.append(record)
        if updated is None:
            raise KeyError(verification_id)
        self.data.verifications = new_records
        self.save()
        return updated
