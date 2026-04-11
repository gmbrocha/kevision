from __future__ import annotations

import re
from pathlib import Path

import fitz

from .models import PreflightIssue, SourceDocument
from .utils import stable_id

SEVERITY_ORDER = {"ok": 0, "low": 1, "medium": 2, "high": 3}
WARNING_RULES = [
    ("broken_stream_length", "medium", "PDF stream Length incorrect"),
    ("missing_xref_object", "high", "cannot find object in xref"),
    ("cache_load_failure", "high", "cannot load object"),
    ("broken_structure_tree", "low", "No common ancestor in structure tree"),
]


def configure_mupdf() -> None:
    fitz.TOOLS.mupdf_display_errors(False)
    fitz.TOOLS.mupdf_display_warnings(False)


def parse_mupdf_warnings(raw: str) -> list[tuple[str, int]]:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    parsed: list[list[object]] = []
    for line in lines:
        repeat_match = re.fullmatch(r"\.\.\. repeated (\d+) times\.\.\.", line)
        if repeat_match and parsed:
            parsed[-1][1] += int(repeat_match.group(1))
            continue
        parsed.append([line, 1])
    return [(message, count) for message, count in parsed]


def classify_warning(message: str) -> tuple[str, str]:
    for code, severity, needle in WARNING_RULES:
        if needle in message:
            return code, severity
    return ("mupdf_warning", "medium")


def capture_preflight_issues(
    *,
    document_id: str,
    source_pdf: str,
    page_number: int | None,
    operation: str,
    raw_warnings: str,
) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    for message, count in parse_mupdf_warnings(raw_warnings):
        code, severity = classify_warning(message)
        issues.append(
            PreflightIssue(
                id=stable_id(source_pdf, page_number or 0, operation, code, message),
                document_id=document_id,
                source_pdf=source_pdf,
                page_number=page_number,
                operation=operation,
                code=code,
                severity=severity,
                message=message,
                count=count,
            )
        )
    return issues


def summarize_documents(documents: list[SourceDocument], issues: list[PreflightIssue]) -> list[SourceDocument]:
    issues_by_doc: dict[str, list[PreflightIssue]] = {}
    for issue in issues:
        issues_by_doc.setdefault(issue.document_id, []).append(issue)

    summarized: list[SourceDocument] = []
    for document in documents:
        doc_issues = issues_by_doc.get(document.id, [])
        max_severity = "ok"
        for issue in doc_issues:
            if SEVERITY_ORDER[issue.severity] > SEVERITY_ORDER[max_severity]:
                max_severity = issue.severity
        summarized.append(
            SourceDocument(
                id=document.id,
                revision_set_id=document.revision_set_id,
                source_pdf=document.source_pdf,
                page_count=document.page_count,
                is_repaired=document.is_repaired,
                needs_pass=document.needs_pass,
                warning_count=sum(issue.count for issue in doc_issues),
                issue_count=len(doc_issues),
                max_severity=max_severity,
            )
        )
    return summarized


def build_diagnostic_summary(documents: list[SourceDocument], issues: list[PreflightIssue]) -> dict[str, object]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for issue in issues:
        if issue.severity in counts:
            counts[issue.severity] += issue.count
    affected_documents = [document for document in documents if document.issue_count]
    return {
        "document_count": len(documents),
        "affected_document_count": len(affected_documents),
        "issue_count": len(issues),
        "warning_count": sum(issue.count for issue in issues),
        "severity_counts": counts,
    }


def format_pdf_label(source_pdf: str, base_dir: Path | None = None) -> str:
    path = Path(source_pdf)
    if base_dir:
        try:
            return path.resolve().relative_to(base_dir.resolve()).as_posix()
        except ValueError:
            pass
    return path.name
