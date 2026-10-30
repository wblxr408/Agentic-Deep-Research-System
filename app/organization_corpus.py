"""Declared sample frame, constrained reads and evidence-backed sample decisions."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, UTC
from html import unescape
from typing import Literal
from urllib.parse import urlsplit
from calendar import monthrange, month_abbr, month_name
from datetime import date

from pydantic import Field, field_validator
from app.channels.execution import HttpReader, public_url
from app.channels.models import ChannelError
from app.research_evaluation import OutputType
from app.research_scope import ScopeRecord
from app.research_sources import ResearchSourceScope

CORPUS_VERSION = 'adrs-corpus-v3'
PUBLICATION_ALIAS_VERSIONS = frozenset({'adrs-corpus-v3'})


def date_membership(lower, upper, start, end):
    lower, upper, start, end = map(str, (lower, upper, start, end))
    if upper < start or lower > end:
        return 'outside'
    return 'within' if start <= lower and upper <= end else 'overlaps'


def _primary_bibtex_metadata(text, page_title):
    """One primary BibTeX record and matching page title, with literal fields."""
    from app.bibliography import bibtex_entries
    entries = list(bibtex_entries(text))
    if len(entries) != 1:
        return None
    entry, fields = entries[0], {}
    for match in re.finditer(r'\b(title|year|month)\s*=\s*', entry, re.I):
        start = match.end()
        if start >= len(entry):
            continue
        end, opener = start, entry[start]
        if opener == '{':
            depth, end = 1, start+1
            while end < len(entry) and depth:
                if entry[end] == '{' and entry[end-1] != '\\': depth += 1
                if entry[end] == '}' and entry[end-1] != '\\': depth -= 1
                end += 1
        elif opener == '"':
            end = start+1
            while end < len(entry) and (entry[end] != '"' or entry[end-1] == '\\'): end += 1
            end += 1
        else:
            while end < len(entry) and entry[end] not in ',\n}': end += 1
        raw = entry[match.start():end]
        value = entry[start:end].strip().strip('{}"').replace('{','').replace('}','').strip()
        fields[match.group(1).lower()] = {'value': value, 'quote': raw,
            'start': text.index(entry)+match.start(), 'end': text.index(entry)+end}
    title = fields.get('title', {}).get('value', '')
    normalize = lambda value: re.sub(r'\W+', ' ', value).strip().casefold()
    if not title or normalize(title) not in normalize(page_title) or not re.fullmatch(r'\d{4}', fields.get('year', {}).get('value','')):
        return None
    year = int(fields['year']['value'])
    if year < 1 or year > 9999:
        return None
    months = {value.lower(): index for index in range(1,13) for value in (month_abbr[index], month_name[index], str(index))}
    month = months.get(fields.get('month',{}).get('value','').lower())
    lower = date(year, month or 1, 1)
    upper = date(year, month, monthrange(year, month)[1]) if month else date(year,12,31)
    return {'title': title, 'published_on': lower.isoformat(), 'published_until': upper.isoformat(),
        'date_precision': 'month' if month else 'year', 'literal_fields': fields,
        'basis': 'single_primary_bibtex_and_matching_page_title_not_independent_semantic_review'}


def _publisher_meta_text(raw_html):
    """Retain publisher citation attributes in order, including author affiliations."""
    from html.parser import HTMLParser
    class Metadata(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.fields = []
        def handle_starttag(self, tag, attrs):
            if tag != 'meta' or len(self.fields) >= 120:
                return
            values = dict(attrs)
            name, content = values.get('name','').lower(), values.get('content','')
            if name in {'citation_title','citation_date','citation_publication_date','citation_doi',
                'citation_author','citation_author_institution','citation_journal_title'} and content and len(content) <= 2000:
                self.fields.append((name, ' '.join(content.split())))
    parser = Metadata(); parser.feed(raw_html)
    if len({value for name,value in parser.fields if name=='citation_title'}) != 1:
        return ''
    # Ordered author/institution attributes are retained as source data, not a
    # new inferred/current affiliation. Multiple institutions remain separate.
    lines=[];size=0
    for name,value in parser.fields:
        line=f'{name}: {value}'
        if size+len(line)+1>16000:break
        lines.append(line);size+=len(line)+1
    return '\n'.join(lines)


class CorpusDeclaration(ScopeRecord):
    source_scope: ResearchSourceScope | None = None
    collection_mode: Literal['search_and_seeds', 'seeds_only'] = 'search_and_seeds'
    seed_urls: tuple[str, ...] = Field(default=(), max_length=16)
    search_terms: tuple[str, ...] = Field(default=(), max_length=16)
    output_types: tuple[OutputType, ...] = Field(default=(), max_length=16)
    allow_ocr: bool = False

    @field_validator('seed_urls')
    @classmethod
    def public_seeds(cls, values):
        for url in values:
            public_url(url)
        return values

    @field_validator('search_terms')
    @classmethod
    def bounded_terms(cls, values):
        if any(not term.strip() or len(term) > 500 for term in values):
            raise ValueError('search terms must contain 1–500 characters')
        return values


def canonical_url(url):
    from app.organization_findings import _publication_url
    return _publication_url(url)


def freeze_corpus(declaration: CorpusDeclaration, scope: dict) -> dict:
    from app.config import get_settings
    from app.document_structure import VERSION as DOCUMENT_PARSER_VERSION
    parsing=get_settings().document_parsing
    seeds = list(declaration.seed_urls) or [url for entity in scope['entities'] for url in entity['source_urls'][:1]]
    from app.external_evidence import request_url_identity
    unique = list(dict.fromkeys(request_url_identity(url) for url in seeds))
    if declaration.collection_mode == 'seeds_only' and not unique:
        raise ValueError('seeds_only requires explicit public seed URLs')
    if declaration.source_scope:
        for url in unique:
            declaration.source_scope.admit(url, for_read=False)
    return {**declaration.model_dump(mode='json'), 'rule_version': CORPUS_VERSION,
        'document_parser_policy':{'schema_version':DOCUMENT_PARSER_VERSION,**{key:getattr(parsing,key) for key in ('ocr_enabled','ocr_language','max_ocr_pages','max_chars','timeout_seconds')}},
        'effective_seed_urls': unique, 'duplicate_seed_urls': len(seeds)-len(unique),
        'seed_request_identity':'version_and_query_preserving_v1',
        'effective_search_terms': list(declaration.search_terms) or [scope['topic']],
        'source_policy': declaration.source_scope.snapshot() if declaration.source_scope else None,
        'inclusion': {'organization_types': scope['organization_types'], 'entities': scope['entities'],
            'disciplines': scope['disciplines'], 'topic': scope['topic'],
            'start_date': scope['start_date'], 'end_date': scope['end_date'],
            'output_types': list(declaration.output_types),
            'topic_and_discipline_status': 'requested_labels_not_independently_classified'},
        'exclusion': ['unsupported source', 'publication date outside range', 'unselected output type',
            'unverified identity/date/title retained as candidate, not silently accepted'],
        'full_text_policy': 'read_explicit_sources_only_no_automatic_pdf_following'}


def source_scope(configuration: dict | None):
    raw = ((configuration or {}).get('corpus') or {}).get('source_scope')
    return ResearchSourceScope.model_validate(raw) if raw else None


def corpus_instructions(configuration: dict | None) -> str:
    corpus = (configuration or {}).get('corpus')
    if not corpus:
        return ''
    return ('\n\n样本基线（原始请求，非现实全集）：' + json.dumps(corpus, ensure_ascii=False)
        + '\n提取每个已读出版页的主要成果，包括明确不符合日期或类型的记录，由程序记录排除。'
        '不要因不满足范围而直接遗漏候选；不得把页面导航／参考文献当主要成果。'
        '摘要页不等于全文；只读种子时不要搜索或跳转其他来源。'
        '日期区间是来源精度的上下界，只有月份时不能把月初当实际发表日；边界交叠保持待核。'
        '学科和主题当前为请求口径，缺少独立分类不能声称已核实学科。')


def seed_only_dag(configuration):
    corpus = (configuration or {}).get('corpus') or {}
    if corpus.get('collection_mode') != 'seeds_only':
        return None
    from app.graph.state import DAGDefinition, PlanNode
    urls = requested_seed_urls(configuration)
    nodes = [PlanNode(node_id=f'corpus-source-{index}', node_type='browser', query=url,
        description='读取用户声明的种子；保存样本候选及全文取得状态') for index, url in enumerate(urls)]
    nodes.append(PlanNode(node_id='analyst', node_type='analyst', query='按冻结样本口径评估已读种子',
        depends_on=[node.node_id for node in nodes], parallel=False))
    return DAGDefinition(dag_name='声明种子样本研究（不扩展检索）', nodes=nodes, edges=[])


def requested_seed_urls(configuration):
    declaration=configuration.get('corpus') or {}
    if declaration.get('seed_request_identity'):return declaration['effective_seed_urls']
    original=declaration.get('seed_urls') or [value for entity in configuration.get('scope',{}).get('entities',[]) for value in entity.get('source_urls',[])[:1]]
    return original or declaration.get('effective_seed_urls',[])


def admit_corpus_request(url,configuration):
    from app.external_evidence import request_url_identity
    policy=source_scope(configuration)
    declaration=(configuration or {}).get('corpus') or {}
    if declaration.get('collection_mode')=='seeds_only' and request_url_identity(url) not in {
            request_url_identity(item) for item in requested_seed_urls(configuration)}:
        raise ChannelError('source_out_of_scope')
    validator=policy.admit if policy else public_url
    validator(url)
    return validator


def read_corpus_source(url: str, configuration: dict, *, timeout: float,max_calls:int=8):
    from app.channels.execution import ExecutionBudget
    meter=ExecutionBudget(time.monotonic()+timeout,max_calls)
    started_at=datetime.now(UTC).isoformat()
    try:results=_read_corpus_source(url,configuration,timeout=timeout,on_request=meter.take)
    except Exception as error:
        error.network_call_count=meter.used
        raise
    for result in results:
        result.acquisition={**(result.acquisition or {}),'network_call_count':meter.used,'source_fetched_at':started_at}
    return results


def _read_corpus_source(url: str, configuration: dict, *, timeout: float,on_request=None):
    """Same pinned transport as the SDK: validate each redirect before connecting."""
    from app.graph.state import BrowserResult
    from app.openminion_research import _PageText
    from app.research_documents import read_document
    deadline = time.monotonic() + timeout
    declaration = configuration['corpus']
    from app.external_evidence import source_time_declarations,html_time_declarations
    validator=admit_corpus_request(url,configuration)
    response = HttpReader(url_validator=validator).read(url, timeout=min(30, timeout), max_bytes=8*1024*1024,on_request=on_request)
    if response.status >= 400:
        from app.channels.execution import response_error
        raise response_error(response)
    content_type = response.headers.get('content-type', '').lower()
    title, acquisition = response.url, {'format': 'text', 'coverage': 'metadata_or_page_text', 'truncated': False}
    if response.body.startswith(b'%PDF-'):
        document = read_document(response.body,format='pdf',timeout=max(0.01,deadline-time.monotonic()),
            allow_ocr=declaration.get('allow_ocr',False),frozen_policy=declaration.get('document_parser_policy'))
        text = document.pop('text')
        complete = document.get('coverage')=='full_text' and not document['truncated'] and document['retained_pages'] == document['total_pages']
        acquisition = {**document, 'format': 'pdf', 'coverage': 'full_text' if complete else 'partial_text'}
    elif any(kind in content_type for kind in ('text/', 'json', 'xml')):
        from app.channels.execution import decode_public_text
        text,acquisition['text_encoding']=decode_public_text(response)
        if 'html' in content_type:
            match = re.search(r'<title[^>]*>(.*?)</title\s*>', text, re.I | re.S)
            if match:
                title = unescape(re.sub('<[^>]*>', '', match.group(1))).strip()
            raw_html = text
            acquisition['source_time_declarations']=html_time_declarations(raw_html)
            parser = _PageText(); parser.feed(text)
            # Primary author cards can be outside article/main or inside header.
            # Keep the publisher's ordered citation attributes alongside text.
            metadata_text = _publisher_meta_text(raw_html)
            text = (metadata_text + '\n\n' if metadata_text else '') + parser.text()
            acquisition['text_scope'] = 'primary_page_text_and_publisher_citation_metadata'
            from urllib.parse import urljoin, urlsplit
            acquisition['document_links'] = list(dict.fromkeys(urljoin(response.url,item['href']) for item in parser.links
                if urlsplit(urljoin(response.url,item['href'])).scheme in {'http','https'}
                and '.pdf' in urlsplit(urljoin(response.url,item['href'])).path.lower()))[:100]
            acquisition['public_links'] = list(dict.fromkeys(urljoin(response.url,item['href']) for item in parser.links
                if urlsplit(urljoin(response.url,item['href'])).scheme in {'http','https'}))[:200]
            acquisition['public_link_records'] = [{'url': urljoin(response.url,item['href']), 'label': item.get('text','').strip()}
                for item in parser.links if urlsplit(urljoin(response.url,item['href'])).scheme in {'http','https'}][:200]
            # Separate discovery view: preserve the original public-link order
            # for old contracts; v2 can see article/PDF links past a long menu.
            research_links = sorted(parser.links, key=lambda item: (
                item.get('kind') != 'full_text', '.pdf' not in urlsplit(urljoin(response.url,item['href'])).path.lower(),
                not item.get('primary', False), item.get('navigation', False)))
            acquisition['research_link_records'] = [
                {'url': urljoin(response.url,item['href']), 'label': item.get('text','').strip(),
                 'kind': item.get('kind'), 'navigation': item.get('navigation',False)}
                for item in research_links if urlsplit(urljoin(response.url,item['href'])).scheme in {'http','https'}][:200]
            from app.organization_taxonomy import publisher_abstract_spans
            acquisition['publisher_abstract_spans'] = publisher_abstract_spans(raw_html, text[:160000])
            acquisition['format'] = 'html'
        if len(text) > 160000:
            text = text[:160000]; acquisition['truncated'] = True
        if acquisition['format']=='html':
            from app.document_html import annotate_html
            acquisition['document_structure']=annotate_html(raw_html,text,response.url)
            from app.research_documents import scholarly_text_sections
            sections=scholarly_text_sections(text)
            acquisition['scientific_sections']=sections
            labels=' '.join(section['label'].casefold() for section in sections)
            # Require article metadata and substantial method/result sections;
            # a landing-page abstract/TOC does not establish full article text.
            substantial=lambda terms,minimum=400:any(any(term in section['label'].casefold() for term in terms)
                and section['end']-section['body_start']>=minimum for section in sections)
            # Nature research articles can put results under Main and conclude
            # before Methods. Require substantial bodies, not a navigation TOC.
            nature_main=(urlsplit(response.url).hostname in {'nature.com','www.nature.com'}
                and substantial(('main',),2000) and substantial(('conclusion',)))
            if (not acquisition['truncated'] and 'citation_title:' in text[:16000]
                and substantial(('method','experimental','evaluation','研究方法','实验方法'))
                and (substantial(('result','discussion','实验结果','讨论')) or nature_main)
                and ('references' in labels or '参考文献' in labels)):
                acquisition['coverage']='full_text'
                acquisition['full_text_basis']=('publisher_article_metadata_and_substantial_main_method_conclusion_reference_sections'
                    if nature_main else 'publisher_article_metadata_and_substantial_method_result_reference_sections')
    else:
        raise ChannelError('unsupported_content_type')
    if not text.strip():
        raise ChannelError('empty_content')
    metadata = _primary_bibtex_metadata(text, title)
    if metadata:
        acquisition['publisher_metadata'] = metadata
    acquisition['requested_url'] = url
    acquisition['source_etag']=response.headers.get('etag')
    acquisition['source_last_modified']=response.headers.get('last-modified')
    acquisition['source_cache_control']=response.headers.get('cache-control')
    acquisition['source_expires']=response.headers.get('expires')
    acquisition['source_time_declarations']=[*acquisition.get('source_time_declarations',[]),*source_time_declarations(headers=response.headers)]
    acquisition['final_url'] = response.url
    policy=source_scope(configuration)
    group=policy.group_for(response.url) if policy else 'public_web_unclassified'
    acquisition['source_scope_group']=group
    acquisition['source_identity_status']='configured_domain_membership_not_independent_authenticity_verification'
    if acquisition.get('format')=='pdf' and declaration.get('source_asset_policy')=='adrs-source-media-v2':
        from app.source_assets import retain_acquired_pdf
        acquisition['source_asset']=retain_acquired_pdf(response.url,response.body,text,deadline=deadline)
    return [BrowserResult(url=response.url, title=title, extracted_content=text,
        citations=[response.url], extraction_level='source_text', channel='web', backend='pinned-http',
        collected_at=datetime.now(UTC).isoformat(), acquisition=acquisition)]


def build_corpus(configuration, findings, evidence, tool_histories) -> dict | None:
    declaration = (configuration or {}).get('corpus')
    if not declaration:
        return None
    rows = {}
    def row(url, discovered_at=None):
        key = canonical_url(url)
        if key not in rows:
            rows[key] = {'source_url': key, 'title': None, 'admission_status': 'candidate',
                'record_kind': 'source_lead', 'reason_code': 'not_evaluated', 'evidence_ids': [],
                'full_text_status': 'not_acquired', 'stages': [{'status': 'candidate',
                    'at': discovered_at or configuration['evidence_cutoff']}]}
        return rows[key]
    for url in declaration['effective_seed_urls']:
        row(url)
    for item in evidence:
        if not item.get('source_url'):
            continue
        entry = row(item['source_url'], item.get('collected_at'))
        entry['title'] = item.get('source_title')
        entry['evidence_ids'].append(item['evidence_id'])
        acquisition = item.get('acquisition') or {}
        metadata = acquisition.get('publisher_metadata')
        if metadata:
            entry['publisher_metadata'] = metadata
            bounds = declaration['inclusion']
            membership = date_membership(metadata['published_on'], metadata['published_until'], bounds['start_date'], bounds['end_date'])
            if membership == 'outside':
                entry.update(title=metadata['title'], record_kind='publication_candidate', admission_status='excluded',
                    reason_code='publication_date_out_of_scope', reason='Publisher date bounds outside declared range')
            elif membership == 'overlaps':
                entry.update(title=metadata['title'], record_kind='publication_candidate', admission_status='candidate',
                    reason_code='date_precision_overlaps_scope', reason='Date interval overlaps scope; exact publication day is unknown')
        if acquisition.get('coverage') == 'full_text' and not acquisition.get('truncated'):
            entry['full_text_status'] = 'acquired'
        entry['stages'].append({'status': 'source_acquired', 'at': item.get('collected_at'),
            'coverage': acquisition.get('coverage', 'unclassified_text_not_fulltext_proof')})
    calls = [call for history in tool_histories for call in history.get('tool_calls', [])]
    for history in calls:
        safety = history.get('safety_json') or {}
        for lead in safety.get('rejected_sources', []):
            if lead.get('url'):
                entry = row(lead['url']); entry.update(admission_status='excluded', reason_code='source_out_of_scope')
        args = history.get('args') or history.get('args_json') or {}
        url = args.get('url') or args.get('query')
        if isinstance(url, str) and url.startswith('https://') and history.get('status') == 'error':
            row(url)['acquisition_error'] = history.get('error_category') or history.get('error') or 'source_read_failed'
    scoped = (findings or {}).get('scope_result') or {}
    for output in scoped.get('outputs', []):
        for url in output['source_urls']:
            entry = row(url)
            entry.update(admission_status='accepted', record_kind='publication', reason_code='source_supported_in_scope',
                title=output['title'], output_id=output['output_id'])
    for pending in (findings or {}).get('pending_records', []):
        proposed = pending.get('proposed_record') or {}
        proof = proposed.get('title_proof') or {}
        source = next((item for item in evidence if item['evidence_id'] == proof.get('evidence_id')), None)
        if not source or not source.get('source_url'):
            continue
        entry = row(source['source_url'])
        if entry['admission_status'] in {'accepted', 'excluded'}:
            continue
        code = pending.get('reason_code') or 'unverified_publication_record'
        entry.update(title=pending.get('title') or entry['title'], record_kind='publication_candidate',
            admission_status='excluded' if code in {'publication_date_out_of_scope', 'output_type_out_of_scope'} else 'candidate',
            reason_code=code, reason=pending['reason'])
    evaluated_at = datetime.now(UTC).isoformat()
    for entry in rows.values():
        entry['evidence_ids'] = list(dict.fromkeys(entry['evidence_ids']))
        entry['stages'].append({'status': entry['admission_status'], 'at': evaluated_at, 'reason_code': entry['reason_code']})
    records = list(rows.values())
    accepted = [entry for entry in records if entry['admission_status'] == 'accepted']
    accepted_ids = {entry['output_id'] for entry in accepted}
    full_text_ids = {entry['output_id'] for entry in accepted if entry['full_text_status'] == 'acquired'}
    declared_version = declaration.get('rule_version', 'adrs-corpus-v2')
    return {'schema_version': declared_version, 'declaration': declaration,
        'request_frozen_at': configuration['evidence_cutoff'], 'evaluated_at': evaluated_at,
        'coverage': 'declared_retrieved_sample_not_real_world_census', 'records': records,
        'executed_queries': [{'requested_query': (call.get('args') or {}).get('query'),
            'executed_query': (call.get('safety_json') or {}).get('source_query', (call.get('args') or {}).get('query')),
            'status': call.get('status'), 'started_at': call.get('started_at'), 'completed_at': call.get('completed_at')}
            for call in calls if call.get('tool_name') == 'execute_search'],
        'counts': {'source_candidates': len(records), 'accepted_source_records': len(accepted),
            'accepted_publications': len(accepted_ids),
            'accepted_research_families': (scoped.get('summary') or {}).get('research_family_count', 0),
            'excluded_candidates': sum(entry['admission_status'] == 'excluded' for entry in records),
            'pending_candidates': sum(entry['admission_status'] == 'candidate' for entry in records),
            'accepted_without_full_text': len(accepted_ids - full_text_ids),
            'duplicate_seed_urls': declaration['duplicate_seed_urls']},
        'counting_unit': ('canonical_source_urls_for_candidates; explicitly_linked_publication_ids_for_publications; explicit_family_links_only'
            if declared_version in PUBLICATION_ALIAS_VERSIONS else
            'canonical_primary_source_url_for_candidates_and_publications; explicit_family_links_only'),
        'limits': ['检索式和纳入条件属于声明，学科／主题尚未独立分类。',
            '页面／检索线索不等于发表记录；采纳仅指通过本次原文字面、日期和归属检查。',
            '未取得全文不等于不可获得；不会自动跳转PDF或扩大来源。']}


def corpus_markdown(corpus):
    if not corpus:
        return ''
    names = {'candidate': '候选待核', 'accepted': '已采纳', 'excluded': '已排除'}
    lines = ['\n\n## 样本基线与流转', '仅相对于声明和实际取得材料描述覆盖，不是现实成果全集。',
        f"请求冻结：{corpus['request_frozen_at']}；评估：{corpus['evaluated_at']}；计数：{corpus['counting_unit']}。",
        '| 来源候选 | 状态 | 全文 | 原因 |', '| --- | --- | --- | --- |']
    def safe(value):
        return str(value).replace('|', '\\|').replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;')
    for item in corpus['records']:
        lines.append(f"| {safe(item['title'] or item['source_url'])} | {names[item['admission_status']]} | {'已取得全文' if item['full_text_status']=='acquired' else '未取得全文'} | {safe(item['reason_code'])} |")
    lines.extend('- ' + value for value in corpus['limits'])
    return '\n'.join(lines) + '\n'
