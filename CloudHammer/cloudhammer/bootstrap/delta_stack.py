from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import cv2

from cloudhammer.config import CloudHammerConfig
from cloudhammer.manifests import read_json, read_jsonl, write_json, write_jsonl
from cloudhammer.page_catalog import stable_page_key


@dataclass(frozen=True)
class LegacyDeltaPaths:
    repo_root: Path

    @property
    def delta_v3(self) -> Path:
        return self.repo_root / "experiments" / "delta_v3"

    @property
    def delta_v4(self) -> Path:
        return self.repo_root / "experiments" / "delta_v4" / "detect.py"

    @property
    def marker_detector(self) -> Path:
        return self.repo_root / "experiments" / "2026_04_delta_marker_detector"


def _load_module(name: str, path: Path) -> ModuleType:
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_legacy_modules(repo_root: Path) -> dict[str, ModuleType]:
    paths = LegacyDeltaPaths(repo_root=repo_root)
    for path in (paths.marker_detector, paths.delta_v3):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return {
        "denoise_1": _load_module("denoise_1", paths.delta_v3 / "denoise_1.py"),
        "denoise_2": _load_module("denoise_2", paths.delta_v3 / "denoise_2.py"),
        "denoise_x": _load_module("denoise_x", paths.delta_v3 / "denoise_x.py"),
        "delta_v4": _load_module("cloudhammer_legacy_delta_v4", paths.delta_v4),
    }


def _coerce_point(value: dict | None) -> dict | None:
    if value is None:
        return None
    return {"x": float(value["x"]), "y": float(value["y"])}


def _normalize_delta_entry(entry: dict) -> dict:
    triangle = entry.get("triangle") or {}
    return {
        "digit": entry.get("digit"),
        "status": entry.get("status"),
        "center": _coerce_point(entry.get("center")),
        "triangle": {
            "apex": _coerce_point(triangle.get("apex")),
            "left_base": _coerce_point(triangle.get("left_base")),
            "right_base": _coerce_point(triangle.get("right_base")),
        },
        "score": float(entry.get("score", 0.0)),
        "geometry_score": float(entry.get("geometry_score", 0.0)),
        "side_support": float(entry.get("side_support", 0.0)),
        "base_support": float(entry.get("base_support", 0.0)),
        "interior_ink_ratio": float(entry.get("interior_ink_ratio", 0.0)),
    }


def normalize_delta_payload(payload: dict, pdf_path: str | Path | None = None, page_index: int | None = None) -> dict:
    return {
        "pdf_path": str(pdf_path or payload.get("pdf_path")),
        "page_index": int(page_index if page_index is not None else payload.get("page_index", 0)),
        "target_digit": payload.get("target_digit"),
        "active_deltas": [_normalize_delta_entry(item) for item in payload.get("active_deltas", [])],
        "historical_deltas": [_normalize_delta_entry(item) for item in payload.get("historical_deltas", [])],
        "geometry_only_deltas": [_normalize_delta_entry(item) for item in payload.get("geometry_only_deltas", [])],
        "canonical_side_px": float(payload.get("canonical_side_px", 0.0)),
    }


def run_denoise_stack(
    repo_root: Path,
    pdf_path: Path,
    page_index: int,
    output_dir: Path,
    key: str,
) -> Path:
    modules = _load_legacy_modules(repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    gray, _ = modules["denoise_1"].detect_deltas.render_page_gray(pdf_path, page_index)
    stage1 = modules["denoise_1"].denoise_stage_1(gray)
    words = modules["denoise_2"].collect_words(pdf_path, page_index)
    stagex = modules["denoise_x"].denoise_stage_x(stage1, words)
    stage2 = modules["denoise_2"].denoise_stage_2(stagex, words)

    cv2.imwrite(str(output_dir / f"{key}_denoise_1.png"), stage1)
    cv2.imwrite(str(output_dir / f"{key}_denoise_x.png"), stagex)
    stage2_path = output_dir / f"{key}_denoise_2.png"
    cv2.imwrite(str(stage2_path), stage2)
    return stage2_path


def run_delta_v4(
    repo_root: Path,
    pdf_path: Path,
    page_index: int,
    denoised_path: Path,
    target_digit: str | None,
    overlay_path: Path,
    legacy_json_path: Path,
) -> dict:
    delta_v4 = _load_legacy_modules(repo_root)["delta_v4"]
    gray = cv2.imread(str(denoised_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(f"Could not read denoised image: {denoised_path}")
    digit_words = delta_v4.extract_digit_words_in_pixels(pdf_path, page_index, dpi=delta_v4.DEFAULT_DPI)
    search_gray, binary = delta_v4.preprocess_image(gray)
    bases, lefts, rights = delta_v4.detect_segments(search_gray)
    seed_candidates = delta_v4.build_candidates(binary, bases, lefts, rights, digit_words, target_digit)
    seed_detections = delta_v4.dedupe_candidates(seed_candidates)
    canonical_side = delta_v4.estimate_canonical_side_length(seed_detections)
    fixed_candidates = delta_v4.build_candidates_from_fixed_size_bases(
        binary,
        bases,
        digit_words,
        target_digit,
        canonical_side,
    )
    detections = delta_v4.dedupe_candidates(seed_candidates + fixed_candidates)
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(overlay_path), delta_v4.overlay_detections(gray, detections, target_digit))
    delta_v4.write_results_json(
        legacy_json_path,
        denoised_path,
        pdf_path,
        page_index,
        target_digit,
        len(digit_words),
        canonical_side,
        detections,
    )
    return read_json(legacy_json_path)


def output_paths_for_page(cfg: CloudHammerConfig, row: dict) -> dict[str, str | Path]:
    pdf_path = Path(row["pdf_path"])
    page_index = int(row["page_index"])
    key = stable_page_key(pdf_path, page_index)
    audit_dir = cfg.path("outputs") / "audit"
    denoise_dir = audit_dir / "denoise"
    return {
        "key": key,
        "normalized_json_path": cfg.path("delta_json") / f"{key}.json",
        "legacy_json_path": cfg.path("delta_json") / "legacy" / f"{key}_legacy.json",
        "denoise_1_path": denoise_dir / f"{key}_denoise_1.png",
        "denoise_x_path": denoise_dir / f"{key}_denoise_x.png",
        "denoised_path": denoise_dir / f"{key}_denoise_2.png",
        "overlay_path": audit_dir / f"{key}_delta_overlay.png",
    }


def _plain_output_paths(paths: dict[str, str | Path]) -> dict[str, str]:
    return {name: str(path) for name, path in paths.items()}


def _page_label(row: dict) -> str:
    render_path = row.get("render_path")
    if render_path:
        return Path(render_path).name
    return f"{Path(row['pdf_path']).name}:p{int(row['page_index']) + 1}"


def _read_valid_delta_payload(path: Path) -> dict | None:
    try:
        if not path.exists() or path.stat().st_size <= 0:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _base_result(row: dict, paths: dict[str, str | Path], status: str) -> dict:
    return {
        "page_id": str(paths["key"]),
        "page_name": _page_label(row),
        "pdf_path": str(row["pdf_path"]),
        "page_index": int(row["page_index"]),
        "delta_json_path": str(paths["normalized_json_path"]),
        "legacy_json_path": str(paths["legacy_json_path"]),
        "overlay_path": str(paths["overlay_path"]),
        "denoised_path": str(paths["denoised_path"]),
        "status": status,
        "error": None,
    }


def _worker_config(task: dict) -> CloudHammerConfig:
    return CloudHammerConfig(root=Path(task["cfg_root"]), data=task["cfg_data"])


def _run_bootstrap_worker(task: dict) -> dict:
    started = time.monotonic()
    row = task["row"]
    paths = task["output_paths"]
    result = _base_result(row, paths, "generated")
    try:
        cfg = _worker_config(task)
        run_bootstrap_for_page(cfg, row, target_digit=task.get("target_digit"))
        result["elapsed_sec"] = round(time.monotonic() - started, 3)
        return result
    except Exception as exc:  # pragma: no cover - exercised by real bad input pages
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc(limit=8)
        result["elapsed_sec"] = round(time.monotonic() - started, 3)
        return result


def _progress_line(
    *,
    completed: int,
    total: int,
    skipped: int,
    generated: int,
    failed: int,
    current: str,
    started: float,
) -> str:
    elapsed = max(time.monotonic() - started, 0.001)
    files_per_min = completed / (elapsed / 60.0)
    return (
        f"{completed}/{total} complete | "
        f"skipped={skipped} generated={generated} failed={failed} | "
        f"current={current} | "
        f"elapsed={elapsed:.1f}s | {files_per_min:.1f} files/min"
    )


def _write_rebuilt_manifest(manifest_path: Path, json_paths: list[Path]) -> int:
    rows: list[dict] = []
    for path in json_paths:
        payload = _read_valid_delta_payload(path)
        if payload is not None:
            rows.append(payload)
    return write_jsonl(manifest_path, rows)


def run_bootstrap_for_page(cfg: CloudHammerConfig, row: dict, target_digit: str | None = None) -> dict:
    repo_root = cfg.root.parent
    pdf_path = Path(row["pdf_path"])
    page_index = int(row["page_index"])
    key = stable_page_key(pdf_path, page_index)
    audit_dir = cfg.path("outputs") / "audit"
    denoise_dir = audit_dir / "denoise"
    legacy_json_dir = cfg.path("delta_json") / "legacy"
    legacy_json_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = cfg.path("delta_json") / f"{key}.json"
    legacy_json_path = legacy_json_dir / f"{key}_legacy.json"
    denoised_path = run_denoise_stack(repo_root, pdf_path, page_index, denoise_dir, key)
    payload = run_delta_v4(
        repo_root,
        pdf_path,
        page_index,
        denoised_path,
        target_digit if target_digit is not None else cfg.target_revision_digit,
        audit_dir / f"{key}_delta_overlay.png",
        legacy_json_path,
    )
    normalized = normalize_delta_payload(payload, pdf_path=pdf_path, page_index=page_index)
    write_json(normalized_path, normalized)
    return normalized


def run_bootstrap_from_manifest(
    cfg: CloudHammerConfig,
    pages_manifest: str | Path | None = None,
    limit: int | None = None,
    target_digit: str | None = None,
    workers: int = 1,
    overwrite: bool = False,
) -> int:
    cfg.ensure_directories()
    if workers < 1:
        raise ValueError("workers must be at least 1")
    manifest = Path(pages_manifest) if pages_manifest is not None else cfg.path("manifests") / "pages.jsonl"
    all_drawing_rows: list[dict] = []
    for row in read_jsonl(manifest):
        if row.get("page_kind") != "drawing":
            continue
        all_drawing_rows.append(row)

    work_rows = all_drawing_rows[:limit] if limit is not None else all_drawing_rows
    total = len(work_rows)
    started = time.monotonic()
    completed = 0
    skipped = 0
    generated = 0
    failed = 0
    failures: list[dict] = []
    tasks: list[dict] = []

    cfg_payload = {"cfg_root": str(cfg.root), "cfg_data": cfg.data}
    effective_target_digit = target_digit if target_digit is not None else cfg.target_revision_digit

    if limit is None:
        print(f"loaded {total} drawing page records from {manifest}")
    else:
        print(f"loaded {len(all_drawing_rows)} drawing page records from {manifest}; processing first {total}")
    for row in work_rows:
        paths = output_paths_for_page(cfg, row)
        normalized_path = Path(paths["normalized_json_path"])
        if not overwrite and _read_valid_delta_payload(normalized_path) is not None:
            skipped += 1
            completed += 1
            print(
                _progress_line(
                    completed=completed,
                    total=total,
                    skipped=skipped,
                    generated=generated,
                    failed=failed,
                    current=_page_label(row),
                    started=started,
                )
            )
            continue
        tasks.append(
            {
                **cfg_payload,
                "row": row,
                "target_digit": effective_target_digit,
                "output_paths": _plain_output_paths(paths),
            }
        )

    if tasks:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            future_to_task = {executor.submit(_run_bootstrap_worker, task): task for task in tasks}
            for future in concurrent.futures.as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                except Exception as exc:  # pragma: no cover - protects parent from process failures
                    result = _base_result(task["row"], task["output_paths"], "failed")
                    result["error"] = f"{type(exc).__name__}: {exc}"
                    result["traceback"] = traceback.format_exc(limit=8)

                completed += 1
                if result.get("status") == "generated":
                    generated += 1
                else:
                    failed += 1
                    failures.append(result)
                    print(
                        f"failed page {result.get('page_id')} "
                        f"({result.get('page_name')}): {result.get('error')}"
                    )

                print(
                    _progress_line(
                        completed=completed,
                        total=total,
                        skipped=skipped,
                        generated=generated,
                        failed=failed,
                        current=str(result.get("page_name") or result.get("pdf_path") or "unknown"),
                        started=started,
                    )
                )

    manifest_path = cfg.path("manifests") / "delta_manifest.jsonl"
    ordered_json_paths: list[Path] = []
    for row in all_drawing_rows:
        paths = output_paths_for_page(cfg, row)
        normalized_path = Path(paths["normalized_json_path"])
        if _read_valid_delta_payload(normalized_path) is not None:
            ordered_json_paths.append(normalized_path)
    manifest_count = _write_rebuilt_manifest(manifest_path, ordered_json_paths)
    print(f"rebuilt {manifest_path} with {manifest_count} rows")

    if failures:
        print("failure summary:")
        for result in failures:
            print(
                f"- {result.get('page_id')} | {result.get('page_name')} | "
                f"{result.get('error')}"
            )
    print(
        f"done: total={total} skipped={skipped} generated={generated} "
        f"failed={failed} manifest_rows={manifest_count}"
    )
    return manifest_count
