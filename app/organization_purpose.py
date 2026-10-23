"""Research questions and bounded report assembly, independent of preference weights."""
from __future__ import annotations

import json
import re
from html import escape
from typing import Annotated, Literal

from pydantic import Field
from app.research_scope import ScopeRecord

ResearchPurpose = Literal['research_development', 'cooperation_discovery', 'comprehensive']
ResearchModule = Literal['landscape', 'evolution', 'relationships', 'deep_dive', 'validation', 'actions']
POLICY_VERSION = 'adrs-analysis-modules-v1'
REPORT_WRITING_GUIDANCE = '''
面向报告读者的写作要求：
用自然、连贯的研究报告语言直接陈述发现、解释和建议，技术术语按读者理解需要说明。
在开头用一处简洁的方法说明交代研究对象、时间、样本和来源范围；具体实验数字注明论文或作者的报告及适用条件。
在结论处交代真正影响判断的材料限制，不反复写“不能保证”“不代表”“未经独立验证”等免责句。
段落kind仅用于内部记录，不在文字中写“来源摘述”“待审核”“待复核”“证据缺口”等工作流标签。
不写产物/数据/规则版本、冻结配置、任务ID、预算、审批、工具权限、内部错误码或模型置信度。
区别来源已取得的覆盖级别与本次进入上下文的选段；没有读到的论文不等于不存在。样本篇数仅使用程序给出的统计占位符，机制比较优先直写成果名称。
用来源归因和有根据的分析表达事实与判断；缺少支持时缩小结论范围或说明尚需哪些研究材料，不编造确定结论。
只围绕研究问题提出下一步行动，不插入“不会擅自联系”等系统行为说明；不为凑齐模板填空表和未知字段。
'''
PURPOSES = {'research_development': '布局与演进', 'cooperation_discovery': '合作发现', 'comprehensive': '综合研究'}
MODULES = {
    'landscape': ('研究全景', '声明样本与公开研究方向；不把论文量解释为投入。'),
    'evolution': ('研究演进', '区分观测变化与覆盖变化；只有一个年度样本时不能确立多年趋势。'),
    'relationships': ('关系分析', '分别表述已知署名／共著、资助、项目及协议；未知保持未知。'),
    'deep_dive': ('成果深读', '仅解释实际取得的原文，无法核清的方法、条件和图表保留缺口。'),
    'validation': ('交叉验证', '列出支持、冲突及未取得材料，不把相关线索当作部署证明。'),
    'actions': ('后续行动', '发展目的提出研究验证问题；合作目的缺需求时先列待补条件，不擅自联系。'),
}
DEFAULTS = {
    'research_development': ('landscape', 'evolution', 'validation'),
    'cooperation_discovery': ('landscape', 'relationships', 'validation', 'actions'),
    'comprehensive': tuple(MODULES),
}


def resolve_modules(purpose: ResearchPurpose, modules: tuple[ResearchModule, ...] | None) -> tuple[ResearchModule, ...]:
    selected = DEFAULTS[purpose] if modules is None else modules
    if not selected or len(selected) > len(MODULES) or len(set(selected)) != len(selected):
        raise ValueError('select one to six distinct research modules')
    return selected


def analysis_catalogue() -> dict:
    return {'rule_version': POLICY_VERSION,
        'purposes': [{'id': key, 'label': label, 'default_modules': DEFAULTS[key]} for key, label in PURPOSES.items()],
        'modules': [{'id': key, 'label': value[0], 'question': value[1]} for key, value in MODULES.items()],
        'capability_note': '模块控制本次问题与叙述章节；完整样本、分类、关系、深读、趋势和行动契约仍按后续任务实现。'}


def analysis_snapshot(configuration: dict | None) -> dict | None:
    if not configuration or configuration.get('analysis_policy_version') != POLICY_VERSION:
        return None
    purpose = configuration['purpose']
    selected = list(configuration['modules'])
    return {'rule_version': POLICY_VERSION, 'purpose': purpose, 'purpose_label': PURPOSES[purpose],
        'modules': selected, 'module_labels': {key: MODULES[key][0] for key in selected},
        'not_requested': [key for key in MODULES if key not in selected],
        'semantics': '研究目的、内容模块与匹配权重分别冻结；不改变模板、权限或取证预算。'}


def analysis_instructions(configuration: dict | None) -> str:
    policy = analysis_snapshot(configuration)
    if not policy:
        return ''
    return ('\n\n研究目的／模块契约（优先于通用商业研究框架）：\n'
        + json.dumps(policy, ensure_ascii=False)
        + '\n只回答已选模块的问题，不补齐未选模块。每类组织均可独立研究，'
          '高校／实验室不要求企业产品或合作页面，任何目的都不强制企业参与。'
          '权重预设不是研究目的；即使合作权重非零，也不据此添加合作分析。'
          '只为当前模块需要补证，已有明确来源时避免泛化市场／新闻任务；browser query 必须是实际 HTTP(S) URL。'
          '事实、分析和未知分开；不足以确认演进或合作时明确缺口，不补造结果。'
        + '\n' + '\n'.join(f'{MODULES[key][0]}：{MODULES[key][1]}' for key in policy['modules']))


class ModuleParagraph(ScopeRecord):
    text: str = Field(min_length=3, max_length=4000)
    kind: Literal['observation', 'interpretation', 'gap']
    citations: tuple[Annotated[int, Field(ge=1)], ...] = Field(default=(), max_length=30)


class ModuleDraft(ScopeRecord):
    module_id: ResearchModule
    paragraphs: tuple[ModuleParagraph, ...] = Field(min_length=1, max_length=20)
    appendix: tuple[ModuleParagraph, ...] = Field(default=(), max_length=20)


class ModuleReportDraft(ScopeRecord):
    title: str = Field(min_length=1, max_length=300)
    summary: tuple[ModuleParagraph, ...] = Field(default=(), max_length=5)
    modules: tuple[ModuleDraft, ...] = Field(min_length=1, max_length=6)


def module_report_instructions(configuration: dict) -> str:
    return ('You are a source-grounded research writer. Return JSON, not a generic company report. '
        'The exact JSON shape is {"title":"short research title","summary":[{"text":"key judgement and implications","kind":"interpretation","citations":[1]}],"modules":[{"module_id":"selected ID",'
        '"paragraphs":[{"text":"plain prose without headings or inline citation markers",'
        '"kind":"observation|interpretation|gap","citations":[1]}],"appendix":[{"text":"detailed methods, experiments or resources","kind":"observation","citations":[1]}]}]}. '
        'Use the existing citation numbers, never invent IDs. Observations need source numbers; '
        'every observation paragraph must have at least one integer in citations. '
        'Missing materials, absence of independently checked conflicts, and inability to verify are kind=gap, '
        'not uncited observations. Example: {"text":"未取得独立材料，无法完成交叉验证。","kind":"gap","citations":[]}. '
        'Organize the main report around the reader questions and leading judgements, comparisons and choices. '
        'Use as many substantive paragraphs as the question and acquired evidence require, within the output allowance. '
        'Keep detailed per-paper methods and experiments in appendix; preserve models, hardware, workloads, baselines, metrics, SLOs and source section/figure names when supplied. '
        'Compare mechanisms and tradeoffs; never rank unrelated experimental maxima. Missing fields stay absent. '
        'Cooperation choices specify required data/equipment/control, a concrete first deliverable and public resources; never invent user resources or willingness to collaborate. '
        'The summary answers the actual research question, rather than listing chapter names. Never fill missing evidence with invented facts. '
        'Do not write sections, modules or product/partner pages that were not selected. '
        'When computed_statistics is present, sample counts, sample percentages and family/label totals '
        'must use literal placeholders {stat:metric_id} from its metric_registry. '
        'For example use {stat:sample:publications}, never recalculate or type an aggregate number. '
        'A percentage metric already includes its percent sign; do not append another sign. '
        'Unknown values stay unknown. Publication dates and source-supported experimental measurements '
        'are separate from sample aggregates and must retain their original source citations. '
        'The server assembles only requested module IDs; an extra or missing module is recorded separately.'
        + REPORT_WRITING_GUIDANCE
        + analysis_instructions(configuration))


def paragraph_repair_messages(rejected: list[dict]) -> list[dict]:
    from app.security.prompt_security import untrusted_context
    payload = json.dumps([{'paragraph_id': f'rejected:{index+1}', **row} for index, row in enumerate(rejected)], ensure_ascii=False)
    return [{'role': 'system', 'content':
        'Correct only the rejected research paragraphs. Return JSON {"repairs":[{"paragraph_id":"rejected:1","text":"corrected prose"}]}. '
        'Return one text per supplied ID. For unbound aggregate errors REMOVE clauses counting publications, sources or yearly samples; '
        'do not replace them with another number, compute counts, or add statistical placeholders. '
        'Use paper names or qualitative scope statements instead. Preserve mechanism explanations, dates and experimental conditions. '
        'Do not add facts or inline citation markers; citation arrays are locked by the server.'},
        {'role': 'user', 'content': untrusted_context('rejected_report_paragraphs', payload, limit=len(payload))}]


def report_prose(text: str) -> str:
    """Render plain paragraph data identically for assembly and issue mapping."""
    text = re.sub(r'\[citation:\d+\]', '', text)
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', escape(text, quote=False))


def assemble_module_report(raw: str, configuration: dict, citation_count: int, *, statistics: dict | None = None) -> tuple[str, dict]:
    """Untrusted prose cannot add report pages or replace selected module IDs."""
    selected = configuration['modules']
    issues, proposed, rejected = [], {}, []
    summary = ()
    validation_errors = []
    title = configuration['scope']['topic']
    try:
        value = raw.strip()
        if value.startswith('```json') and value.endswith('```'):
            value = value[7:-3].strip()
        parsed = ModuleReportDraft.model_validate_json(value)
        title = parsed.title
        summary = parsed.summary
        for module in parsed.modules:
            if module.module_id not in selected:
                issues.append(f'unrequested_module:{module.module_id}')
            elif module.module_id in proposed:
                issues.append(f'duplicate_module:{module.module_id}')
            else:
                proposed[module.module_id] = module
    except ValueError as error:
        issues.append('module_response_invalid_or_incomplete')
        validation_errors = error.errors(include_input=False) if hasattr(error, 'errors') else [{'message': str(error)[:1000]}]

    prose=report_prose

    def bind_statistics(text):
        if not statistics:
            if '{stat:' in text:raise ValueError('statistics_snapshot_unavailable')
            return text,[]
        registry=statistics.get('metric_registry') or {}
        pattern=r'\{stat:([^\s{}]{1,260})\}'
        requested=re.findall(pattern,text)
        if any(key not in registry for key in requested):raise ValueError('unknown_statistical_metric')
        for match in re.finditer(pattern,text):
            metric=registry[match.group(1)]
            # Select the nearest explicit unit; quantities on opposite sides
            # of the same sentence must not borrow one another's population.
            after=text[match.end():match.end()+28]
            before=re.split(r'[，,。；;：:\n]',text[:match.start()])[-1][-28:]
            hint=after.lstrip()
            expected=None
            if re.match(r'(?:篇|份|个)?(?:全文|完整正文|全文文档)',hint) or re.search(r'(?:全文(?:文档)?|完整正文)(?:共|有|为|取得|获得|数量|数)?\s*$',before):
                expected={'full_text_document_version'}
            elif re.match(r'(?:条|个)?证据(?:条目|片段)?',hint):expected={'evidence_not_publication'}
            elif re.match(r'(?:份|个)?(?:来源文档|文档版本|来源)',hint):expected={'source_document_version','source_url_not_publication'}
            elif re.match(r'(?:个|项)?研究家族',hint):expected={'research_family_or_unlinked_publication'}
            elif re.match(r'(?:篇|条|项)?(?:论文|发表|成果)',hint) or re.search(r'(?:采纳发表|发表记录|论文|采纳样本|发表样本)(?:共|有|为|数量|数)?\s*$',before):
                expected={'publication'}
            elif re.match(r'篇(?:[，,。；;\s]|$)',hint):expected={'publication'}
            unit=metric.get('counting_unit') or metric.get('unit')
            if expected and unit not in expected:raise ValueError('statistical_population_mismatch')
            if expected and metric.get('unit')=='percent':raise ValueError('statistical_measure_mismatch')
            if re.search(r'(?:占比|比例|percentage|share)\s*$',before,re.I) and metric.get('unit')!='percent':
                raise ValueError('statistical_measure_mismatch')
            if hint.startswith(('%','％')) and metric.get('unit')=='percent':raise ValueError('duplicate_percentage_unit')
        remainder=re.sub(pattern,'[computed statistic]',text)
        if '{stat:' in remainder:raise ValueError('invalid_statistical_placeholder')
        # Literal aggregate quantities cannot override the computed snapshot.
        # Dates and measurements from an individual paper remain source claims.
        number=r'(?:\d+(?:[.,]\d+)*|[零〇一二两三四五六七八九十百千万]+)'
        document_units=r'(?:篇|份|个)\s*(?:全文|完整正文|来源文档|文档版本|来源|证据条目|证据片段)'
        if re.search(number+r'\s*'+document_units,remainder,re.I):raise ValueError('unbound_source_aggregate')
        units=r'(?:篇(?!全文|完整正文|文档)(?:论文|成果|发表)?|条发表|项成果|个?(?:研究家族|发表记录|分类标签|采纳样本)|publications?\b|papers?\b|families\b)'
        if re.search(number+r'\s*'+units,remainder,re.I):raise ValueError('unbound_sample_aggregate')
        for clause in re.split(r'[。；;\n]',remainder):
            aggregate=re.search(r'样本|采纳|发表|家族|分类|标签|占比|占总|sample|publication|families|percentage',clause,re.I)
            if aggregate and re.search(number+r'\s*(?:[%％]|/\s*'+number+r')',clause):
                raise ValueError('unbound_sample_ratio')
        bindings=[{'metric_id':key,'snapshot_id':statistics['snapshot_id'],'display':registry[key]['display'],
            'value':registry[key]['value'],'unit':registry[key].get('unit'),
            'counting_unit':registry[key].get('counting_unit',registry[key].get('unit')),'numerator':registry[key].get('numerator'),
            'denominator':registry[key].get('denominator')} for key in dict.fromkeys(requested)]
        return re.sub(pattern,lambda match:registry[match.group(1)]['display'],text),bindings

    # The model title is plain prose too; it cannot inject headings or totals.
    try:
        rendered_title,_=bind_statistics(title)
    except ValueError:
        issues.append('unbound_statistic_in_title');rendered_title=configuration['scope']['topic']
    lines = ['# ' + prose(rendered_title.replace('\n', ' ').replace('\r', ' ')), '']
    modules = []
    summary_paragraphs = []
    appendix_lines = []
    # All reader layers use the same source/statistic validation and escaping.
    # A model cannot bypass these controls by placing prose in the appendix.
    def render_items(items, key, target):
        paragraphs = []
        for item in items:
            numbers = list(dict.fromkeys(item.citations))
            if any(number > citation_count for number in numbers) or (item.kind == 'observation' and not numbers):
                issues.append(f'invalid_source_numbers:{key}')
                rejected.append({'module_id': key, 'reason': 'invalid_source_numbers', 'paragraph': item.model_dump(mode='json')})
                continue
            try:
                rendered, bindings = bind_statistics(item.text)
            except ValueError as error:
                issues.append(f'{error}:{key}')
                rejected.append({'module_id': key, 'reason': str(error), 'paragraph': item.model_dump(mode='json')})
                continue
            paragraphs.append({**item.model_dump(mode='json'), 'citations': numbers,
                'rendered_text': rendered, 'statistic_bindings': bindings})
            refs = ' '.join(f'[citation:{number}]' for number in numbers)
            target.append(f'{prose(rendered)} {refs}'.rstrip()+'\n')
        return paragraphs
    if summary:
        lines.append('## 核心判断\n')
        summary_paragraphs = render_items(summary, 'summary', lines)
    for key in selected:
        lines.append('## ' + MODULES[key][0] + '\n')
        draft = proposed.get(key)
        paragraphs = render_items(draft.paragraphs, key, lines) if draft else []
        appendix = []
        if draft and draft.appendix:
            rendered_appendix = []
            appendix = render_items(draft.appendix, key, rendered_appendix)
            if appendix:
                appendix_lines.extend(['### '+MODULES[key][0]+'\n', *rendered_appendix])
        if not paragraphs:
            issues.append(f'module_unavailable:{key}')
            lines.append('现有资料不足以回答这一问题。\n')
        modules.append({'module_id': key, 'label': MODULES[key][0], 'paragraphs': paragraphs,
            'appendix': appendix,
            'status': 'draft_requires_review' if paragraphs else 'unavailable'})
    main_markdown = '\n'.join(lines)
    appendix_markdown = '## 技术附录\n\n'+'\n'.join(appendix_lines) if appendix_lines else ''
    return main_markdown+('\n\n'+appendix_markdown if appendix_markdown else ''), {'rule_version': POLICY_VERSION, 'purpose': configuration['purpose'],
        'summary':summary_paragraphs,
        'reading_structure': {'main_markdown': main_markdown, 'appendix_markdown': appendix_markdown},
        'raw_model_response': raw, 'validation_errors': validation_errors,
        'modules': modules, 'not_requested': [key for key in MODULES if key not in selected],
        'issues': list(dict.fromkeys(issues)), 'validation': 'selected_ids_source_numbers_and_bound_sample_statistics',
        'statistics_snapshot_id':statistics.get('snapshot_id') if statistics else None,
        'rejected_paragraphs': rejected,
        'independent_semantic_review': False}
