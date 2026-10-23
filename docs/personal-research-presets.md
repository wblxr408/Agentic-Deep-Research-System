# 个人权重预设 ACI

用于保存和复用当前用户的研究偏好。预设只定义匹配权重，不改变对象范围、证据真实性、工具权限、预算或商业数据授权；操作复用现有认证和 PostgreSQL。5.2 的[工作台编辑器](organization-weight-editor.md)现已支持选择、编辑、恢复及保存不可变新版本，参见[真实界面与研究记录](acceptance/organization-weights-ui-20261020.md)。

## 操作与输入输出

| 操作 | 输入及结果 |
| --- | --- |
| `POST /api/v1/research/presets` | `name` 和 `configuration`（现有权重配置）；创建服务端随机 `preset_id`，返回 v1、原始配置、生效配置／映射及创建时间，HTTP 201。 |
| `GET /api/v1/research/presets` | 只返回当前 owner 每个预设的最新版本，`items` 可为空。 |
| `GET /api/v1/research/presets/{preset_id}` | 默认最新版本；`?version=1` 读取指定历史版本。不存在或不属于当前用户均返回 404。 |
| `GET /api/v1/research/presets/{preset_id}/versions` | 只返回当前 owner 的全部不可变版本；未知资源返回 404。 |
| `PUT /api/v1/research/presets/{preset_id}` | `expected_version`、新 `name`、`configuration`；以当前版本为前提追加新版本，旧记录不覆盖。版本冲突为 409。 |

`name` 为去空白后的非空名称，最长 300 字符；版本为正整数。完整配置校验复用[权重 ACI](research-evaluation-and-weights.md)。未知字段、同时指定两个权重来源、非法权重或版本返回 422。未认证返回 401，不提供跨用户共享或删除接口。

研究请求选择个人预设时，发送：

```json
{
  "organization_research": {
    "scope": {"...": "填写完整的原有范围字段"},
    "weight_preset": {"preset_id": "返回的 UUID", "version": 1}
  }
}
```

同一组织请求选择 `weight_preset` 时不要再发送 `weights`。版本可以省略，表示**创建研究时**选择当时最新版本；服务端解析后冻结实际 ID、版本、名称和生效配置。完整范围示例见[组织运行契约](organization-research-runtime.md)。旧结果不再次查询最新预设以覆盖历史配置，默认值改变也不重算已保存的个人版本。

## 权限、持久化与并发

owner 由现有认证主体绑定，输入不接受自报 owner。列表、历史读取、更新与用于创建研究的预设解析均带 owner 条件，外部用户知道 ID 也不能读取、写入或引用它。`organization_weight_presets` 在同一 PostgreSQL 数据库保存每个版本的原始／生效 JSONB；版本行不可覆盖，`(preset_id, version)` 为主键。应用初始化和迁移入口共用该表 DDL。

更新事务锁定当前 owner 的既有身份行，再读取最新版本并比较 `expected_version`，随后追加；同一 owner 的预设编辑顺序执行。客户端收到 409 应重新读取并展示差异后再提交，不能静默覆盖。数据库不可用或写入失败不返回已保存；重试创建可能产生新 ID，当前没有跨请求创建幂等键，界面需要根据实际回执处理重试。

计算和保存不取证、不调用模型、不产生新的来源采集费用。用户选择个人预设创建研究后，才进入原有有界取证流程。查询与写入使用现有数据库连接／事务；取消或应用重启后可从历史版本和研究快照读取已提交值。

## 安全引用与证据边界

沿用 A2ABreak v1.0，各方案引用其“工程解决方案／验收办法”，不是上游官方修复声明：

- [A2AB-03／上下文归属与跨租户隔离](<C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-03 上下文归属与跨租户隔离.md>)：`load_preset`、列表、版本读取、更新及研究创建解析均执行认证 owner 查询，授权发生在将配置送入研究之前。
- [A2AB-06／并发状态版本与审批绑定](<C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-06 并发状态版本与审批绑定.md>)：事务和 `expected_version` 拒绝旧版本写入；历史快照不因用户修改预设而改变。并发竞争的多请求场景与重复创建幂等未额外验证。
- [A2AB-08／结构化授权请求与权限不放大](<C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-08 结构化授权请求与权限不放大.md>)：个人预设只是偏好来源，不修改现有授权／渠道／内部资料边界，没有新增委派或权限范围。

实际端到端过程及未覆盖项见本轮交付记录；不以保存成功或空列表代替真实研究消费与历史结果验证。
