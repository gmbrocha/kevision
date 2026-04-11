from __future__ import annotations

import argparse
from pathlib import Path

from .exporter import ExportBlockedError, Exporter
from .scanner import RevisionScanner
from .web import create_app
from .workspace import WorkspaceStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="revision_tool", description="Review revision drawing sets.")
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
        try:
            outputs = Exporter(store).export(force_attention=args.force_attention)
        except ExportBlockedError as exc:
            print(str(exc))
            return 1
        for label, path in outputs.items():
            print(f"{label}: {path}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2
