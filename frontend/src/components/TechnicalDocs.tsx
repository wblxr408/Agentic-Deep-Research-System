import {useLocale,t} from '../i18n'
import {useState} from 'react'
import {AppearanceControls} from './Appearance'
import {Icon} from './Interface'
import ArchitectureDiagram from './ArchitectureDiagram'
import {architectureScenes} from './researchArchitecture'
import '../technical.css'

export default function TechnicalDocs() {
  useLocale()

  const [active,setActive]=useState('planning'),scene=architectureScenes.find(item=>item.id===active)||architectureScenes[0]
  return <div className="technical-page"><header className="technical-header"><a className="brand" href="?view=home"><Icon name="layers" size={24}/>DeepIntel.</a><span>{t("技术文档")}</span><AppearanceControls/></header>
    <main className="technical-main"><div className="technical-intro"><span className="eyebrow">{t("ADRS / 技术架构")}</span><h1>{t("研究架构与执行细节")}</h1><p>{t("问题、证据、模型与工具，在执行中如何交接。")}</p></div>
      <nav className="technical-tabs pill-tabs" aria-label={t("技术主题")}>{architectureScenes.map(item=><button key={item.id} type="button" aria-current={active===item.id?'page':undefined} onClick={()=>setActive(item.id)}>{item.title}</button>)}</nav>
      <section className="technical-topic"><div className="technical-topic-title"><h2>{scene.title}</h2><p>{scene.summary}</p></div><ArchitectureDiagram key={scene.id} scene={scene}/><div className="technical-notes">{scene.notes.map((note,index)=><p key={note}><span>0{index+1}</span>{note}</p>)}</div></section>
    </main><footer className="site-footer"><span>DeepIntel.</span><span>{t("交互参考：")}<a href="https://www.beautifului.dev/" target="_blank" rel="noopener noreferrer">Beautiful UI</a> · <a href="https://bencho.dev/" target="_blank" rel="noopener noreferrer">Bencho</a></span></footer>
  </div>
}
