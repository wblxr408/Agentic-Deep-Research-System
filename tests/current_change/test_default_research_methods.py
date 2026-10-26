"""Only the new default-method distribution contract, against PostgreSQL.

Does not run other suites, create a research task, or invoke a model. Generated
non-login principals and their methods are removed in the same case's finally.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import asyncpg
import pytest

from app.config import get_settings
from app.db import connection
from app.skills.registry import SkillRegistry
from app.skills.service import (
    delete_skill, get_skill_by_id, list_skill_meta, update_skill,
)


@pytest.mark.asyncio
async def test_new_account_receives_private_defaults_once_and_keeps_its_choices(monkeypatch):
    pool = await asyncpg.create_pool(get_settings().database.url, min_size=1, max_size=3)
    monkeypatch.setattr(connection, '_db_pool', pool)
    owners = [str(uuid4()), str(uuid4())]
    try:
        async with pool.acquire() as conn:
            for owner in owners:
                await conn.execute(
                    "INSERT INTO auth_principals(id,username,password_hash,role) VALUES($1::uuid,$2,'!non-login-fixture','user')",
                    owner, 'default-method-case-' + owner,
                )
        initial, concurrent = await asyncio.gather(list_skill_meta(owners[0]), list_skill_meta(owners[0]))
        assert len(initial) == 45, 'A new account must immediately receive the 45 bundled research methods'
        assert {m.id for m in initial} == {m.id for m in concurrent}, 'Concurrent reads must produce one private copy'
        by_slug = {m.metadata.slug: m for m in initial}
        target = by_slug['bookshelf-literature-search-openalex']
        record = await get_skill_by_id(target.id, owners[0])
        personal_markdown = record.content.markdown_content.replace('enabled: true', 'enabled: false', 1) + '\n\nPersonal research convention.\n'
        changed = await update_skill(target.id, personal_markdown, owners[0])
        removed = by_slug['bookshelf-cover-letter']
        await delete_skill(removed.id, owners[0])

        again = await list_skill_meta(owners[0], include_deleted=True)
        assert len(again) == 45, 'Read after personal changes must not reseed deleted or disabled defaults'
        current = await get_skill_by_id(target.id, owners[0])
        assert current.meta.version == changed.meta.version and not current.metadata.enabled
        assert current.content.markdown_content == changed.content.markdown_content
        assert next(m for m in again if m.id == removed.id).is_deleted
        runtime = SkillRegistry(owners[0])
        await runtime.load()
        assert target.id not in {m.id for m in runtime.list_runtime_skills()}

        other = await list_skill_meta(owners[1])
        assert len(other) == 45
        assert not ({m.id for m in initial} & {m.id for m in other}), 'Default contents must have independent owner records'
        other_target = next(m for m in other if m.metadata.slug == target.metadata.slug)
        original = await get_skill_by_id(other_target.id, owners[1])
        assert original.metadata.enabled and 'Personal research convention.' not in original.content.markdown_content
    finally:
        async with pool.acquire() as conn:
            await conn.execute('DELETE FROM skill_meta WHERE owner_id=ANY($1::uuid[])', owners)
            await conn.execute('DELETE FROM auth_principals WHERE id=ANY($1::uuid[])', owners)
        await pool.close()
