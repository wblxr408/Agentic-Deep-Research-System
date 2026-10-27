"""Project frozen method preparation and owner-bound execution receipts."""
from __future__ import annotations

from app.skills.stages import preparation_view

TRACKING='adrs-method-use-v1'
TOOL_STAGES={'search','browser','rag','mcp'}


def method_usage_view(selection,model_receipts,tool_receipts,status):
    compilation=(selection or {}).get('stage_compilation') or {}
    if not compilation or not isinstance(compilation.get('profiles'),dict):
        return {'version':TRACKING,'availability':'legacy_unknown','stages':[]}
    plans=preparation_view(compilation,selection)
    result=[]
    for plan in plans:
        stage=plan['stage'];profile=compilation['profiles'][stage]
        details={item['skill_id']:item for item in profile.get('entries',[])}
        relevant=[row for row in model_receipts if (row.get('method_context') or {}).get('stage')==stage
                  and (row.get('method_context') or {}).get('compilation_id')==compilation.get('compilation_id')]
        old_calls=[row for row in model_receipts if (row.get('agent')==stage or stage=='planner' and row.get('agent')=='replan'
                   or stage=='render' and row.get('purpose')=='render')
                   and row.get('skill_tracking_version')!=TRACKING]
        tool_used=any(row.get('tool')==stage and row.get('status')=='settled' and row.get('calls') for row in tool_receipts)
        restrictions={item.get('skill_id') for item in profile.get('restrictions',[])}
        for entry in plan['entries']:
            detail=details.get(entry['skill_id']) or {}
            if stage in TOOL_STAGES:
                if tool_used and (entry['skill_id'] in restrictions or detail.get('required_tools')):
                    usage='tool_policy_applied'
                else:
                    usage='tool_without_model'
            elif 'has_model_content' not in detail:
                usage='legacy_unknown'
            elif not detail['has_model_content']:
                usage='no_model_content'
            else:
                matches=[row for row in relevant if any(item.get('skill_id')==entry['skill_id'] and item.get('version')==entry['version']
                    for item in (row.get('method_context') or {}).get('methods',[]))]
                if any(row.get('response_received') is True for row in matches):
                    usage='sent'
                elif any(row.get('dispatch_status')=='dispatch_attempted' for row in matches):
                    usage='delivery_unknown'
                elif any(row.get('status')=='inflight' for row in matches):
                    usage='pending'
                elif old_calls:
                    usage='legacy_unknown'
                elif status in {'completed','failed','canceled'}:
                    usage='not_sent'
                else:
                    usage='waiting'
            entry['usage']=usage
        result.append(plan)
    return {'version':TRACKING,'availability':'available','scope':'all_owner_task_executions',
        'semantics':'provider_response_confirms_request_not_model_compliance', 'stages':result}
