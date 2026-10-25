import { useEffect, useId, useState } from 'react'
import { AppearanceControls } from './Appearance'
import { Icon } from './Interface'
import '../technical.css'

interface Topic { id: string; title: string; summary: string; steps: Array<[string,string]>; notes: string[]; branches?: Array<[number,number]> }
const topics: Topic[] = [
  {id:'planning',title:'研究编排',summary:'明确问题，组织取证、分析和交付。能够独立研究的子问题才并行。',
    steps:[['研究问题','提取对象、时间、学科、目的与交付要求。'],['研究计划','明确依赖、取证目标、原任务额度与停止条件。'],['取证工具','搜索、网页读取和内部资料检索按需调用。'],['问题分析','围绕子问题阅读原文，保留方法、实验条件和数字。'],['核对与补证','结论对照来源；有具体缺口时进行有界补证。'],['图文交付','组织判断、图表、来源和技术附录。']],
    notes:['Planner 负责计划；Analyst 负责分析；报告阶段组织交付。','Search、Browser、RAG 是取证工具，阶段 Skill 提供方法约束。','补证材料未变且完成分析的输入绑定有效时，复用原分析。']},
  {id:'matching',title:'对象与匹配',summary:'企业、高校与实验室可组合选择，评价规则随学科变化。',
    steps:[['研究对象','选择具体实体，保存别称和历史隶属。'],['学科范围','指定学科和主题，调整技术分类。'],['评价体系','选择适用的 CCF、JCR、中科院分区等体系及版本。'],['范围筛选','按时间、来源、对象和必要条件筛选。'],['权重匹配','分层组合技术契合、研究演进和合作资源维度。'],['结果比较','查看指标依据及覆盖，调整后重排候选。']],
    notes:['目的可选择布局与演进、合作发现或综合研究。','指标来源和版本随配置保留，缺失信息按实际覆盖展示。','代表成果的技术价值通过全文分析呈现。']},
  {id:'evidence',title:'网上取证',summary:'沿学术索引与官方来源检索，取得可定位、可引用的资料。',
    steps:[['发现线索','搜索出版商、学术索引、机构和项目官网。'],['读取原文','读取 HTML、论文 PDF、产品文档与官方公告。'],['结构解析','提取正文、表格、标题与图文关系，记录原文位置。'],['证据留存','保存来源、取得时间、原文与解析版本，合并重复观察。'],['分析引用','按问题选取相关段落，结论关联原文范围。'],['显式归档','将选定材料归档，在授权范围内后续使用。']],
    notes:['论文发现使用 DBLP、arXiv、学术检索和出版商来源。','企业、高校及实验室官网用于核对团队和公开技术资料。','工具用途、输入输出、权限与错误处理共同构成 ACI。']},
  {id:'retrieval',title:'证据与 RAG',summary:'数据库留存证据，检索找出当前问题需要的片段。',
    steps:[['任务原文','网上取证与本人导入资料形成证据账本。'],['结构分块','按结构切分，保留父子关系与精确位置。'],['检索索引','当前默认使用 FTS / BM25，通道按实际配置选择。'],['候选融合','召回片段，保留排名依据并合并近重复。'],['上下文装配','围绕子问题选择方法与实验段落，在原额度内装配。'],['引用回溯','从结论返回片段、原文及对应资料版本。']],
    notes:['单次研究可直接定位原文，不强制先向量化。','跨任务沿用需要明确范围，读取遵守原资料权限。','反馈用于改善选择，来源事实与原文保持可追溯。']},
  {id:'skills',title:'阶段 Skill',summary:'把研究方法和输出要求加载到需要的阶段。',
    steps:[['阶段目标','确定本阶段的问题与产出。'],['自动匹配','匹配领域分析、技术深读与绘图等方法。'],['手动选择','用户可启用、禁用或选择单图绘图 Skill。'],['约束编译','组合可信方法、工具准入和阶段输出契约。'],['阶段执行','使用当前方法和授权工具完成分析。'],['结构化结果','交付结果、来源、覆盖与后续所需信息。']],
    notes:['Skill 负责方法，工具负责操作，Agent 分析当前问题。','绘图可选择内置方式或已配置的受信 Skill 适配器。','网页与论文内容作为资料，执行规则来自可信配置。'],branches:[[0,1],[0,2],[1,3],[2,3],[3,4],[4,5]]},
  {id:'routing',title:'模型与成本',summary:'规则处理、模型选择和阶段额度共同决定一次调用。',
    steps:[['任务要求','读取能力需求、上下文容量与资料等级。'],['规则处理','代码完成配置校验、统计、去重和明确定位。'],['常规模型','从已授权主备路由选择满足条件的模型。'],['按需升级','依据明确触发条件和预配置的升级名额处理。'],['额度准入','请求前预留输入输出，核对原任务期限。'],['用量结算','汇总模型与工具用量，失败及迟到请求保留结算。']],
    notes:['审核和正文调用共用原任务总 Token 额度。','服务故障回退与能力升级分别记录。','实际用量在研究记录中查看，配置价格用于估算。']},
  {id:'aci',title:'工具接口',summary:'工具用途、参数与返回结果也是产品接口。',
    steps:[['用途','明确适用问题、操作性质与选择条件。'],['输入','约定参数类型、范围、字段和来源绑定。'],['运行边界','绑定任务、资料范围、期限、份额与取消状态。'],['工具操作','执行搜索、读取、检索、绘图或归档。'],['结果','返回内容、定位、覆盖和操作状态。'],['错误恢复','区分空结果、临时故障和被拒请求，保存处理依据。']],
    notes:['交接保持原任务、执行和计划身份。','明确的输入输出契约连接各阶段。','界面展示工具名称与摘要，详情进入研究记录。']},
  {id:'execution',title:'边界与恢复',summary:'执行绑定当前任务、资料权限、额度和期限。',
    steps:[['任务身份','绑定当前用户、任务、执行和计划。'],['资料范围','读取前检查来源权限、等级与有效范围。'],['工具准入','按已授权工具和出站边界接纳。'],['预算期限','在原额度与期限内继续、暂停或停止。'],['进度保存','保留阶段、原文、输入绑定和实际用量。'],['取消恢复','本人可取消；符合原条件的检查点可显式继续。']],
    notes:['画布呈现实际步骤和计划调整原因。','迟到返回结算用量，结果保持当前执行归属。','继续研究沿用原任务记录与剩余额度。']},
  {id:'delivery',title:'图文交付',summary:'组织研究发现，用图表、来源和附录支撑阅读。',
    steps:[['研究结论','围绕布局、机制、演进或合作问题组织分析。'],['原文核对','对照实际来源核对数字、条件和判断。'],['报告模板','选择预设或自定义页面，适配对象与学科。'],['绘图 Skill','按数据和论证目标选择图型，支持单图覆盖。'],['图文组装','组合正文、比较图、关系图、来源与附录。'],['导出反馈','下载可用格式、重开历史并对具体内容反馈。']],
    notes:['正文保留发现、分析、图表、引用和简短方法说明。','预算、审核和版本在研究记录查看。','本次产物提供实际可用的导出格式。']},
]
const positions=[{x:60,y:38},{x:410,y:38},{x:760,y:38},{x:760,y:248},{x:410,y:248},{x:60,y:248}]
function Diagram({topic}:{topic:Topic}) {
  const [reduced,setReduced]=useState(()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [playing,setPlaying]=useState(()=>!reduced),[step,setStep]=useState(0),[selected,setSelected]=useState(0)
  const marker=useId().replace(/:/g,'')
  const [compact,setCompact]=useState(()=>window.matchMedia('(max-width: 700px)').matches)
  useEffect(()=>{const media=window.matchMedia('(max-width: 700px)');const change=()=>setCompact(media.matches);media.addEventListener('change',change);return()=>media.removeEventListener('change',change)},[])
  const diagramPositions=compact?positions.map((_,i)=>({x:40,y:30+i*125})):positions
  const diagramWidth=compact?420:1080,diagramHeight=compact?790:400,nodeWidth=compact?340:260,nodeHeight=compact?90:104
  useEffect(()=>setSelected(step),[step])
  useEffect(()=>{const media=window.matchMedia('(prefers-reduced-motion: reduce)');const change=()=>{setReduced(media.matches);if(media.matches)setPlaying(false)};media.addEventListener('change',change);return()=>media.removeEventListener('change',change)},[])
  useEffect(()=>{if(!playing||reduced)return;const timer=window.setInterval(()=>{if(!document.hidden)setStep(value=>(value+1)%topic.steps.length)},1800);return()=>window.clearInterval(timer)},[playing,reduced,topic.steps.length])
  const edges=topic.branches||topic.steps.slice(1).map((_,i):[number,number]=>[i,i+1])
  return <section className="technical-figure" aria-label={`${topic.title}原理演示`}>
    <div className="technical-figure-top"><span>原理演示</span><div className="canvas-toolbar"><button type="button" className="icon-button" disabled={reduced} aria-label={playing?'暂停演示':'播放演示'} onClick={()=>setPlaying(v=>!v)}><Icon name={playing?'pause':'play'}/></button><button type="button" className="icon-button" aria-label="下一步演示" onClick={()=>{setPlaying(false);setStep(v=>(v+1)%topic.steps.length)}}><Icon name="step"/></button><span>{step+1} / {topic.steps.length}</span></div></div>
    <div className="technical-figure-scroll"><div className="technical-diagram" data-compact={compact} data-playing={playing&&!reduced} style={{aspectRatio:`${diagramWidth}/${diagramHeight}`}}>
      <svg viewBox={`0 0 ${diagramWidth} ${diagramHeight}`} className="technical-connections" aria-hidden="true"><defs><marker id={marker} markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0L6 3L0 6" fill="var(--accent)"/></marker></defs>
        {edges.map(([from,to])=>{const a=diagramPositions[from],b=diagramPositions[to],same=a.y===b.y;const x1=a.x+nodeWidth/2,y1=a.y+nodeHeight,x2=b.x+nodeWidth/2,y2=b.y;const path=same?`M${a.x+(b.x>a.x?nodeWidth:0)},${a.y+52} L${b.x+(b.x>a.x?0:nodeWidth)},${b.y+52}`:`M${x1},${y1} C${x1},${(y1+y2)/2} ${x2},${(y1+y2)/2} ${x2},${y2}`;return <g key={`${from}-${to}`}><path className="technical-line" d={path} markerEnd={`url(#${marker})`}/><path className={`technical-packet ${step===to?'is-active':''}`} d={path} pathLength="100"/></g>})}
      </svg>
      {topic.steps.map(([label],index)=><button key={label} className={`technical-node ${step===index?'is-active':''}`} style={{left:`${diagramPositions[index].x/diagramWidth*100}%`,top:`${diagramPositions[index].y/diagramHeight*100}%`,width:`${nodeWidth/diagramWidth*100}%`,height:`${nodeHeight/diagramHeight*100}%`}} type="button" aria-pressed={selected===index} onClick={()=>{setSelected(index);setStep(index);setPlaying(false)}}><span className="technical-node-icon"><Icon name={['search','network','book','layers','target','chart'][index]}/></span><span><span className="technical-node-number">0{index+1}</span><strong>{label}</strong></span><span className="technical-node-dot"/></button>)}
    </div></div>
    <div className="technical-boundary"><span><Icon name="target" size={17}/>任务范围</span><span>阶段 Skill</span><span>原额度与期限</span><span>证据定位</span></div>
    <div className="technical-detail" aria-live="polite"><span>0{selected+1}</span><div><h3>{topic.steps[selected][0]}</h3><p>{topic.steps[selected][1]}</p></div></div>
  </section>
}
export default function TechnicalDocs() {
  const [active,setActive]=useState('planning'),topic=topics.find(t=>t.id===active)||topics[0]
  return <div className="technical-page"><header className="technical-header"><a className="brand" href="?view=home"><Icon name="layers" size={24}/>DeepIntel.</a><span>技术原理</span><AppearanceControls/></header>
    <main className="technical-main"><div className="technical-intro"><span className="eyebrow">研究流程</span><h1>一次搜索，<br/><em>如何成为研究。</em></h1><p>问题、工具、证据与判断，如何在同一条流程里连接。</p></div>
      <nav className="technical-tabs pill-tabs" aria-label="技术主题">{topics.map(t=><button key={t.id} type="button" aria-current={active===t.id?'page':undefined} aria-selected={active===t.id} onClick={()=>setActive(t.id)}>{t.title}</button>)}</nav>
      <section className="technical-topic"><div className="technical-topic-title"><h2>{topic.title}</h2><p>{topic.summary}</p></div><Diagram key={topic.id} topic={topic}/><div className="technical-notes">{topic.notes.map((note,i)=><p key={note}><span>0{i+1}</span>{note}</p>)}</div></section>
    </main><footer className="site-footer"><span>DeepIntel.</span><span>交互参考：<a href="https://www.beautifului.dev/" target="_blank" rel="noopener noreferrer">Beautiful UI</a> · <a href="https://bencho.dev/" target="_blank" rel="noopener noreferrer">Bencho</a></span></footer>
  </div>
}
