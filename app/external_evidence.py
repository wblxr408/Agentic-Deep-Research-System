"""Task-local web reuse and time declarations, independent of fact support."""
from __future__ import annotations

from datetime import UTC,datetime
from email.utils import parsedate_to_datetime
import re
from urllib.parse import urlsplit,urlunsplit

VERSION='adrs-external-evidence-v1'
PUBLIC_TRANSPORTS=frozenset({'pinned-http','public-browser'})


def request_url_identity(url):
    """Never fold document versions or drop/reorder query parameters."""
    parsed=urlsplit(url)
    if parsed.scheme.lower() not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('public_source_request_identity_requires_http_url_without_credentials')
    host=parsed.hostname.lower().encode('idna').decode('ascii')
    if ':' in host:host='['+host+']'
    if parsed.port is not None and parsed.port!={'http':80,'https':443}[parsed.scheme.lower()]:host+=':'+str(parsed.port)
    return urlunsplit((parsed.scheme.lower(),host,parsed.path or '/',parsed.query,''))


def observed_instant(value):
    if not isinstance(value,str):return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:return None


def freshness(evidence,understanding,*,now=None,for_cache=False):
    current=now or datetime.now(UTC)
    temporal=(understanding or {}).get('temporal') or {}
    policy=(understanding or {}).get('external_evidence') or {}
    if policy and policy.get('version')!=VERSION:return {'status':'unsupported_external_evidence_policy','usable':False}
    if not for_cache and temporal.get('mode')!='realtime':return {'status':'retained_historical_observation','usable':True}
    maximum=policy.get('task_cache_hours',24) if for_cache else temporal.get('max_age_hours')
    if maximum is None:return {'status':'freshness_policy_unavailable','usable':False}
    if for_cache and temporal.get('mode')=='realtime':maximum=min(maximum,temporal.get('max_age_hours') or 0)
    acquisition=evidence.get('acquisition') or {}
    fetched=observed_instant(acquisition.get('source_fetched_at') or evidence.get('collected_at'))
    if fetched is None:return {'status':'acquisition_time_unknown_or_legacy_naive','usable':False}
    age=(current-fetched).total_seconds()
    control=str(acquisition.get('source_cache_control') or '').lower()
    if for_cache and any(token in control for token in ('no-store','no-cache')):
        return {'status':'upstream_requires_fresh_request','usable':False,'age_seconds':age}
    seconds=max(0,float(maximum)*3600)
    if for_cache:
        limits=re.findall(r'(?:^|,)\s*max-age\s*=\s*"?(\d+)',control)
        if limits:seconds=min(seconds,min(map(int,limits)))
    if for_cache and acquisition.get('source_expires'):
        try:
            expires=parsedate_to_datetime(acquisition['source_expires'])
            if expires.tzinfo:seconds=min(seconds,max(0,(expires-fetched).total_seconds()))
        except (ValueError,TypeError,OverflowError):pass
    usable=0<=age<seconds
    return {'status':'within_acquisition_age' if usable else 'acquisition_expired_or_future',
        'usable':usable,'age_seconds':age,'maximum_age_seconds':seconds,
        'meaning':'fetch_age_not_publication_age_or_fact_verification'}


def reusable_task_source(evidence,url,understanding):
    if evidence.get('source_type')!='web' or evidence.get('source_backend') not in PUBLIC_TRANSPORTS:
        return False
    acquisition=evidence.get('acquisition') or {}
    if acquisition.get('coverage') in {'discovery_only','search_snippet'} or not evidence.get('content','').strip():return False
    return bool(matches_request(evidence,url) and freshness(evidence,understanding,for_cache=True)['usable'])


def matches_request(evidence,url):
    acquisition=evidence.get('acquisition') or {}
    try:requested=request_url_identity(url)
    except ValueError:return False
    for item in (evidence.get('source_url'),acquisition.get('requested_url'),acquisition.get('final_url')):
        try:
            if item and request_url_identity(item)==requested:return True
        except ValueError:continue
    return False


def archive_version_allowed(source,version,events):
    event=events.get(version.get('first_evidence_id')) or {}
    from app.data_governance import source_observation
    privacy=source_observation({'source_type':source.get('source_type'),'source_url':source.get('source_url'),
        'source_backend':event.get('backend'),'source_channel':event.get('channel'),'collected_by':event.get('collector'),
        'content':version.get('content',''),'acquisition':version.get('acquisition')})
    return bool(source.get('source_type')=='web' and event.get('backend') in PUBLIC_TRANSPORTS
        and privacy['data_class']=='public'
        and version.get('coverage') in {'full_text','partial_text','metadata_or_page_text','page_text'}
        and version.get('character_count',0)>0)


def source_time_declarations(metadata=None,headers=None):
    metadata=metadata or {};headers=headers or {};values=[]
    for key,kind in {'article:published_time':'publication','citation_date':'publication',
        'citation_publication_date':'publication','datePublished':'publication',
        'article:modified_time':'update','dateModified':'update','event:start_time':'event'}.items():
        raw=metadata.get(key)
        if isinstance(raw,str) and raw.strip():values.append({'kind':kind,'field':key,'raw':raw[:300],
            'origin':'page_metadata','status':'source_declared_not_independently_verified'})
    for key in ('date','last-modified','expires'):
        if headers.get(key):values.append({'kind':'http_response' if key=='date' else 'http_resource_update' if key=='last-modified' else 'http_cache_expiry',
            'field':key,'raw':headers[key][:300],'origin':'response_header','status':'transport_metadata_not_publication_or_event_date'})
    return values


def html_time_declarations(raw_html):
    from html.parser import HTMLParser
    class Dates(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=True);self.values=[]
        def handle_starttag(self,tag,attrs):
            if tag!='meta' or len(self.values)>=24:return
            attributes=dict(attrs);name=attributes.get('name') or attributes.get('property')
            if name and isinstance(attributes.get('content'),str):
                self.values.extend(source_time_declarations({name:attributes['content']}))
    parser=Dates();parser.feed(raw_html)
    return parser.values


def public_synthesis_gap(evidence,state):
    if evidence.get('source_type')!='web':return None
    from app.organization_corpus import source_scope
    from app.channels.execution import public_url
    from app.channels.models import ChannelError
    try:
        policy=source_scope(state.get('organization_research'))
        if policy:policy.admit(evidence.get('source_url') or '',for_read=(evidence.get('acquisition') or {}).get('coverage')!='discovery_only')
        else:public_url(evidence.get('source_url') or '')
    except (ChannelError,ValueError,TypeError):return 'current_public_source_scope_not_established'
    observation=freshness(evidence,state.get('query_understanding'))
    if not observation['usable']:return observation['status']
    return None


def collect_public_source(url,configuration,understanding,agent,*,owner_id,max_calls,timeout_seconds):
    """Source text first; one optional bounded DOM read, no model decision."""
    import time
    from app.organization_corpus import read_corpus_source,source_scope
    from app.channels.models import ChannelError
    policy=(understanding or {}).get('external_evidence') or {}
    mode=policy.get('read_mode','auto')
    agent.last_channel_attempts=[]
    if policy and policy.get('version')!=VERSION:raise ChannelError('external_evidence_contract_unavailable')
    if mode not in {'auto','source','rendered'}:raise ChannelError('unsupported_web_read_mode')
    config=configuration or {'corpus':{'collection_mode':'search_and_seeds','allow_ocr':False,
        'document_parser_policy':policy.get('document_parser_policy')}}
    scoped=bool(source_scope(config) or config['corpus'].get('collection_mode')=='seeds_only')
    if scoped and mode=='rendered':raise ChannelError('rendered_source_scope_unavailable')
    from app.channels.catalog import route_query
    channel,operation,_=route_query(url)
    from app.data_governance import sensitive_url
    credentialed=sensitive_url(url)
    if credentialed and mode=='rendered':raise ChannelError('credential_url_requires_direct_pinned_source_reader')
    if credentialed:mode='source'
    if mode=='auto' and not scoped and channel!='web' and operation=='read':
        return agent.execute_browse(url,owner_id=owner_id,max_calls=max_calls,timeout_seconds=timeout_seconds,analyze_page=False)
    deadline=time.monotonic()+timeout_seconds;attempts=[];results=[]
    try:
        if mode!='rendered':
            try:
                results=read_corpus_source(url,config,timeout=max(0,deadline-time.monotonic()),max_calls=max_calls)
                used=max((item.acquisition or {}).get('network_call_count',0) for item in results)
                attempts.append({'channel':'web','backend':'pinned-http','status':'success','call_count':used,'result_count':len(results)})
            except Exception as error:
                used=getattr(error,'network_call_count',0)
                attempts.append({'channel':'web','backend':'pinned-http','status':'failed','call_count':used,
                    'result_count':0,'error_category':error.category if isinstance(error,ChannelError) else type(error).__name__})
                if mode!='auto' or scoped or not isinstance(error,ChannelError) or error.category!='empty_content':raise
            requires_dom=not results or any((item.acquisition or {}).get('format')=='html'
                and len(item.extracted_content)<2000 and any(marker in item.extracted_content.casefold()
                    for marker in ('enable javascript','javascript is required','请开启javascript','请启用javascript')) for item in results)
            if mode=='source' or scoped or not requires_dom:
                agent.last_channel_attempts=attempts
                return results
        used=sum(item['call_count'] for item in attempts)
        if used>=max_calls or time.monotonic()>=deadline:
            if results:
                agent.last_channel_attempts=attempts
                for item in results:item.acquisition={**(item.acquisition or {}),'rendering_gap':'original_transport_allowance_insufficient'}
                return results
            raise ChannelError('budget_exceeded')
        rendered=agent.execute_browse(url,owner_id=owner_id,max_calls=max_calls-used,
            timeout_seconds=max(0,deadline-time.monotonic()),analyze_page=False,force_browser=True)
        attempts.extend(agent.last_channel_attempts)
        agent.last_channel_attempts=attempts
        acquired=[item for item in rendered if item.extracted_content.strip() and not item.error_message]
        if results and not acquired:
            for item in results:item.acquisition={**(item.acquisition or {}),'rendering_gap':'rendered_source_text_unavailable'}
            return results
        return [*results,*(acquired or rendered)]
    except Exception as error:
        current=getattr(agent,'last_channel_attempts',[]) or []
        error.channel_attempts=[*attempts,*[item for item in current if item not in attempts]]
        raise
