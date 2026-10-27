from __future__ import annotations

import hashlib
import json
from typing import Any

import asyncpg
import yaml
from fastapi import HTTPException

from app.core.time import utc_now_naive
from app.db.connection import get_db_pool
from app.db.json import dumps_json
from app.skills.defaults import ensure_default_methods
from app.skills.models import (
    SkillContentRecord,
    SkillMetadata,
    SkillMetaRecord,
    SkillRecord,
)
from app.skills.parser import (
    derive_coarse_terms,
    FRONTMATTER_PATTERN,
    parse_skill_markdown,
)


async def ensure_skill_storage_bootstrapped() -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        meta_count = await conn.fetchval("SELECT COUNT(*) FROM skill_meta")
        if int(meta_count or 0) > 0:
            return
        legacy_owner = await conn.fetchval("SELECT id FROM auth_principals WHERE role='admin' ORDER BY created_at,id LIMIT 1")
        if legacy_owner is None:
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
                        coarse_terms_json, metadata_json, is_deleted, created_at, updated_at, owner_id
                    )
                    VALUES (
                        $1::uuid, $2, $3, $4, $5, $6, $7,
                        $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb,
                        $12::jsonb, $13, $14, $15, $16,
                        $17::jsonb, $18::jsonb, FALSE, $19, $20, $21::uuid
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
                    legacy_owner,
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
    raw_metadata = row['metadata_json']
    metadata_json = dict(json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata or {})
    metadata_json["version"] = int(row["current_version"])
    metadata = SkillMetadata.model_validate(metadata_json)
    return SkillMetaRecord(
        id=str(row["id"]),
        metadata=metadata,
        coarse_terms=list(json.loads(row['coarse_terms_json']) if isinstance(row['coarse_terms_json'], str) else row['coarse_terms_json'] or []),
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


async def list_skill_meta(owner_id: str, include_deleted: bool = False) -> list[SkillMetaRecord]:
    await ensure_skill_storage_bootstrapped()
    await ensure_default_methods(owner_id)
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
                WHERE owner_id = $1::uuid
                ORDER BY updated_at DESC, created_at DESC
                """, owner_id
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, slug, name, description, current_version, enabled, priority,
                       tags_json, keywords_json, trigger_patterns_json, allowed_tools_json,
                       agent_hints_json, domain, tenant_id, project_id, scope,
                       coarse_terms_json, metadata_json, is_deleted, created_at, updated_at
                FROM skill_meta
                WHERE is_deleted = FALSE AND owner_id = $1::uuid
                ORDER BY updated_at DESC, created_at DESC
                """, owner_id
            )
    return [_row_to_meta(row) for row in rows]


async def get_skill_meta_by_id(skill_id: str, owner_id: str) -> SkillMetaRecord:
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
            WHERE id = $1::uuid AND owner_id = $2::uuid
            """,
            skill_id,
            owner_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _row_to_meta(row)


async def get_skill_meta_by_slug(slug: str, owner_id: str) -> SkillMetaRecord | None:
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
            WHERE slug = $1 AND owner_id = $2::uuid
            """,
            slug,
            owner_id,
        )
    return _row_to_meta(row) if row else None


async def get_skill_content(skill_id: str, version: int, owner_id: str) -> SkillContentRecord:
    await ensure_skill_storage_bootstrapped()
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT content.skill_id, content.version, content.markdown_content, content.body, content.overview,
                   content.prompt, content.constraints, content.content_hash, content.created_at
            FROM skill_content content
            JOIN skill_meta meta ON meta.id = content.skill_id
            WHERE content.skill_id = $1::uuid AND content.version = $2 AND meta.owner_id = $3::uuid
            """,
            skill_id,
            version,
            owner_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Skill content not found")
    return _row_to_content(row)


async def get_skill_content_batch(skill_refs: list[tuple[str, int]], owner_id: str) -> dict[tuple[str, int], SkillContentRecord]:
    await ensure_skill_storage_bootstrapped()
    if not skill_refs:
        return {}
    pool = await get_db_pool()
    mapping: dict[tuple[str, int], SkillContentRecord] = {}
    async with pool.acquire() as conn:
        for skill_id, version in skill_refs:
            row = await conn.fetchrow(
                """
                SELECT content.skill_id, content.version, content.markdown_content, content.body, content.overview,
                       content.prompt, content.constraints, content.content_hash, content.created_at
                FROM skill_content content
                JOIN skill_meta meta ON meta.id = content.skill_id
                WHERE content.skill_id = $1::uuid AND content.version = $2 AND meta.owner_id = $3::uuid
                """,
                skill_id,
                version,
                owner_id,
            )
            if row:
                content = _row_to_content(row)
                mapping[(skill_id, version)] = content
    return mapping


async def get_skill_by_id(skill_id: str, owner_id: str) -> SkillRecord:
    meta = await get_skill_meta_by_id(skill_id, owner_id)
    content = await get_skill_content(skill_id, meta.version, owner_id)
    return SkillRecord(meta=meta, content=content)


async def create_skill(markdown_content: str, owner_id: str) -> SkillRecord:
    metadata, body, sections = parse_skill_markdown(markdown_content)
    existing = await get_skill_meta_by_slug(metadata.slug, owner_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Skill slug '{metadata.slug}' already exists")

    coarse_terms = derive_coarse_terms(metadata)
    now = utc_now_naive()
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO skill_meta (
                    slug, name, description, current_version, enabled, priority,
                    tags_json, keywords_json, trigger_patterns_json, allowed_tools_json,
                    agent_hints_json, domain, tenant_id, project_id, scope,
                    coarse_terms_json, metadata_json, owner_id, is_deleted, created_at, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6,
                    $7::jsonb, $8::jsonb, $9::jsonb, $10::jsonb,
                    $11::jsonb, $12, $13, $14, $15,
                    $16::jsonb, $17::jsonb, $18::uuid, FALSE, $19, $19
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
                owner_id,
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
    return SkillRecord(meta=_row_to_meta(row), content=await get_skill_content(str(row["id"]), metadata.version, owner_id))


def _set_frontmatter_scalar(markdown_content: str, key: str, value: str) -> str:
    """Change a top-level scalar without discarding personal YAML comments."""
    text=markdown_content.strip()
    match=FRONTMATTER_PATTERN.match(text)
    if not match:
        raise HTTPException(422,'invalid_skill_document')
    header=match.group(1)
    node=yaml.compose(header)
    if not isinstance(node,yaml.MappingNode):
        raise HTTPException(422,'invalid_skill_document')
    pairs=[(k,v) for k,v in node.value if isinstance(k,yaml.ScalarNode) and k.value==key]
    if pairs:
        k,v=pairs[-1]
        if not isinstance(v,yaml.ScalarNode) or v.start_mark.index<k.end_mark.index:
            raise HTTPException(422,'skill_frontmatter_scalar_not_editable')
        header=header[:v.start_mark.index]+value+header[v.end_mark.index:]
    elif node.flow_style:
        close=node.end_mark.index-1
        header=header[:close]+(', ' if node.value else '')+f'{json.dumps(key)}: {value}'+header[close:]
    else:
        header=header.rstrip()+f'\n{key}: {value}'
    return text[:match.start(1)]+header+text[match.end(1):]+'\n'


async def _write_skill_revision(conn, skill_id: str, markdown_content: str, owner_id: str,
                                expected_version: int | None = None) -> SkillRecord:
    existing=await conn.fetchrow('''SELECT current_version,is_deleted FROM skill_meta
        WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',skill_id,owner_id)
    if not existing or existing['is_deleted']:
        raise HTTPException(status_code=404,detail='Skill not found')
    if expected_version is not None and existing['current_version']!=expected_version:
        raise HTTPException(status_code=409,detail='skill_version_conflict')
    metadata, body, sections = parse_skill_markdown(markdown_content)
    conflict=await conn.fetchval('SELECT id FROM skill_meta WHERE slug=$1 AND owner_id=$2::uuid AND id<>$3::uuid',metadata.slug,owner_id,skill_id)
    if conflict:
        raise HTTPException(status_code=409,detail='skill_slug_conflict')
    next_version=max(metadata.version,existing['current_version']+1)
    markdown_content=_set_frontmatter_scalar(markdown_content,'version',str(next_version))
    metadata,body,sections=parse_skill_markdown(markdown_content)
    coarse_terms = derive_coarse_terms(metadata)
    now = utc_now_naive()
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
                WHERE id = $1::uuid AND owner_id = $20::uuid
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
                owner_id,
            )
    if not row:
        raise HTTPException(status_code=404, detail="Skill not found")
    content_row=await conn.fetchrow(
                """
                INSERT INTO skill_content (
                    skill_id, version, markdown_content, body, overview, prompt, constraints, content_hash, created_at
                )
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING skill_id,version,markdown_content,body,overview,prompt,constraints,content_hash,created_at
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
    return SkillRecord(meta=_row_to_meta(row),content=_row_to_content(content_row))


async def update_skill(skill_id: str, markdown_content: str, owner_id: str, *, expected_version: int | None = None) -> SkillRecord:
    await ensure_skill_storage_bootstrapped()
    pool=await get_db_pool()
    try:
        async with pool.acquire() as conn,conn.transaction():
            return await _write_skill_revision(conn,skill_id,markdown_content,owner_id,expected_version)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409,detail='skill_version_or_slug_conflict') from None


async def delete_skill(skill_id: str, owner_id: str) -> None:
    await ensure_skill_storage_bootstrapped()
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE skill_meta
            SET is_deleted = TRUE,
                enabled = FALSE,
                updated_at = $2
            WHERE id = $1::uuid AND owner_id = $3::uuid
            """,
            skill_id,
            utc_now_naive(),
            owner_id,
        )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="Skill not found")
