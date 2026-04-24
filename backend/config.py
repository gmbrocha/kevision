from __future__ import annotations

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_RESOURCES_DIR = REPO_ROOT / "resources"
DEFAULT_REVISION_SETS_DIR = REPO_ROOT / "revision_sets"
