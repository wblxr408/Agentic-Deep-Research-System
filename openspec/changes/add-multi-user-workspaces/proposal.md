# Proposal

## Why

当前系统只有首次管理员初始化与登录。用户要求开放注册、普通用户与管理员分权，并在研究任务、资料和配置的全过程保持个人隔离；现有全局模型配置会突破数据库已经存在的 owner 边界。

## What Changes

- 增加普通用户注册、登录/退出入口和当前账号页面。
- 增加管理员账号管理、启停账号和注册开关，现有单管理员原位迁移。
- 保留资源按 owner 授权，补齐模型调用上下文、缓存退出清理与 Skill 标识命名空间。
- 通过本次功能的真实 HTTP/PostgreSQL 端到端路径验证；遵守既有禁止回归及非 E2E 检查约束。

## Capabilities

### New Capabilities

- `user-workspaces`: 注册、账号角色管理、私有工作区和模型配置执行隔离。

### Modified Capabilities

无（当前尚无归档主规格）。

## Impact

涉及 PostgreSQL 增量迁移、认证与配置 API、研究后台入口、现有 owner 查询、前端认证/导航/账号管理，以及 README/TODO。沿用 FastAPI、PostgreSQL、React 与现有会话 Cookie，不引入身份服务或新依赖。原付费研究优化保持暂停。
