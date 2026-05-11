from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .revision_state.models import StagedPackage
from .utils import stable_id

if TYPE_CHECKING:
    from .workspace import WorkspaceStore

REVISION_NUMBER_PATTERN = re.compile(r"Revision\s*(?:#|Set)?\s*(?P<number>\d+)", re.IGNORECASE)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def infer_revision_number_from_name(value: str) -> int | None:
    match = REVISION_NUMBER_PATTERN.search(value or "")
    if not match:
        return None
    try:
        number = int(match.group("number"))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def parse_revision_number(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not re.fullmatch(r"\d+", text):
        return None
    number = int(text)
    return number if number > 0 else None


def staged_package_id(folder_name: str) -> str:
    return stable_id("staged-package", folder_name.strip().lower())


def package_folders(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        return []
    return sorted(
        folder
        for folder in input_dir.iterdir()
        if folder.is_dir()
        and not folder.name.startswith(".")
        and any(folder.rglob("*.pdf"))
    )


def reconcile_staged_packages(store: WorkspaceStore, *, save: bool = False) -> tuple[list[StagedPackage], bool]:
    input_dir = Path(store.data.input_dir)
    existing_by_folder = {package.folder_name.lower(): package for package in store.data.staged_packages}
    scanned_by_folder = {
        Path(revision_set.source_dir).name.lower(): revision_set
        for revision_set in store.data.revision_sets
        if revision_set.source_dir
    }
    now = utc_timestamp()
    reconciled: list[StagedPackage] = []

    for folder in package_folders(input_dir):
        existing = existing_by_folder.get(folder.name.lower())
        scanned = scanned_by_folder.get(folder.name.lower())
        if existing:
            revision_number = existing.revision_number
        elif scanned and scanned.set_number > 0:
            revision_number = scanned.set_number
        else:
            revision_number = infer_revision_number_from_name(folder.name)
        created_at = existing.created_at if existing else now
        package = StagedPackage(
            id=existing.id if existing else staged_package_id(folder.name),
            folder_name=folder.name,
            source_dir=str(folder.resolve()),
            label=(existing.label if existing else folder.name) or folder.name,
            revision_number=revision_number,
            created_at=created_at,
            updated_at=existing.updated_at if existing else now,
        )
        if existing and (
            existing.source_dir != package.source_dir
            or existing.label != package.label
            or existing.revision_number != package.revision_number
        ):
            package = replace(package, updated_at=now)
        reconciled.append(package)

    changed = [package.__dict__ for package in store.data.staged_packages] != [package.__dict__ for package in reconciled]
    if changed:
        store.data.staged_packages = reconciled
        if save:
            store.save()
    return reconciled, changed


def register_staged_package(
    store: WorkspaceStore,
    folder: Path,
    *,
    label: str | None = None,
    revision_number: int | None,
    save: bool = False,
) -> StagedPackage:
    reconcile_staged_packages(store, save=False)
    now = utc_timestamp()
    folder = folder.resolve()
    package_id = staged_package_id(folder.name)
    packages: list[StagedPackage] = []
    updated: StagedPackage | None = None
    for package in store.data.staged_packages:
        if package.id == package_id or package.folder_name.lower() == folder.name.lower():
            updated = replace(
                package,
                folder_name=folder.name,
                source_dir=str(folder),
                label=(label or package.label or folder.name),
                revision_number=revision_number,
                updated_at=now,
            )
            packages.append(updated)
        else:
            packages.append(package)
    if updated is None:
        updated = StagedPackage(
            id=package_id,
            folder_name=folder.name,
            source_dir=str(folder),
            label=label or folder.name,
            revision_number=revision_number,
            created_at=now,
            updated_at=now,
        )
        packages.append(updated)
    store.data.staged_packages = sorted(packages, key=staged_package_sort_key)
    if save:
        store.save()
    return updated


def update_revision_numbers(store: WorkspaceStore, values: dict[str, object]) -> list[str]:
    reconcile_staged_packages(store, save=False)
    errors: list[str] = []
    now = utc_timestamp()
    updated: list[StagedPackage] = []
    for package in store.data.staged_packages:
        if package.id not in values:
            updated.append(package)
            continue
        revision_number = parse_revision_number(values[package.id])
        if revision_number is None:
            errors.append(f"{package.label}: revision number must be a positive integer.")
            updated.append(package)
            continue
        updated.append(replace(package, revision_number=revision_number, updated_at=now))
    store.data.staged_packages = sorted(updated, key=staged_package_sort_key)
    return errors + validate_staged_packages(store)


def revision_number_for_folder(store: WorkspaceStore, folder: Path) -> int | None:
    package = staged_package_for_folder(store, folder)
    if package is not None:
        return package.revision_number
    return infer_revision_number_from_name(folder.name)


def staged_package_for_folder(store: WorkspaceStore, folder: Path) -> StagedPackage | None:
    folder_name = folder.name.lower()
    for package in store.data.staged_packages:
        if package.folder_name.lower() == folder_name:
            return package
    return None


def label_for_folder(store: WorkspaceStore, folder: Path) -> str:
    folder_name = folder.name.lower()
    for package in store.data.staged_packages:
        if package.folder_name.lower() == folder_name:
            return package.label or package.folder_name
    return folder.name


def validate_staged_packages(store: WorkspaceStore) -> list[str]:
    packages, _ = reconcile_staged_packages(store, save=False)
    errors: list[str] = []
    numbered: dict[int, list[StagedPackage]] = {}
    for package in packages:
        if package.revision_number is None or package.revision_number <= 0:
            errors.append(f"{package.label}: assign a positive revision number.")
            continue
        numbered.setdefault(package.revision_number, []).append(package)
    for revision_number, duplicates in sorted(numbered.items()):
        if len(duplicates) > 1:
            labels = ", ".join(package.label for package in duplicates)
            errors.append(f"Revision {revision_number} is assigned to multiple packages: {labels}.")
    return errors


def staged_package_sort_key(package: StagedPackage) -> tuple[int, str]:
    return (package.revision_number if package.revision_number is not None else 999999, package.label.lower())
