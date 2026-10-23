"""Build matching inputs only from an owned, completed research's saved sources."""
from collections import defaultdict
from datetime import date, datetime

from app.research_evaluation import EvaluationContext, applicability, scheme_catalogue
from app.research_matching import (
    ComparisonGroup, MatchingCandidate, MatchingEvidence, MatchingObservation, MatchingSnapshotInput,
)
from app.research_scope import OrganizationEntity, OrganizationResearchScope

BRIDGE_VERSION = 'adrs-session-matching-v1'


def snapshot_from_research(session_id: str, execution_id: str, completed_at: datetime | date,
                           configuration: dict, findings: dict, state: dict, *, origin='saved_research') -> MatchingSnapshotInput:
    if not findings or 'scope_result' not in findings:
        raise ValueError('这份研究没有结构化成果归属；请先完成带来源的组织研究。')
    scope = OrganizationResearchScope.model_validate(configuration['scope'])
    scoped = findings['scope_result']
    outputs = {item['output_id']: item for item in scoped['outputs']}
    sources = {item['evidence_id']: item for item in state.get('collected_evidence', []) if item.get('source_url')}
    valid_refs = set()
    for proof in findings.get('source_checks', {}).get('proofs', []):
        source = sources.get(proof['evidence_id'])
        if (source and source['source_url'] == proof['source_url'] and
            source['content'][proof['start']:proof['end']] == proof['quote']):
            valid_refs.add(proof['evidence_id'])
    family_ids = {key: 'family:' + family['family_id'] for family in scoped['research_families'] for key in family['output_ids']}
    groups, candidates, used_refs = {}, [], set()
    for entity in scoped['selected_entities']:
        view = next(item for item in scoped['views'] if item['entity_id'] == entity['entity_id'])
        families = defaultdict(list)
        for key in view['output_ids']:
            metadata = findings['publication_metadata'][key]
            for discipline in scope.disciplines:
                families[(discipline, metadata['output_type'], family_ids.get(key, 'publication:' + key))].append(outputs[key])
        observations = []
        for (discipline, output_type, family_id), members in sorted(families.items()):
            context_key = (discipline, output_type)
            if context_key not in groups:
                context = EvaluationContext(disciplines=(discipline,), output_type=output_type)
                groups[context_key] = ComparisonGroup(
                    group_id=f'group-{len(groups) + 1}', discipline=discipline, output_type=output_type,
                    metric_year=completed_at.year, category='requested_scope_no_automatic_metric_assignment',
                    feature_rules={'topic_relevance': 'token_overlap_v1', 'recency': 'linear_recency_v1',
                        'research_alignment': 'provided_v1', 'evidence_completeness': 'provided_v1',
                        'cooperation_complementarity': 'provided_v1'},
                    performance_applicable=any(applicability(scheme.scheme_id, context)[0] for scheme in scheme_catalogue()),
                )
            representative = max(members, key=lambda item: (item.get('published_until') or item['published_on'], item['output_id']))
            refs = sorted({ref for member in members
                for ref in findings['publication_metadata'][member['output_id']]['evidence_ids']})
            if not refs or not set(refs) <= valid_refs:
                raise ValueError('成果来源未能与保存的原文位置对应；保留原报告，不创建替代快照。')
            used_refs.update(refs)
            observations.append(MatchingObservation(
                family_id=family_id, group_id=groups[context_key].group_id,
                published_on=representative['published_on'], published_until=representative.get('published_until'),
                date_precision=representative.get('date_precision', 'day'), title=representative['title'], evidence_ids=tuple(refs),
            ))
        candidates.append(MatchingCandidate(entity=OrganizationEntity.model_validate(entity), observations=tuple(observations)))
    if not groups or not used_refs:
        raise ValueError('本次没有可归属的成果样本，无法生成有依据的重排；原缺口继续保留。')
    evidence = []
    for key in sorted(used_refs):
        source = sources[key]
        if not source.get('collected_at'):
            raise ValueError('来源没有保存采集时间，不能补造证据截止口径。')
        evidence.append(MatchingEvidence(evidence_id=key, source_url=source['source_url'],
            retrieved_on=datetime.fromisoformat(source['collected_at']).date(), verification_status='unreviewed'))
    cutoff=completed_at.date() if isinstance(completed_at,datetime) else completed_at
    return MatchingSnapshotInput(scope=scope, evidence_cutoff=cutoff, evidence=tuple(evidence),
        groups=tuple(groups.values()), candidates=tuple(candidates), session_id=session_id, origin=origin,
        source_execution_id=execution_id, bridge_version=BRIDGE_VERSION,
        bridge_notes=(
            '来源为本会话已保存的成果、引用位置和采集时间；创建与重排不调用模型或取证。',
            '主题分项仅采用已保存标题的词面重合；未把网页导航当成摘要，不代表语义相关性评估。',
            '发表年月／年份保留完整日期区间；时效性不虚构精确发表日。',
            '同组按请求学科标签和成果类型组织；尚未逐篇自动分类，不跨组统一排名。',
            '研究家族在每个类型组内取最近发表代表，家族等权；未链接版本仍按独立发表单元。',
            '原文位置校验不等于独立语义复核；来源仍标未复核，不生成已确认合作事实。',
            '未取得的成果评价／路线契合／证据完整度／合作互补性保持未知和区间，不以零分代替。',
            '没有对本次成果自动应用目录或论文指标；原研究冻结目录仍由原会话保存。',
        ))
