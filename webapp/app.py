from __future__ import annotations

import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import fitz
from flask import Flask, abort, flash, g, has_request_context, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from backend.diagnostics import build_diagnostic_summary, configure_mupdf, format_pdf_label
from backend.deliverables.crop_comparison import build_cloud_comparison_image, find_previous_sheet_version
from backend.deliverables.excel_exporter import ExportBlockedError, Exporter
from backend.deliverables.review_packet import build_review_packet
from backend.projects import ProjectRecord, ProjectRegistry
from backend.review import change_item_needs_attention
from backend.revision_state.tracker import RevisionScanner
from backend.scope_extraction import enrich_workspace_scope_text
from backend.workspace import WorkspaceStore


class DisabledReviewAssistProvider:
    """Placeholder until local-model review assist is wired into the web app."""

    name = "archived"
    enabled = False


def filter_change_items(store: WorkspaceStore, filter_status: str, search_query: str) -> list:
    items = store.data.change_items
    if filter_status != "all":
        items = [item for item in items if item.status == filter_status]
    query = search_query.strip().lower()
    if query:
        items = [
            item
            for item in items
            if query in " ".join(
                [
                    item.sheet_id,
                    item.detail_ref or "",
                    item.reviewer_text or "",
                    item.raw_text or "",
                    str(item.provenance.get("source", "")),
                ]
            ).lower()
        ]
    return sorted(items, key=lambda item: (item.status != "pending", item.sheet_id, item.detail_ref or "", item.id))


def build_change_navigation(items: list, current_id: str) -> dict[str, object]:
    ids = [item.id for item in items]
    try:
        index = ids.index(current_id)
    except ValueError:
        return {"index": None, "total": len(ids), "previous_change_id": None, "next_change_id": None}
    previous_change_id = ids[index - 1] if index > 0 else None
    next_change_id = ids[index + 1] if index + 1 < len(ids) else None
    return {
        "index": index + 1,
        "total": len(ids),
        "previous_change_id": previous_change_id,
        "next_change_id": next_change_id,
    }


def discipline_for_sheet(sheet_id: str) -> str:
    prefix = "".join(ch for ch in sheet_id.upper() if ch.isalpha())
    return {
        "AD": "Architectural Demo",
        "AE": "Architectural",
        "A": "Architectural",
        "IN": "Interior",
        "PL": "Plumbing",
        "P": "Plumbing",
        "MP": "Mechanical / Plumbing",
        "MH": "Mechanical",
        "ME": "Mechanical",
        "EL": "Electrical",
        "EP": "Electrical Power",
        "E": "Electrical",
        "S": "Structural",
        "SF": "Structural",
        "GI": "General",
        "CS": "Civil",
    }.get(prefix, prefix or "Drawing")


def compact_sheet_title(title: str) -> str:
    normalized = " ".join((title or "").split())
    if not normalized:
        return "Untitled drawing"
    if len(normalized) > 120:
        return f"{normalized[:117].rstrip()}..."
    return normalized


def sheet_is_index_like(sheet) -> bool:
    title = " ".join((sheet.sheet_title or "").split()).upper()
    excerpt = " ".join((getattr(sheet, "page_text_excerpt", "") or "").split()).upper()
    combined = f"{title} {excerpt[:500]}"
    if any(token in combined for token in ("SHEET INDEX", "CONFORMED SET", "PAGE NO. SHEET NO.", "SHEET NO. SHEET NAME")):
        return True
    return len(title) > 220 and title.count(" X ") >= 6


def latest_real_sheet_version(sheet, all_sheets: list, revision_sets_by_id: dict) -> object | None:
    candidates = [item for item in all_sheets if item.sheet_id == sheet.sheet_id and item.id != sheet.id and not sheet_is_index_like(item)]
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda item: (
            item.status != "active",
            -revision_sets_by_id[item.revision_set_id].set_number,
            item.page_number,
        ),
    )
    return ranked[0]


HIGH_RES_SHEET_SCALE = 2.25
HIGH_RES_CROP_MAX_SCALE = 6.0
HIGH_RES_CROP_TARGET_WIDTH = 1800
DRIVE_REVIEW_FOLDER_URL = "https://drive.google.com/drive/folders/1_6LogBKmxt38bF9dGBPyc1l_z38z1MaT"


class ActiveProjectWorkspace:
    def __init__(self, current_store):
        self.current_store = current_store

    def current(self) -> WorkspaceStore:
        return self.current_store()

    def __getattr__(self, name):
        return getattr(self.current(), name)


def create_app(workspace_dir: Path, verification_provider=None) -> Flask:
    configure_mupdf()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.getenv("SCOPELEDGER_WEBAPP_SECRET", "scopeledger-dev")
    registry = ProjectRegistry(Path(workspace_dir)).load()
    seed_store = WorkspaceStore(Path(workspace_dir)).load()
    provider = verification_provider or DisabledReviewAssistProvider()
    project_root = Path.cwd().resolve()
    app.config["STORE"] = seed_store
    app.config["PROJECT_REGISTRY"] = registry
    app.config["REVIEW_ASSIST_PROVIDER"] = provider

    def active_project() -> ProjectRecord:
        project_id = session.get("project_id")
        if project_id:
            try:
                project = registry.get(project_id)
                if project.status == "active":
                    return project
            except KeyError:
                pass
        project = registry.first_active()
        session["project_id"] = project.id
        return project

    def load_project_store(project: ProjectRecord | None = None) -> WorkspaceStore:
        selected = project or active_project()
        if project is None and has_request_context():
            cached = getattr(g, "active_store", None)
            if cached is not None:
                return cached
            g.active_store = WorkspaceStore(Path(selected.workspace_dir)).load()
            return g.active_store
        return WorkspaceStore(Path(selected.workspace_dir)).load()

    store = ActiveProjectWorkspace(load_project_store)

    def rescan_active_project() -> tuple[WorkspaceStore, int]:
        project = active_project()
        current = load_project_store(project)
        scanner = RevisionScanner(Path(current.data.input_dir), Path(project.workspace_dir))
        return scanner.scan(), scanner.cache_hits

    def utc_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def copy_package_source(source_path: Path, destination_dir: Path) -> None:
        destination_dir.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(source_path, destination_dir, dirs_exist_ok=True)
            return
        if source_path.is_file():
            shutil.copy2(source_path, destination_dir / source_path.name)
            return
        raise FileNotFoundError(source_path)

    def safe_path_part(value: str) -> str:
        cleaned = "".join("_" if char in '<>:"/\\|?*' or ord(char) < 32 else char for char in value.strip())
        return cleaned.strip(" .")

    def safe_upload_parts(filename: str) -> list[str]:
        parts = []
        for part in filename.replace("\\", "/").split("/"):
            if part in {"", ".", ".."}:
                continue
            safe_part = safe_path_part(part)
            if safe_part:
                parts.append(safe_part)
        return parts

    def safe_package_dir_name(value: str) -> str:
        return safe_path_part(value) if value.strip() else ""

    def has_uploaded_files(field_name: str) -> bool:
        return any(item and item.filename for item in request.files.getlist(field_name))

    def infer_package_name_from_uploads(field_name: str) -> str:
        for item in request.files.getlist(field_name):
            if not item or not item.filename:
                continue
            parts = safe_upload_parts(item.filename)
            if len(parts) > 1:
                return parts[0]
            if parts:
                return Path(parts[0]).stem
        return "Uploaded_Package"

    def save_uploaded_pdfs(field_name: str, destination_dir: Path, *, preserve_relative: bool) -> list[Path]:
        saved: list[Path] = []
        destination_dir.mkdir(parents=True, exist_ok=True)
        for item in request.files.getlist(field_name):
            if not item or not item.filename:
                continue
            parts = safe_upload_parts(item.filename)
            if not parts or Path(parts[-1]).suffix.lower() != ".pdf":
                continue
            if preserve_relative and len(parts) > 1:
                relative_path = Path(*parts)
                if relative_path.parts and relative_path.parts[0].lower() == destination_dir.name.lower():
                    relative_path = Path(*relative_path.parts[1:]) if len(relative_path.parts) > 1 else Path(parts[-1])
            else:
                relative_path = Path(parts[-1])
            target = destination_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            item.save(target)
            saved.append(target)
        return saved

    def stage_uploaded_package(field_name: str, input_dir: Path, package_label: str) -> tuple[str, list[Path]]:
        destination_name = safe_package_dir_name(package_label) or infer_package_name_from_uploads(field_name)
        destination_dir = input_dir / destination_name
        return destination_name, save_uploaded_pdfs(field_name, destination_dir, preserve_relative=True)

    def stage_manual_package(source_text: str, input_dir: Path, package_label: str) -> tuple[str, Path]:
        source_path = Path(source_text).expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        destination_name = safe_package_dir_name(package_label) or source_path.stem
        destination_dir = input_dir / destination_name
        copy_package_source(source_path, destination_dir)
        return destination_name, destination_dir

    @app.context_processor
    def inject_globals() -> dict[str, object]:
        store = load_project_store()
        change_items = store.data.change_items
        total_changes = len(change_items)
        reviewed_count = len([item for item in change_items if item.status in {"approved", "rejected"}])
        current_package = max(store.data.revision_sets, key=lambda item: item.set_number, default=None)
        diagnostic_summary = build_diagnostic_summary(store.data.documents, store.data.preflight_issues)
        return {
            "active_project": active_project(),
            "active_projects": registry.active_projects(),
            "archived_projects": registry.archived_projects(),
            "pending_count": len([item for item in change_items if item.status == "pending"]),
            "approved_count": len([item for item in change_items if item.status == "approved"]),
            "rejected_count": len([item for item in change_items if item.status == "rejected"]),
            "attention_count": len([item for item in change_items if item.status == "pending" and change_item_needs_attention(item)]),
            "total_change_count": total_changes,
            "reviewed_count": reviewed_count,
            "review_progress": round((reviewed_count / total_changes) * 100) if total_changes else 100,
            "current_package_label": current_package.label if current_package else "No package loaded",
            "ai_enabled": provider.enabled,
            "diagnostic_summary": diagnostic_summary,
            "needs_attention": change_item_needs_attention,
            "drive_review_folder_url": DRIVE_REVIEW_FOLDER_URL,
        }

    @app.template_filter("status_label")
    def status_label_filter(status: str) -> str:
        return {"approved": "Accepted", "pending": "Pending", "rejected": "Rejected"}.get(status, status.title())

    @app.template_filter("badge_class")
    def badge_class_filter(status: str) -> str:
        return {"approved": "accepted", "pending": "pending", "rejected": "rejected"}.get(status, status)

    @app.template_filter("discipline")
    def discipline_filter(sheet_id: str) -> str:
        return discipline_for_sheet(sheet_id)

    @app.template_filter("compact_sheet_title")
    def compact_sheet_title_filter(title: str) -> str:
        return compact_sheet_title(title)

    @app.template_filter("sheet_index_like")
    def sheet_index_like_filter(sheet) -> bool:
        return sheet_is_index_like(sheet)

    def build_output_files() -> dict[str, Path]:
        return {
            "workbook": store.output_dir / "revision_changelog.xlsx",
            "review_packet": store.output_dir / "revision_changelog_review_packet.html",
            "preview_pdf": store.output_dir / "conformed_preview.pdf",
        }

    def high_res_sheet_path(sheet) -> Path:
        high_res_dir = store.assets_dir / "pages_hi"
        high_res_dir.mkdir(parents=True, exist_ok=True)
        return high_res_dir / f"{sheet.id}_x{str(HIGH_RES_SHEET_SCALE).replace('.', '_')}.png"

    def high_res_cloud_path(cloud) -> Path:
        high_res_dir = store.assets_dir / "crops_hi"
        high_res_dir.mkdir(parents=True, exist_ok=True)
        return high_res_dir / f"{cloud.id}_viewer_v2.png"

    def cloud_comparison_path(cloud) -> Path:
        comparison_dir = store.assets_dir / "comparisons"
        comparison_dir.mkdir(parents=True, exist_ok=True)
        return comparison_dir / f"{cloud.id}_comparison.png"

    def ensure_high_res_sheet(sheet) -> Path:
        output_path = high_res_sheet_path(sheet)
        source_pdf = store.resolve_path(sheet.source_pdf)
        source_mtime = source_pdf.stat().st_mtime if source_pdf.exists() else 0
        if output_path.exists() and output_path.stat().st_mtime >= source_mtime:
            return output_path
        document = fitz.open(source_pdf)
        try:
            page = document[sheet.page_number - 1]
            pix = page.get_pixmap(matrix=fitz.Matrix(HIGH_RES_SHEET_SCALE, HIGH_RES_SHEET_SCALE), alpha=False)
            pix.save(output_path)
        finally:
            document.close()
        return output_path

    def ensure_high_res_cloud(cloud) -> Path:
        sheet = store.get_sheet(cloud.sheet_version_id)
        output_path = high_res_cloud_path(cloud)
        source_pdf = store.resolve_path(sheet.source_pdf)
        source_mtime = source_pdf.stat().st_mtime if source_pdf.exists() else 0
        if output_path.exists() and output_path.stat().st_mtime >= source_mtime:
            return output_path
        document = fitz.open(source_pdf)
        try:
            page = document[sheet.page_number - 1]
            page_rect = page.rect
            x, y, width, height = [float(value) for value in cloud.bbox]
            pad = max(64.0, min(max(width, height) * 0.12, 180.0))
            sheet_width = float(sheet.width or page_rect.width)
            sheet_height = float(sheet.height or page_rect.height)
            scale_x = page_rect.width / sheet_width
            scale_y = page_rect.height / sheet_height
            clip = fitz.Rect(
                max(0.0, (x - pad) * scale_x),
                max(0.0, (y - pad) * scale_y),
                min(page_rect.width, (x + width + pad) * scale_x),
                min(page_rect.height, (y + height + pad) * scale_y),
            )
            crop_scale = min(HIGH_RES_CROP_MAX_SCALE, max(HIGH_RES_SHEET_SCALE, HIGH_RES_CROP_TARGET_WIDTH / max(clip.width, 1.0)))
            pix = page.get_pixmap(matrix=fitz.Matrix(crop_scale, crop_scale), clip=clip, alpha=False)
            pix.save(output_path)
        finally:
            document.close()
        return output_path

    def ensure_cloud_comparison(cloud) -> Path:
        sheet = store.get_sheet(cloud.sheet_version_id)
        output_path = cloud_comparison_path(cloud)
        source_paths = [store.resolve_path(sheet.source_pdf)]
        revision_sets_by_id = {revision_set.id: revision_set for revision_set in store.data.revision_sets}
        previous_sheet = find_previous_sheet_version(sheet, store.data.sheets, revision_sets_by_id)
        if previous_sheet:
            source_paths.append(store.resolve_path(previous_sheet.source_pdf))
        source_mtime = max((path.stat().st_mtime for path in source_paths if path.exists()), default=0)
        if output_path.exists() and output_path.stat().st_mtime >= source_mtime:
            return output_path
        generated = build_cloud_comparison_image(
            store,
            cloud=cloud,
            current_sheet=sheet,
            previous_sheet=previous_sheet,
            output_path=output_path,
        )
        if generated:
            return generated
        return ensure_high_res_cloud(cloud)

    @app.template_filter("sheet_viewer_image")
    def sheet_viewer_image_filter(sheet) -> str:
        return url_for("sheet_viewer_asset", sheet_version_id=sheet.id)

    @app.template_filter("cloud_viewer_image")
    def cloud_viewer_image_filter(cloud) -> str:
        return url_for("cloud_viewer_asset", cloud_id=cloud.id)

    @app.template_filter("cloud_comparison_image")
    def cloud_comparison_image_filter(cloud) -> str:
        return url_for("cloud_comparison_asset", cloud_id=cloud.id)

    @app.template_filter("asset_path")
    def asset_path_filter(path: str) -> str:
        if not path:
            return ""
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(store.assets_dir.resolve()).as_posix()
            return url_for("workspace_asset", asset_path=relative)
        except ValueError:
            pass
        try:
            relative = resolved.relative_to(project_root).as_posix()
            return url_for("project_asset", asset_path=relative)
        except ValueError:
            pass
        parts = list(resolved.parts)
        if "assets" in parts:
            relative = Path(*parts[parts.index("assets") + 1 :]).as_posix()
            return url_for("workspace_asset", asset_path=relative)
        return url_for("workspace_asset", asset_path=resolved.name)

    @app.template_filter("pdf_label")
    def pdf_label_filter(path: str) -> str:
        return format_pdf_label(path, Path(store.data.input_dir))

    @app.route("/projects")
    def projects():
        rows = []
        for project in registry.projects:
            try:
                project_store = WorkspaceStore(Path(project.workspace_dir)).load()
                rows.append(
                    {
                        "project": project,
                        "revision_set_count": len(project_store.data.revision_sets),
                        "sheet_count": len([sheet for sheet in project_store.data.sheets if sheet.status == "active"]),
                        "pending_count": len([item for item in project_store.data.change_items if item.status == "pending"]),
                        "approved_count": len([item for item in project_store.data.change_items if item.status == "approved"]),
                    }
                )
            except FileNotFoundError:
                rows.append(
                    {
                        "project": project,
                        "revision_set_count": 0,
                        "sheet_count": 0,
                        "pending_count": 0,
                        "approved_count": 0,
                    }
                )
        return render_template("projects.html", project_rows=rows)

    @app.post("/projects")
    def create_project():
        name = request.form.get("name", "").strip()
        workspace_dir = request.form.get("workspace_dir", "").strip()
        if not name:
            flash("Project name is required.", "warning")
            return redirect(url_for("projects"))
        try:
            project = registry.create_project(
                name=name,
                workspace_dir=Path(workspace_dir) if workspace_dir else None,
            )
        except Exception as exc:
            flash(f"Project creation failed: {exc}", "warning")
            return redirect(url_for("projects"))
        session["project_id"] = project.id
        flash(f"Created {project.name}. Add package files, then populate the workspace.", "success")
        return redirect(url_for("dashboard"))

    @app.get("/system/dialog/workspace-folder")
    def workspace_folder_dialog():
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(title="Choose ScopeLedger workspace folder")
            root.destroy()
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        return jsonify({"path": selected})

    @app.post("/projects/<project_id>/select")
    def select_project(project_id: str):
        try:
            project = registry.get(project_id)
        except KeyError:
            abort(404)
        if project.status != "active":
            flash("Restore the project before selecting it.", "warning")
            return redirect(url_for("projects"))
        session["project_id"] = project.id
        return redirect(url_for("dashboard"))

    @app.post("/projects/<project_id>/archive")
    def archive_project(project_id: str):
        try:
            project = registry.archive_project(project_id)
        except KeyError:
            abort(404)
        if session.get("project_id") == project.id:
            active = registry.active_projects()
            session["project_id"] = active[0].id if active else project.id
        flash(f"Archived {project.name}. Its workspace files are kept, but it is removed from active workflow until restored.", "success")
        return redirect(url_for("projects"))

    @app.post("/projects/<project_id>/restore")
    def restore_project(project_id: str):
        try:
            project = registry.restore_project(project_id)
        except KeyError:
            abort(404)
        session["project_id"] = project.id
        flash(f"Restored {project.name}.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/")
    def index():
        return redirect(url_for("projects"))

    @app.route("/overview")
    def dashboard():
        rows = []
        for revision_set in store.data.revision_sets:
            set_sheets = [sheet for sheet in store.data.sheets if sheet.revision_set_id == revision_set.id]
            set_change_items = [item for item in store.data.change_items if any(sheet.id == item.sheet_version_id for sheet in set_sheets)]
            rows.append(
                {
                    "revision_set": revision_set,
                    "sheet_count": len(set_sheets),
                    "active_count": len([sheet for sheet in set_sheets if sheet.status == "active"]),
                    "superseded_count": len([sheet for sheet in set_sheets if sheet.status == "superseded"]),
                    "narrative_count": len([entry for entry in store.data.narrative_entries if entry.revision_set_id == revision_set.id]),
                    "change_count": len(set_change_items),
                    "discipline": ", ".join(sorted({discipline_for_sheet(sheet.sheet_id) for sheet in set_sheets if sheet.sheet_id})[:3]) or "Drawings",
                }
            )
        pricing_summary = Exporter(store).pricing_summary()
        pending_review_count = len([item for item in store.data.change_items if item.status == "pending"])
        first_pending = next((item for item in filter_change_items(store, "pending", "")), None)
        return render_template(
            "dashboard.html",
            revision_rows=rows,
            pricing_summary=pricing_summary,
            pending_review_count=pending_review_count,
            first_pending=first_pending,
            output_files=build_output_files(),
            populate_status=store.data.populate_status or {},
        )

    @app.post("/packages/import")
    def import_package():
        current = load_project_store()
        source_text = request.form.get("source_path", "").strip()
        package_label = request.form.get("package_label", "").strip()
        if has_uploaded_files("package_files"):
            try:
                destination_name, saved = stage_uploaded_package("package_files", Path(current.data.input_dir), package_label)
                if not saved:
                    flash("No PDF files were selected for import.", "warning")
                    return redirect(url_for("dashboard"))
            except Exception as exc:
                flash(f"Package import failed: {exc}", "warning")
                return redirect(url_for("dashboard"))
            flash(
                f"Staged package {destination_name} with {len(saved)} PDF file(s). Populate the workspace to generate review data.",
                "success",
            )
            return redirect(url_for("dashboard"))

        if source_text:
            try:
                destination_name, _ = stage_manual_package(source_text, Path(current.data.input_dir), package_label)
            except Exception as exc:
                flash(f"Package import failed: {exc}", "warning")
                return redirect(url_for("dashboard"))
            flash(
                f"Staged package {destination_name}. Populate the workspace to generate review data.",
                "success",
            )
            return redirect(url_for("dashboard"))

        flash(
            "Choose PDF files or a folder from your computer, or enter a manual server path.",
            "warning",
        )
        return redirect(url_for("dashboard"))

    @app.post("/packages/append-file")
    def append_package_file():
        current = load_project_store()
        revision_set_id = request.form.get("revision_set_id", "").strip()
        source_text = request.form.get("source_path", "").strip()
        if not revision_set_id:
            flash("Choose a target package.", "warning")
            return redirect(url_for("dashboard"))
        try:
            revision_set = next(item for item in current.data.revision_sets if item.id == revision_set_id)
        except StopIteration:
            flash("Target package was not found.", "warning")
            return redirect(url_for("dashboard"))
        destination_dir = current.resolve_path(revision_set.source_dir)

        if has_uploaded_files("append_files"):
            try:
                saved = save_uploaded_pdfs("append_files", destination_dir, preserve_relative=False)
                if not saved:
                    flash("No PDF files were selected to append.", "warning")
                    return redirect(url_for("dashboard"))
            except Exception as exc:
                flash(f"File append failed: {exc}", "warning")
                return redirect(url_for("dashboard"))
            flash(
                f"Staged {len(saved)} appended PDF file(s). Populate the workspace to refresh review data.",
                "success",
            )
            return redirect(url_for("dashboard"))

        if source_text:
            source_path = Path(source_text).expanduser().resolve()
            if not source_path.exists() or not source_path.is_file():
                flash(f"PDF path does not exist: {source_path}", "warning")
                return redirect(url_for("dashboard"))
            try:
                destination_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination_dir / source_path.name)
            except Exception as exc:
                flash(f"File append failed: {exc}", "warning")
                return redirect(url_for("dashboard"))
            flash(
                f"Staged {source_path.name}. Populate the workspace to refresh review data.",
                "success",
            )
            return redirect(url_for("dashboard"))

        flash("Choose PDF files from your computer, or enter a manual server path.", "warning")
        return redirect(url_for("dashboard"))

    @app.post("/workspace/populate")
    def populate_workspace():
        current = load_project_store()
        current.update_populate_status(
            state="running",
            stage="scan",
            message="Scanning staged packages and rendering drawing pages.",
            started_at=utc_timestamp(),
            finished_at="",
            package_count=0,
            document_count=0,
            sheet_count=0,
            cloud_count=0,
            change_item_count=0,
            cache_hits=0,
            error="",
        )
        refreshed: WorkspaceStore | None = None
        try:
            refreshed, cache_hits = rescan_active_project()
            refreshed.update_populate_status(
                state="running",
                stage="scope_extraction",
                message="Extracting scope text and review reasons from cloud regions.",
                package_count=len(refreshed.data.revision_sets),
                document_count=len(refreshed.data.documents),
                sheet_count=len(refreshed.data.sheets),
                cloud_count=len(refreshed.data.clouds),
                change_item_count=len(refreshed.data.change_items),
                cache_hits=cache_hits,
            )
            enrich_workspace_scope_text(refreshed)
            refreshed.update_populate_status(
                state="done",
                stage="complete",
                message="Workspace is populated and ready for review.",
                finished_at=utc_timestamp(),
                package_count=len(refreshed.data.revision_sets),
                document_count=len(refreshed.data.documents),
                sheet_count=len(refreshed.data.sheets),
                cloud_count=len(refreshed.data.clouds),
                change_item_count=len(refreshed.data.change_items),
                cache_hits=cache_hits,
                error="",
            )
            g.active_store = refreshed
        except Exception as exc:
            failed_store = refreshed or current
            failed_store.update_populate_status(
                state="failed",
                stage="failed",
                message="Workspace population failed.",
                finished_at=utc_timestamp(),
                error=str(exc),
            )
            flash(f"Workspace population failed: {exc}", "warning")
            return redirect(url_for("dashboard"))
        flash(
            f"Workspace populated: {len(refreshed.data.revision_sets)} package(s), {len(refreshed.data.sheets)} sheet version(s), {len(refreshed.data.change_items)} change item(s).",
            "success",
        )
        return redirect(url_for("dashboard"))

    @app.route("/conformed")
    def conformed():
        revision_sets_by_id = {revision_set.id: revision_set for revision_set in store.data.revision_sets}
        groups: dict[str, list] = {}
        for sheet in store.data.sheets:
            groups.setdefault(sheet.sheet_id, []).append(sheet)

        show_filter = request.args.get("show", "revised")
        search_query = request.args.get("q", "")
        rendered_groups = []
        index_page_count = 0
        for sheet_id, versions in groups.items():
            index_page_count += len([sheet for sheet in versions if sheet_is_index_like(sheet)])
            real_versions = [sheet for sheet in versions if not sheet_is_index_like(sheet)]
            candidate_versions = real_versions or versions
            ranked = sorted(
                candidate_versions,
                key=lambda item: (item.status != "active", -revision_sets_by_id[item.revision_set_id].set_number, item.page_number),
            )
            latest = ranked[0]
            superseded = ranked[1:]
            if show_filter == "revised" and not superseded:
                continue
            if search_query and search_query.lower() not in " ".join([sheet_id, latest.sheet_title]).lower():
                continue
            rendered_groups.append(
                {
                    "sheet_id": sheet_id,
                    "latest": latest,
                    "latest_revision_set": revision_sets_by_id[latest.revision_set_id],
                    "superseded": [
                        {"sheet": version, "revision_set": revision_sets_by_id[version.revision_set_id]}
                        for version in superseded
                    ],
                }
            )
        rendered_groups.sort(key=lambda item: item["sheet_id"])
        revised_count = sum(1 for versions in groups.values() if len(versions) > 1)
        return render_template(
            "conformed.html",
            groups=rendered_groups,
            show_filter=show_filter,
            search_query=search_query,
            sheet_id_count=len(groups),
            revised_count=revised_count,
            index_page_count=index_page_count,
        )

    @app.route("/sheets")
    def sheets():
        filter_status = request.args.get("status", "all")
        search_query = request.args.get("q", "")
        include_index_matches = request.args.get("include_index", "0") == "1"
        active_sheet_count = len([sheet for sheet in store.data.sheets if sheet.status == "active"])
        superseded_sheet_count = len([sheet for sheet in store.data.sheets if sheet.status == "superseded"])
        index_match_count = len([sheet for sheet in store.data.sheets if sheet_is_index_like(sheet)])
        all_sheets = store.data.sheets
        if filter_status != "all":
            all_sheets = [sheet for sheet in all_sheets if sheet.status == filter_status]
        if not include_index_matches:
            all_sheets = [sheet for sheet in all_sheets if not sheet_is_index_like(sheet)]
        if search_query:
            query = search_query.lower()
            all_sheets = [
                sheet
                for sheet in all_sheets
                if query in " ".join([sheet.sheet_id, sheet.sheet_title, discipline_for_sheet(sheet.sheet_id)]).lower()
            ]
        changes_by_sheet = {}
        for item in store.data.change_items:
            changes_by_sheet[item.sheet_version_id] = changes_by_sheet.get(item.sheet_version_id, 0) + 1
        return render_template(
            "sheets.html",
            sheets=all_sheets,
            filter_status=filter_status,
            search_query=search_query,
            changes_by_sheet=changes_by_sheet,
            active_sheet_count=active_sheet_count,
            superseded_sheet_count=superseded_sheet_count,
            include_index_matches=include_index_matches,
            index_match_count=index_match_count,
        )

    @app.route("/sheets/<sheet_version_id>")
    def sheet_detail(sheet_version_id: str):
        try:
            sheet = store.get_sheet(sheet_version_id)
        except KeyError:
            abort(404)
        revision_sets_by_id = {revision_set.id: revision_set for revision_set in store.data.revision_sets}
        if sheet_is_index_like(sheet):
            replacement = latest_real_sheet_version(sheet, store.data.sheets, revision_sets_by_id)
            if replacement:
                return redirect(url_for("sheet_detail", sheet_version_id=replacement.id))
        chain = sorted([item for item in store.data.sheets if item.sheet_id == sheet.sheet_id], key=lambda item: (item.status != "active", item.page_number))
        clouds = store.sheet_clouds(sheet.id)
        changes = store.sheet_changes(sheet.id)
        narratives = [entry for entry in store.data.narrative_entries if entry.id in sheet.narrative_entry_ids]
        change_by_cloud = {item.cloud_candidate_id: item.id for item in changes if item.cloud_candidate_id}
        return render_template(
            "sheet_detail.html",
            sheet=sheet,
            chain=chain,
            clouds=clouds,
            changes=changes,
            narratives=narratives,
            change_by_cloud=change_by_cloud,
        )

    @app.route("/changes")
    def changes():
        filter_status = request.args.get("status", "pending")
        search_query = request.args.get("q", "")
        attention_only = request.args.get("attention", "0") == "1"
        items = filter_change_items(store, filter_status, search_query)
        if attention_only:
            items = [item for item in items if item.status == "pending" and change_item_needs_attention(item)]
        counts = {
            "all": len(store.data.change_items),
            "pending": len([item for item in store.data.change_items if item.status == "pending"]),
            "approved": len([item for item in store.data.change_items if item.status == "approved"]),
            "rejected": len([item for item in store.data.change_items if item.status == "rejected"]),
            "needs_check": len([item for item in store.data.change_items if item.status == "pending" and change_item_needs_attention(item)]),
        }
        first_pending = next((item for item in filter_change_items(store, "pending", "")), None)
        return render_template(
            "changes.html",
            items=items,
            filter_status=filter_status,
            search_query=search_query,
            attention_only=attention_only,
            counts=counts,
            first_pending=first_pending,
        )

    @app.route("/changes/<change_id>")
    def change_detail(change_id: str):
        try:
            item = store.get_change_item(change_id)
        except KeyError:
            abort(404)
        sheet = store.get_sheet(item.sheet_version_id)
        cloud = store.get_cloud(item.cloud_candidate_id) if item.cloud_candidate_id else None
        verifications = store.change_verifications(change_id)
        queue_status = request.args.get("queue", "pending")
        search_query = request.args.get("q", "")
        attention_only = request.args.get("attention", "0") == "1"
        queue_items = filter_change_items(store, queue_status, search_query)
        if attention_only:
            queue_items = [queued_item for queued_item in queue_items if queued_item.status == "pending" and change_item_needs_attention(queued_item)]
        navigation = build_change_navigation(queue_items, change_id)
        return render_template(
            "change_detail.html",
            item=item,
            sheet=sheet,
            cloud=cloud,
            verifications=verifications,
            provider_name=provider.name,
            queue_status=queue_status,
            search_query=search_query,
            attention_only=attention_only,
            navigation=navigation,
            item_needs_attention=item.status == "pending" and change_item_needs_attention(item),
            sheet_revision_set=next((revision_set for revision_set in store.data.revision_sets if revision_set.id == sheet.revision_set_id), None),
        )

    @app.post("/changes/<change_id>/review")
    def review_change(change_id: str):
        try:
            item = store.get_change_item(change_id)
        except KeyError:
            abort(404)
        status = request.form.get("status_override") or request.form.get("status", item.status)
        reviewer_text = request.form.get("reviewer_text", item.reviewer_text or item.raw_text)
        reviewer_notes = request.form.get("reviewer_notes", item.reviewer_notes)
        store.update_change_item(change_id, status=status, reviewer_text=reviewer_text, reviewer_notes=reviewer_notes)
        flash(f"Updated {change_id} to {status}.", "success")
        attention_param = request.form.get("attention_only", "0")
        if request.form.get("advance") == "next" and request.form.get("next_change_id"):
            redirect_kwargs = {
                "change_id": request.form["next_change_id"],
                "queue": request.form.get("queue_status", "pending"),
                "q": request.form.get("search_query", ""),
            }
            if attention_param == "1":
                redirect_kwargs["attention"] = "1"
            redirect_to = url_for(
                "change_detail",
                **redirect_kwargs,
            )
        else:
            if request.form.get("redirect_to"):
                redirect_to = request.form["redirect_to"]
            else:
                redirect_kwargs = {
                    "change_id": change_id,
                    "queue": request.form.get("queue_status", "pending"),
                    "q": request.form.get("search_query", ""),
                }
                if attention_param == "1":
                    redirect_kwargs["attention"] = "1"
                redirect_to = url_for("change_detail", **redirect_kwargs)
        return redirect(redirect_to)

    @app.post("/changes/bulk-review")
    def bulk_review():
        selected_ids = request.form.getlist("change_ids")
        if not selected_ids:
            flash("No queue items were selected.", "warning")
            return redirect(request.form.get("redirect_to") or url_for("changes"))
        status = request.form.get("status")
        if status not in {"pending", "approved", "rejected"}:
            flash("Choose a valid bulk action.", "warning")
            return redirect(request.form.get("redirect_to") or url_for("changes"))
        count = 0
        for change_id in selected_ids:
            try:
                item = store.get_change_item(change_id)
            except KeyError:
                continue
            reviewer_text = item.reviewer_text or item.raw_text
            store.update_change_item(change_id, status=status, reviewer_text=reviewer_text)
            count += 1
        flash(f"Updated {count} queue items to {status}.", "success")
        return redirect(request.form.get("redirect_to") or url_for("changes"))

    @app.post("/changes/<change_id>/verify")
    def verify_change(change_id: str):
        try:
            store.get_change_item(change_id)
        except KeyError:
            abort(404)
        return jsonify({"error": "Review assist is currently disabled while CloudHammer model integration is in progress."}), 400

    @app.post("/changes/<change_id>/apply-verification/<verification_id>")
    def apply_verification(change_id: str, verification_id: str):
        abort(404)

    @app.route("/export")
    def export_view():
        export_history = list(reversed(store.data.exports))
        attention_pending_count = len(
            [item for item in store.data.change_items if item.status == "pending" and change_item_needs_attention(item)]
        )
        return render_template(
            "export.html",
            export_history=export_history,
            attention_pending_count=attention_pending_count,
            output_files=build_output_files(),
            pricing_summary=Exporter(store).pricing_summary(),
        )

    @app.post("/export/run")
    def export_run():
        force_attention = request.form.get("force_attention") == "1"
        try:
            outputs = Exporter(store).export(force_attention=force_attention)
        except ExportBlockedError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("export_view"))
        flash(f"Exported {len(outputs)} files to {store.output_dir}.", "success")
        return redirect(url_for("export_view"))

    @app.post("/review-packet/run")
    def review_packet_run():
        result = build_review_packet(store)
        flash(f"Review packet ready with {result.item_count} change crops.", "success")
        return redirect(url_for("output_asset", asset_path=result.html_path.relative_to(store.output_dir).as_posix()))

    @app.route("/settings")
    def settings():
        verification_history = list(reversed(store.data.verifications))
        return render_template("settings.html", provider=provider, verification_history=verification_history)

    @app.route("/diagnostics")
    def diagnostics():
        filter_severity = request.args.get("severity", "all")
        issues = store.data.preflight_issues
        if filter_severity != "all":
            issues = [issue for issue in issues if issue.severity == filter_severity]
        issue_summary = [
            {
                "severity": severity,
                "code": code,
                "count": count,
                "message": next(
                    (issue.message for issue in store.data.preflight_issues if issue.severity == severity and issue.code == code),
                    "",
                ),
            }
            for (severity, code), count in Counter((issue.severity, issue.code) for issue in store.data.preflight_issues).most_common()
        ]
        documents = sorted(
            store.data.documents,
            key=lambda item: (item.max_severity != "high", item.max_severity != "medium", -item.warning_count, item.source_pdf),
        )
        return render_template(
            "diagnostics.html",
            documents=documents,
            issues=issues,
            issue_summary=issue_summary,
            filter_severity=filter_severity,
        )

    @app.route("/workspace-assets/<path:asset_path>")
    def workspace_asset(asset_path: str):
        return send_from_directory(store.assets_dir.resolve(), asset_path)

    @app.route("/workspace-assets/sheets-hi/<sheet_version_id>.png")
    def sheet_viewer_asset(sheet_version_id: str):
        try:
            sheet = store.get_sheet(sheet_version_id)
        except KeyError:
            abort(404)
        return send_from_directory(high_res_sheet_path(sheet).parent.resolve(), ensure_high_res_sheet(sheet).name)

    @app.route("/workspace-assets/clouds-hi/<cloud_id>.png")
    def cloud_viewer_asset(cloud_id: str):
        try:
            cloud = store.get_cloud(cloud_id)
        except KeyError:
            abort(404)
        return send_from_directory(high_res_cloud_path(cloud).parent.resolve(), ensure_high_res_cloud(cloud).name)

    @app.route("/workspace-assets/cloud-comparisons/<cloud_id>.png")
    def cloud_comparison_asset(cloud_id: str):
        try:
            cloud = store.get_cloud(cloud_id)
        except KeyError:
            abort(404)
        comparison_path = ensure_cloud_comparison(cloud)
        return send_from_directory(comparison_path.parent.resolve(), comparison_path.name)

    @app.route("/project-assets/<path:asset_path>")
    def project_asset(asset_path: str):
        return send_from_directory(project_root, asset_path)

    @app.route("/outputs/<path:asset_path>")
    def output_asset(asset_path: str):
        return send_from_directory(store.output_dir.resolve(), asset_path)

    return app
