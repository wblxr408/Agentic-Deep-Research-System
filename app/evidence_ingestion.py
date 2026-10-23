"""Task-scoped retained-text versions and intake outcomes; no acquisition or index."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from urllib.parse import urlsplit, urlunsplit

VERSION = 'adrs-task-evidence-ingestion-v1'


def _identity(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')).hexdigest()


def retained_evidence_identity(evidence):
    """Same retained-text identity for the ledger and model excerpt anchors."""
    acquisition=evidence.get('acquisition') or {}
    source_type=evidence.get('source_type','unknown')
    raw_url=evidence.get('source_url')
    try:
        parts=urlsplit(raw_url or '')
        location=urlunsplit((parts.scheme.lower(),parts.netloc.lower(),parts.path,parts.query,'')) if parts.scheme else raw_url
    except ValueError:location=raw_url
    origin=acquisition.get('chunk_id') or location or 'unlocated:'+evidence['evidence_id']
    coverage=acquisition.get('coverage') or ('retrieved_internal_chunk' if source_type=='knowledge_base' else 'coverage_unknown')
    return {'source_id':'source:'+_identity([source_type,origin]),
        'version_id':'version:'+_identity({'text':evidence['content'],'coverage':coverage,'acquisition':acquisition}),
        'coverage':coverage}


def reconcile_evidence_ledger(state, previous, *, owner_id, session_id):
    """Caller supplies DB-bound identity inside the existing execution transaction."""
    if not owner_id or not session_id:
        raise ValueError('evidence_ledger_requires_database_owner_and_session')
    previous = previous or {}
    if previous and (previous.get('owner_id') != owner_id or previous.get('session_id') != session_id):
        raise ValueError('evidence_ledger_scope_conflict')
    ledger = deepcopy(previous) if previous else {
        'schema_version': VERSION, 'owner_id': owner_id, 'session_id': session_id,
        'sources': {}, 'events': {}, 'recovery_events': {}, 'conflicts': [],
        'storage': 'existing_session_runtime_jsonb',
        'retained_content': 'acquired_normalized_text_not_original_network_bytes',
        'reuse_scope': 'current_task_only', 'automatic_embedding': False,
        'capture_mode': 'request_driven_acquisition_and_checkpoint_event_reconciliation',
    }
    if ledger['schema_version'] != VERSION:
        raise ValueError('unsupported_evidence_ledger_version')
    execution_id = (state.get('session') or {}).get('execution_id')
    for evidence in state.get('collected_evidence', []):
        evidence_id, content = evidence.get('evidence_id'), evidence.get('content')
        if not evidence_id or not isinstance(content, str):
            issue={'reason':'retained_evidence_missing_identity_or_text','evidence_id':evidence_id}
            if issue not in ledger['conflicts']:ledger['conflicts'].append(issue)
            continue
        acquisition=deepcopy(evidence.get('acquisition') or {})
        source_type=evidence.get('source_type','unknown')
        raw_url=evidence.get('source_url')
        retained=retained_evidence_identity(evidence)
        source_id,coverage,version_id=retained['source_id'],retained['coverage'],retained['version_id']
        existing=ledger['events'].get(evidence_id)
        if existing:
            if existing['source_id']!=source_id or existing['version_id']!=version_id:
                # Persisting would destroy the meaning of an existing citation.
                raise ValueError('evidence_identity_changed_content_or_source:'+evidence_id)
            continue
        source=ledger['sources'].setdefault(source_id,{'source_id':source_id,'source_type':source_type,
            'source_url':raw_url,'title':evidence.get('source_title'),'versions':{},'evidence_ids':[]})
        reused=version_id in source['versions']
        if not reused:
            source['versions'][version_id]={'version_id':version_id,'content':content,'character_count':len(content),
                'body_identity':'text:'+_identity(content),
                'format':acquisition.get('format','unknown'),'coverage':coverage,'acquisition':acquisition,
                'first_evidence_id':evidence_id,'collected_at':evidence.get('collected_at'),
                'source_modified_at':acquisition.get('source_last_modified',acquisition.get('last_modified')),
                'source_etag':acquisition.get('source_etag',acquisition.get('etag')),'offset_unit':'retained_text_character',
                'network_bytes_retained':False}
        source['evidence_ids'].append(evidence_id)
        source['latest_observed_version_id']=version_id
        ledger['events'][evidence_id]={'evidence_id':evidence_id,'source_id':source_id,'version_id':version_id,
            'execution_id':execution_id,'collected_at':evidence.get('collected_at'),
            'collector':evidence.get('collected_by'),'channel':evidence.get('source_channel'),'backend':evidence.get('source_backend'),
            'outcome':'reused_retained_version' if reused else 'new_retained_version',
            'coverage':coverage,'content_reference':{'source_id':source_id,'version_id':version_id,'start':0,'end':len(content)}}

    outcomes=state.get('node_outcomes',[])
    latest={outcome['node_id']:outcome for outcome in outcomes if outcome.get('node_id')}
    hard_stop=(state.get('budget_state') or {}).get('hard_stop_reason')
    canceled=state.get('runtime_status')=='canceled'
    for outcome in outcomes:
        if outcome.get('status') not in {'retryable_error','terminal_error','awaiting_approval'}:continue
        identity='intake-outcome:'+_identity([outcome.get('node_id'),outcome.get('tool_call_id'),
            outcome.get('status'),outcome.get('retry_count'),outcome.get('approval_request_id'),outcome.get('error_category')])
        # An outcome identity refers to the original execution, including after resume.
        record=ledger['recovery_events'].setdefault(identity,{'outcome_id':identity,'execution_id':execution_id,**deepcopy(outcome)})
        current=latest.get(outcome.get('node_id'),{})
        record['recovery_status']=('resolved_by_later_success' if current.get('status')=='success' else
            'canceled_no_automatic_retry' if canceled else
            'budget_exhausted_requires_explicit_recovery' if hard_stop else
            'pending_manual_review' if current.get('status')=='terminal_error' else
            'awaiting_original_approval' if current.get('status')=='awaiting_approval' else 'bounded_original_retry_policy')
        record['automatic_new_job_created']=False
        record['hard_stop_reason']=hard_stop
    ledger['last_execution_id']=execution_id
    bodies={}
    for source in ledger['sources'].values():
        for version in source['versions'].values():
            if version.get('body_identity'):
                bodies.setdefault(version['body_identity'],[]).append({'source_id':source['source_id'],
                    'version_id':version['version_id'],'evidence_id':version['first_evidence_id']})
    ledger['body_duplicates']={'method':'identical_retained_text_only','groups':[
        {'body_identity':key,'records':records} for key,records in bodies.items() if len(records)>1],
        'automatic_removal':False,'meaning':'matching_text_not_independent_origin_or_semantic_equivalence'}
    ledger['summary']=ledger_summary(ledger)
    return ledger


def ledger_summary(ledger):
    sources=ledger.get('sources',{});events=ledger.get('events',{})
    versions=[version for source in sources.values() for version in source['versions'].values()]
    recovery=list(ledger.get('recovery_events',{}).values())
    return {'schema_version':VERSION,'sources':len(sources),'retained_versions':len(versions),'intake_events':len(events),
        'discovery_only_versions':sum(value['coverage']=='discovery_only' for value in versions),
        'reused_version_events':sum(value['outcome']=='reused_retained_version' for value in events.values()),
        'unresolved_outcomes':sum(value['recovery_status']!='resolved_by_later_success' for value in recovery),
        'recovered_outcomes':sum(value['recovery_status']=='resolved_by_later_success' for value in recovery),
        'conflicts':len(ledger.get('conflicts',[])),
        'body_duplicate_groups':len((ledger.get('body_duplicates') or {}).get('groups') or [])}


def ledger_view(ledger,*,include_content=False):
    result=deepcopy(ledger)
    from app.external_evidence import archive_version_allowed
    for source in result.get('sources',{}).values():
        for version in source['versions'].values():
            version['archive_available']=archive_version_allowed(source,version,result.get('events') or {})
    if not include_content:
        for source in result.get('sources',{}).values():
            for version in source['versions'].values():version.pop('content',None)
    return result
