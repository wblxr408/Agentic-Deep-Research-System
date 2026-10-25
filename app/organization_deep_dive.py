"""Bounded, evidence-located technical cards for representative publications."""
from __future__ import annotations

import json
import re
from typing import Literal
from urllib.parse import quote

from pydantic import Field
from app.research_scope import Identifier, ScopeRecord
from app.organization_relationships import RelationProof

VERSION='adrs-technical-cards-v1'
FIELDS={'problem':'研究问题','prior_limitations':'已有方法局限','method_overview':'方法概览','mechanism':'机制／架构',
    'innovation':'创新主张','experimental_design':'实验设计','baselines':'对照基线','conditions':'适用／复现条件',
    'results':'来源报告的结果','limitations':'结果边界与局限'}
FieldName=Literal['problem','prior_limitations','method_overview','mechanism','innovation','experimental_design','baselines','conditions','results','limitations']


class TechnicalStatement(ScopeRecord):
    text:str=Field(min_length=3,max_length=2400)
    proofs:tuple[RelationProof,...]=Field(min_length=1,max_length=5)


class FigureReference(ScopeRecord):
    label:str=Field(min_length=2,max_length=120)
    proof:RelationProof
    page:int|None=Field(default=None,ge=1,le=80)


class TechnicalCardProposal(ScopeRecord):
    output_id:Identifier
    fields:dict[FieldName,TechnicalStatement]=Field(default_factory=dict,max_length=10)
    figure_references:tuple[FigureReference,...]=Field(default=(),max_length=20)


class TechnicalPreviewRequest(ScopeRecord):
    technical_cards:tuple[TechnicalCardProposal,...]=Field(default=(),max_length=20)


def technical_instructions(configuration):
    if 'deep_dive' not in (configuration or {}).get('modules',[]):return ''
    return '''\nRepresentative technical reading: add "technical_cards" INSIDE organization_data.
Shape: [{"output_id":"accepted proposed publication ID","fields":{"problem":{"text":"source-grounded summary","proofs":[{"evidence_id":"ev-ID","quote":"literal original excerpt"}]},"method_overview":{"text":"brief method overview","proofs":[{"evidence_id":"ev-ID","quote":"literal excerpt"}]}},"figure_references":[{"label":"literal Figure/Table/Equation label","page":null,"proof":{"evidence_id":"ev-ID","quote":"literal source caption/reference"}}]}].
Allowed fields: problem, prior_limitations, method_overview, mechanism, innovation, experimental_design, baselines, conditions, results, limitations. Return 1–3 representative cards, not all publications. Use a few compact fields per card and COMPLETE JSON. Every supplied field needs literal proofs, not only citation numbers. Missing fields stay unknown. Abstract/metadata-only sources can support problem and method_overview; do not invent detailed mechanisms, novelty comparisons, baselines, settings, numerical results or conditions without acquired full text. Full text may be provided as bounded windows; do not claim to have read omitted passages. Preserve reported results as source claims, never independent reproduction. Figure references locate actual labels/pages; no source image is acquired merely by citing a figure. Omit unverifiable fields and page numbers.'''


def _pattern(value):return r'\s+'.join(re.escape(token) for token in value.split())


def _full_text(source):
    meta=source.get('acquisition') or {}
    if meta.get('coverage')!='full_text' or meta.get('truncated'):return False
    if meta.get('format')=='pdf':
        return bool(meta.get('total_pages') and meta.get('retained_pages')==meta['total_pages'] and meta.get('pages'))
    return bool(meta.get('scientific_sections') and meta.get('full_text_basis'))


def build_technical_cards(configuration,findings,evidence,proposals=None):
    from app.organization_findings import _publication_url
    sources={item['evidence_id']:item for item in evidence if item.get('evidence_id') and item.get('source_url')}
    outputs={item['output_id']:item for item in (findings.get('scope_result') or {}).get('outputs',[])}
    proposals=proposals or {};cards=[];pending=[];proposed={}
    values=proposals.get('technical_cards',[])
    if not isinstance(values,list):values=[];pending.append({'reason':'technical_cards_expected_array'})
    if len(values)>20:pending.append({'reason':'technical_card_limit_20'})
    for value in values[:20]:
        try:
            card=TechnicalCardProposal.model_validate(value)
            card=card.model_copy(update={'output_id':findings.get('publication_id_aliases',{}).get(card.output_id,card.output_id)})
            if card.output_id not in outputs or card.output_id in proposed:raise ValueError('unknown or duplicate representative output')
            proposed[card.output_id]=card
        except ValueError as error:pending.append({'reason':str(error)[:400]})

    def linked_source(source,output):
        if (source.get('acquisition') or {}).get('coverage')=='discovery_only':return False
        primary={_publication_url(url) for url in output['source_urls']}
        if _publication_url(source['source_url']) in primary:return True
        for other in sources.values():
            if _publication_url(other['source_url']) in primary:
                links=(other.get('acquisition') or {}).get('document_links',[])
                if _publication_url(source['source_url']) in {_publication_url(url) for url in links}:return True
        return False

    def locate(proof,output,require_full):
        source=sources.get(proof.evidence_id)
        if not source or not linked_source(source,output):raise ValueError('proof is not retained primary work or publisher-linked document')
        if require_full and not _full_text(source):raise ValueError('full_text_required_for_this_field')
        match=re.search(_pattern(proof.quote),source.get('content') or '',re.I)
        if not match:raise ValueError('literal quote is absent from retained source')
        pages=[page['number'] for page in (source.get('acquisition') or {}).get('pages',[])
            if match.start()<page['end'] and match.end()>page['start']]
        return {'evidence_id':proof.evidence_id,'source_url':source['source_url'],'start':match.start(),'end':match.end(),
            'quote':match.group(),'pages':pages,'source_coverage':(source.get('acquisition') or {}).get('coverage','unknown')}

    # Without a requested representative, leave the available sample as unknown cards.
    requested=list(proposed) or list(outputs)[:3]
    for output_id in requested:
        output=outputs[output_id];proposal=proposed.get(output_id);fields={};figures=[]
        available=[source for source in sources.values() if linked_source(source,output)]
        full=any(_full_text(source) for source in available)
        for key,label in FIELDS.items():
            statement=proposal.fields.get(key) if proposal else None
            record={'label':label,'text':None,'status':'unknown','proofs':[],'reason':'not_extracted_from_available_source'}
            if statement:
                try:
                    anchors=[locate(proof,output,key not in {'problem','method_overview'}) for proof in statement.proofs]
                    source_text=' '.join(anchor['quote'] for anchor in anchors)
                    for value in re.findall(r'(?<!\w)\d+(?:\.\d+)?%?',statement.text):
                        if not re.search(r'(?<![\d.])'+re.escape(value)+r'(?![\d.])',source_text):
                            raise ValueError('numeric_summary_value_missing_from_literal_proofs')
                    record.update(text=statement.text,status='source_summary_requires_semantic_review',proofs=anchors,reason=None)
                except ValueError as error:record['reason']=str(error)
            elif key not in {'problem','method_overview'} and not full:record['reason']='full_text_unavailable_not_inferred_from_abstract'
            fields[key]=record
        for item in proposal.figure_references if proposal else ():
            try:
                anchor=locate(item.proof,output,True)
                if not re.search(_pattern(item.label),anchor['quote'],re.I):raise ValueError('figure_label_absent_from_source_quote')
                if item.page is not None and item.page not in anchor['pages']:raise ValueError('figure_page_not_supported_by_pdf_offsets')
                figures.append({'label':item.label,'proof':anchor,'page':item.page,'asset_status':'source_reference_only_not_image_acquired',
                    'source_url':anchor['source_url']+(f'#page={item.page}' if item.page else ''),'origin':'original_source_reference_not_system_generated_chart'})
            except ValueError as error:pending.append({'output_id':output_id,'kind':'figure_reference','reason':str(error)})
        cards.append({'output_id':output_id,'title':output['title'],'source_urls':output['source_urls'],
            'reading_depth':'full_text_source_with_bounded_context' if full else 'abstract_metadata_only',
            'full_text_available':full,'model_read_entire_document':False,'fields':fields,'figure_references':figures,
            'unknown_fields':[key for key,value in fields.items() if value['status']=='unknown'],
            'interpretation':'字段是有字面定位的来源摘要，未独立复现或完成语义审核；完整来源可用不等于模型看过全部正文。'})
    return {'schema_version':VERSION,'cards':cards,'pending_records':pending,'selected_output_ids':requested,
        'selection_basis':'analyst_proposed_representatives' if proposed else 'bounded_sample_fallback_not_quality_rank',
        'coverage':'representative_accepted_publications_only','effects':{'network_requests':0,'model_calls':0},
        'gaps':['原文图号／页码定位不代表已取得图片、表格结构或公式图像；未取得的资产明确留空。']}


def technical_context(view):
    if not view:return None
    return {'schema_version':view['schema_version'],'cards':view['cards'][:20],
        'retained_card_count':len(view['cards']),'pending_records':view['pending_records'][:10],'gaps':view['gaps']}


def technical_evidence_windows(source,limit):
    """Select source windows, keeping offsets instead of manufacturing a summary."""
    text=source.content;meta=source.acquisition or {};ranges=[(0,min(len(text),2000))]
    for section in meta.get('scientific_sections',[]):
        if re.search(r'method|experiment|evaluation|result|discussion|conclusion|limitation|方法|结果|讨论|结论',section['label'],re.I):
            ranges.append((section['start'],min(section['end'],section['start']+3500)))
    if meta.get('format')=='pdf':
        for hit in re.finditer(r'(?im)^.{0,30}(?:method|design|architecture|evaluation|experiment|baseline|result|limitation|conclusion).{0,70}$',text):
            ranges.append((max(0,hit.start()-200),min(len(text),hit.start()+3000)))
            if len(ranges)>=10:break
    if len(ranges)==1:ranges.append((ranges[0][1],min(len(text),limit)))
    merged=[]
    for lower,upper in sorted(ranges):
        if merged and lower<=merged[-1][1]:merged[-1]=(merged[-1][0],max(upper,merged[-1][1]))
        else:merged.append((lower,upper))
    lines=[];remaining=limit
    for lower,upper in merged:
        if remaining<=0:break
        upper=min(upper,lower+remaining);piece=text[lower:upper];remaining-=len(piece)
        lines.append(f'[retained source characters {lower}:{upper}]\n'+piece)
    return '\n'.join(lines),limit-remaining


def technical_markdown(view):
    if not view:return ''
    def safe(text):return str(text).replace('<','&lt;').replace('>','&gt;').replace('|','\\|').replace('\n',' ')
    lines=['\n\n## 代表成果深读与来源定位', '规则：'+VERSION]
    for card in view['cards']:
        lines+=['\n### '+safe(card['title']),card['interpretation'],f"阅读深度：{card['reading_depth']}；未知项：{len(card['unknown_fields'])}。"]
        for field in card['fields'].values():
            lines.append('\n**'+field['label']+'**：'+(safe(field['text']) if field['text'] else '未知（'+safe(field['reason'])+'）'))
            for anchor in field['proofs']:
                lines.append(f"- 原文 {safe(anchor['evidence_id'])} 字符 {anchor['start']}–{anchor['end']}，页 {','.join(map(str,anchor['pages'])) or '无PDF页码'}：<{quote(anchor['source_url'],safe=':/?#=&%+@~!$*,;()-_.')}>。")
        for figure in card['figure_references']:lines.append('- 原文定位：'+safe(figure['label'])+'；'+figure['asset_status']+'。')
    lines+=view['gaps']
    return '\n'.join(lines)
