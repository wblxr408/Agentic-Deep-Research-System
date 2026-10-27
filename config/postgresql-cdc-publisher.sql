-- Install only in a source database explicitly administered for this feed.
-- Map the application's approved content into adrs_cdc.source_documents.
-- The trigger publishes changes in the same transaction as each row change.
CREATE SCHEMA IF NOT EXISTS adrs_cdc;
REVOKE CREATE ON SCHEMA adrs_cdc FROM PUBLIC;

CREATE TABLE IF NOT EXISTS adrs_cdc.source_documents (
    document_key TEXT PRIMARY KEY CHECK (length(document_key) BETWEEN 1 AND 200),
    title TEXT NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS adrs_cdc.entity_versions (
    document_key TEXT PRIMARY KEY,
    revision BIGINT NOT NULL CHECK (revision > 0)
);
CREATE TABLE IF NOT EXISTS adrs_cdc.snapshots (
    snapshot_id UUID PRIMARY KEY,
    row_count BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS adrs_cdc.events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_key TEXT NOT NULL,
    revision BIGINT NOT NULL CHECK (revision > 0),
    operation TEXT NOT NULL CHECK (operation IN ('upsert','delete')),
    title TEXT,
    content TEXT,
    is_snapshot BOOLEAN NOT NULL DEFAULT FALSE,
    snapshot_id UUID REFERENCES adrs_cdc.snapshots(snapshot_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE adrs_cdc.events ADD COLUMN IF NOT EXISTS snapshot_id UUID REFERENCES adrs_cdc.snapshots(snapshot_id);
CREATE INDEX IF NOT EXISTS adrs_cdc_events_order ON adrs_cdc.events(created_at,event_id);
CREATE INDEX IF NOT EXISTS adrs_cdc_events_snapshot ON adrs_cdc.events(snapshot_id,event_id);
CREATE TABLE IF NOT EXISTS adrs_cdc.acknowledgments (
    consumer_id UUID NOT NULL,
    event_id UUID NOT NULL REFERENCES adrs_cdc.events(event_id) ON DELETE CASCADE,
    acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(consumer_id,event_id)
);

CREATE OR REPLACE FUNCTION adrs_cdc.publish_document_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, adrs_cdc AS $$
DECLARE item_key TEXT; next_revision BIGINT;
BEGIN
    IF TG_OP='UPDATE' AND NEW.document_key IS DISTINCT FROM OLD.document_key THEN
        RAISE EXCEPTION 'document_key is immutable';
    END IF;
    item_key := CASE WHEN TG_OP='DELETE' THEN OLD.document_key ELSE NEW.document_key END;
    INSERT INTO adrs_cdc.entity_versions(document_key,revision) VALUES(item_key,1)
        ON CONFLICT(document_key) DO UPDATE SET revision=adrs_cdc.entity_versions.revision+1
        RETURNING revision INTO next_revision;
    INSERT INTO adrs_cdc.events(document_key,revision,operation,title,content)
        VALUES(item_key,next_revision,CASE WHEN TG_OP='DELETE' THEN 'delete' ELSE 'upsert' END,
            CASE WHEN TG_OP='DELETE' THEN NULL ELSE NEW.title END,
            CASE WHEN TG_OP='DELETE' THEN NULL ELSE NEW.content END);
    IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$;
DROP TRIGGER IF EXISTS adrs_cdc_publish ON adrs_cdc.source_documents;
CREATE TRIGGER adrs_cdc_publish AFTER INSERT OR UPDATE OR DELETE ON adrs_cdc.source_documents
    FOR EACH ROW EXECUTE FUNCTION adrs_cdc.publish_document_change();

CREATE OR REPLACE FUNCTION adrs_cdc.reject_truncate() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, adrs_cdc AS $$
BEGIN
    RAISE EXCEPTION 'TRUNCATE is not captured; use explicit DELETE';
END;
$$;
DROP TRIGGER IF EXISTS adrs_cdc_no_truncate ON adrs_cdc.source_documents;
CREATE TRIGGER adrs_cdc_no_truncate BEFORE TRUNCATE ON adrs_cdc.source_documents
    FOR EACH STATEMENT EXECUTE FUNCTION adrs_cdc.reject_truncate();

-- An operator may call this explicitly after installing the trigger. The table
-- lock gives this bootstrap a consistent boundary with concurrent writes.
CREATE OR REPLACE FUNCTION adrs_cdc.capture_snapshot() RETURNS BIGINT
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, adrs_cdc AS $$
DECLARE inserted BIGINT; snapshot_uuid UUID := gen_random_uuid();
BEGIN
    LOCK TABLE adrs_cdc.source_documents IN SHARE ROW EXCLUSIVE MODE;
    INSERT INTO adrs_cdc.entity_versions(document_key,revision)
        SELECT document_key,1 FROM adrs_cdc.source_documents ON CONFLICT(document_key) DO NOTHING;
    INSERT INTO adrs_cdc.snapshots(snapshot_id,row_count)
        SELECT snapshot_uuid,COUNT(*) FROM adrs_cdc.source_documents;
    INSERT INTO adrs_cdc.events(document_key,revision,operation,title,content,is_snapshot,snapshot_id)
        SELECT d.document_key,v.revision,'upsert',d.title,d.content,TRUE,snapshot_uuid
        FROM adrs_cdc.source_documents d JOIN adrs_cdc.entity_versions v USING(document_key);
    GET DIAGNOSTICS inserted = ROW_COUNT;
    RETURN inserted;
END;
$$;
REVOKE ALL ON FUNCTION adrs_cdc.publish_document_change() FROM PUBLIC;
REVOKE ALL ON FUNCTION adrs_cdc.reject_truncate() FROM PUBLIC;
REVOKE ALL ON FUNCTION adrs_cdc.capture_snapshot() FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA adrs_cdc FROM PUBLIC;

-- An administrator grants a dedicated reader only USAGE on this schema,
-- SELECT on events, snapshots and acknowledgments, and INSERT on acknowledgments.
-- Do not grant the reader ownership, trigger, DELETE, or replication rights.
