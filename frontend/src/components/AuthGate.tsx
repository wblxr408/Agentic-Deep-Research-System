import {t,useLocale,uiMessage} from '../i18n'
import { FormEvent, useState } from 'react'
import { AppearanceControls } from './Appearance'
import {PasswordRecovery} from './EmailRecovery'

export type Account = { id: string; username: string; role: 'user' | 'admin'; auth_type: string }
export type AuthState = { initialized: boolean; authenticated: boolean; registration_enabled?: boolean; user?: Account; auth_enabled?: boolean; email_recovery_available?:boolean }

async function readDetail(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({})) as { detail?: unknown }
  const messages: Record<string, string> = {
    invalid_credentials: t("用户名或密码不正确。"), username_unavailable: t("用户名已被使用。"),
    username_invalid_or_reserved: t("请换一个用户名。"), registration_closed: t("注册暂未开放。"),
    administrator_setup_required: t("请先创建管理员。"), rate_limited: t("操作较频繁，请稍后再试。"),
    administrator_already_initialized: t("管理员已创建，请登录。"),
  }
  if (typeof body.detail === 'string') return messages[body.detail] || t("请求未成功，请重试。")
  return response.status === 422 ? t("请检查用户名和密码格式。") : t("请求未成功，请重试。")
}

export default function AuthGate({ state, onAuthenticated, mode = 'login', onModeChange }: { state: AuthState; onAuthenticated: () => void; mode?: 'login' | 'register'; onModeChange?: (mode: 'login' | 'register') => void }) {
  useLocale()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [recovering,setRecovering] = useState(false)
  const initialize = !state.initialized
  const register = !initialize && mode === 'register'
  const creating = initialize || register

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    if (creating && password !== confirmPassword) {
      setError(t("两次输入的密码不一致。"))
      return
    }
    if (creating && new TextEncoder().encode(password).length > 72) { setError(t("密码请控制在 72 字节以内。")); return }
    setSubmitting(true)
    try {
      const response = await fetch(initialize ? '/api/v1/auth/initialize' : register ? '/api/v1/auth/register' : '/api/v1/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      })
      if (!response.ok) throw new Error(await readDetail(response))
      onAuthenticated()
    } catch (cause) {
      setError(cause instanceof Error ? uiMessage(cause.message) : t("认证失败。"))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-screen">
      <div className="auth-appearance"><AppearanceControls /></div>
      <section className="auth-card" aria-labelledby="auth-title">
        <a href="?view=home" className="auth-home">{t("← 首页")}</a><div className="mb-8 border-l-4 border-xm-500 pl-4">
          <p className="text-xs font-semibold uppercase text-xm-500">DeepIntel</p>
          <h1 id="auth-title" className="mt-1 text-2xl font-semibold text-xmgray-900">{recovering?t('找回密码'):initialize ? t("创建管理员") : register ? t("创建你的工作区") : t("继续你的研究")}</h1>
          <p className="mt-2 text-sm leading-6 text-xmgray-500">{recovering?t('使用已验证的邮箱重置密码。'):initialize ? t("完成首次设置。") : register ? t("让问题、资料与发现有处可循。") : t("登录你的个人工作区。")}</p>
        </div>
        {recovering?<PasswordRecovery available={state.email_recovery_available===true} onBack={()=>setRecovering(false)}/>:register && !state.registration_enabled ? <div className="space-y-4"><p>{t("注册暂未开放。")}</p><button type="button" className="btn-primary" onClick={() => onModeChange?.('login')}>{t("返回登录")}</button></div> : <form className="space-y-4" onSubmit={submit}>
          <label className="block text-sm text-xmgray-700">{t("用户名")}<input className="input-xm mt-1 rounded-md py-3" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={event => setUsername(event.target.value)} required minLength={creating ? 3 : 1} maxLength={120} pattern={creating ? '[A-Za-z0-9_.-]+' : undefined} aria-describedby={creating ? 'username-format' : undefined} />
          </label>
          {creating && <p id="username-format" className="field-hint">{t("3–120 位字母、数字、下划线、点或短横线。")}</p>}
          <label className="block text-sm text-xmgray-700">{t("密码")}<input className="input-xm mt-1 rounded-md py-3" type="password" autoComplete={creating ? 'new-password' : 'current-password'} value={password} onChange={event => setPassword(event.target.value)} required minLength={creating ? 12 : 1} aria-describedby={creating ? 'password-format' : undefined} />
          </label>
          {creating && <p id="password-format" className="field-hint">{t("至少 12 个字符，最多 72 字节。")}</p>}
          {creating && <label className="block text-sm text-xmgray-700">{t("确认密码")}<input className="input-xm mt-1 rounded-md py-3" type="password" autoComplete="new-password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} required minLength={12} />
          </label>}
          {error && <p className="border-l-2 border-red-600 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{uiMessage(error)}</p>}
          <button className="btn-primary w-full rounded-md" type="submit" disabled={submitting}>{submitting ? t("正在提交…") : initialize ? t("创建管理员并继续") : register ? t("注册并进入") : t("登录")}</button>
          {!creating&&<button type="button" className="btn-ghost text-sm" onClick={()=>{setError(null);setRecovering(true)}}>{t('忘记密码？')}</button>}
        </form>}
        {!initialize && !recovering && <div className="auth-switch">{register ? t("已有账号？") : t("还没有账号？")}{(register || state.registration_enabled) ? <button type="button" onClick={() => onModeChange?.(register ? 'login' : 'register')}>{register ? t("登录") : t("创建账号")}</button> : <span>{t("注册暂未开放")}</span>}</div>}
      </section>
    </main>
  )
}
