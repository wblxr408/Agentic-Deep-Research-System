import {useEffect,useRef,useState} from 'react'
import type {CSSProperties,ReactNode} from 'react'
import {t,uiMessage,useLocale} from '../i18n'
import {Icon,TraceLoader} from './Interface'
import {blankReportLayout,layoutBindings,layoutImportError,layoutInteractions,layoutKinds,layoutMissing,layoutProblem,layoutRole,layoutRoles,newLayoutBlock,nextLayoutId} from './reportLayouts'
import type {LayoutBlock,LayoutKind,LayoutSample,ReportLayout} from './reportLayouts'
import '../layout-editor.css'

interface LayoutDataPreview {binding:{sections:Array<{section_id:string;role:string;title:string;title_origin?:string;blocks:Array<{block_id:string;kind:LayoutKind;status:string;data?:{kind:string;markdown?:string;metric?:{label:string;display:string};items?:unknown[];reference?:{chart_id:string}}|null}>}>;unplaced_sections:Array<{title:string;markdown:string}>};charts:Array<{chart_id:string;title:string}>}
interface Props {layout?:ReportLayout|null;sample?:LayoutSample|null;active:boolean;onChange:(layout:ReportLayout,sample?:LayoutSample|null)=>void;onManual:()=>void;onBusy:(busy:boolean)=>void;drawingMode:string;drawingSkills:Array<{id:string;name:string}>;slotSkills:Record<string,string>;onSlotSkillChange:(id:string,skill:string)=>void;previewSessionId?:string;previewDelivery:unknown}
function Field({label,children}:{label:string;children:ReactNode}){return <label className="layout-field"><span>{label}</span>{children}</label>}

export function BlankLayoutPreview({layout}:{layout:ReportLayout}) {
  useLocale()
  const tokens=layout.tokens
  const style={'--layout-paper':tokens.background,'--layout-ink':tokens.foreground,'--layout-accent':tokens.accent,'--layout-title':`${tokens.title_px}px`,'--layout-body':`${tokens.body_px}px`,'--layout-gap':`${tokens.spacing}px`,fontFamily:tokens.font==='serif'?"Georgia,'Songti SC',serif":tokens.font==='mono'?"Consolas,monospace":"'Segoe UI','Microsoft YaHei',sans-serif"} as CSSProperties
  return <div className={`layout-preview layout-preview--${layout.density}`} style={style} data-width={tokens.width} aria-label={t('空白版式预览')}>
    <div className="layout-preview-caption">{t('空白预览')}</div>
    {layout.running_header&&<div className="layout-running">{t('页眉')}</div>}
    <h3 className="layout-preview-title">{t('报告标题')}</h3>
    {layout.interactions.includes('contents')&&<div className="layout-preview-toc">{layout.sections.map((section,i)=><span key={section.section_id}>{String(i+1).padStart(2,'0')} {layoutRole(section.role)}</span>)}</div>}
    {layout.sections.map((section,i)=><section className="layout-preview-section" key={section.section_id}>
      <h4><span>{String(i+1).padStart(2,'0')}</span>{layoutRole(section.role)}</h4>
      <div className="layout-preview-grid">{section.blocks.map(block=><div key={block.block_id} className={`layout-slot layout-slot--${block.kind}`} style={{gridColumn:`span ${block.span}`}} data-aspect={block.aspect}>
        <span>{layoutKinds[block.kind]}</span>
        {['text','list','callout'].includes(block.kind)?<div className="layout-lines" aria-hidden="true"><i/><i/><i/></div>:block.kind==='table'?<div className="layout-table-shape" aria-hidden="true">{Array.from({length:9},(_,n)=><i key={n}/>)}</div>:block.kind==='heading'?<div className="layout-heading-shape" aria-hidden="true"/>:<Icon name={block.kind==='chart'?'chart':block.kind==='metric'?'target':'source'} size={30}/>}
      </div>)}</div>
    </section>)}
    {layout.running_footer&&<div className="layout-running">{t('页脚')}</div>}
  </div>
}

export default function ReportLayoutEditor({layout,sample,active,onChange,onManual,onBusy,drawingMode,drawingSkills,slotSkills,onSlotSkillChange,previewSessionId,previewDelivery}:Props) {
  useLocale()
  const [tab,setTab]=useState<'edit'|'preview'|'data'>('edit'),[selected,setSelected]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const [dataPreview,setDataPreview]=useState<{key:string;value:LayoutDataPreview}|null>(null),[previewing,setPreviewing]=useState(false),[previewError,setPreviewError]=useState('')
  const upload=useRef<HTMLInputElement>(null),controller=useRef<AbortController|null>(null),generation=useRef(0),pending=useRef<{file:File;id:string}|null>(null)
  const previewController=useRef<AbortController|null>(null),previewGeneration=useRef(0),previewKey=JSON.stringify({session:previewSessionId,delivery:previewDelivery}),currentPreviewKey=useRef(previewKey);currentPreviewKey.current=previewKey
  const current=useRef({onChange,onBusy});current.current={onChange,onBusy}
  useEffect(()=>()=>{generation.current++;controller.current?.abort();controller.current=null;previewGeneration.current++;previewController.current?.abort()},[])
  const index=Math.min(selected,Math.max(0,(layout?.sections.length||1)-1)),section=layout?.sections[index]
  const blocks=layout?.sections.flatMap(s=>s.blocks)||[],figures=blocks.filter(b=>['chart','image'].includes(b.kind)).length
  const selectedDrawingOverrides=Object.values(slotSkills).filter(Boolean).length
  function cancel(){generation.current++;controller.current?.abort();controller.current=null;pending.current=null;setBusy(false);onBusy(false);setError('')}
  function update(next:ReportLayout){onChange(next);setError('')}
  function updateSection(patch:Partial<NonNullable<typeof section>>){if(layout)update({...layout,sections:layout.sections.map((s,i)=>i===index?{...s,...patch}:s)})}
  function updateBlock(id:string,patch:Partial<LayoutBlock>){if(section)updateSection({blocks:section.blocks.map(b=>b.block_id===id?{...b,...patch}:b)})}
  function moveSection(delta:number){if(!layout)return;const sections=[...layout.sections];[sections[index],sections[index+delta]]=[sections[index+delta],sections[index]];update({...layout,sections});setSelected(index+delta)}
  async function previewData(){
    if(!previewSessionId)return
    previewController.current?.abort();const abort=new AbortController(),stamp=++previewGeneration.current,key=previewKey;previewController.current=abort
    setPreviewing(true);setPreviewError('');setTab('data')
    try{
      const response=await fetch(`/api/v1/research/${encodeURIComponent(previewSessionId)}/layout-preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(previewDelivery),signal:abort.signal})
      if(!response.ok)throw new Error(t('暂时无法读取原研究的预览。'))
      const result=await response.json() as LayoutDataPreview
      if(stamp===previewGeneration.current&&currentPreviewKey.current===key)setDataPreview({key,value:result})
    }catch(cause){if(stamp===previewGeneration.current&&!abort.signal.aborted)setPreviewError(cause instanceof Error?uiMessage(cause.message):t('暂时无法读取原研究的预览。'))}
    finally{if(stamp===previewGeneration.current){previewController.current=null;setPreviewing(false)}}
  }
  async function importFile(file:File,retry=false){
    if(!/\.(html?|docx)$/i.test(file.name)){setError(t('请选择 HTML 或 DOCX 文件。'));return}
    if(!file.size||file.size>2*1024*1024){setError(t('文件需在 2 MB 以内，且不能为空。'));return}
    controller.current?.abort();const stamp=++generation.current,abort=new AbortController();controller.current=abort
    if(!retry||pending.current?.file!==file)pending.current={file,id:crypto.randomUUID()}
    const data=new FormData();data.append('file',file);data.append('request_id',pending.current!.id)
    setBusy(true);onBusy(true);setError('')
    let applied=false
    try{
      const response=await fetch('/api/v1/research/layout-samples',{method:'POST',body:data,signal:abort.signal})
      const result=await response.json()
      if(!response.ok)throw new Error(layoutImportError(typeof result.detail==='string'?result.detail:''))
      const problem=layoutProblem(result.layout)
      if(problem)throw new Error(problem)
      if(stamp!==generation.current)return
      current.current.onChange(result.layout,{source_id:result.source_id,file_name:result.file_name,parse:result.parse});applied=true;setSelected(0);setTab('preview');pending.current=null
    }catch(cause){if(stamp===generation.current&&!abort.signal.aborted)setError(cause instanceof Error?uiMessage(cause.message):t('导入未完成，请重试。'))}
    finally{if(stamp===generation.current){setBusy(false);controller.current=null;if(!applied)current.current.onBusy(false)}}
  }
  return <div className="layout-workbench">
    <div className="layout-entry-actions"><button type="button" className="btn-primary" disabled={busy} onClick={()=>upload.current?.click()}><Icon name="source" size={16}/>{t('导入样例')}</button><button type="button" className="btn-ghost" disabled={busy} onClick={()=>{onChange(blankReportLayout(),null);setTab('edit');setSelected(0);setError('')}}>{t('从空白设计')}</button><button type="button" className="btn-ghost" disabled={busy} aria-pressed={!active} onClick={onManual}>{t('手动章节')}</button>{!active&&layout&&<button type="button" className="choice-text-button" onClick={()=>onChange(layout)}>{t('继续编辑版式')}</button>}</div>
    <input ref={upload} className="layout-file-input" type="file" accept=".html,.htm,.docx" aria-label={t('上传报告样例')} onChange={event=>{const file=event.target.files?.[0];event.target.value='';if(file)void importFile(file)}}/>
    {busy&&<div className="layout-feedback" role="status"><TraceLoader/>{t('正在读取样例…')}<button type="button" className="choice-text-button" onClick={cancel}>{t('取消导入')}</button></div>}
    {error&&<div className="layout-feedback layout-feedback--error" role="alert">{uiMessage(error)}{pending.current&&<button type="button" className="choice-text-button" onClick={()=>void importFile(pending.current!.file,true)}>{t('重试导入')}</button>}</div>}
    {active&&layout&&<>
      <div className="layout-toolbar"><div><strong>{t('{0} 章 · {1} 个组件',layout.sections.length,blocks.length)}</strong>{sample&&<span className="layout-source-name" title={sample.file_name}>{sample.file_name}</span>}</div><div className="layout-tabs" role="group" aria-label={t('版式视图')}><button type="button" aria-pressed={tab==='edit'} onClick={()=>setTab('edit')}>{t('编辑版式')}</button><button type="button" aria-pressed={tab==='preview'} onClick={()=>setTab('preview')}>{t('空白预览')}</button>{previewSessionId&&<button type="button" aria-pressed={tab==='data'} onClick={()=>void previewData()}>{t('原研究数据')}</button>}</div></div>
      {tab==='preview'?<BlankLayoutPreview layout={layout}/>:tab==='data'?<div className="layout-data-preview" aria-label={t('原研究数据预览')}>
        <p>{t('使用原研究结果预览。')}</p>{previewing&&<p role="status">{t('正在匹配资料…')}</p>}{previewError&&<p role="alert">{uiMessage(previewError)}</p>}
        {!previewing&&dataPreview?.key!==previewKey&&<button type="button" className="choice-text-button" onClick={()=>void previewData()}>{t('更新数据预览')}</button>}
        {dataPreview?.key===previewKey&&<>{dataPreview.value.binding.sections.map(section=><section key={section.section_id}><h4>{section.title_origin==='role_default'?layoutRole(section.role):section.title||layoutRole(section.role)}</h4>{section.blocks.map(block=>{const chart=dataPreview.value.charts.find(item=>item.chart_id===block.data?.reference?.chart_id),detail=block.data?.kind==='narrative'?block.data.markdown?.slice(0,180):block.data?.kind==='metric'?`${block.data.metric?.label||''} · ${block.data.metric?.display||''}`:block.data?.kind==='chart'?chart?.title:['sources','metrics','relationships','technical_comparison'].includes(block.data?.kind||'')?t('{0} 项资料',block.data?.items?.length||0):'';return <div className="layout-data-row" key={block.block_id}><span>{layoutKinds[block.kind]}</span><strong>{block.status==='required_missing'?t('等待资料'):block.status==='omitted'?t('已省略'):block.status==='missing'?t('暂无匹配资料'):block.status==='text_fallback'?t('已有文字'):t('已匹配')}</strong>{detail&&<p>{detail}</p>}</div>})}</section>)}{!!dataPreview.value.binding.unplaced_sections.length&&<section><h4>{t('其他研究内容')}</h4>{dataPreview.value.binding.unplaced_sections.map((item,index)=><div className="layout-data-row" key={index}><span>{item.title}</span><strong>{t('保留在完整报告')}</strong><p>{item.markdown.slice(0,180)}</p></div>)}</section>}</>}
      </div>:<div className="layout-editor-fields">
        <div className="layout-section-picker"><Field label={t('编辑章节')}><select aria-label={t('编辑章节')} value={index} onChange={e=>setSelected(Number(e.target.value))}>{layout.sections.map((s,i)=><option key={s.section_id} value={i}>{String(i+1).padStart(2,'0')} · {layoutRole(s.role)}</option>)}</select></Field><div className="layout-icon-actions"><button type="button" aria-label={t('版式章节上移')} disabled={!index} onClick={()=>moveSection(-1)}>↑</button><button type="button" aria-label={t('版式章节下移')} disabled={index>=layout.sections.length-1} onClick={()=>moveSection(1)}>↓</button><button type="button" aria-label={t('删除版式章节')} disabled={layout.sections.length<=1} onClick={()=>{update({...layout,sections:layout.sections.filter((_,i)=>i!==index)});setSelected(Math.max(0,index-1))}}><Icon name="close" size={15}/></button></div></div>
        {section&&<><div className="layout-fields-row"><Field label={t('章节用途')}><select aria-label={t('章节用途')} value={section.role} onChange={e=>updateSection({role:e.target.value})}>{Object.entries(layoutRoles).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></Field><Field label={t('分栏')}><select aria-label={t('版式分栏')} value={section.columns} onChange={e=>{const columns=Number(e.target.value);updateSection({columns,blocks:section.blocks.map(b=>({...b,span:b.kind==='heading'?12:12/columns}))})}}>{[1,2,3].map(n=><option key={n} value={n}>{t('{0} 栏',n)}</option>)}</select></Field></div>
          <div className="layout-component-list">{section.blocks.map((block,i)=><div className="layout-component-item" key={block.block_id}><div className="layout-component-row"><span className="layout-order">{String(i+1).padStart(2,'0')}</span><select aria-label={t('组件{0}类型',i+1)} value={block.kind} onChange={e=>updateBlock(block.block_id,{kind:e.target.value as LayoutKind,level:e.target.value==='heading'?3:null})}>{Object.entries(layoutKinds).map(([key,label])=><option key={key} value={key} disabled={['chart','image'].includes(key)&&!['chart','image'].includes(block.kind)&&figures>=12}>{label}</option>)}</select><select aria-label={t('组件{0}宽度',i+1)} value={block.span} onChange={e=>updateBlock(block.block_id,{span:Number(e.target.value)})}><option value={12}>{t('全行')}</option><option value={6}>{t('半行')}</option><option value={4}>{t('三分之一')}</option>{![12,6,4].includes(block.span)&&<option value={block.span}>{t('当前宽度')}</option>}</select><div className="layout-row-actions">{[-1,1].map(delta=><button type="button" key={delta} aria-label={t(delta<0?'组件{0}上移':'组件{0}下移',i+1)} disabled={delta<0?!i:i===section.blocks.length-1} onClick={()=>{const items=[...section.blocks];[items[i],items[i+delta]]=[items[i+delta],items[i]];updateSection({blocks:items})}}>{delta<0?'↑':'↓'}</button>)}<button type="button" aria-label={t('移除版式组件{0}',i+1)} onClick={()=>updateSection({blocks:section.blocks.filter(b=>b.block_id!==block.block_id)})}><Icon name="close" size={15}/></button></div></div>{['chart','image'].includes(block.kind)&&<Field label={t('图表形式')}><select aria-label={t('组件{0}图表形式',i+1)} value={block.chart_kind} onChange={e=>updateBlock(block.block_id,{chart_kind:e.target.value})}>{Object.entries({auto:t('自动选择'),none:t('文字为主'),line:t('折线图'),bar:t('条形图'),network:t('关系图'),timeline:t('时间线'),table:t('表格')}).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></Field>}{block.kind!=='heading'&&<details className="choice-more layout-component-options"><summary>{t('资料与缺口处理')}</summary><div className="layout-fields-row"><Field label={t('对应资料')}><select aria-label={t('组件{0}对应资料',i+1)} value={block.binding} onChange={e=>updateBlock(block.block_id,{binding:e.target.value})}>{Object.entries(layoutBindings).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></Field><Field label={t('资料不足时')}><select aria-label={t('组件{0}资料不足时',i+1)} value={block.missing} onChange={e=>updateBlock(block.block_id,{missing:e.target.value})}>{Object.entries(layoutMissing).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></Field>{['chart','table','image'].includes(block.kind)&&drawingMode!=='builtin'&&<Field label={t('绘图方法')}><select aria-label={t('组件{0}绘图方法',i+1)} value={slotSkills[block.block_id]||''} onChange={e=>onSlotSkillChange(block.block_id,e.target.value)}><option value="">{t('沿用整体选择')}</option>{drawingSkills.map(skill=><option key={skill.id} value={skill.id} disabled={!slotSkills[block.block_id]&&selectedDrawingOverrides>=12}>{skill.name}</option>)}</select></Field>}</div></details>}</div>)}</div>
          <button type="button" className="choice-add" disabled={blocks.length>=96||section.blocks.length>=32} onClick={()=>updateSection({blocks:[...section.blocks,newLayoutBlock(nextLayoutId('block',blocks.map(b=>b.block_id)),12/section.columns)]})}><Icon name="plus" size={15}/>{t('添加组件')}</button>
          {section.blocks.some(block=>['chart','image'].includes(block.kind))&&<details className="choice-more"><summary>{t('图形比例')}</summary><div className="layout-fields-row">{section.blocks.map((block,i)=>['chart','image'].includes(block.kind)&&<Field key={block.block_id} label={t('组件{0}比例',i+1)}><select aria-label={t('组件{0}比例',i+1)} value={block.aspect} onChange={event=>updateBlock(block.block_id,{aspect:event.target.value})}><option value="auto">{t('自动选择')}</option><option value="wide">{t('横向')}</option><option value="square">{t('方形')}</option><option value="portrait">{t('纵向')}</option></select></Field>)}</div></details>}
        </>}
        <button type="button" className="choice-add" disabled={layout.sections.length>=24} onClick={()=>{const section_id=nextLayoutId('section',layout.sections.map(s=>s.section_id));update({...layout,sections:[...layout.sections,{section_id,role:'general',level:2,columns:1,blocks:[newLayoutBlock(nextLayoutId('block',blocks.map(b=>b.block_id)))]}]});setSelected(layout.sections.length)}}><Icon name="plus" size={15}/>{t('添加版式章节')}</button>
        <details className="choice-more"><summary>{t('配色与排版')}</summary><div className="layout-token-grid">{(['background','foreground','accent'] as const).map((key,i)=><Field key={key} label={[t('纸面'),t('文字'),t('强调色')][i]}><input type="color" aria-label={[t('纸面颜色'),t('文字颜色'),t('强调色')][i]} value={layout.tokens[key]} onChange={e=>update({...layout,tokens:{...layout.tokens,[key]:e.target.value}})}/></Field>)}</div><div className="layout-fields-row"><Field label={t('字体')}><select aria-label={t('版式字体')} value={layout.tokens.font} onChange={e=>update({...layout,tokens:{...layout.tokens,font:e.target.value as ReportLayout['tokens']['font']}})}><option value="sans">{t('无衬线')}</option><option value="serif">{t('衬线')}</option><option value="mono">{t('等宽')}</option></select></Field><Field label={t('疏密')}><select aria-label={t('版式疏密')} value={layout.density} onChange={e=>update({...layout,density:e.target.value as ReportLayout['density']})}><option value="compact">{t('紧凑')}</option><option value="standard">{t('标准')}</option><option value="spacious">{t('舒展')}</option></select></Field></div><div className="layout-fields-row">{(['title_px','body_px','spacing'] as const).map((key,i)=><Field key={key} label={[t('标题字号'),t('正文字号'),t('区块间距')][i]}><input type="range" aria-label={[t('版式标题字号'),t('版式正文字号'),t('版式区块间距')][i]} min={[24,14,8][i]} max={[96,24,48][i]} value={layout.tokens[key]} onChange={e=>update({...layout,tokens:{...layout.tokens,[key]:Number(e.target.value)}})}/><output>{layout.tokens[key]}</output></Field>)}</div></details>
        <details className="choice-more"><summary>{t('交互与页眉页脚')}</summary><div className="choice-checks">{Object.entries(layoutInteractions).map(([key,label])=><label key={key}><input type="checkbox" checked={layout.interactions.includes(key)} onChange={e=>update({...layout,interactions:e.target.checked?[...layout.interactions,key]:layout.interactions.filter(k=>k!==key)})}/>{label}</label>)}{(['running_header','running_footer'] as const).map((key,i)=><label key={key}><input type="checkbox" checked={layout[key]} onChange={e=>update({...layout,[key]:e.target.checked})}/>{i?t('页脚'):t('页眉')}</label>)}</div></details>
        {sample&&<details className="choice-more"><summary>{t('解析记录')}</summary><p>{t('{0} 格式',sample.parse.format.toUpperCase())}</p>{sample.parse.locations[section?.section_id||'']?.line!==undefined&&<p>{t('当前章节来自第 {0} 行',sample.parse.locations[section!.section_id].line)}</p>}{sample.parse.differences.map(key=><p key={key}>{t(({external_assets_omitted:'图像保留为占位。',source_scripts_not_used:'原脚本已移除。',complex_css_requires_adjustment:'复杂样式可在编辑器调整。',source_images_omitted:'图像保留为占位。',floating_objects_require_adjustment:'浮动对象可在编辑器调整。'} as Record<string,string>)[key]||'可在编辑器调整版式。')}</p>)}</details>}
      </div>}
    </>}
  </div>
}
