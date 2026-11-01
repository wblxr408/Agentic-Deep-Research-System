# Proposal

**当前路线（2026-11-01用户确认）：** 本变更在 `codex/simplify-existing-architecture` 实施原架构精简；原目录名保留历史引用。先做原账本／缓存计量、内容归属和有界输入、分级与依赖复用，再按覆盖删重复调用。三角色方案保存在独立 `codex/three-role-agents` 分支，不成为本变更前提；已进入5.1／5.5部分源码实施，完整差量与运行接受仍待完成，见[实施记录](../../../docs/acceptance/architecture-simplification-20261101.md)。

## Why

ADRS 已有动态DAG、专家模型调用、条件重规划和受控交付，按OpenAI Agents SDK口径可包含专家Agent；七个组件的数量不能证明架构有问题。当前需要解决的是已有记录中的核验误拦、章节重复、无关上下文和修订后的重复审核，应优先在现有图与组件内补差。

2026-11-01复评撤回“统一主Agent循环是P0前提”的判断。最新原根已实际完成事实／读者／PDF图文交付，累计6,092,491 Token；这证明该范围可交付，未证明成本合理或全部功能通过。变更目录名保留为历史标识，当前范围改为研究质量、成本与职责收敛；完整依据见design.md D1。

## What Changes

- 用户确认把旧调研的目录缓存、百篇筛选、分级导读和分批补证接入现有RAG，按[复用／适配清单](../../../docs/CORPUS_RAG_INTEGRATION_PLAN.md)沿现有资料入口、来源生命周期、解析／分块、检索、技术卡和根恢复补消费者。目录逐项枚举与证据top-k分开，原稿／摘要／派生卡、材料可用／已读／已核状态分列；旧机构／网络／会刊规则须参数化。衔接主题深读与R8图型／图块，当前仅规划，未导入旧数据或新增运行服务。
- 百篇规模纳入本轮合同：区分全语料覆盖和全部精读，沿已有逐篇卡／分包／原根持久化按主题综合，按剩余论文／字段／审核预测；新增一篇只更新受影响依赖，不创建100套Agent或将600万历史修复累计按篇放大。具体见成本方案第8节，当前未取得100篇运行证据。
- 2026-11-01用户纠正：最新报告缺所需可视化且论文原图仍为整页预览。原R8／12.9提升本次P0，补图需求覆盖、模块／机制图、真正事件时间轴、数据图与独立原论文图块；本变更只接合审核和交付，唯一实现归属沿原任务，不能把历史图文审核通过解释为上述需求完成。见[可视化修复计划](../../../docs/REPORT_VISUALIZATION_PLAN.md)。
- 全功能状态和顺序由[完整实施计划](../../../docs/IMPLEMENTATION_PLAN.md)维护；28个原ID保留，4.1／4.2退出当前执行清单，26个追踪项按补差／复用／职责澄清处理，不能全部解释为新增开发。
- 保留原ORG、18个OPT、FLOW与M1／M2／M3范围、实际验收及冻结状态，承接见design.md D0。
- 保留现有LangGraph、Planner／replan、工具交接、Analyst、Reflection与Report入口。澄清一个研究根的状态／预算所有权与各专家的输出职责；不要求合并类、建立新主Agent文件或迁移SDK。
- Search／Browser／RAG按现有工具契约使用；Analyst保留领域分析，Report保留写作与独立交付判定。逐项核查Reflection与报告审核的输入、目的和触发，只有同一判断确实重复且无独有覆盖时才删减对应调用，不整段取消评审阶段。
- 复用已经按阶段编译的冻结Skill，明确当前调用所需内容和必要约束；只补实际装入无关内容的路径，不增加通用动作层或额外Skill选择模型。
- 事实依据与实质影响分别判断：核心结论及其依赖必须核验，次要细节和编辑建议分级处理；相同标准贯穿正文、附录、图表及解说。
- 写作前建立结论与章节的归属，明确主文、附录和必要简述的职责；修订作用于明确内容单元，避免反复整稿重写。
- 按主张、必要上下文、证据及政策依赖复用判定；保留一次当前整稿的读者审阅，局部修改只重核受影响范围。
- 沿原根账本补齐操作用途、共享修订机会和剩余工作预测，复用已有预留／收据／无损格式投影；分别展示原生、未知与在途用量，不因角色数推断重复成本。
- 质量／内容／复用政策按必要版本差量对新任务启用，历史任务保持原合同；当前不推出 `single_research_agent_v1`，不要求两套运行器并存或把界面强制改为一个Agent。
- 主循环仅为后置候选：须有真实业务缺口证明现有DAG／重规划无法适当承接，先比较原Planner的最小扩展，再计入额外控制请求和迁移成本；当前无充分证据，不进入必做依赖。

## Capabilities

### New Capabilities

- `single-research-control`：保留路径名以维持引用；当前定义研究根所有权、专家／工具职责、已有观察驱动规划、冻结Skill及稳定恢复，不要求新增统一主循环。
- `material-quality-review`：面向研究目的的核验范围、实质影响分级、审阅收敛与交付裁决。
- `report-content-ownership`：问题、结论、章节及主附录职责，内容单元修订和依赖传播。
- `incremental-research-cost`：有界上下文、审核复用、统一循环预算及可归因成本观察。

### Modified Capabilities

沿本变更原主规格为空的基线，以上合同只承载实际质量、内容和复用政策差量，不要求新运行器。与在途 `bounded-research-planning`、`stage-skill-compilation`、`research-model-budget`、`research-delivery-view` 的接合见design.md；实施时使用其真实归档路径，不建立第二套预算／交付权威，也不因四份文件存在就重做其已有要求。

## Impact

- 编排：优先审阅 `compiler.py`、`planning_control.py`、`tool_handoff.py` 及原角色消费者；仅发现具体接线或重复判断差量才改，不以触及七类或新增控制器作为完成标准。
- Skill／上下文：`app/skills/stages.py`、`service.py`、`research_context.py`，继续使用已注册且冻结的内容。
- 内容／质量：`report_composition.py`、`report_editorial.py`、`report_revision.py`、`claim_verification.py`、`report_quality.py`、`report_surface_review.py`。
- 计量／交付：复用 `llm_budget.py`、`adaptive_budget.py`、`runtime_accounting.py`、现有执行控制及报告持久化；API／工作台只补当前质量、步骤理由及成本的必要投影。
- 沿用 Python、LangGraph、PostgreSQL／JSONB、现有前端及工具供应方；本期不引入新 Agent 框架、数据库、常驻服务或子 Agent 系统。
- 原规划已经形成，当前5.1／5.5开始部分源码实施；实施节奏沿原大模块完成后的真实端到端要求，子项只审阅源码和文档，不恢复局部／TDD／回归或构建等门禁。本变更不自行启动新旅程或发布。
