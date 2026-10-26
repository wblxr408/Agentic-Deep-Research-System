import {uiDefinition,t} from '../i18n'
export type NodeKind='action'|'agent'|'tool'|'store'|'decision'|'control'|'extension'
export interface ArchitectureNode {id:string;title:string;detail:string;x:number;y:number;region?:string;kind:NodeKind;inputs:string[];outputs:string[];source:string[];role?:string;width?:number;height?:number}
export interface ArchitectureRegion {id:string;title:string;subtitle:string;x:number;y:number;width:number;height:number;parent?:string;tone?:'host'|'runtime'|'loop'|'data';hideHeader?:boolean;agentRole?:string}
export interface ArchitectureEdge {from:string;to:string;label?:string;kind?:'data'|'control'|'return';via?:[number,number][];fromSide?:'left'|'right'|'top'|'bottom';toSide?:'left'|'right'|'top'|'bottom'}
export interface ArchitectureScene {id:string;title:string;summary:string;width:number;height:number;regions:ArchitectureRegion[];nodes:ArchitectureNode[];edges:ArchitectureEdge[];tour:string[];notes:string[]}
type NodeSpec=[string,string,string,string?,NodeKind?]
const src={graph:'app/graph/compiler.py',analyst:'app/agents/analyst.py',api:'app/api/research.py',state:'app/graph/state.py',budget:'app/llm_budget.py',routing:'app/model_routing.py',tools:'app/graph/source_policy.py',evidence:'app/evidence_ingestion.py',selection:'app/evidence_selection.py',skills:'app/skills/stages.py'}
const N=(id:string,title:string,detail:string,x:number,y:number,region:string|undefined,inputs:string[],outputs:string[],source:string[],kind:NodeKind='action',role?:string):ArchitectureNode=>({id,title,detail,x,y,region,inputs,outputs,source,kind,role})
const E=(from:string,to:string,label?:string,kind:ArchitectureEdge['kind']='data'):ArchitectureEdge=>({from,to,label,kind})

const planning:ArchitectureScene=uiDefinition({id:'planning',title:'全景架构',summary:'输入与配置 → 执行边界 → 研究编排 → 证据、分析与交付。',width:1540,height:890,
  regions:[
    {id:'host',title:'Host · 执行基础',subtitle:'身份、方法、模型、预算与恢复',x:210,y:48,width:1090,height:806,tone:'host'},
    {id:'policy',title:'本次执行配置',subtitle:'随任务冻结',x:242,y:92,width:1028,height:132,parent:'host'},
    {id:'runtime',title:'Runtime · 研究编排',subtitle:'明确步骤、依赖与条件分支',x:242,y:252,width:1028,height:468,parent:'host',tone:'runtime'},
    {id:'records',title:'持久状态与事件',subtitle:'保存结果，推送过程',x:242,y:742,width:1028,height:90,parent:'host',tone:'data'}],
  nodes:[
    N('question','研究问题','确定对象、时间、学科、目标及交付要求。',18,282,undefined,['用户问题'],['理解结果'],[src.api]),
    N('configuration','研究配置','冻结对象、模块、来源、权重、模板与绘图选择。',18,412,undefined,['用户选择'],['任务配置'],[src.api]),
    N('materials','本人资料','选定内部资料后，在原归属范围内参与研究。',18,542,undefined,['资料范围'],['授权资料引用'],[src.tools],'store'),
    N('identity','身份与范围','绑定当前用户、任务和执行版本，检查资料及出站范围。',267,142,'policy',['任务身份','资料范围'],['准入结果'],[src.api,src.tools],'control'),
    N('skills','阶段 Skill','将选定方法编译为阶段约束和能力提示。',515,142,'policy',['可信 Skill','阶段目标'],['方法约束'],[src.skills]),
    N('route','模型路由','按阶段、能力和已授权配置选择模型及回退路径。',763,142,'policy',['阶段需求','模型配置'],['模型选择'],[src.routing]),
    N('quota','原预算与期限','调用前准入并预留用量，所有阶段共用原任务额度。',1011,142,'policy',['已用量','原期限'],['调用准入'],[src.budget],'control'),
    N('planner','规划 Agent','把研究问题转为取证目标和有依赖的执行计划。',275,310,'runtime',['理解结果','冻结配置'],['DAG 计划'],['app/agents/planner.py',src.graph],'agent','planner'),
    N('tools','取证工具','Runtime 按计划调用搜索、浏览、检索或扩展工具。',523,310,'runtime',['工具节点','授权范围'],['取证结果'],[src.graph],'tool'),
    N('analyst','分析 Agent','按成果批次与研究问题读取证据，生成有来源的分析。',771,310,'runtime',['证据','问题模块'],['分析结果'],[src.analyst],'agent','analyst'),
    N('reflection','核对 Agent','核对来源、数字、条件和缺口，给出具体修改或补证目标。',1019,310,'runtime',['分析','证据'],['核对结果','缺口'],['app/agents/reflection.py'],'agent','reflection'),
    N('scope','范围与模块','固定研究对象、学科、问题模块和选定来源。',275,452,'runtime',['任务配置'],['范围契约'],[src.graph]),
    N('dag','依赖与调度','只并发可独立执行的取证节点，汇总后进入分析。',275,584,'runtime',['DAG','节点状态'],['就绪批次'],[src.graph],'decision'),
    N('binding','工具绑定','将计划节点绑定到实际工具，校验参数与访问边界。',523,452,'runtime',['计划节点','工具契约'],['合法请求'],[src.tools,src.graph],'control'),
    N('source','原文与定位','保存 HTML／PDF 原文、结构片段、来源与可引用位置。',523,584,'runtime',['取得的内容'],['任务证据'],[src.evidence,'app/evidence_chunks.py'],'store'),
    N('extract','成果与署名','分批提取成果、机构署名、方法及实验信息，保存阶段结果。',771,452,'runtime',['全文批次'],['成果记录'],[src.analyst]),
    N('questions','按问题分析','围绕布局、演进、技术机制和合作资源处理证据。',771,584,'runtime',['成果','问题种子'],['逐题分析'],[src.analyst]),
    N('verify','来源与主张','将判断、数字和实验条件对应到具体证据。',1019,452,'runtime',['主张','原文'],['核对结论'],['app/agents/reflection.py']),
    N('gap','定向补证','把明确缺口交回规划与工具；输入未变化时复用有效分析。',1019,584,'runtime',['具体缺口'],['补证任务'],[src.graph],'decision'),
    N('checkpoint','阶段检查点','保存已完成阶段、输入绑定及原始用量。',275,772,'records',['阶段结果'],['可恢复状态'],['app/governance/runtime.py',src.state],'store'),
    N('events','SSE 事件','通过所属执行的事件出口推送动作、结果与恢复过程。',523,772,'records',['执行事件'],['实时工作区'],[src.api],'store'),
    N('recovery','分类恢复','按错误类型退避、修正输入并在原次数和期限内继续。',771,772,'records',['错误类别'],['恢复动作或停止'],[src.graph],'control'),
    N('usage','用量与控制','保留模型／工具收据；暂停、终止和继续都绑定原执行。',1019,772,'records',['调用收据','用户操作'],['实际用量','控制状态'],['app/runtime_accounting.py',src.api],'control'),
    N('report','报告 Agent','把经过处理的分析组织为结论、图表、引用与技术附录。',1330,310,undefined,['分析','核对结果'],['报告草稿'],['app/agents/report.py'],'agent','report'),
    N('figures','模板与绘图','按对象、学科、论证目标和所选绘图 Skill 生成图文。',1330,452,undefined,['报告计划','图表数据'],['图文页面'],['app/report_planning.py','app/figure_renderer.py']),
    N('delivery','交付与记录','报告用于阅读发现，研究记录保存过程、用量与来源交接。',1330,584,undefined,['正文','图表','引用'],['可重开的报告'],['app/db/report_delivery.py'],'store')],
  edges:[E('question','planner','问题'),E('configuration','skills','配置'),E('materials','tools','资料'),E('identity','planner',undefined,'control'),E('skills','analyst',undefined,'control'),E('route','analyst',undefined,'control'),E('quota','reflection',undefined,'control'),E('planner','tools','计划'),E('tools','analyst','证据'),E('analyst','reflection','分析'),E('reflection','report','结论'),E('planner','scope'),E('scope','dag'),E('tools','binding'),E('binding','source'),E('analyst','extract'),E('extract','questions'),E('reflection','verify'),E('verify','gap'),E('report','figures'),E('figures','delivery'),{...E('gap','dag','补证','return'),fromSide:'bottom',toSide:'bottom',via:[[1114,728],[356,728]]},E('questions','checkpoint'),E('source','events'),E('questions','recovery',undefined,'control'),E('verify','usage',undefined,'control')],
  tour:['question','planner','dag','tools','binding','source','analyst','extract','questions','reflection','verify','gap','report','figures','delivery'],
  notes:['主流程采用明确编排；取证工具由 Runtime 按依赖调度。','分析按问题推进，模型调用、结果解析和阶段保存分开处理。','节点可查看输入、输出、相邻交接与实际代码位置。']})

const owners:Record<string,string>={planner:'planning-stage',scope:'planning-stage',dag:'planning-stage',tools:'evidence-stage',binding:'evidence-stage',source:'evidence-stage',analyst:'analysis-stage',extract:'analysis-stage',questions:'analysis-stage',reflection:'reflection-stage',verify:'reflection-stage',gap:'reflection-stage'}
planning.regions.push(...[['planning-stage',t("规划 Agent 工作区"),260],['evidence-stage',t("取证工具工作区"),508],['analysis-stage',t("分析 Agent 工作区"),756],['reflection-stage',t("核对 Agent 工作区"),1004]].map(([id,title,x])=>({id:String(id),title:String(title),subtitle:'',x:Number(x),y:290,width:226,height:406,parent:'runtime',hideHeader:true})))
planning.nodes=planning.nodes.map(node=>node.region==='records'?{...node,y:787,height:36}:owners[node.id]?{...node,region:owners[node.id]}:node)

const agentloop:ArchitectureScene=uiDefinition({id:'agentloop',title:'Agent 执行循环',summary:'展开一次阶段执行：上下文、模型处理、工具调度、结果回写与续轮。',width:1540,height:910,
  regions:[{id:'host',title:'Host · 运行边界',subtitle:'任务身份、资源、工具准入与恢复',x:28,y:40,width:1260,height:836,tone:'host'},
    {id:'runtime',title:'Runtime · 阶段推进',subtitle:'按契约选择当前步骤并保存结果',x:284,y:122,width:748,height:598,parent:'host',tone:'runtime'},
    {id:'loop',title:'Agent Loop · 模型处理',subtitle:'本次问题 → 上下文 → 阶段输出 → 结果回写',x:316,y:184,width:684,height:404,parent:'runtime',tone:'loop',agentRole:'analyst'}],
  nodes:[
    N('task','当前阶段任务','从已冻结计划或分析问题队列取得当前步骤。',58,212,'host',['任务','执行游标'],['当前步骤'],[src.graph]),
    N('context','上下文装配','组合当前问题、阶段 Skill、选定证据片段和已保存结果。',350,258,'loop',['问题','方法','证据'],['模型输入'],[src.analyst,src.selection]),
    N('model','模型处理','通过已授权主备模型处理当前阶段，收集实际用量。',778,258,'loop',['消息','模型预算'],['模型响应','收据'],['app/llm_client.py',src.budget]),
    N('decision','阶段输出','规划阶段产出计划；分析阶段产出当前问题的结构化结果。',778,458,'loop',['模型响应'],['计划或分析对象'],['app/agents/planner.py',src.analyst],'decision'),
    N('result','解析与校验','解析结构、检查字段、来源关联和本阶段完成条件。',350,458,'loop',['结构化输出'],['有效结果或错误'],[src.analyst]),
    N('routing','模型路由','从已授权配置选择满足当前能力和上下文要求的模型。',58,372,'host',['阶段需求'],['模型客户端'],[src.routing]),
    N('evidence','证据与历史','按问题取得相关正文及已完成结果，保留来源定位。',58,542,'host',['任务证据','阶段状态'],['上下文片段'],[src.selection],'store'),
    N('request','工具请求校验','规划／补证提供 DAG 节点，校验工具绑定、参数和资料范围。',1070,258,'host',['计划节点','工具允许范围'],['合法工具请求'],[src.tools,src.graph],'control'),
    N('tool','实际工具执行','搜索、浏览、RAG 和扩展接口返回原始结果与运行状态。',1330,258,undefined,['合法请求'],['原始内容','调用状态'],[src.graph],'tool'),
    N('normalize','结果规范化','将工具返回转换为统一证据，保留空结果、拒绝或失败状态。',1330,458,undefined,['工具结果'],['证据对象','错误分类'],[src.evidence]),
    N('checkpoint','结果回写','提交当前问题结果、尝试次数及输入绑定，保留可恢复位置。',350,630,'runtime',['有效阶段结果'],['持久检查点'],[src.analyst,src.graph],'store'),
    N('next','下一题或结束','依据问题队列、缺口和停止条件决定续轮或交给下一角色。',778,630,'runtime',['已完成结果','剩余问题'],['下一阶段'],[src.graph],'decision'),
    N('stage','阶段交接','将分析、核对或报告结果交给后继阶段。',1070,542,'host',['阶段产出'],['后继输入'],[src.graph]),
    N('events','事件与工作区','开始、动作、结果和修复事件通过 SSE 更新当前执行画布。',1070,740,'host',['公开执行事件'],['实时反馈'],[src.api],'store'),
    N('control','暂停与终止','在执行边界检查本人暂停、取消和执行版本；保存后交还控制。',58,770,'host',['控制状态'],['继续／停止'],[src.api],'control'),
    N('budget','预算与期限','模型请求和工具调度受原任务余额与期限约束。',350,770,'host',['原额度','用量'],['调用准入'],[src.budget],'control'),
    N('repair','分类修复','临时服务故障退避；结构、长度及上下文按类型修正后重试。',778,770,'host',['错误','本类计数'],['修正请求或停止'],[src.graph],'control')],
  edges:[E('task','context','任务'),E('evidence','context','片段'),E('context','model','模型输入'),E('routing','model',undefined,'control'),E('model','decision','响应'),E('decision','result','阶段结果'),E('result','checkpoint','保存'),E('checkpoint','next','进度'),E('next','stage','结束'),{...E('next','context','续题','return'),fromSide:'left',toSide:'left',via:[[302,688],[302,302]]},E('decision','request','规划／补证'),E('request','tool','合法请求'),E('tool','normalize','返回'),{...E('normalize','evidence','证据回流','return'),fromSide:'bottom',toSide:'right',via:[[1425,730],[268,730],[268,572]]},E('stage','events','公开反馈'),E('result','repair','错误','control'),E('repair','context',undefined,'return'),E('budget','checkpoint',undefined,'control'),E('control','budget',undefined,'control')],
  tour:['task','context','model','decision','request','tool','normalize','evidence','context','model','decision','result','checkpoint','next','stage','events'],
  notes:['模型输出先进入结构与来源校验，再用于阶段推进。','工具节点来自规划与补证，由 Runtime 调度并回收结果。','演示沿公开的处理路径推进；真实任务动作在研究工作区查看。']})

// Topic lenses keep their own topology, contracts and concrete return paths.
function lens(id:string,title:string,summary:string,left:NodeSpec[],core:NodeSpec[],right:NodeSpec[],links:Array<[string,string,string?,ArchitectureEdge['kind']?]>,notes:string[]):ArchitectureScene {
  const nodes:ArchitectureNode[]=[]
  const add=(items:NodeSpec[],region:string,x:number,y:number,columns=1)=>items.forEach(([key,label,detail,file,kind],i)=>nodes.push(N(key,label,detail,x+(i%columns)*270,y+Math.floor(i/columns)*150,region,
    links.filter(link=>link[1]===key).map(link=>link[2]||([...left,...core,...right].find(item=>item[0]===link[0])?.[1]||link[0])),
    links.filter(link=>link[0]===key).map(link=>link[2]||([...left,...core,...right].find(item=>item[0]===link[1])?.[1]||link[1])),[file||src.graph],kind)))
  add(left,'input',64,180);add(core,'runtime',380,180,2);add(right,'output',1000,180)
  return {id,title,summary,width:1250,height:Math.max(760,Math.ceil(core.length/2)*150+270,left.length*150+240,right.length*150+240),
    regions:[{id:'input',title:t("输入与资源"),subtitle:t("选定范围与来源"),x:32,y:90,width:250,height:left.length*150+60,tone:'data'},
      {id:'runtime',title:t("处理与调度"),subtitle:t("明确处理步骤与返回分支"),x:340,y:90,width:570,height:Math.ceil(core.length/2)*150+60,tone:'runtime'},
      {id:'output',title:t("结果与后续"),subtitle:t("保留可追溯的产出"),x:968,y:90,width:250,height:right.length*150+60,tone:'host'}],nodes,edges:links.map(([a,b,label,kind])=>E(a,b,label,kind)),tour:[...left,...core,...right].filter(item=>item[4]!=='extension').map(item=>item[0]),notes}
}
const evidence=uiDefinition(lens('evidence','网上取证','发现线索、读取原文、结构解析和证据留存分开处理。',
  [['scope','来源范围','出版商、学术索引、企业／高校／机构官网及所选来源。',src.tools],['query','检索目标','把明确问题、对象别称和时间范围转为查询。','app/agents/planner.py'],['upload','本人导入','按本人资料范围取得所选文件。',src.api,'store']],
  [['search','搜索发现','搜索工具返回可核查链接与摘要。','app/tools/search_tools.py','tool'],['access','访问准入','读取前校验资料归属、域名与出站范围。',src.tools,'control'],['read','网页／PDF 读取','取得原始 HTML、论文 PDF 和官方文档。','app/tools/public_browser.py','tool'],['parse','结构解析','正文、标题、表格、图片与位置分开留存。',src.evidence],['dedupe','去重与归并','归并同一成果与重复观察，保留来源区别。','app/organization_corpus.py'],['locate','片段与定位','按结构保留可引用片段及父子关系。','app/evidence_chunks.py']],
  [['ledger','任务证据账本','把取得的内容、来源与解析信息作为任务证据保存。',src.evidence,'store'],['analysis','交给分析','针对问题选择相关正文及实验条件。',src.selection],['archive','显式归档','在所选范围内将材料转为后续可检索资源。',src.api,'store']],
  [['scope','access','边界','control'],['query','search','查询'],['search','access','链接'],['access','read','准入'],['upload','parse','原文件'],['read','parse','原文'],['parse','dedupe','成果'],['parse','locate','结构'],['dedupe','ledger','记录'],['locate','ledger','定位'],['ledger','analysis','证据'],['ledger','archive','选定材料']],
  ['搜索摘要用于发现线索，全文与文档进入后续处理。','空结果、读取失败和访问拒绝各自保留实际状态。']))
const retrieval=uiDefinition(lens('retrieval','证据与 RAG','留存证据与召回片段是两项职责，按问题选择检索路径。',
  [['question','当前子问题','读取当前分析问题与必要技术术语。',src.analyst],['ledger','任务原文','本次取得的正文可直接按证据和位置选择。',src.evidence,'store'],['library','授权资料库','用户选定范围内的已归档材料。',src.api,'store']],
  [['filter','范围过滤','按任务、资料归属与选定来源过滤候选。','app/retrieval_filters.py','control'],['chunks','结构分块','保留段落、表格与上下级关系。','app/evidence_chunks.py'],['fts','FTS／BM25','默认词法检索通道召回问题相关片段。','app/tools/retrieval_tools.py','tool'],['fusion','候选融合','合并近重复候选，保留排名与来源。','app/retrieval_candidates.py'],['context','上下文选择','选取方法、实验及数字片段并控制模型输入。',src.selection],['graph','向量／图谱扩展','扩展位：按独立配置接入检索适配器，当前默认路径仍为词法通道。','docs/OPTIMIZATION_TODO.md','extension']],
  [['citation','引用定位','结论关联片段，再回到原文和资料记录。','app/evidence_chunks.py','store'],['answer','分析使用','检索结果作为证据输入，由分析阶段回答当前问题。',src.analyst],['feedback','选择反馈','记录所用片段与结果，用于改善后续选择。','app/retrieval_features.py']],
  [['question','filter','问题'],['library','filter','范围'],['ledger','chunks','正文'],['chunks','fts','片段'],['filter','fts','过滤','control'],['fts','fusion','候选'],['fusion','context','排名'],['ledger','context','直接定位'],['context','answer','上下文'],['context','citation','引用'],['answer','feedback','实际使用'],['feedback','fusion','选择反馈','return'],['graph','fusion','扩展通道']],
  ['数据库和原文保存证据；检索用于挑选当前问题需要的片段。','当前任务的正文可以直接使用，不强制先建立向量库。']))
const skills=uiDefinition(lens('skills','阶段 Skill','方法选择、可信编译、工具准入和输出契约逐项交接。',
  [['goal','阶段目标','读取本阶段问题及预期产出。',src.graph],['manual','用户选择','启用、禁用、覆盖阶段方法或单图绘图方案。','app/api/skills.py'],['catalog','可信注册表','保存可用 Skill 定义、版本和方法内容。','app/skills/registry.py','store']],
  [['match','自动匹配','按对象、领域和阶段匹配已配置的 Skill。','app/skills/service.py'],['resolve','选择合并','合并自动选择、手动覆盖和禁用项。',src.skills,'decision'],['compile','方法编译','将可信方法转为阶段提示和结构化约束。',src.skills],['tools','工具允许范围','将方法所需能力与任务的工具授权取交集。',src.graph,'control'],['load','阶段加载','只向当前 Agent 交付所需方法与能力提示。',src.graph],['output','结果契约','产出满足本阶段结构、证据与内容要求的结果。',src.analyst]],
  [['analysis','分析与深读','将选定方法用于技术分类、机制及演进分析。',src.analyst],['figure','绘图 Skill','按单图方案选用内置渲染或已配置适配器。','app/figure_renderer.py','tool'],['record','选择记录','保留本任务的选用版本、覆盖和产出。','app/skills/models.py','store']],
  [['goal','match','目标'],['catalog','match','方法'],['match','resolve','候选'],['manual','resolve','手动覆盖'],['resolve','compile','选定方法'],['compile','load','阶段约束'],['compile','tools','能力需求'],['tools','load','允许能力','control'],['load','output','执行'],['output','analysis','研究结果'],['output','figure','绘图方案'],['output','record','选用信息']],
  ['Skill 规定方法，Agent 处理研究问题，工具执行具体操作。','网页和论文作为资料进入证据范围。']))
const routing=uiDefinition(lens('routing','模型与成本','规则处理、主备模型、能力升级和总额度有不同控制点。',
  [['stage','阶段需求','读取任务类型、资料等级和上下文要求。',src.routing],['config','授权模型','使用用户已配置的模型、价格和主备关系。',src.routing,'store'],['usage','原用量','模型与工具的实际消耗累计到同一任务。','app/runtime_accounting.py','store']],
  [['rules','代码处理','配置校验、统计、去重和明确定位由代码完成。','app/organization_statistics.py'],['choose','路由选择','选择满足阶段能力和上下文要求的授权模型。',src.routing,'decision'],['reserve','额度预留','请求前核对输入输出预估、阶段份额及原期限。',src.budget,'control'],['request','模型请求','通过统一客户端提交请求并接收实际使用量。','app/llm_client.py','tool'],['fallback','服务回退','按原配置处理服务故障的主备切换。','app/llm_client.py','decision'],['upgrade','能力升级','按明确触发条件与已有升级名额调整能力。',src.routing,'decision']],
  [['response','阶段响应','响应回到原阶段，随后解析和校验。',src.analyst],['settle','用量结算','失败和迟到响应仍保留收据及实际用量。','app/runtime_accounting.py','store'],['stop','不足时停止','保留已得资料与结果，并展示具体额度或期限原因。',src.graph,'control']],
  [['stage','rules','确定性部分'],['stage','choose','模型需求'],['config','choose','路由'],['choose','reserve','选择'],['usage','reserve','余额','control'],['reserve','request','准入'],['request','response','响应'],['request','settle','收据'],['request','fallback','服务故障','return'],['fallback','request','主备重试','return'],['response','upgrade','能力条件'],['upgrade','choose','升级选择','return'],['reserve','stop','不足','control']],
  ['正文、核对与修订共用原任务总 Token 预算。','服务回退与能力升级分别记录，不用重建任务来重置余额。']))
const aci=uiDefinition(lens('aci','工具接口','一次调用从用途与参数进入，经过准入、执行、结果校验和证据交接。',
  [['purpose','用途与契约','定义适用问题、读写性质、输入输出和错误。',src.tools],['plan','计划节点','当前工具动作带有 node_id、query／url 和前置依赖。',src.state],['scope','授权范围','绑定本人任务、资料和允许访问的来源。',src.tools,'control']],
  [['binding','工具绑定','把计划工具类型绑定到实际适配器与参数模式。',src.graph],['validate','参数校验','校验必填、类型、长度和输入来源。',src.graph,'control'],['admit','运行准入','检查执行版本、允许工具、出站、预算与取消。',src.tools,'control'],['execute','执行工具','通过对应工具函数执行一次已准入动作。',src.graph,'tool'],['normalize','规范化结果','统一返回内容、状态、覆盖与位置。',src.evidence],['classify','错误分类','区分空结果、临时故障、拒绝和不可恢复问题。',src.graph,'decision']],
  [['evidence','证据交接','有效材料进入证据账本并交给后续阶段。',src.evidence,'store'],['retry','有界恢复','依据具体错误、分类计数和原剩余预算决定重试。',src.graph,'control'],['trace','调用记录','按 call_id、node_id 保留输入、结果、用量及事件。',src.graph,'store']],
  [['purpose','binding','契约'],['plan','binding','节点'],['binding','validate','参数'],['scope','admit','范围','control'],['validate','admit','合法输入'],['admit','execute','准入'],['execute','normalize','返回'],['normalize','evidence','内容'],['execute','classify','异常'],['classify','retry','分类'],['retry','admit','再准入','return'],['execute','trace','记录']],
  ['ACI 同时约定用途、输入输出、权限和错误处理。','工具反馈与真实阶段关联，画布展示简短结果，详情保留原输入。']))
const execution=uiDefinition(lens('execution','边界与恢复','暂停、失败、自动修复与检查点继续是不同的状态转移。',
  [['identity','任务身份','owner、session、execution 共同绑定本次执行。',src.api,'control'],['request','当前请求','模型或工具请求带有阶段与输入绑定。',src.graph],['control','用户控制','本人可请求暂停、继续或终止。',src.api,'control']],
  [['access','资料与工具准入','检查所选资料、出站与工具允许范围。',src.tools,'control'],['budget','原额度与期限','使用已有起始时间和实际余额进行准入。',src.budget,'control'],['run','执行当前步骤','执行已准入的模型处理或工具动作。',src.graph],['save','检查点保存','保存阶段结果、输入绑定、计数和用量。',src.state,'store'],['classify','自动诊断','读取具体阶段错误、额度、期限及核对问题。',src.graph,'decision'],['repair','分类修复','按类型退避、修正输入或对报告主张分轮修订。',src.graph]],
  [['resume','检查点继续','校验原归属、执行版本、资料及剩余额度后继续。',src.api,'control'],['stop','明确停止原因','展示已做处理、当前阻塞及适用操作。',src.api,'control'],['events','实时反馈','通过原 SSE 出口逐次展示执行、修复与停止。',src.api,'store']],
  [['identity','access','身份','control'],['request','access','输入'],['access','budget','允许范围'],['budget','run','准入'],['run','save','结果'],['run','classify','错误'],['classify','repair','可修复'],['repair','budget','重试前准入','return'],['classify','stop','达到边界','control'],['control','save','安全边界暂停','control'],['save','resume','原检查点'],['resume','budget','继续','return'],['save','events','过程'],['stop','events','原因']],
  ['连接、超时、限流、服务端、结构和上下文采用分类次数与处理。','原预算、期限、资料访问与用户暂停优先级持续有效。']))
const delivery=uiDefinition(lens('delivery','图文交付','研究判断、主张核对、报告计划与绘图按各自契约交接。',
  [['analysis','研究发现','包含布局、演进、技术机制与合作资源等所选模块。',src.analyst],['evidence','来源与原文','保留支撑主张的原文位置和资料引用。',src.evidence,'store'],['template','模板与绘图选择','选择预设／自定义模板及整体或单图绘图 Skill。','app/report_planning.py']],
  [['claims','主张核对','核对数字、实验条件、来源和矛盾。','app/agents/reflection.py'],['plan','报告计划','组织章节、重点判断、图表与引用位置。','app/report_planning.py'],['write','正文生成','围绕研究重点写出分析和具体建议。','app/agents/report.py','agent'],['data','图表数据','统计和比较由确定性结果提供，保留分母与口径。','app/organization_statistics.py'],['figures','图形渲染','根据所选图型和绘图适配器产出图表。','app/figure_renderer.py','tool'],['revise','定向修订','根据具体主张问题修改，轮间无进展则停止。','app/report_revision.py','decision']],
  [['report','图文报告','正文、图表、引用、目录与技术附录组合成交付页面。','app/organization_report.py'],['record','研究记录','预算、审核、版本及原始过程单独保留。','app/db/report_delivery.py','store'],['feedback','导出与反馈','重开已保存报告，导出实际支持的格式并反馈具体问题。','app/db/report_delivery.py']],
  [['analysis','claims','判断'],['evidence','claims','原文'],['claims','plan','可用结论'],['template','plan','结构'],['plan','write','章节'],['analysis','data','成果记录'],['data','figures','统计数据'],['template','figures','绘图选择'],['write','revise','主张'],['revise','write','修改','return'],['write','report','正文'],['figures','report','配图'],['report','record','产物'],['report','feedback','交付']],
  ['图表用于说明判断，具体口径和来源可追溯。','读者默认看到研究内容，过程字段进入独立研究记录。']))
const matching=uiDefinition(lens('matching','对象与匹配','先确定对象与范围，再按学科口径、技术问题和合作资源比较。',
  [['objects','研究对象','企业、高校和科研实验室可单选、多选或混合。',src.api],['purpose','研究目的','选择布局演进、合作发现或综合研究。','app/organization_purpose.py'],['criteria','评价与权重','按学科选择适用体系、版本和匹配维度。',src.api]],
  [['identity','实体与隶属','解析机构别称、团队和历史署名，保留时间关系。','app/organization_relationships.py'],['corpus','成果范围','按时间、来源和必要条件筛选并归并成果。','app/organization_corpus.py'],['taxonomy','学科与技术分类','按选定学科建立技术层级，允许核心与关联方向。','app/organization_taxonomy.py'],['statistics','指标与口径','统计时保留分母、覆盖及多标签归属。','app/organization_statistics.py'],['trends','研究演进','把成果沿时间和技术路线组织，分析变化依据。','app/organization_trends.py'],['partners','合作资源','分析团队关系、既有合作和具体课题切入点。','app/organization_actions.py']],
  [['compare','比较与优先级','结合配置权重、技术契合和证据覆盖比较候选。','app/organization_findings.py'],['deep','代表成果深读','对关键方法、实验和条件进行机制分析。','app/organization_deep_dive.py'],['recommend','具体合作建议','将技术需求与团队资源关联成可行动的课题。','app/organization_actions.py']],
  [['objects','identity','实体'],['purpose','taxonomy','问题'],['criteria','statistics','口径'],['identity','corpus','归属'],['corpus','taxonomy','成果'],['taxonomy','statistics','分类'],['corpus','trends','时间'],['identity','partners','团队关系'],['statistics','compare','指标'],['trends','compare','路线'],['partners','recommend','资源'],['corpus','deep','重点全文'],['deep','recommend','技术条件'],['compare','recommend','优先级']],
  ['论文、官方项目与技术资料共同支撑分析。','体系与权重随研究配置选择，技术价值通过原文和代表成果展开。']))
export const architectureScenes=[planning,agentloop,matching,evidence,retrieval,skills,routing,aci,execution,delivery]
