from __future__ import annotations

import re
from dataclasses import asdict, replace
from pathlib import Path

import fitz

from ..cloudhammer_client.inference import CloudInferenceClient, NullCloudInferenceClient
from ..diagnostics import capture_preflight_issues, configure_mupdf, summarize_documents
from ..review_queue import ensure_queue_order, legacy_review_sort_key, review_queue_sort_key
from ..scope_extraction import extract_cloud_scope_text
from ..workspace import WorkspaceStore
from ..utils import DATE_PATTERN, choose_best_sheet_id, clean_display_text, normalize_text, parse_detail_ref, parse_mmddyyyy, stable_id
from .models import ChangeItem, CloudCandidate, NarrativeEntry, PreflightIssue, RevisionSet, SheetVersion, SourceDocument
from .page_classification import sheet_is_index_like

REVISION_FOLDER_PATTERN = re.compile(r"Revision\s*(?:#|Set)?\s*(?P<number>\d+)", re.IGNORECASE)
SCOPE_EXTRACTION_CACHE_VERSION = 3
REVIEW_SIDE_PROVENANCE_KEYS = {
    "scopeledger.pre_review.v1",
    "scopeledger.crop_adjustment.v1",
    "scopeledger.geometry_correction.v1",
    "scopeledger.legend_context.v1",
}


def _preferred_sheet_prefixes(pdf_path: Path | None) -> tuple[str, ...]:
    if not pdf_path:
        return ()
    name = pdf_path.name.lower()
    if "plumbing" in name:
        return ("PL", "P", "MP")
    return ()


class RevisionScanner:
    def __init__(
        self,
        input_dir: Path,
        workspace_dir: Path,
        cloud_inference_client: CloudInferenceClient | None = None,
    ):
        configure_mupdf()
        self.input_dir = input_dir.resolve()
        self.workspace_dir = workspace_dir
        self.cloud_inference_client = cloud_inference_client or NullCloudInferenceClient()
        self.store = WorkspaceStore(workspace_dir)
        if self.store.data_path.exists():
            self.store.load()
            if Path(self.store.data.input_dir).resolve() != self.input_dir:
                self.store.create(self.input_dir)
        else:
            self.store.create(self.input_dir)
        self.previous_clouds = list(self.store.data.clouds)
        self.previous_change_items = list(self.store.data.change_items)
        self.previous_verifications = list(self.store.data.verifications)
        self.previous_review_events = list(self.store.data.review_events)
        self.previous_scan_cache = dict(self.store.data.scan_cache.get("documents", {}))
        self.cache_hits = 0

    def _cloud_inference_cache_key(self) -> str:
        return str(
            getattr(
                self.cloud_inference_client,
                "cache_key",
                getattr(self.cloud_inference_client, "name", self.cloud_inference_client.__class__.__name__),
            )
        )

    def scan(self) -> WorkspaceStore:
        documents: list[SourceDocument] = []
        preflight_issues: list[PreflightIssue] = []
        revision_sets: list[RevisionSet] = []
        narratives: list[NarrativeEntry] = []
        sheets: list[SheetVersion] = []
        clouds: list[CloudCandidate] = []
        next_scan_cache: dict[str, dict[str, object]] = {}

        for folder in sorted(path for path in self.input_dir.iterdir() if path.is_dir()):
            revision_set = self._build_revision_set(folder)
            revision_sets.append(revision_set)
            folder_sheets: list[SheetVersion] = []

            for pdf_path in sorted(folder.rglob("*.pdf")):
                source_pdf = str(pdf_path.resolve())
                revision_set.pdf_paths.append(source_pdf)
                fingerprint = self._document_fingerprint(pdf_path)
                cache_entry = self.previous_scan_cache.get(source_pdf)
                if self._cache_entry_usable(cache_entry, fingerprint):
                    cached_document, cached_issues, cached_narratives, cached_sheets, cached_clouds = self._inflate_cache_entry(cache_entry)
                    documents.append(cached_document)
                    preflight_issues.extend(cached_issues)
                    narratives.extend(cached_narratives)
                    sheets.extend(cached_sheets)
                    clouds.extend(cached_clouds)
                    folder_sheets.extend(cached_sheets)
                    next_scan_cache[source_pdf] = self._build_cache_entry(
                        fingerprint=fingerprint,
                        document=cached_document,
                        preflight_issues=cached_issues,
                        narratives=cached_narratives,
                        sheets=cached_sheets,
                        clouds=cached_clouds,
                    )
                    self.cache_hits += 1
                    continue

                parsed_document, parsed_issues, parsed_narratives, parsed_sheets, parsed_clouds = self._scan_document(
                    revision_set=revision_set,
                    pdf_path=pdf_path,
                )
                documents.append(parsed_document)
                preflight_issues.extend(parsed_issues)
                narratives.extend(parsed_narratives)
                sheets.extend(parsed_sheets)
                clouds.extend(parsed_clouds)
                folder_sheets.extend(parsed_sheets)
                next_scan_cache[source_pdf] = self._build_cache_entry(
                    fingerprint=fingerprint,
                    document=parsed_document,
                    preflight_issues=parsed_issues,
                    narratives=parsed_narratives,
                    sheets=parsed_sheets,
                    clouds=parsed_clouds,
                )

            revision_sets[-1] = replace(
                revision_set,
                set_date=self._choose_revision_set_date(folder_sheets),
            )

        sheets = self._apply_supersedence(revision_sets, sheets)
        change_items = self._restore_review_state(self._generate_change_items(narratives, sheets, clouds))
        change_items, _ = ensure_queue_order(change_items)
        clouds = self._restore_review_managed_clouds(clouds, change_items)
        documents = summarize_documents(documents, preflight_issues)

        self.store.data.documents = documents
        self.store.data.preflight_issues = preflight_issues
        self.store.data.revision_sets = revision_sets
        self.store.data.narrative_entries = narratives
        self.store.data.sheets = sheets
        self.store.data.clouds = clouds
        self.store.data.change_items = change_items
        self.store.data.verifications = [record for record in self.previous_verifications if record.change_item_id in {item.id for item in change_items}]
        self.store.data.review_events = self.previous_review_events
        self.store.data.scan_cache = {"documents": next_scan_cache}
        self.store.save()
        return self.store

    def _scan_document(
        self,
        revision_set: RevisionSet,
        pdf_path: Path,
    ) -> tuple[SourceDocument, list[PreflightIssue], list[NarrativeEntry], list[SheetVersion], list[CloudCandidate]]:
        source_pdf = str(pdf_path.resolve())
        document_id = stable_id(source_pdf)
        preflight_issues: list[PreflightIssue] = []
        narratives: list[NarrativeEntry] = []
        sheets: list[SheetVersion] = []
        clouds: list[CloudCandidate] = []
        narrative_by_sheet: dict[str, list[NarrativeEntry]] = {}

        fitz.TOOLS.reset_mupdf_warnings()
        try:
            document = fitz.open(pdf_path)
        except Exception as exc:
            source_document = SourceDocument(
                id=document_id,
                revision_set_id=revision_set.id,
                source_pdf=source_pdf,
                page_count=0,
            )
            preflight_issues.append(
                PreflightIssue(
                    id=stable_id(source_pdf, 0, "open", "pdf_open_failed", exc.__class__.__name__),
                    document_id=document_id,
                    source_pdf=source_pdf,
                    page_number=None,
                    operation="open",
                    code="pdf_open_failed",
                    severity="high",
                    message=f"PDF could not be opened: {exc.__class__.__name__}",
                )
            )
            return source_document, preflight_issues, narratives, sheets, clouds
        try:
            preflight_issues.extend(
                capture_preflight_issues(
                    document_id=document_id,
                    source_pdf=source_pdf,
                    page_number=None,
                    operation="open",
                    raw_warnings=fitz.TOOLS.mupdf_warnings(),
                )
            )
            source_document = SourceDocument(
                id=document_id,
                revision_set_id=revision_set.id,
                source_pdf=source_pdf,
                page_count=document.page_count,
                is_repaired=bool(getattr(document, "is_repaired", False)),
                needs_pass=int(getattr(document, "needs_pass", 0)),
            )

            for page_index in range(document.page_count):
                page = document[page_index]

                fitz.TOOLS.reset_mupdf_warnings()
                text = page.get_text("text")
                preflight_issues.extend(
                    capture_preflight_issues(
                        document_id=document_id,
                        source_pdf=source_pdf,
                        page_number=page_index + 1,
                        operation="text",
                        raw_warnings=fitz.TOOLS.mupdf_warnings(),
                    )
                )
                if self._is_narrative_page(text):
                    page_narratives = self._parse_narrative_page(
                        revision_set_id=revision_set.id,
                        source_pdf=source_pdf,
                        page_number=page_index + 1,
                        text=text,
                    )
                    for entry in page_narratives:
                        narratives.append(entry)
                        narrative_by_sheet.setdefault(entry.sheet_id, []).append(entry)
                    continue

                metadata = self._extract_sheet_metadata(page, text, pdf_path)
                if not metadata["sheet_id"]:
                    continue

                sheet_id = stable_id(pdf_path, page_index + 1, metadata["sheet_id"])
                render_path = self.store.page_path(sheet_id)
                fitz.TOOLS.reset_mupdf_warnings()
                pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0), alpha=False)
                preflight_issues.extend(
                    capture_preflight_issues(
                        document_id=document_id,
                        source_pdf=source_pdf,
                        page_number=page_index + 1,
                        operation="render",
                        raw_warnings=fitz.TOOLS.mupdf_warnings(),
                    )
                )
                pix.save(render_path)

                page_narratives = narrative_by_sheet.get(metadata["sheet_id"], [])
                sheet = SheetVersion(
                    id=sheet_id,
                    revision_set_id=revision_set.id,
                    source_pdf=source_pdf,
                    page_number=page_index + 1,
                    sheet_id=metadata["sheet_id"],
                    sheet_title=metadata["sheet_title"],
                    issue_date=metadata["issue_date"],
                    revision_entries=metadata["revision_entries"],
                    narrative_entry_ids=[entry.id for entry in page_narratives],
                    render_path=str(render_path.resolve()),
                    width=pix.width,
                    height=pix.height,
                    page_text_excerpt=normalize_text(text)[:1000],
                )
                sheets.append(sheet)

                preflight_issues.extend(self._run_import_check(document_id, source_pdf, document, page_index))
                clouds.extend(self._detect_cloud_candidates(page=page, sheet=sheet))
        finally:
            document.close()

        return source_document, preflight_issues, narratives, sheets, clouds

    def _build_revision_set(self, folder: Path) -> RevisionSet:
        match = REVISION_FOLDER_PATTERN.search(folder.name)
        set_number = int(match.group("number")) if match else 0
        return RevisionSet(
            id=stable_id(folder.resolve()),
            label=folder.name,
            source_dir=str(folder.resolve()),
            set_number=set_number,
            set_date=None,
            pdf_paths=[],
        )

    def _document_fingerprint(self, pdf_path: Path) -> str:
        stat = pdf_path.stat()
        return stable_id(pdf_path.resolve(), stat.st_size, stat.st_mtime_ns)

    def _cache_entry_usable(self, cache_entry: dict[str, object] | None, fingerprint: str) -> bool:
        if not cache_entry or cache_entry.get("fingerprint") != fingerprint:
            return False
        if cache_entry.get("cloud_inference_cache_key") != self._cloud_inference_cache_key():
            return False
        if (
            cache_entry.get("clouds")
            and cache_entry.get("scope_extraction_version") != SCOPE_EXTRACTION_CACHE_VERSION
            and not isinstance(self.cloud_inference_client, NullCloudInferenceClient)
        ):
            return False
        for sheet in cache_entry.get("sheets", []):
            render_path = sheet.get("render_path", "")
            if render_path and not (self.store.page_dir / Path(render_path).name).exists():
                return False
        for cloud in cache_entry.get("clouds", []):
            if cloud.get("image_path") and not (self.store.crop_dir / Path(cloud["image_path"]).name).exists():
                return False
        return True

    def _inflate_cache_entry(
        self,
        cache_entry: dict[str, object],
    ) -> tuple[SourceDocument, list[PreflightIssue], list[NarrativeEntry], list[SheetVersion], list[CloudCandidate]]:
        sheets = []
        for item in cache_entry.get("sheets", []):
            payload = dict(item)
            if payload.get("render_path"):
                payload["render_path"] = str((self.store.page_dir / Path(payload["render_path"]).name).resolve())
            sheets.append(SheetVersion(**payload))

        clouds = []
        for item in cache_entry.get("clouds", []):
            payload = dict(item)
            if payload.get("image_path"):
                payload["image_path"] = str((self.store.crop_dir / Path(payload["image_path"]).name).resolve())
            if payload.get("page_image_path"):
                payload["page_image_path"] = str((self.store.page_dir / Path(payload["page_image_path"]).name).resolve())
            clouds.append(CloudCandidate(**payload))

        return (
            SourceDocument(**cache_entry["document"]),
            [PreflightIssue(**item) for item in cache_entry.get("preflight_issues", [])],
            [NarrativeEntry(**item) for item in cache_entry.get("narratives", [])],
            sheets,
            clouds,
        )

    def _build_cache_entry(
        self,
        fingerprint: str,
        document: SourceDocument,
        preflight_issues: list[PreflightIssue],
        narratives: list[NarrativeEntry],
        sheets: list[SheetVersion],
        clouds: list[CloudCandidate],
    ) -> dict[str, object]:
        return {
            "fingerprint": fingerprint,
            "scope_extraction_version": SCOPE_EXTRACTION_CACHE_VERSION,
            "cloud_inference_cache_key": self._cloud_inference_cache_key(),
            "document": asdict(document),
            "preflight_issues": [asdict(issue) for issue in preflight_issues],
            "narratives": [asdict(entry) for entry in narratives],
            "sheets": [asdict(sheet) for sheet in sheets],
            "clouds": [asdict(cloud) for cloud in clouds],
            "page_fingerprints": [stable_id(fingerprint, sheet.page_number, sheet.sheet_id) for sheet in sheets],
        }

    def _restore_review_state(self, items: list[ChangeItem]) -> list[ChangeItem]:
        previous_by_id = {item.id: item for item in self.previous_change_items}
        previous_by_key = {(item.sheet_id, item.detail_ref, item.normalized_text): item for item in self.previous_change_items}
        previous_by_cloud = {item.cloud_candidate_id: item for item in self.previous_change_items if item.cloud_candidate_id}
        restored: list[ChangeItem] = []
        restored_ids: set[str] = set()
        current_sheet_version_ids = {item.sheet_version_id for item in items}
        for item in items:
            previous = (
                previous_by_id.get(item.id)
                or previous_by_key.get((item.sheet_id, item.detail_ref, item.normalized_text))
                or previous_by_cloud.get(item.cloud_candidate_id or "")
            )
            if previous:
                item = replace(
                    item,
                    status=previous.status,
                    reviewer_text=previous.reviewer_text,
                    reviewer_notes=previous.reviewer_notes,
                    provenance=self._preserve_review_side_provenance(item, previous),
                    queue_order=previous.queue_order or item.queue_order,
                    parent_change_item_id=previous.parent_change_item_id,
                    superseded_by_change_item_ids=list(previous.superseded_by_change_item_ids),
                    superseded_reason=previous.superseded_reason,
                    superseded_at=previous.superseded_at,
                )
            restored.append(item)
            restored_ids.add(item.id)

        for previous in sorted(self.previous_change_items, key=review_queue_sort_key):
            if previous.id in restored_ids or previous.sheet_version_id not in current_sheet_version_ids:
                continue
            if not self._is_review_managed_item(previous):
                continue
            restored.append(previous)
            restored_ids.add(previous.id)
        return sorted(restored, key=review_queue_sort_key)

    def _preserve_review_side_provenance(self, item: ChangeItem, previous: ChangeItem) -> dict[str, object]:
        provenance = dict(item.provenance)
        previous_provenance = previous.provenance or {}
        for key in REVIEW_SIDE_PROVENANCE_KEYS:
            if key in previous_provenance:
                provenance[key] = previous_provenance[key]
        return provenance

    def _restore_review_managed_clouds(self, clouds: list[CloudCandidate], change_items: list[ChangeItem]) -> list[CloudCandidate]:
        clouds_by_id = {cloud.id: cloud for cloud in clouds}
        previous_clouds_by_id = {cloud.id: cloud for cloud in self.previous_clouds}
        restored = list(clouds)
        for item in change_items:
            if not item.cloud_candidate_id or item.cloud_candidate_id in clouds_by_id:
                continue
            if not self._is_review_managed_item(item):
                continue
            previous_cloud = previous_clouds_by_id.get(item.cloud_candidate_id)
            if previous_cloud is None:
                continue
            restored.append(previous_cloud)
            clouds_by_id[previous_cloud.id] = previous_cloud
        return restored

    def _is_review_managed_item(self, item: ChangeItem) -> bool:
        provenance = item.provenance or {}
        legend_payload = provenance.get("scopeledger.legend_context.v1")
        return bool(
            item.parent_change_item_id
            or provenance.get("scopeledger.geometry_correction.v1")
            or (isinstance(legend_payload, dict) and legend_payload.get("confirmed"))
        )

    def _is_narrative_page(self, text: str) -> bool:
        if not text:
            return False
        lower = text.lower()
        return (
            "instructions to contractor" in lower
            or "narrative page" in lower
            or "attachments:" in lower
        )

    def _parse_narrative_page(
        self,
        revision_set_id: str,
        source_pdf: str,
        page_number: int,
        text: str,
    ) -> list[NarrativeEntry]:
        entries: list[NarrativeEntry] = []
        current: dict[str, str] | None = None

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = re.match(
                r"^(?P<idx>\d+)\.\s+(?P<sheet>(?:GI|AD|AE|IN|PL|EL|EP|MP|MH|ME|E|M|S|SF|CS)\d{3}(?:\.\d+)?)\s+(?P<title>.+)$",
                line,
            )
            if match:
                if current:
                    entries.append(
                        NarrativeEntry(
                            id=stable_id(revision_set_id, source_pdf, page_number, current["sheet_id"], current["heading"]),
                            revision_set_id=revision_set_id,
                            source_pdf=source_pdf,
                            page_number=page_number,
                            sheet_id=current["sheet_id"],
                            heading=current["heading"],
                            summary=current["summary"].strip(),
                        )
                    )
                current = {
                    "sheet_id": match.group("sheet"),
                    "heading": match.group("title").strip(),
                    "summary": match.group("title").strip(),
                }
                continue

            if current and re.match(r"^[a-z]\.", line, re.IGNORECASE):
                current["summary"] += " " + line
            elif current and not re.match(r"^(Page \d+ of \d+|ATTACHMENTS:)", line, re.IGNORECASE):
                current["summary"] += " " + line

        if current:
            entries.append(
                NarrativeEntry(
                    id=stable_id(revision_set_id, source_pdf, page_number, current["sheet_id"], current["heading"]),
                    revision_set_id=revision_set_id,
                    source_pdf=source_pdf,
                    page_number=page_number,
                    sheet_id=current["sheet_id"],
                    heading=current["heading"],
                    summary=current["summary"].strip(),
                )
            )
        return entries

    def _extract_sheet_metadata(self, page: fitz.Page, text: str, pdf_path: Path | None = None) -> dict[str, object]:
        title_block_words = [
            word[4]
            for word in page.get_text("words")
            if word[0] >= page.rect.width * 0.64 and word[1] >= page.rect.height * 0.72
        ]
        title_block_text = " ".join(title_block_words)
        preferred_prefixes = _preferred_sheet_prefixes(pdf_path)
        sheet_id = choose_best_sheet_id(title_block_text) or choose_best_sheet_id(
            text,
            preferred_prefixes=preferred_prefixes,
            prefer_repeated=bool(preferred_prefixes),
        )

        issue_date = None
        issue_match = re.search(r"Issue Date[:\s]+(?P<date>\d{2}/\d{2}/\d{4})", text)
        if issue_match:
            issue_date = issue_match.group("date")
        else:
            dates = DATE_PATTERN.findall(title_block_text)
            if dates:
                issue_date = dates[0]

        sheet_title = sheet_id or "Unknown Sheet"
        if sheet_id:
            title_match = re.search(
                rf"{re.escape(sheet_id)}\s+(?P<title>.+?)(?:RENOVATE BUILDING|CONSTRUCTION DOCUMENTS|Checker|Author|[A-Z]{{2,4}}\s+\d+\s+\d+|NO\.\s+REVISIONS|1/\d+\"|$)",
                re.sub(r"\s+", " ", text),
                re.IGNORECASE,
            )
            if title_match:
                sheet_title = title_match.group("title").strip(" -")

        revision_entries = []
        revision_entries.extend(
            sorted(
                {
                    value.strip()
                    for value in re.findall(r"(Revision\s*#\s*[\w\-]+\s+\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
                }
            )
        )
        r_marker = re.findall(r"\(R\d+\s+\d{2}/\d{2}/\d{4}\)", text)
        revision_entries.extend(marker.strip("()") for marker in r_marker if marker.strip("()") not in revision_entries)

        return {
            "sheet_id": sheet_id,
            "sheet_title": re.sub(r"\s+", " ", sheet_title),
            "issue_date": issue_date,
            "revision_entries": revision_entries,
        }

    def _choose_revision_set_date(self, sheets: list[SheetVersion]) -> str | None:
        dates = [sheet.issue_date for sheet in sheets if sheet.issue_date]
        if not dates:
            return None
        return sorted(dates, key=parse_mmddyyyy)[-1]

    def _apply_supersedence(
        self,
        revision_sets: list[RevisionSet],
        sheets: list[SheetVersion],
    ) -> list[SheetVersion]:
        order_lookup = {revision_set.id: revision_set.set_number for revision_set in revision_sets}
        grouped: dict[str, list[SheetVersion]] = {}
        for sheet in sheets:
            grouped.setdefault(sheet.sheet_id, []).append(sheet)

        updated: list[SheetVersion] = []
        for versions in grouped.values():
            index_like_versions = [version for version in versions if sheet_is_index_like(version)]
            real_versions = [version for version in versions if not sheet_is_index_like(version)]
            if real_versions:
                for version in index_like_versions:
                    updated.append(replace(version, status="superseded"))
                versions = real_versions
            ranked = sorted(
                versions,
                key=lambda item: (
                    order_lookup.get(item.revision_set_id, 0),
                    parse_mmddyyyy(item.issue_date),
                    item.page_number,
                ),
            )
            for version in ranked[:-1]:
                updated.append(replace(version, status="superseded"))
            updated.append(replace(ranked[-1], status="active"))
        return sorted(updated, key=lambda item: (item.sheet_id, item.page_number))

    def _run_import_check(
        self,
        document_id: str,
        source_pdf: str,
        document: fitz.Document,
        page_index: int,
    ) -> list[PreflightIssue]:
        target = fitz.open()
        try:
            source_page = document[page_index]
            target_page = target.new_page(width=source_page.rect.width, height=source_page.rect.height)
            fitz.TOOLS.reset_mupdf_warnings()
            target_page.show_pdf_page(target_page.rect, document, page_index)
            return capture_preflight_issues(
                document_id=document_id,
                source_pdf=source_pdf,
                page_number=page_index + 1,
                operation="import_check",
                raw_warnings=fitz.TOOLS.mupdf_warnings(),
            )
        finally:
            target.close()

    def _detect_cloud_candidates(self, *, page: fitz.Page, sheet: SheetVersion) -> list[CloudCandidate]:
        """Delegate cloud detection to CloudHammer integration.

        The legacy OpenCV contour detector has been retired from the active
        scanner path. Until the local CloudHammer model is wired in, the
        default client returns no detections and the scanner relies on
        narrative/index-derived change records only.
        """

        if sheet_is_index_like(sheet):
            return []

        detections = self.cloud_inference_client.detect(page=page, sheet=sheet)
        candidates: list[CloudCandidate] = []
        for index, detection in enumerate(detections):
            cloud_id = stable_id(sheet.id, index, *detection.bbox)
            scope_result = extract_cloud_scope_text(page, sheet, [int(value) for value in detection.bbox])
            candidates.append(
                CloudCandidate(
                    id=cloud_id,
                    sheet_version_id=sheet.id,
                    bbox=[int(value) for value in detection.bbox],
                    image_path=detection.image_path,
                    page_image_path=detection.page_image_path or sheet.render_path,
                    confidence=round(float(detection.confidence), 3),
                    extraction_method=detection.extraction_method,
                    nearby_text=scope_result.text or detection.nearby_text,
                    detail_ref=detection.detail_ref or scope_result.detail_ref,
                    scope_text=scope_result.text,
                    scope_reason=scope_result.reason,
                    scope_signal=round(scope_result.signal, 3),
                    scope_method=scope_result.method,
                    metadata=dict(detection.metadata),
                )
            )
        return candidates

    def _signal_score(self, raw_text: str, sheet: SheetVersion) -> float:
        """Estimate whether a visual-region item carries useful scope text.

        Visual detections can exist before OCR/scope extraction is fully wired.
        The score is diagnostic only; it should not decide whether a cloud is
        exported.
        """

        text = normalize_text(raw_text)
        if not text:
            return 0.1
        if "cloudhammer detected revision cloud" in text or "detected revision region" in text:
            return 0.65
        if text.startswith("possible revision region"):
            return 0.25 if sheet.sheet_id.lower() in text else 0.2
        scope_terms = (
            "install",
            "replace",
            "remove",
            "repair",
            "provide",
            "modify",
            "relocate",
            "reroute",
            "patch",
            "infill",
            "connect",
        )
        score = 0.35
        if any(term in text for term in scope_terms):
            score += 0.35
        if parse_detail_ref(raw_text, sheet.sheet_id):
            score += 0.15
        if len(text) > 80:
            score += 0.1
        return min(1.0, score)

    def _generate_change_items(
        self,
        narratives: list[NarrativeEntry],
        sheets: list[SheetVersion],
        clouds: list[CloudCandidate],
    ) -> list[ChangeItem]:
        narratives_by_id = {entry.id: entry for entry in narratives}
        clouds_by_sheet: dict[str, list[CloudCandidate]] = {}
        for cloud in clouds:
            clouds_by_sheet.setdefault(cloud.sheet_version_id, []).append(cloud)

        unique: dict[tuple[str, str | None, str], ChangeItem] = {}
        for sheet in sheets:
            sheet_clouds = clouds_by_sheet.get(sheet.id, [])
            sheet_narratives = [narratives_by_id[narrative_id] for narrative_id in sheet.narrative_entry_ids if narrative_id in narratives_by_id]
            if sheet_narratives:
                for index, narrative in enumerate(sheet_narratives):
                    cloud = sheet_clouds[index] if index < len(sheet_clouds) else (sheet_clouds[0] if sheet_clouds else None)
                    detail_ref = parse_detail_ref(narrative.summary, sheet.sheet_id) or (cloud.detail_ref if cloud else None)
                    item = ChangeItem(
                        id=stable_id(sheet.id, narrative.id, detail_ref or "narrative"),
                        sheet_version_id=sheet.id,
                        cloud_candidate_id=cloud.id if cloud else None,
                        sheet_id=sheet.sheet_id,
                        detail_ref=detail_ref,
                        raw_text=narrative.summary,
                        normalized_text=normalize_text(narrative.summary),
                        provenance={
                            "source": "narrative",
                            "narrative_entry_id": narrative.id,
                            "cloud_candidate_id": cloud.id if cloud else None,
                            "extraction_signal": 1.0,
                        },
                    )
                    unique[(item.sheet_id, item.detail_ref, item.normalized_text)] = item

            visual_clouds = [cloud for cloud in sheet_clouds if cloud.extraction_method == "cloudhammer_manifest"] if sheet_narratives else sheet_clouds
            for cloud in visual_clouds:
                raw_text = cloud.nearby_text or (f"Possible revision region near {cloud.detail_ref}" if cloud.detail_ref else "Possible revision region")
                dedupe_key = (sheet.sheet_id, cloud.detail_ref, normalize_text(raw_text))
                if (
                    normalize_text(raw_text) == "possible revision region"
                    and any(key[0] == sheet.sheet_id and key[1] == cloud.detail_ref for key in unique)
                ):
                    continue
                item = ChangeItem(
                    id=stable_id(sheet.id, cloud.id, raw_text),
                    sheet_version_id=sheet.id,
                    cloud_candidate_id=cloud.id,
                    sheet_id=sheet.sheet_id,
                    detail_ref=cloud.detail_ref,
                    raw_text=raw_text,
                    normalized_text=normalize_text(raw_text),
                    provenance={
                        "source": "visual-region",
                        "cloud_candidate_id": cloud.id,
                        "extraction_method": cloud.extraction_method,
                        "extraction_signal": round(cloud.scope_signal or self._signal_score(raw_text, sheet), 3),
                        "scope_text_reason": cloud.scope_reason,
                        "scope_text_method": cloud.scope_method,
                        "scope_text_signal": cloud.scope_signal,
                        "cloud_confidence": cloud.confidence,
                        **cloud.metadata,
                    },
                )
                unique[dedupe_key] = item

        return sorted(unique.values(), key=legacy_review_sort_key)

