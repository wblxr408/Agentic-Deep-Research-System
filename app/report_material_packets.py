"""Owned reader material packets inside the existing report review, not an agent."""
from __future__ import annotations

import json
from collections import defaultdict
from app.query_understanding import identity

LEGACY_POLICY='adrs-reader-owned-material-v1'
POLICY='adrs-reader-owned-material-v2-scientific-dependencies'
SUPPORTED_POLICIES={LEGACY_POLICY,POLICY}
COVERAGE_POLICY='adrs-packet-work-coverage-v1'
DOCUMENT_POLICY='adrs-reader-document-passes-v1'
MAX_BYTES=60000
MAX_RECORDS=8


def source_dependency(source,policy):
    if policy==LEGACY_POLICY:
        return identity({name:source.get(name) for name in
            ('evidence_id','content','source_url','source_type','acquisition')})
    acquisition=source.get('acquisition') or {}
    snapshot=acquisition.get('source_access_snapshot')
    return identity({'policy':policy,**{name:source.get(name) for name in
        ('evidence_id','content','source_url','source_title','source_type')},
        'versions':{name:acquisition.get(name) for name in
            ('source_document_id','source_content_version','parse_version_id','coverage')},
        'access_revision':acquisition.get('source_access_revision'),
        'access_snapshot':{key:value for key,value in snapshot.items() if key!='checked_at'}
            if isinstance(snapshot,dict) else snapshot})


def material_owners(record,findings,evidence,technical,actions,*,coverage_works=(),policy=POLICY):
    """Use exact citations and retained identities; titles only locate report prose."""
    sources=[item.model_dump(mode='json') if hasattr(item,'model_dump') else item for item in evidence]
    if technical and not sources:raise ValueError('reader_material_requires_retained_evidence')
    source_ids={index:item['evidence_id'] for index,item in enumerate(sources,1)}
    by_source={item['evidence_id']:item for item in sources}
    if policy not in SUPPORTED_POLICIES:raise ValueError('reader_material_policy_unsupported')
    dependencies={key:source_dependency(item,policy) for key,item in by_source.items()}
    paragraphs={};sections=defaultdict(list)
    for module in record.get('modules',[]):
        for section in ('paragraphs','appendix'):
            for index,item in enumerate(module.get(section) or []):
                key=f"{module['module_id']}:{section}:{index}"
                links=[source_ids.get(number,'unresolved:'+str(number)) for number in item.get('citations',[])]
                paragraphs[key]={'id':key,'text':item.get('rendered_text') or item.get('text',''),
                    'module_id':module['module_id'],'section':section,'kind':item.get('kind'),
                    'source_ids':links}
                sections[(module['module_id'],section)].append(key)
    for index,item in enumerate(record.get('summary') or []):
        key=f'summary:{index}'
        paragraphs[key]={'id':key,'text':item.get('rendered_text') or item.get('text',''),
            'module_id':'summary','section':'paragraphs','kind':item.get('kind'),
            'source_ids':[source_ids.get(number,'unresolved:'+str(number)) for number in item.get('citations',[])]}
        sections[('summary','paragraphs')].append(key)
    paragraphs={**{key:value for key,value in paragraphs.items() if value['module_id']=='summary'},
        **{key:value for key,value in paragraphs.items() if value['module_id']!='summary'}}
    neighbours={}
    for keys in sections.values():
        for index,key in enumerate(keys):neighbours[key]=keys[max(0,index-1):index+2]
    def proof_ids(value):
        if isinstance(value,dict):
            own={value['evidence_id']} if isinstance(value.get('evidence_id'),str) else set()
            return own.union(*(proof_ids(item) for item in value.values()))
        if isinstance(value,(list,tuple)):return set().union(*(proof_ids(item) for item in value))
        return set()
    outputs={item['output_id']:item for item in (findings.get('scope_result') or {}).get('outputs',[])}
    cards={item['output_id']:item for item in (findings.get('technical_reading') or {}).get('cards',[])}
    work_sources={}
    for key,output in outputs.items():
        metadata=(findings.get('publication_metadata') or {}).get(key,{})
        card=cards.get(key,{})
        work_sources[key]=proof_ids({name:card[name] for name in ('fields','reading_contract') if name in card}) | set(metadata.get('primary_evidence_ids') or [])
        work_sources[key]|={source_id for source_id in metadata.get('evidence_ids',[])
            if (by_source.get(source_id) or {}).get('source_url') in output.get('source_urls',[])}
    owners=[];seen=set()
    covered={row.get('output_id') for row in technical}
    coverage_rows=[{'output_id':row['output_id'],'title':row['title']} for row in coverage_works if row['output_id'] not in covered]
    for kind,rows in (('technical',technical),('actions',actions),('coverage',coverage_rows)):
        for row in rows:
            key=row.get('output_id') if kind!='actions' else row.get('action_id')
            if not isinstance(key,str) or not key or (kind,key) in seen:raise ValueError('reader_material_owner_identity_invalid')
            seen.add((kind,key));owner_id=kind+':'+key
            original=cards.get(key,{}) if kind!='actions' else next(
                (item for item in (findings.get('actions') or {}).get('cards',[]) if item.get('action_id')==key),{})
            links=work_sources.get(key,set()) if kind!='actions' else proof_ids({name:original[name]
                for name in ('basis','supporting','proofs','public_contacts','public_entrypoints') if name in original}).union(*(
                work_sources.get(work,set()) for work in row.get('related_output_ids') or []))
            if kind=='actions' and not links:links=set(by_source)
            title=(outputs.get(key) or {}).get('title') if kind!='actions' else row.get('question') or row.get('goal')
            selected={key for key,paragraph in paragraphs.items()
                if (set(paragraph['source_ids']) & links or title and title in paragraph['text'])
                and (kind!='actions' or paragraph['module_id'] in {'actions','relationships'})}
            if kind=='actions' and not selected:
                selected={key for key,value in paragraphs.items() if value['module_id']=='actions'}
            if any(key not in by_source for key in links):raise ValueError('reader_material_source_binding_missing')
            selected.update(other for key in list(selected) for other in neighbours[key])
            owners.append({'owner_id':owner_id,'kind':kind,'key':key,'title':title,'material':{'title':title,**row},
                'paragraph_ids':[key for key in paragraphs if key in selected],
                'source_dependencies':{key:dependencies.get(key,'unresolved') for key in sorted(links)}})
    return owners,paragraphs,dependencies


def context_overrides(value,owners,paragraphs):
    if not isinstance(value,list):raise ValueError('reader_material_contexts_missing')
    known={item['owner_id'] for item in owners};result={};seen=set()
    for row in value:
        owner=row.get('owner_id');keys=row.get('paragraph_ids')
        if (owner not in known|{'*'} or owner in seen or not isinstance(keys,list)
                or any(not isinstance(key,str) or key not in paragraphs for key in keys)):
            raise ValueError('reader_material_context_invalid')
        seen.add(owner);result[owner]=list(dict.fromkeys(keys))
    return result


def material_packets(owners,paragraphs,dependencies,contexts,coverage,*,question,criteria,model,route,scope,allow_exclusion,
                     coverage_policy=None,policy=POLICY,binding_context=None):
    """Stable hash-prefix partitions split only affected buckets; records stay whole."""
    if policy not in SUPPORTED_POLICIES:raise ValueError('reader_material_policy_unsupported')
    destinations={item['output_id']:item for item in coverage}
    # Local IDs survive index shifts. Duplicate occurrences remain distinct.
    local_ids={};counts=defaultdict(int)
    for key,row in paragraphs.items():
        digest=identity({name:value for name,value in row.items() if name!='id'})
        counts[digest]+=1;local_ids[key]='p-'+digest+':'+str(counts[digest])
    def build(rows,prefix):
        selected={key for row in rows for key in [*row['paragraph_ids'],*contexts.get(row['owner_id'],[]),*contexts.get('*',[])]}
        for row in rows:
            if row['kind']=='technical':selected.update((destinations.get(row['key']) or {}).get('paragraph_ids',[]))
        ordered=[key for key in paragraphs if key in selected]
        pointers={};prose=[];source_dependencies={}
        for key in ordered:
            row=paragraphs[key];alias=local_ids[key];pointers[alias]=key
            prose.append({**{name:value for name,value in row.items() if name!='id'},'id':alias})
            source_dependencies.update({name:dependencies.get(name,'unresolved') for name in row['source_ids']})
        for row in rows:source_dependencies.update(row['source_dependencies'])
        kind=rows[0]['kind'];criterion={'technical':'mechanisms','actions':'first_project','coverage':'selection'}[kind]
        packet={'question':question,'criterion':criteria[criterion],'material':[row['material'] for row in rows],
            'paragraphs':prose,'source_dependencies':source_dependencies,'review_scope':scope,
            'destinations':{row['key']:(destinations.get(row['key']) or {}).get('destination')
                for row in rows if kind=='technical'}}
        packet['exclusion_only']=bool(allow_exclusion and kind=='technical'
            and all((destinations.get(row['key']) or {}).get('destination')=='excluded' for row in rows))
        if coverage_policy:
            packet.pop('destinations',None)
            packet.pop('exclusion_only',None)
            packet.update(coverage_policy=coverage_policy,allow_exclusion=bool(allow_exclusion),
                coverage_work_ids=[row['key'] for row in rows if row['kind']!='actions'])
        if policy==POLICY:packet.pop('source_dependencies')
        size=len(json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
        return {'name':kind+':'+prefix,'criterion':criterion,'packet':packet,'aliases':pointers,
            'binding':identity({'policy':policy,'model':model,'route':route,'packet':packet,
                **({'source_dependencies':source_dependencies,'review_context':binding_context} if policy==POLICY else {})}),
            **({'source_dependencies':source_dependencies} if policy==POLICY else {}),
            'input_bytes':size,'owner_ids':[row['owner_id'] for row in rows],
            'blocked':size>MAX_BYTES}
    result=[]
    def partition(rows,prefix):
        candidate=build(rows,prefix)
        if (len(rows)<=MAX_RECORDS and not candidate['blocked']) or len(rows)==1:
            result.append(candidate);return
        groups=defaultdict(list)
        for row in rows:groups[identity(row['owner_id'])[len(prefix)]].append(row)
        for label,values in sorted(groups.items()):partition(values,prefix+label)
    for kind in ('technical','actions','coverage'):
        rows=sorted((row for row in owners if row['kind']==kind),key=lambda row:row['owner_id'])
        if rows:partition(rows,'')
    return result
