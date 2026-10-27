"""Bounded beam traversal over authorized source structure and literal mentions."""
from __future__ import annotations

import json
import time
from uuid import UUID

from app.retrieval_features import lexical_view
from app.retrieval_filters import compile_filter,current_document_clause
from app.source_lifecycle import access_clause

VERSION='adrs-beam-retrieval-v1'


def policy():
    return {'version':VERSION,'beam_width':8,'max_depth':2,'fanout_per_node':8,'max_edge_visits':128,
        'seed_score':'best_original_route_reciprocal_rank','path_score':'decayed_seed_and_literal_query_overlap',
        'edge_types':['same_source_parent','same_dictionary_literal_mention']}


def _object(value):
    value=json.loads(value) if isinstance(value,str) else value
    return value if isinstance(value,dict) else {}


def _node(row):
    reference=_object(row['metadata']).get('chunk_reference') or {}
    return {'chunk_id':str(row['id']),'source_id':str(row['document_source_id']),
        'source_revision':row['source_access_revision'],'generation_id':str(row['index_generation_id']) if row['index_generation_id'] else None,
        'source_version':reference.get('source_version'),'start':reference.get('start'),'end':reference.get('end')}


def _valid_mentions(row):
    reference=_object(row['metadata']).get('chunk_reference') or {};start=reference.get('start');end=reference.get('end')
    if type(start) is not int or type(end) is not int or end-start!=len(row['content']):return []
    output=[]
    for mention in reference.get('entity_mentions') or []:
        if not isinstance(mention,dict):continue
        left,right=mention.get('start'),mention.get('end');quote=mention.get('quote')
        if (type(left) is not int or type(right) is not int or not start<=left<right<=end or not isinstance(quote,str)
                or row['content'][left-start:right-start]!=quote):continue
        if not all(isinstance(mention.get(key),str) and mention[key] for key in ('entity_id','name','kind')):continue
        output.append({key:mention[key] for key in ('entity_id','name','kind','start','end','quote')})
    return output


def _valid_reference(row):
    metadata=_object(row['metadata']);reference=metadata.get('chunk_reference') or {}
    start,end=reference.get('start'),reference.get('end');version=reference.get('source_version')
    return (isinstance(version,str) and bool(version) and version==metadata.get('parse_version_id')
        and type(start) is int and type(end) is int and 0<=start<end and end-start==len(row['content']))


def _edge(left,right):
    if not _valid_reference(left) or not _valid_reference(right):return None
    left_ref=_object(left['metadata']).get('chunk_reference') or {};right_ref=_object(right['metadata']).get('chunk_reference') or {}
    parent=left_ref.get('parent_block_id')
    if (isinstance(parent,str) and parent and parent==right_ref.get('parent_block_id') and str(left['document_source_id'])==str(right['document_source_id'])
            and left_ref.get('source_version')==right_ref.get('source_version')):
        return {'kind':'same_source_parent','parent_block_id':parent}
    left_mentions=_valid_mentions(left);right_mentions=_valid_mentions(right)
    for first in sorted(left_mentions,key=lambda item:(item['entity_id'],item['start'])):
        for second in sorted(right_mentions,key=lambda item:(item['entity_id'],item['start'])):
            if (first['entity_id']==second['entity_id'] and first['kind']==second['kind']
                    and first['name'].casefold()==second['name'].casefold()):
                return {'kind':'same_dictionary_literal_mention','entity_id':first['entity_id'],'name':first['name'],
                    'entity_kind':first['kind'],'from_mention':first,'to_mention':second,
                    'semantics':'literal_mention_not_confirmed_identity_or_relationship'}
    return None


async def _current_nodes(conn,ids,owner,group,session,filters):
    if not ids:return {}
    business,parameters=compile_filter(filters,start_parameter=5)
    rows=await conn.fetch(f'''SELECT d.id,d.content,d.metadata,d.source_id AS document_source_id,h.generation_id AS index_generation_id,
        COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS source_access_revision
        FROM documents d JOIN document_sources s ON s.id=d.source_id AND s.owner_id=d.owner_id
        LEFT JOIN source_index_heads h ON h.source_id=d.source_id AND h.owner_id=d.owner_id
        WHERE d.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active'
          AND d.id=ANY($4::uuid[]) AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business}''',
        str(owner),group,str(session) if session else None,[UUID(str(value)) for value in ids],*parameters)
    return {str(row['id']):dict(row) for row in rows}


async def _neighbors(conn,parent,owner,group,session,filters,limit):
    business,parameters=compile_filter(filters,start_parameter=6)
    rows=await conn.fetch(f'''WITH seed AS MATERIALIZED (
        SELECT d.id,d.source_id,d.content,d.metadata,h.generation_id,
          COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS revision
        FROM documents d JOIN document_sources s ON s.id=d.source_id AND s.owner_id=d.owner_id
        LEFT JOIN source_index_heads h ON h.source_id=d.source_id AND h.owner_id=d.owner_id
        WHERE d.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active' AND d.id=$4::uuid
          AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business})
        SELECT d.id,d.content,d.metadata,d.source_id AS document_source_id,h.generation_id AS index_generation_id,
          COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS source_access_revision,
          seed.revision AS seed_revision,seed.generation_id AS seed_generation
        FROM seed JOIN documents d ON d.owner_id=$1::uuid AND d.id<>seed.id
        JOIN document_sources s ON s.id=d.source_id AND s.owner_id=d.owner_id
        LEFT JOIN source_index_heads h ON h.source_id=d.source_id AND h.owner_id=d.owner_id
        LEFT JOIN LATERAL (
          SELECT a.value FROM jsonb_array_elements(CASE WHEN jsonb_typeof(seed.metadata->'chunk_reference'->'entity_mentions')='array'
              THEN seed.metadata->'chunk_reference'->'entity_mentions' ELSE '[]'::jsonb END) a(value)
          JOIN jsonb_array_elements(CASE WHEN jsonb_typeof(d.metadata->'chunk_reference'->'entity_mentions')='array'
              THEN d.metadata->'chunk_reference'->'entity_mentions' ELSE '[]'::jsonb END) b(value)
            ON a.value->>'entity_id'=b.value->>'entity_id' AND a.value->>'kind'=b.value->>'kind'
              AND lower(a.value->>'name')=lower(b.value->>'name') LIMIT 1) shared ON TRUE
        WHERE ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active'
          AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business}
          AND ((d.source_id=seed.source_id AND d.metadata->'chunk_reference'->>'parent_block_id' IS NOT NULL
            AND d.metadata->'chunk_reference'->>'parent_block_id'=seed.metadata->'chunk_reference'->>'parent_block_id') OR shared.value IS NOT NULL)
        ORDER BY CASE WHEN d.source_id=seed.source_id THEN 0 ELSE 1 END,d.id LIMIT $5''',str(owner),group,
        str(session) if session else None,str(parent['id']),limit,*parameters)
    if any(row['seed_revision']!=parent['source_access_revision'] or row['seed_generation']!=parent['index_generation_id'] for row in rows):return [],False
    return [dict(row) for row in rows[:limit-1]],len(rows)>=limit


async def retrieve(conn,seed_routes,query,owner,group,session,filters,limit,deadline=None):
    config=policy();width=config['beam_width'];depth=config['max_depth'];fanout=config['fanout_per_node']
    initial={}
    for route,rows in seed_routes.items():
        for rank,row in enumerate(rows[:limit],1):
            if not row['document_source_id']:continue
            key=str(row['id']);item=initial.setdefault(key,{'row':dict(row),'rank':rank,'routes':[]})
            item['rank']=min(item['rank'],rank);item['routes'].append({'channel':route,'rank':rank})
    ordered=sorted(initial.items(),key=lambda item:(item[1]['rank'],item[0]))[:width]
    current=await _current_nodes(conn,[key for key,_ in ordered],owner,group,session,filters)
    beam=[]
    for key,item in ordered:
        actual=current.get(key)
        if not actual or _node(actual)!=_node(item['row']):continue
        score=1/(1+item['rank']);beam.append({'row':actual,'score':score,'nodes':[_node(actual)],'edges':[],
            'seed_routes':item['routes'],'seed_rank':item['rank']})
    eligible_seed_count=len(beam)
    seen={item['nodes'][0]['chunk_id'] for item in beam};found={};visits=0;expanded=0;truncated=False
    terms=set(list(lexical_view(query)['terms'])[:128])
    for level in range(1,depth+1):
        candidates=[]
        for parent in beam:
            if visits>=config['max_edge_visits'] or deadline is not None and time.monotonic()>=deadline:
                truncated=True;break
            neighbors,more=await _neighbors(conn,parent['row'],owner,group,session,filters,fanout+1);expanded+=1;truncated|=more
            for row in neighbors:
                if visits>=config['max_edge_visits']:truncated=True;break
                visits+=1;key=str(row['id'])
                if key in seen:continue
                edge=_edge(parent['row'],row)
                if not edge:continue
                document_terms=set(lexical_view(row['content'][:4000])['terms'])
                overlap=len(terms&document_terms)/len(terms) if terms else 0.
                score=(.7*parent['score']+.3*overlap)*(.9 if edge['kind']=='same_source_parent' else .75)
                candidates.append({'row':row,'score':score,'nodes':parent['nodes']+[_node(row)],'edges':parent['edges']+[edge],
                    'seed_routes':parent['seed_routes'],'seed_rank':parent['seed_rank']})
        best={}
        for item in sorted(candidates,key=lambda value:(-value['score'],str(value['row']['id']))):
            best.setdefault(str(item['row']['id']),item)
        beam=list(best.values())[:width]
        if len(best)>width:truncated=True
        if not beam:break
        for item in beam:
            key=str(item['row']['id']);seen.add(key);found[key]={**item['row'],'auxiliary_score':item['score'],
                'beam_path':{'version':VERSION,'nodes':item['nodes'],'edges':item['edges'],'seed_routes':item['seed_routes'],
                    'seed_rank':item['seed_rank'],'depth':level,'score':item['score']}}
    ranked=sorted(found.values(),key=lambda row:(-row['auxiliary_score'],str(row['id'])))[:limit]
    truncated|=len(found)>limit
    return ranked,{'seed_count':len(ordered),'eligible_seed_count':eligible_seed_count,'expanded_nodes':expanded,'edge_visits':visits,
        'beam_width':width,'max_depth':depth,'fanout_per_node':fanout,'max_edge_visits':config['max_edge_visits'],'scope_truncated':truncated}


async def path_current(conn,path,owner,group,session,filters):
    if not isinstance(path,dict) or path.get('version')!=VERSION:return False
    nodes=path.get('nodes');edges=path.get('edges')
    if not isinstance(nodes,list) or not isinstance(edges,list) or not 2<=len(nodes)<=3 or len(edges)!=len(nodes)-1:return False
    try:ids=[str(UUID(item['chunk_id'])) for item in nodes]
    except (KeyError,ValueError,TypeError):return False
    if len(set(ids))!=len(ids):return False
    current=await _current_nodes(conn,ids,owner,group,session,filters)
    if len(current)!=len(ids) or any(_node(current[key])!=node for key,node in zip(ids,nodes)):return False
    return all(_edge(current[ids[index]],current[ids[index+1]])==edge for index,edge in enumerate(edges))
