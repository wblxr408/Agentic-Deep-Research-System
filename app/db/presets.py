"""Owner-bound immutable preference revisions on the existing PostgreSQL DB."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from pydantic import Field

from app.research_matching import WeightConfigurationRequest, preview_weights
from app.research_scope import Label, ScopeRecord

PRESET_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS organization_weight_presets (
    preset_id UUID NOT NULL,
    owner_id UUID NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    name TEXT NOT NULL,
    configuration JSONB NOT NULL,
    effective_configuration JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (preset_id, version)
);
CREATE INDEX IF NOT EXISTS idx_organization_presets_owner
    ON organization_weight_presets(owner_id, preset_id, version DESC);
"""


class PresetReference(ScopeRecord):
    preset_id: UUID
    version: int | None = Field(default=None, ge=1)


class PresetInput(ScopeRecord):
    name: Label
    configuration: WeightConfigurationRequest


class PresetUpdate(PresetInput):
    expected_version: int = Field(ge=1)


def preset_record(row) -> dict | None:
    if row is None:
        return None
    return {'preset_id': str(row['preset_id']), 'version': row['version'], 'name': row['name'],
            'configuration': json.loads(row['configuration']) if isinstance(row['configuration'], str) else row['configuration'],
            'effective_configuration': json.loads(row['effective_configuration']) if isinstance(row['effective_configuration'], str) else row['effective_configuration'],
            'created_at': row['created_at'].isoformat()}


async def load_preset(connection, owner_id: str, identifier: str, version: int | None = None):
    return preset_record(await connection.fetchrow(
        """SELECT * FROM organization_weight_presets
           WHERE preset_id=$1::uuid AND owner_id=$2::uuid AND ($3::integer IS NULL OR version=$3)
           ORDER BY version DESC LIMIT 1""", identifier, owner_id, version))


async def insert_preset(connection, owner_id: str, request: PresetInput, *, identifier: str | None = None, version: int = 1):
    effective = preview_weights(request.configuration)
    row = await connection.fetchrow(
        """INSERT INTO organization_weight_presets
           (preset_id,owner_id,version,name,configuration,effective_configuration)
           VALUES ($1::uuid,$2::uuid,$3,$4,$5::jsonb,$6::jsonb) RETURNING *""",
        identifier or str(uuid4()), owner_id, version, request.name,
        request.configuration.model_dump_json(), effective.model_dump_json())
    return preset_record(row)
