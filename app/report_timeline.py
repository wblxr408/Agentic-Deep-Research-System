"""Publication events from accepted records, retaining date precision and proofs."""
from __future__ import annotations

from copy import deepcopy
from datetime import date

POLICY='adrs-source-publication-events-v1'
PANEL_SIZE=8


def date_label(lower,upper,precision):
    start,end=date.fromisoformat(lower),date.fromisoformat(upper)
    if start>end:raise ValueError('event_date_bounds_reversed')
    if precision=='year' and start.year==end.year:return str(start.year)+'（年精度）'
    if precision=='month' and (start.year,start.month)==(end.year,end.month):return start.isoformat()[:7]+'（月精度）'
    if precision=='day' and start==end:return start.isoformat()
    raise ValueError('event_date_precision_invalid')


def build_timeline(findings,citations,used):
    """Select cited works; date-only sources become explicit chart citations."""
    refs={row.get('locator',{}).get('evidence_id'):row['citation_id'] for row in citations
        if isinstance(row.get('locator'),dict) and row.get('citation_id')}
    metadata=findings.get('publication_metadata') or {}
    cards={row['output_id']:row for row in (findings.get('technical_reading') or {}).get('cards',[])}
    events=[];missing=[];required=[]
    for output in (findings.get('scope_result') or {}).get('outputs',[]):
        meta=metadata.get(output['output_id']) or {};binding=meta.get('publication_event') or {}
        # A catalog record is not a request to illustrate uncited material.
        if not any(refs.get(key) in used for key in meta.get('evidence_ids',[])):continue
        required.append(output['output_id'])
        if binding.get('policy')!=POLICY:
            missing.append({'output_id':output['output_id'],'reason':'publication_event_proof_unavailable'});continue
        proofs=[binding['title_proof'],*binding['date_proofs']]
        if not all(refs.get(proof['evidence_id']) for proof in proofs):
            missing.append({'output_id':output['output_id'],'reason':'publication_event_citation_unavailable'});continue
        lower,upper=output['published_on'],output.get('published_until') or output['published_on']
        if (binding['title']!=output['title'] or binding['lower']!=lower or binding['upper']!=upper
                or binding['precision']!=output['date_precision']):
            missing.append({'output_id':output['output_id'],'reason':'publication_event_record_changed'});continue
        detail=(cards.get(output['output_id'],{}).get('fields') or {}).get('mechanism') or {}
        detail_proofs=detail.get('proofs') or []
        detail_text=detail.get('text') if detail_proofs and all(refs.get(p['evidence_id']) for p in detail_proofs) else ''
        event={'event_id':output['output_id'],'label':output['title'],'lower':lower,'upper':upper,
            'precision':output['date_precision'],'date_label':date_label(lower,upper,output['date_precision']),
            'date_basis':binding['basis'],'date_kind':'preprint_version' if 'preprint_version' in binding['basis'] else 'publication',
            'date_binding':deepcopy(binding),'detail':detail_text or '',
            'detail_proofs':deepcopy(detail_proofs) if detail_text else [],
            'citation_ids':list(dict.fromkeys(refs[p['evidence_id']] for p in
                [*proofs,*(detail_proofs if detail_text else [])]))}
        events.append(event)
    events.sort(key=lambda row:(row['lower'],row['upper'],row['event_id']))
    if not events:return None,missing
    return {'chart_id':'publication_events','title':('已引用成果的发表与机制时间轴'
            if any(event['detail'] for event in events) else '已引用成果的发表时间轴'),'module':'evolution',
        'kind':'timeline','unit_label':'发表事件（保留原日期精度）','events':events,'event_policy':POLICY,
        'total_events':len(events),'missing_events':missing,'required_event_ids':required,
        'citation_ids':list(dict.fromkeys(ref for row in events for ref in row['citation_ids'])),
        'note':'按日期区间排列已引用成果，重叠区间不确定先后；预印本版本日期不作为首次发布。'
            '横线表示日期精度范围，未连接事件；先后不证明继承、因果或技术成熟度。'},missing


def validate_event(event,findings,evidence,citation_evidence):
    """Bind rendered dates to accepted work metadata and actual retained spans."""
    output=next((row for row in (findings.get('scope_result') or {}).get('outputs',[])
        if row['output_id']==event['event_id']),None)
    binding=((findings.get('publication_metadata') or {}).get(event['event_id']) or {}).get('publication_event')
    if not output or not binding or binding.get('policy')!=POLICY or event.get('date_binding')!=binding:
        raise ValueError('publication_event_binding_changed')
    if (event['label']!=output['title'] or event['lower']!=output['published_on']
            or event['upper']!=(output.get('published_until') or output['published_on'])
            or event['precision']!=output['date_precision'] or event['date_basis']!=binding['basis']
            or binding['lower']!=event['lower'] or binding['upper']!=event['upper']
            or binding['precision']!=event['precision'] or binding['title']!=event['label']
            or event['date_label']!=date_label(event['lower'],event['upper'],event['precision'])):
        raise ValueError('publication_event_record_changed')
    expected_kind='preprint_version' if 'preprint_version' in binding['basis'] else 'publication'
    if event['date_kind']!=expected_kind:raise ValueError('publication_event_date_kind_changed')
    proofs=[binding['title_proof'],*binding['date_proofs']]
    if not binding['date_proofs']:raise ValueError('publication_event_date_proof_missing')
    if event.get('detail'):
        card=next((row for row in (findings.get('technical_reading') or {}).get('cards',[])
            if row['output_id']==event['event_id']),{})
        field=(card.get('fields') or {}).get('mechanism') or {}
        if event['detail']!=field.get('text') or event.get('detail_proofs')!=field.get('proofs'):
            raise ValueError('publication_event_mechanism_changed')
        proofs+=event['detail_proofs']
    retained=set()
    for proof in proofs:
        source=evidence.get(proof['evidence_id']);start,end=proof.get('start'),proof.get('end')
        if (not source or type(start) is not int or type(end) is not int
                or not 0<=start<end<=len(source.content) or source.content[start:end]!=proof.get('quote')
                or source.source_url!=proof.get('source_url')
                or (source.acquisition or {}).get('coverage')=='discovery_only'):
            raise ValueError('publication_event_source_span_changed')
        retained.add(proof['evidence_id'])
    if {citation_evidence.get(ref) for ref in event['citation_ids']}!=retained:
        raise ValueError('publication_event_citations_changed')
