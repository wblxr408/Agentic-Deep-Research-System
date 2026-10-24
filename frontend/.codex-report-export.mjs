// Generate the real accepted reader artifact using the existing report component.
// This is document production, with no assertions or startup/health requests.
import {readFile,writeFile,mkdir} from 'node:fs/promises'
import {resolve} from 'node:path'
import {createServer} from 'vite'
import react from '@vitejs/plugin-react'
import {JSDOM} from 'jsdom'

const input=resolve(process.argv[2])
const destination=resolve(process.argv[3])
const value=JSON.parse(await readFile(input,'utf8'))
if (value.status!=='completed' || !value.report || value.delivery_view?.delivery_complete!==true)
  throw new Error('No accepted complete report to export; retained drafts are not normal delivery.')
const server=await createServer({configFile:false,root:process.cwd(),plugins:[react()],
  server:{middlewareMode:true},appType:'custom'})
try {
  const {renderReport}=await server.ssrLoadModule('/.codex-report-render.tsx')
  const fragment=renderReport(value.delivery_view)
  const dom=new JSDOM('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main></main></body></html>')
  const document=dom.window.document
  document.title=value.delivery_view.title
  document.querySelector('main').innerHTML=fragment
  document.querySelectorAll('[data-app-only],button,script,iframe,object,embed').forEach(node=>node.remove())
  document.querySelectorAll('[data-report-page]').forEach(node=>node.removeAttribute('hidden'))
  document.querySelectorAll('[role="button"]').forEach(node=>{
    node.removeAttribute('role');node.removeAttribute('tabindex');node.removeAttribute('aria-pressed')
  })
  document.querySelectorAll('details').forEach(node=>node.removeAttribute('open'))
  document.querySelectorAll('img').forEach(node=>{
    if(!node.src.startsWith('data:image/')) {
      const link=document.createElement('a');link.href=node.src;link.textContent=node.alt||'查看来源图片';node.replaceWith(link)
    }
  })
  const style=document.createElement('style')
  style.textContent='body{margin:0;background:#efefed;color:#242424;font:16px/1.8 system-ui,sans-serif}main{max-width:1120px;margin:28px auto;background:#fff;padding:24px}a{overflow-wrap:anywhere}p,td{overflow-wrap:anywhere}@media(max-width:600px){main{margin:0;padding:4px}}@media print{body{background:white}main{margin:0;padding:0;max-width:none}details{break-inside:avoid}}'
  document.head.append(style)
  await mkdir(destination,{recursive:true})
  await writeFile(resolve(destination,'report.html'),dom.serialize(),'utf8')
  await writeFile(resolve(destination,'report.md'),value.delivery_view.report_markdown,'utf8')
  await writeFile(resolve(destination,'main.md'),value.delivery_view.main_report_markdown||value.delivery_view.report_markdown,'utf8')
  if(value.delivery_view.appendix_markdown)await writeFile(resolve(destination,'appendix.md'),value.delivery_view.appendix_markdown,'utf8')
  await writeFile(resolve(destination,'research.json'),JSON.stringify(value.export_view,null,2),'utf8')
  console.log(JSON.stringify({session_id:value.session_id,html:resolve(destination,'report.html'),
    pages:value.delivery_view.pages.length,charts:value.delivery_view.charts.length,
    audit:value.report_audit,production_method:'existing_report_component_static_export_not_workspace_login'}))
} finally {await server.close()}
