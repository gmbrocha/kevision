from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import shutil
import time
import uuid
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import fitz
from flask import Flask, abort, flash, g, has_request_context, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from backend.bulk_review_jobs import BulkReviewJobConflict, BulkReviewJobManager
from backend.cloudhammer_client.inference import ManifestCloudInferenceClient
from backend.cloudhammer_client.live_pipeline import CloudHammerRunResult, CloudHammerRunner, LiveCloudHammerPipeline
from backend.crop_adjustments import (
    CropAdjustmentError,
    apply_crop_adjustment,
    build_selected_review_overlay_image,
    crop_adjustment_template_context,
    selected_review_page_boxes,
)
from backend.diagnostics import build_diagnostic_summary, configure_mupdf, format_pdf_label
from backend.deliverables.crop_comparison import build_cloud_comparison_image, find_previous_sheet_version
from backend.deliverables.excel_exporter import ExportBlockedError, Exporter
from backend.deliverables.review_packet import build_review_packet
from backend.geometry_corrections import GeometryCorrectionError, apply_geometry_correction
from backend.legend_context import (
    confirm_legend_context_item,
    enrich_workspace_legend_context,
    is_probable_legend_context,
    legend_context_human_result,
    legend_context_payload,
    legend_context_text,
)
from backend.keynote_legends import (
    KEYNOTE_REGISTRY_EXTRACTOR_VERSION,
    KEYNOTE_REGISTRY_SCHEMA,
    apply_pre_review_keynote_expansions,
    build_workspace_keynote_registry,
    keynote_expansion_payload,
)
from backend.local_env import load_local_env_defaults
from backend.package_runs import (
    assemble_cloudhammer_package_runs,
    build_failed_package_run_record,
    build_package_run_record,
    plan_package_runs,
)
from backend.projects import ProjectRecord, ProjectRegistry, default_app_data_dir
from backend.pre_review import (
    PRE_REVIEW_1,
    PRE_REVIEW_2,
    build_pre_review_provider_from_env,
    ensure_workspace_pre_review,
    pre_review_payload,
    select_pre_review_source,
)
from backend.review import change_item_needs_attention
from backend.review_events import record_review_update
from backend.review_queue import ensure_queue_order, is_superseded, ordered_change_items, review_queue_counts, visible_change_items
from backend.revision_state.page_classification import sheet_is_index_like
from backend.revision_state.tracker import SHEET_METADATA_CACHE_VERSION, RevisionScanner
from backend.scope_extraction import enrich_workspace_scope_text
from backend.staged_packages import (
    infer_revision_number_from_name,
    parse_revision_number,
    reconcile_staged_packages,
    register_staged_package,
    staged_package_sort_key,
    update_revision_numbers,
    validate_staged_packages,
)
from backend.workspace import WorkspaceStore


class DisabledReviewAssistProvider:
    """Placeholder until local-model review assist is wired into the web app."""

    name = "archived"
    enabled = False


VALID_PACKAGE_SCOPES = {"all", "newest", "package"}


def path_identity(value: str) -> str:
    if not value:
        return ""
    return str(Path(value).resolve()).lower()


def package_context(store: WorkspaceStore) -> dict[str, object]:
    packages = sorted(store.data.staged_packages, key=staged_package_sort_key)
    packages_by_id = {package.id: package for package in packages}
    packages_by_source = {path_identity(package.source_dir): package for package in packages}
    packages_by_folder = {package.folder_name.lower(): package for package in packages}
    revision_sets_by_id = {revision_set.id: revision_set for revision_set in store.data.revision_sets}
    revision_package_ids: dict[str, str] = {}
    for revision_set in store.data.revision_sets:
        package = packages_by_source.get(path_identity(revision_set.source_dir))
        if package is None:
            package = packages_by_folder.get(Path(revision_set.source_dir).name.lower())
        if package is not None:
            revision_package_ids[revision_set.id] = package.id

    sheet_package_ids: dict[str, str] = {}
    for sheet in store.data.sheets:
        package_id = revision_package_ids.get(sheet.revision_set_id)
        if package_id:
            sheet_package_ids[sheet.id] = package_id

    item_package_ids: dict[str, str] = {}
    for item in visible_change_items(store.data.change_items):
        package_id = sheet_package_ids.get(item.sheet_version_id)
        if package_id:
            item_package_ids[item.id] = package_id

    newest_package = max(
        [package for package in packages if package.revision_number is not None],
        key=lambda package: (package.revision_number or 0, package.label.lower()),
        default=None,
    )
    return {
        "packages": packages,
        "packages_by_id": packages_by_id,
        "revision_sets_by_id": revision_sets_by_id,
        "sheet_package_ids": sheet_package_ids,
        "item_package_ids": item_package_ids,
        "newest_package": newest_package,
    }


def normalize_package_filter(store: WorkspaceStore, package_scope: str = "all", package_id: str = "") -> tuple[str, str]:
    context = package_context(store)
    packages_by_id = context["packages_by_id"]
    scope = package_scope if package_scope in VALID_PACKAGE_SCOPES else "all"
    if scope == "newest":
        newest = context["newest_package"]
        return ("newest", newest.id if newest else "")
    if scope == "package" and package_id in packages_by_id:
        return ("package", package_id)
    return ("all", "")


def package_query_args(package_scope: str, package_id: str) -> dict[str, str]:
    if package_scope in {"newest", "package"}:
        return {"package_scope": package_scope, "package_id": package_id}
    return {}


def filter_change_items(
    store: WorkspaceStore,
    filter_status: str,
    search_query: str,
    package_scope: str = "all",
    package_id: str = "",
) -> list:
    ensure_review_queue_state(store)
    package_scope, package_id = normalize_package_filter(store, package_scope, package_id)
    context = package_context(store)
    items = visible_change_items(store.data.change_items)
    if package_scope in {"newest", "package"} and package_id:
        item_package_ids = context["item_package_ids"]
        items = [item for item in items if item_package_ids.get(item.id) == package_id]
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
    return ordered_change_items(items)


def review_package_filter_context(store: WorkspaceStore, package_scope: str = "all", package_id: str = "") -> dict[str, object]:
    package_scope, package_id = normalize_package_filter(store, package_scope, package_id)
    context = package_context(store)
    item_package_ids = context["item_package_ids"]
    visible = visible_change_items(store.data.change_items)
    pending_by_package = Counter(item_package_ids.get(item.id, "") for item in visible if item.status == "pending")
    total_by_package = Counter(item_package_ids.get(item.id, "") for item in visible)
    options = []
    for package in context["packages"]:
        options.append(
            {
                "id": package.id,
                "label": package.label,
                "revision_number": package.revision_number,
                "pending_count": pending_by_package.get(package.id, 0),
                "total_count": total_by_package.get(package.id, 0),
            }
        )
    selected_package = context["packages_by_id"].get(package_id) if package_id else None
    newest_package = context["newest_package"]
    return {
        "package_scope": package_scope,
        "package_id": package_id,
        "query_args": package_query_args(package_scope, package_id),
        "options": options,
        "selected_package": selected_package,
        "newest_package": newest_package,
        "newest_pending_count": pending_by_package.get(newest_package.id, 0) if newest_package else 0,
        "all_pending_count": len([item for item in visible if item.status == "pending"]),
    }


def ensure_review_queue_state(store: WorkspaceStore) -> bool:
    updated_items, changed = ensure_queue_order(store.data.change_items)
    if changed:
        store.data.change_items = updated_items
        store.save()
    return changed


def visible_review_counts(store: WorkspaceStore) -> dict[str, int]:
    ensure_review_queue_state(store)
    counts = review_queue_counts(store.data.change_items)
    visible = visible_change_items(store.data.change_items)
    counts["needs_check"] = len([item for item in visible if item.status == "pending" and change_item_needs_attention(item)])
    return counts


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


def sheet_has_later_real_revision(sheet, all_sheets: list, revision_sets_by_id: dict) -> bool:
    current_revision = revision_sets_by_id.get(sheet.revision_set_id)
    if current_revision is None:
        return False
    current_number = current_revision.set_number
    for candidate in all_sheets:
        if candidate.id == sheet.id or candidate.sheet_id != sheet.sheet_id or sheet_is_index_like(candidate):
            continue
        candidate_revision = revision_sets_by_id.get(candidate.revision_set_id)
        if candidate_revision and candidate_revision.set_number > current_number:
            return True
    return False


def sheet_status_for_drawings(sheet, all_sheets: list, revision_sets_by_id: dict) -> str:
    return "superseded" if sheet_has_later_real_revision(sheet, all_sheets, revision_sets_by_id) else "active"


HIGH_RES_SHEET_SCALE = 2.25
HIGH_RES_CROP_MAX_SCALE = 6.0
HIGH_RES_CROP_TARGET_WIDTH = 1800
DRIVE_REVIEW_FOLDER_URL = "https://drive.google.com/drive/folders/1_6LogBKmxt38bF9dGBPyc1l_z38z1MaT"
SAFE_PROJECT_ASSET_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
VALID_REVIEW_STATUSES = {"pending", "approved", "rejected"}
DEFAULT_DEV_SECRET_KEY = "scopeledger-dev"  # nosec B105
CHUNKED_UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024
MAX_CHUNKED_UPLOAD_CHUNK_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_CHUNKED_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_CHUNKED_UPLOAD_FILES = 500
CHUNKED_UPLOAD_STALE_SECONDS = 6 * 60 * 60
UPLOAD_ID_RE = re.compile(r"^[a-f0-9]{32}$")


class ActiveProjectWorkspace:
    def __init__(self, current_store):
        self.current_store = current_store

    def current(self) -> WorkspaceStore:
        return self.current_store()

    def __getattr__(self, name):
        return getattr(self.current(), name)


def _load_secret_key(*, production: bool) -> str:
    secret = os.getenv("SCOPELEDGER_WEBAPP_SECRET", "")
    if production and not secret:
        raise RuntimeError("SCOPELEDGER_WEBAPP_SECRET is required when production mode is enabled.")
    return secret or DEFAULT_DEV_SECRET_KEY


def _configured_allowed_import_roots() -> tuple[Path, ...]:
    raw_value = os.getenv("SCOPELEDGER_ALLOWED_IMPORT_ROOTS", "")
    roots = []
    for item in raw_value.split(os.pathsep):
        root_text = item.strip().strip('"')
        if root_text:
            roots.append(Path(root_text).expanduser().resolve())
    return tuple(roots)


def _configured_max_chunked_upload_bytes() -> int:
    raw_value = os.getenv("SCOPELEDGER_MAX_UPLOAD_BYTES", "").strip()
    if not raw_value:
        return DEFAULT_MAX_CHUNKED_UPLOAD_BYTES
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("SCOPELEDGER_MAX_UPLOAD_BYTES must be an integer byte count.") from exc
    if value < MAX_CHUNKED_UPLOAD_CHUNK_BYTES:
        raise RuntimeError("SCOPELEDGER_MAX_UPLOAD_BYTES must be at least 16777216 bytes.")
    return value


def create_app(
    app_data_dir: Path | None = None,
    verification_provider=None,
    cloudhammer_runner: CloudHammerRunner | None = None,
    pre_review_provider=None,
    bulk_review_manager: BulkReviewJobManager | None = None,
    *,
    production: bool = False,
) -> Flask:
    configure_mupdf()
    project_root = Path.cwd().resolve()
    loaded_env_files = load_local_env_defaults(project_root)
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = _load_secret_key(production=production)
    registry = ProjectRegistry(Path(app_data_dir) if app_data_dir else default_app_data_dir()).load()
    provider = verification_provider or DisabledReviewAssistProvider()
    cloudhammer_runner = cloudhammer_runner or LiveCloudHammerPipeline()
    pre_review_provider = pre_review_provider or build_pre_review_provider_from_env()
    bulk_review_manager = bulk_review_manager or BulkReviewJobManager()
    allowed_import_roots = _configured_allowed_import_roots()
    max_chunked_upload_bytes = _configured_max_chunked_upload_bytes()
    app.config["STORE"] = None
    app.config["PROJECT_REGISTRY"] = registry
    app.config["REVIEW_ASSIST_PROVIDER"] = provider
    app.config["CLOUDHAMMER_RUNNER"] = cloudhammer_runner
    app.config["PRE_REVIEW_PROVIDER"] = pre_review_provider
    app.config["BULK_REVIEW_JOBS"] = bulk_review_manager
    app.config["SCOPELEDGER_LOADED_ENV_FILES"] = loaded_env_files
    app.config["SCOPELEDGER_PRODUCTION"] = production
    app.config["SCOPELEDGER_ALLOWED_IMPORT_ROOTS"] = allowed_import_roots
    app.config["SCOPELEDGER_MAX_CHUNKED_UPLOAD_BYTES"] = max_chunked_upload_bytes
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if production:
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["MAX_CONTENT_LENGTH"] = MAX_CHUNKED_UPLOAD_CHUNK_BYTES + (1024 * 1024)
    project_asset_roots = [
        project_root / "CloudHammer" / "runs",
        project_root / "CloudHammer" / "data" / "rasterized_pages",
        project_root / "CloudHammer_v2" / "outputs",
    ]
    project_optional_endpoints = {
        "index",
        "projects",
        "create_project",
        "dashboard",
        "conformed",
        "sheets",
        "changes",
        "export_view",
        "settings",
        "diagnostics",
        "workspace_folder_dialog",
        "select_project",
        "archive_project",
        "restore_project",
        "delete_project",
        "static",
    }
    bulk_review_locked_post_endpoints = {
        "import_package",
        "append_package_file",
        "save_package_order",
        "init_chunked_upload",
        "receive_chunked_upload_chunk",
        "complete_chunked_upload",
        "populate_workspace",
        "update_crop_adjustment",
        "update_geometry_correction",
        "accept_legend_context",
        "review_change",
        "export_run",
        "review_packet_run",
    }

    def active_project_or_none() -> ProjectRecord | None:
        project_id = session.get("project_id")
        if project_id:
            try:
                project = registry.get(project_id)
                if project.status == "active":
                    return project
            except KeyError:
                pass
        project = registry.first_active()
        if project:
            session["project_id"] = project.id
        else:
            session.pop("project_id", None)
        return project

    def active_project() -> ProjectRecord:
        project = active_project_or_none()
        if project is None:
            raise RuntimeError("No active project is selected.")
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

    def csrf_token() -> str:
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def csrf_field() -> str:
        return f'<input type="hidden" name="csrf_token" value="{csrf_token()}">'

    def request_csrf_token() -> str:
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            return str(payload.get("csrf_token", ""))
        return request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")

    def csrf_error_response():
        message = "Invalid or missing form token. Refresh the page and try again."
        if request.path.startswith("/uploads/") or "application/json" in request.headers.get("Accept", ""):
            return jsonify({"error": message}), 400
        abort(400, description=message)

    @app.before_request
    def enforce_csrf_for_production_posts():
        if not app.config["SCOPELEDGER_PRODUCTION"] or request.method != "POST":
            return None
        expected = session.get("csrf_token")
        supplied = request_csrf_token()
        if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
            return csrf_error_response()
        return None

    @app.before_request
    def require_project_for_workspace_routes():
        endpoint = request.endpoint or ""
        if endpoint in project_optional_endpoints:
            return None
        if active_project_or_none() is None:
            flash("Create or restore a project before running workspace actions.", "warning")
            return redirect(url_for("projects"))
        return None

    @app.before_request
    def block_workspace_mutations_during_bulk_review():
        if request.method != "POST" or (request.endpoint or "") not in bulk_review_locked_post_endpoints:
            return None
        project = active_project_or_none()
        if project is not None and bulk_review_manager.has_running_job(project.id):
            return bulk_review_block_response()
        return None

    @app.after_request
    def add_release_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if app.config["SCOPELEDGER_PRODUCTION"]:
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def rescan_active_project(cloud_inference_client=None) -> tuple[WorkspaceStore, int]:
        project = active_project()
        current = load_project_store(project)
        scanner = RevisionScanner(
            Path(current.data.input_dir),
            Path(project.workspace_dir),
            cloud_inference_client=cloud_inference_client,
        )
        return scanner.scan(), scanner.cache_hits

    def utc_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def safe_redirect_target(value: str | None, default: str) -> str:
        target = (value or "").strip()
        if not target or "\\" in target:
            return default
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
            return default
        return target

    def local_referrer_or(default: str) -> str:
        referrer = request.referrer or ""
        parsed = urlsplit(referrer)
        if parsed.scheme or parsed.netloc:
            if parsed.netloc != request.host:
                return default
        target = parsed.path or ""
        if parsed.query:
            target = f"{target}?{parsed.query}"
        return safe_redirect_target(target, default)

    def bulk_review_block_response():
        message = "A bulk review update is running. Workspace changes will be available when it finishes."
        if request.is_json or "application/json" in request.headers.get("Accept", ""):
            return jsonify({"error": message}), 409
        flash(message, "warning")
        return redirect(local_referrer_or(url_for("changes")))

    def review_url_kwargs(
        *,
        queue_status: str = "pending",
        search_query: str = "",
        attention_only: bool = False,
        package_scope: str = "all",
        package_id: str = "",
    ) -> dict[str, str]:
        scope, selected_package_id = normalize_package_filter(store, package_scope, package_id)
        kwargs: dict[str, str] = {}
        if queue_status:
            kwargs["queue"] = queue_status
        kwargs["q"] = search_query
        kwargs.update(package_query_args(scope, selected_package_id))
        if attention_only:
            kwargs["attention"] = "1"
        return kwargs

    def replacement_redirect_target(
        item,
        *,
        queue_status: str = "pending",
        search_query: str = "",
        attention_only: bool = False,
        package_scope: str = "all",
        package_id: str = "",
    ) -> str:
        for replacement_id in item.superseded_by_change_item_ids:
            try:
                store.get_change_item(replacement_id)
            except KeyError:
                continue
            kwargs = {
                "change_id": replacement_id,
                **review_url_kwargs(
                    queue_status=queue_status,
                    search_query=search_query,
                    attention_only=attention_only,
                    package_scope=package_scope,
                    package_id=package_id,
                ),
            }
            return url_for("change_detail", **kwargs)
        kwargs = review_url_kwargs(
            queue_status="",
            search_query=search_query,
            attention_only=attention_only,
            package_scope=package_scope,
            package_id=package_id,
        )
        kwargs["status"] = queue_status
        return url_for("changes", **kwargs)

    def next_pending_change_id_after(
        change_id: str,
        *,
        search_query: str = "",
        attention_only: bool = False,
        package_scope: str = "all",
        package_id: str = "",
    ) -> str | None:
        queue_items = filter_change_items(store, "pending", search_query, package_scope, package_id)
        if attention_only:
            queue_items = [item for item in queue_items if item.status == "pending" and change_item_needs_attention(item)]
        ids = [item.id for item in queue_items]
        if change_id in ids:
            index = ids.index(change_id)
            for candidate_id in ids[index + 1 :]:
                return candidate_id
        for candidate_id in ids:
            if candidate_id != change_id:
                return candidate_id
        if search_query or attention_only:
            for item in filter_change_items(store, "pending", "", package_scope, package_id):
                if item.id != change_id:
                    return item.id
        return None

    def next_change_id_after_in_queue(
        change_id: str,
        *,
        queue_status: str = "pending",
        search_query: str = "",
        attention_only: bool = False,
        package_scope: str = "all",
        package_id: str = "",
    ) -> str | None:
        queue_items = filter_change_items(store, queue_status, search_query, package_scope, package_id)
        if attention_only:
            queue_items = [item for item in queue_items if item.status == "pending" and change_item_needs_attention(item)]
        navigation = build_change_navigation(queue_items, change_id)
        next_id = navigation.get("next_change_id")
        return str(next_id) if next_id else None

    def current_review_session_id() -> str:
        value = session.get("review_session_id")
        if not value:
            value = uuid.uuid4().hex
            session["review_session_id"] = value
        return str(value)

    def current_reviewer_id() -> str:
        email = (
            request.headers.get("Cf-Access-Authenticated-User-Email")
            or request.headers.get("CF-Access-Authenticated-User-Email")
        )
        if email:
            return email.strip().lower()
        name = (
            request.headers.get("Cf-Access-Authenticated-User-Name")
            or request.headers.get("CF-Access-Authenticated-User-Name")
        )
        if name:
            return name.strip()
        value = session.get("reviewer_id")
        if not value:
            value = f"anonymous:{uuid.uuid4().hex}"
            session["reviewer_id"] = value
        return str(value)

    def is_safe_project_asset(path: Path) -> bool:
        if path.suffix.lower() not in SAFE_PROJECT_ASSET_SUFFIXES:
            return False
        try:
            resolved = path.resolve()
        except OSError:
            return False
        for root in project_asset_roots:
            try:
                resolved.relative_to(root.resolve())
                return True
            except ValueError:
                continue
        return False

    def empty_pricing_summary() -> dict[str, object]:
        return {
            "output_dir": "",
            "approved_count": 0,
            "pending_count": 0,
            "rejected_count": 0,
            "attention_pending_count": 0,
            "force_attention": False,
            "pricing_log_count": 0,
            "pricing_candidate_count": 0,
            "filtered_count": 0,
            "filtered_by_reason": {},
            "active_sheet_count": 0,
            "superseded_sheet_count": 0,
            "revision_set_count": 0,
        }

    def empty_counts() -> dict[str, int]:
        return {"all": 0, "pending": 0, "approved": 0, "rejected": 0, "needs_check": 0}

    def empty_output_files() -> dict[str, Path]:
        missing_output_dir = registry.app_data_dir / "__no_active_project_outputs__"
        return {
            "workbook": missing_output_dir / "revision_changelog.xlsx",
            "review_packet": missing_output_dir / "revision_changelog_review_packet.html",
            "preview_pdf": missing_output_dir / "conformed_preview.pdf",
        }

    def count_jsonl_rows(path: Path) -> int:
        if not path.exists():
            return 0
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())

    def package_revision_label(package) -> str:
        if package.revision_number:
            return f"Revision {package.revision_number}"
        return package.label or package.folder_name

    def package_run_display_status(plan) -> str:
        record = plan.record or {}
        if record.get("status") == "failed":
            return "failed"
        if plan.is_dirty:
            return "pending" if not record else "dirty"
        if record.get("last_action") == "reused":
            return "reused"
        if record.get("status") == "complete":
            return "processed"
        return str(record.get("status") or "pending")

    def package_run_display_action(plan) -> str:
        status = package_run_display_status(plan)
        if status == "dirty":
            return "process"
        if status == "pending":
            return "process"
        return status

    def summarize_populate_artifacts(project: ProjectRecord, store: WorkspaceStore, runner: CloudHammerRunner | None = None) -> dict[str, object]:
        input_dir = Path(store.data.input_dir)
        staged_pdfs = sorted(input_dir.rglob("*.pdf")) if input_dir.exists() else []
        package_dirs = {pdf.parent for pdf in staged_pdfs}
        status = dict(store.data.populate_status or {})
        run_dir_text = status.get("cloudhammer_run_dir")
        run_dir = Path(str(run_dir_text)) if run_dir_text else None
        live_root = Path(project.workspace_dir) / "outputs" / "cloudhammer_live"
        if run_dir is None and live_root.exists():
            run_dirs = [path for path in live_root.iterdir() if path.is_dir()]
            run_dir = max(run_dirs, key=lambda path: path.stat().st_mtime, default=None)

        live_artifact_count = 0
        live_last_write = ""
        live_run_dir = ""
        inferred_pages = 0
        inferred_candidates = 0
        if run_dir and run_dir.exists():
            live_run_dir = str(run_dir)
            latest_mtime = 0.0
            for path in run_dir.rglob("*"):
                if not path.is_file():
                    continue
                live_artifact_count += 1
                try:
                    latest_mtime = max(latest_mtime, path.stat().st_mtime)
                except OSError:
                    continue
            if latest_mtime:
                live_last_write = datetime.fromtimestamp(latest_mtime, timezone.utc).isoformat()
            inferred_pages = count_jsonl_rows(run_dir / "pages_manifest.jsonl")
            inferred_candidates = count_jsonl_rows(run_dir / "whole_cloud_candidates" / "whole_cloud_candidates_manifest.jsonl")

        summary = {
            "staged_package_count": len(package_dirs),
            "staged_pdf_count": len(staged_pdfs),
            "live_run_dir": live_run_dir,
            "live_artifact_count": live_artifact_count,
            "live_last_write": live_last_write,
            "inferred_cloudhammer_page_count": inferred_pages,
            "inferred_cloudhammer_candidate_count": inferred_candidates,
        }
        if runner is not None:
            packages, _ = reconcile_staged_packages(store, save=False)
            plans = plan_package_runs(store, runner, sorted(packages, key=staged_package_sort_key))
            dirty = [plan for plan in plans if plan.is_dirty]
            complete = [plan for plan in plans if not plan.is_dirty]
            next_plan = dirty[0] if dirty else None
            summary.update(
                {
                    "total_package_count": len(plans),
                    "dirty_package_count": len(dirty),
                    "reusable_package_count": len(complete),
                    "next_package_label": next_plan.package.label if next_plan else "",
                    "next_revision_number": next_plan.package.revision_number if next_plan else "",
                    "next_dirty_reason": next_plan.dirty_reason if next_plan else "",
                    "package_run_rows": [
                        {
                            "package_id": plan.package.id,
                            "label": plan.package.label,
                            "revision_number": plan.package.revision_number,
                            "action": package_run_display_action(plan),
                            "dirty_reason": plan.dirty_reason,
                            "status": package_run_display_status(plan),
                            "last_action": (plan.record or {}).get("last_action", ""),
                            "processed_at": (plan.record or {}).get("processed_at", ""),
                            "failed_at": (plan.record or {}).get("failed_at", ""),
                            "last_error": (plan.record or {}).get("last_error", ""),
                            "page_count": (plan.record or {}).get("page_count", 0),
                            "candidate_count": (plan.record or {}).get("candidate_count", 0),
                        }
                        for plan in plans
                    ],
                }
            )
        return summary

    def populate_status_payload(project: ProjectRecord, store: WorkspaceStore) -> dict[str, object]:
        status = dict(store.data.populate_status or {})
        status.update(summarize_populate_artifacts(project, store, app.config["CLOUDHAMMER_RUNNER"]))
        state = str(status.get("state") or "idle")
        if state not in {"running", "failed", "blocked", "done"} and status.get("dirty_package_count"):
            next_label = status.get("next_package_label") or "the next package"
            next_revision = status.get("next_revision_number")
            revision_text = f"Revision {next_revision}" if next_revision else str(next_label)
            status["state"] = "ready"
            status["stage"] = "package_setup"
            status["message"] = f"Ready to process {revision_text}: {next_label}."
        return status

    def keynote_registry_status_from_store(store: WorkspaceStore) -> dict[str, int]:
        registry = store.data.keynote_registry if isinstance(store.data.keynote_registry, dict) else {}
        sheets = registry.get("sheets") if isinstance(registry.get("sheets"), dict) else {}
        definitions = [
            definition
            for entry in sheets.values()
            if isinstance(entry, dict)
            for definition in (entry.get("definitions") or [])
        ]
        return {
            "keynote_registry_scanned_sheet_count": len(sheets),
            "keynote_registry_sheet_count": len(
                [entry for entry in sheets.values() if isinstance(entry, dict) and entry.get("definitions")]
            ),
            "keynote_registry_definition_count": len(definitions),
            "keynote_registry_cache_hits": len(sheets),
        }

    def keynote_registry_covers_workspace(store: WorkspaceStore) -> bool:
        registry = store.data.keynote_registry if isinstance(store.data.keynote_registry, dict) else {}
        sheets = registry.get("sheets") if isinstance(registry.get("sheets"), dict) else {}
        eligible_sheets = [sheet for sheet in store.data.sheets if sheet.source_pdf and sheet.page_number >= 1]
        if not eligible_sheets:
            return True
        for sheet in eligible_sheets:
            entry = sheets.get(sheet.id)
            if not isinstance(entry, dict):
                return False
            if (
                entry.get("schema") != KEYNOTE_REGISTRY_SCHEMA
                or entry.get("extractor_version") != KEYNOTE_REGISTRY_EXTRACTOR_VERSION
            ):
                return False
            if entry.get("sheet_version_id") != sheet.id or entry.get("revision_set_id") != sheet.revision_set_id:
                return False
            if entry.get("page_number") != sheet.page_number or not isinstance(entry.get("definitions"), list):
                return False
        return True

    def workspace_missing_pre_review(store: WorkspaceStore) -> bool:
        provider = app.config["PRE_REVIEW_PROVIDER"]
        if not getattr(provider, "enabled", False):
            return False
        for item in store.data.change_items:
            if is_superseded(item) or item.provenance.get("source") != "visual-region":
                continue
            payload = pre_review_payload(item)
            pre_review_2 = payload.get(PRE_REVIEW_2) if isinstance(payload.get(PRE_REVIEW_2), dict) else None
            if not pre_review_2 or not pre_review_2.get("available"):
                return True
        return False

    def clean_populate_can_short_circuit(store: WorkspaceStore, dirty_count: int, rebuild_all: bool) -> bool:
        if rebuild_all or dirty_count:
            return False
        if not store.data.revision_sets or not store.data.sheets or not store.data.scan_cache.get("documents"):
            return False
        for entry in store.data.scan_cache.get("documents", {}).values():
            if entry.get("sheet_metadata_version") != SHEET_METADATA_CACHE_VERSION:
                return False
        if workspace_missing_pre_review(store):
            return False
        return keynote_registry_covers_workspace(store)

    def copy_package_source(source_path: Path, destination_dir: Path) -> int:
        destination_dir.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            copied = 0
            for pdf_path in sorted(source_path.rglob("*.pdf")):
                target = destination_dir / pdf_path.relative_to(source_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pdf_path, target)
                copied += 1
            return copied
        if source_path.is_file():
            if source_path.suffix.lower() != ".pdf":
                raise ValueError(f"Manual package file must be a PDF: {source_path}")
            shutil.copy2(source_path, destination_dir / source_path.name)
            return 1
        raise FileNotFoundError(source_path)

    def require_manual_source_allowed(source_path: Path) -> None:
        if not app.config["SCOPELEDGER_PRODUCTION"]:
            return
        roots: tuple[Path, ...] = app.config["SCOPELEDGER_ALLOWED_IMPORT_ROOTS"]
        if not roots:
            raise PermissionError("Manual server-path imports are disabled until SCOPELEDGER_ALLOWED_IMPORT_ROOTS is configured.")
        for root in roots:
            try:
                source_path.relative_to(root)
                return
            except ValueError:
                continue
        raise PermissionError("Manual server path is outside the configured production import allowlist.")

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

    def require_revision_number(value: object) -> int:
        revision_number = parse_revision_number(value)
        if revision_number is None:
            raise ValueError("Assign a positive revision number before importing a package.")
        return revision_number

    def register_package_folder(store: WorkspaceStore, folder: Path, label: str, revision_number: int | None) -> None:
        register_staged_package(
            store,
            folder,
            label=label or folder.name,
            revision_number=revision_number,
            save=True,
        )

    def set_package_setup_status(store: WorkspaceStore, *, error: str = "") -> None:
        if error:
            store.update_populate_status(
                state="blocked",
                stage="package_setup",
                message="Package setup needs attention.",
                error=error,
            )
            return
        store.update_populate_status(
            state="idle",
            stage="package_setup",
            message="Package staged. Confirm package order, then populate workspace.",
            error="",
        )

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

    def safe_upload_relative_path(filename: str, relative_path: str = "") -> Path:
        parts = safe_upload_parts(relative_path or filename)
        if not parts or Path(parts[-1]).suffix.lower() != ".pdf":
            raise ValueError(f"Only PDF files can be uploaded: {filename or relative_path}")
        return Path(*parts)

    def stage_uploaded_package(
        field_name: str,
        current: WorkspaceStore,
        package_label: str,
        revision_number: int,
    ) -> tuple[str, list[Path]]:
        input_dir = Path(current.data.input_dir)
        destination_name = safe_package_dir_name(package_label) or infer_package_name_from_uploads(field_name)
        destination_dir = input_dir / destination_name
        saved = save_uploaded_pdfs(field_name, destination_dir, preserve_relative=True)
        if saved:
            register_package_folder(current, destination_dir, destination_name, revision_number)
        return destination_name, saved

    def stage_manual_package(
        source_text: str,
        current: WorkspaceStore,
        package_label: str,
        revision_number: int | None,
    ) -> tuple[str, Path]:
        input_dir = Path(current.data.input_dir)
        source_path = Path(source_text).expanduser().resolve()
        require_manual_source_allowed(source_path)
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        if source_path.is_dir() and _is_revision_package_root(source_path):
            copied = []
            for package_dir in _revision_package_children(source_path):
                destination_dir = input_dir / safe_package_dir_name(package_dir.name)
                if copy_package_source(package_dir, destination_dir):
                    copied.append(destination_dir)
                    register_package_folder(
                        current,
                        destination_dir,
                        destination_dir.name,
                        infer_revision_number_from_name(package_dir.name),
                    )
            if not copied:
                raise ValueError(f"No PDF files found under revision package root: {source_path}")
            return f"{len(copied)} packages from {source_path.name}", input_dir
        if revision_number is None:
            raise ValueError("Assign a positive revision number before importing a package.")
        destination_name = safe_package_dir_name(package_label) or source_path.stem
        destination_dir = input_dir / destination_name
        copied_count = copy_package_source(source_path, destination_dir)
        if copied_count == 0:
            raise ValueError(f"No PDF files found under {source_path}")
        register_package_folder(current, destination_dir, destination_name, revision_number)
        return destination_name, destination_dir

    def _revision_package_children(source_path: Path) -> list[Path]:
        return sorted(
            child
            for child in source_path.iterdir()
            if child.is_dir() and re.search(r"Revision\s*#\s*\d+", child.name, re.IGNORECASE)
        )

    def _is_revision_package_root(source_path: Path) -> bool:
        children = _revision_package_children(source_path)
        if len(children) < 2:
            return False
        direct_pdfs = list(source_path.glob("*.pdf"))
        return not direct_pdfs

    def chunked_upload_root(project: ProjectRecord | None = None) -> Path:
        selected = project or active_project()
        return Path(selected.workspace_dir).resolve() / ".chunked_uploads"

    def chunked_upload_dir(upload_id: str, project: ProjectRecord | None = None) -> Path:
        if not UPLOAD_ID_RE.match(upload_id):
            raise ValueError("Invalid upload id.")
        return chunked_upload_root(project) / upload_id

    def chunked_metadata_path(upload_id: str, project: ProjectRecord | None = None) -> Path:
        return chunked_upload_dir(upload_id, project) / "metadata.json"

    def remove_chunked_upload(upload_id: str, project: ProjectRecord | None = None) -> bool:
        root = chunked_upload_root(project).resolve()
        upload_dir = chunked_upload_dir(upload_id, project).resolve()
        try:
            upload_dir.relative_to(root)
        except ValueError:
            return False
        if not upload_dir.exists():
            return False
        shutil.rmtree(upload_dir, ignore_errors=True)
        return True

    def cleanup_stale_chunked_uploads(project: ProjectRecord | None = None) -> int:
        root = chunked_upload_root(project)
        if not root.exists():
            return 0
        cutoff = time.time() - CHUNKED_UPLOAD_STALE_SECONDS
        deleted = 0
        for child in root.iterdir():
            if not child.is_dir() or not UPLOAD_ID_RE.match(child.name):
                continue
            try:
                if child.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
            if remove_chunked_upload(child.name, project):
                deleted += 1
        return deleted

    def load_chunked_metadata(upload_id: str, project: ProjectRecord | None = None) -> dict:
        metadata_path = chunked_metadata_path(upload_id, project)
        if not metadata_path.exists():
            raise FileNotFoundError("Upload session was not found.")
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def infer_package_name_from_upload_records(files: list[dict]) -> str:
        if not files:
            return "Uploaded_Package"
        parts = Path(files[0]["relative_path"]).parts
        if len(parts) > 1:
            return parts[0]
        return Path(parts[0]).stem if parts else "Uploaded_Package"

    def stage_chunked_uploaded_files(metadata: dict, assembled_paths: list[Path], current: WorkspaceStore) -> tuple[str, int]:
        files = metadata["files"]
        if metadata["purpose"] == "append_file":
            revision_set_id = metadata.get("revision_set_id", "")
            try:
                revision_set = next(item for item in current.data.revision_sets if item.id == revision_set_id)
            except StopIteration as exc:
                raise ValueError("Target package was not found.") from exc
            destination_dir = current.resolve_path(revision_set.source_dir)
            destination_dir.mkdir(parents=True, exist_ok=True)
            for file_record, assembled_path in zip(files, assembled_paths):
                target = destination_dir / Path(file_record["relative_path"]).name
                shutil.copy2(assembled_path, target)
            return revision_set.label, len(assembled_paths)

        package_label = metadata.get("package_label", "")
        revision_number = require_revision_number(metadata.get("revision_number"))
        destination_name = safe_package_dir_name(package_label) or infer_package_name_from_upload_records(files)
        destination_dir = Path(current.data.input_dir) / destination_name
        destination_dir.mkdir(parents=True, exist_ok=True)
        for file_record, assembled_path in zip(files, assembled_paths):
            relative_path = Path(file_record["relative_path"])
            if len(relative_path.parts) > 1 and relative_path.parts[0].lower() == destination_dir.name.lower():
                relative_path = Path(*relative_path.parts[1:]) if len(relative_path.parts) > 1 else Path(relative_path.name)
            target = destination_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(assembled_path, target)
        register_package_folder(current, destination_dir, destination_name, revision_number)
        return destination_name, len(assembled_paths)

    def assemble_chunked_upload(metadata: dict, upload_dir: Path) -> list[Path]:
        assembled_paths: list[Path] = []
        for file_record in metadata["files"]:
            file_index = int(file_record["index"])
            chunk_count = int(file_record["chunk_count"])
            assembled_path = upload_dir / f"file_{file_index}.assembled"
            with assembled_path.open("wb") as output:
                for chunk_index in range(chunk_count):
                    chunk_path = upload_dir / f"file_{file_index}_chunk_{chunk_index}.part"
                    if not chunk_path.exists():
                        raise FileNotFoundError(f"Missing upload chunk {chunk_index + 1} of {chunk_count} for {file_record['name']}.")
                    with chunk_path.open("rb") as chunk_file:
                        shutil.copyfileobj(chunk_file, output)
            if assembled_path.stat().st_size != int(file_record["size"]):
                raise ValueError(f"Uploaded file size mismatch for {file_record['name']}.")
            assembled_paths.append(assembled_path)
        return assembled_paths

    @app.context_processor
    def inject_globals() -> dict[str, object]:
        project = active_project_or_none()
        active_store = load_project_store(project) if project else None
        change_items = visible_change_items(active_store.data.change_items) if active_store else []
        total_changes = len(change_items)
        reviewed_count = len([item for item in change_items if item.status in {"approved", "rejected"}])
        current_package = max(active_store.data.revision_sets, key=lambda item: item.set_number, default=None) if active_store else None
        active_bulk_job = bulk_review_manager.active_job(project.id) if project else None
        bulk_review_job = active_bulk_job.to_dict() if active_bulk_job else None
        diagnostic_summary = (
            build_diagnostic_summary(active_store.data.documents, active_store.data.preflight_issues)
            if active_store
            else build_diagnostic_summary([], [])
        )
        return {
            "active_project": project,
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
            "pre_review_provider": pre_review_provider,
            "bulk_review_job": bulk_review_job,
            "bulk_review_job_running": bool(bulk_review_job),
            "diagnostic_summary": diagnostic_summary,
            "needs_attention": change_item_needs_attention,
            "pre_review_payload": pre_review_payload,
            "keynote_expansion_payload": keynote_expansion_payload,
            "legend_context_payload": legend_context_payload,
            "legend_context_text": legend_context_text,
            "pre_review_1": PRE_REVIEW_1,
            "pre_review_2": PRE_REVIEW_2,
            "drive_review_folder_url": DRIVE_REVIEW_FOLDER_URL,
            "is_production": app.config["SCOPELEDGER_PRODUCTION"],
            "csrf_token": csrf_token,
            "csrf_field": csrf_field,
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

    def pre_review_overlay_path(item) -> Path:
        overlay_dir = store.assets_dir / "pre_review"
        overlay_dir.mkdir(parents=True, exist_ok=True)
        return overlay_dir / f"{item.id}_pre_review.png"

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
        comparison_code_mtime = max(
            (project_root / "backend" / "deliverables" / "crop_comparison.py").stat().st_mtime,
            (project_root / "backend" / "revision_state" / "page_classification.py").stat().st_mtime,
        )
        source_mtime = max(source_mtime, comparison_code_mtime)
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

    def ensure_pre_review_overlay(item) -> Path:
        if not item.cloud_candidate_id:
            raise KeyError(item.id)
        cloud = store.get_cloud(item.cloud_candidate_id)
        output_path = pre_review_overlay_path(item)
        generated = build_selected_review_overlay_image(store, item, cloud, output_path, include_all=True)
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
            relative = resolved.relative_to(store.output_dir.resolve()).as_posix()
            return url_for("output_asset", asset_path=relative)
        except ValueError:
            pass
        try:
            relative = resolved.relative_to(project_root).as_posix()
            if is_safe_project_asset(resolved):
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
                ensure_review_queue_state(project_store)
                project_items = visible_change_items(project_store.data.change_items)
                rows.append(
                    {
                        "project": project,
                        "revision_set_count": len(project_store.data.revision_sets),
                        "sheet_count": len([sheet for sheet in project_store.data.sheets if sheet.status == "active"]),
                        "pending_count": len([item for item in project_items if item.status == "pending"]),
                        "approved_count": len([item for item in project_items if item.status == "approved"]),
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
        if workspace_dir:
            flash("Project storage is managed by ScopeLedger. Create the project, then add packages from Overview.", "warning")
            return redirect(url_for("projects"))
        try:
            project = registry.create_project(name=name)
        except Exception as exc:
            flash(f"Project creation failed: {exc}", "warning")
            return redirect(url_for("projects"))
        session["project_id"] = project.id
        flash(f"Created {project.name}. Add package files, then populate the workspace.", "success")
        return redirect(url_for("dashboard"))

    @app.get("/system/dialog/workspace-folder")
    def workspace_folder_dialog():
        if app.config["SCOPELEDGER_PRODUCTION"]:
            return jsonify({"error": "Server-side folder browsing is disabled in production handoff mode."}), 404
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
            if active:
                session["project_id"] = active[0].id
            else:
                session.pop("project_id", None)
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

    @app.post("/projects/<project_id>/delete")
    def delete_project(project_id: str):
        if bulk_review_manager.has_running_job(project_id):
            return bulk_review_block_response()
        confirmation = request.form.get("delete_confirmation", "")
        try:
            project = registry.delete_project(project_id, confirmation)
        except KeyError:
            abort(404)
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("projects"))
        except PermissionError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("projects"))
        except OSError as exc:
            flash(f"Project deletion failed: {exc}", "warning")
            return redirect(url_for("projects"))
        if session.get("project_id") == project.id:
            active = registry.active_projects()
            if active:
                session["project_id"] = active[0].id
            else:
                session.pop("project_id", None)
        flash(f"Deleted {project.name} and its managed project workspace.", "success")
        return redirect(url_for("projects"))

    @app.route("/")
    def index():
        return redirect(url_for("projects"))

    @app.route("/overview")
    def dashboard():
        project = active_project_or_none()
        if project is None:
            return render_template(
                "dashboard.html",
                revision_rows=[],
                staged_package_rows=[],
                package_setup_errors=[],
                can_populate=False,
                pricing_summary=empty_pricing_summary(),
                pending_review_count=0,
                first_pending=None,
                output_files=empty_output_files(),
                populate_status={},
            )
        cleanup_stale_chunked_uploads(project)
        active_store = load_project_store()
        reconcile_staged_packages(active_store, save=True)
        package_setup_errors = validate_staged_packages(active_store)
        revision_sets_by_folder = {Path(revision_set.source_dir).name.lower(): revision_set for revision_set in active_store.data.revision_sets}
        rows = []
        for package in sorted(active_store.data.staged_packages, key=staged_package_sort_key):
            revision_set = revision_sets_by_folder.get(package.folder_name.lower())
            set_sheets = [sheet for sheet in active_store.data.sheets if revision_set and sheet.revision_set_id == revision_set.id]
            set_change_items = [
                item
                for item in visible_change_items(active_store.data.change_items)
                if any(sheet.id == item.sheet_version_id for sheet in set_sheets)
            ]
            package_dir = Path(package.source_dir)
            pdf_files = sorted(package_dir.rglob("*.pdf")) if package_dir.exists() else []
            rows.append(
                {
                    "package": package,
                    "revision_set": revision_set,
                    "pdf_count": len(pdf_files),
                    "staged_files": [pdf.relative_to(package_dir).as_posix() for pdf in pdf_files],
                    "sheet_count": len(set_sheets),
                    "active_count": len([sheet for sheet in set_sheets if sheet.status == "active"]),
                    "superseded_count": len([sheet for sheet in set_sheets if sheet.status == "superseded"]),
                    "narrative_count": len([entry for entry in active_store.data.narrative_entries if revision_set and entry.revision_set_id == revision_set.id]),
                    "change_count": len(set_change_items),
                    "discipline": ", ".join(sorted({discipline_for_sheet(sheet.sheet_id) for sheet in set_sheets if sheet.sheet_id})[:3]) or "Drawings",
                }
            )
        pricing_summary = Exporter(active_store).pricing_summary()
        pending_review_count = len([item for item in visible_change_items(active_store.data.change_items) if item.status == "pending"])
        first_pending = next((item for item in filter_change_items(active_store, "pending", "")), None)
        return render_template(
            "dashboard.html",
            revision_rows=rows,
            staged_package_rows=[row for row in rows if row["revision_set"] is None],
            package_setup_errors=package_setup_errors,
            can_populate=bool(rows) and not package_setup_errors,
            pricing_summary=pricing_summary,
            pending_review_count=pending_review_count,
            first_pending=first_pending,
            output_files=build_output_files(),
            populate_status=populate_status_payload(project, active_store),
        )

    @app.get("/workspace/populate/status")
    def populate_status():
        project = active_project()
        current = load_project_store(project)
        status = populate_status_payload(project, current)
        status["package_setup_errors"] = validate_staged_packages(current)
        return jsonify(status)

    @app.post("/packages/order")
    def save_package_order():
        current = load_project_store()
        values = {
            package.id: request.form.get(f"revision_number_{package.id}", "")
            for package in reconcile_staged_packages(current, save=False)[0]
        }
        update_revision_numbers(current, values)
        current.save()
        return redirect(url_for("dashboard"))

    @app.post("/packages/import")
    def import_package():
        current = load_project_store()
        source_text = request.form.get("source_path", "").strip()
        package_label = request.form.get("package_label", "").strip()
        revision_number = parse_revision_number(request.form.get("revision_number"))
        if has_uploaded_files("package_files"):
            try:
                destination_name, saved = stage_uploaded_package(
                    "package_files",
                    current,
                    package_label,
                    require_revision_number(request.form.get("revision_number")),
                )
                if not saved:
                    set_package_setup_status(current, error="No PDF files were selected for import.")
                    flash("No PDF files were selected for import.", "warning")
                    return redirect(url_for("dashboard"))
            except Exception as exc:
                set_package_setup_status(current, error=f"Package import failed: {exc}")
                flash(f"Package import failed: {exc}", "warning")
                return redirect(url_for("dashboard"))
            set_package_setup_status(current)
            flash(
                f"Staged package {destination_name} with {len(saved)} PDF file(s). Populate the workspace to generate review data.",
                "success",
            )
            return redirect(url_for("dashboard"))

        if source_text:
            try:
                destination_name, _ = stage_manual_package(source_text, current, package_label, revision_number)
            except PermissionError:
                set_package_setup_status(current, error="Manual server path is outside the allowed import location.")
                flash("Package import failed.", "warning")
                return redirect(url_for("dashboard"))
            except Exception as exc:
                set_package_setup_status(current, error=f"Package import failed: {exc}")
                flash(f"Package import failed: {exc}", "warning")
                return redirect(url_for("dashboard"))
            set_package_setup_status(current)
            flash(
                f"Staged package {destination_name}. Populate the workspace to generate review data.",
                "success",
            )
            return redirect(url_for("dashboard"))

        set_package_setup_status(current, error="Choose PDF files or a folder from your computer.")
        flash(
            "Choose PDF files or a folder from your computer.",
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
            try:
                require_manual_source_allowed(source_path)
            except PermissionError as exc:
                flash(f"File append failed: {exc}", "warning")
                return redirect(url_for("dashboard"))
            if not source_path.exists() or not source_path.is_file():
                flash(f"PDF path does not exist: {source_path}", "warning")
                return redirect(url_for("dashboard"))
            if source_path.suffix.lower() != ".pdf":
                flash(f"Manual append file must be a PDF: {source_path}", "warning")
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

        flash("Choose PDF files from your computer.", "warning")
        return redirect(url_for("dashboard"))

    @app.post("/uploads/chunked/init")
    def init_chunked_upload():
        project = active_project()
        cleanup_stale_chunked_uploads(project)
        current = load_project_store(project)
        payload = request.get_json(silent=True) or {}
        purpose = payload.get("purpose", "")
        if purpose not in {"import_package", "append_file"}:
            return jsonify({"error": "Unsupported upload purpose."}), 400
        if purpose == "append_file":
            revision_set_id = str(payload.get("revision_set_id", "")).strip()
            if not any(item.id == revision_set_id for item in current.data.revision_sets):
                return jsonify({"error": "Choose a target package."}), 400
            revision_number = None
        else:
            revision_set_id = ""
            revision_number = parse_revision_number(payload.get("revision_number"))
            if revision_number is None:
                return jsonify({"error": "Assign a positive revision number before importing a package."}), 400

        raw_files = payload.get("files") or []
        if not raw_files:
            return jsonify({"error": "Choose at least one PDF file."}), 400
        if len(raw_files) > MAX_CHUNKED_UPLOAD_FILES:
            return jsonify({"error": f"Upload is limited to {MAX_CHUNKED_UPLOAD_FILES} PDF files at a time."}), 413

        files = []
        total_size = 0
        for index, file_record in enumerate(raw_files):
            name = str(file_record.get("name", "")).strip()
            relative_path = str(file_record.get("relative_path", "")).strip()
            try:
                safe_relative_path = safe_upload_relative_path(name, relative_path)
                size = int(file_record.get("size", 0))
            except (TypeError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 400
            if size <= 0:
                return jsonify({"error": f"Uploaded PDF is empty: {name or relative_path}"}), 400
            if total_size + size > app.config["SCOPELEDGER_MAX_CHUNKED_UPLOAD_BYTES"]:
                limit_mb = app.config["SCOPELEDGER_MAX_CHUNKED_UPLOAD_BYTES"] // (1024 * 1024)
                return jsonify({"error": f"Selected PDFs exceed the configured {limit_mb} MiB upload limit."}), 413
            chunk_count = (size + CHUNKED_UPLOAD_CHUNK_BYTES - 1) // CHUNKED_UPLOAD_CHUNK_BYTES
            files.append(
                {
                    "index": index,
                    "name": safe_relative_path.name,
                    "relative_path": str(safe_relative_path),
                    "size": size,
                    "chunk_count": chunk_count,
                }
            )
            total_size += size

        upload_id = uuid.uuid4().hex
        upload_dir = chunked_upload_dir(upload_id, project)
        upload_dir.mkdir(parents=True, exist_ok=False)
        metadata = {
            "schema": "scopeledger.chunked_upload.v1",
            "upload_id": upload_id,
            "purpose": purpose,
            "package_label": str(payload.get("package_label", "")).strip(),
            "revision_number": revision_number,
            "revision_set_id": revision_set_id,
            "created_at": utc_timestamp(),
            "files": files,
            "total_size": total_size,
        }
        chunked_metadata_path(upload_id, project).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return jsonify(
            {
                "upload_id": upload_id,
                "chunk_size": CHUNKED_UPLOAD_CHUNK_BYTES,
                "file_count": len(files),
                "total_size": total_size,
            }
        )

    @app.post("/uploads/chunked/chunk")
    def receive_chunked_upload_chunk():
        project = active_project()
        upload_id = request.form.get("upload_id", "")
        try:
            metadata = load_chunked_metadata(upload_id, project)
            upload_dir = chunked_upload_dir(upload_id, project)
            file_index = int(request.form.get("file_index", "-1"))
            chunk_index = int(request.form.get("chunk_index", "-1"))
        except (FileNotFoundError, TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        files = metadata["files"]
        if file_index < 0 or file_index >= len(files):
            return jsonify({"error": "Invalid file index."}), 400
        chunk_count = int(files[file_index]["chunk_count"])
        if chunk_index < 0 or chunk_index >= chunk_count:
            return jsonify({"error": "Invalid chunk index."}), 400
        chunk = request.files.get("chunk")
        if chunk is None:
            return jsonify({"error": "Missing upload chunk."}), 400
        chunk_path = upload_dir / f"file_{file_index}_chunk_{chunk_index}.part"
        chunk.save(chunk_path)
        if chunk_path.stat().st_size > MAX_CHUNKED_UPLOAD_CHUNK_BYTES:
            chunk_path.unlink(missing_ok=True)
            return jsonify({"error": "Upload chunk is too large."}), 413
        return jsonify({"ok": True})

    @app.post("/uploads/chunked/abort")
    def abort_chunked_upload():
        project = active_project()
        payload = request.get_json(silent=True) or request.form
        upload_id = str(payload.get("upload_id", "")).strip()
        try:
            deleted = remove_chunked_upload(upload_id, project)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "deleted": deleted})

    @app.post("/uploads/chunked/complete")
    def complete_chunked_upload():
        project = active_project()
        current = load_project_store(project)
        payload = request.get_json(silent=True) or {}
        upload_id = str(payload.get("upload_id", "")).strip()
        try:
            metadata = load_chunked_metadata(upload_id, project)
            upload_dir = chunked_upload_dir(upload_id, project)
            assembled_paths = assemble_chunked_upload(metadata, upload_dir)
            destination_name, file_count = stage_chunked_uploaded_files(metadata, assembled_paths, current)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400
        remove_chunked_upload(upload_id, project)
        action = "appended to" if metadata["purpose"] == "append_file" else "staged as"
        flash(f"Chunked upload complete: {file_count} PDF file(s) {action} {destination_name}. Populate the workspace to generate review data.", "success")
        return jsonify({"ok": True, "redirect_url": url_for("dashboard")})

    @app.post("/workspace/populate")
    def populate_workspace():
        project = active_project()
        current = load_project_store()
        reconcile_staged_packages(current, save=True)
        package_setup_errors = validate_staged_packages(current)
        rebuild_all = request.form.get("rebuild_all") == "1"
        if package_setup_errors:
            current.update_populate_status(
                state="blocked",
                stage="package_setup",
                message="Package revision numbers need attention before Populate can run.",
                error=" ".join(package_setup_errors),
            )
            return redirect(url_for("dashboard"))
        packages = sorted(current.data.staged_packages, key=staged_package_sort_key)
        runner = app.config["CLOUDHAMMER_RUNNER"]
        plans = plan_package_runs(current, runner, packages, force_rebuild=rebuild_all)
        dirty_count = len([plan for plan in plans if plan.is_dirty])
        previous_visible_ids = {item.id for item in visible_change_items(current.data.change_items)}
        if clean_populate_can_short_circuit(current, dirty_count, rebuild_all):
            for plan in plans:
                record = dict(plan.record)
                record["last_action"] = "reused"
                current.data.package_runs[plan.package.id] = record
            visible_items = visible_change_items(current.data.change_items)
            pending_review_count = len([item for item in visible_items if item.status == "pending"])
            now = utc_timestamp()
            current.update_populate_status(
                state="done",
                stage="complete",
                message=(
                    f"Workspace already up to date: 0 package(s) processed, "
                    f"{len(plans)} package(s) reused, 0 new review item(s), "
                    f"{pending_review_count} pending total."
                ),
                started_at=now,
                finished_at=now,
                total_package_count=len(plans),
                dirty_package_count=0,
                processed_package_count=0,
                reused_package_count=len(plans),
                current_package_label="",
                current_revision_number="",
                new_change_item_count=0,
                pending_review_count=pending_review_count,
                package_count=len(current.data.revision_sets),
                document_count=len(current.data.documents),
                sheet_count=len(current.data.sheets),
                cloud_count=len(current.data.clouds),
                change_item_count=len(visible_items),
                cache_hits=len(current.data.documents),
                error="",
                **keynote_registry_status_from_store(current),
            )
            flash(
                (
                    f"Workspace already up to date: {len(plans)} package(s) reused, "
                    f"{len(visible_items)} change item(s)."
                ),
                "success",
            )
            return redirect(url_for("dashboard"))
        current.update_populate_status(
            state="running",
            stage="package_plan",
            message=(
                "Rebuilding all revision packages."
                if rebuild_all
                else f"Preparing package runs: {dirty_count} package(s) to process, {len(plans) - dirty_count} package(s) to reuse."
            ),
            started_at=utc_timestamp(),
            finished_at="",
            total_package_count=len(plans),
            dirty_package_count=dirty_count,
            processed_package_count=0,
            reused_package_count=0,
            current_package_label="",
            current_revision_number="",
            package_count=len(current.data.revision_sets),
            document_count=0,
            sheet_count=0,
            cloud_count=0,
            change_item_count=0,
            cache_hits=0,
            error="",
        )
        refreshed: WorkspaceStore | None = None
        cloudhammer_result: CloudHammerRunResult | None = None
        pre_review_summary = None
        keynote_registry_summary = None
        keynote_expansion_summary = None
        processed_count = 0
        reused_count = 0
        package_records: list[dict] = []
        active_package_plan = None

        def package_status_fields(plan, index: int | None = None) -> dict[str, object]:
            package = plan.package
            return {
                "total_package_count": len(plans),
                "dirty_package_count": dirty_count,
                "processed_package_count": processed_count,
                "reused_package_count": reused_count,
                "current_package_label": package.label,
                "current_revision_number": package.revision_number or "",
                "current_package_index": index or "",
                "current_package_total": len(plans),
            }

        try:
            for index, plan in enumerate(plans, start=1):
                package = plan.package
                revision_text = package_revision_label(package)
                if not plan.is_dirty:
                    reused_count += 1
                    record = dict(plan.record)
                    record["last_action"] = "reused"
                    current.data.package_runs[package.id] = record
                    package_records.append(record)
                    current.update_populate_status(
                        state="running",
                        stage="package_reuse",
                        message=f"Reusing {revision_text} ({index} of {len(plans)}): {package.label}.",
                        **package_status_fields(plan, index),
                    )
                    continue

                current.update_populate_status(
                    state="running",
                    stage="drawing_analysis",
                    message=f"Processing {revision_text} ({index} of {len(plans)}): {package.label}.",
                    **package_status_fields(plan, index),
                )
                active_package_plan = plan
                cloudhammer_result = runner.run(
                    input_dir=Path(package.source_dir),
                    workspace_dir=Path(project.workspace_dir),
                )
                processed_count += 1
                record = build_package_run_record(
                    package,
                    cloudhammer_result,
                    pdf_fingerprints=plan.pdf_fingerprints,
                    pipeline_fingerprint=plan.pipeline_fingerprint,
                )
                record["last_action"] = "processed"
                current.data.package_runs[package.id] = record
                current.save()
                active_package_plan = None
                package_records.append(record)
                current.update_populate_status(
                    state="running",
                    stage="package_complete",
                    message=f"Processed {revision_text}: {cloudhammer_result.candidate_count} detected region(s).",
                    **package_status_fields(plan, index),
                    **cloudhammer_result.to_status(),
                )

            cloudhammer_result, pdf_cache_keys = assemble_cloudhammer_package_runs(
                Path(project.workspace_dir),
                package_records,
            )
            current.update_populate_status(
                state="running",
                stage="scan",
                message=(
                    f"Assembling workspace from {processed_count} processed package(s) "
                    f"and {reused_count} reused package(s)."
                ),
                processed_package_count=processed_count,
                reused_package_count=reused_count,
                total_package_count=len(plans),
                dirty_package_count=dirty_count,
                current_package_label="",
                current_revision_number="",
                **cloudhammer_result.to_status(),
            )
            cloud_client = ManifestCloudInferenceClient(
                cloudhammer_result.candidate_manifest,
                pdf_cache_keys=pdf_cache_keys,
                rows=cloudhammer_result.candidate_rows,
            )
            refreshed, cache_hits = rescan_active_project(cloud_inference_client=cloud_client)
            refreshed.update_populate_status(
                state="running",
                stage="scope_extraction",
                message="Extracting scope text and review reasons from cloud regions.",
                processed_package_count=processed_count,
                reused_package_count=reused_count,
                total_package_count=len(plans),
                dirty_package_count=dirty_count,
                current_package_label="",
                current_revision_number="",
                package_count=len(refreshed.data.revision_sets),
                document_count=len(refreshed.data.documents),
                sheet_count=len(refreshed.data.sheets),
                cloud_count=len(refreshed.data.clouds),
                change_item_count=len(visible_change_items(refreshed.data.change_items)),
                cache_hits=cache_hits,
                **(keynote_registry_summary.to_status() if keynote_registry_summary else {}),
                **(cloudhammer_result.to_status() if cloudhammer_result else {}),
            )
            enrich_workspace_scope_text(refreshed)
            refreshed.update_populate_status(
                state="running",
                stage="keynote_registry",
                message="Building same-sheet keynote registry.",
                processed_package_count=processed_count,
                reused_package_count=reused_count,
                total_package_count=len(plans),
                dirty_package_count=dirty_count,
                current_package_label="",
                current_revision_number="",
                package_count=len(refreshed.data.revision_sets),
                document_count=len(refreshed.data.documents),
                sheet_count=len(refreshed.data.sheets),
                cloud_count=len(refreshed.data.clouds),
                change_item_count=len(visible_change_items(refreshed.data.change_items)),
                cache_hits=cache_hits,
                **(cloudhammer_result.to_status() if cloudhammer_result else {}),
            )
            keynote_registry_summary = build_workspace_keynote_registry(refreshed)
            refreshed.update_populate_status(
                state="running",
                stage="legend_context",
                message="Resolving legend context for detected regions.",
                processed_package_count=processed_count,
                reused_package_count=reused_count,
                total_package_count=len(plans),
                dirty_package_count=dirty_count,
                current_package_label="",
                current_revision_number="",
                package_count=len(refreshed.data.revision_sets),
                document_count=len(refreshed.data.documents),
                sheet_count=len(refreshed.data.sheets),
                cloud_count=len(refreshed.data.clouds),
                change_item_count=len(visible_change_items(refreshed.data.change_items)),
                cache_hits=cache_hits,
                **keynote_registry_summary.to_status(),
                **(cloudhammer_result.to_status() if cloudhammer_result else {}),
            )
            enrich_workspace_legend_context(refreshed)
            refreshed.update_populate_status(
                state="running",
                stage="pre_review",
                message="Running pre-review on detected regions.",
                processed_package_count=processed_count,
                reused_package_count=reused_count,
                total_package_count=len(plans),
                dirty_package_count=dirty_count,
                current_package_label="",
                current_revision_number="",
                package_count=len(refreshed.data.revision_sets),
                document_count=len(refreshed.data.documents),
                sheet_count=len(refreshed.data.sheets),
                cloud_count=len(refreshed.data.clouds),
                change_item_count=len(visible_change_items(refreshed.data.change_items)),
                cache_hits=cache_hits,
                **(cloudhammer_result.to_status() if cloudhammer_result else {}),
            )

            last_pre_review_status_write = {"time": 0.0, "completed": -1}

            def update_pre_review_progress(summary) -> None:
                completed = summary.pre_review_2_count + summary.failed_count + summary.skipped_count
                now = time.monotonic()
                is_finished = summary.total_count == 0 or completed >= summary.total_count
                if not is_finished and completed == last_pre_review_status_write["completed"]:
                    return
                if not is_finished and now - last_pre_review_status_write["time"] < 2.0:
                    return
                last_pre_review_status_write["time"] = now
                last_pre_review_status_write["completed"] = completed
                refreshed.update_populate_status(
                    state="running",
                    stage="pre_review",
                    message="Running pre-review on detected regions.",
                    processed_package_count=processed_count,
                    reused_package_count=reused_count,
                    total_package_count=len(plans),
                    dirty_package_count=dirty_count,
                    current_package_label="",
                    current_revision_number="",
                    package_count=len(refreshed.data.revision_sets),
                    document_count=len(refreshed.data.documents),
                    sheet_count=len(refreshed.data.sheets),
                    cloud_count=len(refreshed.data.clouds),
                    change_item_count=len(visible_change_items(refreshed.data.change_items)),
                    cache_hits=cache_hits,
                    **(keynote_registry_summary.to_status() if keynote_registry_summary else {}),
                    **summary.to_status(),
                    **(cloudhammer_result.to_status() if cloudhammer_result else {}),
                )

            pre_review_summary = ensure_workspace_pre_review(
                refreshed,
                app.config["PRE_REVIEW_PROVIDER"],
                progress_callback=update_pre_review_progress,
            )
            keynote_expansion_summary = apply_pre_review_keynote_expansions(refreshed)
            visible_items = visible_change_items(refreshed.data.change_items)
            new_change_item_count = len([item for item in visible_items if item.id not in previous_visible_ids])
            pending_review_count = len([item for item in visible_items if item.status == "pending"])
            refreshed.update_populate_status(
                state="done",
                stage="complete",
                message=(
                    f"Workspace populated: {processed_count} package(s) processed, "
                    f"{reused_count} package(s) reused, {new_change_item_count} new review item(s), "
                    f"{pending_review_count} pending total."
                ),
                finished_at=utc_timestamp(),
                processed_package_count=processed_count,
                reused_package_count=reused_count,
                total_package_count=len(plans),
                dirty_package_count=dirty_count,
                current_package_label="",
                current_revision_number="",
                new_change_item_count=new_change_item_count,
                pending_review_count=pending_review_count,
                package_count=len(refreshed.data.revision_sets),
                document_count=len(refreshed.data.documents),
                sheet_count=len(refreshed.data.sheets),
                cloud_count=len(refreshed.data.clouds),
                change_item_count=len(visible_items),
                cache_hits=cache_hits,
                error="",
                **(keynote_registry_summary.to_status() if keynote_registry_summary else {}),
                **(keynote_expansion_summary.to_status() if keynote_expansion_summary else {}),
                **pre_review_summary.to_status(),
                **(cloudhammer_result.to_status() if cloudhammer_result else {}),
            )
            g.active_store = refreshed
        except Exception as exc:
            failed_store = refreshed or current
            if active_package_plan is not None:
                failed_record = build_failed_package_run_record(
                    active_package_plan.package,
                    pdf_fingerprints=active_package_plan.pdf_fingerprints,
                    pipeline_fingerprint=active_package_plan.pipeline_fingerprint,
                    dirty_reason=active_package_plan.dirty_reason,
                    error=str(exc),
                )
                failed_store.data.package_runs[active_package_plan.package.id] = failed_record
            failed_store.update_populate_status(
                state="failed",
                stage="failed",
                message="Workspace population failed.",
                finished_at=utc_timestamp(),
                processed_package_count=processed_count,
                reused_package_count=reused_count,
                total_package_count=len(plans),
                dirty_package_count=dirty_count,
                error=str(exc),
                **(pre_review_summary.to_status() if pre_review_summary else {}),
                **(keynote_registry_summary.to_status() if keynote_registry_summary else {}),
                **(keynote_expansion_summary.to_status() if keynote_expansion_summary else {}),
                **(cloudhammer_result.to_status() if cloudhammer_result else {}),
            )
            flash(f"Workspace population failed: {exc}", "warning")
            return redirect(url_for("dashboard"))
        flash(
            (
                f"Workspace populated: {processed_count} package(s) processed, {reused_count} reused, "
                f"{len(refreshed.data.sheets)} sheet version(s), "
                f"{len(visible_change_items(refreshed.data.change_items))} change item(s)."
            ),
            "success",
        )
        if pre_review_summary and (
            pre_review_summary.failed_count
            or pre_review_summary.disabled_reason not in {"", "disabled"}
        ):
            flash("Pre-review enrichment was skipped or incomplete; detected regions are still available for review.", "warning")
        return redirect(url_for("dashboard"))

    @app.route("/conformed")
    def conformed():
        if active_project_or_none() is None:
            return render_template(
                "conformed.html",
                groups=[],
                show_filter=request.args.get("show", "revised"),
                search_query=request.args.get("q", ""),
                sheet_id_count=0,
                revised_count=0,
                index_page_count=0,
            )
        revision_sets_by_id = {revision_set.id: revision_set for revision_set in store.data.revision_sets}
        groups: dict[str, list] = {}
        for sheet in store.data.sheets:
            groups.setdefault(sheet.sheet_id, []).append(sheet)

        show_filter = request.args.get("show", "revised")
        search_query = request.args.get("q", "")
        rendered_groups = []
        index_page_count = 0
        revised_sheet_count = 0
        for sheet_id, versions in groups.items():
            index_page_count += len([sheet for sheet in versions if sheet_is_index_like(sheet)])
            real_versions = [sheet for sheet in versions if not sheet_is_index_like(sheet)]
            candidate_versions = real_versions or versions
            ranked = sorted(
                candidate_versions,
                key=lambda item: (
                    -revision_sets_by_id[item.revision_set_id].set_number,
                    item.status != "active",
                    item.page_number,
                ),
            )
            latest = ranked[0]
            latest_revision_number = revision_sets_by_id[latest.revision_set_id].set_number
            superseded = [
                version
                for version in ranked[1:]
                if revision_sets_by_id[version.revision_set_id].set_number < latest_revision_number
            ]
            if superseded:
                revised_sheet_count += 1
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
        return render_template(
            "conformed.html",
            groups=rendered_groups,
            show_filter=show_filter,
            search_query=search_query,
            sheet_id_count=len(groups),
            revised_count=revised_sheet_count,
            index_page_count=index_page_count,
        )

    @app.route("/sheets")
    def sheets():
        filter_status = request.args.get("status", "all")
        search_query = request.args.get("q", "")
        include_index_matches = request.args.get("include_index", "0") == "1"
        if active_project_or_none() is None:
            return render_template(
                "sheets.html",
                sheets=[],
                filter_status=filter_status,
                search_query=search_query,
                changes_by_sheet={},
                active_sheet_count=0,
                superseded_sheet_count=0,
                include_index_matches=include_index_matches,
                index_match_count=0,
            )
        revision_sets_by_id = {revision_set.id: revision_set for revision_set in store.data.revision_sets}
        rendered_sheets = [
            replace(sheet, status=sheet_status_for_drawings(sheet, store.data.sheets, revision_sets_by_id))
            for sheet in store.data.sheets
        ]
        countable_sheets = [sheet for sheet in rendered_sheets if not sheet_is_index_like(sheet)]
        active_sheet_count = len([sheet for sheet in countable_sheets if sheet.status == "active"])
        superseded_sheet_count = len([sheet for sheet in countable_sheets if sheet.status == "superseded"])
        index_match_count = len([sheet for sheet in store.data.sheets if sheet_is_index_like(sheet)])
        all_sheets = rendered_sheets
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
        for item in visible_change_items(store.data.change_items):
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
        changes = visible_change_items(store.sheet_changes(sheet.id))
        clouds_by_id = {cloud.id: cloud for cloud in store.data.clouds}
        review_overlays = []
        for item in changes:
            cloud = clouds_by_id.get(item.cloud_candidate_id or "")
            if not cloud:
                continue
            boxes = selected_review_page_boxes(item, cloud)
            status_class = {"approved": "accepted", "rejected": "rejected", "pending": "pending"}.get(item.status, "pending")
            for box_index, box in enumerate(boxes, start=1):
                if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
                    continue
                label = item.detail_ref or ("Cloud" if len(boxes) == 1 else f"Cloud {box_index}")
                review_overlays.append(
                    {
                        "item": item,
                        "box": box,
                        "label": label,
                        "status_class": status_class,
                    }
                )
        narratives = [entry for entry in store.data.narrative_entries if entry.id in sheet.narrative_entry_ids]
        return render_template(
            "sheet_detail.html",
            sheet=sheet,
            chain=chain,
            changes=changes,
            narratives=narratives,
            review_overlays=review_overlays,
        )

    @app.route("/changes")
    def changes():
        filter_status = request.args.get("status", "pending")
        search_query = request.args.get("q", "")
        attention_only = request.args.get("attention", "0") == "1"
        package_scope = request.args.get("package_scope", "all")
        package_id = request.args.get("package_id", "")
        if active_project_or_none() is None:
            return render_template(
                "changes.html",
                items=[],
                filter_status=filter_status,
                search_query=search_query,
                attention_only=attention_only,
                counts=empty_counts(),
                first_pending=None,
                review_filter={
                    "package_scope": "all",
                    "package_id": "",
                    "query_args": {"package_scope": "all"},
                    "options": [],
                    "selected_package": None,
                    "newest_package": None,
                    "newest_pending_count": 0,
                    "all_pending_count": 0,
                },
                item_package_context={"packages_by_id": {}, "item_package_ids": {}},
            )
        review_filter = review_package_filter_context(store, package_scope, package_id)
        items = filter_change_items(
            store,
            filter_status,
            search_query,
            str(review_filter["package_scope"]),
            str(review_filter["package_id"]),
        )
        if attention_only:
            items = [item for item in items if item.status == "pending" and change_item_needs_attention(item)]
        counts = visible_review_counts(store)
        first_pending = next(
            (
                item
                for item in filter_change_items(
                    store,
                    "pending",
                    "",
                    str(review_filter["package_scope"]),
                    str(review_filter["package_id"]),
                )
            ),
            None,
        )
        return render_template(
            "changes.html",
            items=items,
            filter_status=filter_status,
            search_query=search_query,
            attention_only=attention_only,
            counts=counts,
            first_pending=first_pending,
            review_filter=review_filter,
            item_package_context=package_context(store),
        )

    @app.route("/changes/<change_id>")
    def change_detail(change_id: str):
        try:
            item = store.get_change_item(change_id)
        except KeyError:
            abort(404)
        queue_status = request.args.get("queue", "pending")
        search_query = request.args.get("q", "")
        attention_only = request.args.get("attention", "0") == "1"
        package_scope = request.args.get("package_scope", "all")
        package_id = request.args.get("package_id", "")
        review_filter = review_package_filter_context(store, package_scope, package_id)
        if is_superseded(item):
            return redirect(
                replacement_redirect_target(
                    item,
                    queue_status=queue_status,
                    search_query=search_query,
                    attention_only=attention_only,
                    package_scope=str(review_filter["package_scope"]),
                    package_id=str(review_filter["package_id"]),
                )
            )
        sheet = store.get_sheet(item.sheet_version_id)
        cloud = store.get_cloud(item.cloud_candidate_id) if item.cloud_candidate_id else None
        verifications = store.change_verifications(change_id)
        queue_items = filter_change_items(
            store,
            queue_status,
            search_query,
            str(review_filter["package_scope"]),
            str(review_filter["package_id"]),
        )
        if attention_only:
            queue_items = [queued_item for queued_item in queue_items if queued_item.status == "pending" and change_item_needs_attention(queued_item)]
        navigation = build_change_navigation(queue_items, change_id)
        return render_template(
            "change_detail.html",
            item=item,
            sheet=sheet,
            cloud=cloud,
            crop_adjustment=crop_adjustment_template_context(store, item, cloud, sheet),
            pre_review=pre_review_payload(item),
            legend_context=legend_context_payload(item),
            resolved_legend_context=legend_context_text(item),
            verifications=verifications,
            provider_name=provider.name,
            queue_status=queue_status,
            search_query=search_query,
            attention_only=attention_only,
            review_filter=review_filter,
            navigation=navigation,
            item_needs_attention=item.status == "pending" and change_item_needs_attention(item),
            sheet_revision_set=next((revision_set for revision_set in store.data.revision_sets if revision_set.id == sheet.revision_set_id), None),
        )

    @app.post("/changes/<change_id>/crop-adjustment")
    def update_crop_adjustment(change_id: str):
        try:
            item = store.get_change_item(change_id)
        except KeyError:
            abort(404)
        if is_superseded(item):
            return jsonify({"error": "This review item has already been corrected."}), 400
        if not item.cloud_candidate_id:
            return jsonify({"error": "This review item does not have an adjustable crop."}), 400
        project = active_project()
        sheet = store.get_sheet(item.sheet_version_id)
        cloud = store.get_cloud(item.cloud_candidate_id)
        payload = request.get_json(silent=True) or {}
        try:
            result = apply_crop_adjustment(
                store,
                item,
                cloud,
                sheet,
                payload.get("crop_box", []),
                reviewer_id=current_reviewer_id(),
                review_session_id=current_review_session_id(),
            )
            record_review_update(
                store,
                project_id=project.id,
                change_id=change_id,
                changes={"provenance": result.item.provenance},
                reviewer_id=current_reviewer_id(),
                review_session_id=current_review_session_id(),
                action="resize",
                human_result_overrides=result.human_result_overrides,
            )
        except CropAdjustmentError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(
            {
                "image_url": url_for("pre_review_overlay_asset", change_id=change_id),
                "crop_box": result.crop_box,
                "page_box": result.page_box,
            }
        )

    @app.post("/changes/<change_id>/geometry-correction")
    def update_geometry_correction(change_id: str):
        try:
            item = store.get_change_item(change_id)
        except KeyError:
            abort(404)
        if is_superseded(item):
            return jsonify({"error": "This review item has already been corrected."}), 400
        if not item.cloud_candidate_id:
            return jsonify({"error": "This review item does not have a correctable crop."}), 400
        project = active_project()
        sheet = store.get_sheet(item.sheet_version_id)
        cloud = store.get_cloud(item.cloud_candidate_id)
        payload = request.get_json(silent=True) or {}
        try:
            result = apply_geometry_correction(
                store,
                item,
                cloud,
                sheet,
                mode=str(payload.get("mode") or ""),
                crop_boxes=payload.get("crop_boxes", []),
                project_id=project.id,
                reviewer_id=current_reviewer_id(),
                review_session_id=current_review_session_id(),
                starter_text_override=str(payload.get("reviewer_text") or ""),
            )
        except GeometryCorrectionError as exc:
            return jsonify({"error": str(exc)}), 400
        redirect_kwargs = {
            "change_id": result.child_items[0].id,
            "queue": str(payload.get("queue_status") or "pending"),
            "q": str(payload.get("search_query") or ""),
        }
        package_scope = str(payload.get("package_scope") or "all")
        package_id = str(payload.get("package_id") or "")
        if package_scope in {"newest", "package"}:
            redirect_kwargs["package_scope"] = package_scope
        if package_scope == "package" and package_id:
            redirect_kwargs["package_id"] = package_id
        if str(payload.get("attention_only") or "0") == "1":
            redirect_kwargs["attention"] = "1"
        return jsonify(
            {
                "ok": True,
                "replacement_change_ids": [child.id for child in result.child_items],
                "redirect_url": url_for("change_detail", **redirect_kwargs),
            }
        )

    @app.post("/changes/<change_id>/accept-legend")
    def accept_legend_context(change_id: str):
        try:
            item = store.get_change_item(change_id)
        except KeyError:
            abort(404)
        queue_status = request.form.get("queue_status", "pending")
        search_query = request.form.get("search_query", "")
        attention_only = request.form.get("attention_only", "0") == "1"
        package_scope = request.form.get("package_scope", "all")
        package_id = request.form.get("package_id", "")
        if is_superseded(item):
            return redirect(
                replacement_redirect_target(
                    item,
                    queue_status=queue_status,
                    search_query=search_query,
                    attention_only=attention_only,
                    package_scope=package_scope,
                    package_id=package_id,
                )
            )
        if not is_probable_legend_context(item):
            flash("This item is not marked as probable legend context.", "warning")
            redirect_kwargs = {
                "change_id": change_id,
                **review_url_kwargs(
                    queue_status=queue_status,
                    search_query=search_query,
                    attention_only=attention_only,
                    package_scope=package_scope,
                    package_id=package_id,
                ),
            }
            return redirect(url_for("change_detail", **redirect_kwargs))

        project = active_project()
        confirmed_at = utc_timestamp()
        reviewer_id = current_reviewer_id()
        review_session_id = current_review_session_id()
        updated = confirm_legend_context_item(
            item,
            reviewer_id=reviewer_id,
            review_session_id=review_session_id,
            confirmed_at=confirmed_at,
        )
        record_review_update(
            store,
            project_id=project.id,
            change_id=change_id,
            changes={
                "provenance": updated.provenance,
                "superseded_reason": updated.superseded_reason,
                "superseded_at": updated.superseded_at,
            },
            reviewer_id=reviewer_id,
            review_session_id=review_session_id,
            action="relabel",
            human_result_overrides=legend_context_human_result(updated),
        )
        next_change_id = next_pending_change_id_after(
            change_id,
            search_query=search_query,
            attention_only=attention_only,
            package_scope=package_scope,
            package_id=package_id,
        )
        if next_change_id:
            redirect_kwargs = {
                "change_id": next_change_id,
                **review_url_kwargs(
                    queue_status="pending",
                    search_query=search_query,
                    attention_only=attention_only,
                    package_scope=package_scope,
                    package_id=package_id,
                ),
            }
            return redirect(url_for("change_detail", **redirect_kwargs))
        redirect_kwargs = review_url_kwargs(
            queue_status="",
            search_query=search_query,
            attention_only=attention_only,
            package_scope=package_scope,
            package_id=package_id,
        )
        redirect_kwargs["status"] = "pending"
        return redirect(url_for("changes", **redirect_kwargs))

    @app.post("/changes/<change_id>/review")
    def review_change(change_id: str):
        try:
            item = store.get_change_item(change_id)
        except KeyError:
            abort(404)
        project = active_project()
        if is_superseded(item):
            queue_status = request.form.get("queue_status", "pending")
            search_query = request.form.get("search_query", "")
            attention_only = request.form.get("attention_only", "0") == "1"
            package_scope = request.form.get("package_scope", "all")
            package_id = request.form.get("package_id", "")
            return redirect(
                replacement_redirect_target(
                    item,
                    queue_status=queue_status,
                    search_query=search_query,
                    attention_only=attention_only,
                    package_scope=package_scope,
                    package_id=package_id,
                )
            )
        status = request.form.get("status_override") or request.form.get("status", item.status)
        default_redirect = url_for("change_detail", change_id=change_id)
        if status not in VALID_REVIEW_STATUSES:
            flash("Choose a valid review status.", "warning")
            return redirect(safe_redirect_target(request.form.get("redirect_to"), default_redirect))
        queue_status = request.form.get("queue_status", "pending")
        search_query = request.form.get("search_query", "")
        attention_param = request.form.get("attention_only", "0")
        attention_only = attention_param == "1"
        package_scope = request.form.get("package_scope", "all")
        package_id = request.form.get("package_id", "")
        advance_to_next = request.form.get("advance") == "next"
        server_next_change_id = (
            next_change_id_after_in_queue(
                change_id,
                queue_status=queue_status,
                search_query=search_query,
                attention_only=attention_only,
                package_scope=package_scope,
                package_id=package_id,
            )
            if advance_to_next
            else None
        )
        selected_pre_review = request.form.get("selected_pre_review", "")
        if selected_pre_review:
            item = select_pre_review_source(item, selected_pre_review)
        reviewer_text = request.form.get("reviewer_text", item.reviewer_text or item.raw_text)
        if selected_pre_review:
            reviewer_text = item.reviewer_text or reviewer_text
        reviewer_notes = request.form.get("reviewer_notes", item.reviewer_notes)
        record_review_update(
            store,
            project_id=project.id,
            change_id=change_id,
            changes={
                "status": status,
                "reviewer_text": reviewer_text,
                "reviewer_notes": reviewer_notes,
                "provenance": item.provenance,
            },
            reviewer_id=current_reviewer_id(),
            review_session_id=current_review_session_id(),
        )
        flash(f"Updated {change_id} to {status}.", "success")
        if advance_to_next and server_next_change_id:
            redirect_kwargs = {
                "change_id": server_next_change_id,
                "queue": queue_status,
                "q": search_query,
            }
            if package_scope in {"newest", "package"}:
                redirect_kwargs["package_scope"] = package_scope
            if package_scope == "package" and package_id:
                redirect_kwargs["package_id"] = package_id
            if attention_param == "1":
                redirect_kwargs["attention"] = "1"
            redirect_to = url_for(
                "change_detail",
                **redirect_kwargs,
            )
        else:
            if advance_to_next:
                redirect_kwargs = review_url_kwargs(
                    queue_status="",
                    search_query=search_query,
                    attention_only=attention_only,
                    package_scope=package_scope,
                    package_id=package_id,
                )
                redirect_kwargs["status"] = queue_status
                redirect_to = url_for("changes", **redirect_kwargs)
            elif request.form.get("redirect_to"):
                redirect_to = safe_redirect_target(request.form.get("redirect_to"), default_redirect)
            else:
                redirect_kwargs = {
                    "change_id": change_id,
                    "queue": queue_status,
                    "q": search_query,
                }
                if package_scope in {"newest", "package"}:
                    redirect_kwargs["package_scope"] = package_scope
                if package_scope == "package" and package_id:
                    redirect_kwargs["package_id"] = package_id
                if attention_param == "1":
                    redirect_kwargs["attention"] = "1"
                redirect_to = url_for("change_detail", **redirect_kwargs)
        return redirect(redirect_to)

    @app.get("/changes/bulk-review/status")
    def bulk_review_status():
        project = active_project()
        job_id = request.args.get("job_id", "").strip() or None
        payload = bulk_review_manager.status_payload(project.id, job_id)
        if payload is None:
            return jsonify({"error": "Bulk review job was not found.", "state": "unknown"}), 404
        return jsonify(payload)

    @app.post("/changes/bulk-review")
    def bulk_review():
        project = active_project()
        selected_ids = request.form.getlist("change_ids")
        redirect_to = safe_redirect_target(request.form.get("redirect_to"), url_for("changes"))
        wants_json = request.is_json or "application/json" in request.headers.get("Accept", "")
        if not selected_ids:
            if wants_json:
                return jsonify({"error": "No queue items were selected."}), 400
            flash("No queue items were selected.", "warning")
            return redirect(redirect_to)
        status = request.form.get("status")
        if status not in VALID_REVIEW_STATUSES:
            if wants_json:
                return jsonify({"error": "Choose a valid bulk action."}), 400
            flash("Choose a valid bulk action.", "warning")
            return redirect(redirect_to)
        try:
            job = bulk_review_manager.start_job(
                project_id=project.id,
                workspace_dir=project.workspace_dir,
                selected_change_ids=selected_ids,
                requested_status=status,
                reviewer_id=current_reviewer_id(),
                review_session_id=current_review_session_id(),
            )
        except BulkReviewJobConflict:
            active_job = bulk_review_manager.active_job(project.id)
            if wants_json:
                payload = active_job.to_dict() if active_job else {"state": "unknown"}
                return jsonify({"error": "A bulk review update is already running.", "job": payload}), 409
            return redirect(redirect_to)

        if wants_json:
            return (
                jsonify(
                    {
                        "job_id": job.id,
                        "state": job.state,
                        "status_url": url_for("bulk_review_status", job_id=job.id),
                    }
                ),
                202,
            )
        return redirect(redirect_to)

    @app.post("/changes/<change_id>/verify")
    def verify_change(change_id: str):
        try:
            store.get_change_item(change_id)
        except KeyError:
            abort(404)
        return jsonify({"error": "Review assist is currently disabled for this item."}), 400

    @app.post("/changes/<change_id>/apply-verification/<verification_id>")
    def apply_verification(change_id: str, verification_id: str):
        abort(404)

    @app.route("/export")
    def export_view():
        if active_project_or_none() is None:
            return render_template(
                "export.html",
                export_history=[],
                attention_pending_count=0,
                output_files=empty_output_files(),
                pricing_summary=empty_pricing_summary(),
            )
        export_history = list(reversed(store.data.exports))
        attention_pending_count = len(
            [item for item in visible_change_items(store.data.change_items) if item.status == "pending" and change_item_needs_attention(item)]
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
        if active_project_or_none() is None:
            return render_template("settings.html", provider=provider, pre_review_provider=pre_review_provider, verification_history=[])
        verification_history = list(reversed(store.data.verifications))
        return render_template("settings.html", provider=provider, pre_review_provider=pre_review_provider, verification_history=verification_history)

    @app.route("/diagnostics")
    def diagnostics():
        filter_severity = request.args.get("severity", "all")
        if active_project_or_none() is None:
            return render_template(
                "diagnostics.html",
                documents=[],
                issues=[],
                issue_summary=[],
                filter_severity=filter_severity,
            )
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

    @app.route("/workspace-assets/pre-review/<change_id>.png")
    def pre_review_overlay_asset(change_id: str):
        try:
            item = store.get_change_item(change_id)
        except KeyError:
            abort(404)
        overlay_path = ensure_pre_review_overlay(item)
        return send_from_directory(overlay_path.parent.resolve(), overlay_path.name)

    @app.route("/project-assets/<path:asset_path>")
    def project_asset(asset_path: str):
        target = (project_root / asset_path).resolve()
        if not is_safe_project_asset(target):
            abort(404)
        return send_from_directory(project_root, target.relative_to(project_root).as_posix())

    @app.route("/outputs/<path:asset_path>")
    def output_asset(asset_path: str):
        return send_from_directory(store.output_dir.resolve(), asset_path)

    return app
