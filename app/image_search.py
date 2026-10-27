"""Owner-scoped text-to-image and reference-image discovery."""
from __future__ import annotations

import asyncio
import json
import math
import time
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field,model_validator

from app.channels.models import ChannelError
from app.db.connection import get_db_pool
from app.db.retrieval_image import has_image_model,list_images,reference_image,source_image_candidates
from app.multimodal import configuration,encode_text_query
from app.research_scope import ScopeRecord


class ImageSearchRequest(ScopeRecord):
    query:str|None=Field(default=None,min_length=1,max_length=4000)
    reference_operation_id:UUID|None=None
    group_name:str|None=Field(default=None,min_length=1,max_length=100)
    task_id:UUID|None=None
    limit:int=Field(default=20,ge=1,le=50)

    @model_validator(mode='after')
    def one_query(self):
        if bool(self.query and self.query.strip())==bool(self.reference_operation_id):raise ValueError('image_search_requires_text_or_reference')
        return self


def _json(value):
    value=json.loads(value) if isinstance(value,str) else value
    return value if isinstance(value,dict) else {}


async def _validate_task(conn,owner,task_id):
    if task_id and not await conn.fetchval('SELECT id FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid',str(task_id),str(owner)):
        raise HTTPException(404,'image_search_task_unavailable')


def _public(row):
    record=dict(row)
    return {'operation_id':str(row['operation_id']),'source_id':str(row['source_id']),'source_name':row['name'],
        'group_name':row['group_name'],'selection':_json(row['selection']),'source_version':row['source_version'],
        'generation_id':str(row['generation_id']),'source_revision':row['revision'],'has_preview':record.get('has_preview',False),
        'source_text_range':_json(row['source_text_range']) if row['source_text_range'] else None}


async def browse(owner,group,task_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        await _validate_task(conn,owner,task_id)
        rows=await list_images(conn,owner,group,task_id)
    return {'items':[_public(row) for row in rows[:100]],'has_more':len(rows)>100}


async def search(owner,request):
    pool=await get_db_pool();group=request.group_name.strip() if request.group_name else None
    if request.group_name is not None and not group:raise HTTPException(422,'image_search_group_invalid')
    deadline=time.monotonic()+60
    async with pool.acquire() as conn:
        await _validate_task(conn,owner,request.task_id)
        if request.reference_operation_id:
            reference=await reference_image(conn,owner,group,request.task_id,request.reference_operation_id)
            if not reference:raise HTTPException(404,'image_search_reference_unavailable')
            profile=_json(reference['model_profile']);encoded={'vector':reference['image_vector'],
                'dimension':reference['dimension'],'profile':profile}
        else:
            try:config=configuration()
            except ValueError:raise HTTPException(422,'multimodal_configuration_unavailable') from None
            if not await has_image_model(conn,owner,group,request.task_id,config):
                return {'items':[],'status':'no_compatible_images','model_calls':0,'coverage':{'scanned':0,'scope_truncated':False}}
            encoded=None
    if encoded is None:
        try:encoded=await asyncio.to_thread(encode_text_query,request.query,timeout=min(35.0,max(1.0,deadline-time.monotonic())))
        except (ValueError,ChannelError,OSError,ImportError):raise HTTPException(422,'image_query_encoding_unavailable') from None
    profile=encoded.get('profile') or {};profile_id=profile.get('profile_id');dimension=encoded.get('dimension')
    if not isinstance(profile_id,str) or type(dimension) is not int or not 1<=dimension<=4096 or len(encoded['vector'])!=dimension*4:
        raise HTTPException(409,'image_search_profile_unavailable')
    async with pool.acquire() as conn:
        rows=await source_image_candidates(conn,owner,group,request.task_id,profile_id,dimension)
    def score():
        import numpy as np
        query=np.frombuffer(encoded['vector'],dtype='<f4');ranked=[];evaluated=0
        if not np.isfinite(query).all() or not .98<=float(np.linalg.norm(query))<=1.02:raise ValueError('image_query_invalid_vector')
        for row in rows[:1000]:
            if time.monotonic()>=deadline:break
            vector=np.frombuffer(row['image_vector'],dtype='<f4')
            if len(vector)!=dimension:continue
            value=float(np.dot(query,vector));evaluated+=1
            if math.isfinite(value):ranked.append((value,row))
        ranked.sort(key=lambda item:(-item[0],str(item[1]['operation_id'])))
        return ranked[:request.limit],evaluated
    try:ranked,evaluated=await asyncio.to_thread(score)
    except (ValueError,ImportError):raise HTTPException(503,'image_search_unavailable') from None
    items=[]
    async with pool.acquire() as conn:
        for score_value,old in ranked:
            current=await reference_image(conn,owner,group,request.task_id,old['operation_id'])
            if not current or current['revision']!=old['revision'] or current['generation_id']!=old['generation_id']:continue
            items.append({**_public(old),'score':score_value,'score_semantics':'normalized_image_similarity_not_visual_interpretation'})
    return {'items':items,'status':'completed' if items else 'empty','model_calls':0 if request.reference_operation_id else 1,
        'model_profile_id':profile_id,'coverage':{'scanned':min(len(rows),1000),'scored':evaluated,
            'scope_truncated':len(rows)>1000 or evaluated<min(len(rows),1000),'scan_limit':1000}}


async def preview(owner,operation_id,group,task_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        await _validate_task(conn,owner,task_id)
        row=await reference_image(conn,owner,group,task_id,operation_id,include_preview=True)
    if not row or not row['image_preview']:raise HTTPException(404,'image_preview_unavailable')
    return bytes(row['image_preview'])
