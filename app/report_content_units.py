"""Server-owned paragraph identity and versioned local-edit provenance.

Identity describes lineage, not semantic equivalence or permission to reuse a
fact judgment. The current full document remains the context dependency.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

POLICY='adrs-report-content-units-v1'


def paragraphs(record):
    for index,row in enumerate(record.get('summary') or []):yield 'summary:'+str(index),row
    for module in record.get('modules') or []:
        for section in ('paragraphs','appendix'):
            for index,row in enumerate(module.get(section) or []):yield f"{module['module_id']}:{section}:{index}",row


def _value(row):
    return {key:deepcopy(row.get(key)) for key in ('text','rendered_text','kind','citations','statistic_bindings')}


def _version(row):
    from app.query_understanding import identity
    return identity(_value(row))


def _document_version(record):
    from app.query_understanding import identity
    return identity({'namespace':record['content_namespace'],'reading_structure':record.get('reading_structure'),'paragraphs':[
        {'location':location,**{key:row['content_unit'][key] for key in ('unit_id','version','revision','owner')}}
        for location,row in paragraphs(record)]})


def references(record):
    """Validate the current artifact before issuing expected-version handles."""
    if not record.get('content_unit_policy'):return {}
    if record['content_unit_policy']!=POLICY:raise ValueError('content_unit_policy_unsupported')
    result={};seen=set()
    for location,row in paragraphs(record):
        unit=row.get('content_unit') or {};key=unit.get('unit_id')
        if (not isinstance(key,str) or not key or key in seen or unit.get('version')!=_version(row)
                or type(unit.get('revision')) is not int or unit['revision']<1
                or unit.get('owner')!=location.rsplit(':',1)[0]):
            raise ValueError('content_unit_current_record_changed')
        seen.add(key)
        result[location]={'unit_id':key,'version':unit['version'],
            'document_version':record.get('content_document_version')}
    if record.get('content_document_version')!=_document_version(record):
        raise ValueError('content_unit_document_changed')
    return result


def lineage_after_deletions(record,deleted=()):
    refs=references(record)
    if not refs:return None
    deleted=set(deleted)
    if not deleted<=set(refs):raise ValueError('content_unit_deleted_location_unknown')
    counts=defaultdict(int);result={}
    for location,_ in paragraphs(record):
        if location in deleted:continue
        owner=location.rsplit(':',1)[0]
        result[owner+':'+str(counts[owner])]=refs[location];counts[owner]+=1
    return result


def initialize(record,configuration):
    policy=configuration.get('content_unit_policy')
    if not policy:return
    if policy!=POLICY:raise ValueError('content_unit_policy_unsupported')
    from app.query_understanding import identity
    record.update(content_unit_policy=POLICY,content_namespace=identity({'policy':POLICY,
        'scope':configuration.get('scope'),'evidence_cutoff':configuration.get('evidence_cutoff')}))
    _bind(record)


def reconcile(previous,current,lineage=None):
    if not current.get('content_unit_policy'):
        if previous.get('content_unit_policy'):raise ValueError('content_unit_policy_removed')
        return
    if (previous.get('content_unit_policy')!=POLICY or current.get('content_unit_policy')!=POLICY
            or previous.get('content_namespace')!=current.get('content_namespace')):
        raise ValueError('content_unit_parent_changed')
    references(current)
    _bind(current,previous,lineage)


def _bind(record,previous=None,lineage=None):
    from app.query_understanding import identity
    previous=previous or {};old_refs=references(previous)
    old_rows=dict(paragraphs(previous));new_rows=dict(paragraphs(record))
    old_by_id={row['content_unit']['unit_id']:(location,row) for location,row in old_rows.items()} if old_refs else {}
    if lineage is not None and not set(lineage)<=set(new_rows):raise ValueError('content_unit_lineage_target_unknown')
    old_signatures=defaultdict(list);new_signatures=defaultdict(list)
    for location,row in old_rows.items():old_signatures[_version(row)].append(location)
    for location,row in new_rows.items():new_signatures[_version(row)].append(location)
    used=set();changes=[];parent=previous.get('content_document_version')
    for location,row in new_rows.items():
        version=_version(row);ref=(lineage or {}).get(location);before=None;before_location=None
        if ref is not None:
            found=old_by_id.get(ref.get('unit_id'))
            if not found or old_refs[found[0]]!=ref:raise ValueError('content_unit_patch_base_changed')
            before_location,before=found
        elif len(old_signatures[version])==len(new_signatures[version])==1:
            before_location=old_signatures[version][0];before=old_rows[before_location]
        if before is not None:
            old=before['content_unit'];key=old['unit_id']
            if key in used:raise ValueError('content_unit_lineage_not_one_to_one')
            revision=old['revision']+int(old['version']!=version)
        else:
            key='unit:'+identity({'namespace':record['content_namespace'],'parent':parent,
                'origin':location,'initial_value':version})
            revision=1
        used.add(key)
        row['content_unit']={'unit_id':key,'version':version,'revision':revision,'owner':location.rsplit(':',1)[0]}
        if previous and (before is None or before_location!=location or before['content_unit']['version']!=version):
            changes.append({'unit_id':key,'operation':'created' if before is None else
                'updated' if before['content_unit']['version']!=version else 'moved',
                'from_location':before_location,'to_location':location,
                'expected_version':before['content_unit']['version'] if before else None,'version':version})
    for key,(location,row) in old_by_id.items():
        if key not in used:changes.append({'unit_id':key,'operation':'deleted','from_location':location,
            'expected_version':row['content_unit']['version']})
    record['content_document_version']=_document_version(record)
    record['content_changes']={'parent_document_version':parent,'document_version':record['content_document_version'],
        'operations':changes,'semantics':'lineage_only_full_context_and_source_review_still_required'}


def require_patch_reference(change,expected):
    if expected is not None and change.get('unit_ref')!=patch_reference(expected):
        raise ValueError('content_unit_patch_base_changed')


def patch_reference(expected):
    from app.query_understanding import identity
    return 'edit:'+identity(expected)


def validate_draft(record,draft):
    refs=references(record)
    if not refs:return
    current=dict(paragraphs(record));raw=dict(paragraphs(draft))
    if set(current)!=set(raw):raise ValueError('content_unit_raw_draft_changed')
    for location,row in raw.items():
        expected=current[location]
        if (row['text']!=expected['text'] or row['kind']!=expected['kind']
                or list(dict.fromkeys(row['citations']))!=expected['citations']):
            raise ValueError('content_unit_raw_draft_changed')
