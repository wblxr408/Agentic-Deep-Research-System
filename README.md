# Agentic Deep Research System (ADRS)

ADRS 面向企业、高校和科研实验室的研究发展分析：从公开论文、官方材料和用户选择的内部资料中取证，梳理研究布局、机制演进、团队资源与合作课题，形成带来源的图文报告。对象可单选、多选或混合，学科、评价体系、权重、内容模块、模板与绘图方案分别配置。

## 当前进度

2026-10-25：工作流新增顶部暂停／继续／终止与停止原因、配置重启入口；恢复默认可见的 SSE Agent／工具实时反馈，节点展示具体任务。修复压缩中间件缓冲 SSE；专用浏览器和真实图检查点操作通过。[执行控制](docs/RESEARCH_EXECUTION_CONTROLS.md) · [实际操作](docs/acceptance/research-controls-sse-20261025.md)

2026-10-25：追加完成独立 Edge 的 9 组双账号／弱网浏览器场景，覆盖跨标签切换、草稿和资料／配置隔离、旧响应迟到、900ms 延迟及限速、认证超时和断网退出恢复。修复空流程记录打开任务白屏、已保存自定义模型下拉框显示错误。[浏览器操作记录](docs/acceptance/accounts-browser-network-20261025.md)

2026-10-25：已补齐多用户注册、账号页和管理员用户管理。注册账号默认为普通用户；研究、资料、报告、模板、Skill、渠道及模型配置按账号归属访问，模型上下文延续到后台线程。管理员管理账号和注册开关，私有研究接口仍按本人授权。现有管理员与 9 个保留任务已原位升级，11 组本次功能端到端操作通过，未调用付费模型。[多用户使用与权限](docs/MULTI_USER_WORKSPACES.md) · [实际交付记录](docs/acceptance/multi-user-workspaces-20261025.md)

2026-10-25：已按用户确认的设计改造前端：首页四套背景及配色、黑色蒙版、中英文主副标题，多行研究草稿与分组配置、真实任务流程画布、独立动态技术文档、来源卡片和图表操作入口。详见[前端设计](docs/FRONTEND_DESIGN.md)和[实际页面操作](docs/acceptance/frontend-workspace-20261025.md)。本轮只推进前端，原后端优化及新付费调研仍暂停。

首页中文为“知之为知之，不知则搜之。”与“搜而不思则罔，思而不搜则殆。”；英文为“Research is all you need”与“In Sources We Trust”，分别采用主、副标题层级。技术入口 `?view=technology` 在独立窗口打开，解释原研究编排、RAG、Skill、模型路由和图文交付；运行工作区按实际计划、持久状态与 SSE 绘制，刷新保留任务进度。

2026-10-25：按用户要求，完成当前“重复补证导致整轮重分析”的源码修复后暂停后续优化与新付费旅程，转入前端方案讨论。U2f原现场保留：首轮7阶段后补证得到相同正文，第二轮在132558 Token处上下文准入暂停。新修复尚未复跑完整端到端，所有未完成验收继续保留。

2026-10-25：ORG、OPT-01—18与FLOW选定实现路径已接入，正在统一真实端到端运行。**新的完整自动深入报告尚未通过交付验收。** 真实任务暴露的上下文、发表身份、结构、审核及恢复问题持续修复，原失败、用量与截止时间保留；源码完成、实际运行、语义支持和真实读者反馈分别记录。

[主TODO](docs/OPTIMIZATION_TODO.md) · [实施账本与选型](docs/IMPLEMENTATION_LEDGER.md) · [统一真实旅程及失败记录](docs/acceptance/unified-research-20261023.md) · [当前使用说明](docs/organization-research-guide.md)

原云端执行点已停写，当前按用户授权回到本机继续，并逐模块推送同一任务分支。U2e完成7阶段、四个论文／出版页来源归并为两发表；111项全部审核、79支持，230460／240000 Token时因修订余量不足保留草稿，未正常图文交付。恢复顺序、统计分句、写作／建议审核、参数／章节定位与阶段分工修复已提交；同原范围和额度的U2f已实际创建继续完整旅程，效果待观察。完整图文、导出和读者质量尚未通过。[本机实际记录](docs/acceptance/local-continuation-20261024.md)保留原结果；[云端交接](docs/CLOUD_CONTINUATION_20261024.md)为历史，本机数据库、密钥、会话和依赖不随Git迁移。

| 能力 | 当前状态与依据 |
| --- | --- |
| 对象、学科、评价与权重 | 单／多组织、历史署名、评价适用性与版本、硬条件、分项贡献、缺失区间、个人预设及固定证据重排已接入。历史复合交付29/34；后五项及本轮跨对象／跨学科整体交付待统一验收。[组织研究计划](docs/RESEARCH_DEVELOPMENT_PLAN.md) |
| 取证与内部资料 | 搜索、受控网页／PDF读取、任务原文版本与定位、显式归档、分块／词汇特征／索引及生命周期已接入。网上证据默认保存在本任务，内部检索由用户明确启用。[工具ACI与五类执行计划](docs/RESEARCH_EXECUTION_PLAYBOOK.md) |
| 深读、演进与行动 | 同一Analyst按问题分阶段分析，取得、选段、成果归属和语义支持分别保存。真实任务已完成十二步分析，完整自动报告仍待通过。[分阶段分析及恢复](docs/question-analysis-workflow.md) |
| 图文模板与绘图 | 预设／自定义页面、主文／技术附录、内置图及报告级／单图Skill选择已接入；固定Matplotlib适配器生成SVG、PNG与单图PDF。依赖已部署，专业绘图与跨学科可读性待实际交付。[绘图契约](docs/research-figure-skills.md) |
| 预算、恢复与取消 | 实际准入、主备结算、已消费审核预留扣用、未知价格、持久收据和本人取消已接入。新长任务采用有限策略2；同根恢复不重置原额度／期限。[预算说明](docs/model-token-budget.md) · [取消与收据](docs/research-cancellation.md) |
| 审核、历史与反馈 | 全部主张覆盖、原文与任务方法分别核对、一次分批定位修订及相同输入原判复用已接入。未支持稿暂停，原稿／响应／实际费用保留，模型核对与人类试读分记；新成本／质量结果待完整旅程。[事实质量](docs/report-evidence-semantics.md) · [历史与模板](docs/report-history-templates.md) · [质量反馈](docs/research-quality-feedback.md) |

原有人工整编的北大图文稿及历史专项运行继续保留，范围见[2026-10-22记录](docs/acceptance/pku-deep-research-20261022.md)。它们不替代本轮全链自动交付。新增DDL和本机依赖已用于真实旅程；未运行的业务边界继续留在TODO，不再用“未部署”代替当前实际状态。

## 核心思想

用完成研究任务所需的最小结构，让用户看懂计划、进度、调整原因和证据依据。Planner、Analyst、Reflection、Report是逻辑角色；搜索、浏览、内部检索是按需取证工具。授权、范围、统计、预算、取消和状态竞争由可信程序执行，Skill提供阶段约束与方法。

公开研究默认联网。用户启用内部资料后，两类证据共同参与研究；内部命中不会关闭联网。原文留存先用数据库与版本账本，是否启用检索按实际召回需求决定。未知指标、未取得全文、未执行通道和未知费用分别保留。

研究计划、运行版本、审核状态和预算放在工作区与研究记录；正常报告保留发现、解释、图表、引用和必要的方法说明。完整准则见[ADRS核心思想](docs/DESIGN_PRINCIPLES.md)与[报告写作规范](docs/REPORT_WRITING_GUIDE.md)。本轮按用户要求只运行完整真实端到端业务，不运行局部、回归、冒烟或其他门禁。

技术摘要与原文引文分别校验：摘要未通过时，在当前原文中复核到的位置仍可用于写作和审核查找；科学结论继续逐项核验。来源文档、发表和全文覆盖分别计数，明确的同发表来源链接保留各自证明；这些增量尚待完整图文旅程验收。

## 完整研究流程与分工

下图对应当前主应用执行顺序。取证可按独立依赖并行；分析在同一Analyst内分阶段运行。目标架构、历史状态及逐阶段输入输出见[完整流程设计](docs/RESEARCH_WORKFLOW_DESIGN.md)。

```mermaid
flowchart TB
    U["用户配置：问题、对象、学科、来源<br/>权重、模块、模板、绘图和预算"]
    C["程序校验、冻结配置与阶段Skill"]
    P["Planner：计划、来源与依赖"]
    D["统一调度：权限、原额度、期限与取消"]
    W["搜索与网页／PDF读取"]
    K["内部资料检索：显式启用"]
    E[("任务原文、版本、覆盖与引用")]
    B{"补证后的材料、权限与输入校验"}
    A["Analyst：成果身份与逐问题分析<br/>机制、实验条件、演进与行动；保存阶段结果"]
    F["Reflection：分析检查与有限补证判断"]
    R["Report：主文、技术附录与固定引用<br/>结构修订最多一轮"]
    Q["逐主张原文／任务方法核对与统计校验"]
    V["定位正文修订：最多一次"]
    G["内置图，或所选Skill与固定绘图程序"]
    H["原资料／配置复核、披露与交付装配"]
    O["图文报告、主文／附录导出与历史"]
    S["保存当前稿、响应、用量和停止原因"]
    U --> C --> P --> D
    D --> W --> E
    D -->|已启用| K --> E
    E --> B
    B -->|首次分析或材料有变化| A
    B -->|同根材料不变，原完整输入仍有效| R
    A --> F --> R --> Q
    F -->|需要且仍有范围与额度| P
    Q -->|需修订且原额度允许| V --> Q
    Q -->|完整支持| G --> H --> O
    Q -->|未完整支持| S
    R -->|结构或服务中断| S
    G -->|未完成| S
    S -->|仅结构或流中断；原输入、额度和期限；最多一次续作| R
```

| 角色／组件 | 职责 | 工具与Skill边界 |
| --- | --- | --- |
| Planner | 拆研究问题、来源和依赖，说明计划调整 | 加载规划阶段Skill；工具权限与预算由程序准入 |
| Search／Browser／RAG | 发现、读取或召回所需证据 | 共同输出真实来源、范围与定位；不各自强制拥有一轮自主思考 |
| Analyst | 按所选模块做布局、关系、机制、实验条件、演进和行动分析 | 加载领域与分析Skill，复用原阶段检查点；实际原文支持仍需后续审核 |
| Reflection／来源审核 | 分别检查分析与最终正文支持，给出定位修订 | 共享原根额度；原文片段、统计单位与修订记录可追溯 |
| Report／绘图 | 面向读者写作，装配页面、主文与附录；按冻结数据绘图 | 可选绘图Skill只提供受信适配范围内的声明式样式，不执行任意脚本 |
| 调度、存储与交付程序 | owner／execution／计划绑定，预算、权限、取消、版本、恢复和导出 | 一个根拥有原额度和期限；新执行隔离迟到写入，旧失败与报告保留 |

源码与适用限制逐项见[实施账本](docs/IMPLEMENTATION_LEDGER.md)。专业绘图、内部资料全链、混合非计算机对象、异常恢复及真实读者验收仍需各自的实际证据；不根据类名、接口存在或模板页数认定完成。

## 技术栈

| 层     | 选型                      | 作用                             |
| ------ | ------------------------- | -------------------------------- |
| 编排   | LangGraph                 | 状态机式工作流、条件分支、检查点 |
| 后端   | FastAPI                   | HTTP API、SSE 流式接口           |
| LLM    | OpenAI 兼容接口           | 支持 Qwen / DeepSeek / OpenAI    |
| 检索   | pgvector + PostgreSQL 全文检索 + RRF + 可选 rerank | 按需内部混合检索；当前全文排序使用 `ts_rank` |
| 浏览器 | Playwright                | 网页抓取与页面提取               |
| 数据库 | PostgreSQL                | 会话、引用、系统配置             |
| 缓存   | Redis                     | 会话缓存、SSE 状态、运行时配置   |
| 前端   | React + Vite + TypeScript | 研究界面与实时输出               |

新增[报告口径与导出](docs/organization-report-export.md)：研究数据保存当次对象、权重、目录版本与来源，读者报告保留发现、条件、图表和引用；提供Markdown、完整研究JSON和离线HTML。[2026-10-21历史专项记录](docs/acceptance/organization-report-export-20261021.md)覆盖PostgreSQL、界面、下载及断网展开；当前图像模板与正文全面审核已接源码，整条自动深入研究仍待本轮统一交付。

已交付[腾讯 Harp 公开有界运行案例](docs/acceptance/tencent-network-case-20261021.md)：新的真实模型／取证任务保留来源、月精度日期、预算、失败和下载产物；生成正文仍需复核，同名搜索噪声及审计缺口随案例公开，不当成精准检索或战略研判已通过。

当前使用步骤及来源限制见[组织研究使用说明](docs/organization-research-guide.md)与[现状规格](docs/SPEC.md#13-功能范围)。[独立高校／混合对象／材料学历史案例](docs/acceptance/organization-cross-domain-20261021.md)覆盖有界样本、学科适用性及同证据改权重，保留当时的报告和取证。CCF／ICORE／ABDC只有部分公开样本，JCR等授权数据及自动赋值仍有缺口。当前新报告在完整依据核对支持后才正常交付；历史专项completed不回算为当前审核通过，模型支持也不代表人工确认。

## 核心能力

- 自动生成研究 DAG
- 工具驱动的多 Agent 协作
- 长生命周期会话与检查点
- SSE 实时事件流
- 证据驱动的报告生成
- 反思校验与重规划
- 报告长度分档控制（短文 / 中篇 / 长篇）
- 内部知识库源 CRUD、分组管理与文件上传
- 16 个上游只读渠道，支持来源选择、后端回退、按用户维护配置与采集历史

上游渠道的操作范围、依赖配置和维护流程见 [渠道使用说明](docs/research-channels.md)，功能回归及真实公开内容结果见 [验证记录](docs/research-channels-verification.md)。

## 目录结构

```text
deepintel/
├── app/                          # 后端主代码
├── docs/                         # 设计、部署、模型与学习资料
├── frontend/                     # 前端项目
├── metrics/                      # 各能力主题的指标采集
├── scripts/                      # 模型预下载与辅助脚本
├── tests/                        # 单元测试与集成测试
├── docker-compose.yml            # 本地一键启动编排
├── Dockerfile                    # 后端镜像
├── requirements.txt              # Python 依赖
├── start-deepintel.ps1           # Windows 启动脚本
├── SPEC.md                       # 技术规格文档
└── README.md                     # 项目总览
```

### `app/` 文件说明

#### `app/main.py`

- FastAPI 入口
- 初始化日志、中间件、路由和生命周期
- 启动时连接数据库，关闭时释放资源

#### `app/config.py`

- 统一读取环境变量
- 定义 LLM、数据库、Redis、RAG、浏览器、API 配置

#### `app/llm_client.py`

- 构建 OpenAI 兼容客户端
- 统一不同 LLM provider 的接入方式

#### `app/api/`

- `health.py`：健康检查与就绪检查
- `research.py`：研究任务创建、状态查询、结果查询、SSE 流式接口
- `config.py`：前端可配置的 LLM 运行时配置接口
- `documents.py`：内部知识库源管理、分组、上传与切分入库接口
- `channels.py`：上游渠道目录、当前用户配置/历史与实际内容采集

#### `app/agents/`

- `planner.py`：把用户问题拆成 DAG
- `search.py`：搜索 Agent
- `browser.py`：浏览器 Agent
- `rag.py`：按需内部资料检索工具，复用 RAG 混合检索实现
- `analyst.py`：综合分析
- `reflection.py`：事实校验与重规划判断
- `report.py`：报告生成
- `browser_demo.py`：浏览器能力演示

#### `app/graph/`

- `state.py`：LangGraph 状态、DAG、证据、引用、校验模型
- `compiler.py`：把节点和边编译成可执行工作流
- `nodes.py`：节点定义
- `edges.py`：边路由定义

#### `app/rag/`

- `embedder.py`：向量嵌入
- `retriever.py`：混合检索
- `reranker.py`：重排序

#### `app/tools/`

- `search_tools.py`：搜索相关工具封装
- `browser_tools.py`：浏览器操作封装
- `retrieval_tools.py`：检索相关工具封装

#### `app/db/`

- `connection.py`：数据库与 Redis 连接
- `models.py`：数据模型
- `migrate.py`：建表与初始化 schema

#### `app/observability/`

- `sse_manager.py`：管理 SSE 事件队列
- `trace.py`：Agent 事件追踪与结构化日志

### 其他目录说明

#### `frontend/`

- `src/App.tsx`：前端主入口与视图切换
- `src/main.tsx`：React 挂载入口
- `src/components/ResearchDashboard.tsx`：研究工作台
- `src/components/AgentTrace.tsx`：Agent 事件流展示
- `src/components/ToolTrace.tsx`：工具调用流展示
- `src/components/ReportPreview.tsx`：报告预览
- `src/components/LLMConfigPanel.tsx`：LLM 配置面板
- `src/components/DocumentManager.tsx`：知识库源、分组、上传与维护界面
- `src/components/ChannelPanel.tsx`：联网渠道选择、后端维护与实际内容采集
- `src/hooks/useSSE.ts`：SSE 连接封装

#### `metrics/`

- `langgraph_workflow/`：工作流指标
- `research_dag/`：DAG 质量与并行度指标
- `multi_agent/`：多 Agent 协作指标
- `stateful_agent/`：会话与恢复指标
- `browser_agent/`：浏览器执行指标
- `reflection_agent/`：校验与幻觉控制指标

#### `tests/`

- `tests/agents/`：Agent 单测
- `tests/graph/`：图编排单测
- `tests/integration/`：端到端流程测试

#### `scripts/`

- `preload_models.py`：预下载模型
- `download_all_models.py`：一次性下载全部依赖模型

#### `docs/`

- `RESEARCH_WORKFLOW_DESIGN.md`：完整调研流程图、阶段分工、交接边界及已有／改造／新增状态
- `OPTIMIZATION_TODO.md`：18 个能力模块及跨模块规划
- `RESEARCH_DEVELOPMENT_PLAN.md`：跨对象、跨学科组织研究实施路线
- `organization-research-scope.md`：已交付的组织范围预览 API、归属计数与输入来源边界
- `research-evaluation-and-weights.md`：评价与权重 API、逐来源接入状态、版本与授权边界
- `research-matching-preview.md`：owner 证据快照、硬筛选、分项贡献、缺失区间及重排 API
- `DEPLOYMENT.md`：部署说明
- `MODEL_DOWNLOAD.md`：模型下载说明
- `LLM_CONFIG_FRONTEND.md`：前端配置说明
- `INTERVIEW_GUIDE.md`：面试讲解资料
- `WBS.md`：工作分解与开发计划

## 开发细节

### 研究流程

1. 用户在前端输入研究主题
2. `app/api/research.py` 创建 session
3. `app/graph/compiler.py` 编译 LangGraph
4. `app/agents/planner.py` 生成 DAG
5. `search / browser` 采集公开证据；用户启用内部资料后，`rag` 补充检索，按 DAG 依赖执行
6. `analyst.py` 生成分析结论
7. `reflection.py` 判断是否需要重规划
8. `report.py` 生成 Markdown 报告并推送 SSE

以上为当前主应用链路，最终 Markdown 在 `report.py` 内另有来源审计。目标中的图像驱动交互报告、绘图与装配后终审见 [完整流程设计](docs/RESEARCH_WORKFLOW_DESIGN.md)，不以目标图替代现状说明。

### 输出长度控制

- 前端支持 `short / medium / long` 三档输出长度。
- 后端按档位控制报告生成 token 预算、搜索次数和工具结果上限。
- 目标是避免报告被截断，同时让简单问题保持低成本。

### 知识库管理

- 前端提供知识库源的新增、编辑、删除和分组管理。
- 上传文件支持 `json`、`md`、`docx`、`pdf`、`txt`。
- 新接入代码按所选策略切分并保存词汇特征；仅显式启用稠密时生成embedding，默认不加载模型。此增量尚未运行，见[特征契约](docs/versioned-retrieval-features.md)。
- 选择“仅保存与直接定位引用”时不物化关键词检索小块；可在详情显式建立词汇索引。已启用来源可关闭或回滚代际，详见[索引契约](docs/versioned-retrieval-indexes.md)。
- 研究界面的“补充检索内部资料”默认关闭，开启后可指定分组；留空检索当前用户全部资料。资料命中、为空或不可用都不决定是否联网，工具许可与预算仍然生效。
- 内部资料来自手动录入或上传。历史研究报告和引用虽已保存，但需要手动入库才能参与内部检索。
- 稠密编码模型用于选择后的表示；检索稠密及重排由服务端分别显式启用。默认词汇查询不加载它们，公开研究默认不启用内部检索。

研究请求示例：

```json
{"query":"分析新能源汽车市场的最新变化","channels":["web"],"use_internal_docs":false}
```

需要结合内部资料时提交 `"use_internal_docs": true`，可同时提交 `"rag_group": "project_a"`。旧 `allow_web_after_rag_hit` 字段被忽略；分组不会隐式启用内部资料。

### 状态与持久化

- 研究状态定义在 `app/graph/state.py`
- 会话数据写入 PostgreSQL
- 检查点优先尝试 Redis，失败后回退到内存
- `research_sessions` 保存任务主记录
- `citations` 保存引用明细
- 审批暂停状态为 `paused`；完整恢复状态写入 `session_runtime_state.state_snapshot_json`，恢复保留原查询、权限与已使用预算。
- `session_id` 只能创建新会话或确认相同的待确认请求；重复执行返回 409，其他用户的会话返回 404。
- 六项执行边界修复及验证范围见 [研究执行边界说明](docs/research-runtime-boundaries.md)。

### SSE 与前端联动

- 后端通过 `app/observability/sse_manager.py` 维护每个 session 的事件队列
- 前端通过 `frontend/src/hooks/useSSE.ts` 订阅 `/api/v1/research/stream/{session_id}`
- `ResearchDashboard` 组合展示 Agent Trace、Tool Trace 和报告内容
- 每个历史/新事件输出前以及空闲等待中重新验证原凭据和会话归属；退出、改密码、撤销令牌后关闭失效连接。

### 配置优先级

运行时配置优先级为：

`前端运行时配置 > 数据库 system_config > 环境变量`

这意味着可以在不改代码的情况下切换 LLM provider 和模型。

## 本地开发

### 环境要求

- Python 3.11+
- Node.js 18+
- PostgreSQL 16 + pgvector
- Redis 7+
- Playwright Chromium

### 后端启动

```bash
.venv\Scripts\activate  # Windows
pip install -r requirements-local.txt
python -m app.db.migrate
uvicorn app.main:app --reload --port 8000
```

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

### Docker 启动

Windows 本机反复出现 `dockerInference` socket 启动 error 时，可用 [`install_docker_safe_start.ps1`](scripts/install_docker_safe_start.ps1) 将桌面、开始菜单及现有任务栏图标接入修复入口，并按 Docker 当前自动启动偏好协调登录项。修复已通过连续两次启动、原报告／证据读取及新事务提交；见[启动修复记录](docs/acceptance/docker-startup-entrypoints-20261021.md)。

```bash
docker compose up -d
```

生产部署前必须从 `.env.example` 创建私有 `.env`，并设置唯一的
`SECURITY_ENCRYPTION_KEY`、`SECURITY_ENVIRONMENT=production`、
`SECURITY_SECURE_COOKIES=true` 和精确的 `API_CORS_ORIGINS`。生产模式会在
启动时拒绝示例密钥、缺失密钥、非安全 Cookie 或 `*` CORS；反向代理的 HTTPS
不替代应用层登录。持久化密钥加密仅保护数据库/备份泄露，不保护已被攻陷的运行进程。

Windows 也可以用：

```powershell
.\start-deepintel.ps1
```

### 本机启动

```powershell
.\start-deepintel.ps1 -Mode local
```

脚本会优先使用项目内 `.venv`，不存在时自动创建并安装依赖。
如果你想直接使用现成的 conda 环境，可以先设置 `DEEPINTEL_PYTHON=C:\Users\wblxr\anaconda3\envs\used_pytorch\python.exe`。

如果只想启动后端：

```powershell
.\start-deepintel.ps1 -Mode local -SkipFrontend
```

## 环境变量

`.env.example` 已包含完整模板，核心项如下：

```env
LLM_PROVIDER=qwen
LLM_MODEL=qwen-plus
LLM_API_KEY=your-api-key
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1

DATABASE_URL=postgresql://deepintel:deepintel_secret@localhost:5433/deepintel
REDIS_URL=redis://localhost:6379/0

RAG_EMBED_MODEL=BAAI/bge-zh-qwen2-int8
RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3
PLAYWRIGHT_HEADLESS=true
API_PORT=8000
FRONTEND_PORT=5173
```

## 开发与调试

- 健康检查：`GET /api/v1/health`
- 就绪检查：`GET /api/v1/ready`
- 研究提交：`POST /api/v1/research`
- 结果查看：`GET /api/v1/research/{session_id}`
- 实时流：`GET /api/v1/research/stream/{session_id}`

建议优先看这几个文件：

- `app/main.py`
- `app/api/research.py`
- `app/graph/compiler.py`
- `app/graph/state.py`
- `frontend/src/components/ResearchDashboard.tsx`

## 学习资料

### 官方文档

- [LangGraph](https://langchain-ai.github.io/langgraph/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [React](https://react.dev/)
- [Vite](https://vite.dev/)
- [Playwright Python](https://playwright.dev/python/)
- [PostgreSQL](https://www.postgresql.org/docs/)
- [Redis](https://redis.io/docs/)
- [pgvector](https://github.com/pgvector/pgvector)

### 代码相关资料

- [SPEC.md](SPEC.md)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [docs/MODEL_DOWNLOAD.md](docs/MODEL_DOWNLOAD.md)
- [docs/INTERVIEW_GUIDE.md](docs/INTERVIEW_GUIDE.md)

## 测试

遵守当前用户约束：本轮仅执行完整真实端到端业务，不运行TDD／单元／回归／冒烟、类型／构建／lint／schema及启动／导入／文件／哈希／文字探针。源码与内容审阅、真实运行及完整交付分别记账；后续具体检查按用户另行明确的范围执行。

OpenMinion任务的真实失败、修复与新增行为证据见[论文读取记录](docs/acceptance/paper-reading-20261018.md)和[综合修复记录](docs/acceptance/sdk-synthesis-recovery-20261018.md)，外部替代响应与真实网络运行分别说明。

## 备注

- 本项目的 README 已按当前仓库代码整理
- 如果后续新增模块，建议同步补充 `README.md` 和 `docs/`
