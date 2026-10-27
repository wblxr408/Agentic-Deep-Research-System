"""Owner-scoped, version-bound model processing receipts and observations."""

SCHEMA_SQL="""
CREATE TABLE IF NOT EXISTS document_processing_operations (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES document_sources(id) ON DELETE CASCADE,
    request_id UUID NOT NULL,
    request_fingerprint TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('vision','cleaning','semantic_comparison','entity_extraction')),
    parse_version TEXT NOT NULL,
    lifecycle_revision BIGINT NOT NULL,
    model_provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_config_version TEXT NOT NULL,
    input_description JSONB NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('preparing','running','completed','failed','canceled','interrupted')),
    dispatch_attempted BOOLEAN NOT NULL DEFAULT FALSE,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    accepted BOOLEAN NOT NULL DEFAULT FALSE,
    accepted_at TIMESTAMPTZ,
    result JSONB,
    usage JSONB,
    error_category TEXT,
    deadline_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(owner_id,id),UNIQUE(owner_id,request_id)
);
ALTER TABLE document_processing_operations ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE document_processing_operations ADD COLUMN IF NOT EXISTS accepted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE document_processing_operations ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;
ALTER TABLE document_processing_operations DROP CONSTRAINT IF EXISTS document_processing_operations_kind_check;
ALTER TABLE document_processing_operations ADD CONSTRAINT document_processing_operations_kind_check
    CHECK(kind IN ('vision','cleaning','semantic_comparison','entity_extraction'));
CREATE UNIQUE INDEX IF NOT EXISTS idx_document_processing_active_source
    ON document_processing_operations(owner_id,source_id) WHERE status IN ('preparing','running');
CREATE INDEX IF NOT EXISTS idx_document_processing_recent
    ON document_processing_operations(owner_id,source_id,created_at DESC);
"""
