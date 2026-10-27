import {t,uiDefinition} from '../i18n'

export type LayoutKind='text'|'heading'|'list'|'metric'|'chart'|'table'|'image'|'callout'
export interface LayoutBlock {block_id:string;kind:LayoutKind;level:3|4|5|6|null;binding:string;chart_kind:string;span:number;aspect:string;missing:string}
export interface LayoutSection {section_id:string;role:string;level:number;columns:number;blocks:LayoutBlock[]}
export interface ReportLayout {
  schema_version:'adrs-report-layout-v1'
  tokens:{background:string;foreground:string;accent:string;font:'serif'|'sans'|'mono';title_px:number;body_px:number;spacing:number;width:'standard'|'wide'}
  density:'compact'|'standard'|'spacious';running_header:boolean;running_footer:boolean;interactions:string[];sections:LayoutSection[]
}
export interface LayoutSample {source_id:string;file_name:string;parse:{format:string;locations:Record<string,Record<string,number>>;differences:string[]}}
export const layoutRoles=uiDefinition({overview:'概览',findings:'研究发现',evolution:'演进',comparison:'比较',relationships:'合作关系',recommendations:'建议',references:'参考资料',general:'正文'})
export const layoutKinds=uiDefinition({text:'段落',heading:'小标题',list:'列表',metric:'指标',chart:'图表',table:'表格',image:'图像',callout:'重点摘记'})
export const layoutInteractions=uiDefinition({contents:'目录',expand:'展开收起',sort:'表格排序',filter:'筛选',tooltip:'悬停提示',tabs:'标签页'})
export function layoutRole(role:string){return (layoutRoles as Record<string,string>)[role]||t('正文')}
export function nextLayoutId(prefix:string,ids:string[]){let n=1;while(ids.includes(`${prefix}-${n}`))n++;return `${prefix}-${n}`}
export function newLayoutBlock(id:string,span=12):LayoutBlock{return {block_id:id,kind:'text',level:null,binding:'auto',chart_kind:'auto',span,aspect:'auto',missing:'text'}}
export function blankReportLayout():ReportLayout{return {schema_version:'adrs-report-layout-v1',tokens:{background:'#f8fafb',foreground:'#183039',accent:'#36867c',font:'sans',title_px:56,body_px:16,spacing:24,width:'standard'},density:'standard',running_header:false,running_footer:false,interactions:['contents'],sections:[{section_id:'section-1',role:'overview',level:1,columns:1,blocks:[newLayoutBlock('block-1')]},{section_id:'section-2',role:'findings',level:2,columns:2,blocks:[{...newLayoutBlock('block-2',6),kind:'chart'},newLayoutBlock('block-3',6)]}]}}
export function layoutFromChapters(pages:Array<{module:string;chart:string}>):ReportLayout {
  const roles:Record<string,string>={landscape:'overview',evolution:'evolution',relationships:'relationships',deep_dive:'findings',validation:'references',actions:'recommendations'}
  let figureCount=0,blockNumber=0
  const sections=pages.slice(0,24).map((page,index)=>{
    const chart=['line','bar','network','timeline','table','scatter','heatmap'].includes(page.chart)&&figureCount<12
    const blocks=[newLayoutBlock(`block-${++blockNumber}`,chart?6:12)]
    if(chart){figureCount++;blocks.push({...newLayoutBlock(`block-${++blockNumber}`,6),kind:'chart',chart_kind:['scatter','heatmap'].includes(page.chart)?'auto':page.chart})}
    return {section_id:`section-${index+1}`,role:roles[page.module]||'general',level:2,columns:chart?2:1,blocks}
  })
  return {...blankReportLayout(),sections}
}
export function layoutProblem(layout:ReportLayout|null|undefined):string|null {
  if(!layout||layout.schema_version!=='adrs-report-layout-v1'||!Array.isArray(layout.sections)||!layout.sections.length||layout.sections.length>24)return t('请保留 1—24 个版式章节。')
  const blocks=layout.sections.flatMap(section=>section.blocks)
  if(blocks.length>96||layout.sections.some(section=>section.blocks.length>32))return t('组件数量超出范围，请减少组件。')
  if(blocks.filter(block=>['chart','image'].includes(block.kind)).length>12)return t('图表与图像合计最多 12 个。')
  if(new Set(layout.sections.map(s=>s.section_id)).size!==layout.sections.length||new Set(blocks.map(b=>b.block_id)).size!==blocks.length)return t('版式组件重复，请重新导入。')
  return null
}
export function layoutImportError(code:string):string {
  const messages:Record<string,string>={layout_format_not_supported:'请选择 HTML 或 DOCX 文件。',layout_sample_size_limit:'文件需在 2 MB 以内，且不能为空。',layout_requires_utf8:'请将 HTML 保存为 UTF-8 后再导入。',layout_structure_not_found:'未找到可用的报告结构，请换一份样例。',layout_parse_timeout:'解析超时，请精简样例后重试。',layout_sample_limit_50:'样例已达到当前容量上限。',layout_request_id_payload_conflict:'文件已改变，请重新选择后导入。',layout_invalid_docx:'DOCX 文件无法读取，请重新导出。',layout_invalid_file_name:'请使用有效的文件名。',layout_component_limit:'样例组件过多，请精简到 96 个以内。',layout_section_limit:'样例章节过多，请精简到 24 章以内。',layout_document_complexity_limit:'样例结构过于复杂，请精简后导入。',layout_style_limit:'样式内容过多，请精简后导入。',layout_style_complexity_limit:'样式规则过多，请精简后导入。',layout_docx_expansion_limit:'DOCX 内容过大，请精简后导入。',layout_docx_xml_limit:'DOCX 结构无法处理，请重新导出。'}
  return t(messages[code]||'导入未完成，请重试。')
}
