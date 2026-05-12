from __future__ import annotations

import re
import shutil
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .utils import ensure_dir, json_dumps
from .workspace import WorkspaceStore


DEFAULT_APP_DATA_DIRNAME = "app_workspaces"


def default_app_data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / DEFAULT_APP_DATA_DIRNAME


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"


def _has_filesystem_link_marker(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = path.stat(follow_symlinks=False).st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


@dataclass
class ProjectRecord:
    id: str
    name: str
    workspace_dir: str
    input_dir: str
    status: str = "active"
    created_at: str = ""
    archived_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict) -> "ProjectRecord":
        return cls(
            id=payload["id"],
            name=payload["name"],
            workspace_dir=payload["workspace_dir"],
            input_dir=payload.get("input_dir", ""),
            status=payload.get("status", "active"),
            created_at=payload.get("created_at", ""),
            archived_at=payload.get("archived_at", ""),
        )


class ProjectRegistry:
    def __init__(self, app_data_dir: Path | str | None = None):
        self.app_data_dir = ensure_dir(Path(app_data_dir).resolve() if app_data_dir else default_app_data_dir().resolve())
        self.root_dir = self.app_data_dir
        self.projects_dir = ensure_dir(self.app_data_dir / "projects")
        self.data_path = self.app_data_dir / "projects.json"
        self.projects: list[ProjectRecord] = []

    def load(self) -> "ProjectRegistry":
        if self.data_path.exists():
            import json

            payload = json.loads(self.data_path.read_text(encoding="utf-8"))
            self.projects = [ProjectRecord.from_dict(item) for item in payload.get("projects", [])]
        else:
            self.projects = []
        return self

    def save(self) -> None:
        self.data_path.write_text(
            json_dumps({"projects": [asdict(project) for project in self.projects]}),
            encoding="utf-8",
        )

    def active_projects(self) -> list[ProjectRecord]:
        return [project for project in self.projects if project.status == "active"]

    def archived_projects(self) -> list[ProjectRecord]:
        return [project for project in self.projects if project.status == "archived"]

    def first_active(self) -> ProjectRecord | None:
        active = self.active_projects()
        if active:
            return active[0]
        return None

    def get(self, project_id: str) -> ProjectRecord:
        for project in self.projects:
            if project.id == project_id:
                return project
        raise KeyError(project_id)

    def create_project(self, name: str, input_dir: Path | str | None = None, workspace_dir: Path | str | None = None) -> ProjectRecord:
        base_slug = slugify(name)
        project_id = base_slug
        suffix = 2
        existing_ids = {project.id for project in self.projects}
        while project_id in existing_ids:
            project_id = f"{base_slug}-{suffix}"
            suffix += 1

        workspace_path = Path(workspace_dir).resolve() if workspace_dir else (self.projects_dir / project_id).resolve()
        input_path = Path(input_dir).resolve() if input_dir else (workspace_path / "input").resolve()
        ensure_dir(input_path)
        WorkspaceStore(workspace_path).create(input_path)
        record = ProjectRecord(
            id=project_id,
            name=name,
            workspace_dir=str(workspace_path),
            input_dir=str(input_path),
            status="active",
            created_at=utc_now(),
        )
        self.projects.append(record)
        self.save()
        return record

    def clear(self) -> int:
        count = len(self.projects)
        self.projects = []
        self.save()
        return count

    def archive_project(self, project_id: str) -> ProjectRecord:
        project = self.get(project_id)
        project.status = "archived"
        project.archived_at = utc_now()
        self.save()
        return project

    def restore_project(self, project_id: str) -> ProjectRecord:
        project = self.get(project_id)
        project.status = "active"
        project.archived_at = ""
        self.save()
        return project

    def delete_project(self, project_id: str, confirmation: str) -> ProjectRecord:
        if confirmation != "DELETE":
            raise ValueError("Type DELETE to confirm project deletion.")
        project = self.get(project_id)
        projects_root = self.projects_dir.resolve()
        raw_workspace_path = Path(project.workspace_dir)
        if _has_filesystem_link_marker(raw_workspace_path):
            raise PermissionError("Only managed project workspaces can be deleted from the UI.")
        workspace_path = raw_workspace_path.resolve()
        try:
            workspace_path.relative_to(projects_root)
        except ValueError as exc:
            raise PermissionError("Only managed project workspaces can be deleted from the UI.") from exc
        if workspace_path == projects_root or workspace_path.parent != projects_root or workspace_path.name != project.id:
            raise PermissionError("Only managed project workspaces can be deleted from the UI.")
        if workspace_path.exists():
            if not workspace_path.is_dir():
                raise PermissionError("Only managed project workspace folders can be deleted from the UI.")
            shutil.rmtree(workspace_path)
        self.projects = [item for item in self.projects if item.id != project.id]
        self.save()
        return project
