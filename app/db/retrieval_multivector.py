"""Store actual local model outputs beside their owned source chunks."""
from __future__ import annotations

import json


async def persist_document_vectors(conn,owner_id,source_id,document_ids,source_version,feature_profile_id,output):
    observed=output['observed'];pair=output['pair'];vectors=output['vectors']
    if len(document_ids)!=len(vectors):raise ValueError('multivector_document_count_mismatch')
    rows=[]
    for document_id,vector in zip(document_ids,vectors,strict=True):
        rows.append((str(document_id),str(source_id),str(owner_id),source_version,feature_profile_id,pair['pair_id'],
            observed['token_dimension'],observed['pooled_dimension'],vector['input_tokens'],vector['token_bytes'],
            vector['pooled_bytes'],json.dumps(vector['locations'],ensure_ascii=False)))
    await conn.executemany('''INSERT INTO retrieval_model_features(document_id,source_id,owner_id,source_version,
        feature_profile_id,pair_id,token_dimension,pooled_dimension,token_count,token_vectors,pooled_vector,token_locations)
        VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)''',rows)
