# Proposal

## Why

ADRS 的七个角色组件由同一工作流调度，开放研究中的下一步判断分散在规划、分析、反思及多种恢复分支中。近期同根研究累计超过 600 万 Token，记录已确认边缘事实阻塞、阅读误判、章节重复及修改后重复审核；需要集中研究决策，并在现有执行边界内减少无效处理。

## What Changes

- 全功能实施顺序、状态、唯一实现归属和原任务映射统一由[完整实施计划](../../../docs/IMPLEMENTATION_PLAN.md)维护；本变更保留28个细项ID，不另建一套与原功能平行的优先队列。
- 保留原 ORG、18 个 OPT、FLOW 与 M1／M2／M3 的功能范围和未完成状态。本变更28项只管理架构差量，不替换原功能任务，也不自动解冻暂缓能力；逐项承接见 design.md D0。
- 新任务采用一个主研究 Agent：读取当前目标、证据和缺口，提出下一项研究动作；可信 workflow 负责动作准入、执行、提交及终止。
- Planner 并入主 Agent 的计划能力；Search、Browser、RAG 成为有界工具适配器；Analyst 成为按问题调用的分析能力；Reflection 成为独立调用的质量评审能力；Report 拆为写作能力与确定性交付流程。保留兼容入口，不以重命名冒充自治实现。
- Skill 从冻结注册目录按需加载，继承显式选择、版本及权限交集；工具执行、预算及资料归属继续由服务端控制。
- 事实依据与实质影响分别判断：核心结论及其依赖必须核验，次要细节和编辑建议分级处理；相同标准贯穿正文、附录、图表及解说。
- 写作前建立结论与章节的归属，明确主文、附录和必要简述的职责；修订作用于明确内容单元，避免反复整稿重写。
- 按主张、必要上下文、证据及政策依赖复用判定；保留一次当前整稿的读者审阅，局部修改只重核受影响范围。
- 控制器、写作、审核及格式修复共享原根账本和持久化循环上限；分别展示原生用量、未知消费及在途预占。
- 分阶段启用 `single_research_agent_v1`。历史任务保持原执行合同；已有报告交付与预算变更继续各自保留实际状态，本提案不改写其验收结论。

## Capabilities

### New Capabilities

- `single-research-control`：主 Agent 决策闭环、按需 Skill、有界动作及兼容恢复。
- `material-quality-review`：面向研究目的的核验范围、实质影响分级、审阅收敛与交付裁决。
- `report-content-ownership`：问题、结论、章节及主附录职责，内容单元修订和依赖传播。
- `incremental-research-cost`：有界上下文、审核复用、统一循环预算及可归因成本观察。

### Modified Capabilities

无已发布主规格修改：本仓库 `openspec list --specs --json` 当前为空。以上能力是面向新运行版本的增量；与在途 `bounded-research-planning`、`stage-skill-compilation`、`research-model-budget`、`research-delivery-view` 的接合及冲突在 design.md 明确，实施时复用其最终归档路径，不并行建立第二套预算或交付权威。

## Impact

- 编排：`app/graph/compiler.py`、`state.py`、`planning_control.py`、`tool_handoff.py`、`research_jobs.py`、`recovery_policy.py` 及原七个角色模块。
- Skill／上下文：`app/skills/stages.py`、`service.py`、`research_context.py`，继续使用已注册且冻结的内容。
- 内容／质量：`report_composition.py`、`report_editorial.py`、`report_revision.py`、`claim_verification.py`、`report_quality.py`、`report_surface_review.py`。
- 计量／交付：`llm_budget.py`、`adaptive_budget.py`、`runtime_accounting.py`、现有执行控制及报告持久化，API 和工作台增加可解释投影。
- 沿用 Python、LangGraph、PostgreSQL／JSONB、现有前端及工具供应方；本期不引入新 Agent 框架、数据库、常驻服务或子 Agent 系统。
- 当前只生成规划文档；实施节奏沿原大模块完成后的真实端到端要求，子项只审阅源码和文档，不恢复局部／TDD／回归或构建等门禁。本变更不自行启动新旅程或发布。
