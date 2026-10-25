# 多用户工作区

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

本轮[端到端操作记录](acceptance/multi-user-workspaces-20261025.md)覆盖注册、角色、资源及配置隔离；通过不等于所有历史研究流程重新验收。邮件找回／验证、组织共享及每用户外部平台登录态尚未提供；本轮没有为这些功能添加假入口。

授权设计采用 [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) 的最小权限、每请求授权与资源归属核验；注册节流和认证错误参考 [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)。本轮没有改变 Agent/A2A 架构。
