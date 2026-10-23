"""Immutable owner-scoped matching evidence on the existing PostgreSQL database."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from app.research_matching import MatchingSnapshotInput

MATCHING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS research_matching_snapshots (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL,
    session_id UUID REFERENCES research_sessions(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_matching_snapshots_owner ON research_matching_snapshots(owner_id);
"""


async def save_matching_snapshot(connection, owner_id: str, snapshot: MatchingSnapshotInput) -> str | None:
    identifier = str(uuid4())
    session_id = str(snapshot.session_id) if snapshot.session_id else None
    row = await connection.fetchrow(
        """INSERT INTO research_matching_snapshots (id, owner_id, session_id, payload, created_at)
           SELECT $1::uuid, $2::uuid, $3::uuid, $4::jsonb, $5::timestamp
           WHERE $3::uuid IS NULL OR EXISTS (SELECT 1 FROM research_sessions WHERE id = $3::uuid AND owner_id = $2::uuid)
           RETURNING id""",
        identifier, owner_id, session_id, snapshot.model_dump_json(), datetime.now(UTC).replace(tzinfo=None),
    )
    return str(row["id"]) if row else None


async def load_matching_snapshot(connection, owner_id: str, identifier: str) -> MatchingSnapshotInput | None:
    row = await connection.fetchrow(
        """SELECT payload FROM research_matching_snapshots WHERE id = $1::uuid AND owner_id = $2::uuid
           AND (session_id IS NULL OR EXISTS (
               SELECT 1 FROM research_sessions s WHERE s.id = session_id AND s.owner_id = $2::uuid))""",
        identifier, owner_id,
    )
    if row is None:
        return None
    payload = row["payload"]
    return MatchingSnapshotInput.model_validate(json.loads(payload) if isinstance(payload, str) else payload)
