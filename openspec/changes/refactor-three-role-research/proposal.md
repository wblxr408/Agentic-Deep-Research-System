# Proposal

## Why

用户提出编排、任务、审计三角色，要求保留完整自动流转及LangGraph／DAG、工具／Skill、RAG、可选Jev和缓存复用。该分支保存可评审候选，便于与原架构精简方案对照；当前实际开发路线仍为 `codex/simplify-existing-architecture`，不据角色数承诺成本下降。

## What Changes

- 明确三个逻辑角色的上下文、输入产出和修改／审计边界，映射原七组件，不要求三个进程或三份预算。
- 编排承接Planner／replan；任务承接分析、写作及局部修订；审计承接独有Reflection与事实／读者／图文判断，返回问题集而非第二份报告。
- LangGraph保留状态流转、并发与恢复；薄DAG执行器只负责当前业务依赖与可执行批次，不新增调度引擎。
- Search、Browser、RAG、注册MCP保持按需工具，冻结Skill按阶段加载；研究正文由任务能力生产，发布由原可信交付流程裁决。
- Jev为可选初判后端，配置时使用，未配置时现有LLM替代；同项初判选择一个后端，共用判据与规范化输出。
- 沿现有产物、依赖审核缓存和原根账本，不复制一套缓存／计量服务；质量、内容和成本共用差量沿原变更任务跟踪。
- 仅新增角色迁移特有任务，保留原ORG／OPT／FLOW、R1—R8、M1—M3、模板／方法／账号及冻结范围。所有运行行为待后续选择与实施。

## Capabilities

### New Capabilities

- `research-role-collaboration`：同根编排／任务／审计的交接、问题回流、可选初判、可信交付与成本归属。

### Modified Capabilities

主规格目录当前为空；不复制在途质量、内容与成本合同。共用要求引用 `refactor-single-research-agent` 的当前复评版本，后续整合沿已交付实现与证据补差，不重新执行同一功能。

## Impact

候选实施涉及现有Planner／replan、Analyst／Report／Reflection消费者、`compiler.py`、`planning_control.py`、`tool_handoff.py`、报告及审核入口、现有Skill、模型治理和根收据。沿用Python、LangGraph、PostgreSQL及现有模型／工具协议；不增加远端Agent发现、跨组织委派、新工作流引擎或预算owner。本次只保存规划，未更改运行代码或执行测试／模型请求。完整协作图、映射和边界见[三角色方案](../../../docs/THREE_ROLE_ARCHITECTURE.md)。
