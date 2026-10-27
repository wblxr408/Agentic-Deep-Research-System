# 多用户工作区

## 邮箱恢复源码进度（2026-10-27）

邮箱验证和找回的持久化内核、发信接口与界面已接入源码：邮箱按账号唯一，待验证时不替换原邮箱；只保存高熵单次挑战的摘要与有效期，验证和密码重置按账号事务串行。绑定时复查当前凭据并要求当前密码；重置成功同时更新密码版本、撤销该用户会话和 API token，并作废其剩余挑战。找回请求对存在和不存在的邮箱返回相同结果，来源／账号／邮箱按动作限流；邮件服务未启用或配置不足返回不可用。账号页可输入邮箱和当前密码并粘贴邮件代码；登录页可请求找回，已有代码时即使邮件服务临时不可用仍可尝试重置。数据库迁移、真实发信、界面和统一端到端均未运行。[实施计划](../openspec/changes/extend-account-workspaces/tasks.md)

部署者可通过 `SECURITY_EMAIL_RECOVERY_ENABLED`、`SECURITY_SMTP_HOST`、`SECURITY_SMTP_PORT`、`SECURITY_SMTP_MODE`（`tls` 或 `starttls`）、`SECURITY_SMTP_FROM`、`SECURITY_SMTP_USERNAME`、`SECURITY_SMTP_PASSWORD` 和 `SECURITY_SMTP_TIMEOUT_SECONDS` 配置自己的 SMTP 服务；凭据只放在部署环境。发送连接校验证书，邮件给出一次性代码，不依赖请求 Host 或把代码放到 URL。服务公开状态只说明配置是否齐全，不能据此确认 SMTP 可连接或邮件已送达。

`GET /api/v1/auth/email` 读取本人已验证邮箱与服务配置状态；`POST /api/v1/auth/email/verification` 接收邮箱和当前密码后发送验证码，`POST /api/v1/auth/email/verify` 消费验证码。公开 `POST /api/v1/auth/password/forgot` 对存在与不存在的邮箱均返回 `check_email_if_account_exists`；`POST /api/v1/auth/password/reset` 消费代码和新密码。验证码失败、无配置、发信失败及限流分别返回错误；密码重置成功后须重新登录。该接口尚未经过真实请求，不代表邮箱恢复已可交付。

## 组织空间源码进度（2026-10-27）

本人可创建空间，通过应用内账号邀请其他人；只有受邀人接受后成为成员。空间所有者可撤回邀请、移除成员和归档空间，普通成员可退出；邀请七天有效。创建和邀请使用本人请求 UUID 保持重放身份，改变请求内容不能复用同一 UUID。默认管理员不是所有空间的成员，成员变更不删除或转移个人资料。空间最多 50 个／拥有者，每个空间最多 100 个活动成员与有效邀请；认证关闭的单用户模式不提供空间。成员和资源共享服务端源码已接入，界面尚未完成，也未迁移或运行验证。

成员可选择本人报告的保存版本或本人资料的当前版本分享给空间，只读查看正文；分享前会再次核对资源归属，读取时重新核对双方成员资格、拥有者状态、分享状态、来源版本及资料生命周期。资料更新、停用、过期或切换版本后，旧分享不会自动扩展到新版本；仅限任务复用的资料不能直接分享到空间。退出或被移除时撤销该成员的分享，重新加入也不会自动恢复。报告中的私人引用记录与来源接口不随报告共享；分享者可单独选择其拥有的资料分享。响应按现有披露规则处理凭据，调用方不能通过分享使用拥有者的模型配置或执行权限。

`GET /api/v1/workspaces/{id}/shareable` 列出本人可分享版本；`GET`／`POST /api/v1/workspaces/{id}/shares` 查看或创建分享，`GET`／`DELETE /api/v1/workspaces/{id}/shares/{share_id}` 读取或由分享者撤回。创建要求请求 UUID，已有活动版本不会通过不同请求重复授权。接口只提供共享文本，历史图表资源尚未接入，界面不应承诺图文原样展示。

`GET/POST /api/v1/workspaces` 列出／创建本人空间；`GET /api/v1/workspaces/invitations` 读取本人待处理邀请，`POST /api/v1/workspaces/invitations/{id}/accept` 或 `/decline` 处理。空间所有者通过 `POST /api/v1/workspaces/{id}/invitations` 指定用户名和 request_id 邀请，`DELETE /api/v1/workspaces/{id}/invitations/{invite_id}` 撤回；成员通过 `DELETE /api/v1/workspaces/{id}/members/{member_id}` 退出或由所有者移除，`DELETE /api/v1/workspaces/{id}` 归档空间。本人活动会话／角色在事务内复查，失效或不属于该空间不返回资源；邀请通过界面显示，不自动给他人发信。共享资料、报告和细节见同一 OpenSpec 后续任务。

首次部署创建管理员；之后首页“注册”创建普通用户。已登录账号右上角显示用户名，点击进入账号页。登录后可使用自己的研究、资料、Skill、模板、权重预设和模型设置。用户名不区分大小写，密码至少 12 个字符且不超过 72 个 UTF-8 字节。

## 权限

| 操作 | 普通用户 | 管理员 |
| --- | --- | --- |
| 本人研究、进度流、报告、引用、原文和图表 | 可读写 | 可读写 |
| 本人资料、分块、备份、模板、权重、Skill、渠道配置 | 可读写 | 可读写 |
| 本人的模型和路由配置 | 可读写 | 可读写 |
| 他人的私有研究、资料、配置或密钥 | 不可访问 | 不可访问 |
| 用户列表、其他账号的角色／启停、注册开关 | 不可访问 | 可管理 |
| 使用服务器环境模型后备配置、宿主登录态 CLI | 不可使用 | 可使用 |

管理入口位于“账号 → 管理用户”。修改角色或禁用账号会撤销该账号现有会话及 API token；数据保留。不能修改自己的权限，并保留至少一名活动管理员。管理员不能通过普通研究／资料接口绕过 owner 归属。

普通用户使用自己的模型密钥。公开 HTTP 搜索／阅读可以使用，调用宿主浏览器或 CLI 登录态的采集后端返回 `administrator_required`；每用户外部平台授权空间留作后续扩展。普通资料解析不受此宿主授权限制。

## 注册与部署

`SECURITY_REGISTRATION_ENABLED=true` 开放部署层注册，管理员还可在页面关闭／重新开放。任一层关闭时注册不可用；环境层关闭时页面不能越过它重新开放。`SECURITY_REGISTRATION_RATE_LIMIT` 默认每来源地址每分钟 6 次，包含首次初始化。生产仍遵守原加密密钥、HTTPS Cookie 和 CORS 配置。

注册请求只接收用户名和密码，不能指定 `role` 或 `owner_id`。首次管理员初始化与注册共享事务锁，初始化前注册返回 409。注册后的普通用户不接收其他人的资料、模板、Skill 或配置副本。

账号采用 PostgreSQL 会话与版本撤销，Cookie 保持 HttpOnly、SameSite=Strict。权限从服务端身份取得，前端按钮不承担最终授权。外观偏好是浏览器级偏好，不保存研究内容或凭证。账号切换／退出清空私有缓存和组件；跨标签发送不含凭据的认证变化通知，回到标签时重新确认身份。

## 接口

| 接口 | 权限与结果 |
| --- | --- |
| `GET /api/v1/auth/status` | 公开；初始化及有效注册开关 |
| `POST /api/v1/auth/initialize` | 仅首次；创建管理员并建立会话 |
| `POST /api/v1/auth/register` | 注册开放；创建 user 并建立会话，201；重复 409；关闭 403；非法字段 422；节流 429 |
| `POST /api/v1/auth/login` | 已启用账号；统一认证失败 401 |
| `GET /api/v1/auth/me` | 本人身份、用户名、角色 |
| `POST /api/v1/auth/logout` | 撤销当前 Cookie 会话 |
| `POST /api/v1/auth/password` | 本人当前密码；更新后撤销全部旧凭证 |
| `GET /api/v1/auth/admin/users?limit=25&offset=0` | admin；分页账号，不包含密码和模型配置 |
| `PATCH /api/v1/auth/admin/users/{id}` | admin；其他账号的 `role`／`is_active`；保护冲突 409 |
| `GET/PUT /api/v1/auth/admin/registration` | admin；数据库开关及环境层有效状态 |

个人模型接口沿用 `/api/v1/config/llm`，资料／研究等 API 沿用原路径。本人不存在和他人标识统一按各资源接口返回 404；分块列表按 owner 过滤返回空集合。研究启动前验证本人的模型配置，未配置返回 `personal_model_configuration_required`（409）。

## 数据与迁移

`app/db/accounts.py` 提供两个架构入口共用的增量 SQL。旧角色字段缺失时最早账号成为管理员，其余旧账号为普通用户；只迁移 NULL 角色，重启不会再次提权。原有资源 owner 保持原值，无 owner 历史数据仅归原管理员。`skill_meta` 改为 `(owner_id,slug)` 唯一，同名 Skill 可在不同账号独立存在。

模型配置不再放入单一进程全局变量。请求身份、配置和后台执行通过 `ContextVar` 绑定，后台重新确认 owner 的活动状态并加载其配置，执行结束恢复原上下文。个人配置变更／删除不会修改已在另一线程绑定的他人配置。读取或解密失败返回错误。

升级先保留数据库与配置，应用增量架构，再部署 API 与前端；原 Cookie 仍可用。多用户数据写入后，不能直接回退到原全局模型配置版本。原研究根的暂停状态、额度和期限不因本次升级重新开始。

## 实际范围与后续

[既有端到端操作记录](acceptance/multi-user-workspaces-20261025.md)覆盖注册、角色、资源及配置隔离；通过不等于所有历史研究流程重新验收。邮箱、组织空间及本人平台授权的新增实现进度见上方与 TODO，仍需统一验证。

用户追加的[浏览器双账号和弱网试用](acceptance/accounts-browser-network-20261025.md)已完成九个场景。认证超时后隐藏私有页面，可点击重新连接；退出请求断网时仍显示操作未完成，恢复连接后重新点击退出。切换账号后，旧身份及资料请求迟到返回不会覆盖当前账号；同一身份正常导航继续保留未提交草稿。

授权设计采用 [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) 的最小权限、每请求授权与资源归属核验；注册节流和认证错误参考 [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)。本轮没有改变 Agent/A2A 架构。
