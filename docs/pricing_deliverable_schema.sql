CREATE TABLE revision_sets (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    set_number INTEGER NOT NULL,
    set_date TEXT,
    source_dir TEXT NOT NULL
);

CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    revision_set_id TEXT NOT NULL REFERENCES revision_sets(id),
    source_pdf TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL DEFAULT 0,
    issue_count INTEGER NOT NULL DEFAULT 0,
    max_severity TEXT NOT NULL DEFAULT 'ok'
);

CREATE TABLE sheet_versions (
    id TEXT PRIMARY KEY,
    revision_set_id TEXT NOT NULL REFERENCES revision_sets(id),
    document_id TEXT REFERENCES documents(id),
    source_pdf TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    sheet_id TEXT NOT NULL,
    sheet_title TEXT,
    issue_date TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
    superseded_by_sheet_version_id TEXT REFERENCES sheet_versions(id),
    render_path TEXT,
    is_latest_for_pricing INTEGER NOT NULL DEFAULT 0 CHECK (is_latest_for_pricing IN (0, 1))
);

CREATE INDEX idx_sheet_versions_sheet_id ON sheet_versions(sheet_id);
CREATE INDEX idx_sheet_versions_revision_set ON sheet_versions(revision_set_id);

CREATE TABLE pricing_changes (
    id TEXT PRIMARY KEY,
    sheet_version_id TEXT NOT NULL REFERENCES sheet_versions(id),
    sheet_id TEXT NOT NULL,
    detail_ref TEXT,
    detail_title TEXT,
    change_summary TEXT NOT NULL,
    pricing_status TEXT NOT NULL CHECK (pricing_status IN ('pending', 'approved', 'rejected')),
    needs_attention INTEGER NOT NULL DEFAULT 0 CHECK (needs_attention IN (0, 1)),
    source_kind TEXT NOT NULL CHECK (source_kind IN ('narrative', 'visual-region', 'manual')),
    extraction_signal REAL,
    superseded_by_change_id TEXT REFERENCES pricing_changes(id),
    is_latest_for_pricing INTEGER NOT NULL DEFAULT 1 CHECK (is_latest_for_pricing IN (0, 1)),
    reviewer_notes TEXT
);

CREATE INDEX idx_pricing_changes_sheet_id ON pricing_changes(sheet_id);
CREATE INDEX idx_pricing_changes_status ON pricing_changes(pricing_status);
CREATE INDEX idx_pricing_changes_latest ON pricing_changes(is_latest_for_pricing);

CREATE TABLE pricing_change_lines (
    id TEXT PRIMARY KEY,
    pricing_change_id TEXT NOT NULL REFERENCES pricing_changes(id),
    line_order INTEGER NOT NULL,
    scope_text TEXT NOT NULL
);

CREATE INDEX idx_pricing_change_lines_change ON pricing_change_lines(pricing_change_id, line_order);

CREATE TABLE change_sources (
    id TEXT PRIMARY KEY,
    pricing_change_id TEXT NOT NULL REFERENCES pricing_changes(id),
    revision_set_id TEXT NOT NULL REFERENCES revision_sets(id),
    sheet_version_id TEXT REFERENCES sheet_versions(id),
    raw_source_text TEXT,
    source_change_item_id TEXT,
    source_cloud_candidate_id TEXT,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('narrative', 'visual-region', 'manual')),
    confidence REAL
);

CREATE INDEX idx_change_sources_change ON change_sources(pricing_change_id);
CREATE INDEX idx_change_sources_revision_set ON change_sources(revision_set_id);

CREATE VIEW pricing_change_log AS
SELECT
    pc.id,
    sv.revision_set_id,
    pc.sheet_id,
    pc.detail_ref,
    pc.detail_title,
    pc.change_summary,
    pc.pricing_status,
    pc.needs_attention,
    pc.source_kind,
    pc.extraction_signal,
    pc.is_latest_for_pricing
FROM pricing_changes pc
JOIN sheet_versions sv ON sv.id = pc.sheet_version_id;
