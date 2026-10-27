import {t} from '../i18n'
import {layoutImportError} from './reportLayouts'

export interface LayoutOperation {operation_id:string;status:string;stage:string;source_id:string|null;attempts:number;max_attempts:number;error_code:string|null;error_category:string|null}
type Stage={stage:string;attempt?:number;status?:string}
export class LayoutOperationFailure extends Error {
  constructor(public code:string,public retry:'same'|'new'|'none'='none') {super(layoutImportError(code))}
}
const base='/api/v1/research/layout-samples/operations'
const aborted=()=>new DOMException('Canceled','AbortError')
function delay(ms:number,signal:AbortSignal){
  return new Promise<void>((resolve,reject)=>{
    if(signal.aborted){reject(aborted());return}
    const timer=window.setTimeout(()=>{signal.removeEventListener('abort',stop);resolve()},ms)
    function stop(){clearTimeout(timer);reject(aborted())}
    signal.addEventListener('abort',stop,{once:true})
  })
}
async function request(url:string,options:RequestInit,signal:AbortSignal,onReconnect?:()=>void){
  for(let attempt=0;attempt<3;attempt++){
    const attemptController=new AbortController(),stop=()=>attemptController.abort()
    const timeout=window.setTimeout(stop,options.method==='POST'?50_000:8_000)
    signal.addEventListener('abort',stop,{once:true})
    try{
      if(signal.aborted)throw aborted()
      const response=await fetch(url,{...options,signal:attemptController.signal})
      if((response.status===408||response.status>=500)&&attempt<2){onReconnect?.();await delay(300*(2**attempt),signal);continue}
      return response
    }catch(error){
      if(signal.aborted)throw aborted()
      if(attempt===2)throw new LayoutOperationFailure('layout_connection_lost','same')
      onReconnect?.();await delay(300*(2**attempt),signal)
    }finally{clearTimeout(timeout);signal.removeEventListener('abort',stop)}
  }
  throw new LayoutOperationFailure('layout_connection_lost','same')
}
async function readResponse(response:Response){
  let body:any={}
  try{body=await response.json()}catch{if(!response.ok)throw new LayoutOperationFailure('layout_connection_lost','same')}
  if(!response.ok){
    const code=typeof body.detail==='string'?body.detail:'layout_connection_lost'
    throw new LayoutOperationFailure(code,response.status===408||response.status>=500?'same':'none')
  }
  return body
}
export async function submitLayoutOperation(file:File,id:string,signal:AbortSignal,onReconnect:()=>void):Promise<LayoutOperation>{
  const data=new FormData();data.append('file',file);data.append('request_id',id)
  return await readResponse(await request(base,{method:'POST',body:data},signal,onReconnect)) as LayoutOperation
}
export async function getLayoutOperation(id:string,signal:AbortSignal,onReconnect?:()=>void):Promise<LayoutOperation>{
  return await readResponse(await request(`${base}/${encodeURIComponent(id)}`,{},signal,onReconnect)) as LayoutOperation
}
export async function getLayoutSample(id:string,signal:AbortSignal,onReconnect?:()=>void){
  return await readResponse(await request(`/api/v1/research/layout-samples/${encodeURIComponent(id)}`,{},signal,onReconnect))
}
export async function cancelLayoutOperation(id:string):Promise<LayoutOperation>{
  const controller=new AbortController()
  return await readResponse(await request(`${base}/${encodeURIComponent(id)}`,{method:'DELETE',keepalive:true},controller.signal)) as LayoutOperation
}

export function stageLabel(event:Stage):string {
  const stages:Record<string,string>={queued:'等待解析',starting:'准备解析',reading:'读取样例',cleaning:'提取版式',preview:'准备空白预览',
    retrying:'解析中断，正在自动重试',completed:'版式已准备',failed:'解析未完成',canceled:'已取消'}
  return t(stages[event.stage]||'正在读取样例…')
}

/** Replayable SSE; on connection faults re-read the same owner's operation. */
export function followLayoutOperation(id:string,signal:AbortSignal,onStage:(stage:Stage)=>void,onReconnect:()=>void):Promise<LayoutOperation>{
  return new Promise((resolve,reject)=>{
    if(signal.aborted){reject(aborted());return}
    let settled=false,checking=false,terminalSeen=false,failures=0,lastRevision=0
    const source=new EventSource(`${base}/${encodeURIComponent(id)}/events`)
    const timeout=window.setTimeout(()=>void check(true),52_000)
    function finish(value:LayoutOperation|Error){
      if(settled)return;settled=true;source.close();clearTimeout(timeout);signal.removeEventListener('abort',stop)
      if(value instanceof Error)reject(value);else resolve(value)
    }
    function stop(){finish(aborted())}
    async function check(final=false){
      if(settled||checking)return
      checking=true
      try{
        const state=await getLayoutOperation(id,signal,onReconnect)
        if(['completed','failed','canceled'].includes(state.status)){finish(state);return}
        if(final||++failures>=3)finish(new LayoutOperationFailure('layout_connection_lost','same'))
      }catch(error){finish(error instanceof Error?error:new LayoutOperationFailure('layout_connection_lost','same'))}
      finally{checking=false;if(terminalSeen&&!settled)void check(true)}
    }
    signal.addEventListener('abort',stop,{once:true})
    source.addEventListener('progress',event=>{
      try{
        const value=JSON.parse((event as MessageEvent).data) as Stage&{revision?:number}
        if((value.revision||0)<=lastRevision)return
        lastRevision=value.revision||lastRevision;failures=0;onStage(value)
        if(value.status&&['completed','failed','canceled'].includes(value.status)){terminalSeen=true;source.close();void check(true)}
      }catch{finish(new LayoutOperationFailure('layout_progress_invalid','same'))}
    })
    source.onerror=()=>{if(!settled){onReconnect();void check()}}
  })
}
