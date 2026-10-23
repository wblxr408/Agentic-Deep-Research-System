# 组织研究请求与运行契约

新增的可选 `organization_research` 将已有组织范围和权重配置接入主应用的 `POST /api/v1/research`。桌面工作台可开启“组织研究模式”，选择高校／科研实验室／企业的非空组合，填写一个或多个具体对象、来源网址、学科与日期，再走原有研究流程。对象范围与信息渠道分别配置。

## 请求、状态与结果

```json
{
  "query": "研究 MIT 与 CSAIL 的公开网络研究方向，分别分析并说明证据缺口",
  "organization_research": {
    "scope": {
      "organization_types": ["university", "laboratory"],
      "entities": [
        {
          "entity_id": "mit",
          "name": "MIT",
          "type": "university",
          "source_urls": ["https://www.mit.edu/research/"],
          "resolution_status": "pending"
        }
      ],
      "disciplines": ["computer science"],
      "topic": "计算机网络研究",
      "start_date": "2020-01-01",
      "end_date": "2026-10-20"
    },
    "weights": {"preset": "research_development"}
  }
}
```

完整字段校验复用[范围契约](organization-research-scope.md)和[权重契约](research-evaluation-and-weights.md)。三类对象支持七种非空组合，具体对象最多 200 个，学科 1–20 个。类型冲突、空类型、倒置日期、无效来源和非法权重由服务端拒绝为 422；页面先给出可理解的输入提示。顶层配置与范围禁止未知字段。未设置新配置时沿用通用研究入口。

创建时服务端计算并保存 `effective_weights`，连同原始配置、范围规则版本、结构版本和取证截止时间形成运行配置。主图状态增加 `organization_research`、`organization_result`，状态累积器识别两字段；编排、分析、反思、重规划与报告均消费同一份配置。运行快照继续保存在原数据库，最终结果接口返回两字段。用户可在结果区域查看本次对象、学科、时间范围和去重证据数量。

Planner 保留主题范围，并把明确对象的来源页接入既有浏览任务。网址后的模型说明文字在组织模式规划入口截断，避免当作网络地址发送；取证权限、真实地址检查和预算仍由原工具网关执行。此处不会提高调用次数或绕过 SSRF／渠道限制。对象很多时仍可能覆盖不足，不能把待处理来源当作已读取。

`organization_result` 保留兼容的证据定位字段；其中名称提及、来源域名和 `publication_attribution: pending` 仍只是定位索引，不能当作论文数。4.4 新增 `scope_result`、`publication_metadata`、`comparison_groups`、`source_checks`、待核项及带依据的推断／建议：从真实原文定位日期、发表时机构署名，并由代码计算各对象及联合汇总。详细字段、日期精度、版本未关联和检查边界见[成果 ACI](organization-findings.md)及[真实端到端记录](acceptance/organization-findings-20261020.md)。候选仍保留消歧状态，自动评价／匹配及完整界面与导出继续实施。

## 持久化与错误处理

原请求进入 `research_sessions.request_payload`；运行快照保留完整配置及中间结果，最终摘要与报告写入现有会话。读取仍按认证 owner 隔离，客户端配置不能指定 owner 或扩大内部资料范围。已待确认的相同请求沿用原冻结配置；[4.2 实跑记录](acceptance/organization-resume-20261020.md)已验证实际暂停、改变默认值、重启 API 后通过原审批恢复，仍保留原配置。

默认权重由 `config/organization-presets.json` 保存操作员版本及两个完整预设。修改值时须修改版本；客户端不能指定配置文件路径。组织运行 v2 同时冻结原始配置、生效权重／偏好映射、范围规则版本、对象、截止时间和评价目录完整记录（20 项体系、当前 12 个部分公开来源发布）。目录只用于保存当时可用口径，`applied_to_evidence: false` 明确表示尚未对取证成果完成评价。恢复读取保存值，不重新加载默认值覆盖；已有 v1 历史记录不伪造补齐缺失目录。本项复用现有 JSONB 字段，不新增表。

本次真实 PostgreSQL 链路发现并修复初始化缺少 `total_tokens`／`total_cost_usd` 的问题；结果／状态读取显式解码 JSON，最终快照保留完成摘要。单个工具失败不再提前终结仍在综合的根工作流；报告提交前不发布 completed 状态。无证据时仍返回原有受限结果，不用自造资料补齐。

没有新增出站服务、Agent 身份或编排框架，也没有独立模型抽取调用。取证失败、重试、取消和超时继续受原预算及审批约束；界面展示执行失败或缺口，不能把一次请求成功当作研究完成。详细实跑记录见[本轮端到端交付](acceptance/organization-runtime-20261020.md)。

## A2ABreak 引用与本次边界

个人预设已接入真实研究：`weight_preset` 与直接 `weights` 二选一，由认证 owner 解析指定或最新版本，再将实际版本、名称及生效配置复制入运行快照。编辑预设不回写旧会话；见[个人预设 ACI](personal-research-presets.md)和[4.3 实跑](acceptance/organization-presets-20261020.md)。5.2 的[工作台编辑器](organization-weight-editor.md)已通过实际界面保存／选择 v2 并启动研究，完整结果仍保存同一版本及分层比例；见[界面端到端记录](acceptance/organization-weights-ui-20261020.md)。

沿用流程设计已完成的全部 11 项适用性评估；本轮不新增 Agent Card、外部委派、Webhook 或分块协议。以下引用本地基线 v1.0 各方案的“工程解决方案／验收办法”，均为来源核对后的工程方案，不表示上游官方修复或所有控制均已部署验证。

- [A2AB-03／上下文归属与跨租户隔离](<C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-03 上下文归属与跨租户隔离.md>)：配置随原 owner 会话、后台作业与快照传递，结果从原归属查询读取。本轮真实管理员登录并读取自己的研究；跨用户拒绝路径尚未追加端到端验证。
- [A2AB-06／并发状态版本与审批绑定](<C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-06 并发状态版本与审批绑定.md>)：保留执行 ID 与数据库事务约束，相同待确认请求复用原配置；根工作流完成后再发布报告状态。4.2 已验证改变默认值和重启后的真实恢复；并发审批尚未实跑。
- [A2AB-08／结构化授权请求与权限不放大](<C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-08 结构化授权请求与权限不放大.md>)：结构化范围和权重是研究偏好，明确来源仍经过原只读工具、网络权限和全链预算；提示词不作为授权控制。本轮真实来源取证保留工具审计，未执行额外攻击或安全回归。
