"""Versioned spans, optional semantic boundaries, and source-grounded metadata."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import re
from typing import Annotated,Literal

from pydantic import Field, StringConstraints,model_validator
from app.research_scope import ScopeRecord, Identifier,Label
from app.organization_taxonomy import TaxonomyRequest, freeze_taxonomy, _literal

VERSION='adrs-evidence-chunks-v1'
MAX_CHUNKS=4000


class EntityTerm(ScopeRecord):
    entity_id:Identifier
    name:Annotated[str,StringConstraints(strip_whitespace=True,min_length=2,max_length=200)]
    kind:Literal['organization','person','location','other']='other'


class ChunkPolicy(ScopeRecord):
    strategy:Literal['fixed','sliding','recursive','structure','semantic']='structure'
    semantic_similarity:float|None=Field(default=None,ge=-1,le=1,allow_inf_nan=False)
    entity_terms:tuple[EntityTerm,...]=Field(default=(),max_length=40)
    disciplines:tuple[Label,...]=Field(default=(),max_length=8)
    taxonomy:TaxonomyRequest|None=None
    include_source_excerpt:bool=False
    retrieval_context:Literal['matched','parent']='matched'

    @model_validator(mode='after')
    def consistent(self):
        if self.strategy=='semantic' and self.semantic_similarity is None:raise ValueError('semantic_similarity_required')
        if self.strategy!='semantic' and self.semantic_similarity is not None:raise ValueError('semantic_similarity_only_for_semantic_strategy')
        if len({item.entity_id for item in self.entity_terms})!=len(self.entity_terms):raise ValueError('duplicate_entity_dictionary_identity')
        if len(set(self.disciplines))!=len(self.disciplines):raise ValueError('duplicate_chunk_discipline')
        if self.taxonomy:
            if not self.disciplines:raise ValueError('chunk_taxonomy_requires_declared_disciplines')
            freeze_taxonomy(self.taxonomy,list(self.disciplines))
        return self


def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()


def _span(record,length):
    location=record.get('retained_location') or record
    start,end=location.get('start'),location.get('end')
    return (start,end) if isinstance(start,int) and not isinstance(start,bool) and isinstance(end,int) and not isinstance(end,bool) and 0<=start<end<=length else None


def _ranges(text,start,end,size,overlap,recursive):
    while start<end:
        target=min(start+size,end)
        if recursive and target<end:
            floor=start+size//2
            for separator in ('\n\n','\n','。','; ','. '):
                found=text.rfind(separator,floor,target)
                if found>=floor:target=found+len(separator);break
        yield start,target
        if target==end:break
        start=max(start+1,target-overlap)


def semantic_units(text,size):
    unit_size=max(100,min(size//2,600))
    return list(_ranges(text,0,len(text),unit_size,0,True))


def build_chunk_plan(text,parsed,source_version,*,size=400,overlap=80,policy=None,semantic_plan=None):
    policy=policy if isinstance(policy,ChunkPolicy) else ChunkPolicy.model_validate(policy or {})
    if not source_version or not isinstance(text,str):raise ValueError('chunk_plan_requires_actual_version_and_text')
    if not 100<=size<=4000 or not 0<=overlap<size or overlap>1000:raise ValueError('invalid_chunk_size_or_overlap')
    policy_data=policy.model_dump(mode='json')
    if policy.strategy!='semantic':policy_data.pop('semantic_similarity',None)
    if policy.strategy=='semantic':
        if not isinstance(semantic_plan,dict) or not isinstance(semantic_plan.get('boundaries'),list) or not semantic_plan.get('encoding_profile'):
            raise ValueError('semantic_chunking_requires_actual_local_encoding')
        points=semantic_plan['boundaries']
        if (not points or points[0]!=0 or points[-1]!=len(text) or any(type(value) is not int for value in points)
                or any(points[i]>=points[i+1] for i in range(len(points)-1))):
            raise ValueError('semantic_chunk_boundaries_invalid')
    profile={'schema_version':VERSION,'policy':policy_data,'size':size,
        'requested_overlap':overlap,'effective_overlap':0 if policy.strategy in {'fixed','semantic'} else overlap}
    if policy.strategy=='semantic':
        profile['semantic_encoding']=semantic_plan['encoding_profile']
        profile['semantic_boundary_id']=identity(semantic_plan['boundaries'])
    profile_id=identity(profile);issues=[];length=len(text);blocks=[]
    for raw in (parsed or {}).get('blocks',[]):
        span=_span(raw,length)
        if span:blocks.append({**raw,'start':span[0],'end':span[1]})
        else:issues.append({'kind':'unavailable_source_block_span','block_id':raw.get('block_id')})
    blocks.sort(key=lambda block:(block['start'],block['end']))
    parents=[{'key':'document','parent_key':None,'kind':'document','start':0,'end':length,'title':None,'heading_level':0}]
    headings=[];stack=[]
    for block in blocks:
        if block.get('kind')!='heading':continue
        level=block.get('heading_level') or 1
        if not isinstance(level,int) or not 1<=level<=6:level=1
        while stack and stack[-1]['heading_level']>=level:stack.pop()['end']=block['start']
        node={'key':f'section:{len(headings)}','parent_key':stack[-1]['key'] if stack else 'document',
            'kind':'section','start':block['start'],'end':length,'title':text[block['start']:block['end']][:300],
            'heading_level':level,'source_block_id':block.get('block_id')}
        headings.append(node);parents.append(node);stack.append(node)
    def enclosing(start,end,records):
        candidates=[parent for parent in records if parent['start']<=start and end<=parent['end']]
        return min(candidates,key=lambda node:(node['end']-node['start'],{'table':0,'code':0,'section':1,'document':2}[node['kind']])) if candidates else parents[0]
    for table in (parsed or {}).get('tables',[]):
        spans=[span for cell in table.get('cells',[]) if (span:=_span(cell,length))]
        if not spans:continue
        start,end=min(span[0] for span in spans),max(span[1] for span in spans)
        parents.append({'key':f'table:{len(parents)}','parent_key':enclosing(start,end,parents[:1]+headings)['key'],
            'kind':'table','start':start,'end':end,'source_table_id':table.get('table_id'),'title':None,'heading_level':None})
    for block in blocks:
        if block.get('kind')=='code':
            parents.append({'key':f'code:{len(parents)}','parent_key':enclosing(block['start'],block['end'],parents[:1]+headings)['key'],
                'kind':'code','start':block['start'],'end':block['end'],'source_block_id':block.get('block_id'),'title':None,'heading_level':None})
    ids={parent['key']:'parent:'+identity([source_version,profile_id,parent['kind'],parent['start'],parent['end']]) for parent in parents}
    for parent in parents:
        parent['parent_id']=ids.get(parent.pop('parent_key'));parent['parent_id_semantics']='source_structure_not_entity_affiliation'
        parent['parent_block_id']=ids[parent.pop('key')]
    by_parent={parent['parent_block_id']:parent for parent in parents}
    boundaries=(sorted({0,length,*[value for parent in parents for value in (parent['start'],parent['end'])],
        *(semantic_plan['boundaries'] if policy.strategy=='semantic' else [])})
        if policy.strategy in {'structure','semantic'} else [0,length])
    taxonomy=freeze_taxonomy(policy.taxonomy,list(policy.disciplines)) if policy.taxonomy else None
    children=[];truncated=False;enrichment_bytes=0;enrichment_omitted=0
    for left,right in zip(boundaries,boundaries[1:]):
        for start,end in _ranges(text,left,right,size,profile['effective_overlap'],policy.strategy in {'structure','recursive'}):
            if len(children)>=MAX_CHUNKS:truncated=True;break
            if not text[start:end].strip():continue
            parent=enclosing(start,end,parents);path=[];current=parent
            for _ in range(12):
                if current.get('title'):path.insert(0,{'title':current['title'],'parent_block_id':current['parent_block_id'],'start':current['start']})
                if not current.get('parent_id'):break
                current=by_parent[current['parent_id']]
            source_blocks=[block for block in blocks if block['start']<end and start<block['end']]
            content=text[start:end];mentions=[]
            for term in policy.entity_terms:
                match=_literal(term.name).search(content)
                if match:mentions.append({'entity_id':term.entity_id,'name':term.name,'kind':term.kind,
                    'start':start+match.start(),'end':start+match.end(),'quote':match.group(),
                    'status':'user_dictionary_literal_mention_not_disambiguated_entity_or_relationship'})
            dates=[]
            for match in list(re.finditer(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)',content))[:20]:
                try:date.fromisoformat(match.group());valid=True
                except ValueError:valid=False
                dates.append({'literal':match.group(),'start':start+match.start(),'end':start+match.end(),
                    'calendar_valid':valid,'role':'literal_date_role_unknown_not_publication_or_affiliation_time'})
            references=[]
            for match in list(re.finditer(r'\b10\.\d{4,9}/[^\s<>]{1,300}|https?://[^\s<>]{1,500}',content,re.I))[:20]:
                references.append({'literal':match.group(),'start':start+match.start(),'end':start+match.end(),
                    'status':'literal_identifier_mention_not_confirmed_citation_or_fetched_source'})
            labels=[]
            if taxonomy:
                from app.organization_taxonomy import classify_text_spans
                labels=classify_text_spans(taxonomy,content,offset=start)
            chunk={'logical_chunk_id':'chunk:'+identity([source_version,profile_id,start,end]),
                'source_version':source_version,'start':start,'end':end,'parent_block_id':parent['parent_block_id'],
                'kind':parent['kind'],'source_block_ids':[block.get('block_id') for block in source_blocks[:50]],
                'source_block_count':len(source_blocks),
                'source_locators':[block.get('source_locator') for block in source_blocks[:20]],'title_path':path,
                'entity_mentions':mentions,'date_mentions':dates,'reference_mentions':references,'labels':labels,
                'classification_hit_limit':24,'classification_limit_reached':len(labels)>=24,
                'classification_scope':'document_chunk_lexical_mapping_not_accepted_publication_classification',
                'unknown_axes':[axis for axis in ('problem','method','application') if not any(label['axis']==axis for label in labels)],
                'metadata_quality':{'range_status':'within_actual_retained_text','source_structure':'available' if source_blocks else 'unknown',
                    'entity_disambiguation':'not_performed','confirmed_entity_relations':False,'independent_semantic_review':False}}
            consumed=len(json.dumps({key:chunk[key] for key in ('entity_mentions','date_mentions','reference_mentions','labels')},ensure_ascii=False).encode('utf-8'))
            if enrichment_bytes+consumed>8*1024*1024:
                for key in ('entity_mentions','date_mentions','reference_mentions','labels'):chunk[key]=[]
                chunk['unknown_axes']=['problem','method','application']
                chunk['metadata_quality']['enrichment']='omitted_under_8MiB_document_metadata_budget';enrichment_omitted+=1
            else:enrichment_bytes+=consumed
            children.append(chunk)
        if truncated:break
    return {'schema_version':VERSION,'profile':profile,'profile_id':profile_id,'source_version':source_version,
        'parents':parents,'children':children,'taxonomy':taxonomy,'issues':issues[:100],'issue_count':len(issues),
        'truncated':truncated,'unindexed_range':[children[-1]['end'] if children else 0,length] if truncated else None,
        'metadata_enrichment_bytes':enrichment_bytes,'metadata_enrichment_omitted_chunks':enrichment_omitted,
        'summary_excerpt':{'start':0,'end':min(400,length),'kind':'literal_source_lead_excerpt_not_generated_summary'} if policy.include_source_excerpt and text else None,
        'storage_note':'parent_and_child_spans_reference_one_original_text_parents_not_embedded',
        'semantic_chunking':semantic_plan if policy.strategy=='semantic' else {'status':'not_selected'}}


def parent_window(text,chunk,parent,limit=2000):
    span=_span(chunk,len(text))
    if span is None:raise ValueError('unavailable_original_chunk_range')
    start,end=span
    if end-start>4000:raise ValueError('matched_chunk_exceeds_parent_window_limit')
    parent_span=_span(parent,len(text)) if parent else None
    if not parent_span or not parent_span[0]<=start<end<=parent_span[1]:raise ValueError('unavailable_original_parent_range')
    limit=max(end-start,min(4000,max(100,int(limit))))
    left=max(parent['start'],start-(limit-(end-start))//2);right=min(parent['end'],left+limit)
    left=max(parent['start'],right-limit)
    return {'text':text[left:right],'start':left,'end':right,'matched_start':start,'matched_end':end,
        'parent_block_id':parent['parent_block_id'],'status':'bounded_original_parent_window_not_full_document'}
