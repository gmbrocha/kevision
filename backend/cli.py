from __future__ import annotations

import argparse
from pathlib import Path

from .cloudhammer_client.inference import ManifestCloudInferenceClient
from .deliverables.excel_exporter import ExportBlockedError, Exporter
from .deliverables.review_packet import build_review_packet
from .projects import ProjectRegistry, default_app_data_dir
from .review_queue import is_superseded
from .review_events import export_review_events_jsonl
from .revision_state.tracker import RevisionScanner
from .workspace import WorkspaceStore
from webapp.app import create_app

FILTER_REASON_LABELS = {
    "placeholder-no-readable-scope": "clouded regions with no readable text",
    "sheet-index-page": "sheet-index pages (not real changes)",
    "locator-only-text": "locator-only labels (e.g. room names, callouts)",
    "empty-text": "items with no text at all",
    "too-short": "items with text too short to price",
    "low-signal-no-scope-keyword": "text with no construction-scope keyword (e.g. just labels)",
}

FRIENDLY_FILE_LABELS = [
    ("revision_changelog_xlsx", "Revision changelog workbook (Excel, embedded crops)"),
    ("pricing_change_log_csv", "Pricing log (approved scope on latest sheets) - hand this to estimators"),
    ("pricing_change_candidates_csv", "Pricing candidates (everything still being reviewed)"),
    ("conformed_sheet_index_csv", "Conformed sheet index (which version of each sheet is current)"),
    ("conformed_preview_pdf", "Conformed preview PDF (latest sheets first, superseded marked in red)"),
    ("supersedence_csv", "Supersedence log"),
    ("revision_index_csv", "Revision-set index"),
    ("approved_changes_csv", "Approved change items (raw)"),
    ("preflight_diagnostics_csv", "PDF preflight diagnostics"),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scopeledger", description="Review revision drawing sets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan revision PDFs into a workspace.")
    scan_parser.add_argument("input_dir", type=Path)
    scan_parser.add_argument("workspace_dir", type=Path)
    scan_parser.add_argument(
        "--cloudhammer-manifest",
        type=Path,
        default=None,
        help="Attach CloudHammer detections from a release/tight-crop manifest during scan.",
    )
    scan_parser.add_argument(
        "--approve-cloudhammer-detections",
        action="store_true",
        help="Mark CloudHammer visual detections approved so the workbook exporter includes them immediately.",
    )

    serve_parser = subparsers.add_parser("serve", help="Run the local review app.")
    serve_parser.add_argument(
        "app_data_dir",
        type=Path,
        nargs="?",
        default=None,
        help="Optional app data root. Defaults to ./app_workspaces under this repo.",
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=5000)
    serve_parser.add_argument("--debug", action="store_true")
    serve_parser.add_argument("--production", action="store_true", help="Serve with Waitress and require production-safe environment settings.")

    export_parser = subparsers.add_parser("export", help="Export approved review data.")
    export_parser.add_argument("workspace_dir", type=Path)
    export_parser.add_argument("--force-attention", action="store_true", help="Allow export even when attention items remain pending.")

    packet_parser = subparsers.add_parser("review-packet", help="Build a browser review packet with crop and source-page context images.")
    packet_parser.add_argument("workspace_dir", type=Path)
    packet_parser.add_argument("--output", type=Path, default=None, help="Optional HTML output path.")

    reset_parser = subparsers.add_parser("reset-projects", help="Clear the app project registry without deleting workspaces or source packages.")
    reset_parser.add_argument(
        "app_data_dir",
        type=Path,
        nargs="?",
        default=None,
        help="Optional app data root. Defaults to ./app_workspaces under this repo.",
    )

    review_events_parser = subparsers.add_parser("export-review-events", help="Export internal review event records as JSONL.")
    review_events_parser.add_argument("registry_or_workspace_dir", type=Path)
    review_events_parser.add_argument("--project-id", required=True, help="Project id whose internal review events should be exported.")
    review_events_parser.add_argument("--out", type=Path, default=None, help="Optional JSONL output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        cloud_client = ManifestCloudInferenceClient(args.cloudhammer_manifest) if args.cloudhammer_manifest else None
        scanner = RevisionScanner(args.input_dir, args.workspace_dir, cloud_inference_client=cloud_client)
        store = scanner.scan()
        approved_cloudhammer = 0
        if args.approve_cloudhammer_detections:
            approved_cloudhammer = approve_cloudhammer_detections(store)
        affected_documents = len([document for document in store.data.documents if document.issue_count])
        message = (
            f"Scanned {len(store.data.revision_sets)} revision sets, "
            f"{len(store.data.sheets)} sheet versions, "
            f"{len(store.data.change_items)} change items, "
            f"{len(store.data.preflight_issues)} diagnostics across {affected_documents} documents into {args.workspace_dir}"
        )
        if args.cloudhammer_manifest:
            message += f" with {len(store.data.clouds)} CloudHammer cloud candidate(s)"
        if approved_cloudhammer:
            message += f" ({approved_cloudhammer} CloudHammer change item(s) auto-approved for preview export)"
        if scanner.cache_hits:
            message += f" ({scanner.cache_hits} unchanged PDFs reused from cache)"
        print(message)
        return 0

    if args.command == "serve":
        if args.production and not _is_loopback_host(args.host):
            print("--production must bind to a loopback host such as 127.0.0.1 or localhost.")
            return 1
        if _is_project_workspace_path(args.app_data_dir):
            print("serve expects an app data root, not a project workspace. Use no path for app_workspaces or pass a dedicated app data folder.")
            return 1
        try:
            app = create_app(args.app_data_dir, production=args.production)
        except RuntimeError as exc:
            print(str(exc))
            return 1
        if args.production:
            try:
                serve_production_app(app, host=args.host, port=args.port)
            except RuntimeError as exc:
                print(str(exc))
                return 1
        else:
            app.run(host=args.host, port=args.port, debug=args.debug)
        return 0

    if args.command == "export":
        store = WorkspaceStore(args.workspace_dir).load()
        exporter = Exporter(store)
        try:
            outputs = exporter.export(force_attention=args.force_attention)
        except ExportBlockedError as exc:
            print(str(exc))
            print("")
            print("Tip: open the GUI and clear the attention queue first, or re-run with --force-attention.")
            print("  python -m backend serve")
            return 1
        print(format_export_summary(exporter.last_summary, outputs, args.workspace_dir))
        return 0

    if args.command == "review-packet":
        store = WorkspaceStore(args.workspace_dir).load()
        result = build_review_packet(store, output_path=args.output)
        print("Review packet complete.")
        print(f"  Items: {result.item_count}")
        print(f"  Assets: {result.asset_count}")
        print(f"  HTML: {result.html_path}")
        return 0

    if args.command == "reset-projects":
        if _is_project_workspace_path(args.app_data_dir):
            print("reset-projects expects an app data root, not a project workspace. Use no path for app_workspaces or pass a dedicated app data folder.")
            return 1
        registry = ProjectRegistry(args.app_data_dir or default_app_data_dir()).load()
        count = registry.clear()
        print(f"Cleared {count} app project registration(s).")
        print(f"  Registry: {registry.data_path}")
        print("  Workspace folders and revision_sets were not deleted.")
        return 0

    if args.command == "export-review-events":
        store = resolve_review_event_store(args.registry_or_workspace_dir, args.project_id)
        output = export_review_events_jsonl(store, project_id=args.project_id, output_path=args.out)
        count = len([event for event in store.data.review_events if event.project_id == args.project_id])
        print("Review events export complete.")
        print(f"  Project: {args.project_id}")
        print(f"  Events: {count}")
        print(f"  JSONL: {output}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    return normalized in {"127.0.0.1", "localhost", "::1"}


def _is_project_workspace_path(path: Path | None) -> bool:
    return bool(path and (path.resolve() / "workspace.json").exists())


def serve_production_app(app, *, host: str, port: int) -> None:
    try:
        from waitress import serve
    except ImportError as exc:
        raise RuntimeError("Waitress is required for --production. Install dependencies with requirements.txt.") from exc
    print(f"Serving ScopeLedger with Waitress at http://{host}:{port}")
    serve(app, host=host, port=port)


def resolve_review_event_store(registry_or_workspace_dir: Path, project_id: str) -> WorkspaceStore:
    base = registry_or_workspace_dir.resolve()
    if (base / "workspace.json").exists():
        return WorkspaceStore(base).load()
    registry_dir = base.parent if base.name == "projects.json" else base
    registry = ProjectRegistry(registry_dir).load()
    try:
        project = registry.get(project_id)
        return WorkspaceStore(project.workspace_dir).load()
    except KeyError:
        return WorkspaceStore(base).load()


def approve_cloudhammer_detections(store: WorkspaceStore) -> int:
    changed = 0
    updated = []
    for item in store.data.change_items:
        if is_superseded(item):
            updated.append(item)
            continue
        if item.provenance.get("source") == "visual-region" and item.provenance.get("extraction_method") == "cloudhammer_manifest":
            item.status = "approved"
            item.reviewer_text = item.reviewer_text or item.raw_text
            changed += 1
        updated.append(item)
    store.data.change_items = updated
    if changed:
        store.save()
    return changed


def format_export_summary(summary: dict, outputs: dict[str, str], workspace_dir: Path) -> str:
    output_dir = summary.get("output_dir") or str(Path(workspace_dir) / "outputs")
    pricing_log = summary.get("pricing_log_count", 0)
    pricing_candidates = summary.get("pricing_candidate_count", 0)
    approved = summary.get("approved_count", 0)
    pending = summary.get("pending_count", 0)
    rejected = summary.get("rejected_count", 0)
    attention_pending = summary.get("attention_pending_count", 0)
    active_sheets = summary.get("active_sheet_count", 0)
    superseded_sheets = summary.get("superseded_sheet_count", 0)
    revision_sets = summary.get("revision_set_count", 0)
    filtered_by_reason = summary.get("filtered_by_reason") or {}

    lines: list[str] = []
    lines.append("")
    lines.append("Export complete.")
    lines.append(f"  Files saved in: {output_dir}")
    lines.append("")
    lines.append("Pricing-ready rows (approved scope on the latest version of each sheet):")
    lines.append(f"  {pricing_log} item{'s' if pricing_log != 1 else ''}    -> pricing_change_log.csv")
    lines.append("")
    lines.append("Pricing candidates (visible scope changes still being reviewed):")
    lines.append(f"  {pricing_candidates} item{'s' if pricing_candidates != 1 else ''}    -> pricing_change_candidates.csv")
    lines.append("")
    lines.append("Conformed sheet set:")
    lines.append(
        f"  {active_sheets} latest sheet{'s' if active_sheets != 1 else ''}, "
        f"{superseded_sheets} superseded across {revision_sets} revision set{'s' if revision_sets != 1 else ''}"
    )
    lines.append("  -> conformed_sheet_index.csv, conformed_preview.pdf")
    lines.append("")
    lines.append("Review queue:")
    lines.append(f"  approved: {approved}   rejected: {rejected}   still pending: {pending}")
    if attention_pending:
        lines.append(f"  WARNING: {attention_pending} item(s) flagged for attention are still pending.")
        lines.append("  -> Review them in the GUI:  python -m backend serve")

    if filtered_by_reason:
        lines.append("")
        lines.append("Filtered out as noise (kept out of the pricing files):")
        for reason, count in sorted(filtered_by_reason.items(), key=lambda item: (-item[1], item[0])):
            label = FILTER_REASON_LABELS.get(reason, reason)
            lines.append(f"  {count:>4}  {label}")
        if "placeholder-no-readable-scope" in filtered_by_reason:
            lines.append("  -> These still appear in the GUI review queue if you want to verify them.")

    lines.append("")
    lines.append("Files written:")
    seen: set[str] = set()
    for key, label in FRIENDLY_FILE_LABELS:
        path = outputs.get(key)
        if not path or path in seen:
            continue
        seen.add(path)
        lines.append(f"  - {label}")
        lines.append(f"      {path}")
    return "\n".join(lines)
