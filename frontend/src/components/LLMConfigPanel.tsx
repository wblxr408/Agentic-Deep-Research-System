/**
 * LLMConfigPanel - Xiaomi-style LLM configuration interface.
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

interface LLMConfigPanelProps {
  onClose?: () => void
}

function LLMConfigPanel({ onClose }: LLMConfigPanelProps) {
  const queryClient = useQueryClient()

  // Form state
  const [provider, setProvider] = useState('qwen')
  const [model, setModel] = useState('qwen-plus')
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(8192)
  const [showApiKey, setShowApiKey] = useState(false)

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
      if (!res.ok) throw new Error('Failed to fetch config')
      return res.json()
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
      if (!res.ok) throw new Error('Failed to fetch providers')
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
    }) => {
      const res = await fetch('/api/v1/config/llm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      if (!res.ok) {
        const error = await res.json()
        throw new Error(error.detail || 'Failed to update config')
      }
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['llm-config'] })
    },
  })

  // Reset config mutation
  const resetMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/v1/config/llm', { method: 'DELETE' })
      if (!res.ok) throw new Error('Failed to reset config')
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['llm-config'] })
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
  const handleSave = useCallback(() => {
    if (!apiKey.trim()) {
      alert('请输入 API Key')
      return
    }

    updateMutation.mutate({
      provider,
      model,
      api_key: apiKey,
      api_base: apiBase.trim() || null,
      temperature,
      max_tokens: maxTokens,
      fallback_provider: enableFallback ? fallbackProvider : null,
      fallback_model: enableFallback ? fallbackModel : null,
      fallback_api_key: enableFallback ? fallbackApiKey : null,
    })
  }, [
    provider, model, apiKey, apiBase, temperature, maxTokens,
    enableFallback, fallbackProvider, fallbackModel, fallbackApiKey,
    updateMutation
  ])

  // Handle reset
  const handleReset = useCallback(() => {
    if (confirm('确定要重置为环境变量默认配置吗？')) {
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
          LLM 配置
        </h2>
        <p className="mt-2 text-sm text-xmgray-500">
          配置大语言模型提供商和 API 密钥。配置将保存到数据库并立即生效。
        </p>
        {config?.updated_at && (
          <p className="mt-1 text-xs text-xmgray-400">
            上次更新：{new Date(config.updated_at).toLocaleString('zh-CN')}
          </p>
        )}
      </div>

      {loadError && (
        <div className="mb-4 p-4 rounded-xl bg-red-50 border border-red-100">
          <p className="text-sm text-red-700">
            配置接口当前不可用，前后端连接可能尚未就绪：{loadError.message}
          </p>
          <button
            type="button"
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ['llm-config'] })
              void refetchProviders()
            }}
            className="mt-3 btn-secondary text-sm"
          >
            重新加载
          </button>
        </div>
      )}

      {/* Provider Selection */}
      <div className="card p-6 mb-4">
        <label className="block text-sm font-medium text-xmgray-700 mb-3">
          选择提供商
        </label>
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
                  <span className="text-sm font-semibold text-xmgray-900">{p.name}</span>
                  {p.recommended && (
                    <span className="tag-orange text-[10px]">推荐</span>
                  )}
                </div>
                <p className="text-xs text-xmgray-500 line-clamp-2">{p.description}</p>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-xmgray-400">暂无可用提供商数据。</p>
        )}
      </div>

      {/* Model Selection */}
      <div className="card p-6 mb-4">
        <label className="block text-sm font-medium text-xmgray-700 mb-3">
          选择模型
        </label>
        <select
          value={model}
          onChange={e => setModel(e.target.value)}
          disabled={!currentProvider}
          className="input-xm w-full"
        >
          {currentProvider?.models.map(m => (
            <option key={m.id} value={m.id}>
              {m.name} - {m.description}
            </option>
          ))}
        </select>
      </div>

      {/* API Key */}
      <div className="card p-6 mb-4">
        <label className="block text-sm font-medium text-xmgray-700 mb-3">
          API Key {config?.api_key_masked && <span className="text-xmgray-400">(当前: {config.api_key_masked})</span>}
        </label>
        <div className="relative">
          <input
            type={showApiKey ? 'text' : 'password'}
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder="输入 API Key"
            className="input-xm w-full pr-20"
          />
          <button
            type="button"
            onClick={() => setShowApiKey(!showApiKey)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-xmgray-400 hover:text-xmgray-600"
          >
            {showApiKey ? '隐藏' : '显示'}
          </button>
        </div>
        <p className="mt-2 text-xs text-xmgray-400">
          API Key 加密存储于数据库，不会明文显示
        </p>
      </div>

      {/* Advanced Settings */}
      <div className="card p-6 mb-4">
        <details className="group">
          <summary className="flex items-center justify-between cursor-pointer">
            <span className="text-sm font-medium text-xmgray-700">高级设置</span>
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
                API Base URL <span className="text-xmgray-400">(可选，用于代理或私有部署)</span>
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
                <span>精确</span>
                <span>创造性</span>
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

      {/* Fallback Settings */}
      <div className="card p-6 mb-4">
        <details className="group">
          <summary className="flex items-center justify-between cursor-pointer">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-xmgray-700">备用模型</span>
              <span className="tag text-[10px]">可选</span>
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
              <span className="text-sm text-xmgray-600">启用备用模型（当主模型失败时自动切换）</span>
            </label>

            {enableFallback && (
              <div className="pl-7 space-y-3 border-l-2 border-xmgray-100 ml-2">
                <div>
                  <label className="block text-sm text-xmgray-600 mb-2">备用提供商</label>
                  <select
                    value={fallbackProvider || ''}
                    onChange={e => {
                      setFallbackProvider(e.target.value || null)
                      const p = providers?.providers.find(p => p.id === e.target.value)
                      setFallbackModel(p?.models[0]?.id || null)
                    }}
                    className="input-xm w-full"
                  >
                    <option value="">选择...</option>
                    {providers?.providers
                      .filter(p => p.id !== provider)
                      .map(p => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                  </select>
                </div>

                {fallbackProvider && (
                  <>
                    <div>
                      <label className="block text-sm text-xmgray-600 mb-2">备用模型</label>
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
                      <label className="block text-sm text-xmgray-600 mb-2">备用 API Key</label>
                      <input
                        type="password"
                        value={fallbackApiKey}
                        onChange={e => setFallbackApiKey(e.target.value)}
                        placeholder="输入备用 API Key"
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
          重置为默认
        </button>
        <div className="flex items-center gap-3">
          {onClose && (
            <button onClick={onClose} className="btn-secondary">
              取消
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={updateMutation.isPending || !apiKey.trim()}
            className="btn-primary"
          >
            {updateMutation.isPending ? (
              <>
                <div className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                保存中
              </>
            ) : (
              '保存配置'
            )}
          </button>
        </div>
      </div>

      {/* Success/Error Messages */}
      {updateMutation.isSuccess && (
        <div className="mt-4 p-3 rounded-xl bg-emerald-50 border border-emerald-100">
          <p className="text-sm text-emerald-700">✓ 配置已保存并立即生效</p>
        </div>
      )}
      {updateMutation.isError && (
        <div className="mt-4 p-3 rounded-xl bg-red-50 border border-red-100">
          <p className="text-sm text-red-700">
            ✗ 保存失败：{updateMutation.error?.message || '未知错误'}
          </p>
        </div>
      )}
    </div>
  )
}

export default LLMConfigPanel
