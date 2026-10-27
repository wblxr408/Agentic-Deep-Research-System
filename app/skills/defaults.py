"""Bundled research methods become independent, editable owner records."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException

from app.core.time import utc_now_naive
from app.db.connection import get_db_pool
from app.db.json import dumps_json
from app.skills.parser import derive_coarse_terms, parse_skill_markdown
from app.skills.generation import bump_generation

_BUNDLE = Path(__file__).resolve().parents[2] / 'resources' / 'research-skills' / 'bookshelf'


@lru_cache(maxsize=1)
def _bundled_methods():
    manifest = json.loads((_BUNDLE / 'manifest.json').read_text(encoding='utf-8'))
    methods = []
    for item in manifest['items']:
        path = (_BUNDLE / item['file']).resolve()
        if path.parent != _BUNDLE or path.suffix != '.md':
            raise ValueError('invalid_bundled_method_path')
        markdown = path.read_text(encoding='utf-8')
        metadata, body, sections = parse_skill_markdown(markdown)
        if metadata.slug != item['slug'] or metadata.scope != 'global':
            raise ValueError('invalid_bundled_method_metadata')
        methods.append((metadata, markdown, body, sections))
    return tuple(methods)


@lru_cache(maxsize=1)
def bundled_releases():
    manifest=json.loads((_BUNDLE / 'manifest.json').read_text(encoding='utf-8'))
    return {item['slug']:str(item.get('release',{}).get('version') or item.get('source_version') or '')
            for item in manifest['items']}


async def ensure_default_methods(owner_id: str) -> None:
    # Parse the repository-owned bundle before beginning any writes. No downloads
    # or upstream programs are part of account initialization.
    methods = _bundled_methods()
    releases=bundled_releases()
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        # Multiple workers/requests initialize one principal atomically. Other
        # principals remain independent; normal edits use the same unique keys.
        owner = await conn.fetchval('SELECT id FROM auth_principals WHERE id=$1::uuid FOR NO KEY UPDATE', owner_id)
        if owner is None:
            raise HTTPException(status_code=401, detail='authentication_required')
        rows = await conn.fetch('SELECT id,slug FROM skill_meta WHERE owner_id=$1::uuid', owner_id)
        existing_slugs = {row['slug'] for row in rows}
        existing_ids = {str(row['id']) for row in rows}
        by_slug = {row['slug']:str(row['id']) for row in rows}
        linked={str(row['skill_id']) for row in await conn.fetch(
            'SELECT DISTINCT skill_id FROM skill_default_transitions WHERE owner_id=$1::uuid',owner_id)}
        now = utc_now_naive()
        changed=False
        for metadata, markdown, body, sections in methods:
            skill_id = str(uuid5(NAMESPACE_URL, f'adrs:research-default:{owner_id}:{metadata.slug}'))
            # Include tombstones and disabled/renamed copies. Never overwrite
            # personal source, recreate a deleted method, or undo a user choice.
            if metadata.slug in existing_slugs or skill_id in existing_ids:
                candidate=skill_id if skill_id in existing_ids else by_slug[metadata.slug]
                if candidate not in linked:
                    first=await conn.fetchrow('''SELECT version,markdown_content FROM skill_content
                        WHERE skill_id=$1::uuid ORDER BY version LIMIT 1''',candidate)
                    # A deterministic ID proves this was seeded, but if its
                    # initial bytes do not match the current bundle the prior
                    # upstream baseline cannot be authenticated automatically.
                    if first and (candidate==skill_id or first['markdown_content']==markdown):
                        initial=first['markdown_content']
                        await conn.execute('''INSERT INTO skill_default_transitions
                            (owner_id,skill_id,personal_version,bundle_slug,baseline_hash,baseline_markdown,provenance,baseline_release)
                            VALUES($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8) ON CONFLICT DO NOTHING''',
                            owner_id,candidate,first['version'],metadata.slug,hashlib.sha256(initial.encode('utf-8')).hexdigest(),
                            initial,'matched' if initial==markdown else 'unverified',releases.get(metadata.slug) if initial==markdown else None)
                        linked.add(candidate)
                continue
            inserted = await conn.fetchval(
                """INSERT INTO skill_meta (
                    id,slug,name,description,current_version,enabled,priority,
                    tags_json,keywords_json,trigger_patterns_json,allowed_tools_json,
                    agent_hints_json,domain,tenant_id,project_id,scope,
                    coarse_terms_json,metadata_json,owner_id,is_deleted,created_at,updated_at)
                VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10::jsonb,$11::jsonb,
                    $12::jsonb,$13,$14,$15,$16,$17::jsonb,$18::jsonb,$19::uuid,FALSE,$20,$20)
                ON CONFLICT DO NOTHING RETURNING id""",
                skill_id, metadata.slug, metadata.name, metadata.description,
                metadata.version, metadata.enabled, metadata.priority,
                dumps_json(metadata.tags), dumps_json(metadata.keywords),
                dumps_json(metadata.trigger_patterns), dumps_json(metadata.allowed_tools),
                dumps_json(metadata.agent_hints.model_dump()), metadata.domain,
                metadata.tenant_id, metadata.project_id, metadata.scope,
                dumps_json(derive_coarse_terms(metadata)), dumps_json(metadata.model_dump()), owner_id, now,
            )
            if inserted is not None:
                changed=True
                await conn.execute(
                    """INSERT INTO skill_content (
                        skill_id,version,markdown_content,body,overview,prompt,constraints,content_hash,created_at)
                    VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9)""",
                    inserted, metadata.version, markdown, body, sections.get('overview', ''),
                    sections.get('prompt', ''), sections.get('constraints', ''),
                    hashlib.sha256(markdown.encode('utf-8')).hexdigest(), now,
                )
                await conn.execute('''INSERT INTO skill_default_transitions
                    (owner_id,skill_id,personal_version,bundle_slug,baseline_hash,baseline_markdown,provenance,baseline_release)
                    VALUES($1::uuid,$2::uuid,$3,$4,$5,$6,'seeded',$7)''',owner_id,inserted,metadata.version,
                    metadata.slug,hashlib.sha256(markdown.encode('utf-8')).hexdigest(),markdown,releases.get(metadata.slug))
        if changed:
            await bump_generation(conn,owner_id)
