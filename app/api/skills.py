from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, ValidationError

from app.security.auth import Principal, require_principal
from app.skills import SkillCreateRequest, SkillUpdateRequest, get_skill_registry
from app.skills.service import create_skill, delete_skill, update_skill, list_skill_meta
from app.skills.parser import SkillParseError
from app.skills.versioning import associate_default, describe_default, list_versions, read_default_source, read_version, restore_version, upgrade_default

router = APIRouter(prefix="/api/v1/skills", tags=["skills"], dependencies=[Depends(require_principal)])
PrincipalDep = Annotated[Principal, Depends(require_principal)]
SkillUpload = Annotated[UploadFile, File(...)]


class DefaultChangeRequest(BaseModel):
    expected_version: int = Field(ge=1)
    target_hash: str = Field(min_length=64,max_length=64)
    base_hash: str | None = Field(default=None,min_length=64,max_length=64)
    bundle_slug: str | None = Field(default=None,min_length=1,max_length=120)


class RestoreRequest(BaseModel):
    expected_version: int = Field(ge=1)


def _runtime_payload(skill: Any) -> dict[str, Any]:
    return skill.to_runtime_view().model_dump()


async def _validated_skill_write(operation):
    try:
        return await operation
    except (SkillParseError, ValidationError):
        raise HTTPException(status_code=422, detail='invalid_skill_document: check stages, tools, reference IDs and unique instruction sections') from None


@router.get("")
async def get_skills(principal: PrincipalDep, include_disabled: bool = False):
    if include_disabled:
        # Management reads current owner metadata; execution retains its active registry.
        skills = await list_skill_meta(principal.id, include_deleted=False)
        return {"items": [skill.to_runtime_view().model_dump() for skill in skills]}
    registry = get_skill_registry(principal.id)
    await registry.ensure_loaded()
    skills = registry.list_runtime_skills()
    return {"items": [skill.to_runtime_view().model_dump() for skill in skills]}


@router.get("/{skill_id}")
async def get_skill(skill_id: str, principal: PrincipalDep):
    skill = await get_skill_registry(principal.id).get_skill_record(skill_id)
    if skill.is_deleted:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _runtime_payload(skill)


@router.get('/{skill_id}/default-update')
async def get_default_update(skill_id: str,principal: PrincipalDep):
    return await describe_default(principal.id,skill_id)


@router.get('/{skill_id}/default-source')
async def get_default_source(skill_id: str,principal: PrincipalDep):
    return await read_default_source(principal.id,skill_id)


@router.post('/{skill_id}/default-association')
async def associate_skill_default(skill_id: str,request: DefaultChangeRequest,principal: PrincipalDep):
    if not request.bundle_slug:
        raise HTTPException(422,'skill_default_missing')
    skill=await _validated_skill_write(associate_default(principal.id,skill_id,request.expected_version,request.bundle_slug,request.target_hash))
    await get_skill_registry(principal.id).load()
    return _runtime_payload(skill)


@router.post('/{skill_id}/default-update')
async def update_skill_default(skill_id: str,request: DefaultChangeRequest,principal: PrincipalDep):
    if not request.base_hash:
        raise HTTPException(422,'skill_default_missing')
    skill,conflicts=await _validated_skill_write(upgrade_default(principal.id,skill_id,request.expected_version,request.base_hash,request.target_hash))
    await get_skill_registry(principal.id).load()
    return {'skill':_runtime_payload(skill),'conflicts':conflicts}


@router.get('/{skill_id}/versions')
async def get_skill_versions(skill_id: str,principal: PrincipalDep,before: int | None=Query(default=None,ge=1)):
    return await list_versions(principal.id,skill_id,before)


@router.get('/{skill_id}/versions/{version}')
async def get_skill_version(skill_id: str,version:int,principal: PrincipalDep):
    if version<1:
        raise HTTPException(422,'skill_version_not_found')
    return await read_version(principal.id,skill_id,version)


@router.post('/{skill_id}/versions/{version}/restore')
async def restore_skill_version(skill_id: str,version:int,request:RestoreRequest,principal: PrincipalDep):
    if version<1:
        raise HTTPException(422,'skill_version_not_found')
    skill=await _validated_skill_write(restore_version(principal.id,skill_id,version,request.expected_version))
    await get_skill_registry(principal.id).load()
    return _runtime_payload(skill)


@router.post("")
async def create_skill_endpoint(request: SkillCreateRequest, principal: PrincipalDep):
    skill = await _validated_skill_write(create_skill(request.markdown_content, principal.id))
    await get_skill_registry(principal.id).load()
    return _runtime_payload(skill)


@router.post("/upload")
async def upload_skill(file: SkillUpload, principal: PrincipalDep):
    if not file.filename or not file.filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md skill files are supported")
    content = await file.read(4*65536+1)
    if len(content) > 4*65536:
        raise HTTPException(status_code=413, detail='skill_upload_too_large')
    try:
        markdown = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail='skill_requires_utf8') from None
    skill = await _validated_skill_write(create_skill(markdown, principal.id))
    await get_skill_registry(principal.id).load()
    return _runtime_payload(skill)


@router.put("/{skill_id}")
async def update_skill_endpoint(skill_id: str, request: SkillUpdateRequest, principal: PrincipalDep):
    skill = await _validated_skill_write(update_skill(skill_id, request.markdown_content, principal.id,expected_version=request.expected_version))
    await get_skill_registry(principal.id).load()
    return _runtime_payload(skill)


@router.delete("/{skill_id}")
async def delete_skill_endpoint(skill_id: str, principal: PrincipalDep):
    await delete_skill(skill_id, principal.id)
    await get_skill_registry(principal.id).load()
    return {"message": "Skill deleted"}
