"""Generate a real Kevin-shaped changelog preview from `workspace_demo/`.

Usage:
    python experiments/preview_kevin_changelog.py

This copies `workspace_demo/` to a temp dir, marks a representative subset of
change items as approved (those with cloud crops + non-trivial reviewer text),
runs the Kevin exporter, and prints the resulting xlsx path. The original
workspace is not modified.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import mkdtemp

from revision_tool.kevin_changelog import write_kevin_changelog
from revision_tool.workspace import WorkspaceStore

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "workspace_demo"
OUT = REPO / "experiments" / "kevin_changelog_preview.xlsx"
LIMIT = 12


def _rewrite_to_current(stale_path: str, workspace: Path) -> str:
    """Map an absolute path stored at scan time to the current workspace root.

    Workspaces store render/crop paths as absolutes (e.g.
    `F:\\Desktop\\drawing_revision\\workspace_demo\\assets\\crops\\X.png`). Once
    the project moved to `F:\\Desktop\\m\\projects\\drawing_revision`, those
    paths no longer resolve. Find the `assets/` segment and re-anchor it under
    the live workspace.
    """
    norm = stale_path.replace("\\", "/")
    marker = "/assets/"
    idx = norm.find(marker)
    if idx == -1:
        return stale_path
    suffix = norm[idx + 1:]
    return str(workspace / suffix)


def _seems_like_real_scope(text: str) -> bool:
    if not text:
        return False
    text = text.strip().lower()
    if len(text) < 6:
        return False
    bad_starts = ("possible revision region", "see ", "ref ")
    return not any(text.startswith(b) for b in bad_starts)


def main() -> None:
    tmp_dir = Path(mkdtemp(prefix="kevin_preview_"))
    workspace = tmp_dir / "workspace"
    shutil.copytree(SOURCE, workspace)

    store = WorkspaceStore(workspace).load()

    # Workspace was scanned at the project's old absolute root; rewrite stale
    # paths so embedded crops resolve from the current location.
    new_root = str(workspace).replace("\\", "/")
    for cloud in store.data.clouds:
        if cloud.image_path:
            cloud.image_path = _rewrite_to_current(cloud.image_path, workspace)
        if cloud.page_image_path:
            cloud.page_image_path = _rewrite_to_current(cloud.page_image_path, workspace)
    for sheet in store.data.sheets:
        if sheet.render_path:
            sheet.render_path = _rewrite_to_current(sheet.render_path, workspace)

    candidates = [
        item for item in store.data.change_items
        if item.cloud_candidate_id and _seems_like_real_scope(item.raw_text)
    ]
    candidates.sort(key=lambda item: (item.sheet_id, item.detail_ref or "", -len(item.raw_text or "")))

    approved_ids: set[str] = set()
    for item in candidates:
        if len(approved_ids) >= LIMIT:
            break
        store.update_change_item(item.id, status="approved", reviewer_text=item.raw_text)
        approved_ids.add(item.id)
    print(f"Marked {len(approved_ids)} items approved (out of {len(candidates)} candidates with crops)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    write_kevin_changelog(store, OUT)
    print(f"Wrote preview: {OUT}")
    print(f"(temp workspace at {workspace} — safe to delete)")


if __name__ == "__main__":
    main()
