from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from backend.projects import ProjectRecord, ProjectRegistry
from backend.revision_state.tracker import RevisionScanner
from backend.workspace import WorkspaceStore


REPO_ROOT = Path(__file__).resolve().parents[1]


def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


@pytest.fixture(scope="session")
def scanned_workspace_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    input_dir = tmp_path_factory.mktemp("revision-input")
    workspace_dir = tmp_path_factory.mktemp("revision-workspace")
    sources = [
        REPO_ROOT / "revision_sets" / "Revision #1 - Drawing Changes" / "Revision #1 - Drawing Changes.pdf",
        REPO_ROOT / "revision_sets" / "Revision #2 - Mod 5 grab bar supports" / "260309 - Drawing Rev2- Steel Grab Bars.pdf",
    ]
    for source in sources:
        rel = source.relative_to(REPO_ROOT / "revision_sets")
        _link_or_copy(source, input_dir / rel)
    RevisionScanner(input_dir, workspace_dir).scan()
    return workspace_dir


@pytest.fixture(autouse=True)
def _enable_review_capture_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REVIEW_CAPTURE", "true")


@pytest.fixture()
def workspace_copy(tmp_path: Path, scanned_workspace_dir: Path) -> Path:
    destination = tmp_path / "workspace"
    shutil.copytree(scanned_workspace_dir, destination)
    store = WorkspaceStore(destination).load()
    registry = ProjectRegistry(destination).load()
    registry.projects = [
        ProjectRecord(
            id="test-project",
            name="Test Project",
            workspace_dir=str(destination.resolve()),
            input_dir=store.data.input_dir,
            status="active",
            created_at=store.data.created_at,
        )
    ]
    registry.save()
    return destination
