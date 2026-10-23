"""Freeze report provenance from this run; never consult current defaults/sources."""
from __future__ import annotations

from copy import deepcopy
from urllib.parse import quote, urlsplit
from app.organization_purpose import analysis_snapshot

DIMENSIONS = {
    'topic_relevance': '主题相关性', 'research_alignment': '研究路线契合',
    'output_performance': '成果表现', 'evidence_completeness': '证据完整度',
    'recency': '时效性', 'cooperation_complementarity': '合作互补性',
}


def build_report_summary(configuration: dict | None, findings: dict | None, evidence: list[dict]) -> dict | None:
    if configuration is None:
        return None
    findings = findings or {}
    scoped = findings.get('scope_result') or {}
    manifest = configuration.get('catalog_manifest') or {}
    sources = {}
    for item in evidence:
        if item.get('evidence_id') and item.get('source_url'):
            sources[item['evidence_id']] = {key: item.get(key) for key in
                ('evidence_id', 'source_title', 'source_url', 'source_type', 'collected_at')}
    gaps = list(findings.get('gaps') or [])
    gaps += ['仅覆盖本次取得的样本；空样本不代表现实中零成果，来源未覆盖年份不补零。',
        '学科比较组使用请求标签；题名／摘要分类是带原文位置的规则映射，未独立核实学科或全文机制，不输出跨学科统一质量榜。',
        '原文位置与引用检查不等于独立语义复核；模型推断、建议和未来情景仍须复核。']
    if not manifest.get('applied_to_evidence'):
        gaps.append('评价目录为冻结的部分样本及授权要求，未自动应用到本次成果；缺失指标不作零分或最低等级。')
    if not scoped:
        gaps.append('本次未建立可复核的成果统计，不能把证据页数当作论文数量。')
    for kind, status in findings.get('relationship_coverage', {}).items():
        observed=((findings.get('relationship_view') or {}).get('coverage',{}).get(kind) or {}).get('observations',0)
        if status == 'not_established' and not observed:
            gaps.append(f'{kind} 关系尚无已纳入的直接依据；不表示该关系不存在。')
    return deepcopy({
        'schema_version': 'adrs-organization-report-v1',
        'configuration': configuration,
        'weights': configuration['effective_weights'],
        'analysis': analysis_snapshot(configuration),
        'corpus': findings.get('corpus'),
        'classification': findings.get('classification'),
        'relationships': findings.get('relationship_view'),
        'technical_reading': findings.get('technical_reading'),
        'trends': findings.get('trend_view'),
        'actions': findings.get('actions'),
        'statistics': findings.get('statistics'),
        'versions': {key: configuration.get(key) for key in ('schema_version', 'scope_rule_version')},
        'request_frozen_at': configuration.get('evidence_cutoff'),
        'sources': list(sources.values()),
        'sample': {'summary': scoped.get('summary'), 'views': scoped.get('views', []),
            'entities': scoped.get('selected_entities', configuration['scope']['entities']),
            'comparison_groups': findings.get('comparison_groups', []),
            'coverage': findings.get('coverage', 'retrieved_sample_not_real_world_census'),
            'counting_rule': 'per_object_full_count_and_union_deduplication',
            'counting_note': '分别保留发表记录与研究家族；同成果可归属多个对象，汇总取并集，未关联版本按独立发表计数。'},
        'evaluation': {'applied_to_evidence': bool(manifest.get('applied_to_evidence')),
            'catalog_schema_version': manifest.get('schema_version'),
            'adapter_rule_version': manifest.get('adapter_rule_version'),
            'schemes': manifest.get('schemes', []), 'sources': manifest.get('sources', [])},
        'pending_records': findings.get('pending_records', []),
        'gaps': list(dict.fromkeys(gaps)),
        'matching_semantics': '偏好配置不等于已完成评分；结果页只读重排不改写本报告的配置、事实或证据。',
    })


def report_summary_markdown(summary: dict | None) -> str:
    if summary is None:
        return ''

    def safe(value):
        text = str(value if value is not None else '未知')
        for old, new in [('\\', '\\\\'), ('|', '\\|'), ('[', '\\['), (']', '\\]'), ('<', '&lt;'), ('>', '&gt;')]:
            text = text.replace(old, new)
        return text.replace('\n', ' ').replace('\r', ' ')

    def link(url):
        return '<' + quote(str(url), safe=':/?#=&%+@~!$*,;()-_.') + '>' if urlsplit(str(url)).scheme in {'http', 'https'} else safe(url)

    config, weights = summary['configuration'], summary['weights']
    scope = config['scope']
    lines = ['\n\n## 研究对象、口径与冻结配置',
        f"主题：{safe(scope['topic'])}；学科：{safe('、'.join(scope['disciplines']))}；时间：{scope['start_date']} 至 {scope['end_date']}。",
        f"对象类型：{safe('、'.join(scope['organization_types']))}；请求冻结时间：{safe(summary['request_frozen_at'])}。实际采集时间逐来源保留。",
        f"范围规则：{safe(config.get('scope_rule_version'))}；配置版本：{safe(weights['config_version'])}；权重规则：{safe(weights['rule_version'])}；预设版本：{safe(weights['preset_version'])}。",
        summary['sample']['counting_note'], summary['matching_semantics'],
        '### 对象与来源']
    if summary.get('analysis'):
        policy = summary['analysis']
        lines.insert(-1, f"研究目的：{safe(policy['purpose_label'])}；研究模块：{safe('、'.join(policy['module_labels'][key] for key in policy['modules']))}；模块规则：{safe(policy['rule_version'])}。目的、模块与权重分别保存。")
    for entity in summary['sample']['entities']:
        lines.append(f"- {safe(entity['name'])}（{safe(entity['type'])}；{safe(entity.get('resolution_status'))}）：" + ' '.join(link(url) for url in entity.get('source_urls', [])))
    if not summary['sample']['entities']:
        lines.append('范围内候选发现尚未确立对象，不补造实体。')
    lines += ['### 原始与生效权重', '| 维度 | 原始权重 | 开启 | 生效权重 |', '| --- | ---: | --- | ---: |']
    for key, value in weights['effective_weights'].items():
        raw = weights['raw_config']['weights'].get(key, {})
        lines.append(f"| {DIMENSIONS.get(key, key)} | {raw.get('weight', 0)} | {'是' if raw.get('enabled', True) else '否'} | {value * 100:.2f}% |")
    for title, raw_key, effective_key in [('成果表现组内权重', 'performance_groups', 'effective_groups'), ('指标组内权重', 'metric_weights', 'effective_metric_weights')]:
        lines += [f'### {title}', '| 项目 | 原始权重 | 开启 | 组内生效权重 |', '| --- | ---: | --- | ---: |']
        for key, value in weights[effective_key].items():
            raw = weights['raw_config'][raw_key].get(key, {})
            lines.append(f"| {safe(key)} | {raw.get('weight', 0)} | {'是' if raw.get('enabled', True) else '否'} | {value * 100:.2f}% |")
        if not weights[effective_key]:
            lines.append('| 未显式配置 | — | — | — |')
    lines.append('### 有序偏好映射（产品偏好，非官方等价）')
    for mapping in weights.get('mappings', []):
        lines.append(f"- {safe(mapping['scheme_id'])}／{safe(mapping['version'])}：" + '；'.join(f'{safe(key)}={value}' for key, value in mapping['scores'].items()))
    lines += ['### 评价口径及可用性',
        f"目录版本：{safe(summary['evaluation']['catalog_schema_version'])}；适配规则：{safe(summary['evaluation']['adapter_rule_version'])}。目录样本不代表本次成果已核定评价。"]
    for scheme in summary['evaluation']['schemes']:
        public = any(source['scheme_id'] == scheme['scheme_id'] and source['access'] == 'public'
                     for source in summary['evaluation']['sources'])
        lines.append(f"- {safe(scheme['scheme_id'])}：{'部分公开样本' if public else '需授权导入／尚无公开样本'}；{link(scheme['source_url'])}；尚未核定本次成果。")
    for source in summary['evaluation']['sources']:
        lines.append(f"- {safe(source['scheme_id'])}／{safe(source['edition'])}／指标年 {source['metric_year']}：{safe(source['access'])}，{safe(source['coverage'])}；{link(source['source_url'])}")
    lines += ['### 实际取证来源']
    for source in summary['sources']:
        lines.append(f"- {safe(source['evidence_id'])}：{safe(source['source_title'])}；{link(source['source_url'])}；采集 {safe(source['collected_at'])}。")
    lines += ['### 缺失与解释边界', *[f'- {safe(gap)}' for gap in summary['gaps']]]
    for item in summary['pending_records'][:30]:
        lines.append(f"- 待核 {safe(item.get('title') or item.get('id') or item['kind'])}：{safe(item['reason'])}")
    if len(summary['pending_records']) > 30:
        lines.append('正文列前 30 项待核，研究数据 JSON 保留全部记录。')
    return '\n'.join(lines) + '\n'
