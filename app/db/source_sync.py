"""Owner-scoped opt-in source subscriptions and durable run receipts."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS source_sync_subscriptions (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
    request_id UUID NOT NULL,
    request_fingerprint TEXT NOT NULL,
    name TEXT NOT NULL,
    group_name TEXT NOT NULL,
    url TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL CHECK (interval_seconds BETWEEN 900 AND 2592000),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    revision BIGINT NOT NULL DEFAULT 1,
    next_run_at TIMESTAMPTZ,
    source_id UUID,
    etag TEXT,
    last_modified TEXT,
    last_outcome TEXT,
    last_error TEXT,
    last_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_id, request_id),
    UNIQUE (owner_id, id)
);
CREATE INDEX IF NOT EXISTS idx_source_sync_due ON source_sync_subscriptions(next_run_at)
    WHERE enabled AND deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS source_sync_runs (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
    subscription_id UUID NOT NULL,
    request_id UUID NOT NULL,
    trigger_kind TEXT NOT NULL CHECK (trigger_kind IN ('manual','scheduled')),
    subscription_revision BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued','running','completed','failed','canceled')),
    attempts INTEGER NOT NULL DEFAULT 0,
    not_before TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deadline_at TIMESTAMPTZ NOT NULL,
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    outcome TEXT,
    error_category TEXT,
    source_id UUID,
    network_calls INTEGER NOT NULL DEFAULT 0,
    network_calls_unknown BOOLEAN NOT NULL DEFAULT FALSE,
    http_status INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_id, request_id),
    UNIQUE (owner_id, id),
    FOREIGN KEY (owner_id, subscription_id) REFERENCES source_sync_subscriptions(owner_id,id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_sync_one_active
    ON source_sync_runs(owner_id,subscription_id) WHERE status IN ('queued','running');
CREATE INDEX IF NOT EXISTS idx_source_sync_dispatch ON source_sync_runs(status,not_before,deadline_at);
CREATE INDEX IF NOT EXISTS idx_source_sync_owner_history ON source_sync_runs(owner_id,subscription_id,created_at DESC);
CREATE TABLE IF NOT EXISTS source_sync_network_receipts (
    owner_id UUID NOT NULL,
    run_id UUID NOT NULL,
    lease_token UUID NOT NULL,
    network_calls INTEGER NOT NULL CHECK(network_calls>=0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(owner_id,run_id,lease_token),
    FOREIGN KEY(owner_id,run_id) REFERENCES source_sync_runs(owner_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS source_sync_actions (
    owner_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
    request_id UUID NOT NULL,
    subscription_id UUID NOT NULL,
    fingerprint TEXT NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (owner_id,request_id),
    FOREIGN KEY (owner_id,subscription_id) REFERENCES source_sync_subscriptions(owner_id,id) ON DELETE CASCADE
);
"""
