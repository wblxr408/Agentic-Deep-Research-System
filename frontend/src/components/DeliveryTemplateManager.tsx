import {t,useLocale,uiMessage} from '../i18n'
import { useRef,useState } from 'react'

interface TemplateRecord {template_id:string;version:number;name:string;project_label:string|null;configuration:Record<string,unknown>}
function ordered(value:unknown):unknown {
  if(Array.isArray(value))return value.map(ordered)
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([key,item])=>[key,ordered(item)]))
  return value
}
async function readJson(response:Response) {
  const value=await response.json()
  if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:t("模板配置不完整或请求未完成。"))
  return value
}
export default function DeliveryTemplateManager({configuration,onApply}:{configuration:unknown;onApply:(configuration:Record<string,unknown>,origin:{template_id:string;version:number})=>void}) {
  useLocale()

  const [items,setItems]=useState<TemplateRecord[]>([]),[selected,setSelected]=useState<TemplateRecord|null>(null)
  const [versions,setVersions]=useState<TemplateRecord[]>([]),[name,setName]=useState(''),[project,setProject]=useState('')
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('')
  const pending=useRef(false),request=useRef<{key:string;id:string}|null>(null)
  const unchanged=Boolean(selected&&selected.name===name.trim()&&(selected.project_label||'')===project.trim()
    &&JSON.stringify(ordered(selected.configuration))===JSON.stringify(ordered(configuration)))
  async function run(action:()=>Promise<void>) {
    if(pending.current)return
    pending.current=true;setBusy(true);setError('');setMessage('')
    try{await action()}catch(error){setError(error instanceof Error?uiMessage(error.message):t("模板操作未完成。"))}
    finally{pending.current=false;setBusy(false)}
  }
  async function refresh() {
    const result=await readJson(await fetch('/api/v1/research/delivery-templates'))
    setItems(result.items)
  }
  function choose(id:string) {
    const item=items.find(item=>item.template_id===id)||null
    setSelected(item);setVersions([])
    if(item){setName(item.name);setProject(item.project_label||'')}
  }
  async function save(asNew:boolean) {
    const path=`/api/v1/research/delivery-templates${!asNew&&selected?'/'+encodeURIComponent(selected.template_id):''}`
    const body={name:name.trim(),project_label:project.trim()||null,configuration,
      expected_version:asNew?null:selected?.version}
    const key=JSON.stringify({path,body})
    if(request.current?.key!==key)request.current={key,id:crypto.randomUUID()}
    const saved=await readJson(await fetch(path,{method:asNew?'POST':'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({...body,request_id:request.current!.id})})) as TemplateRecord
    setSelected(saved);setVersions([]);setMessage(t("已保存“{0}”。", saved.name))
    try{await refresh()}catch{setError(t("模板已保存；列表刷新未完成，可再次读取已保存样式。"))}
  }
  return <details className="choice-more saved-template-manager">
    <summary className="cursor-pointer text-sm">{t("我的报告样式")}</summary>

    <div className="space-y-2">
      <button type="button" className="btn-ghost text-xs" disabled={busy} onClick={()=>run(refresh)}>{t("读取已保存样式")}</button>
      <label className="block text-xs">{t("已保存样式")}<select className="input-xm mt-1 w-full" value={selected?.template_id||''} disabled={busy} onChange={event=>choose(event.target.value)}>
        <option value="">{t("选择样式")}</option>{items.map(item=><option key={item.template_id} value={item.template_id}>{item.name}{item.project_label?` · ${item.project_label}`:''}</option>)}
      </select></label>
      {selected&&<div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-ghost text-xs" disabled={busy} onClick={()=>run(async()=>{
          const result=await readJson(await fetch(`/api/v1/research/delivery-templates/${encodeURIComponent(selected.template_id)}/versions`))
          setVersions(result.items)
        })}>{t("历史样式")}</button>
        {!!versions.length&&<label className="text-xs">{t("保存记录")}<select className="input-xm ml-2" value={selected.version} disabled={busy} onChange={event=>setSelected(versions.find(item=>item.version===Number(event.target.value))||null)}>
          {versions.map(item=><option key={item.version} value={item.version}>{t("第 ")}{item.version} {t(" 次保存")}</option>)}
        </select></label>}
        <button type="button" className="btn-ghost text-xs" disabled={busy} onClick={()=>{
          onApply(selected.configuration,{template_id:selected.template_id,version:selected.version});setMessage(t("已选用“{0}”。", selected.name))
        }}>{t("使用这个样式")}</button>
      </div>}
      <label className="block text-xs">{t("样式名称")}<input className="input-xm mt-1 w-full" maxLength={300} value={name} disabled={busy} onChange={event=>setName(event.target.value)}/></label>
      <label className="block text-xs">{t("归类（可选）")}<input className="input-xm mt-1 w-full" maxLength={300} value={project} disabled={busy} onChange={event=>setProject(event.target.value)}/></label>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-ghost text-xs" disabled={busy||!name.trim()} onClick={()=>run(()=>save(true))}>{t("另存一个样式")}</button>
        <button type="button" className="btn-ghost text-xs" disabled={busy||!selected||!name.trim()||unchanged} onClick={()=>run(()=>save(false))}>{t("更新这个样式")}</button>
      </div>
      {busy&&<p role="status" className="text-xs">{t("正在保存…")}</p>}
      {message&&<p role="status" className="text-xs">{uiMessage(message)}</p>}
      {error&&<p role="alert" className="text-xs text-red-700">{uiMessage(error)}</p>}
    </div>
  </details>
}
