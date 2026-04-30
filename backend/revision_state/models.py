from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SourceDocument:
    id: str
    revision_set_id: str
    source_pdf: str
    page_count: int
    is_repaired: bool = False
    needs_pass: int = 0
    warning_count: int = 0
    issue_count: int = 0
    max_severity: str = "ok"


@dataclass
class PreflightIssue:
    id: str
    document_id: str
    source_pdf: str
    page_number: int | None
    operation: str
    code: str
    severity: str
    message: str
    count: int = 1


@dataclass
class NarrativeEntry:
    id: str
    revision_set_id: str
    source_pdf: str
    page_number: int
    sheet_id: str
    heading: str
    summary: str


@dataclass
class RevisionSet:
    id: str
    label: str
    source_dir: str
    set_number: int
    set_date: str | None
    pdf_paths: list[str] = field(default_factory=list)


@dataclass
class SheetVersion:
    id: str
    revision_set_id: str
    source_pdf: str
    page_number: int
    sheet_id: str
    sheet_title: str
    issue_date: str | None
    revision_entries: list[str] = field(default_factory=list)
    narrative_entry_ids: list[str] = field(default_factory=list)
    status: str = "pending"
    render_path: str = ""
    width: int = 0
    height: int = 0
    page_text_excerpt: str = ""


@dataclass
class CloudCandidate:
    id: str
    sheet_version_id: str
    bbox: list[int]
    image_path: str
    page_image_path: str
    confidence: float
    extraction_method: str
    nearby_text: str
    detail_ref: str | None
    scope_text: str = ""
    scope_reason: str = ""
    scope_signal: float = 0.0
    scope_method: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChangeItem:
    id: str
    sheet_version_id: str
    cloud_candidate_id: str | None
    sheet_id: str
    detail_ref: str | None
    raw_text: str
    normalized_text: str
    provenance: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    reviewer_text: str = ""
    reviewer_notes: str = ""


@dataclass
class VerificationRecord:
    id: str
    change_item_id: str
    provider: str
    created_at: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    disposition: str = "pending"


@dataclass
class WorkspaceData:
    workspace_version: int = 2
    input_dir: str = ""
    created_at: str = ""
    documents: list[SourceDocument] = field(default_factory=list)
    preflight_issues: list[PreflightIssue] = field(default_factory=list)
    revision_sets: list[RevisionSet] = field(default_factory=list)
    narrative_entries: list[NarrativeEntry] = field(default_factory=list)
    sheets: list[SheetVersion] = field(default_factory=list)
    clouds: list[CloudCandidate] = field(default_factory=list)
    change_items: list[ChangeItem] = field(default_factory=list)
    verifications: list[VerificationRecord] = field(default_factory=list)
    exports: list[dict[str, Any]] = field(default_factory=list)
    scan_cache: dict[str, Any] = field(default_factory=dict)
    populate_status: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkspaceData":
        def load_many(key: str, factory):
            return [factory(**item) for item in payload.get(key, [])]

        return cls(
            workspace_version=payload.get("workspace_version", 1),
            input_dir=payload.get("input_dir", ""),
            created_at=payload.get("created_at", ""),
            documents=load_many("documents", SourceDocument),
            preflight_issues=load_many("preflight_issues", PreflightIssue),
            revision_sets=load_many("revision_sets", RevisionSet),
            narrative_entries=load_many("narrative_entries", NarrativeEntry),
            sheets=load_many("sheets", SheetVersion),
            clouds=load_many("clouds", CloudCandidate),
            change_items=load_many("change_items", ChangeItem),
            verifications=load_many("verifications", VerificationRecord),
            exports=payload.get("exports", []),
            scan_cache=payload.get("scan_cache", {}),
            populate_status=payload.get("populate_status", {}),
        )
