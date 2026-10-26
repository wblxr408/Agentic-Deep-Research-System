import {t,useLocale} from '../i18n'
export interface CorpusDraft {
  enabled: boolean; mode: 'search_and_seeds' | 'seeds_only'; group: 'publishers' | 'official'
  domains: string; seeds: string; terms: string; outputTypes: string; allowOcr?: boolean
}
export const defaultCorpusDraft: CorpusDraft = { enabled: false, mode: 'search_and_seeds', group: 'publishers', domains: '', seeds: '', terms: '', outputTypes: '' }
const lines = (value: string) => value.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
export function corpusRequest(draft?: CorpusDraft) {
  if (!draft?.enabled) return undefined
  const domains = draft.domains.split(/[,，]/).map(item => item.trim()).filter(Boolean)
  if (domains.some(domain => /[/:\s]/.test(domain))) throw new Error(t("请填写有效的网站域名，或直接粘贴网址。"))
  const seeds = lines(draft.seeds)
  for (const value of seeds) {
    let url: URL
    try { url = new URL(value) } catch { throw new Error(t("请填写完整的文档网址，例如 https://example.org/paper.pdf。")) }
    if (url.protocol !== 'https:') throw new Error(t("文档网址请使用 HTTPS。"))
  }
  return { collection_mode: draft.mode, seed_urls: seeds, search_terms: lines(draft.terms),allow_ocr:!!draft.allowOcr,
    output_types: draft.outputTypes.split(/[,，]/).map(item => item.trim()).filter(Boolean),
    ...(domains.length ? { source_scope: { groups: [draft.group],
      ...(draft.group === 'official' ? { official_domains: domains } : { publisher_domains: domains }) } } : {}) }
}
export default function CorpusPanel({ value, onChange }: { value?: CorpusDraft; onChange: (value: CorpusDraft) => void }) {
  useLocale()

  const draft = value || defaultCorpusDraft
  const update = (patch: Partial<CorpusDraft>) => onChange({ ...draft, ...patch })
  return <div className="rounded-xl border border-xmgray-200 p-3">
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-orange-500" checked={draft.enabled} onChange={event => update({ enabled: event.target.checked })} />{t("声明样本与来源范围")}</label>
    {draft.enabled && <div className="mt-3 space-y-3 text-xs text-xmgray-600">
      <label className="block">{t("样本采集方式")}<select aria-label={t("样本采集方式")} className="input-xm mt-1 text-sm" value={draft.mode} onChange={event => update({ mode: event.target.value as CorpusDraft['mode'] })}>
        <option value="search_and_seeds">{t("检索并读取种子")}</option><option value="seeds_only">{t("只读声明种子")}</option>
      </select></label>
      <label className="block">{t("来源用途")}<select className="input-xm mt-1 text-sm" value={draft.group} onChange={event => update({ group: event.target.value as CorpusDraft['group'] })}>
        <option value="publishers">{t("出版商／论文集")}</option><option value="official">{t("机构官网文档")}</option>
      </select></label>
      <label className="block">{t("来源域名（逗号分隔）")}<input className="input-xm mt-1 text-sm" value={draft.domains} onChange={event => update({ domains: event.target.value })} placeholder={t("例如：usenix.org, dl.acm.org")} /></label>
      <p>{t("填写后限制公开材料的读取及重定向；搜索服务仅用于发现，结果还会按范围过滤。当前限定来源采用网页渠道；其他平台渠道需单独研究。留空沿用原有出站边界。")}</p>
      <label className="block">{t("样本种子（每行一个 HTTPS 网址）")}<textarea className="input-xm mt-1 text-sm" rows={3} value={draft.seeds} onChange={event => update({ seeds: event.target.value })} /></label>
      <p>{t("种子留空使用所选对象来源。只读种子时不会扩展搜索或自动跟进全文链接；重复网址合并后仍保存原声明。")}</p>
      <label className="flex items-start gap-2"><input type="checkbox" checked={!!draft.allowOcr} onChange={event=>update({allowOcr:event.target.checked})} />{t("对已获准读取的无文本PDF页启用本机OCR；仍需服务端允许，不增加来源范围。")}</label>
      <label className="block">{t("检索式声明（每行一条）")}<textarea className="input-xm mt-1 text-sm" rows={2} value={draft.terms} onChange={event => update({ terms: event.target.value })} /></label>
      <label className="block">{t("成果类型（可选，逗号分隔）")}<input className="input-xm mt-1 text-sm" value={draft.outputTypes} onChange={event => update({ outputTypes: event.target.value })} placeholder="conference_paper, journal_article, preprint" /></label>
      <p>{t("对象、日期及类型按声明筛选；主题／学科仍需后续核实。采纳样本和未取得全文分别显示，不能将受限样本称为现实全集。")}</p>
    </div>}
  </div>
}
