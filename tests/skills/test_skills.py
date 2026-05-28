from datetime import datetime
from fnmatch import fnmatch

import pytest

from app.skills.models import SkillContentRecord, SkillMetaRecord, SkillRecord
from app.skills.parser import derive_coarse_terms, parse_skill_markdown
from app.skills.registry import SkillRegistry
from app.skills.service import update_skill


SAMPLE_SKILL = """---
name: Finance Research
slug: finance-research
description: Focuses on financial research and tool constraints.
version: 1
enabled: true
priority: 200
tags:
  - finance
keywords:
  - earnings
domain: finance
trigger_patterns:
  - "财报"
  - "finance"
allowed_tools:
  - search
  - rag
agent_hints:
  planner: Prefer earnings, guidance, and filings.
  analyst: Highlight risk, guidance, and valuation.
---

# Overview
Financial domain research context.

# Prompt
Prefer listed-company disclosures and earnings material.

# Constraints
Do not use browser unless explicitly required by active skills.
"""


def _build_skill(
    skill_id: str,
    markdown: str = SAMPLE_SKILL,
):
    metadata, body, sections = parse_skill_markdown(markdown)
    now = datetime.utcnow()
    meta = SkillMetaRecord(
        id=skill_id,
        metadata=metadata,
        coarse_terms=derive_coarse_terms(metadata),
        created_at=now,
        updated_at=now,
        is_deleted=False,
    )
    content = SkillContentRecord(
        skill_id=skill_id,
        version=metadata.version,
        markdown_content=markdown,
        body=body,
        prompt=sections.get("prompt", ""),
        constraints=sections.get("constraints", ""),
        overview=sections.get("overview", ""),
        created_at=now,
    )
    return SkillRecord(meta=meta, content=content)


def test_parse_skill_markdown_extracts_frontmatter_and_sections():
    metadata, body, sections = parse_skill_markdown(SAMPLE_SKILL)

    assert metadata.slug == "finance-research"
    assert metadata.allowed_tools == ["search", "rag"]
    assert "Financial domain research context." in sections["overview"]
    assert "Prefer listed-company disclosures" in sections["prompt"]
    assert "Do not use browser" in sections["constraints"]
    assert "# Prompt" in body


@pytest.mark.asyncio
async def test_skill_registry_matches_and_merges_context():
    skill = _build_skill("00000000-0000-0000-0000-000000000001")
    meta = skill.meta
    content = skill.content

    registry = SkillRegistry()
    registry._meta_by_id = {meta.id: meta}
    registry._rebuild_indexes([meta])
    registry._remember_content(content)

    context = await registry.resolve_for_session(
        query="请分析这家公司的财报和 finance 指标",
        manually_enabled_skill_ids=[],
        manually_disabled_skill_ids=[],
    )

    assert context.auto_matched_skill_ids == [meta.id]
    assert context.effective_skill_ids == [meta.id]
    assert context.effective_tool_allowlist == ["search", "rag"]
    assert "Prefer listed-company disclosures" in context.effective_prompt_sections["prompt"]
    assert context.effective_agent_hints["planner"] == ["Prefer earnings, guidance, and filings."]
    assert context.resolved_skills[0].version == 1
    assert context.resolved_skills[0].prompt_sections["overview"] == "Financial domain research context."


@pytest.mark.asyncio
async def test_manual_enable_does_not_bypass_scope_filters():
    scoped_markdown = """---
name: Tenant Skill
slug: tenant-skill
description: Tenant scoped skill.
version: 1
enabled: true
priority: 180
tenant_id: tenant-a
project_id: project-a
scope: project
keywords:
  - restricted
allowed_tools:
  - search
---

# Overview
Scoped skill.
"""
    skill = _build_skill("00000000-0000-0000-0000-000000000010", scoped_markdown)
    registry = SkillRegistry()
    registry._meta_by_id = {skill.id: skill.meta}
    registry._rebuild_indexes([skill.meta])
    registry._remember_content(skill.content)

    context = await registry.resolve_for_session(
        query="restricted research",
        manually_enabled_skill_ids=[skill.id],
        manually_disabled_skill_ids=[],
        tenant_id="tenant-b",
        project_id="project-b",
    )

    assert context.effective_skill_ids == []
    assert context.resolved_skills == []


@pytest.mark.asyncio
async def test_update_skill_bumps_version_and_rewrites_markdown(monkeypatch):
    skill_id = "00000000-0000-0000-0000-000000000020"
    existing_markdown = SAMPLE_SKILL.replace("version: 1", "version: 3", 1)
    existing_skill = _build_skill(skill_id, existing_markdown)
    requested_markdown = SAMPLE_SKILL
    requested_metadata, requested_body, requested_sections = parse_skill_markdown(requested_markdown)
    captured: dict[str, str | int] = {}

    class _FakeTransaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _FakeConn:
        async def fetchrow(self, query, *args):
            next_version = args[4]
            next_metadata = requested_metadata.model_copy(update={"version": next_version})
            captured["next_version"] = next_version
            return {
                "id": skill_id,
                "slug": next_metadata.slug,
                "name": next_metadata.name,
                "description": next_metadata.description,
                "current_version": next_version,
                "enabled": next_metadata.enabled,
                "priority": next_metadata.priority,
                "tags_json": next_metadata.tags,
                "keywords_json": next_metadata.keywords,
                "trigger_patterns_json": next_metadata.trigger_patterns,
                "allowed_tools_json": next_metadata.allowed_tools,
                "agent_hints_json": next_metadata.agent_hints.model_dump(),
                "domain": next_metadata.domain,
                "tenant_id": next_metadata.tenant_id,
                "project_id": next_metadata.project_id,
                "scope": next_metadata.scope,
                "coarse_terms_json": derive_coarse_terms(next_metadata),
                "metadata_json": next_metadata.model_dump(),
                "is_deleted": False,
                "created_at": existing_skill.created_at,
                "updated_at": existing_skill.updated_at,
            }

        async def execute(self, query, *args):
            captured["stored_markdown"] = args[2]
            captured["stored_version"] = args[1]
            return "INSERT 0 1"

        def transaction(self):
            return _FakeTransaction()

        def acquire(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _FakePool:
        def acquire(self):
            return _FakeConn()

    async def _fake_get_skill_content(requested_skill_id: str, requested_version: int):
        stored_markdown = str(captured["stored_markdown"])
        _, body, sections = parse_skill_markdown(stored_markdown)
        return SkillContentRecord(
            skill_id=requested_skill_id,
            version=requested_version,
            markdown_content=stored_markdown,
            body=body,
            prompt=sections.get("prompt", ""),
            constraints=sections.get("constraints", ""),
            overview=sections.get("overview", ""),
            content_hash=None,
            created_at=existing_skill.created_at,
        )

    async def _fake_get_skill_meta_by_id(requested_skill_id: str):
        assert requested_skill_id == skill_id
        return existing_skill.meta

    async def _fake_get_skill_meta_by_slug(slug: str):
        assert slug == requested_metadata.slug
        return None

    async def _fake_get_db_pool():
        return _FakePool()

    monkeypatch.setattr("app.skills.service.get_skill_meta_by_id", _fake_get_skill_meta_by_id)
    monkeypatch.setattr("app.skills.service.get_skill_meta_by_slug", _fake_get_skill_meta_by_slug)
    monkeypatch.setattr("app.skills.service.get_db_pool", _fake_get_db_pool)
    monkeypatch.setattr("app.skills.service.get_skill_content", _fake_get_skill_content)

    updated_skill = await update_skill(skill_id, requested_markdown)

    assert captured["next_version"] == 4
    assert captured["stored_version"] == 4
    assert "version: 4" in str(captured["stored_markdown"])
    assert updated_skill.metadata.version == 4
    assert updated_skill.content.version == 4
    assert requested_sections["prompt"] in updated_skill.content.prompt


@pytest.mark.asyncio
async def test_registry_upsert_deindexes_old_terms_and_refreshes_match_cache():
    registry = SkillRegistry()
    original_skill = _build_skill("00000000-0000-0000-0000-000000000030")
    registry._meta_by_id = {original_skill.id: original_skill.meta}
    registry._rebuild_indexes([original_skill.meta])
    registry._remember_content(original_skill.content)

    original_context = await registry.resolve_for_session(
        query="finance earnings 财报",
        manually_enabled_skill_ids=[],
        manually_disabled_skill_ids=[],
    )

    updated_markdown = """---
name: Macro Research
slug: macro-research
description: Focuses on macro research and inflation.
version: 2
enabled: true
priority: 210
tags:
  - macro
keywords:
  - inflation
domain: macro
trigger_patterns:
  - "通胀"
  - "inflation"
allowed_tools:
  - search
agent_hints:
  planner: Prefer CPI, rates, and central bank material.
---

# Overview
Macro domain context.

# Prompt
Prefer inflation, rates, and central-bank sources.
"""
    updated_skill = _build_skill(original_skill.id, updated_markdown)
    await registry.upsert(updated_skill)

    stale_query_context = await registry.resolve_for_session(
        query="finance earnings 财报",
        manually_enabled_skill_ids=[],
        manually_disabled_skill_ids=[],
    )
    new_query_context = await registry.resolve_for_session(
        query="inflation 通胀",
        manually_enabled_skill_ids=[],
        manually_disabled_skill_ids=[],
    )

    assert original_context.effective_skill_ids == [original_skill.id]
    assert stale_query_context.effective_skill_ids == []
    assert stale_query_context.match_cache_key != original_context.match_cache_key
    assert new_query_context.effective_skill_ids == [original_skill.id]
    assert new_query_context.resolved_skills[0].version == 2
    assert new_query_context.resolved_skills[0].slug == "macro-research"


@pytest.mark.asyncio
async def test_get_skill_record_can_use_meta_l2_cache(monkeypatch):
    skill = _build_skill("00000000-0000-0000-0000-000000000040")

    class _FakeRedis:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        async def get(self, key: str):
            return self.store.get(key)

        async def set(self, key: str, value: str, ex: int | None = None):
            self.store[key] = value
            return True

        async def delete(self, *keys: str):
            for key in keys:
                self.store.pop(key, None)
            return len(keys)

        async def keys(self, pattern: str):
            return [key for key in self.store if fnmatch(key, pattern)]

    fake_redis = _FakeRedis()

    async def _fake_get_redis():
        return fake_redis

    async def _fail_get_skill_meta_by_id(skill_id: str):
        raise AssertionError(f"DB fallback should not be used for meta {skill_id}")

    async def _fake_get_skill_content(skill_id: str, version: int):
        assert skill_id == skill.id
        assert version == skill.metadata.version
        return skill.content

    monkeypatch.setattr("app.skills.registry.get_redis", _fake_get_redis)
    monkeypatch.setattr("app.skills.registry.get_skill_meta_by_id", _fail_get_skill_meta_by_id)
    monkeypatch.setattr("app.skills.registry.get_skill_content", _fake_get_skill_content)

    registry = SkillRegistry()
    await registry._cache_meta_l2(skill.meta)

    loaded_skill = await registry.get_skill_record(skill.id)

    assert loaded_skill.id == skill.id
    assert loaded_skill.metadata.slug == skill.metadata.slug
    assert loaded_skill.content.markdown_content == skill.content.markdown_content
    assert registry.get_meta_by_id(skill.id) is not None
