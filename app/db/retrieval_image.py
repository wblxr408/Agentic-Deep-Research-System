"""Versioned image candidates: source discovery and anchored text handoff."""
from __future__ import annotations

import json
import time

from app.retrieval_filters import compile_filter,current_document_clause
from app.source_lifecycle import access_clause


def _object(value):
    parsed=json.loads(value) if isinstance(value,str) else value
    return parsed if isinstance(parsed,dict) else {}


async def has_image_index(conn,owner_id,group,session_id,filters,config):
    business,parameters=compile_filter(filters,start_parameter=6)
    return await conn.fetchval(f'''SELECT EXISTS(SELECT 1 FROM retrieval_multimodal_generations mg
        JOIN retrieval_multimodal_features f ON f.operation_id=mg.operation_id AND f.owner_id=mg.owner_id AND f.source_id=mg.source_id
        JOIN document_processing_operations o ON o.id=f.operation_id AND o.owner_id=f.owner_id AND o.source_id=f.source_id
        JOIN document_sources s ON s.id=f.source_id AND s.owner_id=f.owner_id
        JOIN document_source_lifecycle lc ON lc.source_id=s.id AND lc.owner_id=s.owner_id
        JOIN source_index_heads h ON h.source_id=s.id AND h.owner_id=s.owner_id AND h.mode='lexical' AND h.generation_id=mg.generation_id
        JOIN retrieval_index_generations g ON g.id=h.generation_id AND g.owner_id=s.owner_id AND g.source_id=s.id AND g.status='ready'
        JOIN documents d ON d.source_id=s.id AND d.owner_id=s.owner_id
        WHERE s.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active'
          AND f.model_profile->>'model'=$4::text AND f.model_profile->>'revision'=$5::text
          AND f.source_version=g.source_version AND f.source_version=s.metadata->>'parse_version_id'
          AND o.status='completed' AND o.parse_version=f.source_version AND o.lifecycle_revision=lc.revision
          AND (d.metadata->'chunk_reference'->>'start')::integer < (o.input_description->'source_text_range'->>'end')::integer
          AND (d.metadata->'chunk_reference'->>'end')::integer > (o.input_description->'source_text_range'->>'start')::integer
          AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business})''',
        str(owner_id),group,str(session_id) if session_id else None,config['model'],config['revision'],*parameters)


async def image_chunk_candidates(conn,owner_id,group,session_id,limit,filters,encoded,deadline=None):
    """Image relevance can hand off only chunks overlapping the selected source range."""
    import asyncio
    business,parameters=compile_filter(filters,start_parameter=7)
    rows=await conn.fetch(f'''SELECT d.id,d.content,d.metadata,d.source_id AS document_source_id,h.generation_id AS index_generation_id,
        lc.revision AS source_access_revision,f.image_vector,f.dimension,f.operation_id,f.selection,
        o.input_description->'source_text_range' AS source_text_range
        FROM retrieval_multimodal_generations mg JOIN retrieval_multimodal_features f
          ON f.operation_id=mg.operation_id AND f.owner_id=mg.owner_id AND f.source_id=mg.source_id
        JOIN document_processing_operations o ON o.id=f.operation_id AND o.owner_id=f.owner_id AND o.source_id=f.source_id
        JOIN document_sources s ON s.id=f.source_id AND s.owner_id=f.owner_id
        JOIN document_source_lifecycle lc ON lc.source_id=s.id AND lc.owner_id=s.owner_id
        JOIN source_index_heads h ON h.source_id=s.id AND h.owner_id=s.owner_id AND h.mode='lexical' AND h.generation_id=mg.generation_id
        JOIN retrieval_index_generations g ON g.id=h.generation_id AND g.owner_id=s.owner_id AND g.source_id=s.id AND g.status='ready'
        JOIN documents d ON d.source_id=s.id AND d.owner_id=s.owner_id
        WHERE s.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active'
          AND mg.model_profile_id=$4::text AND f.dimension=$5::integer
          AND f.source_version=g.source_version AND f.source_version=s.metadata->>'parse_version_id'
          AND g.feature_profile_id=s.metadata->'feature_plan'->>'profile_id'
          AND o.status='completed' AND o.parse_version=f.source_version AND o.lifecycle_revision=lc.revision
          AND (d.metadata->'chunk_reference'->>'start')::integer < (o.input_description->'source_text_range'->>'end')::integer
          AND (d.metadata->'chunk_reference'->>'end')::integer > (o.input_description->'source_text_range'->>'start')::integer
          AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business}
        ORDER BY f.operation_id,d.id LIMIT $6''',str(owner_id),group,str(session_id) if session_id else None,
        encoded['profile']['profile_id'],encoded['dimension'],2001,*parameters)
    scanned=min(len(rows),2000)
    def score():
        import numpy as np
        query=np.frombuffer(encoded['vector'],dtype='<f4');found={};evaluated=0
        for row in rows[:scanned]:
            if deadline is not None and time.monotonic()>=deadline:break
            image=np.frombuffer(row['image_vector'],dtype='<f4')
            if len(image)!=len(query):continue
            value=float(np.dot(query,image));evaluated+=1
            if not np.isfinite(value):continue
            key=str(row['id']);prior=found.get(key)
            if prior and prior['auxiliary_score']>=value:continue
            item={key:row[key] for key in ('id','content','metadata','document_source_id','index_generation_id','source_access_revision')}
            item.update(auxiliary_score=value,image_operation_id=str(row['operation_id']),image_selection=_object(row['selection']),
                source_text_range=_object(row['source_text_range']),image_profile_id=encoded['profile']['profile_id'])
            found[key]=item
        ranked=sorted(found.values(),key=lambda item:(-item['auxiliary_score'],str(item['id'])))[:limit]
        return ranked,{'scanned_image_chunk_pairs':scanned,'scored_pairs':evaluated,'scan_limit':2000,
            'scope_truncated':len(rows)>2000 or evaluated<scanned}
    return await asyncio.to_thread(score)


async def source_image_candidates(conn,owner_id,group,session_id,profile_id,dimension):
    """Image discovery also includes pages with no extracted text."""
    return await conn.fetch(f'''SELECT f.operation_id,f.source_id,s.name,s.group_name,f.selection,f.image_vector,f.dimension,(f.image_preview IS NOT NULL) AS has_preview,
        f.source_version,h.generation_id,lc.revision,o.input_description->'source_text_range' AS source_text_range
        FROM retrieval_multimodal_generations mg JOIN retrieval_multimodal_features f
          ON f.operation_id=mg.operation_id AND f.owner_id=mg.owner_id AND f.source_id=mg.source_id
        JOIN document_processing_operations o ON o.id=f.operation_id AND o.owner_id=f.owner_id AND o.source_id=f.source_id
        JOIN document_sources s ON s.id=f.source_id AND s.owner_id=f.owner_id
        JOIN document_source_lifecycle lc ON lc.source_id=s.id AND lc.owner_id=s.owner_id
        JOIN source_index_heads h ON h.source_id=s.id AND h.owner_id=s.owner_id AND h.mode='lexical' AND h.generation_id=mg.generation_id
        JOIN retrieval_index_generations g ON g.id=h.generation_id AND g.owner_id=s.owner_id AND g.source_id=s.id AND g.status='ready'
        WHERE s.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active'
          AND mg.model_profile_id=$4::text AND f.dimension=$5::integer AND f.source_version=g.source_version
          AND f.source_version=s.metadata->>'parse_version_id' AND g.feature_profile_id=s.metadata->'feature_plan'->>'profile_id'
          AND o.status='completed' AND o.parse_version=f.source_version AND o.lifecycle_revision=lc.revision
          AND {access_clause('s','$3','$2')} ORDER BY f.operation_id LIMIT 1001''',
        str(owner_id),group,str(session_id) if session_id else None,profile_id,dimension)


async def has_image_model(conn,owner_id,group,session_id,config):
    return await conn.fetchval(f'''SELECT EXISTS(SELECT 1 FROM retrieval_multimodal_generations mg
        JOIN retrieval_multimodal_features f ON f.operation_id=mg.operation_id AND f.owner_id=mg.owner_id AND f.source_id=mg.source_id
        JOIN document_processing_operations o ON o.id=f.operation_id AND o.owner_id=f.owner_id AND o.source_id=f.source_id
        JOIN document_sources s ON s.id=f.source_id AND s.owner_id=f.owner_id
        JOIN document_source_lifecycle lc ON lc.source_id=s.id AND lc.owner_id=s.owner_id
        JOIN source_index_heads h ON h.source_id=s.id AND h.owner_id=s.owner_id AND h.mode='lexical' AND h.generation_id=mg.generation_id
        JOIN retrieval_index_generations g ON g.id=h.generation_id AND g.owner_id=s.owner_id AND g.source_id=s.id AND g.status='ready'
        WHERE s.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active'
          AND f.model_profile->>'model'=$4::text AND f.model_profile->>'revision'=$5::text
          AND f.source_version=g.source_version AND f.source_version=s.metadata->>'parse_version_id'
          AND g.feature_profile_id=s.metadata->'feature_plan'->>'profile_id' AND o.status='completed'
          AND o.parse_version=f.source_version AND o.lifecycle_revision=lc.revision AND {access_clause('s','$3','$2')})''',
        str(owner_id),group,str(session_id) if session_id else None,config['model'],config['revision'])


async def reference_image(conn,owner_id,group,session_id,operation_id,*,include_preview=False):
    preview='f.image_preview' if include_preview else 'NULL::bytea AS image_preview'
    return await conn.fetchrow(f'''SELECT f.operation_id,f.source_id,s.name,s.group_name,f.selection,f.image_vector,f.dimension,
        f.model_profile,f.source_version,h.generation_id,lc.revision,{preview},
        o.input_description->'source_text_range' AS source_text_range
        FROM retrieval_multimodal_generations mg JOIN retrieval_multimodal_features f
          ON f.operation_id=mg.operation_id AND f.owner_id=mg.owner_id AND f.source_id=mg.source_id
        JOIN document_processing_operations o ON o.id=f.operation_id AND o.owner_id=f.owner_id AND o.source_id=f.source_id
        JOIN document_sources s ON s.id=f.source_id AND s.owner_id=f.owner_id
        JOIN document_source_lifecycle lc ON lc.source_id=s.id AND lc.owner_id=s.owner_id
        JOIN source_index_heads h ON h.source_id=s.id AND h.owner_id=s.owner_id AND h.mode='lexical' AND h.generation_id=mg.generation_id
        JOIN retrieval_index_generations g ON g.id=h.generation_id AND g.owner_id=s.owner_id AND g.source_id=s.id AND g.status='ready'
        WHERE s.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active' AND f.operation_id=$4::uuid
          AND f.source_version=g.source_version AND f.source_version=s.metadata->>'parse_version_id'
          AND g.feature_profile_id=s.metadata->'feature_plan'->>'profile_id' AND o.status='completed'
          AND o.parse_version=f.source_version AND o.lifecycle_revision=lc.revision AND {access_clause('s','$3','$2')}''',
        str(owner_id),group,str(session_id) if session_id else None,str(operation_id))


async def list_images(conn,owner_id,group,session_id):
    return await conn.fetch(f'''SELECT f.operation_id,f.source_id,s.name,s.group_name,f.selection,(f.image_preview IS NOT NULL) AS has_preview,
        f.source_version,h.generation_id,lc.revision,o.input_description->'source_text_range' AS source_text_range
        FROM retrieval_multimodal_generations mg JOIN retrieval_multimodal_features f
          ON f.operation_id=mg.operation_id AND f.owner_id=mg.owner_id AND f.source_id=mg.source_id
        JOIN document_processing_operations o ON o.id=f.operation_id AND o.owner_id=f.owner_id AND o.source_id=f.source_id
        JOIN document_sources s ON s.id=f.source_id AND s.owner_id=f.owner_id
        JOIN document_source_lifecycle lc ON lc.source_id=s.id AND lc.owner_id=s.owner_id
        JOIN source_index_heads h ON h.source_id=s.id AND h.owner_id=s.owner_id AND h.mode='lexical' AND h.generation_id=mg.generation_id
        JOIN retrieval_index_generations g ON g.id=h.generation_id AND g.owner_id=s.owner_id AND g.source_id=s.id AND g.status='ready'
        WHERE s.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active'
          AND f.source_version=g.source_version AND f.source_version=s.metadata->>'parse_version_id'
          AND g.feature_profile_id=s.metadata->'feature_plan'->>'profile_id' AND o.status='completed'
          AND o.parse_version=f.source_version AND o.lifecycle_revision=lc.revision AND {access_clause('s','$3','$2')}
        ORDER BY o.created_at DESC,o.id DESC LIMIT 101''',str(owner_id),group,str(session_id) if session_id else None)
