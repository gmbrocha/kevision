from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import fitz

from .diagnostics import configure_mupdf
from .models import ChangeItem, SheetVersion
from .review import change_item_needs_attention
from .workspace import WorkspaceStore


class ExportBlockedError(RuntimeError):
    pass


class Exporter:
    def __init__(self, store: WorkspaceStore):
        configure_mupdf()
        self.store = store

    def export(self, force_attention: bool = False) -> dict[str, str]:
        pending_attention = [
            item for item in self.store.data.change_items if item.status == "pending" and change_item_needs_attention(item)
        ]
        if pending_attention and not force_attention:
            raise ExportBlockedError(
                f"Export blocked: {len(pending_attention)} attention item(s) are still pending review. Resolve them or force the export."
            )
        approved = [item for item in self.store.data.change_items if item.status == "approved"]
        outputs = {
            "approved_changes_csv": str(self._write_approved_csv(approved)),
            "approved_changes_json": str(self._write_approved_json(approved)),
            "supersedence_csv": str(self._write_supersedence_csv()),
            "revision_index_csv": str(self._write_revision_index_csv()),
            "preflight_diagnostics_csv": str(self._write_preflight_diagnostics_csv()),
            "preflight_diagnostics_json": str(self._write_preflight_diagnostics_json()),
            "conformed_preview_pdf": str(self._write_preview_pdf()),
        }
        self.store.data.exports.append(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "outputs": outputs,
                "approved_count": len(approved),
                "pending_count": len([item for item in self.store.data.change_items if item.status == "pending"]),
                "attention_pending_count": len(pending_attention),
                "forced_attention": force_attention,
            }
        )
        self.store.save()
        return outputs

    def _write_approved_csv(self, approved: list[ChangeItem]) -> Path:
        path = self.store.output_dir / "approved_changes.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "change_id",
                    "sheet_id",
                    "detail_ref",
                    "reviewer_text",
                    "raw_text",
                    "sheet_version_id",
                    "status",
                ],
            )
            writer.writeheader()
            for item in approved:
                writer.writerow(
                    {
                        "change_id": item.id,
                        "sheet_id": item.sheet_id,
                        "detail_ref": item.detail_ref or "",
                        "reviewer_text": item.reviewer_text or item.raw_text,
                        "raw_text": item.raw_text,
                        "sheet_version_id": item.sheet_version_id,
                        "status": item.status,
                    }
                )
        return path

    def _write_approved_json(self, approved: list[ChangeItem]) -> Path:
        path = self.store.output_dir / "approved_changes.json"
        rows = []
        for item in approved:
            rows.append(
                {
                    "change_id": item.id,
                    "sheet_id": item.sheet_id,
                    "detail_ref": item.detail_ref,
                    "text": item.reviewer_text or item.raw_text,
                    "raw_text": item.raw_text,
                    "sheet_version_id": item.sheet_version_id,
                }
            )
        path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        return path

    def _write_supersedence_csv(self) -> Path:
        path = self.store.output_dir / "supersedence.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["sheet_id", "sheet_version_id", "status", "source_pdf", "page_number", "issue_date"],
            )
            writer.writeheader()
            for sheet in self.store.data.sheets:
                writer.writerow(
                    {
                        "sheet_id": sheet.sheet_id,
                        "sheet_version_id": sheet.id,
                        "status": sheet.status,
                        "source_pdf": sheet.source_pdf,
                        "page_number": sheet.page_number,
                        "issue_date": sheet.issue_date or "",
                    }
                )
        return path

    def _write_revision_index_csv(self) -> Path:
        path = self.store.output_dir / "revision_index.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["revision_set", "set_number", "set_date", "pdf_count"],
            )
            writer.writeheader()
            for revision_set in self.store.data.revision_sets:
                writer.writerow(
                    {
                        "revision_set": revision_set.label,
                        "set_number": revision_set.set_number,
                        "set_date": revision_set.set_date or "",
                        "pdf_count": len(revision_set.pdf_paths),
                    }
                )
        return path

    def _write_preview_pdf(self) -> Path:
        output_path = self.store.output_dir / "conformed_preview.pdf"
        document = fitz.open()
        try:
            active = sorted([sheet for sheet in self.store.data.sheets if sheet.status == "active"], key=lambda item: item.sheet_id)
            superseded = sorted([sheet for sheet in self.store.data.sheets if sheet.status == "superseded"], key=lambda item: item.sheet_id)
            for sheet in [*active, *superseded]:
                self._append_rasterized_sheet(document, sheet)
            document.save(output_path)
        finally:
            document.close()
        return output_path

    def _append_rasterized_sheet(self, output: fitz.Document, sheet: SheetVersion) -> None:
        page = output.new_page(width=sheet.width or 1224, height=sheet.height or 792)
        page.insert_image(page.rect, filename=sheet.render_path)
        if sheet.status == "superseded":
            banner = fitz.Rect(72, 72, page.rect.width - 72, 180)
            page.draw_rect(banner, color=(1, 0, 0), fill=(1, 1, 1), fill_opacity=0.65, overlay=True)
            page.insert_textbox(
                banner,
                "SUPERSEDED BY LATER REVISION",
                fontsize=42,
                color=(1, 0, 0),
                align=1,
                overlay=True,
            )

    def _write_preflight_diagnostics_csv(self) -> Path:
        path = self.store.output_dir / "preflight_diagnostics.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "source_pdf",
                    "page_number",
                    "operation",
                    "severity",
                    "code",
                    "message",
                    "count",
                ],
            )
            writer.writeheader()
            for issue in self.store.data.preflight_issues:
                writer.writerow(
                    {
                        "source_pdf": issue.source_pdf,
                        "page_number": issue.page_number or "",
                        "operation": issue.operation,
                        "severity": issue.severity,
                        "code": issue.code,
                        "message": issue.message,
                        "count": issue.count,
                    }
                )
        return path

    def _write_preflight_diagnostics_json(self) -> Path:
        path = self.store.output_dir / "preflight_diagnostics.json"
        payload = {
            "documents": [
                {
                    "source_pdf": document.source_pdf,
                    "page_count": document.page_count,
                    "warning_count": document.warning_count,
                    "issue_count": document.issue_count,
                    "max_severity": document.max_severity,
                    "is_repaired": document.is_repaired,
                    "needs_pass": document.needs_pass,
                }
                for document in self.store.data.documents
            ],
            "issues": [
                {
                    "source_pdf": issue.source_pdf,
                    "page_number": issue.page_number,
                    "operation": issue.operation,
                    "severity": issue.severity,
                    "code": issue.code,
                    "message": issue.message,
                    "count": issue.count,
                }
                for issue in self.store.data.preflight_issues
            ],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path
