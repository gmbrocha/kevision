from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .utils import ensure_dir, json_dumps
from .workspace import WorkspaceStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"


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
    def __init__(self, seed_workspace_dir: Path | str):
        self.seed_workspace_dir = Path(seed_workspace_dir).resolve()
        self.root_dir = self.seed_workspace_dir.parent
        self.projects_dir = ensure_dir(self.root_dir / "projects")
        self.data_path = self.root_dir / "projects.json"
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
