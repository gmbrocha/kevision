from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cloudhammer_client.live_pipeline import CloudHammerRunResult
from .revision_state.models import StagedPackage
from .utils import ensure_dir, json_dumps, stable_id


PACKAGE_RUN_SCHEMA = "scopeledger.package_run.v1"
ASSEMBLED_RUN_SCHEMA = "scopeledger.cloudhammer_assembled_run.v1"


@dataclass(frozen=True)
class PackageRunPlan:
    package: StagedPackage
    record: dict[str, Any]
    pdf_fingerprints: list[dict[str, Any]]
    pipeline_fingerprint: str
    dirty_reason: str

    @property
    def is_dirty(self) -> bool:
        return bool(self.dirty_reason)


def cloudhammer_pipeline_fingerprint(runner: object) -> str:
    explicit = getattr(runner, "fingerprint", None)
    if callable(explicit):
        return str(explicit())
    model_path = getattr(runner, "model_path", "")
    model_parts: list[Any] = [getattr(runner, "name", runner.__class__.__name__), str(model_path)]
    if model_path:
        path = Path(model_path)
        if path.exists():
            stat = path.stat()
            model_parts.extend([stat.st_size, stat.st_mtime_ns])
    timeout = getattr(runner, "timeout_seconds", "")
    if timeout:
        model_parts.append(timeout)
    return stable_id("cloudhammer-pipeline", *model_parts)


def package_pdf_fingerprints(package: StagedPackage) -> list[dict[str, Any]]:
    source_dir = Path(package.source_dir)
    if not source_dir.exists():
        return []
    fingerprints: list[dict[str, Any]] = []
    for pdf_path in sorted(source_dir.rglob("*.pdf")):
        if not pdf_path.is_file():
            continue
        stat = pdf_path.stat()
        rel_path = pdf_path.relative_to(source_dir).as_posix()
        fingerprints.append(
            {
                "path": rel_path,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "fingerprint": stable_id(rel_path, stat.st_size, stat.st_mtime_ns),
            }
        )
    return fingerprints


def plan_package_runs(
    store: WorkspaceStore,
    runner: object,
    packages: list[StagedPackage],
    *,
    force_rebuild: bool = False,
) -> list[PackageRunPlan]:
    pipeline_fingerprint = cloudhammer_pipeline_fingerprint(runner)
    plans: list[PackageRunPlan] = []
    for package in packages:
        record = dict((store.data.package_runs or {}).get(package.id) or {})
        pdf_fingerprints = package_pdf_fingerprints(package)
        dirty_reason = (
            "rebuild_requested"
            if force_rebuild
            else package_dirty_reason(
                package,
                record,
                pdf_fingerprints=pdf_fingerprints,
                pipeline_fingerprint=pipeline_fingerprint,
            )
        )
        plans.append(
            PackageRunPlan(
                package=package,
                record=record,
                pdf_fingerprints=pdf_fingerprints,
                pipeline_fingerprint=pipeline_fingerprint,
                dirty_reason=dirty_reason,
            )
        )
    return plans


def package_dirty_reason(
    package: StagedPackage,
    record: dict[str, Any],
    *,
    pdf_fingerprints: list[dict[str, Any]],
    pipeline_fingerprint: str,
) -> str:
    if not record:
        return "not_processed"
    if record.get("schema") != PACKAGE_RUN_SCHEMA:
        return "schema_changed"
    if record.get("status") != "complete":
        return "not_complete"
    if record.get("package_id") != package.id or record.get("folder_name") != package.folder_name:
        return "package_identity_changed"
    if record.get("source_dir") != str(Path(package.source_dir).resolve()):
        return "source_dir_changed"
    if record.get("revision_number") != package.revision_number:
        return "revision_number_changed"
    if record.get("pdf_fingerprints") != pdf_fingerprints:
        return "source_pdfs_changed"
    if record.get("pipeline_fingerprint") != pipeline_fingerprint:
        return "pipeline_changed"
    for key in ("run_dir", "pages_manifest", "candidate_manifest"):
        value = str(record.get(key) or "")
        if not value or not Path(value).exists():
            return "missing_run_artifact"
    candidate_fingerprint = file_fingerprint(Path(str(record.get("candidate_manifest") or "")))
    if record.get("candidate_manifest_fingerprint") and record.get("candidate_manifest_fingerprint") != candidate_fingerprint:
        return "run_artifact_changed"
    return ""


def build_package_run_record(
    package: StagedPackage,
    result: CloudHammerRunResult,
    *,
    pdf_fingerprints: list[dict[str, Any]],
    pipeline_fingerprint: str,
) -> dict[str, Any]:
    return {
        "schema": PACKAGE_RUN_SCHEMA,
        "status": "complete",
        "package_id": package.id,
        "folder_name": package.folder_name,
        "label": package.label,
        "revision_number": package.revision_number,
        "source_dir": str(Path(package.source_dir).resolve()),
        "pdf_fingerprints": pdf_fingerprints,
        "pipeline_fingerprint": pipeline_fingerprint,
        "run_dir": str(result.run_dir.resolve()),
        "pages_manifest": str(result.pages_manifest.resolve()),
        "candidate_manifest": str(result.candidate_manifest.resolve()),
        "candidate_manifest_fingerprint": file_fingerprint(result.candidate_manifest),
        "page_count": result.page_count,
        "candidate_count": result.candidate_count,
        "skipped_reason": result.skipped_reason,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


def build_failed_package_run_record(
    package: StagedPackage,
    *,
    pdf_fingerprints: list[dict[str, Any]],
    pipeline_fingerprint: str,
    dirty_reason: str,
    error: str,
) -> dict[str, Any]:
    return {
        "schema": PACKAGE_RUN_SCHEMA,
        "status": "failed",
        "package_id": package.id,
        "folder_name": package.folder_name,
        "label": package.label,
        "revision_number": package.revision_number,
        "source_dir": str(Path(package.source_dir).resolve()),
        "pdf_fingerprints": pdf_fingerprints,
        "pipeline_fingerprint": pipeline_fingerprint,
        "dirty_reason": dirty_reason,
        "last_action": "failed",
        "last_error": error,
        "failed_at": datetime.now(timezone.utc).isoformat(),
    }


def file_fingerprint(path: Path) -> str:
    if not path.exists():
        return ""
    stat = path.stat()
    return stable_id(str(path.resolve()), stat.st_size, stat.st_mtime_ns)


def assemble_cloudhammer_package_runs(
    workspace_dir: Path,
    records: list[dict[str, Any]],
) -> tuple[CloudHammerRunResult, dict[str, str]]:
    run_dir = ensure_dir(workspace_dir / "outputs" / "cloudhammer_live" / "assembled" / _assembled_run_id())
    pages_manifest = run_dir / "pages_manifest.jsonl"
    candidate_manifest = run_dir / "whole_cloud_candidates" / "whole_cloud_candidates_manifest.jsonl"
    candidate_manifest.parent.mkdir(parents=True, exist_ok=True)

    page_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    pdf_cache_keys: dict[str, str] = {}
    for record in records:
        page_rows.extend(read_jsonl(Path(str(record.get("pages_manifest") or ""))))
        candidate_rows.extend(read_jsonl(Path(str(record.get("candidate_manifest") or ""))))
        for pdf in record.get("pdf_fingerprints") or []:
            rel_path = str(pdf.get("path") or "")
            if not rel_path:
                continue
            pdf_path = Path(str(record.get("source_dir") or "")) / rel_path
            pdf_cache_keys[str(pdf_path.resolve()).lower()] = stable_id(
                "package-run-pdf",
                record.get("package_id"),
                pdf.get("fingerprint"),
                record.get("pipeline_fingerprint"),
                record.get("candidate_manifest_fingerprint"),
            )

    write_jsonl(pages_manifest, page_rows)
    write_jsonl(candidate_manifest, candidate_rows)
    result = CloudHammerRunResult(
        run_dir=run_dir,
        pages_manifest=pages_manifest,
        candidate_manifest=candidate_manifest,
        page_count=sum(1 for row in page_rows if row.get("page_kind") == "drawing" and row.get("render_path")),
        candidate_count=len(candidate_rows),
        skipped_reason="no_drawing_pages" if not page_rows else "",
    )
    summary = {
        "schema": ASSEMBLED_RUN_SCHEMA,
        "package_count": len(records),
        "reused_package_count": len([record for record in records if record.get("last_action") == "reused"]),
        "processed_package_count": len([record for record in records if record.get("last_action") == "processed"]),
        "run": result.to_status(),
    }
    (run_dir / "cloudhammer_assembled_summary.json").write_text(json_dumps(summary), encoding="utf-8")
    return result, pdf_cache_keys


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _assembled_run_id() -> str:
    return "assemble_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
