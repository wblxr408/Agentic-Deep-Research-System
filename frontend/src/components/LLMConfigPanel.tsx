import {t,useLocale,localeCode,uiMessage} from '../i18n'
/**
 * LLMConfigPanel - Personal model configuration interface.
 *
 * Design: Clean, minimal settings panel
 * - Provider selection with descriptions
 * - Model dropdown with recommendations
 * - Secure API key input
 * - Save/Reset actions
 */

import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

interface LLMConfig {
  routing?: Record<string,unknown>
  provider: string
  model: string
  api_key_masked: string
  api_base: string | null
  temperature: number
  max_tokens: number
  fallback_provider: string | null
  fallback_model: string | null
  has_fallback_api_key: boolean
  updated_at: string | null
}

interface LLMStatus {
  is_configured: boolean
  provider: string | null
  model: string | null
  has_api_key: boolean
  last_updated: string | null
}

interface Provider {
  id: string
  name: string
  description: string
  models: Array<{
    id: string
    name: string
    description: string
  }>
  api_base_default: string
  recommended: boolean
}

interface ProvidersResponse {
  providers: Provider[]
  default: {
    provider: string
    model: string
  }
}

interface SavedModelProfile {
  provider:string;model:string;api_base:string|null;has_api_key:boolean;updated_at:string
}

async function readErrorMessage(res: Response, fallback: string) {
  const text = await res.text()
  try {
    const data = JSON.parse(text) as { detail?: string|Array<{msg?:string;loc?:Array<string|number>}> }
    if (typeof data.detail==='string') return data.detail
    if (Array.isArray(data.detail)) return data.detail.map(item=>`${item.loc?.join('.') || t("配置")}：${item.msg || t("格式无效")}`).join('；')
    return fallback
  } catch {
    return text || fallback
  }
}

interface LLMConfigPanelProps {
  onClose?: () => void
}

function LLMConfigPanel({ onClose }: LLMConfigPanelProps) {
  useLocale()

  const queryClient = useQueryClient()

  // Form state
  const [provider, setProvider] = useState('qwen')
  const [model, setModel] = useState('qwen-plus')
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(8192)
  const [showApiKey, setShowApiKey] = useState(false)
  const [routingText,setRoutingText]=useState('{}')

  // Fallback state
  const [enableFallback, setEnableFallback] = useState(false)
  const [fallbackProvider, setFallbackProvider] = useState<string | null>(null)
  const [fallbackModel, setFallbackModel] = useState<string | null>(null)
  const [fallbackApiKey, setFallbackApiKey] = useState('')

  // Fetch current config
  const { data: config, isLoading: configLoading, error: configError } = useQuery<LLMConfig>({
    queryKey: ['llm-config'],
    queryFn: async () => {
      const res = await fetch('/api/v1/config/llm')
      if (!res.ok) throw new Error(t("无法读取模型配置"))
      return res.json()
    },
  })

  const { data: status } = useQuery<LLMStatus>({
    queryKey: ['llm-status'],
    queryFn: async () => {
      const res = await fetch('/api/v1/config/llm/status')
      if (!res.ok) throw new Error(t("无法读取模型状态"))
      return res.json()
    },
  })

  const savedProfiles = useQuery<{profiles:SavedModelProfile[]}>({
    queryKey:['llm-profiles'],
    queryFn:async()=>{
      const response=await fetch('/api/v1/config/llm/profiles')
      if(!response.ok)throw new Error(t('无法读取已保存模型'))
      return response.json()
    },
  })

  // Fetch available providers
  const {
    data: providers,
    isLoading: providersLoading,
    error: providersError,
    refetch: refetchProviders,
  } = useQuery<ProvidersResponse>({
    queryKey: ['llm-providers'],
    queryFn: async () => {
      const res = await fetch('/api/v1/config/llm/providers')
      if (!res.ok) throw new Error(t("无法读取模型提供商"))
      return res.json()
    },
  })

  // Update config mutation
  const updateMutation = useMutation({
    mutationFn: async (data: {
      provider: string
      model: string
      api_key: string
      api_base: string | null
      temperature: number
      max_tokens: number
      fallback_provider?: string | null
      fallback_model?: string | null
      fallback_api_key?: string | null
      routing?: Record<string,unknown>
    }) => {
      const res = await fetch('/api/v1/config/llm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (!res.ok) {
        throw new Error(await readErrorMessage(res, t("无法保存模型配置")))
      }
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['llm-config'] })
      queryClient.invalidateQueries({ queryKey: ['llm-status'] })
    },
  })

  const saveProfileMutation=useMutation({
    mutationFn:async(data:Parameters<typeof updateMutation.mutate>[0])=>{
      const response=await fetch(`/api/v1/config/llm/profiles/${encodeURIComponent(data.provider)}`,{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
      if(!response.ok)throw new Error(await readErrorMessage(response,t('无法保存可选配置')))
      return response.json()
    },
    onSuccess:()=>{setApiKey('');void queryClient.invalidateQueries({queryKey:['llm-profiles']})},
  })
  const activateProfileMutation=useMutation({
    mutationFn:async(selected:string)=>{
      const response=await fetch(`/api/v1/config/llm/profiles/${encodeURIComponent(selected)}/activate`,{method:'POST'})
      if(!response.ok)throw new Error(await readErrorMessage(response,t('无法应用模型配置')))
      return response.json()
    },
    onSuccess:()=>{
      setApiKey('');setFallbackApiKey('')
      void queryClient.invalidateQueries({queryKey:['llm-config']})
      void queryClient.invalidateQueries({queryKey:['llm-status']})
    },
  })

  // Reset config mutation
  const resetMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/v1/config/llm', { method: 'DELETE' })
      if (!res.ok) throw new Error(await readErrorMessage(res, t("无法重置模型配置")))
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['llm-config'] })
      queryClient.invalidateQueries({ queryKey: ['llm-status'] })
      setApiKey('')
      setFallbackApiKey('')
    },
  })

  // Initialize form from config
  useEffect(() => {
    if (config) {
      setProvider(config.provider)
      setModel(config.model)
      setApiBase(config.api_base || '')
      setTemperature(config.temperature)
      setMaxTokens(config.max_tokens)
      setRoutingText(JSON.stringify(config.routing || {},null,2))

      if (config.fallback_provider) {
        setEnableFallback(true)
        setFallbackProvider(config.fallback_provider)
        setFallbackModel(config.fallback_model)
      }
    }
  }, [config])

  // Get current provider info
  const currentProvider = providers?.providers.find(p => p.id === provider)
  const fallbackProviderInfo = providers?.providers.find(p => p.id === fallbackProvider)
  const loadError = (providersError || configError) as Error | null

  // Handle save
  const handleSave = useCallback((target:'active'|'profile'='active') => {
    if (!apiKey.trim()) {
      alert(t("请输入 API Key"))
      return
    }
    let routing:Record<string,unknown>
    try {
      if (routingText.length>65536) throw new Error(t("配置过长"))
      const parsed:unknown=JSON.parse(routingText)
      if (!parsed || typeof parsed!=='object' || Array.isArray(parsed)) throw new Error(t("需要JSON对象"))
      routing=parsed as Record<string,unknown>
    } catch {
      alert(t("模型路由配置应为有效JSON对象；可以填写 {} 使用当前主模型。"))
      return
    }

    const payload={
      provider,
      model,
      api_key: apiKey,
      api_base: apiBase.trim() || null,
      temperature,
      max_tokens: maxTokens,
      fallback_provider: enableFallback ? fallbackProvider : null,
      fallback_model: enableFallback ? fallbackModel : null,
      fallback_api_key: enableFallback ? fallbackApiKey : null,
      routing,
    }
    if(target==='profile')saveProfileMutation.mutate(payload)
    else updateMutation.mutate(payload)
  }, [
    provider, model, apiKey, apiBase, temperature, maxTokens,
    enableFallback, fallbackProvider, fallbackModel, fallbackApiKey,
    updateMutation,saveProfileMutation,routingText
  ])

  // Handle reset
  const handleReset = useCallback(() => {
    if (confirm(t("重置你的模型配置？"))) {
      resetMutation.mutate()
    }
  }, [resetMutation])

  // Loading state
  if (configLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="w-6 h-6 border-2 border-xmgray-200 border-t-xm-500 rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-xmgray-900 tracking-tight">
          {t("我的模型")}</h2>
        <p className="mt-2 text-sm text-xmgray-500">
          {t("设置你的研究模型与 API 密钥。")}</p>
        {config?.updated_at && (
          <p className="mt-1 text-xs text-xmgray-400">
            {t("上次更新：")}{new Date(config.updated_at).toLocaleString(localeCode())}
          </p>
        )}
      </div>

      {loadError && (
        <div className="mb-4 p-4 rounded-xl bg-red-50 border border-red-100">
          <p className="text-sm text-red-700">
            {t("读取配置失败：")}{uiMessage(loadError.message)}
          </p>
          <button
            type="button"
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ['llm-config'] })
              void refetchProviders()
            }}
            className="mt-3 btn-secondary text-sm"
          >
            {t("重新加载")}</button>
        </div>
      )}

      {!!savedProfiles.data?.profiles.length&&<section className="card p-6 mb-4" aria-label={t('已保存的模型')}>
        <h3 className="text-sm font-medium mb-3">{t('已保存的模型')}</h3>
        {savedProfiles.data.profiles.map(profile=><div key={profile.provider} className="flex flex-wrap items-center justify-between gap-3 border-b border-xmgray-200 py-3 last:border-0">
          <div><p className="font-medium">{profile.provider==='agnes'?'Agnes':profile.provider} · {profile.model}</p><p className="text-xs text-xmgray-500">{profile.api_base}</p></div>
          <button type="button" className="btn-secondary text-sm" disabled={activateProfileMutation.isPending}
            onClick={()=>activateProfileMutation.mutate(profile.provider)}>{t('应用此配置')}</button>
        </div>)}
      </section>}
      {(savedProfiles.error||activateProfileMutation.error)&&<p role="alert" className="mb-4 text-sm text-red-700">{uiMessage((savedProfiles.error||activateProfileMutation.error)?.message||'')}</p>}

      {/* Provider Selection */}
      <div className="card p-6 mb-4">
        <label className="block text-sm font-medium text-xmgray-700 mb-3">
          {t("选择提供商")}</label>
        {providersLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="w-5 h-5 border-2 border-xmgray-200 border-t-xm-500 rounded-full animate-spin" />
          </div>
        ) : providers?.providers?.length ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {providers.providers.map(p => (
              <button
                key={p.id}
                onClick={() => {
                  setProvider(p.id)
                  setModel(p.models[0]?.id || '')
                  setApiBase(p.api_base_default)
                }}
                className={`p-4 rounded-xl border-2 text-left transition-all ${
                  provider === p.id
                    ? 'border-xm-500 bg-xm-50'
                    : 'border-xmgray-100 hover:border-xmgray-200'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-semibold text-xmgray-900">{t(p.name)}</span>
                  {p.recommended && (
                    <span className="tag-orange text-[10px]">{t("推荐")}</span>
                  )}
                </div>
                <p className="text-xs text-xmgray-500 line-clamp-2">{t(p.description)}</p>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-xmgray-400">{t("暂无可用提供商数据。")}</p>
        )}
      </div>

      {/* Current AI Status */}
      <div className="card p-6 mb-4 border border-xmgray-100 bg-gradient-to-br from-white to-xm-50/40">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-medium text-xmgray-700">{t("当前模型")}</span>
              <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                status?.is_configured ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
              }`}>
                {status?.is_configured ? t("已配置") : t("未配置")}
              </span>
            </div>
            <p className="text-sm text-xmgray-500">
              {status?.provider && status?.model
                ? `${status.provider} / ${status.model}`
                : t("未取得配置")}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-xmgray-400">API Key</p>
            <p className="text-sm font-medium text-xmgray-700">
              {config?.api_key_masked || t("未提供")}
            </p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <div className="rounded-xl bg-white/80 border border-xmgray-100 p-3">
            <p className="text-xs text-xmgray-400">API Base</p>
            <p className="mt-1 text-xmgray-700 break-all">{config?.api_base || t("默认地址")}</p>
          </div>
          <div className="rounded-xl bg-white/80 border border-xmgray-100 p-3">
            <p className="text-xs text-xmgray-400">{t("温度 / Token")}</p>
            <p className="mt-1 text-xmgray-700">
              {config ? `${config.temperature.toFixed(1)} / ${config.max_tokens}` : '-'}
            </p>
          </div>
          <div className="rounded-xl bg-white/80 border border-xmgray-100 p-3">
            <p className="text-xs text-xmgray-400">{t("最近更新时间")}</p>
            <p className="mt-1 text-xmgray-700">
              {status?.last_updated || config?.updated_at
                ? new Date(status?.last_updated || config?.updated_at || '').toLocaleString(localeCode())
                : t("暂无")}
            </p>
          </div>
        </div>
      </div>

      {/* Model Selection */}
      <div className="card p-6 mb-4">
        <label className="block text-sm font-medium text-xmgray-700 mb-3">
          {t("选择模型")}</label>
        <select
          value={model}
          onChange={e => setModel(e.target.value)}
          disabled={!currentProvider}
          className="input-xm w-full"
        >
          {model && !currentProvider?.models.some(item => item.id === model) && (
            <option value={model}>{model}</option>
          )}
          {currentProvider?.models.map(m => (
            <option key={m.id} value={m.id}>
              {m.name} - {t(m.description)}
            </option>
          ))}
        </select>
      </div>

      {/* API Key */}
      <div className="card p-6 mb-4">
        <label className="block text-sm font-medium text-xmgray-700 mb-3">
          API Key {config?.provider===provider&&config?.api_key_masked && <span className="text-xmgray-400">{t("(当前: ")}{config.api_key_masked})</span>}
        </label>
        <div className="relative">
          <input
            type={showApiKey ? 'text' : 'password'}
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder={t("输入 API Key")}
            className="input-xm w-full pr-20"
          />
          <button
            type="button"
            onClick={() => setShowApiKey(!showApiKey)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-xmgray-400 hover:text-xmgray-600"
          >
            {showApiKey ? t("隐藏") : t("显示")}
          </button>
        </div>
        <p className="mt-2 text-xs text-xmgray-400">
          {t("API Key 加密存储于数据库，不会明文显示")}</p>
      </div>

      {/* Advanced Settings */}
      <div className="card p-6 mb-4">
        <details className="group">
          <summary className="flex items-center justify-between cursor-pointer">
            <span className="text-sm font-medium text-xmgray-700">{t("高级设置")}</span>
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              className="text-xmgray-400 transition-transform group-open:rotate-180"
            >
              <path d="M4 6L8 10L12 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </summary>

          <div className="mt-4 space-y-4">
            {/* API Base */}
            <div>
              <label className="block text-sm text-xmgray-600 mb-2">
                API Base URL <span className="text-xmgray-400">{t("(可选，用于代理或私有部署)")}</span>
              </label>
              <input
                type="text"
                value={apiBase}
                onChange={e => setApiBase(e.target.value)}
                placeholder={currentProvider?.api_base_default || ''}
                className="input-xm w-full text-sm"
              />
            </div>

            {/* Temperature */}
            <div>
              <label className="block text-sm text-xmgray-600 mb-2">
                Temperature: {temperature.toFixed(1)}
              </label>
              <input
                type="range"
                min="0"
                max="2"
                step="0.1"
                value={temperature}
                onChange={e => setTemperature(parseFloat(e.target.value))}
                className="w-full accent-xm-500"
              />
              <div className="flex justify-between text-xs text-xmgray-400 mt-1">
                <span>{t("精确")}</span>
                <span>{t("创造性")}</span>
              </div>
            </div>

            {/* Max Tokens */}
            <div>
              <label className="block text-sm text-xmgray-600 mb-2">
                Max Tokens: {maxTokens}
              </label>
              <input
                type="range"
                min="256"
                max="32768"
                step="256"
                value={maxTokens}
                onChange={e => setMaxTokens(parseInt(e.target.value))}
                className="w-full accent-xm-500"
              />
            </div>
          </div>
        </details>
      </div>

      <details className="card mb-6">
        <summary className="cursor-pointer text-sm font-medium">{t("按阶段选择模型与成本策略")}</summary>
        <p className="mt-3 text-xs text-xmgray-500">{t("默认使用当前主模型。高级路由只选择已配置服务内的候选，先检查阶段、能力、质量档位、资料许可与上下文容量，再比较有来源的配置报价；未知价格不会当作免费。")}</p>
        <label className="block mt-3 text-sm">{t("路由配置")}<textarea className="input-xm w-full mt-2 font-mono text-xs" rows={12} value={routingText}
            maxLength={65536} spellCheck={false} onChange={event=>setRoutingText(event.target.value)} />
        </label>
        <p className="mt-2 text-xs text-xmgray-500">{t("私有资料默认不转发备用服务。服务故障回退和研究内容补证分别处理；运行中的任务发现配置变化会停止下一次模型请求。")}</p>
      </details>

      {/* Fallback Settings */}
      <div className="card p-6 mb-4">
        <details className="group">
          <summary className="flex items-center justify-between cursor-pointer">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-xmgray-700">{t("备用模型")}</span>
              <span className="tag text-[10px]">{t("可选")}</span>
            </div>
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              className="text-xmgray-400 transition-transform group-open:rotate-180"
            >
              <path d="M4 6L8 10L12 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </summary>

          <div className="mt-4 space-y-4">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={enableFallback}
                onChange={e => setEnableFallback(e.target.checked)}
                className="w-4 h-4 accent-xm-500"
              />
              <span className="text-sm text-xmgray-600">{t("启用备用模型（当主模型失败时自动切换）")}</span>
            </label>

            {enableFallback && (
              <div className="pl-7 space-y-3 border-l-2 border-xmgray-100 ml-2">
                <div>
                  <label className="block text-sm text-xmgray-600 mb-2">{t("备用提供商")}</label>
                  <select
                    value={fallbackProvider || ''}
                    onChange={e => {
                      setFallbackProvider(e.target.value || null)
                      const p = providers?.providers.find(p => p.id === e.target.value)
                      setFallbackModel(p?.models[0]?.id || null)
                    }}
                    className="input-xm w-full"
                  >
                    <option value="">{t("选择...")}</option>
                    {providers?.providers
                      .filter(p => p.id !== provider)
                      .map(p => (
                        <option key={p.id} value={p.id}>{t(p.name)}</option>
                      ))}
                  </select>
                </div>

                {fallbackProvider && (
                  <>
                    <div>
                      <label className="block text-sm text-xmgray-600 mb-2">{t("备用模型")}</label>
                      <select
                        value={fallbackModel || ''}
                        onChange={e => setFallbackModel(e.target.value || null)}
                        className="input-xm w-full"
                      >
                        {fallbackProviderInfo?.models.map(m => (
                          <option key={m.id} value={m.id}>{m.name}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm text-xmgray-600 mb-2">{t("备用 API Key")}</label>
                      <input
                        type="password"
                        value={fallbackApiKey}
                        onChange={e => setFallbackApiKey(e.target.value)}
                        placeholder={t("输入备用 API Key")}
                        className="input-xm w-full"
                      />
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </details>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between pt-4">
        <button
          onClick={handleReset}
          disabled={resetMutation.isPending}
          className="btn-ghost text-sm"
        >
          {t("重置为默认")}</button>
        <div className="flex items-center gap-3">
          {onClose && (
            <button onClick={onClose} className="btn-secondary">
              {t("取消")}</button>
          )}
          <button type="button" className="btn-secondary" onClick={()=>handleSave('profile')}
            disabled={saveProfileMutation.isPending||updateMutation.isPending||!apiKey.trim()}>
            {saveProfileMutation.isPending?t('保存中'):t('保存为可选配置')}</button>
          <button
            onClick={()=>handleSave()}
            disabled={updateMutation.isPending || !apiKey.trim()}
            className="btn-primary"
          >
            {updateMutation.isPending ? (
              <>
                <div className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                {t("保存中")}</>
            ) : (
              t("保存配置")
            )}
          </button>
        </div>
      </div>

      {/* Success/Error Messages */}
      {saveProfileMutation.isSuccess&&<p role="status" className="mt-4 text-sm text-emerald-700">{t('可选模型配置已保存')}</p>}
      {saveProfileMutation.error&&<p role="alert" className="mt-4 text-sm text-red-700">{uiMessage(saveProfileMutation.error.message)}</p>}
      {updateMutation.isSuccess && (
        <div className="mt-4 p-3 rounded-xl bg-emerald-50 border border-emerald-100">
          <p className="text-sm text-emerald-700">{t("✓ 配置已保存并立即生效")}</p>
        </div>
      )}
      {updateMutation.isError && (
        <div className="mt-4 p-3 rounded-xl bg-red-50 border border-red-100">
          <p className="text-sm text-red-700">
            {t("✗ 保存失败：")}{uiMessage(updateMutation.error?.message) || t("未知错误")}
          </p>
        </div>
      )}
    </div>
  )
}

export default LLMConfigPanel
