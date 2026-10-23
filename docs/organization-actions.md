# 研究验证路线与合作行动卡

2026-10-21：OpenSpec 7.7 的代码已接入，尚未运行；按用户要求，全部 TODO 实现结束后统一端到端验收。本文描述数据契约与实现，不是通过记录。

## 用途与链路

勾选 `actions` 模块时，既有 Analyst 在 `organization_data.action_cards` 提交带原文依据的建议；普通函数 `build_action_view` 校验提案，复用现有 `snapshot_from_research` 与 `score_matching_snapshot` 计算同组优先级。Report、结果摘要、Markdown、JSON 和离线 HTML 使用该结果。没有新增 Agent、模型回路或对外联系工具。

发展目的允许 `research_validation`，合作发现允许 `cooperation`，综合目的允许两种。单独高校／实验室同样可生成研究验证路线。目的和权重分别冻结；合作权重不自动增加合作页。

## 输入与输出

启动请求在 `organization_research.action_requirements` 中可提供：`research_goal`、`cooperation_goal`、`offering`、`time_window`，以及最多 12 个自由条件、4 个关系硬条件和 20 个指标硬条件。可选文字为空时传 null，非空至少 3 字符、最多 1,200 字符。前端仅在选择行动模块时显示需求面板。

Analyst 建议含选定对象 ID、行动模式、待验证问题、1–5 个来源引语、可选互补假设、最多 8 个建议步骤、5 个公开联系入口；至多处理 20 张提案。建议不能携带“已确认关系”或指定评分。引语必须定位于本任务保留原文，来源必须能识别目标对象，搜索发现片段不能冒充已读原文。

结果保存 `requirements`、`cards`、`priority_preview`、`priority_gap`、原冻结权重及缺口。卡片区分需求不足、硬条件未成立、缺有依据议题、有条件研究路线、仍需可行性／联系核实。优先级保留比较组、分项贡献、缺失区间与覆盖率，不输出跨学科质量榜或合作成功概率。历史署名人员及相关关系单列，核实状态不因评分变化。

合作目的缺少合作目标、可提供资源或时间要求时保持缺项；自由文字条件没有被当成已完成可行性审核。公开入口必须是实际保留页面中的原始 HTTP(S) 链接并满足冻结来源范围，不能拼接邮箱或猜 URL。记录 `outbound_action_taken=false`；没有发送操作。

## 本人证据预览 API

- `GET /api/v1/research/{session_id}/actions`：读取本人已完成研究的保存视图；历史研究只读投影明确返回 `persisted=false`。
- `POST /api/v1/research/{session_id}/actions/preview`：以本人原始证据检查显式候选，可传 `requirements`、`weights`、`action_cards`；不写原报告、关系、预算或资料，不新增采集或模型调用。省略 requirements 沿用原需求，显式 `{}` 表示清空预览需求。

示例请求体：

```json
{"requirements":{"cooperation_goal":"验证分布式存储方案","offering":"提供实际工作负载","time_window":"未来六个月"},"action_cards":[]}
```

空提案返回缺议题卡，不能据此宣称完成匹配；没有实际 run/session/execution 来源或有效日期时显示 `priority_gap`。不存在或不归属当前主体返回 404，未完成／非组织研究／预览缺原文返回 409，非法结构返回 422。补齐合法输入后可重新预览；新取证需单独启动研究。

## 运行与证据边界

沿用既有 A2ABreak v1.0 全 11 项适用性评估，本增量执行 A2AB-03《上下文归属与跨租户隔离》的本人证据查询、A2AB-07《Webhook归属验证与受控出站》的公开入口准入、A2AB-08《结构化授权请求与权限不放大》的只读建议、A2AB-10《委派环路检测与全链预算》的既有模型／工具预算；引用均为方案“工程解决方案／验收办法”章节，索引与具体方案见 [TODO 安全引用](OPTIMIZATION_TODO.md#安全方案引用与规划状态)。没有新增外部 A2A、Agent Card、Webhook 或委派，其他项沿用原评估。这些是待项目验证的工程方案，不能视为已完成安全验收。

统一端到端阶段需覆盖：三种目的、独立高校、需求缺失、硬条件未知、改权重但不改关系、旧冻结权重、双 owner、公开入口来源及各导出一致性。本阶段没有执行这些场景。
