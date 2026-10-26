import {t,useLocale,uiMessage} from '../i18n'
import {useRef,useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import ResearchComposer from './ResearchComposer'
import {choiceProblem} from './ResearchOptionsEditor'
import {setupFromRequest,setupRequest} from './researchSetup'
import type {ResearchSetup} from './researchSetup'
import type {UnderstandingSnapshot} from './QueryUnderstandingPanel'

async function post(path:string,body:unknown) {
  const response=await fetch(`/api/v1/research${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  const value=await response.json().catch(()=>({detail:t("暂时没有收到完整结果，请重试。")}))
  if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:t("请检查对象、日期和报告选择后重新预览。"))
  return value
}
export default function ResearchConfigurationEditor({query,parameters,onStarted}:{query:string;parameters?:Record<string,unknown>;onStarted:(sessionId:string)=>void}) {
  useLocale()

  const [value,setValue]=useState(()=>setupFromRequest(parameters,query)),[preview,setPreview]=useState<{key:string;value:UnderstandingSnapshot}|null>(null)
  const [busy,setBusy]=useState(false),[starting,setStarting]=useState(false),[error,setError]=useState('')
  const pending=useRef(false),current=useRef(value),input=useRef<HTMLTextAreaElement>(null);current.current=value
  const skills=useQuery<{items:Array<{id:string;name:string;enabled:boolean}>}>({queryKey:['skills'],queryFn:async()=>{const response=await fetch('/api/v1/skills');if(!response.ok)throw new Error(t("暂时无法读取研究方法"));return response.json()}})
  const key=JSON.stringify(value),ready=preview?.key===key&&!!preview.value.ready
  function change(next:ResearchSetup){current.current=next;setValue(next);setError('')}
  async function perform(start:boolean){
    if(pending.current)return
    const problem=choiceProblem(value);if(problem){setError(uiMessage(problem.message));return}
    pending.current=true;setBusy(true);setStarting(start);setError('')
    try{
      const body=setupRequest(value)
      if(start){
        if(!ready||!preview)throw new Error(t("请先预览当前选择。"))
        const created=await post('',{...body,query_preview_id:preview.value.interpretation_id})
        if(typeof created.session_id!=='string')throw new Error(t("新研究尚未创建，请重试。"))
        onStarted(created.session_id)
      }else{
        const snapshot=await post('/understanding',body) as UnderstandingSnapshot
        if(JSON.stringify(current.current)!==key)return
        setPreview({key,value:snapshot})
      }
    }catch(cause){setError(cause instanceof Error?uiMessage(cause.message):t("暂时无法处理，请重试。"))}
    finally{pending.current=false;setBusy(false);setStarting(false)}
  }
  return <details className="restart-choices" aria-label={t("调整后重新研究")}><summary>{t("调整后重新研究")}<small>{t("从当前选择开始")}</small></summary><ResearchComposer restart value={value} onChange={change} inputRef={input} onStart={()=>void perform(true)} onPreview={()=>void perform(false)} busy={busy} starting={starting} understanding={preview?.value||null} previewCurrent={preview?.key===key} error={uiMessage(error)} skills={skills.data?.items||[]}/></details>
}
