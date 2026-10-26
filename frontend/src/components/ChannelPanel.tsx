import {t,useLocale,localeCode,uiMessage} from '../i18n'
import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

interface Config {
  enabled: boolean
  backends: string[]
  timeout_seconds: number
  max_attempts: number
  feeds: string[]
  transcription_provider: 'groq' | 'openai' | null
}
interface Channel {
  name: string
  label: string
  operations: string[]
  backends: string[]
  optional_backends: string[]
  config: Config
  setup: string
  last_attempt: { backend: string; status: string; error_category: string | null; timestamp: string } | null
}
interface ContentResult {
  status: string
  items: { url: string; title: string; content: string; channel: string; backend: string }[]
  attempts: { backend: string; status: string; error_category: string | null }[]
}
async function responseJson(response: Response) {
  const body = await response.json()
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : t("请求失败 ({0})", response.status))
  return body
}

export default function ChannelPanel({ selected, onChange }: { selected: string[]; onChange: (value: string[]) => void }) {
  useLocale()

  const client = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const selectedRef = useRef(selected)
  selectedRef.current = selected
  const channels = useQuery<{ items: Channel[] }>({
    queryKey: ['channels'],
    queryFn: ({ signal }) => fetch('/api/v1/channels', { signal }).then(responseJson),
  })
  const preferred=new Set(['web','exa','github','rss'])
  const renderChannel=(channel:Channel)=><div key={channel.name} className="channel-card">
    <div className="channel-card-title"><label><input type="checkbox" checked={selected.includes(channel.name)}
      disabled={!channel.config.enabled||!channel.operations.includes('search')||(!selected.includes(channel.name)&&selected.length>=8)}
      onChange={event=>onChange(event.target.checked?[...selected,channel.name]:selected.filter(name=>name!==channel.name))}/>{t(channel.label)}</label>
      <button type="button" className="btn-ghost" aria-label={t("配置 {0}", t(channel.label))} onClick={()=>setEditing(editing===channel.name?null:channel.name)}>{t("配置")}</button>
    </div>
    <span className="channel-kind">{!channel.config.enabled?t("已停用"):channel.operations.includes('search')?t("搜索与链接"):t("链接读取")}</span>
    {channel.last_attempt&&<details className="channel-attempt"><summary>{t("上次记录")}</summary><p>{channel.last_attempt.backend} · {({budget_exceeded:t("额度用完"),timeout:t("超时"),unavailable:t("不可用")} as Record<string,string>)[channel.last_attempt.error_category||'']||channel.last_attempt.error_category||channel.last_attempt.status} · {new Date(channel.last_attempt.timestamp).toLocaleString(localeCode())}</p></details>}
  </div>
  return <section className="configuration-section" aria-label={t("联网渠道")}>
    <div className="channel-panel-heading"><h3>{t("搜索渠道")}</h3><span>{selected.length?t("已选 {0} / 8", selected.length):t("自动")}</span></div>
    {channels.isPending&&<p role="status">{t("读取渠道配置…")}</p>}
    {channels.error&&<p role="alert" className="composer-error">{uiMessage(channels.error.message)}<button type="button" className="btn-ghost" onClick={()=>void channels.refetch()}>{t("重试")}</button></p>}
    <div className="channel-grid">{channels.data?.items.filter(channel=>preferred.has(channel.name)).map(renderChannel)}</div>
    <details className="more-channels"><summary>{t("更多平台")}</summary><div className="channel-grid">{channels.data?.items.filter(channel=>!preferred.has(channel.name)).map(renderChannel)}</div></details>
    {channels.data?.items.filter(channel=>channel.name===editing).map(channel=><ChannelEditor key={channel.name} channel={channel} onSaved={config=>{if(!config.enabled)onChange(selectedRef.current.filter(name=>name!==channel.name));client.invalidateQueries({queryKey:['channels']})}} onCollected={()=>client.invalidateQueries({queryKey:['channels']})}/>)}
  </section>
}

function ChannelEditor({ channel, onSaved, onCollected }: { channel: Channel; onSaved: (config: Config) => void; onCollected: () => void }) {
  useLocale()

  const [config, setConfig] = useState(channel.config)
  const [primary, setPrimary] = useState(channel.config.backends[0] || channel.backends[0])
  const [fallback, setFallback] = useState(channel.config.backends.length === 0 || channel.config.backends.length > 1)
  const [feeds, setFeeds] = useState(channel.config.feeds.join('\n'))
  const [query, setQuery] = useState('')
  const [operation, setOperation] = useState(channel.operations[0])
  const save = useMutation({
    mutationFn: (value: Config) => fetch(`/api/v1/channels/${channel.name}/config`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) }).then(responseJson),
    onSuccess: (value: Config) => { setConfig(value); onSaved(value) },
  })
  const collect = useMutation<ContentResult, Error>({
    mutationFn: () => fetch('/api/v1/channels/collect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channel: channel.name, operation, query: query.trim(), limit: 5 }) }).then(responseJson),
    onSuccess: onCollected,
  })
  const busy = save.isPending || collect.isPending
  const inputStyle = 'mt-1 w-full rounded-lg border border-xmgray-200 bg-white px-3 py-2 text-sm focus:border-xm-400 focus:outline-none'
  return <div className="mt-3 rounded-xl border border-xm-100 bg-white p-4">
    <h3 className="text-sm font-medium text-xmgray-800">{t(channel.label)} {t(" 渠道维护")}</h3>
    <p className="mt-2 text-xs leading-5 text-xmgray-500">{t(channel.setup)}</p>
    <fieldset disabled={busy} className="mt-3 grid gap-3 sm:grid-cols-2">
      <label className="text-xs text-xmgray-600">{t("首选后端")}<select className={inputStyle} value={primary} onChange={e => { setPrimary(e.target.value); save.reset() }}>
          {[...channel.backends, ...channel.optional_backends].map(backend => <option key={backend} value={backend}>{backend}</option>)}
        </select>
      </label>
      <label className="text-xs text-xmgray-600">{t("总超时（秒）")}<input type="number" min={1} max={90} className={inputStyle} value={config.timeout_seconds} onChange={e => { setConfig({ ...config, timeout_seconds: Number(e.target.value) }); save.reset() }} /></label>
      <label className="text-xs text-xmgray-600">{t("最多后端尝试")}<input type="number" min={1} max={5} className={inputStyle} value={config.max_attempts} onChange={e => { setConfig({ ...config, max_attempts: Number(e.target.value) }); save.reset() }} /></label>
      <div className="flex flex-col justify-center gap-2 text-xs text-xmgray-600">
        <label><input type="checkbox" className="mr-2 accent-orange-500" checked={config.enabled} onChange={e => { setConfig({ ...config, enabled: e.target.checked }); save.reset() }} />{t("启用渠道")}</label>
        <label><input type="checkbox" className="mr-2 accent-orange-500" checked={fallback} onChange={e => { setFallback(e.target.checked); save.reset() }} />{t("失败后按默认顺序使用备选")}</label>
      </div>
      {channel.name === 'rss' && <label className="text-xs text-xmgray-600 sm:col-span-2">{t("RSS / Atom 源（每行一个 HTTPS 链接，最多 10 个）")}<textarea className={inputStyle} rows={3} value={feeds} onChange={e => { setFeeds(e.target.value); save.reset() }} /></label>}
      {primary === 'transcribe' && <label className="text-xs text-xmgray-600 sm:col-span-2">{t("转录服务商（需已在 Agent-Reach 配置专用密钥）")}<select className={inputStyle} value={config.transcription_provider || ''} onChange={e => { setConfig({ ...config, transcription_provider: e.target.value as Config['transcription_provider'] }); save.reset() }}><option value="">{t("请选择")}</option><option value="groq">Groq</option><option value="openai">OpenAI</option></select>
      </label>}
      <button type="button" className="btn-primary justify-center text-sm" onClick={() => save.mutate({ ...config, backends: [primary, ...(fallback ? channel.backends.filter(backend => backend !== primary) : [])], feeds: feeds.split('\n').map(value => value.trim()).filter(Boolean) })}>{t("保存渠道配置")}</button>
    </fieldset>
    {save.isSuccess && <p role="status" className="mt-2 text-xs text-green-700">{t("已保存")}</p>}
    {save.error && <p role="alert" className="mt-2 text-xs text-red-600">{uiMessage(save.error.message)}</p>}
    <div className="mt-4 border-t border-xmgray-100 pt-3">
      <div className="grid gap-2 sm:grid-cols-[auto_1fr_auto]">
        <label className="text-xs text-xmgray-600">{t("采集方式")}<select className={inputStyle} value={operation} disabled={busy} onChange={e => { setOperation(e.target.value); collect.reset() }}>{channel.operations.map(op => <option key={op} value={op}>{op === 'read' ? t("读取链接") : t("搜索")}</option>)}</select></label>
        <label className="text-xs text-xmgray-600">{t("采集关键词或链接")}<input className={inputStyle} value={query} disabled={busy} onChange={e => { setQuery(e.target.value); collect.reset() }} /></label>
        <button type="button" className="btn-secondary self-end text-sm" disabled={busy || !query.trim()} onClick={() => collect.mutate()}>{t("采集内容")}</button>
      </div>
      {busy && <p role="status" className="mt-2 text-xs">{t("处理中…")}</p>}
      {collect.error && <p role="alert" className="mt-2 text-xs text-red-600">{uiMessage(collect.error.message)}</p>}
      {collect.data && <div className="mt-3 space-y-3 text-xs">
        {collect.data.attempts.map((attempt, index) => <p key={index} className="text-xmgray-500">{attempt.backend}: {attempt.error_category || t("采集成功")}</p>)}
        {!collect.data.items.length && <p className="text-amber-700">{t("未取得内容，请根据采集记录调整配置或登录态。")}</p>}
        {collect.data.items.map(item => <article key={item.url} className="rounded-lg bg-xmgray-50 p-3"><a className="text-xm-600 underline" href={item.url} target="_blank" rel="noreferrer">{item.title}</a><p className="mt-1 text-xmgray-400">{item.channel} / {item.backend}</p><p className="mt-2 whitespace-pre-wrap break-words text-xmgray-700">{item.content}</p></article>)}
      </div>}
    </div>
  </div>
}
