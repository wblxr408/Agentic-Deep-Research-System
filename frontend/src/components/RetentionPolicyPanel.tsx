export interface RetentionDraft {reuse_scope:'task'|'group'|'owner';task_id:string;valid_from:string;valid_until:string;purge_after:string}
export const defaultRetentionDraft:RetentionDraft={reuse_scope:'task',task_id:'',valid_from:'',valid_until:'',purge_after:''}
export function retentionPolicyRequest(value:RetentionDraft) {
  const date=(input:string)=>input?new Date(input).toISOString():null
  const policy={reuse_scope:value.reuse_scope,task_id:value.reuse_scope==='task'&&value.task_id.trim()?value.task_id.trim():null,valid_from:date(value.valid_from),valid_until:date(value.valid_until),purge_after:date(value.purge_after)}
  if(policy.task_id&&!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(policy.task_id))throw new Error('请填写有效的本人研究任务编号。')
  if(policy.valid_from&&policy.valid_until&&policy.valid_until<=policy.valid_from)throw new Error('失效时间应晚于生效时间。')
  return policy
}
export default function RetentionPolicyPanel({value,onChange}:{value:RetentionDraft;onChange:(value:RetentionDraft)=>void}) {
  return <fieldset className="space-y-3 rounded-lg border p-4 text-sm"><legend className="px-2 font-medium">保存与复用范围</legend>
    <label className="block">资料可供哪些研究使用<select aria-label="资料复用范围" className="input-xm ml-2" value={value.reuse_scope} onChange={event=>onChange({...value,reuse_scope:event.target.value as RetentionDraft['reuse_scope'],task_id:''})}><option value="task">仅绑定任务（默认）</option><option value="group">明确选择同一分组的研究</option><option value="owner">本人跨任务复用</option></select></label>
    {value.reuse_scope==='task'&&<label className="block">本人研究任务编号<input aria-label="资料绑定任务编号" className="input-xm mt-1 w-full" value={value.task_id} onChange={event=>onChange({...value,task_id:event.target.value})} placeholder="可稍后绑定；未绑定时只支持本人直接定位" /></label>}
    <p className="text-xs text-xmgray-500">任务范围不会被其他任务召回。分组复用要求研究实际选择该组；本人跨任务复用须在这里明确选择。</p>
    <div className="grid gap-2 sm:grid-cols-3">{(['valid_from','valid_until','purge_after'] as const).map((key,index)=><label className="block text-xs" key={key}>{['生效时间（可选）','失效时间（可选）','旧版本可清理时间（可选）'][index]}<input aria-label={['资料生效时间','资料失效时间','旧版本可清理时间'][index]} type="datetime-local" className="input-xm mt-1 w-full" value={value[key]} onChange={event=>onChange({...value,[key]:event.target.value})}/></label>)}</div>
    <p className="text-xs text-xmgray-500">时间按本机时区填写。到期停止新检索；达到清理时间后仍需本人显式操作，当前版本不会自动删除。</p>
  </fieldset>
}
