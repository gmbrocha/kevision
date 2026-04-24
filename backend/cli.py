from __future__ import annotations

import argparse
from pathlib import Path

from .deliverables.excel_exporter import ExportBlockedError, Exporter
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
    parser = argparse.ArgumentParser(prog="kevision", description="Review revision drawing sets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan revision PDFs into a workspace.")
    scan_parser.add_argument("input_dir", type=Path)
    scan_parser.add_argument("workspace_dir", type=Path)

    serve_parser = subparsers.add_parser("serve", help="Run the local review app.")
    serve_parser.add_argument("workspace_dir", type=Path)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=5000)
    serve_parser.add_argument("--debug", action="store_true")

    export_parser = subparsers.add_parser("export", help="Export approved review data.")
    export_parser.add_argument("workspace_dir", type=Path)
    export_parser.add_argument("--force-attention", action="store_true", help="Allow export even when attention items remain pending.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        scanner = RevisionScanner(args.input_dir, args.workspace_dir)
        store = scanner.scan()
        affected_documents = len([document for document in store.data.documents if document.issue_count])
        message = (
            f"Scanned {len(store.data.revision_sets)} revision sets, "
            f"{len(store.data.sheets)} sheet versions, "
            f"{len(store.data.change_items)} change items, "
            f"{len(store.data.preflight_issues)} diagnostics across {affected_documents} documents into {args.workspace_dir}"
        )
        if scanner.cache_hits:
            message += f" ({scanner.cache_hits} unchanged PDFs reused from cache)"
        print(message)
        return 0

    if args.command == "serve":
        app = create_app(args.workspace_dir)
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
            print(f"  python -m backend serve {args.workspace_dir}")
            return 1
        print(format_export_summary(exporter.last_summary, outputs, args.workspace_dir))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


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
        lines.append(f"  -> Review them in the GUI:  python -m backend serve {workspace_dir}")

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
