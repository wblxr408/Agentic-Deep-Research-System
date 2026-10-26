import {uiDefinition,useLocale} from '../i18n'
import '../agent-avatar.css'
import type {CSSProperties} from 'react'

export type AgentExpression='waiting'|'working'|'recovering'|'paused'|'failed'|'completed'|'resting'|'unknown'
const names:Record<AgentExpression,string>=uiDefinition({waiting:'等待表情',working:'执行表情',recovering:'修复表情',paused:'暂停表情',failed:'受阻表情',completed:'完成表情',resting:'休息表情',unknown:'未知状态表情'})

/** Original SVG character. State is supplied by the execution, never a timer. */
export default function AgentAvatar({name,expression,role}:{name:string;expression:AgentExpression;role:string}) {
  useLocale()

  const delay=({planner:0,analyst:1.1,reflection:2.3,report:.6} as Record<string,number>)[role]||0
  return <svg className={`agent-bot bot-${expression}`} viewBox="0 0 112 112" role="img" aria-label={`${name}：${names[expression]}`} style={{'--bot-delay':`${delay}s`} as CSSProperties}>
    <ellipse className="bot-shadow" cx="56" cy="96" rx="29" ry="5"/>
    <g className="bot-character">
      <path className="bot-ear" d="M20 48h-4a5 5 0 0 0-5 5v9a5 5 0 0 0 5 5h4m72-19h4a5 5 0 0 1 5 5v9a5 5 0 0 1-5 5h-4"/>
      <path className="bot-body" d="M28 24Q56 13 84 24Q96 30 95 53L93 72Q90 86 77 88H35Q22 86 19 72L17 53Q16 30 28 24Z"/>
      <path className="bot-highlight" d="M31 28Q56 20 81 28"/>
      <path className="bot-role-mark" d={role==='reflection'?'M48 80l5 4 10-8':role==='report'?'M47 79h18m-15 4h12':role==='planner'?'M49 80l7-4 7 4-7 4z':'M49 79h14m-7-4v8'}/>
      <g className="bot-gaze">
        {expression==='completed'?<g className="bot-eyes happy"><path d="M33 55q7-12 14 0m18 0q7-12 14 0"/></g>:
        expression==='failed'?<g className="bot-eyes worried"><path d="m34 43 13 6m18 0 13-6"/><rect x="36" y="52" width="9" height="17" rx="4.5"/><rect x="67" y="52" width="9" height="17" rx="4.5"/></g>:
        expression==='paused'||expression==='resting'?<g className="bot-eyes resting"><path d="M34 57h13m18 0h13"/></g>:
        expression==='recovering'?<g className="bot-eyes repairing"><path d="m33 43 14-3m18 0 14 3"/><rect x="36" y="50" width="10" height="19" rx="5"/><rect x="66" y="48" width="10" height="23" rx="5"/></g>:
        expression==='unknown'?<g className="bot-eyes"><rect x="35" y="48" width="11" height="19" rx="5.5"/><circle cx="71" cy="57" r="7"/></g>:
        <g className="bot-eyes open"><rect x="34" y={expression==='working'?43:46} width="13" height={expression==='working'?27:23} rx="6.5"/><rect x="65" y={expression==='working'?43:46} width="13" height={expression==='working'?27:23} rx="6.5"/></g>}
      </g>
      {expression==='working'&&<g className="bot-focus"><path d="M27 37v-6h6m46 0h6v6M27 73v6h6m46 0h6v-6"/></g>}
      {expression==='recovering'&&<g className="bot-repair-badge"><circle cx="91" cy="80" r="12"/><path d="m86 85 8-8m-4-4a5 5 0 0 0 6 6l-1-4-4 1z"/></g>}
      {expression==='completed'&&<g className="bot-done-badge"><circle cx="91" cy="80" r="12"/><path d="m85 80 4 4 8-9"/></g>}
    </g>
  </svg>
}
