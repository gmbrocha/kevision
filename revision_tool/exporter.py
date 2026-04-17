from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import fitz

from .diagnostics import configure_mupdf
from .models import ChangeItem, SheetVersion
from .review import change_item_needs_attention
from .utils import clean_display_text, parse_mmddyyyy
from .workspace import WorkspaceStore


class ExportBlockedError(RuntimeError):
    pass


PLACEHOLDER_SCOPE_PATTERN = re.compile(r"^possible revision region(\s+near\s+.+)?$", re.IGNORECASE)

LABEL_ONLY_TOKENS = frozenset(
    {
        "ROOM", "ROOMS", "FLOOR", "FLOORS", "PLAN", "PLANS", "SECTION", "SECTIONS",
        "DETAIL", "DETAILS", "VIEW", "VIEWS", "ELEVATION", "ELEVATIONS",
        "SCHED", "SCHEDULE", "SCHEDULES", "GLAZING", "CEILING", "CEILINGS",
        "EXISTING", "EXIST", "NEW", "TYP", "SIM", "SIMILAR", "SHEET", "SHEETS",
        "ABOVE", "BELOW", "EDGE", "EDGES", "AREA", "ZONE", "ZONES",
        "OVERALL", "ENLARGED", "REFLECTED", "PARTIAL",
        "MENS", "WOMENS", "LADIES", "LOBBY", "OFFICE", "CORRIDOR",
        "CHAPEL", "ATTIC", "RADIO", "COPY", "FAMILY", "DICTATION", "MD",
        "RX", "ATS", "PHARMACY", "NURSE", "NURSES", "WAITING", "STORAGE",
        "JANITOR", "ELEC", "MECH",
        "SEE", "FOR", "AT", "OF", "TO", "AND", "OR", "PER", "WITH",
        "DRAWINGS", "DRAWING", "NOTE", "NOTES",
    }
)

LOCATOR_TOKEN_PATTERN = re.compile(
    r"^(?:"
    r"SIM|SIM\.|TYP|EAST|WEST|NORTH|SOUTH|CENTER|CENTRAL|CENTRAL STAIR|EXIST STAIR|STAIR|"
    r"ROOM|RADIO ROOM|UNISEX TOILET|CHAPEL|BUILDING|VALLEY|RIDGE|SHOWER|BATHROOM|ALCOVE|TOILET|"
    r"[A-Z]{1,3}\d{2,4}(?:\.\d+)?|"
    r"\d+[A-Z]?\d*[A-Z]?|"
    r"[A-Z\d]{1,5}(?:[\-/.][A-Z\d.]+){1,3}"
    r")$",
    re.IGNORECASE,
)

EXTRA_PRICING_SCOPE_TOKENS = (
    "PARTITION", "COLUMN", "STRINGER", "CHWS", "CHWR", "VAV", "HEPA", "FILTER",
    "JOIST", "RAFTER", "SLAB", "CMU", "FOOTING", "SOFFIT", "CONDUIT",
    "DUCTWORK", "ROUTE", "RE-ROUTE", "REROUTE", "INFILL", "RELOCATE",
    "EXTEND", "MODIFY", "CONNECT", "MOUNT", "CHIP", "CHIPPING",
    "MILLWORK", "HANDRAIL", "GUARDRAIL", "CABINET",
)


class Exporter:
    def __init__(self, store: WorkspaceStore):
        configure_mupdf()
        self.store = store
        self.last_summary: dict[str, object] = {}

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
            "pricing_change_candidates_csv": str(self._write_pricing_change_candidates_csv()),
            "pricing_change_candidates_json": str(self._write_pricing_change_candidates_json()),
            "pricing_change_log_csv": str(self._write_pricing_change_log_csv()),
            "pricing_change_log_json": str(self._write_pricing_change_log_json()),
            "supersedence_csv": str(self._write_supersedence_csv()),
            "conformed_sheet_index_csv": str(self._write_conformed_sheet_index_csv()),
            "conformed_sheet_index_json": str(self._write_conformed_sheet_index_json()),
            "revision_index_csv": str(self._write_revision_index_csv()),
            "preflight_diagnostics_csv": str(self._write_preflight_diagnostics_csv()),
            "preflight_diagnostics_json": str(self._write_preflight_diagnostics_json()),
            "conformed_preview_pdf": str(self._write_preview_pdf()),
        }
        summary = self._build_summary(approved=approved, pending_attention=pending_attention, force_attention=force_attention)
        self.last_summary = summary
        self.store.data.exports.append(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "outputs": outputs,
                "approved_count": len(approved),
                "pending_count": len([item for item in self.store.data.change_items if item.status == "pending"]),
                "attention_pending_count": len(pending_attention),
                "forced_attention": force_attention,
                "summary": summary,
            }
        )
        self.store.save()
        return outputs

    def pricing_summary(self) -> dict[str, object]:
        """Read-only snapshot of the same metrics export() produces, without writing files."""
        change_items = self.store.data.change_items
        approved = [item for item in change_items if item.status == "approved"]
        pending_attention = [
            item for item in change_items if item.status == "pending" and change_item_needs_attention(item)
        ]
        return self._build_summary(approved=approved, pending_attention=pending_attention, force_attention=False)

    def _build_summary(
        self,
        approved: list[ChangeItem],
        pending_attention: list[ChangeItem],
        force_attention: bool,
    ) -> dict[str, object]:
        all_rows = self._all_pricing_rows()
        candidate_rows = [row for row in all_rows if row["pricing_relevance"]]
        log_rows = [row for row in candidate_rows if row["pricing_status"] == "approved" and row["latest_for_pricing"]]
        sheets = self.store.data.sheets
        change_items = self.store.data.change_items
        filtered_by_reason: dict[str, int] = {}
        for row in all_rows:
            if not row["pricing_relevance"]:
                reason = str(row["relevance_reason"])
                filtered_by_reason[reason] = filtered_by_reason.get(reason, 0) + 1
        return {
            "output_dir": str(self.store.output_dir),
            "approved_count": len(approved),
            "pending_count": len([item for item in change_items if item.status == "pending"]),
            "rejected_count": len([item for item in change_items if item.status == "rejected"]),
            "attention_pending_count": len(pending_attention),
            "force_attention": force_attention,
            "pricing_log_count": len(log_rows),
            "pricing_candidate_count": len(candidate_rows),
            "filtered_count": sum(filtered_by_reason.values()),
            "filtered_by_reason": filtered_by_reason,
            "active_sheet_count": len([sheet for sheet in sheets if sheet.status == "active"]),
            "superseded_sheet_count": len([sheet for sheet in sheets if sheet.status == "superseded"]),
            "revision_set_count": len(self.store.data.revision_sets),
        }

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

    def _build_sheet_context_maps(self) -> tuple[dict[str, object], dict[str, SheetVersion]]:
        revision_sets_by_id = {revision_set.id: revision_set for revision_set in self.store.data.revision_sets}
        active_by_sheet_id = {sheet.sheet_id: sheet for sheet in self.store.data.sheets if sheet.status == "active"}
        return revision_sets_by_id, active_by_sheet_id

    def _build_pricing_change_row(self, item: ChangeItem) -> dict[str, object]:
        revision_sets_by_id, active_by_sheet_id = self._build_sheet_context_maps()
        sheet = self.store.get_sheet(item.sheet_version_id)
        revision_set = revision_sets_by_id[sheet.revision_set_id]
        latest_sheet = active_by_sheet_id.get(sheet.sheet_id, sheet)
        reviewer_text = clean_display_text(item.reviewer_text or item.raw_text)
        scope_lines = self._extract_scope_lines(reviewer_text)
        latest_revision_set = revision_sets_by_id[latest_sheet.revision_set_id]
        relevance_reason = self._pricing_relevance_reason(
            sheet.sheet_title,
            scope_lines,
            reviewer_text,
            str(item.provenance.get("source", "")),
            item.status,
        )

        return {
            "change_id": item.id,
            "revision_set_number": revision_set.set_number,
            "revision_set_label": revision_set.label,
            "sheet_id": item.sheet_id,
            "sheet_title": self._display_sheet_title(sheet.sheet_title),
            "detail_ref": item.detail_ref or "",
            "detail_title": "",
            "change_summary": self._build_change_summary(scope_lines, reviewer_text),
            "scope_lines": scope_lines,
            "pricing_status": item.status,
            "needs_attention": change_item_needs_attention(item),
            "source_kind": str(item.provenance.get("source", "")),
            "extraction_signal": item.provenance.get("extraction_signal"),
            "source_pdf": sheet.source_pdf,
            "page_number": sheet.page_number,
            "sheet_version_id": sheet.id,
            "sheet_version_status": sheet.status,
            "superseded_by_revision_set": latest_revision_set.set_number if latest_sheet.id != sheet.id else "",
            "latest_for_pricing": latest_sheet.id == sheet.id,
            "reviewer_notes": clean_display_text(item.reviewer_notes),
            "pricing_relevance": relevance_reason in ("likely-pricing-scope", "reviewer-approved"),
            "relevance_reason": relevance_reason,
        }

    def _all_pricing_rows(self) -> list[dict[str, object]]:
        return [
            self._build_pricing_change_row(item)
            for item in self.store.data.change_items
            if item.status != "rejected"
        ]

    def _pricing_candidate_rows(self) -> list[dict[str, object]]:
        rows = [row for row in self._all_pricing_rows() if row["pricing_relevance"]]
        return sorted(
            rows,
            key=lambda row: (
                not row["latest_for_pricing"],
                row["revision_set_number"],
                row["sheet_id"],
                row["detail_ref"],
                row["change_id"],
            ),
        )

    def _pricing_log_rows(self) -> list[dict[str, object]]:
        rows = [row for row in self._pricing_candidate_rows() if row["pricing_status"] == "approved" and row["latest_for_pricing"]]
        return sorted(rows, key=lambda row: (row["sheet_id"], row["detail_ref"], row["change_id"]))

    def _write_pricing_change_candidates_csv(self) -> Path:
        path = self.store.output_dir / "pricing_change_candidates.csv"
        rows = self._pricing_candidate_rows()
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "change_id",
                    "revision_set_number",
                    "revision_set_label",
                    "sheet_id",
                    "sheet_title",
                    "detail_ref",
                    "detail_title",
                    "change_summary",
                    "scope_lines",
                    "pricing_status",
                    "needs_attention",
                    "source_kind",
                    "extraction_signal",
                    "source_pdf",
                    "page_number",
                    "sheet_version_id",
                    "sheet_version_status",
                    "superseded_by_revision_set",
                    "latest_for_pricing",
                    "reviewer_notes",
                    "pricing_relevance",
                    "relevance_reason",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({**row, "scope_lines": "; ".join(row["scope_lines"])})
        return path

    def _write_pricing_change_candidates_json(self) -> Path:
        path = self.store.output_dir / "pricing_change_candidates.json"
        path.write_text(json.dumps(self._pricing_candidate_rows(), indent=2), encoding="utf-8")
        return path

    def _write_pricing_change_log_csv(self) -> Path:
        path = self.store.output_dir / "pricing_change_log.csv"
        rows = self._pricing_log_rows()
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "change_id",
                    "revision_set_number",
                    "revision_set_label",
                    "sheet_id",
                    "sheet_title",
                    "detail_ref",
                    "detail_title",
                    "change_summary",
                    "scope_lines",
                    "pricing_status",
                    "needs_attention",
                    "source_kind",
                    "extraction_signal",
                    "source_pdf",
                    "page_number",
                    "sheet_version_id",
                    "sheet_version_status",
                    "superseded_by_revision_set",
                    "latest_for_pricing",
                    "reviewer_notes",
                    "pricing_relevance",
                    "relevance_reason",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({**row, "scope_lines": "; ".join(row["scope_lines"])})
        return path

    def _write_pricing_change_log_json(self) -> Path:
        path = self.store.output_dir / "pricing_change_log.json"
        path.write_text(json.dumps(self._pricing_log_rows(), indent=2), encoding="utf-8")
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

    def _conformed_sheet_index_rows(self) -> list[dict[str, object]]:
        revision_sets_by_id, active_by_sheet_id = self._build_sheet_context_maps()
        rows = []
        for sheet in self.store.data.sheets:
            revision_set = revision_sets_by_id[sheet.revision_set_id]
            latest_sheet = active_by_sheet_id.get(sheet.sheet_id, sheet)
            latest_revision_set = revision_sets_by_id[latest_sheet.revision_set_id]
            rows.append(
                {
                    "sheet_id": sheet.sheet_id,
                    "sheet_title": self._display_sheet_title(sheet.sheet_title),
                    "sheet_version_id": sheet.id,
                    "revision_set_number": revision_set.set_number,
                    "revision_set_label": revision_set.label,
                    "issue_date": sheet.issue_date or "",
                    "sheet_version_status": sheet.status,
                    "source_pdf": sheet.source_pdf,
                    "page_number": sheet.page_number,
                    "latest_sheet_version_id": latest_sheet.id,
                    "latest_revision_set_number": latest_revision_set.set_number,
                    "latest_revision_set_label": latest_revision_set.label,
                    "latest_source_pdf": latest_sheet.source_pdf,
                    "latest_page_number": latest_sheet.page_number,
                    "latest_for_pricing": latest_sheet.id == sheet.id,
                    "render_path": sheet.render_path,
                }
            )
        return sorted(
            rows,
            key=lambda row: (row["sheet_id"], not row["latest_for_pricing"], row["revision_set_number"], row["page_number"]),
        )

    def _write_conformed_sheet_index_csv(self) -> Path:
        path = self.store.output_dir / "conformed_sheet_index.csv"
        rows = self._conformed_sheet_index_rows()
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "sheet_id",
                    "sheet_title",
                    "sheet_version_id",
                    "revision_set_number",
                    "revision_set_label",
                    "issue_date",
                    "sheet_version_status",
                    "source_pdf",
                    "page_number",
                    "latest_sheet_version_id",
                    "latest_revision_set_number",
                    "latest_revision_set_label",
                    "latest_source_pdf",
                    "latest_page_number",
                    "latest_for_pricing",
                    "render_path",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        return path

    def _write_conformed_sheet_index_json(self) -> Path:
        path = self.store.output_dir / "conformed_sheet_index.json"
        path.write_text(json.dumps(self._conformed_sheet_index_rows(), indent=2), encoding="utf-8")
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

    def _extract_scope_lines(self, text: str) -> list[str]:
        cleaned = clean_display_text(text)
        if not cleaned:
            return []

        if "|" in cleaned:
            parts = cleaned.split("|")
        elif "\n" in text:
            parts = re.split(r"[\r\n]+", text)
        else:
            parts = re.split(r"\s*;\s*", cleaned)

        lines: list[str] = []
        seen: set[str] = set()
        for part in parts:
            line = clean_display_text(part).strip(" -|:,.;")
            if not line:
                continue
            normalized = line.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            lines.append(line)

        if lines:
            return lines[:8]
        return [cleaned]

    def _build_change_summary(self, scope_lines: list[str], fallback_text: str) -> str:
        if not scope_lines:
            return clean_display_text(fallback_text)
        if len(scope_lines) == 1:
            return scope_lines[0]
        summary = "; ".join(scope_lines[:2])
        if len(scope_lines) > 2:
            summary += f" (+{len(scope_lines) - 2} more)"
        return summary

    def _display_sheet_title(self, sheet_title: str) -> str:
        title = clean_display_text(sheet_title)
        if self._looks_like_sheet_index_title(title):
            return "Sheet Index / Conformed Set"
        return title

    def _pricing_relevance_reason(
        self,
        sheet_title: str,
        scope_lines: list[str],
        fallback_text: str,
        source_kind: str,
        status: str = "pending",
    ) -> str:
        combined_text = clean_display_text(" ".join(scope_lines) or fallback_text)
        if not combined_text:
            return "empty-text"

        if self._is_placeholder_scope(scope_lines, combined_text):
            return "placeholder-no-readable-scope"

        if status == "approved":
            return "reviewer-approved"

        if self._looks_like_sheet_index_title(sheet_title):
            return "sheet-index-page"

        if self._contains_pricing_scope_signal(combined_text):
            return "likely-pricing-scope"

        if source_kind == "narrative":
            return "likely-pricing-scope"

        if self._is_likely_locator_text(scope_lines or [combined_text]):
            return "locator-only-text"

        if len(scope_lines) == 1 and len(scope_lines[0]) <= 8:
            return "too-short"

        return "low-signal-no-scope-keyword"

    def _is_placeholder_scope(self, scope_lines: list[str], combined_text: str) -> bool:
        candidates: list[str] = list(scope_lines) if scope_lines else []
        if combined_text:
            candidates.append(combined_text)
        for candidate in candidates:
            if PLACEHOLDER_SCOPE_PATTERN.match(candidate.strip()):
                return True
        return False

    def _looks_like_sheet_index_title(self, sheet_title: str) -> bool:
        title = clean_display_text(sheet_title).upper()
        if not title:
            return False
        if any(token in title for token in ("SHEET INDEX", "CONFORMED SET", "PAGE NO.", "SHEET NO.")):
            return True
        if len(title) > 220 and title.count(" X ") >= 6:
            return True
        return False

    def _is_likely_locator_text(self, scope_lines: list[str]) -> bool:
        lines = [clean_display_text(line) for line in scope_lines if clean_display_text(line)]
        if not lines:
            return False
        if any(self._contains_pricing_scope_signal(line) for line in lines):
            return False

        tokens: list[str] = []
        for line in lines:
            for part in re.split(r"[;,]", line):
                token = part.strip(" -|:.;\"'")
                if token:
                    tokens.append(token)
        if not tokens:
            return False
        return all(self._token_is_locator_or_label(token) for token in tokens)

    def _token_is_locator_or_label(self, token: str) -> bool:
        if not token:
            return False
        if LOCATOR_TOKEN_PATTERN.fullmatch(token):
            return True
        words = [word for word in re.split(r"\s+", token.upper()) if word]
        if not words:
            return False
        return all(
            word in LABEL_ONLY_TOKENS or LOCATOR_TOKEN_PATTERN.fullmatch(word)
            for word in words
        )

    def _contains_pricing_scope_signal(self, text: str) -> bool:
        upper = clean_display_text(text).upper()
        strong_scope_tokens = (
            "ADD",
            "REMOVE",
            "REPLACE",
            "INSTALL",
            "PROVIDE",
            "PATCH",
            "REPAIR",
            "DEMOLISH",
            "STUD",
            "GYPSUM",
            "BOARD",
            "SHAFTLINER",
            "SHAFT LINER",
            "BEAD",
            "DUCT",
            "PIPE",
            "PIPING",
            "VALVE",
            "DRAIN",
            "GRAB BAR",
            "SUPPORT",
            "ASSEMBLY",
            "RATED",
            "ENCLOSURE",
            "CONCRETE",
            "FASTEN",
            "INSULATION",
            "MASONRY",
            "OPENING",
            "FRAME",
            "CAULK",
            "FIRE",
            "ACCESSORY",
            "HWR",
            "HWS",
            "HW",
            "VTR",
            "BLOCKING",
            "TRACK",
            "BEAM",
            "RISER",
            *EXTRA_PRICING_SCOPE_TOKENS,
        )
        if any(token in upper for token in strong_scope_tokens):
            return True

        quantity_material_patterns = (
            r'\b\d+(?:\s+\d/\d+)?["\']?\s*(?:CT|MTL|METAL)?\s*STUDS?\b',
            r'\b\d+(?:\s+\d/\d+)?["\']?\s*(?:FIRE[- ]SHIELD|GYP|GYPSUM|BOARD|PIPE|DUCT)\b',
            r'\b(?:LAYER|LAYERS)\s+\d',
        )
        return any(re.search(pattern, upper, re.IGNORECASE) for pattern in quantity_material_patterns)
