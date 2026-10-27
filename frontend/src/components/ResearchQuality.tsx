import {uiDefinition,t,useLocale,uiMessage} from '../i18n'
import {useRef,useState} from 'react'
import QuestionCoverage,{type QuestionCoverageData} from './QuestionCoverage'

type Candidate={candidate_id:string;rank:number;title:string;routes:string[]}
type Run={run_id:string;node_id:string;tool:string;query:string;candidates:Candidate[];filter_bucket:string;
  channel_contributions:Array<{route:string;returned_candidates:number;unique_returned:number;returned_share:number|null}>}
type Event={request_id:string;kind:string;created_at:string;payload:{note?:string;answer?:Record<string,string>}}
interface Quality {
  question_coverage?:QuestionCoverageData
  binding_id:string;data:{retained_evidence:number;coverage:Record<string,number>;freshness_observations:Record<string,number>}
  retrieval_runs:Run[];ranking_judgments:Array<{run_id:string;top_k:number;recall_at_k:number|null;ndcg_at_k:number|null;mrr:number|null;pairwise_accuracy:number|null;judged_count:number;pool_size:number}>
  answer:{model_audit_supported_claims:number|null;model_audit_total_claims:number|null;audit_complete:boolean;
    model_audit_source_supported_claims?:number|null;model_audit_method_supported_claims?:number|null}
  agent:{tool_calls:number;failed_or_stopped_calls:number;user_confirmed_task_complete:boolean}
  statistics_review:{available:boolean;issues:Array<{reason:string;metric_id?:string}>;input_conflicts?:unknown[]}
  feedback:Event[];historical_feedback_count:number;improvement_candidates:Array<{kind:string;basis:string;action:string}>
  runtime_ledger?:unknown
}
type Kind='adopted'|'corrected'|'task_complete'|'opened'|'ranking_assessment'|'answer_assessment'
const labels:Record<Kind,string>=uiDefinition({adopted:'已采纳',corrected:'纠错',task_complete:'已满足研究目标',opened:'已阅读',ranking_assessment:'标注检索相关性',answer_assessment:'评价报告内容'})
const percent=(value:number|null)=>value===null?t("缺少标注"):`${(value*100).toFixed(1)}%`

export default function ResearchQuality({sessionId}:{sessionId:string}) {
  useLocale()

  const [value,setValue]=useState<Quality|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState('')
  const [kind,setKind]=useState<Kind>('adopted'),[note,setNote]=useState(''),[runId,setRunId]=useState('')
  const [grades,setGrades]=useState<Record<string,number>>({}),[topK,setTopK]=useState(10)
  const [answer,setAnswer]=useState({correctness:'unknown',faithfulness:'unknown',citation_accuracy:'unknown'})
  const [compareIds,setCompareIds]=useState(''),[comparison,setComparison]=useState<unknown>(null)
  const pending=useRef(false),retry=useRef<{key:string;payload:unknown}|null>(null)
  const run=value?.retrieval_runs.find(item=>item.run_id===runId)
  async function read() {
    const response=await fetch(`/api/v1/research/${encodeURIComponent(sessionId)}/quality`)
    const data=await response.json()
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:t("质量记录读取失败。"))
    setValue(data)
    if(value?.binding_id&&value.binding_id!==data.binding_id){setGrades({});setRunId('');retry.current=null}
  }
  async function perform(action:'read'|'save'|'compare') {
    if(pending.current)return
    pending.current=true;setBusy(true);setError('');setSaved('')
    try {
      if(action==='read')await read()
      else if(action==='compare') {
        const ids=[...new Set([sessionId,...compareIds.split(/[\s,，]+/).filter(Boolean)])]
        if(ids.length<2||ids.length>8)throw new Error(t("填写1至7个其他本人任务ID。"))
        const params=new URLSearchParams();ids.forEach(id=>params.append('session_ids',id))
        const response=await fetch('/api/v1/research/quality/compare?'+params)
        const data=await response.json()
        if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:t("比较记录读取失败。"))
        setComparison(data)
      } else {
        if(!value)throw new Error(t("请先读取质量记录。"))
        if(kind==='corrected'&&!note.trim())throw new Error(t("请说明需要纠正的内容及依据。"))
        if(kind==='ranking_assessment'&&(!run||!Object.keys(grades).length))throw new Error(t("请选择检索步骤并明确标注至少一个候选。"))
        if(kind==='ranking_assessment'&&(!Number.isInteger(topK)||topK<1||topK>100))throw new Error(t("K需要填写1至100的整数。"))
        const body={binding_id:value.binding_id,kind,target_id:'report',note,
          ...(kind==='ranking_assessment'?{ranking:{run_id:runId,grades,top_k:topK}}:{}),
          ...(kind==='answer_assessment'?{answer}:{})}
        const key=JSON.stringify(body)
        if(retry.current?.key!==key)retry.current={key,payload:{...body,request_id:crypto.randomUUID()}}
        const response=await fetch(`/api/v1/research/${encodeURIComponent(sessionId)}/feedback`,{
          method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(retry.current.payload)})
        const data=await response.json()
        if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:t("反馈未能保存。"))
        setSaved(data.replayed?t("此前反馈已保存。"):t("反馈已保存。"));retry.current=null;setNote('')
        try{await read()}catch{setError(t("反馈已保存，记录刷新未完成；可稍后重新读取。"))}
      }
    }catch(failure){setError(failure instanceof Error?uiMessage(failure.message):t("操作未完成。"))}
    finally{pending.current=false;setBusy(false)}
  }
  return <details data-app-only className="card p-4 text-sm" aria-label={t("研究质量与反馈")}>
    <summary className="cursor-pointer font-medium">{t("研究质量与反馈")}</summary>
    <p className="my-2 text-xs text-xmgray-500">{t("查看本任务保留的资料、检索与审核记录。阅读或采纳不等于事实正确；纠错保存为反馈，需要确认后再修订报告。")}</p>
    <button type="button" className="btn-ghost text-xs" disabled={busy} onClick={()=>perform('read')}>{t("读取 / 刷新质量记录")}</button>
    {busy&&<p role="status">{t("正在处理…")}</p>}{saved&&<p role="status" className="my-2 text-green-800">{saved}</p>}
    {error&&<p role="alert" className="my-2 text-red-700">{uiMessage(error)}</p>}
    {value&&<>
      {value.question_coverage&&<QuestionCoverage value={value.question_coverage}/>}
      <p className="my-2">{t("保留证据 ")}{value.data.retained_evidence} {t(" 条；工具调用 ")}{value.agent.tool_calls} {t(" 次，其中失败或停止 ")}{value.agent.failed_or_stopped_calls} {t("次。 陈述核对")}{value.answer.model_audit_supported_claims??t("未知")} / {value.answer.model_audit_total_claims??t("未知")} {t(" 项，")}{value.answer.audit_complete?t("已完成记录"):t("尚不完整")}。
        {typeof value.answer.model_audit_source_supported_claims==='number' && <>{t("其中原文支持 ")}{value.answer.model_audit_source_supported_claims} {t(" 项，任务方法依据支持 ")}{value.answer.model_audit_method_supported_claims ?? 0} {t(" 项。")}</>}</p>
      <p className="text-xs">{t("统计快照：")}{!value.statistics_review.available?t("本任务无统计快照"):value.statistics_review.issues.length?t("{0}处算术或集合差异", value.statistics_review.issues.length):t("未记录算术或集合差异")}{t("。解析准确率和真实全集召回率需要独立标注。")}</p>
      <details className="my-2"><summary>{t("资料覆盖与统计依据")}</summary><pre className="overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify({data:value.data,statistics:value.statistics_review},null,2)}</pre></details>
      <details className="my-2"><summary>{t("模型、工具与本地计算用量")}</summary><p className="text-xs">{t("已知价格的小计与未定价项目分开；本地计算时间不折算为虚构账单，也不重复计入绘图模型费用。")}</p><pre className="max-h-96 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(value.runtime_ledger,null,2)}</pre></details>
      {!!value.improvement_candidates.length&&<ul className="my-2 list-disc pl-5">{value.improvement_candidates.map(item=><li key={item.kind}>{item.action}</li>)}</ul>}
      <div className="my-3 space-y-2 border-t pt-3">
        <label className="block">{t("反馈类型")}<select className="input-xm ml-2" value={kind} disabled={busy} onChange={event=>setKind(event.target.value as Kind)}>
          {(Object.keys(labels) as Kind[]).map(key=><option key={key} value={key}>{labels[key]}</option>)}</select></label>
        {kind==='answer_assessment'&&<div className="flex flex-wrap gap-3">{Object.entries({correctness:t("答案正确"),faithfulness:t("忠于所引资料"),citation_accuracy:t("引用匹配")}).map(([key,label])=>
          <label key={key}>{label}<select className="input-xm ml-1" disabled={busy} value={answer[key as keyof typeof answer]}
            onChange={event=>setAnswer(previous=>({...previous,[key]:event.target.value}))}>
            <option value="unknown">{t("尚未判断")}</option><option value="yes">{t("是")}</option><option value="no">{t("否")}</option></select></label>)}</div>}
        {kind==='ranking_assessment'&&<>
          <p className="text-xs">{t("分数仅表示对本步骤问题的相关性。未判断候选保留空值；标完整个返回池后才能计算池内Recall与NDCG，不代表全库召回。")}</p>
          <label>{t("检索步骤")}<select className="input-xm ml-2 max-w-full" value={runId} disabled={busy} onChange={event=>{setRunId(event.target.value);setGrades({})}}>
            <option value="">{t("请选择")}</option>{value.retrieval_runs.map(item=><option key={item.run_id} value={item.run_id}>{item.node_id} · {item.tool} · {item.candidates.length}{t("条")}</option>)}</select></label>
          <label className="ml-3">K <input type="number" className="input-xm w-20" min={1} max={100} value={topK} disabled={busy} onChange={event=>setTopK(Number(event.target.value))}/></label>
          {run&&<><p className="my-2 whitespace-pre-wrap">{t("本步骤问题：")}{run.query}</p><ol className="max-h-80 space-y-2 overflow-auto">{run.candidates.map(item=><li key={item.candidate_id} className="flex items-center justify-between gap-3">
            <span className="min-w-0 break-words">{item.rank}. {item.title||item.candidate_id}</span>
            <select className="input-xm shrink-0" aria-label={t("第{0}条相关性", item.rank)} disabled={busy} value={grades[item.candidate_id]??''} onChange={event=>setGrades(previous=>{
              const next={...previous};if(event.target.value==='')delete next[item.candidate_id];else next[item.candidate_id]=Number(event.target.value);return next})}>
              <option value="">{t("未判断")}</option><option value="0">{t("0 无关")}</option><option value="1">{t("1 略相关")}</option><option value="2">{t("2 相关")}</option><option value="3">{t("3 高度相关")}</option></select>
          </li>)}</ol></>}
        </>}
        <label className="block">{t("说明与依据")}<textarea className="input-xm mt-1 w-full" rows={3} maxLength={4000} disabled={busy} value={note} onChange={event=>setNote(event.target.value)}/></label>
        <button type="button" className="btn-primary text-xs" disabled={busy} onClick={()=>perform('save')}>{t("保存反馈")}</button>
      </div>
      {!!value.ranking_judgments.length&&<div className="my-3 overflow-auto"><table className="w-full text-left text-xs"><caption>{t("已标注的返回候选池")}</caption>
        <thead><tr><th>{t("步骤")}</th><th>{t("已标/返回")}</th><th>{t("池内Recall@K")}</th><th>NDCG@K</th><th>MRR</th><th>Pairwise</th></tr></thead>
        <tbody>{value.ranking_judgments.map(item=><tr key={item.run_id}><td>{item.run_id}</td><td>{item.judged_count}/{item.pool_size}</td><td>{percent(item.recall_at_k)}</td><td>{percent(item.ndcg_at_k)}</td><td>{item.mrr??t("缺少标注")}</td><td>{percent(item.pairwise_accuracy)}</td></tr>)}</tbody></table></div>}
      <details className="my-2"><summary>{t("反馈记录（")}{value.feedback.length}{t("条）")}</summary><ul className="space-y-2">{value.feedback.map(item=><li key={item.request_id}>
        {labels[item.kind as Kind]||item.kind} · {new Date(item.created_at).toLocaleString()}<p className="whitespace-pre-wrap">{item.payload.note}</p>
        {item.payload.answer&&<pre className="text-xs">{JSON.stringify(item.payload.answer,null,2)}</pre>}</li>)}</ul>
        {!!value.historical_feedback_count&&<p className="text-xs">{t("另有")}{value.historical_feedback_count}{t("条绑定旧快照的反馈，不计入当前版本。")}</p>}</details>
      <details className="my-2"><summary>{t("比较本人已有任务")}</summary>
        <p className="text-xs">{t("只读取已有记录，不重新检索或调用模型。问题、范围或交付要求不同会标记不可直接比较，不自动产生节省比例或改变配置。")}</p>
        <label className="block">{t("其他任务ID（逗号分隔）")}<input className="input-xm my-2 w-full" value={compareIds} disabled={busy} onChange={event=>setCompareIds(event.target.value)}/></label>
        <button type="button" className="btn-ghost text-xs" disabled={busy} onClick={()=>perform('compare')}>{t("读取比较记录")}</button>
        {comparison!=null&&<pre className="max-h-96 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(comparison,null,2)}</pre>}
      </details>
    </>}
  </details>
}
