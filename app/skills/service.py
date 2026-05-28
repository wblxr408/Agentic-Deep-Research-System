from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app.db.connection import get_db_pool
from app.db.json import dumps_json
from app.skills.models import SkillContentRecord, SkillMetaRecord, SkillMetadata, SkillRecord
from app.skills.parser import build_skill_markdown, derive_coarse_terms, parse_skill_markdown


async def ensure_skill_storage_bootstrapped() -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        meta_count = await conn.fetchval("SELECT COUNT(*) FROM skill_meta")
        if int(meta_count or 0) > 0:
            return

        legacy_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'skills'
            )
            """
        )
        if not legacy_exists:
            return

        rows = await conn.fetch(
            """
            SELECT id, markdown_content, metadata_json, is_deleted, created_at, updated_at
            FROM skills
            WHERE is_deleted = FALSE
            ORDER BY created_at ASC
            """
        )
        if not rows:
            return

        async with conn.transaction():
            for row in rows:
                metadata, body, sections = parse_skill_markdown(row["markdown_content"])
                coarse_terms = derive_coarse_terms(metadata)
                await conn.execute(
                    """
                    INSERT INTO skill_meta (
                        id, slug, name, description, current_version, enabled, priority,
                        tags_json, keywords_json, trigger_patterns_json, allowed_tools_json,
                        agent_hints_json, domain, tenant_id, project_id, scope,
                        coarse_terms_json, metadata_json, is_deleted, created_at, updated_at
                    )
                    VALUES (
                        $1::uuid, $2, $3, $4, $5, $6, $7,
                        $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb,
                        $12::jsonb, $13, $14, $15, $16,
                        $17::jsonb, $18::jsonb, FALSE, $19, $20
                    )
                    ON CONFLICT (id) DO NOTHING
                    """,
                    row["id"],
                    metadata.slug,
                    metadata.name,
                    metadata.description,
                    metadata.version,
                    metadata.enabled,
                    metadata.priority,
                    dumps_json(metadata.tags),
                    dumps_json(metadata.keywords),
                    dumps_json(metadata.trigger_patterns),
                    dumps_json(metadata.allowed_tools),
                    dumps_json(metadata.agent_hints.model_dump()),
                    metadata.domain,
                    metadata.tenant_id,
                    metadata.project_id,
                    metadata.scope,
                    dumps_json(coarse_terms),
                    dumps_json(metadata.model_dump()),
                    row["created_at"],
                    row["updated_at"],
                )
                await conn.execute(
                    """
                    INSERT INTO skill_content (
                        skill_id, version, markdown_content, body, overview, prompt, constraints, content_hash, created_at
                    )
                    VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (skill_id, version) DO NOTHING
                    """,
                    row["id"],
                    metadata.version,
                    row["markdown_content"],
                    body,
                    sections.get("overview", ""),
                    sections.get("prompt", ""),
                    sections.get("constraints", ""),
                    _content_hash(row["markdown_content"]),
                    row["created_at"],
                )


def _content_hash(markdown_content: str) -> str:
    return hashlib.sha256(markdown_content.encode("utf-8")).hexdigest()


def _row_to_meta(row: Any) -> SkillMetaRecord:
    metadata_json = dict(row["metadata_json"] or {})
    metadata_json["version"] = int(row["current_version"])
    metadata = SkillMetadata.model_validate(metadata_json)
    return SkillMetaRecord(
        id=str(row["id"]),
        metadata=metadata,
        coarse_terms=list(row["coarse_terms_json"] or []),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        is_deleted=bool(row["is_deleted"]),
    )


def _row_to_content(row: Any) -> SkillContentRecord:
    return SkillContentRecord(
        skill_id=str(row["skill_id"]),
        version=int(row["version"]),
        markdown_content=row["markdown_content"],
        body=row["body"],
        overview=row["overview"] or "",
        prompt=row["prompt"] or "",
        constraints=row["constraints"] or "",
        content_hash=row.get("content_hash"),
        created_at=row["created_at"],
    )


async def list_skill_meta(include_deleted: bool = False) -> list[SkillMetaRecord]:
    await ensure_skill_storage_bootstrapped()
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if include_deleted:
            rows = await conn.fetch(
                """
                SELECT id, slug, name, description, current_version, enabled, priority,
                       tags_json, keywords_json, trigger_patterns_json, allowed_tools_json,
                       agent_hints_json, domain, tenant_id, project_id, scope,
                       coarse_terms_json, metadata_json, is_deleted, created_at, updated_at
                FROM skill_meta
                ORDER BY updated_at DESC, created_at DESC
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, slug, name, description, current_version, enabled, priority,
                       tags_json, keywords_json, trigger_patterns_json, allowed_tools_json,
                       agent_hints_json, domain, tenant_id, project_id, scope,
                       coarse_terms_json, metadata_json, is_deleted, created_at, updated_at
                FROM skill_meta
                WHERE is_deleted = FALSE
                ORDER BY updated_at DESC, created_at DESC
                """
            )
    return [_row_to_meta(row) for row in rows]


async def get_skill_meta_by_id(skill_id: str) -> SkillMetaRecord:
    await ensure_skill_storage_bootstrapped()
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, slug, name, description, current_version, enabled, priority,
                   tags_json, keywords_json, trigger_patterns_json, allowed_tools_json,
                   agent_hints_json, domain, tenant_id, project_id, scope,
                   coarse_terms_json, metadata_json, is_deleted, created_at, updated_at
            FROM skill_meta
            WHERE id = $1::uuid
            """,
            skill_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _row_to_meta(row)


async def get_skill_meta_by_slug(slug: str) -> SkillMetaRecord | None:
    await ensure_skill_storage_bootstrapped()
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, slug, name, description, current_version, enabled, priority,
                   tags_json, keywords_json, trigger_patterns_json, allowed_tools_json,
                   agent_hints_json, domain, tenant_id, project_id, scope,
                   coarse_terms_json, metadata_json, is_deleted, created_at, updated_at
            FROM skill_meta
            WHERE slug = $1
            """,
            slug,
        )
    return _row_to_meta(row) if row else None


async def get_skill_content(skill_id: str, version: int) -> SkillContentRecord:
    await ensure_skill_storage_bootstrapped()
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT skill_id, version, markdown_content, body, overview, prompt, constraints, content_hash, created_at
            FROM skill_content
            WHERE skill_id = $1::uuid AND version = $2
            """,
            skill_id,
            version,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Skill content not found")
    return _row_to_content(row)


async def get_skill_content_batch(skill_refs: list[tuple[str, int]]) -> dict[tuple[str, int], SkillContentRecord]:
    await ensure_skill_storage_bootstrapped()
    if not skill_refs:
        return {}
    pool = await get_db_pool()
    mapping: dict[tuple[str, int], SkillContentRecord] = {}
    async with pool.acquire() as conn:
        for skill_id, version in skill_refs:
            row = await conn.fetchrow(
                """
                SELECT skill_id, version, markdown_content, body, overview, prompt, constraints, content_hash, created_at
                FROM skill_content
                WHERE skill_id = $1::uuid AND version = $2
                """,
                skill_id,
                version,
            )
            if row:
                content = _row_to_content(row)
                mapping[(skill_id, version)] = content
    return mapping


async def get_skill_by_id(skill_id: str) -> SkillRecord:
    meta = await get_skill_meta_by_id(skill_id)
    content = await get_skill_content(skill_id, meta.version)
    return SkillRecord(meta=meta, content=content)


async def create_skill(markdown_content: str) -> SkillRecord:
    metadata, body, sections = parse_skill_markdown(markdown_content)
    existing = await get_skill_meta_by_slug(metadata.slug)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Skill slug '{metadata.slug}' already exists")

    coarse_terms = derive_coarse_terms(metadata)
    now = datetime.utcnow()
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO skill_meta (
                    slug, name, description, current_version, enabled, priority,
                    tags_json, keywords_json, trigger_patterns_json, allowed_tools_json,
                    agent_hints_json, domain, tenant_id, project_id, scope,
                    coarse_terms_json, metadata_json, is_deleted, created_at, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6,
                    $7::jsonb, $8::jsonb, $9::jsonb, $10::jsonb,
                    $11::jsonb, $12, $13, $14, $15,
                    $16::jsonb, $17::jsonb, FALSE, $18, $18
                )
                RETURNING id, slug, name, description, current_version, enabled, priority,
                          tags_json, keywords_json, trigger_patterns_json, allowed_tools_json,
                          agent_hints_json, domain, tenant_id, project_id, scope,
                          coarse_terms_json, metadata_json, is_deleted, created_at, updated_at
                """,
                metadata.slug,
                metadata.name,
                metadata.description,
                metadata.version,
                metadata.enabled,
                metadata.priority,
                dumps_json(metadata.tags),
                dumps_json(metadata.keywords),
                dumps_json(metadata.trigger_patterns),
                dumps_json(metadata.allowed_tools),
                dumps_json(metadata.agent_hints.model_dump()),
                metadata.domain,
                metadata.tenant_id,
                metadata.project_id,
                metadata.scope,
                dumps_json(coarse_terms),
                dumps_json(metadata.model_dump()),
                now,
            )
            await conn.execute(
                """
                INSERT INTO skill_content (
                    skill_id, version, markdown_content, body, overview, prompt, constraints, content_hash, created_at
                )
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                row["id"],
                metadata.version,
                markdown_content,
                body,
                sections.get("overview", ""),
                sections.get("prompt", ""),
                sections.get("constraints", ""),
                _content_hash(markdown_content),
                now,
            )
    return SkillRecord(meta=_row_to_meta(row), content=await get_skill_content(str(row["id"]), metadata.version))


async def update_skill(skill_id: str, markdown_content: str) -> SkillRecord:
    existing = await get_skill_meta_by_id(skill_id)
    metadata, body, sections = parse_skill_markdown(markdown_content)
    slug_conflict = await get_skill_meta_by_slug(metadata.slug)
    if slug_conflict is not None and slug_conflict.id != skill_id:
        raise HTTPException(status_code=409, detail=f"Skill slug '{metadata.slug}' already exists")

    next_version = max(metadata.version, existing.version + 1)
    if next_version != metadata.version:
        metadata = metadata.model_copy(update={"version": next_version})
        markdown_content = build_skill_markdown(
            metadata=metadata.model_dump(),
            body=body,
        )

    coarse_terms = derive_coarse_terms(metadata)
    now = datetime.utcnow()
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE skill_meta
                SET slug = $2,
                    name = $3,
                    description = $4,
                    current_version = $5,
                    enabled = $6,
                    priority = $7,
                    tags_json = $8::jsonb,
                    keywords_json = $9::jsonb,
                    trigger_patterns_json = $10::jsonb,
                    allowed_tools_json = $11::jsonb,
                    agent_hints_json = $12::jsonb,
                    domain = $13,
                    tenant_id = $14,
                    project_id = $15,
                    scope = $16,
                    coarse_terms_json = $17::jsonb,
                    metadata_json = $18::jsonb,
                    is_deleted = FALSE,
                    updated_at = $19
                WHERE id = $1::uuid
                RETURNING id, slug, name, description, current_version, enabled, priority,
                          tags_json, keywords_json, trigger_patterns_json, allowed_tools_json,
                          agent_hints_json, domain, tenant_id, project_id, scope,
                          coarse_terms_json, metadata_json, is_deleted, created_at, updated_at
                """,
                skill_id,
                metadata.slug,
                metadata.name,
                metadata.description,
                next_version,
                metadata.enabled,
                metadata.priority,
                dumps_json(metadata.tags),
                dumps_json(metadata.keywords),
                dumps_json(metadata.trigger_patterns),
                dumps_json(metadata.allowed_tools),
                dumps_json(metadata.agent_hints.model_dump()),
                metadata.domain,
                metadata.tenant_id,
                metadata.project_id,
                metadata.scope,
                dumps_json(coarse_terms),
                dumps_json(metadata.model_dump()),
                now,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Skill not found")
            await conn.execute(
                """
                INSERT INTO skill_content (
                    skill_id, version, markdown_content, body, overview, prompt, constraints, content_hash, created_at
                )
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (skill_id, version) DO UPDATE SET
                    markdown_content = EXCLUDED.markdown_content,
                    body = EXCLUDED.body,
                    overview = EXCLUDED.overview,
                    prompt = EXCLUDED.prompt,
                    constraints = EXCLUDED.constraints,
                    content_hash = EXCLUDED.content_hash
                """,
                skill_id,
                next_version,
                markdown_content,
                body,
                sections.get("overview", ""),
                sections.get("prompt", ""),
                sections.get("constraints", ""),
                _content_hash(markdown_content),
                now,
            )
    return SkillRecord(meta=_row_to_meta(row), content=await get_skill_content(skill_id, next_version))


async def delete_skill(skill_id: str) -> None:
    await ensure_skill_storage_bootstrapped()
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE skill_meta
            SET is_deleted = TRUE,
                enabled = FALSE,
                updated_at = $2
            WHERE id = $1::uuid
            """,
            skill_id,
            datetime.utcnow(),
        )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="Skill not found")
