import {Children,cloneElement,isValidElement,useState} from 'react'
import type {ReactElement,ReactNode} from 'react'
import {t} from '../i18n'

type ChildrenProps={children?:ReactNode;hidden?:boolean;'aria-sort'?:'ascending'|'descending';'data-layout-search'?:string}
const element=(value:ReactNode):value is ReactElement<ChildrenProps>=>isValidElement<ChildrenProps>(value)
function plain(value:ReactNode):string {
  if(value===null||value===undefined||typeof value==='boolean')return ''
  if(typeof value==='string'||typeof value==='number')return String(value)
  if(Array.isArray(value))return value.map(plain).join(' ')
  return element(value)?plain(value.props.children):''
}

/** Keep the original Markdown cells and citation elements while ordering rows. */
export default function ReportMarkdownTable({children,interactions}:{children:ReactNode;interactions:string[]}) {
  const [filter,setFilter]=useState(''),[sort,setSort]=useState<{column:number;direction:1|-1}|null>(null)
  const parts=Children.toArray(children)
  const head=parts.find(item=>element(item)&&item.type==='thead') as ReactElement<ChildrenProps>|undefined
  const body=parts.find(item=>element(item)&&item.type==='tbody') as ReactElement<ChildrenProps>|undefined
  if(!head||!body||!interactions.some(item=>item==='sort'||item==='filter'))return <div className="layout-table-wrap"><table>{children}</table></div>
  const heading=cloneElement(head,{},Children.map(head.props.children,row=>{
    if(!element(row)||row.type!=='tr')return row
    let column=0
    return cloneElement(row,{},Children.map(row.props.children,cell=>{
      if(!element(cell)||cell.type!=='th'||!interactions.includes('sort'))return cell
      const index=column++
      const direction=sort?.column===index?sort.direction:null
      return cloneElement(cell,{'aria-sort':direction?(direction===1?'ascending':'descending'):undefined},
        <button type="button" data-report-offline data-layout-sort={index} onClick={()=>setSort(current=>({column:index,direction:current?.column===index&&current.direction===1?-1:1}))}>{cell.props.children} <span aria-hidden="true">{direction?(direction===1?'↑':'↓'):'↕'}</span></button>)
    }))
  }))
  const rows=Children.toArray(body.props.children).filter((row):row is ReactElement<ChildrenProps>=>element(row)&&row.type==='tr')
    .map((row,index)=>({row,index,cells:Children.toArray(row.props.children).filter(element).map(cell=>plain(cell.props.children))}))
  if(sort)rows.sort((a,b)=>String(a.cells[sort.column]||'').localeCompare(String(b.cells[sort.column]||''),undefined,{numeric:true,sensitivity:'base'})*sort.direction||a.index-b.index)
  const search=filter.trim().toLocaleLowerCase()
  return <div className="layout-table" data-layout-table>
    {interactions.includes('filter')&&<label className="layout-filter" data-report-offline><span>{t('筛选表格')}</span><input type="search" data-layout-filter value={filter} onChange={event=>setFilter(event.target.value)}/></label>}
    <div className="layout-table-wrap"><table>{heading}{cloneElement(body,{},rows.map(({row,cells})=>cloneElement(row,{'data-layout-search':cells.join(' '),hidden:!!search&&!cells.some(cell=>cell.toLocaleLowerCase().includes(search))})))}</table></div>
  </div>
}
