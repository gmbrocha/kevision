from __future__ import annotations

import re
from dataclasses import asdict, replace
from pathlib import Path

import fitz

from ..cloudhammer_client.inference import CloudInferenceClient, NullCloudInferenceClient
from ..diagnostics import capture_preflight_issues, configure_mupdf, summarize_documents
from ..workspace import WorkspaceStore
from ..utils import DATE_PATTERN, choose_best_sheet_id, clean_display_text, normalize_text, parse_detail_ref, parse_mmddyyyy, stable_id
from .models import ChangeItem, CloudCandidate, NarrativeEntry, PreflightIssue, RevisionSet, SheetVersion, SourceDocument

REVISION_FOLDER_PATTERN = re.compile(r"Revision\s*#(?P<number>\d+)", re.IGNORECASE)
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
        self.previous_change_items = list(self.store.data.change_items)
        self.previous_verifications = list(self.store.data.verifications)
        self.previous_scan_cache = dict(self.store.data.scan_cache.get("documents", {}))
        self.cache_hits = 0

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
        documents = summarize_documents(documents, preflight_issues)

        self.store.data.documents = documents
        self.store.data.preflight_issues = preflight_issues
        self.store.data.revision_sets = revision_sets
        self.store.data.narrative_entries = narratives
        self.store.data.sheets = sheets
        self.store.data.clouds = clouds
        self.store.data.change_items = change_items
        self.store.data.verifications = [record for record in self.previous_verifications if record.change_item_id in {item.id for item in change_items}]
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
        document = fitz.open(pdf_path)
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

                metadata = self._extract_sheet_metadata(page, text)
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
        restored: list[ChangeItem] = []
        for item in items:
            previous = previous_by_id.get(item.id) or previous_by_key.get((item.sheet_id, item.detail_ref, item.normalized_text))
            if previous:
                restored.append(
                    replace(
                        item,
                        status=previous.status,
                        reviewer_text=previous.reviewer_text,
                        reviewer_notes=previous.reviewer_notes,
                    )
                )
            else:
                restored.append(item)
        return restored

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

    def _extract_sheet_metadata(self, page: fitz.Page, text: str) -> dict[str, object]:
        title_block_words = [
            word[4]
            for word in page.get_text("words")
            if word[0] >= page.rect.width * 0.64 and word[1] >= page.rect.height * 0.72
        ]
        title_block_text = " ".join(title_block_words)
        sheet_id = choose_best_sheet_id(title_block_text) or choose_best_sheet_id(text)

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

        detections = self.cloud_inference_client.detect(page=page, sheet=sheet)
        candidates: list[CloudCandidate] = []
        for index, detection in enumerate(detections):
            cloud_id = stable_id(sheet.id, index, *detection.bbox)
            candidates.append(
                CloudCandidate(
                    id=cloud_id,
                    sheet_version_id=sheet.id,
                    bbox=[int(value) for value in detection.bbox],
                    image_path=detection.image_path,
                    page_image_path=detection.page_image_path or sheet.render_path,
                    confidence=round(float(detection.confidence), 3),
                    extraction_method=detection.extraction_method,
                    nearby_text=detection.nearby_text,
                    detail_ref=detection.detail_ref,
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
        if "cloudhammer detected revision cloud" in text:
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
                        "extraction_signal": round(self._signal_score(raw_text, sheet), 3),
                    },
                )
                unique[dedupe_key] = item

        return sorted(unique.values(), key=lambda item: (item.sheet_id, item.detail_ref or "", item.id))

