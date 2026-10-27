import {t,useLocale,uiMessage,localeCode} from '../i18n'
import { FormEvent, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Account } from './AuthGate'
import { TraceLoader } from './Interface'
import {EmailSettings} from './EmailRecovery'
import CollaborationSpaces from './CollaborationSpaces'
import PersonalConnections from './PersonalConnections'

async function accountRequest(path: string, init?: RequestInit) {
  const response = await fetch(`/api/v1/auth${path}`, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const messages: Record<string, string> = { invalid_credentials: t("当前密码不正确。"), cannot_change_own_access: t("不能修改自己的权限。"), last_administrator_required: t("至少保留一名活动管理员。"), administrator_required: t("需要管理员权限。"), account_not_found: t("账号不存在。") }
    throw new Error(messages[String(body.detail)] || (response.status === 422 ? t("请检查输入格式。") : t("操作未完成，请重试。")))
  }
  return response.status === 204 ? null : response.json()
}
const jsonBody = (method: string, value: unknown) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) })

export default function AccountPanel({ account, onLogout, onAdmin }: { account: Account; onLogout: () => Promise<void>; onAdmin: () => void }) {
  useLocale()

  const [currentPassword, setCurrentPassword] = useState(''), [newPassword, setNewPassword] = useState(''), [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  async function changePassword(event: FormEvent) {
    event.preventDefault(); setError('')
    if (newPassword !== confirmPassword) { setError(t("两次输入的新密码不一致。")); return }
    if (new TextEncoder().encode(newPassword).length > 72) { setError(t("密码请控制在 72 字节以内。")); return }
    setBusy(true)
    try {
      await accountRequest('/password', jsonBody('POST', { current_password: currentPassword, new_password: newPassword }))
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword('')
      await onLogout()
    } catch (cause) { setError(cause instanceof Error ? uiMessage(cause.message) : t("密码未更新。")) }
    finally { setBusy(false) }
  }
  async function logout() { setBusy(true); setError(''); try { await onLogout() } catch { setError(t("退出未完成，请重试。")); setBusy(false) } }
  return <div className="account-panel"><header className="account-heading"><p className="eyebrow">{t("个人工作区")}</p><h1>{account.username}</h1><span className="account-role">{account.role === 'admin' ? t("管理员") : t("普通用户")}</span></header>
    <section className="account-card"><h2>{t("账号")}</h2><div className="account-actions">{account.role === 'admin' && <button type="button" className="btn-secondary" onClick={onAdmin}>{t("管理用户")}</button>}<button type="button" className="btn-secondary" disabled={busy} onClick={() => void logout()}>{t("退出登录")}</button></div></section>
    {account.auth_type !== 'disabled'&&<EmailSettings key={`email:${account.id}`} ownerId={account.id}/>}
    {account.auth_type !== 'disabled'&&<CollaborationSpaces key={`spaces:${account.id}`} ownerId={account.id}/>}
    {account.auth_type !== 'disabled'&&<PersonalConnections key={`connections:${account.id}`} ownerId={account.id}/>}
    {account.auth_type !== 'disabled' && <section className="account-card"><h2>{t("修改密码")}</h2><form onSubmit={changePassword} className="account-form">
      <label>{t("当前密码")}<input type="password" autoComplete="current-password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} required className="input-xm" /></label>
      <label>{t("新密码")}<input type="password" autoComplete="new-password" value={newPassword} onChange={e => setNewPassword(e.target.value)} minLength={12} required className="input-xm" /></label>
      <label>{t("确认新密码")}<input type="password" autoComplete="new-password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} minLength={12} required className="input-xm" /></label>
      <p className="field-hint">{t("至少 12 个字符，最多 72 字节。更新后重新登录。")}</p><button type="submit" className="btn-primary" disabled={busy}>{t("更新密码")}</button>
    </form></section>}{error && <p role="alert">{uiMessage(error)}</p>}
  </div>
}

type ManagedAccount = { id: string; username: string; role: 'user' | 'admin'; is_active: boolean; created_at: string }
function AccountRow({ account, self }: { account: ManagedAccount; self: boolean }) {
  useLocale()

  const client = useQueryClient(), [role, setRole] = useState(account.role), [active, setActive] = useState(account.is_active)
  const update = useMutation({ mutationFn: () => accountRequest(`/admin/users/${account.id}`, jsonBody('PATCH', { role, is_active: active })), onSuccess: () => client.invalidateQueries({ queryKey: ['managed-accounts'] }) })
  const changed = role !== account.role || active !== account.is_active
  return <article className="managed-account"><div><strong>{account.username}{self && <span className="field-hint"> {t(" · 当前账号")}</span>}</strong><p className="field-hint">{new Date(account.created_at).toLocaleDateString(localeCode())}</p></div>
    <label><span className="sr-only">{account.username} {t(" 的角色")}</span><select value={role} disabled={self || update.isPending} onChange={e => setRole(e.target.value as ManagedAccount['role'])}><option value="user">{t("普通用户")}</option><option value="admin">{t("管理员")}</option></select></label>
    <label className="account-active"><input type="checkbox" checked={active} disabled={self || update.isPending} onChange={e => setActive(e.target.checked)} />{t("启用")}</label>
    <button type="button" className="btn-secondary" disabled={self || !changed || update.isPending} onClick={() => update.mutate()}>{update.isPending ? t("保存中…") : t("保存")}</button>
    {update.error && <p className="account-row-error" role="alert">{uiMessage(update.error.message)}</p>}
  </article>
}

export function AdminAccounts({ account }: { account: Account }) {
  useLocale()

  const client = useQueryClient(), [page, setPage] = useState(0), [policyError, setPolicyError] = useState('')
  const users = useQuery<{ items: ManagedAccount[]; total: number }>({ queryKey: ['managed-accounts', page], queryFn: () => accountRequest(`/admin/users?limit=25&offset=${page * 25}`) })
  const policy = useQuery<{ enabled: boolean; deployment_enabled: boolean; effective_enabled: boolean }>({ queryKey: ['registration-policy'], queryFn: () => accountRequest('/admin/registration') })
  const changePolicy = useMutation({ mutationFn: (enabled: boolean) => accountRequest('/admin/registration', jsonBody('PUT', { enabled })), onSuccess: () => { setPolicyError(''); void client.invalidateQueries({ queryKey: ['registration-policy'] }); window.dispatchEvent(new Event('deepintel:auth-policy-changed')) }, onError: error => setPolicyError(uiMessage(error.message)) })
  return <div className="account-panel"><header className="account-heading"><p className="eyebrow">{t("管理员")}</p><h1>{t("用户管理")}</h1></header>
    <section className="account-card registration-policy"><div><h2>{t("开放注册")}</h2><p className="field-hint">{policy.data?.deployment_enabled === false ? t("部署配置已关闭注册。") : t("新账号默认为普通用户。")}</p></div><button type="button" className="btn-secondary" role="switch" aria-checked={policy.data?.effective_enabled || false} aria-label={t("开放注册")} disabled={!policy.data || policy.data.deployment_enabled === false || changePolicy.isPending} onClick={() => changePolicy.mutate(!policy.data?.enabled)}>{policy.data?.effective_enabled ? t("已开放") : t("已关闭")}</button></section>
    {(policy.error || policyError) && <p role="alert">{policyError || uiMessage(policy.error?.message)}</p>}
    <section className="account-card"><div className="account-list-heading"><h2>{t("账号")}</h2><span className="field-hint">{users.data?.total ?? '—'} {t(" 位用户")}</span></div>
      {users.isPending && <p role="status"><TraceLoader />{t("正在读取账号")}</p>}{users.error && <p role="alert">{uiMessage(users.error.message)}</p>}
      {users.data?.items.map(item => <AccountRow key={`${item.id}:${item.role}:${item.is_active}`} account={item} self={item.id === account.id} />)}
      <nav className="account-pagination" aria-label={t("账号分页")}><button type="button" className="btn-secondary" disabled={page === 0} onClick={() => setPage(value => value - 1)}>{t("上一页")}</button><span>{page + 1}</span><button type="button" className="btn-secondary" disabled={!users.data || (page + 1) * 25 >= users.data.total} onClick={() => setPage(value => value + 1)}>{t("下一页")}</button></nav>
    </section>
  </div>
}
