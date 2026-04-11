from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_from_directory, url_for

from .diagnostics import build_diagnostic_summary, configure_mupdf, format_pdf_label
from .exporter import ExportBlockedError, Exporter
from .review import change_item_needs_attention
from .verification import OpenAIVerificationProvider, build_context_bundle, create_verification_record
from .workspace import WorkspaceStore


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


def create_app(workspace_dir: Path, verification_provider=None) -> Flask:
    configure_mupdf()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.getenv("REVISION_TOOL_SECRET", "revision-tool-dev")
    store = WorkspaceStore(Path(workspace_dir)).load()
    provider = verification_provider or OpenAIVerificationProvider()
    diagnostic_summary = build_diagnostic_summary(store.data.documents, store.data.preflight_issues)
    app.config["STORE"] = store
    app.config["VERIFICATION_PROVIDER"] = provider

    @app.context_processor
    def inject_globals() -> dict[str, object]:
        change_items = store.data.change_items
        return {
            "pending_count": len([item for item in change_items if item.status == "pending"]),
            "approved_count": len([item for item in change_items if item.status == "approved"]),
            "rejected_count": len([item for item in change_items if item.status == "rejected"]),
            "attention_count": len([item for item in change_items if change_item_needs_attention(item)]),
            "ai_enabled": provider.enabled,
            "diagnostic_summary": diagnostic_summary,
            "needs_attention": change_item_needs_attention,
        }

    @app.template_filter("asset_path")
    def asset_path_filter(path: str) -> str:
        if not path:
            return ""
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(store.assets_dir.resolve()).as_posix()
        except ValueError:
            parts = list(resolved.parts)
            if "assets" in parts:
                relative = Path(*parts[parts.index("assets") + 1 :]).as_posix()
            else:
                relative = resolved.name
        return url_for("workspace_asset", asset_path=relative)

    @app.template_filter("pdf_label")
    def pdf_label_filter(path: str) -> str:
        return format_pdf_label(path, Path(store.data.input_dir))

    @app.route("/")
    def dashboard():
        rows = []
        for revision_set in store.data.revision_sets:
            set_sheets = [sheet for sheet in store.data.sheets if sheet.revision_set_id == revision_set.id]
            rows.append(
                {
                    "revision_set": revision_set,
                    "sheet_count": len(set_sheets),
                    "active_count": len([sheet for sheet in set_sheets if sheet.status == "active"]),
                    "superseded_count": len([sheet for sheet in set_sheets if sheet.status == "superseded"]),
                    "narrative_count": len([entry for entry in store.data.narrative_entries if entry.revision_set_id == revision_set.id]),
                }
            )
        recent_changes = store.data.change_items[:10]
        attention_items = [item for item in store.data.change_items if change_item_needs_attention(item)][:10]
        noisy_documents = sorted(
            [document for document in store.data.documents if document.issue_count],
            key=lambda item: (item.max_severity != "high", item.max_severity != "medium", -item.warning_count, item.source_pdf),
        )[:10]
        return render_template(
            "dashboard.html",
            revision_rows=rows,
            recent_changes=recent_changes,
            attention_items=attention_items,
            noisy_documents=noisy_documents,
        )

    @app.route("/sheets")
    def sheets():
        filter_status = request.args.get("status", "all")
        all_sheets = store.data.sheets
        if filter_status != "all":
            all_sheets = [sheet for sheet in all_sheets if sheet.status == filter_status]
        return render_template("sheets.html", sheets=all_sheets, filter_status=filter_status)

    @app.route("/sheets/<sheet_version_id>")
    def sheet_detail(sheet_version_id: str):
        try:
            sheet = store.get_sheet(sheet_version_id)
        except KeyError:
            abort(404)
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
            items = [item for item in items if change_item_needs_attention(item)]
        return render_template(
            "changes.html",
            items=items,
            filter_status=filter_status,
            search_query=search_query,
            attention_only=attention_only,
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
            queue_items = [queued_item for queued_item in queue_items if change_item_needs_attention(queued_item)]
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
            item_needs_attention=change_item_needs_attention(item),
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
            item = store.get_change_item(change_id)
        except KeyError:
            abort(404)
        if not provider.enabled:
            return jsonify({"error": "Verification is disabled. Set OPENAI_API_KEY to enable it."}), 400
        context_bundle = build_context_bundle(store, item)
        try:
            response = provider.verify_change(change_id, context_bundle)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 400

        record = create_verification_record(
            change_item_id=change_id,
            provider=provider.name,
            request_payload=response.pop("request_payload", context_bundle),
            response_payload=response,
        )
        store.data.verifications.append(record)
        store.save()
        return jsonify({"verification": response, "record_id": record.id})

    @app.post("/changes/<change_id>/apply-verification/<verification_id>")
    def apply_verification(change_id: str, verification_id: str):
        try:
            record = next(record for record in store.data.verifications if record.id == verification_id and record.change_item_id == change_id)
        except StopIteration:
            abort(404)
        corrected_text = record.response_payload.get("corrected_text") or ""
        status = "approved" if corrected_text else "pending"
        store.update_change_item(change_id, reviewer_text=corrected_text or store.get_change_item(change_id).raw_text, status=status)
        store.update_verification(verification_id, disposition="accepted")
        flash(f"Applied verification {verification_id}.", "success")
        return redirect(url_for("change_detail", change_id=change_id))

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
        documents = sorted(
            store.data.documents,
            key=lambda item: (item.max_severity != "high", item.max_severity != "medium", -item.warning_count, item.source_pdf),
        )
        return render_template(
            "diagnostics.html",
            documents=documents,
            issues=issues,
            filter_severity=filter_severity,
        )

    @app.route("/workspace-assets/<path:asset_path>")
    def workspace_asset(asset_path: str):
        return send_from_directory(store.assets_dir, asset_path)

    return app
