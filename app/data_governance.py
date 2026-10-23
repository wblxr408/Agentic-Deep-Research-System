"""Deterministic data boundaries for the existing root/tools/provider gateway."""
from __future__ import annotations

import re
from typing import Literal
from urllib.parse import parse_qsl,urlsplit,urlunsplit,urlencode

from pydantic import Field,model_validator
from app.research_scope import ScopeRecord

VERSION='adrs-data-governance-v1'
DataClass=Literal['public','internal','confidential','regulated']
RANK={'public':0,'internal':1,'private':1,'confidential':2,'regulated':3}
ANONYMOUS_BACKENDS={'pinned-http','public-browser','duckduckgo','bing-rss','github-api','v2ex-api',
    'bilibili-api','feed','xiaoyuzhou-page','jina','exa-mcp'}
PUBLIC_CHANNELS={'web','exa','rss','v2ex'}
URL_PATTERN=re.compile(r'https?://[^\s<>"\x27\\]+',re.I)
SECRET_PATTERN=re.compile(r'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})\b|'
    r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|'
    r'(?i:authorization\s*[:=]\s*(?:bearer|basic)\s+[A-Za-z0-9_./+=-]{16,})')
RESTRICTION_PATTERN=re.compile(r'(?im)^\s*(?:strictly confidential|confidential|internal use only|'
    r'仅供内部使用|机密资料|绝密资料)\s*[。.！!]*\s*$')
SENSITIVE_PARAMETER=re.compile(r'(?i)^(?:access[_-]?token|refresh[_-]?token|api[_-]?key|token|key|secret|'
    r'client_secret|password|passwd|authorization|auth|signature|sig|jwt|session(?:id|_id)?|sid|'
    r'x-amz-(?:credential|signature|security-token)|x-goog-(?:credential|signature)|samlresponse|ticket)$')


class DataPolicy(ScopeRecord):
    input_class:DataClass='public'
    max_model_class:DataClass='internal'
    public_search_queries:tuple[str,...]=Field(default=(),max_length=16)

    @model_validator(mode='after')
    def choices(self):
        if RANK[self.input_class]>RANK[self.max_model_class]:raise ValueError('input_class_exceeds_requested_model_egress_ceiling')
        if any(not value.strip() or len(value)>1800 or any(ord(c)<32 for c in value) for value in self.public_search_queries):
            raise ValueError('public_search_queries_require_bounded_single_line_values')
        if len(set(self.public_search_queries))!=len(self.public_search_queries):raise ValueError('duplicate_public_search_query')
        return self


def maximum(*classes):
    return max((value for value in classes if value in RANK),key=lambda value:RANK[value],default='public')


def model_class(value):
    return 'private' if value=='internal' else value


def sensitive_url(url):
    try:
        parsed=urlsplit(url)
        return bool(parsed.username or parsed.password or any(SENSITIVE_PARAMETER.fullmatch(key) for key,_ in parse_qsl(parsed.query,keep_blank_values=True))
            or re.search(r'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\.',parsed.path))
    except (ValueError,TypeError):return True


def display_url(url):
    """Presentation only; never use this redacted URL to fetch another resource."""
    try:
        parsed=urlsplit(url)
        if parsed.scheme not in {'http','https'}:return url
        host=parsed.hostname or ''
        if ':' in host:host='['+host+']'
        authority=host+(':'+str(parsed.port) if parsed.port else '')
        query=urlencode([(key,'[redacted]' if SENSITIVE_PARAMETER.fullmatch(key) else value)
            for key,value in parse_qsl(parsed.query,keep_blank_values=True)])
        path=re.sub(r'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+','[redacted]',parsed.path)
        return urlunsplit((parsed.scheme,authority,path,query,''))
    except (ValueError,TypeError):return '[restricted source URL]'


def scrub_urls(text):
    return URL_PATTERN.sub(lambda match:display_url(match[0]) if sensitive_url(match[0]) else match[0],text)


def text_class(text):
    scrubbed=scrub_urls(str(text or ''))
    if SECRET_PATTERN.search(scrubbed):return 'confidential','access_credential_literal'
    if RESTRICTION_PATTERN.search(scrubbed):return 'confidential','explicit_document_restriction_banner'
    if scrubbed!=text:return 'internal','credential_bearing_source_url'
    return 'public','no_detected_restriction_signal_not_a_license_or_authenticity_verdict'


def classify_source(*,source_type='web',backend=None,channel=None,url=None,content='',declared=None):
    content_class,reason=text_class(content)
    inferred='internal' if source_type!='web' or backend not in ANONYMOUS_BACKENDS else 'public'
    reasons=[reason]
    if inferred=='internal':reasons.append('internal_or_authenticated_or_unknown_transport')
    if url and sensitive_url(url):inferred=maximum(inferred,'internal');reasons.append('source_access_capability_in_url')
    # An untrusted public label can never downgrade observed restrictions.
    inferred=maximum(inferred,content_class,declared)
    return {'version':VERSION,'data_class':inferred,'reasons':reasons,
        'source_channel':channel,'basis':'trusted_transport_plus_literal_signals_and_explicit_higher_class',
        'license_status':'not_established','semantic_dlp':'not_performed'}


def _identity(value):
    from app.query_understanding import identity
    return identity(value)


def read_identity(url):
    from app.external_evidence import request_url_identity
    return _identity(request_url_identity(url))


def source_observation(item):
    acquisition=item.get('acquisition') or {}
    observed=classify_source(source_type=item.get('source_type') if item.get('collected_by') in {'search','browser'} else 'internal',
        backend=item.get('source_backend'),channel=item.get('source_channel'),url=item.get('source_url'),
        content=item.get('content',''),declared=(acquisition.get('data_governance') or {}).get('data_class'))
    if any(sensitive_url(value) for value in (acquisition.get('requested_url'),acquisition.get('final_url')) if value):
        observed['data_class']=maximum(observed['data_class'],'internal')
        observed['reasons'].append('requested_or_redirected_access_capability')
    return observed


def _url_values(value):
    if isinstance(value,dict):
        for item in value.values():yield from _url_values(item)
    elif isinstance(value,(tuple,list)):
        for item in value:yield from _url_values(item)
    elif isinstance(value,str):
        yield from (match[0] for match in URL_PATTERN.finditer(value))


def freeze_policy(query,policy,limits,organization,snapshot):
    options=policy if isinstance(policy,DataPolicy) else DataPolicy.model_validate(policy or {})
    declared=options.input_class
    initial=maximum(declared,'internal' if limits.get('use_internal_docs') or any(name not in PUBLIC_CHANNELS for name in limits.get('channels',[])) else 'public',text_class(query)[0])
    urls=list(dict.fromkeys([*_url_values(query),*_url_values(organization or {})]))[:256]
    if any(sensitive_url(url) for url in urls):initial=maximum(initial,'internal')
    queries=list(options.public_search_queries)
    if declared=='public' and text_class(query)[0]=='public':
        queries.append(query)
        for entity in (snapshot.get('slots') or {}).get('entities',[])[:40]:queries.append(entity['name']+' '+query)
    from app.query_rewriting import search_route
    from app.channels.catalog import route_query
    approved=[]
    for base in dict.fromkeys(queries):
        if text_class(base)[0]!='public':raise ValueError('declared_public_search_contains_access_credentials_or_restrictions')
        route=search_route(base,snapshot,remaining_calls=1000,remaining_seconds=300)
        approved.extend(route_query(item['query'])[2] for item in route['variants'])
    body={'version':VERSION,'policy':options.model_dump(mode='json'),'initial_class':initial,
        'approved_search_query_ids':sorted({_identity(value.strip()) for value in approved}),
        'approved_read_url_ids':sorted({read_identity(url) for url in urls if urlsplit(url).scheme in {'http','https'}}),
        'classification_semantics':'egress_restriction_not_publication_license_or_factual_support'}
    return {**body,'policy_id':_identity(body)}


def frozen_policy(snapshot):
    if not snapshot:return {'version':VERSION,'policy':DataPolicy().model_dump(mode='json'),'initial_class':'internal',
        'approved_search_query_ids':[],'approved_read_url_ids':[],'legacy':True}
    body={key:value for key,value in snapshot.items() if key!='policy_id'}
    if body.get('version')!=VERSION or _identity(body)!=snapshot.get('policy_id'):raise ValueError('frozen_data_governance_contract_invalid')
    DataPolicy.model_validate(body['policy'])
    return snapshot


def effective_context(state):
    policy=frozen_policy((state.get('query_understanding') or {}).get('data_governance'))
    level=policy['initial_class'];reasons=[]
    for item in state.get('collected_evidence') or []:
        observed=source_observation(item)
        level=maximum(level,observed['data_class'])
        if observed['data_class']!='public':reasons.append({'evidence_id':item.get('evidence_id'),'data_class':observed['data_class'],'reasons':observed['reasons']})
    return {'version':VERSION,'data_class':level,'model_class':model_class(level),
        'max_model_class':policy['policy']['max_model_class'],'policy_id':policy.get('policy_id'),
        'nonpublic_sources':reasons}


def network_context(state):
    policy=frozen_policy((state.get('query_understanding') or {}).get('data_governance'))
    context=effective_context(state);initial=policy['approved_read_url_ids'];reads=set()
    for item in state.get('collected_evidence') or []:
        source=source_observation(item)
        if source['data_class']=='public':
            for url in _url_values({'url':item.get('source_url'),'content':item.get('content',''),'acquisition':item.get('acquisition')}):
                try:reads.add(read_identity(url))
                except ValueError:continue
    return {**context,'approved_search_query_ids':policy['approved_search_query_ids'],
        'approved_read_url_ids':list(dict.fromkeys([*initial,*sorted(reads)]))[:1024]}


def authorize_network(query,context,*,operation='search'):
    from app.channels.models import ChannelError
    if SECRET_PATTERN.search(scrub_urls(query)):raise ChannelError('access_credentials_cannot_be_external_query_data')
    if operation=='search' and any(sensitive_url(url) for url in _url_values(query)):
        raise ChannelError('credential_url_requires_direct_read_not_search_or_proxy')
    if not context or context.get('data_class')=='public':return
    field='approved_read_url_ids' if operation=='read' else 'approved_search_query_ids'
    identifier=read_identity(query) if operation=='read' else _identity(query.strip())
    if identifier not in context.get(field,[]):raise ChannelError('private_context_network_query_not_authorized')


def provider_request(request,context,route):
    from app.llm_budget import TokenBudgetExceeded
    context=context or {'data_class':'internal','max_model_class':'internal'}
    required=context['data_class']
    if RANK[required]>RANK[context['max_model_class']]:raise TokenBudgetExceeded('task_model_data_class_ceiling_exceeded')
    if route and RANK.get(route.get('data_class'),-1)<RANK[required]:raise TokenBudgetExceeded('model_route_data_class_insufficient')
    redactions=0
    def secure(value):
        nonlocal redactions
        if isinstance(value,str):
            cleaned=scrub_urls(value)
            if SECRET_PATTERN.search(cleaned):raise TokenBudgetExceeded('access_credentials_blocked_before_model_dispatch')
            redactions+=int(cleaned!=value)
            return cleaned
        if isinstance(value,list):return [secure(item) for item in value]
        if isinstance(value,dict):
            if any(isinstance(key,str) and SECRET_PATTERN.search(key) for key in value):
                raise TokenBudgetExceeded('access_credentials_blocked_before_model_dispatch')
            return {key:secure(item) for key,item in value.items()}
        return value
    secured=secure(request)
    return secured,{'version':VERSION,'data_class':required,'credential_url_messages_redacted':redactions,
        'credential_literals_sent':False,'policy_id':context.get('policy_id')}


def owned_request_url(value,state):
    """Resolve only exact redacted copies of URLs supplied by this task owner."""
    from app.external_evidence import request_url_identity
    try:target=request_url_identity(value)
    except ValueError:return value
    originals=list(dict.fromkeys([*_url_values(state.get('user_query','')),*_url_values(state.get('organization_research') or {})]))[:256]
    matches=[]
    for original in originals:
        if not sensitive_url(original):continue
        try:
            if request_url_identity(display_url(original))==target:matches.append(original)
        except ValueError:continue
    if len(matches)>1:raise ValueError('redacted_source_url_ambiguous_between_owned_resources')
    return matches[0] if matches else value
