from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ..utils import ensure_dir, json_dumps


DEFAULT_MODEL_PATH = Path("CloudHammer") / "runs" / "cloudhammer_roi-symbol-text-fp-hn-20260502" / "weights" / "best.pt"
DEFAULT_TIMEOUT_SECONDS = 3600
COMMAND_OUTPUT_LIMIT = 2400


class CloudHammerPipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloudHammerCommandRecord:
    label: str
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class CloudHammerRunResult:
    run_dir: Path
    pages_manifest: Path
    candidate_manifest: Path
    page_count: int
    candidate_count: int
    skipped_reason: str = ""
    commands: list[CloudHammerCommandRecord] = field(default_factory=list)

    def to_status(self) -> dict[str, object]:
        return {
            "cloudhammer_run_dir": str(self.run_dir),
            "cloudhammer_pages_manifest": str(self.pages_manifest),
            "cloudhammer_candidate_manifest": str(self.candidate_manifest),
            "cloudhammer_page_count": self.page_count,
            "cloudhammer_candidate_count": self.candidate_count,
            "cloudhammer_skipped_reason": self.skipped_reason,
        }


class CloudHammerRunner(Protocol):
    name: str

    def run(self, *, input_dir: Path, workspace_dir: Path) -> CloudHammerRunResult:
        ...


class LiveCloudHammerPipeline:
    """Run the current CloudHammer full-page pipeline for a project workspace.

    Output artifacts stay inside the app project workspace under
    outputs/cloudhammer_live/. This keeps client handoff inference separate
    from CloudHammer_v2 eval/training artifacts.
    """

    name = "cloudhammer_live_pipeline"

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        python_executable: str | None = None,
        model_path: Path | None = None,
        timeout_seconds: int | None = None,
    ):
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.python_executable = python_executable or sys.executable
        raw_model_path = model_path or Path(os.getenv("SCOPELEDGER_CLOUDHAMMER_MODEL", str(DEFAULT_MODEL_PATH)))
        if not raw_model_path.is_absolute():
            raw_model_path = self.repo_root / raw_model_path
        self.model_path = raw_model_path.resolve()
        self.timeout_seconds = timeout_seconds or _configured_timeout_seconds()

    def run(self, *, input_dir: Path, workspace_dir: Path) -> CloudHammerRunResult:
        input_dir = input_dir.resolve()
        workspace_dir = workspace_dir.resolve()
        if not input_dir.exists():
            raise FileNotFoundError(f"Project input folder does not exist: {input_dir}")
        if not self.model_path.exists():
            raise FileNotFoundError(f"CloudHammer model checkpoint not found: {self.model_path}")

        run_dir = ensure_dir(workspace_dir / "outputs" / "cloudhammer_live" / self._run_id())
        config_path = run_dir / "config" / "cloudhammer_live.yaml"
        pages_manifest = run_dir / "pages_manifest.jsonl"
        candidate_manifest = run_dir / "whole_cloud_candidates" / "whole_cloud_candidates_manifest.jsonl"
        commands: list[CloudHammerCommandRecord] = []

        self._write_config(config_path)
        commands.append(
            self._run_command(
                "catalog_pages",
                [
                    self.python_executable,
                    str(self.repo_root / "CloudHammer" / "scripts" / "catalog_pages.py"),
                    "--config",
                    str(config_path),
                    "--revision-sets",
                    str(input_dir),
                    "--manifest-out",
                    str(pages_manifest),
                ],
            )
        )
        page_count = _count_drawing_page_rows(pages_manifest)
        if page_count == 0:
            _write_empty_jsonl(candidate_manifest)
            result = CloudHammerRunResult(
                run_dir=run_dir,
                pages_manifest=pages_manifest,
                candidate_manifest=candidate_manifest,
                page_count=0,
                candidate_count=0,
                skipped_reason="no_drawing_pages",
                commands=commands,
            )
            self._write_summary(result)
            return result

        commands.append(
            self._run_command(
                "infer_pages",
                [
                    self.python_executable,
                    str(self.repo_root / "CloudHammer" / "scripts" / "infer_pages.py"),
                    "--config",
                    str(config_path),
                    "--model",
                    str(self.model_path),
                    "--pages-manifest",
                    str(pages_manifest),
                ],
            )
        )
        commands.append(
            self._run_command(
                "group_fragment_detections",
                [
                    self.python_executable,
                    str(self.repo_root / "CloudHammer" / "scripts" / "group_fragment_detections.py"),
                    "--detections-dir",
                    str(run_dir / "model_only" / "detections"),
                    "--output-dir",
                    str(run_dir / "fragment_grouping"),
                    "--overmerge-refinement",
                    "--overmerge-refinement-profile",
                    "review_v1",
                ],
            )
        )
        commands.append(
            self._run_command(
                "export_whole_cloud_candidates",
                [
                    self.python_executable,
                    str(self.repo_root / "CloudHammer" / "scripts" / "export_whole_cloud_candidates.py"),
                    "--grouped-detections-dir",
                    str(run_dir / "fragment_grouping" / "detections_grouped"),
                    "--output-dir",
                    str(run_dir / "whole_cloud_candidates"),
                    "--crop-margin-ratio",
                    "0.16",
                    "--min-crop-margin",
                    "550",
                    "--max-crop-margin",
                    "950",
                ],
            )
        )

        candidate_count = _count_jsonl_rows(candidate_manifest)
        result = CloudHammerRunResult(
            run_dir=run_dir,
            pages_manifest=pages_manifest,
            candidate_manifest=candidate_manifest,
            page_count=page_count,
            candidate_count=candidate_count,
            commands=commands,
        )
        self._write_summary(result)
        return result

    def _run_id(self) -> str:
        return "run_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

    def _write_config(self, config_path: Path) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "\n".join(
                [
                    "paths:",
                    "  rasterized_pages: rasterized_pages",
                    "  manifests: manifests",
                    "  outputs: model_only",
                    "render:",
                    "  dpi: 300",
                    "inference:",
                    "  confidence_threshold: 0.5",
                    "  tile_size: 1280",
                    "  tile_overlap: 192",
                    "  nms_iou: 0.5",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _run_command(self, label: str, command: list[str]) -> CloudHammerCommandRecord:
        try:
            completed = subprocess.run(  # nosec B603
                command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _decode_subprocess_output(exc.stdout)
            stderr = _decode_subprocess_output(exc.stderr)
            detail = _compact_text(stderr or stdout or "no subprocess output captured")
            raise CloudHammerPipelineError(
                f"CloudHammer {label} timed out after {self.timeout_seconds} seconds: {detail}"
            ) from exc
        record = CloudHammerCommandRecord(
            label=label,
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )
        if completed.returncode != 0:
            detail = _compact_text(record.stderr or record.stdout or f"exit code {completed.returncode}")
            raise CloudHammerPipelineError(f"CloudHammer {label} failed: {detail}")
        return record

    def _write_summary(self, result: CloudHammerRunResult) -> None:
        payload = {
            "schema": "scopeledger.cloudhammer_live_run.v1",
            "runner": self.name,
            "model_path": str(self.model_path),
            "run": {
                **result.to_status(),
                "commands": [asdict(command) for command in result.commands],
            },
        }
        (result.run_dir / "cloudhammer_live_summary.json").write_text(json_dumps(payload), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _count_jsonl_rows(path: Path) -> int:
    return len(_read_jsonl(path))


def _count_drawing_page_rows(path: Path) -> int:
    return sum(1 for row in _read_jsonl(path) if row.get("page_kind") == "drawing" and row.get("render_path"))


def _write_empty_jsonl(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _configured_timeout_seconds() -> int:
    raw_value = os.getenv("SCOPELEDGER_CLOUDHAMMER_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("SCOPELEDGER_CLOUDHAMMER_TIMEOUT_SECONDS must be an integer second count.") from exc
    if value <= 0:
        raise RuntimeError("SCOPELEDGER_CLOUDHAMMER_TIMEOUT_SECONDS must be greater than zero.")
    return value


def _decode_subprocess_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return value.strip()


def _compact_text(value: str, limit: int = COMMAND_OUTPUT_LIMIT) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    keep = max(1, (limit - 15) // 2)
    return f"{text[:keep]} ... {text[-keep:]}"
