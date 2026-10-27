"""Explicit, owner-scoped default upgrades and immutable revision restore."""
from __future__ import annotations

import difflib
import hashlib

import asyncpg
from fastapi import HTTPException

from app.db.connection import get_db_pool
from app.skills.defaults import _bundled_methods, bundled_releases, ensure_default_methods
from app.skills.parser import parse_skill_markdown
from app.skills.service import _set_frontmatter_scalar, _write_skill_revision

MAX_LINES=4000
MAX_DIFF_CHARS=120000


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _catalog():
    return {meta.slug:markdown for meta,markdown,_,_ in _bundled_methods()}


def _normalize(text,enabled):
    text=_set_frontmatter_scalar(text,'version','1')
    return _set_frontmatter_scalar(text,'enabled','true' if enabled else 'false')


def _changes(base,other,side):
    matcher=difflib.SequenceMatcher(a=base,b=other,autojunk=True)
    return [(a,b,side,other[c:d]) for tag,a,b,c,d in matcher.get_opcodes() if tag!='equal']


def _merge(base_text,personal_text,target_text,enabled):
    """Three-way line merge; overlapping changes preserve the personal side."""
    base=_normalize(base_text,enabled).splitlines(keepends=True)
    personal=_normalize(personal_text,enabled).splitlines(keepends=True)
    target=_normalize(target_text,enabled).splitlines(keepends=True)
    if max(map(len,(base,personal,target)))>MAX_LINES:
        raise HTTPException(422,'skill_merge_too_large')
    changes=sorted(_changes(base,personal,'personal')+_changes(base,target,'default'),key=lambda x:(x[0],x[1],x[2]))
    result=[];conflicts=[];cursor=0;index=0
    while index<len(changes):
        start,end,_,_=changes[index];group=[changes[index]];index+=1
        while index<len(changes) and changes[index][0]<=end:
            change=changes[index];group.append(change);end=max(end,change[1]);index+=1
        result.extend(base[cursor:start])
        def side_result(side):
            parts=[];position=start
            for a,b,kind,replacement in group:
                if kind!=side:
                    continue
                parts.extend(base[position:a]);parts.extend(replacement);position=b
            parts.extend(base[position:end]);return parts
        original=base[start:end];mine=side_result('personal');incoming=side_result('default')
        if mine==original:
            result.extend(incoming)
        elif incoming==original or incoming==mine:
            result.extend(mine)
        else:
            result.extend(mine);conflicts.append({'start_line':start+1,'end_line':max(start+1,end)})
        cursor=end
    result.extend(base[cursor:])
    merged=''.join(result)
    parse_skill_markdown(merged)
    return merged,conflicts


def _diff(before,after):
    before_lines=before.splitlines(keepends=True);after_lines=after.splitlines(keepends=True)
    truncated=max(len(before_lines),len(after_lines))>MAX_LINES
    lines=list(difflib.unified_diff(before_lines[:MAX_LINES],after_lines[:MAX_LINES],
                                    fromfile='before',tofile='after',n=3))
    text=''.join(lines)
    return {'text':text[:MAX_DIFF_CHARS],'truncated':truncated or len(text)>MAX_DIFF_CHARS}


async def _snapshot(conn,owner_id,skill_id,*,lock=False):
    row=await conn.fetchrow('''SELECT m.id,m.slug,m.enabled,m.current_version,m.is_deleted,c.markdown_content
        FROM skill_meta m JOIN skill_content c ON c.skill_id=m.id AND c.version=m.current_version
        WHERE m.owner_id=$1::uuid AND m.id=$2::uuid'''+(' FOR UPDATE OF m' if lock else ''),owner_id,skill_id)
    if not row or row['is_deleted']:
        raise HTTPException(404,'Skill not found')
    origin=await conn.fetchrow('''SELECT * FROM skill_default_transitions WHERE owner_id=$1::uuid AND skill_id=$2::uuid
        AND personal_version<=$3 ORDER BY personal_version DESC LIMIT 1''',owner_id,skill_id,row['current_version'])
    if origin and origin['provenance']=='unlinked':
        origin=None
    return row,origin


async def describe_default(owner_id,skill_id):
    await ensure_default_methods(owner_id)
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        current,origin=await _snapshot(conn,owner_id,skill_id)
    catalog=_catalog();slug=origin['bundle_slug'] if origin else current['slug'];target=catalog.get(slug)
    data={'current_version':current['current_version'],'bundle_slug':slug if target or origin else None,
          'source_available':target is not None,
          'linked':bool(origin),'provenance':origin['provenance'] if origin else None,
          'base_hash':origin['baseline_hash'] if origin else None,'target_hash':_hash(target) if target else None,
          'base_release':origin['baseline_release'] if origin else None,'target_release':bundled_releases().get(slug) if target else None,
          'update_available':False,'personal_diff':None,'default_diff':None,'conflicts':[],'merge_error':None}
    if not target:
        try:
            if origin and origin['provenance']!='unverified':
                data['personal_diff']=_diff(_normalize(origin['baseline_markdown'],current['enabled']),_normalize(current['markdown_content'],current['enabled']))
        except (ValueError,HTTPException):
            data['merge_error']='skill_merge_invalid'
        return data
    enabled=current['enabled']
    data['update_available']=bool(origin and origin['provenance']!='unverified' and origin['baseline_hash']!=data['target_hash'])
    try:
        if not origin or origin['provenance']=='unverified':
            data['default_diff']=_diff(_normalize(current['markdown_content'],enabled),_normalize(target,enabled))
            return data
        base=origin['baseline_markdown'];personal=current['markdown_content']
        data['personal_diff']=_diff(_normalize(base,enabled),_normalize(personal,enabled))
        data['default_diff']=_diff(_normalize(base,enabled),_normalize(target,enabled))
        if data['update_available']:
            merged,conflicts=_merge(base,personal,target,enabled)
            metadata,_,_=parse_skill_markdown(merged)
            if metadata.slug!=current['slug']:
                raise HTTPException(422,'skill_merge_identity_changed')
            data['conflicts']=conflicts
    except (ValueError,HTTPException):
        data['merge_error']='skill_merge_invalid'
    return data


async def read_default_source(owner_id,skill_id):
    await ensure_default_methods(owner_id)
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        current,origin=await _snapshot(conn,owner_id,skill_id)
    slug=origin['bundle_slug'] if origin else current['slug']
    target=_catalog().get(slug)
    if target is None:
        raise HTTPException(404,'skill_default_missing')
    return {'bundle_slug':slug,'release':bundled_releases().get(slug),'markdown_content':target}


async def _transition(conn,owner_id,skill_id,version,slug,markdown,provenance,release=None):
    await conn.execute('''INSERT INTO skill_default_transitions
        (owner_id,skill_id,personal_version,bundle_slug,baseline_hash,baseline_markdown,provenance,baseline_release)
        VALUES($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8)''',owner_id,skill_id,version,slug,_hash(markdown) if markdown is not None else None,markdown,provenance,release)


async def associate_default(owner_id,skill_id,expected_version,slug,target_hash):
    target=_catalog().get(slug)
    if not target or _hash(target)!=target_hash:
        raise HTTPException(409,'skill_default_changed')
    pool=await get_db_pool()
    try:
        async with pool.acquire() as conn,conn.transaction():
            current,origin=await _snapshot(conn,owner_id,skill_id,lock=True)
            if current['current_version']!=expected_version:
                raise HTTPException(409,'skill_version_conflict')
            if origin and origin['provenance']!='unverified':
                raise HTTPException(409,'skill_default_already_linked')
            if slug!=(origin['bundle_slug'] if origin else current['slug']):
                raise HTTPException(409,'skill_default_changed')
            saved=await _write_skill_revision(conn,skill_id,current['markdown_content'],owner_id,expected_version)
            await _transition(conn,owner_id,skill_id,saved.metadata.version,slug,target,'associated',bundled_releases().get(slug))
            return saved
    except asyncpg.UniqueViolationError:
        raise HTTPException(409,'skill_version_or_slug_conflict') from None


async def upgrade_default(owner_id,skill_id,expected_version,base_hash,target_hash):
    pool=await get_db_pool()
    try:
        async with pool.acquire() as conn,conn.transaction():
            current,origin=await _snapshot(conn,owner_id,skill_id,lock=True)
            if current['current_version']!=expected_version:
                raise HTTPException(409,'skill_version_conflict')
            if not origin or origin['provenance']=='unverified' or origin['baseline_hash']!=base_hash:
                raise HTTPException(409,'skill_default_changed')
            target=_catalog().get(origin['bundle_slug'])
            if not target or _hash(target)!=target_hash or target_hash==base_hash:
                raise HTTPException(409,'skill_default_changed')
            merged,conflicts=_merge(origin['baseline_markdown'],current['markdown_content'],target,current['enabled'])
            metadata,_,_=parse_skill_markdown(merged)
            if metadata.slug!=current['slug']:
                raise HTTPException(422,'skill_merge_identity_changed')
            saved=await _write_skill_revision(conn,skill_id,merged,owner_id,expected_version)
            await _transition(conn,owner_id,skill_id,saved.metadata.version,origin['bundle_slug'],target,'upgraded',bundled_releases().get(origin['bundle_slug']))
            return saved,conflicts
    except asyncpg.UniqueViolationError:
        raise HTTPException(409,'skill_version_or_slug_conflict') from None


async def list_versions(owner_id,skill_id,before=None):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        current,_=await _snapshot(conn,owner_id,skill_id)
        rows=await conn.fetch('''SELECT version,created_at FROM skill_content WHERE skill_id=$1::uuid
            AND ($2::integer IS NULL OR version<$2) ORDER BY version DESC LIMIT 31''',skill_id,before)
    page=rows[:30]
    return {'current_version':current['current_version'],'items':[{'version':row['version'],
        'created_at':row['created_at'].isoformat(),'current':row['version']==current['current_version']} for row in page],
        'next_before':page[-1]['version'] if len(rows)>30 else None}


async def read_version(owner_id,skill_id,version):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        await _snapshot(conn,owner_id,skill_id)
        row=await conn.fetchrow('''SELECT version,markdown_content,created_at FROM skill_content
            WHERE skill_id=$1::uuid AND version=$2''',skill_id,version)
    if not row:
        raise HTTPException(404,'skill_version_not_found')
    return {'version':row['version'],'markdown_content':row['markdown_content'],'created_at':row['created_at'].isoformat()}


async def restore_version(owner_id,skill_id,version,expected_version):
    pool=await get_db_pool()
    try:
        async with pool.acquire() as conn,conn.transaction():
            current,_=await _snapshot(conn,owner_id,skill_id,lock=True)
            if current['current_version']!=expected_version:
                raise HTTPException(409,'skill_version_conflict')
            prior=await conn.fetchrow('SELECT markdown_content FROM skill_content WHERE skill_id=$1::uuid AND version=$2',skill_id,version)
            if not prior:
                raise HTTPException(404,'skill_version_not_found')
            source=await conn.fetchrow('''SELECT * FROM skill_default_transitions WHERE owner_id=$1::uuid AND skill_id=$2::uuid
                AND personal_version<=$3 ORDER BY personal_version DESC LIMIT 1''',owner_id,skill_id,version)
            markdown=_set_frontmatter_scalar(prior['markdown_content'],'enabled','true' if current['enabled'] else 'false')
            saved=await _write_skill_revision(conn,skill_id,markdown,owner_id,expected_version)
            if source:
                await _transition(conn,owner_id,skill_id,saved.metadata.version,source['bundle_slug'],source['baseline_markdown'],source['provenance'],source['baseline_release'])
            else:
                await _transition(conn,owner_id,skill_id,saved.metadata.version,None,None,'unlinked')
            return saved
    except asyncpg.UniqueViolationError:
        raise HTTPException(409,'skill_version_or_slug_conflict') from None
