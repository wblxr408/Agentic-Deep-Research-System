import {uiDefinition,useLocale,t} from '../i18n'
import { createContext, useContext, useEffect, useLayoutEffect, useState } from 'react'
import type { ReactNode } from 'react'
import {setLocale} from '../i18n'

export const palettes = uiDefinition([
  { id: 'paper-moss', name: '纸白 · 苔绿', color: '#526552', image: 'hero-paper-moss-v1.png' },
  { id: 'warm-ochre', name: '暖灰 · 赭石', color: '#a47742', image: 'hero-warm-ochre-v1.png' },
  { id: 'mist-indigo', name: '雾白 · 靛蓝', color: '#536584', image: 'hero-mist-indigo-v1.png' },
  { id: 'ink-teal', name: '墨黑 · 青绿', color: '#397d79', image: 'hero-ink-teal-v1.png' },
] as const)
type Theme = typeof palettes[number]['id']
type Language = 'zh' | 'en'
interface Preference { theme: Theme; language: Language }
const key = 'deepintel.appearance.v1'
function readPreference(): Preference {
  try {
    const value = JSON.parse(localStorage.getItem(key) || '{}')
    return { theme: palettes.some(p => p.id === value?.theme) ? value.theme : 'paper-moss', language: value?.language === 'en' ? 'en' : 'zh' }
  } catch { return { theme: 'paper-moss', language: 'zh' } }
}
const AppearanceContext = createContext({ ...readPreference(), setTheme: (_theme: Theme) => {}, setLanguage: (_language: Language) => {} })

export function AppearanceProvider({ children }: { children: ReactNode }) {
  useLocale()

  const [preference, setPreference] = useState(readPreference)
  useLayoutEffect(()=>setLocale(preference.language),[preference.language])
  useEffect(() => {
    document.documentElement.dataset.theme = preference.theme
    document.documentElement.lang = preference.language === 'zh' ? 'zh-CN' : 'en'
    try { localStorage.setItem(key, JSON.stringify(preference)) } catch { /* Theme remains usable without storage. */ }
  }, [preference])
  useEffect(() => {
    const synchronize = (event: StorageEvent) => { if (event.key === key) setPreference(readPreference()) }
    window.addEventListener('storage', synchronize)
    return () => window.removeEventListener('storage', synchronize)
  }, [])
  return <AppearanceContext.Provider value={{ ...preference,
    setTheme: theme => setPreference(current => ({ ...current, theme })),
    setLanguage: language => setPreference(current => ({ ...current, language })),
  }}>{children}</AppearanceContext.Provider>
}
export const useAppearance = () => useContext(AppearanceContext)

export function AppearanceControls() {
  useLocale()

  const { theme, language, setTheme, setLanguage } = useAppearance()
  return <div className="appearance-controls">
    <details className="palette-menu">
      <summary aria-label={t("切换配色")}><span className="palette-glyph" style={{ background: palettes.find(item => item.id === theme)?.color }} />
        <span className="palette-label">{t("配色")}</span></summary>
      <div className="palette-options" role="group" aria-label={t("界面配色")}>
        {palettes.map(item => <button type="button" key={item.id} aria-label={item.name} aria-pressed={theme === item.id}
          onClick={event => { setTheme(item.id); event.currentTarget.closest('details')?.removeAttribute('open') }}>
          <span className="palette-swatch" style={{ background: item.color }} />{item.name}<span>{theme === item.id ? '✓' : ''}</span>
        </button>)}
      </div>
    </details>
    <button className="language-switch" type="button" onClick={() => setLanguage(language === 'zh' ? 'en' : 'zh')}
      aria-label={language === 'zh' ? t("切换到英文") : 'Switch to Chinese'}>{language === 'zh' ? 'EN' : '中文'}</button>
  </div>
}
