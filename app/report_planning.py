"""Reader task structure chosen without an additional planning model."""
from __future__ import annotations

VERSION='adrs-reader-writing-plan-v1'
KINDS={'answer','summary','comparison','report','data_analysis'}
SECTIONS={
    'answer':['直接回答','关键依据及影响答案的条件','参考资料'],
    'summary':['核心结论','围绕研究问题的主要发现','需要采取的下一步','参考资料'],
    'comparison':['比较结论','统一比较口径及关键条件','机制与适用条件对照','选择建议及依据','参考资料'],
    'report':['核心判断','研究范围与方法','按研究问题组织的主要发现','机制、演进与代表成果','建议及下一步','参考资料'],
    'data_analysis':['数据回答的问题','数据范围、分母及缺失','按同一快照计算的结果','解释与适用条件','参考资料'],
}


def build_writing_plan(snapshot,configuration=None):
    from app.query_understanding import identity
    snapshot=snapshot or {};delivery=snapshot.get('delivery') or {};slots=snapshot.get('slots') or {}
    selected=delivery.get('output_kind','auto')
    kind=selected if selected!='auto' else {'fact':'answer','aggregate':'data_analysis','comparison':'comparison'}.get(snapshot.get('query_type'),'report')
    if kind not in KINDS:raise ValueError('unsupported_reader_output_kind')
    owner='custom_pages' if delivery.get('pages') else 'selected_organization_modules' if configuration else 'reader_task'
    body={'version':VERSION,'output_kind':kind,'selection_basis':'explicit' if selected!='auto' else 'frozen_query_type',
        'depth':slots.get('depth','standard'),'structure_owner':owner,'suggested_sections':SECTIONS[kind],
        'additional_model_calls':0,'generation_completion':'valid_structure_and_finished_provider_response',
        'delivery_completion':'supported_complete_audit_and_required_figure_delivery'}
    return {**body,'plan_id':identity(body)}


def writing_plan(snapshot,configuration=None):
    from app.query_understanding import identity
    frozen=(snapshot or {}).get('writing_plan')
    if not frozen:return build_writing_plan(snapshot,configuration)
    body={key:value for key,value in frozen.items() if key!='plan_id'}
    if body.get('version')!=VERSION or body.get('output_kind') not in KINDS or identity(body)!=frozen.get('plan_id'):
        raise ValueError('frozen_reader_writing_plan_invalid')
    if build_writing_plan(snapshot,configuration)!=frozen:raise ValueError('frozen_reader_writing_plan_inputs_changed')
    return frozen


def writing_instructions(plan):
    kind=plan['output_kind']
    specific={
        'answer':'先直接回答问题，再用必要的原文与具体条件解释。不要为了凑章节添加企业全景、统计或泛泛建议。',
        'summary':'按当前研究问题挑出最有用的判断；解释判断依赖的来源与条件，避免逐条转述来源和重复总结。',
        'comparison':'围绕共同问题比较各对象或机制，说明统一口径、差异及适用条件；不能把不同环境的实验数值排成无条件优劣榜。',
        'data_analysis':'使用提供的确定性统计快照／指标，不在语言模型内重算样本、分母、比例或单位。不足以量化的问题明确所需数据，并给出已有资料支持的定性判断。',
        'report':'开头给出能帮助读者作判断的核心发现，按问题组织机制与演进；逐篇细节和完整实验表放入技术附录，建议连接问题、证据、资源与下一步。',
    }[kind]
    structure=('必须保持明确选择的自定义页面顺序与问题。' if plan['structure_owner']=='custom_pages' else
        '保持所选组织研究模块及既有JSON契约；在核心判断和各模块内适配本次读者任务。' if plan['structure_owner']=='selected_organization_modules' else
        '按内容需要使用这些结构：'+'、'.join(plan['suggested_sections'])+'。没有内容的章节省略，不以固定段数或字数填充。')
    return ('\n\n读者任务与写作结构：\n'+specific+'\n'+structure+
        ('\n本次为简明回答，保留直接影响判断的依据与条件，细节按需进入附录。' if plan['depth']=='brief' else
         '\n本次需要深入分析，贯通机制、比较基线、完整实验条件、演进及可执行下一步；正文突出判断，逐项细节放入附录。' if plan['depth']=='deep' else
         '\n按标准分析深度解释关键机制、比较依据和后续行动。')+
        '\n事实必须回到原始资料；区分作者报告的结果、综合解释和建议。支持度由后续原文审核确定，引用排名不等于核实。'
        '\n系统版本、产物状态、预算、审核标签、未启用能力及重复免责不进入报告正文。方法口径只在必要位置交代一次。')
