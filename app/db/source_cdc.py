"""Owner-bound transactional outbox feeds, event receipts and source mapping."""

SCHEMA_SQL="""
CREATE TABLE IF NOT EXISTS source_cdc_connections (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
    request_id UUID NOT NULL,
    request_fingerprint TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    endpoint_fingerprint TEXT NOT NULL,
    name TEXT NOT NULL,
    group_name TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL DEFAULT 60 CHECK(interval_seconds BETWEEN 30 AND 3600),
    credentials_encrypted TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    revision BIGINT NOT NULL DEFAULT 1,
    next_run_at TIMESTAMPTZ,
    snapshot_status TEXT NOT NULL DEFAULT 'not_observed',
    snapshot_id UUID,
    snapshot_rows BIGINT,
    snapshot_pending BIGINT,
    last_status TEXT,
    last_error TEXT,
    last_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(owner_id,id), UNIQUE(owner_id,request_id)
);
CREATE INDEX IF NOT EXISTS idx_source_cdc_due ON source_cdc_connections(next_run_at)
    WHERE enabled AND deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS source_cdc_entities (
    owner_id UUID NOT NULL,
    connection_id UUID NOT NULL,
    entity_key TEXT NOT NULL,
    latest_revision BIGINT NOT NULL,
    latest_fingerprint TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('active','deleted')),
    source_id UUID,
    PRIMARY KEY(owner_id,connection_id,entity_key),
    FOREIGN KEY(owner_id,connection_id) REFERENCES source_cdc_connections(owner_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS source_cdc_actions (
    owner_id UUID NOT NULL,
    connection_id UUID NOT NULL,
    request_id UUID NOT NULL,
    fingerprint TEXT NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(owner_id,request_id),
    FOREIGN KEY(owner_id,connection_id) REFERENCES source_cdc_connections(owner_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS source_cdc_events (
    owner_id UUID NOT NULL,
    connection_id UUID NOT NULL,
    event_id UUID NOT NULL,
    entity_key TEXT NOT NULL,
    source_revision BIGINT NOT NULL,
    operation TEXT NOT NULL,
    payload_fingerprint TEXT NOT NULL,
    payload JSONB,
    status TEXT NOT NULL CHECK(status IN ('applied','superseded','duplicate_version','blocked','retry_requested','skipped')),
    error_category TEXT,
    source_id UUID,
    source_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(owner_id,connection_id,event_id),
    FOREIGN KEY(owner_id,connection_id) REFERENCES source_cdc_connections(owner_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_source_cdc_event_state ON source_cdc_events(owner_id,connection_id,status,updated_at);
CREATE TABLE IF NOT EXISTS source_cdc_runs (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL,
    connection_id UUID NOT NULL,
    request_id UUID NOT NULL,
    trigger_kind TEXT NOT NULL CHECK(trigger_kind IN ('manual','scheduled')),
    connection_revision BIGINT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed','canceled')),
    deadline_at TIMESTAMPTZ NOT NULL,
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    error_category TEXT,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    applied_count INTEGER NOT NULL DEFAULT 0,
    acknowledged_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(owner_id,id), UNIQUE(owner_id,request_id),
    FOREIGN KEY(owner_id,connection_id) REFERENCES source_cdc_connections(owner_id,id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_cdc_one_active ON source_cdc_runs(owner_id,connection_id)
    WHERE status IN ('queued','running');
CREATE INDEX IF NOT EXISTS idx_source_cdc_dispatch ON source_cdc_runs(status,created_at,deadline_at);
"""
