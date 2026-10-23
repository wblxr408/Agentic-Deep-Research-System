# Agentic Deep Research System — 技术规格文档

2026-10-22当前执行范围见[完整流程基线](COMPLETE_RESEARCH_FLOW.md)：主要流程优先，18模块作为能力目录，高级候选优化后置。`GET /research/{id}`在实际owner鉴权后返回`plan_manifest/plan_history/iteration_control`和`delivery_view`；后者使用冻结报告、引用、统计与审核，不调用模型或工具，保留版本身份、页面/图表、单位与缺口。前端提供预设/复制/自定义顺序、主题、图文阅读、数据表、原文入口、离线HTML/JSON/Markdown及浏览器打印。未支持的Skill/原生格式不静默替换，见[交付ACI](research-delivery.md)。此为源码接入，运行证据单独记录；下列阶段更新为历史快照。

2026-10-22：OPT-07 [查询理解ACI](query-understanding.md)已接入未运行：POST research/understanding只预览，创建复算并用query_preview_id检测变化，未解歧义409，实际owner上下文404，非法配置422。任务保存五类查询、实体/指代、时间/复杂度、目的/深度和声明式交付快照，原主链/恢复/结果沿用；旧待确认请求兼容新增默认字段。完整图像渲染和绘图适配仍由后续模块接续，不等同于新产物已交付。下一OPT-08，全部实施后统一端到端。

2026-10-22，OPT-06 [生命周期与版本](evidence-lifecycle.md)代码／契约已接入、未运行：不可变全文／原位修订、family当前项、任务默认隔离和显式复用、有效期／Tombstone／恢复／显式清理、有界原子批量发布及访问epoch。三通道统计、上下文和综合复核当前范围；旧报告证据不覆盖，事实修订保留关联。原DELETE改为可恢复隐藏。全部实施后统一端到端，当前未迁移，下一OPT-07。

2026-10-21 实现状态补充：7.4–7.8 已在代码接入，尚待全部 TODO 实现后的统一端到端验收。新增[按目的行动卡](organization-actions.md)和[同版本统计／正文指标绑定／图表／导出](organization-statistics.md)；历史29/34为已验收复合任务数。未启动新服务版本或验证，不将代码状态等同于现有运行能力。其他模块继续按OPT-01–18实施。

OPT-01 [接入与版本恢复](task-evidence-ingestion.md)已在代码接入、未验证，使用现有会话JSONB与上传API，增加本人接入账本、明确覆盖的正文版本、文件／目录批次及分组内事务幂等。没有新增索引服务、Agent或后台同步，后续继续OPT-02。

OPT-02 [结构化解析与审核](structured-document-parsing.md)已在代码接入、未验证：TXT／MD／JSON／DOCX／PDF及实际取得HTML保存结构和原位置，扫描PDF可显式启用有界本机OCR；表格值、图像指针、质量与人工结构审核各自标明边界。新依赖／服务尚未应用，继续OPT-03及后续模块，最后统一端到端验收。

OPT-03 [版本块、元数据与引用](versioned-evidence-chunks.md)已在代码接入、未运行。来源保存一次原文和父子范围，上传／批次共用策略；当前owner／分组／状态／解析与分块版本成立才允许父级扩展。字面实体／日期／引用／学科标签与已核事实分别表达，Citation和主张摘录保留任务依据定位；新索引不改旧任务依据。下一OPT-04，主TODO复合验收继续未完成。

OPT-04 [多视图与成本选择](versioned-retrieval-features.md)已接入代码、未运行：有界混合词项／原位置、源内TF／DF／IDF、可选稠密及实际编码身份、时间来源与模态缺口。新上传默认不编码；检索词汇与可选模型分别执行，未知／不兼容向量不混用。行为／学习稀疏／多向量／图文候选有明确未采用状态，BSR保留待定义。下一OPT-05，尚未开始最终统一验收。

OPT-05 [索引代际及当前范围统计](versioned-retrieval-indexes.md)已接入代码、未迁移／运行。Posting、代际／长度、head及幂等操作复用同一PostgreSQL；direct新来源不物化检索小块，显式发布才加入检索。BM25的N／DF来自当前授权已发布范围，FTS独立融合；向量在兼容范围精确计算，不默认建IVF。本人重建／关闭／回滚使用来源及head revision绑定，失败事务不发布，不重写旧报告。下一OPT-06。

> 版本：v2.6 | 现状更新：2026-10-21 | 状态：已交付能力与目标设计分别维护

> **核心思想**：简洁性、透明度、可靠的 ACI。五个技术主题是实现研究能力的工程维度，设计取舍遵循 [ADRS 核心思想](DESIGN_PRINCIPLES.md)。

> 本文保留架构设计和概念示例；当前可用范围以 1.3、[使用说明](organization-research-guide.md)及其真实交付记录为准。示例评分、图示或类名不作为已经完成或质量达标的证据。验证遵守用户只允许端到端能力场景的要求，不执行回归、冒烟或类型／构建／lint 等门禁。

---

> 当前补充（7.3，29/34）：已实现[学科分类与独立版本](organization-taxonomy.md)，材料学新研究及同证据重分类有真实端到端结果；原报告首次口径与后续分类历史分别保存，未覆盖年份不补零。整体 ORG／OPT、关系与深读等能力仍待完成。

## 目录

1. [项目概述](#1-项目概述)
2. [五大核心架构主题](#2-五大核心架构主题)
   - [2.1 Autonomous Research Workflow（自主研究工作流）](#21-autonomous-research-workflow自主研究工作流)
   - [2.2 Research DAG Generation（研究图生成）](#22-research-dag-generation研究图生成)
   - [2.3 Tool-driven Multi-Agent Collaboration（工具驱动多智能体协作）](#23-tool-driven-multi-agent-collaboration工具驱动多智能体协作)
   - [2.4 Long-running Stateful Agent（长生命周期有状态智能体）](#24-long-running-stateful-agent长生命周期有状态智能体)
   - [2.5 Self-Reflection & Verification（自校验与验证）](#25-self-reflection--verification自校验与验证)
3. [技术选型矩阵](#3-技术选型矩阵)
4. [系统详细设计](#4-系统详细设计)
5. [开发路线图](#5-开发路线图)
6. [评估指标体系](#6-评估指标体系)

---

## 1. 项目概述

### 1.1 项目定位

**项目名称**：Agentic Deep Research System（ADRS）

**一句话定位**：一个以简洁设计、透明计划和可靠工具接口完成证据驱动研究的 AI 研究平台，同时展示 Agent Engineering 的工程实现。

**目标用户**：需要研究企业、高校及科研实验室的研究布局、学术活动与潜在合作依据的使用者；工程能力展示是辅助用途。

**设计优先级**：先满足研究任务的实际需要，再决定 DAG、Agent 数量、框架和抽象层。对外呈现计划、执行状态、调整原因和证据；工具接口维护用途、输入输出、权限、超时、错误与重试契约。工具测试遵守当前变更范围和用户禁止回归测试的约束；详细准则以 [ADRS 核心思想](DESIGN_PRINCIPLES.md) 为准。

### 1.2 五大核心能力映射

| 主题 | 核心能力 | 面试价值 |
|------|---------|---------|
| Autonomous Research Workflow | 用户输入 → 有界研究；审批、预算与缺证状态明确呈现 | 展示 Agent 自主性 |
| Research DAG Generation | 动态生成研究计划 DAG，支持循环与条件分支 | 区别于 LangChain 链式结构 |
| Tool-driven Multi-Agent | 多个专业 Agent 通过工具调用协作，非角色扮演 | 展示工具调用设计 |
| Long-running Stateful Agent | 检查点持久化 + 会话恢复 + 长时间运行 | 区别于单次 API 调用 |
| Self-Reflection & Verification | 报告前反思、最终主张审计与待复核状态 | 展示可核查的自检过程 |

### 1.3 功能范围

样本基线已交付：运行 v4 冻结来源、采集方式、检索式与成果类型，工具执行范围与候选流转分别保存。只读／检索及月精度交叠有[真实端到端记录](acceptance/organization-corpus-20261021.md)；[ACI](organization-corpus.md)说明支持、拒绝和未验证分支。日期区间交叠保持待核，受限样本不是现实全集。

研究目的／模块选择已交付：三种目的、推荐模块及非空自定义，独立于权重冻结；可信程序组装所选内容，报告摘要与下载保留选择。见[ACI](organization-analysis-modules.md)及[实际三目的记录](acceptance/organization-purpose-20261021.md)。基础模块段落不等于完整专题数据契约完成，最终主张审计仍可为待复核。

2026-10-21 已接入组织范围／家族、评价适配／分层偏好、正式研究请求和状态、暂停恢复、owner 个人版本、样本归属与去重汇总、界面、不可变快照重排、报告摘要与 Markdown／JSON／离线 HTML 导出。真实 PostgreSQL、独立高校／混合对象及非计算机期刊场景已有专项记录，见[当前能力与使用说明](organization-research-guide.md)。

评价目录仅部分公开样本，其他体系保留授权导入或数据缺口，不自动给本次成果赋指标。候选消歧准确率、完整分类／关系／深读／趋势／行动及图像驱动模板仍未完成；最终正文审计可能需要复核，已有腾讯案例保留同名检索噪声、工具失败和未核主张，不能把 completed 当成质量通过。

**核心范围**
- 有界自主研究工作流：从查询到受预算、审批和证据条件约束的报告
- 动态研究计划生成（支持迭代重规划）
- 工具驱动多智能体协作（Search / Browser / RAG / Analyst / Reflection）
- 既有 PostgreSQL 运行快照与审批恢复；Redis 检查点不可用时有降级，不能泛称所有故障均自动恢复
- 流式输出（SSE + 可核查的研究计划与执行轨迹）
- 报告前 Reflection 和最终 Markdown 主张审计；未核、未检查及人工复核状态明确保留

**当前边界**
- 当前交付未引入微服务拆分或模型训练；图像驱动报告、自定义模板及绘图 Skill 仍按 TODO 推进。

---

## 2. 五大核心架构主题

---

### 2.1 Autonomous Research Workflow（自主研究工作流）

#### 2.1.1 概念定义

**Autonomous Research Workflow** 在本项目中是指：系统根据用户目标规划、取证、分析并交付有来源的报告；审批、缺证、预算耗尽或不可恢复错误可以暂停或产生受限结果，需要用户补充的情况会明确呈现。

这不是简单的链式调用，而是一个**有反馈的闭环系统**：

```
用户查询
    ↓
[输入理解 → 研究规划 → 信息收集 → 分析综合 → 质量校验 → 报告生成]
                                                                ↓
                                                          ┌─通过→ 报告输出
                                                          └─失败→ 研究规划（重规划）
```

#### 2.1.2 端到端流程

| 阶段 | 描述 | 自主决策点 |
|------|------|----------|
| **输入理解** | 解析用户查询，识别研究范围和约束条件 | 判断查询是否清晰 |
| **研究规划** | 生成研究计划，决定信息来源和优先级 | 分配 Agent 类型 |
| **信息收集** | 并行执行搜索、浏览、检索 | 决定搜索深度 |
| **分析综合** | 聚合证据，生成分析 | 识别信息缺口 |
| **质量校验** | Reflection Agent 校验幻觉和完整性 | 决定是否重规划 |
| **报告生成** | 流式输出 Markdown 报告 | 决定报告结构 |

#### 2.1.3 自主性级别

| 级别 | 描述 | 实现要求 |
|------|------|---------|
| L1 | 单次 LLM 调用 | 最基础 |
| L2 | 链式多步调用 | LangChain 水平 |
| L3 | 带条件的分支工作流 | 本系统水平 |
| L4 | 自主决策 + 重规划 | 本系统目标 |
| L5 | 持续学习 + 自我改进 | 未来方向 |

**本系统定位 L4**：Planner Agent 动态生成研究计划，Reflection Agent 判断质量，触发重规划循环。

#### 2.1.4 设计决策

```
问：为什么需要 Planner Agent 而不是固定的流程？
答：因为不同研究主题需要不同的信息收集策略。
   - "2025年AI市场分析" → 需要数据统计 + 报告 + 新闻
   - "量子计算最新进展" → 需要论文 + 学术评论 + 技术博客
   - "某公司财务状况" → 需要财报 + 新闻 + 行业对比
   Planner Agent 根据查询动态决定信息收集路径。
```

---

### 2.2 Research DAG Generation（研究图生成）

#### 2.2.1 概念定义

**Research DAG Generation** 是指：不是硬编码的研究流程，而是由 LLM 驱动的**动态研究图生成**。

核心思想：研究计划本身就是一段可以被执行的代码（状态机），而非静态配置。

```
传统方式（硬编码流程）：
    查询 → [搜索 → 浏览 → 分析] → 报告

本系统方式（动态生成）：
    查询 → Planner Agent 生成研究计划（DAG） → 执行 DAG → 报告
                          ↓
                   ┌─搜索节点 (step-1)
                   ├─浏览节点 (step-2, 依赖 step-1)
                   ├─内部资料检索节点 (step-3, 用户启用后参与)
                   └─分析节点 (依赖 step-1,2,3)
```

#### 2.2.2 DAG 的结构

公开研究默认通过 `search / browser` 联网取证。`rag` 是用户按需启用的内部资料检索工具，资料来自用户手动录入或上传；它补充证据，不是联网前置条件，也不能因命中而跳过搜索和浏览。规划、简单事实查询、模型失败回退及重规划均遵守同一来源策略；未启用时服务端剔除内部检索节点并在执行边界拒绝内部读取。

研究请求使用 `use_internal_docs`（默认 `false`）和 `rag_group`（启用后可选，留空检索当前用户全部资料）。旧 `allow_web_after_rag_hit` 字段被忽略，旧状态缺少新选项时默认关闭内部检索。工具许可、owner 隔离和全链预算继续约束两类取证，命中计数只用于观测。

并行取证共享剩余调用预算，预算不足时优先分配给联网等主取证，内部资料检索使用补充份额；不会因启用可选资料而将唯一剩余调用全部分配给内部检索。

研究计划的 DAG 包含：

1. **节点（Node）**：一个具体的研究步骤
   - 类型：search / browser / rag
   - 查询：具体的搜索词或 URL
   - 状态：pending / running / done / failed
   - 依赖：可指定前置依赖节点

2. **边（Edge）**：节点间的关系
   - 顺序依赖：step-2 必须在 step-1 完成后执行
   - 并行关系：step-2 和 step-3 可以同时执行
   - 条件分支：if 置信度 < 0.7 then 重规划

3. **属性（Attributes）**：
   - 超时时间
   - 重试次数
   - 置信度阈值

#### 2.2.3 DAG 的优势 vs 硬编码流程

| 维度 | 硬编码流程 | 动态 DAG 生成（本系统） |
|------|----------|----------------------|
| 适应性 | 固定流程，不适应复杂主题 | 每个主题生成专属流程 |
| 并行性 | 顺序执行，无法并行 | 自动识别可并行节点 |
| 条件分支 | 需要预判所有情况 | LLM 动态决定分支条件 |
| 可观测性 | 黑盒执行 | DAG 结构清晰可见 |
| 扩展性 | 新流程需要改代码 | 新增 Agent 类型即可 |

#### 2.2.4 DAG 生成示例

以下示例由用户显式启用 `use_internal_docs=true`，并已将相关内部材料录入资料库；默认公开研究没有 `rag` 节点。

```
用户查询："分析 2025 年中国新能源汽车充电桩市场"

Planner Agent 生成的 DAG（JSON）：
{
  "dag_id": "dag-2025-ev-charging",
  "nodes": [
    {
      "node_id": "n1",
      "type": "search",
      "query": "2025年中国充电桩市场规模统计",
      "parallel": true
    },
    {
      "node_id": "n2",
      "type": "search",
      "query": "充电桩行业政策 2024-2025",
      "parallel": true
    },
    {
      "node_id": "n3",
      "type": "browser",
      "query": "工信部充电桩报告",
      "depends_on": ["n1"]
    },
    {
      "node_id": "n4",
      "type": "rag",
      "query": "内部资料中的充电桩技术路线对比",
      "parallel": true
    },
    {
      "node_id": "n5",
      "type": "analyst",
      "depends_on": ["n1", "n2", "n3", "n4"]
    }
  ]
}

执行顺序：
- n1, n2, n4 并行执行（parallel=true）
- n3 等待 n1 完成
- n5 等待 n1, n2, n3, n4 全部完成
```

#### 2.2.5 设计决策

```
问：为什么不使用 LangChain 的 LCEL（链式表达式语言）？
答：LCEL 本质上是链式组合（Chain Composition），适合"输入→处理→输出"的简单流程。
    研究任务需要：
    1. 动态分支（if-then-else）
    2. 并行执行（fan-out/fan-in）
    3. 循环（replan loop）
    4. 状态持久化（checkpoint）
    这些在 DAG 中天然支持，但 LCEL 需要特殊语法。
    LangGraph 的 StateGraph 是 DAG 的编译器，直接建模这些问题。
```

---

### 2.3 Tool-driven Multi-Agent Collaboration（工具驱动多智能体协作）

#### 2.3.1 概念定义

**Tool-driven** vs **Role-based**：

| 模式 | 描述 | 代表框架 | 适用场景 |
|------|------|---------|---------|
| **Role-based** | Agent 被赋予角色（"你是分析师"），通过对话协作 | CrewAI, AutoGen | 快速原型 |
| **Tool-driven** | Agent 是工具的使用者，通过工具调用协作 | 本系统 | 生产系统 |

```
Role-based 方式：
    Analyst Agent: "我作为资深分析师..."
    Search Agent: "我作为搜索专家..."
    协作方式：消息传递，对话协商

Tool-driven 方式：
    Planner Agent: 调用 search(query="...")
                调用 browser(url="...")
                调用 rag(query="...")
    协作方式：工具调用，明确的输入输出
```

#### 2.3.2 Tool Interface 定义

每个工具都有明确的签名和输出规范：

```python
# 工具接口规范
class Tool:
    name: str                    # 工具唯一名称
    description: str             # 工具功能描述
    input_schema: dict           # JSON Schema 输入规范
    output_schema: dict          # JSON Schema 输出规范
    requires_confirmation: bool   # 是否需要用户确认

# 工具调用示例
ToolCall(
    tool="duckduckgo_search",
    args={"query": "2025年中国充电桩市场"},
    result=SearchResult(...),
    duration_ms=245,
    cost_usd=0.001
)
```

#### 2.3.3 Agent 工具集

| Agent | 工具集 | 工具数量 | 调用频率 |
|-------|--------|---------|---------|
| **Planner Agent** | 任务分解工具 | 1 | 每会话 1 次 |
| **Search Agent** | DuckDuckGo搜索、Bing搜索 | 2 | 高 |
| **Browser Agent** | Playwright（浏览、提取、截图） | 3 | 中 |
| **内部资料检索工具（rag）** | 向量检索、BM25检索、混合检索 | 3 | 用户启用后按需调用 |
| **Analyst Agent** | 推理工具（无外部工具） | 0 | 每会话 1-2 次 |
| **Reflection Agent** | 验证工具（无外部工具） | 0 | 每会话 1-2 次 |
| **Report Agent** | 报告生成工具（无外部工具） | 0 | 每会话 1 次 |

#### 2.3.4 工具调用追踪

每次工具调用都记录完整信息：

```python
@dataclass
class ToolCallRecord:
    call_id: str
    tool_name: str
    args: dict
    start_time: datetime
    end_time: datetime
    duration_ms: int
    status: str  # pending / running / success / error / timeout
    result_summary: str
    cost_usd: float
    error_message: str | None
```

前端展示：

```
┌──────────────────────────────────────────────────────┐
│ Tool Trace Timeline                                 │
├──────────────────────────────────────────────────────┤
│ [Search] ✓ duckduckgo_search (245ms)              │
│ [Search] ✓ bing_search (189ms)                    │
│ [Browser] ✓ playwright_extract (2.1s)              │
│ [RAG] ✓ hybrid_retrieval (89ms)                   │
│ [LLM] ✓ qwen_analyze (3.2s)                      │
└──────────────────────────────────────────────────────┘
```

#### 2.3.5 协作模式

**并行 + 汇聚（Fan-out / Fan-in）**：

```
                    ┌─ Search Agent (n1)
                    │
Planner ────────────┼─ Browser Agent (n2)
                    │
                    └─ RAG Agent (n3)
                          │
                          ↓
                    Analyst Agent
```

**顺序依赖**：

```
Browser Agent ──→ (等待) ──→ Analyst Agent ──→ Reflection Agent
                        ↑
                        │
                  (n3 依赖 n1 的结果)
```

#### 2.3.6 设计决策

```
问：为什么不使用 MCP（Model Context Protocol）？
答：MCP 是工具发现和调用的协议标准，适合工具生态。
    本系统使用 LangChain 的 Tool 接口，同时可以暴露为 MCP Server。
    架构上：
    - 内部：LangChain Tool（工具定义和执行）
    - 外部：MCP（工具的跨服务暴露）
    两者是互补关系，不是替代关系。
```

---

### 2.4 Long-running Stateful Agent（长生命周期有状态智能体）

#### 2.4.1 概念定义

**短生命周期 vs 长生命周期**：

| 维度 | 短生命周期 | 长生命周期（本系统） |
|------|------------|---------------------|
| 执行时间 | 秒级 | 分钟到小时级 |
| 状态管理 | 无状态，每次请求独立 | 有状态，跨步骤保持 |
| 故障恢复 | 重试当前请求 | 从检查点恢复 |
| 会话管理 | 无会话 | 多会话隔离 |
| 资源释放 | 立即释放 | 需要显式清理 |

#### 2.4.2 检查点机制

LangGraph 的检查点（Checkpoint）保存状态的完整快照：

```python
# 检查点内容
Checkpoint:
  ├── thread_id: "session-2025-ev-001"
  ├── checkpoint_id: "ckpt-20250512-143022"
  ├── created_at: 2025-05-12T14:30:22Z
  ├── state:
  │     ├── research_plan: [...]
  │     ├── search_results: [...]
  │     ├── browser_results: [...]
  │     ├── aggregated_evidence: [...]
  │     ├── analysis: "..."
  │     └── revision_count: 2
  └── next_node: "reflection"
```

**检查点触发时机**：
- 每个节点执行完成后自动保存
- 条件分支执行前保存
- 长时间等待前保存
- 用户显式保存

#### 2.4.3 会话持久化

PostgreSQL 中的检查点存储：

```sql
-- LangGraph 检查点表（LangGraph 自动管理）
CREATE TABLE checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_id)
);

-- 研究会话元数据（自定义）
CREATE TABLE research_sessions (
    id UUID PRIMARY KEY,
    user_query TEXT NOT NULL,
    status VARCHAR(20),  -- pending / running / completed / failed
    current_checkpoint_id TEXT,
    total_cost_usd NUMERIC(10, 6),
    created_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);
```

#### 2.4.4 故障恢复流程

```
正常执行：
START → Planner → Search → Browser → Analyst → Reflection → Report → END

故障发生在 "Analyst" 节点：
START → Planner → Search → Browser → [Analyst CRASH]
                                          ↑
                                      检查点保存了
                                  Planner → Search → Browser 的结果

恢复后：
完整检查点 → Analyst → ...
                              ↑
                          从此处继续，无需重做
```

当前审批恢复通过 `/api/v1/research/{session_id}/approvals/{approval_id}` 完成：原子保存当前用户的决定，所有待审批项得到决定后，从 PostgreSQL 完整状态建立新的执行段，经 `approval_resume → dag_executor` 继续原 DAG。查询、渠道、内部资料选项、工具许可及已使用预算一起恢复，Planner 不会重做；拒绝的节点跳过。旧版缺失授权上下文的快照返回明确冲突。该入口处理审批暂停，任意故障节点的自动重启不由此接口承诺。

#### 2.4.5 会话隔离

每个研究会话有独立的：
- 状态隔离：`thread_id` 区分会话
- 缓存隔离：Redis key 包含 session_id
- 资源隔离：独立的工作目录
- 成本追踪：每会话独立计费

```python
# 会话隔离配置
config = {
    "configurable": {
        "thread_id": f"{session_id}:{execution_segment_id}",  # 每个执行段独立，避免恢复时列表再次累加
    }
}

# Redis key 隔离
cache_key = f"session:{session_id}:plan"
result = redis.get(cache_key)
```

#### 2.4.6 长生命周期 vs 短生命周期的工程挑战

| 挑战 | 短生命周期方案 | 长生命周期方案（本系统） |
|------|-------------|----------------------|
| 内存管理 | 每次请求独立 | 需要释放中间结果 |
| 上下文膨胀 | 无问题 | 需要摘要压缩 |
| 网络中断 | 重试当前请求 | 从检查点恢复 |
| 服务重启 | 无影响 | 从检查点恢复 |
| 成本控制 | 请求级计费 | 会话级计费 |

**本系统的解决方案**：
- 上下文膨胀：Browser Agent 的三级提取策略（Snippet/Skim/Deep）
- 成本控制：会话级成本上限，超限自动终止

#### 2.4.7 设计决策

```
问：为什么不使用 Redis Session？
答：Redis Session 只能存储 KV 数据，无法存储 LangGraph 的状态图结构。
    本系统需要：
    1. 状态图的完整快照（检查点）
    2. 状态历史（用于回溯）
    3. 跨节点的状态合并（DAG 执行后的状态聚合）
    这些需要 PostgresSaver，而非 Redis。
    Redis 用于：会话缓存、LLM 响应缓存、队列管理。
```

---

### 2.5 Self-Reflection & Verification（自校验与验证）

#### 2.5.1 概念定义

**Self-Reflection** 是指：Agent 在生成结果后，主动检查结果的质量，发现问题则触发修正。

这不是测试，而是 Agent 系统的**内置质量门控**：

```
传统方式（无校验）：
    生成报告 → 用户发现错误 → 重新生成

本系统方式（有校验）：
    生成报告 → Reflection Agent 校验 → [通过] → 输出
                                ↓
                           [失败] → Planner 重规划 → 重新生成
```

#### 2.5.2 校验维度

| 维度 | 检查内容 | 检测方法 |
|------|---------|---------|
| **事实性** | 声明是否与证据一致 | 证据链交叉验证 |
| **数值准确性** | 数字、日期是否正确 | 精确匹配证据 |
| **时效性** | 数据是否在合理时间范围 | 时间戳校验 |
| **一致性** | 是否存在自相矛盾 | 逻辑冲突检测 |
| **完整性** | 是否覆盖所有研究维度 | 规划覆盖度检查 |
| **引用覆盖率** | 每个声明是否有引用支撑 | Citation 覆盖率 |

#### 2.5.3 反思循环

Reflection Agent 输出结构化结果：

```python
@dataclass
class ReflectionResult:
    total_claims: int           # 总声明数
    verified_claims: int         # 验证通过的声明数
    hallucinated_claims: list[HallucinatedClaim]  # 幻觉声明
    conflicts: list[ClaimConflict]  # 逻辑冲突
    citation_coverage: float     # 引用覆盖率 [0, 1]
    overall_confidence: float   # 整体置信度 [0, 1]
    needs_revision: bool        # 是否需要重规划
    revision_focus: str        # 重规划重点
```

**决策逻辑**：

```
if overall_confidence >= 0.85 AND citation_coverage >= 0.95:
    → 通过，生成报告
elif revision_count < MAX_REVISIONS:
    → 重规划，增加信息收集
else:
    → 达到最大重规划次数，生成报告（带警告）
```

#### 2.5.4 幻觉检测机制

**什么是幻觉**：
- Agent 生成了证据中不存在的信息
- 过度推断：从弱证据得出强结论
- 时间错误：引用过时数据

**检测方法**：

```python
# 每个声明的校验流程
for claim in analysis.claims:
    evidence = find_evidence(claim.key_facts)
    
    if not evidence:
        # 无证据支撑 → 标记为幻觉
        flag_hallucination(claim, "no_evidence")
    elif claim.date < evidence.date - timedelta(days=730):
        # 数据超过 2 年 → 标记为过时
        flag_outdated(claim, evidence.date)
    elif claim.magnitude > evidence.magnitude * 1.5:
        # 数量级差异过大 → 标记为可疑
        flag_suspicious(claim, "magnitude_mismatch")
    else:
        # 通过验证
        verify(claim, evidence)
```

#### 2.5.5 多轮反思

反思可以多轮进行，每轮聚焦不同维度：

```
第 1 轮反思：
  - 检查事实准确性
  - 标记：2 个幻觉声明

重规划（第 1 次）：
  - 针对幻觉声明，增加证据收集
  - 重新执行信息收集

第 2 轮反思：
  - 检查逻辑一致性
  - 标记：1 个逻辑冲突

重规划（第 2 次）：
  - 针对逻辑冲突，补充对比分析

第 3 轮反思：
  - 检查完整性
  - 通过

生成报告
```

**最大重规划次数：3 次**（防止无限循环）

#### 2.5.6 置信度传播

以下是未标定的设计示意及界面草案，不是当前报告准确率、已实现的端到端置信度计算或实测 82%／96%／2%。当前主张审核直接保留 supported／未支持／未检查及 needs_review，不以该示意代替实际证据。

置信度从证据 → 声明 → 结论逐层传播：

```
证据置信度 (0.9)
    ↓
声明置信度 = min(证据置信度) * 一致性系数
    ↓
分析置信度 = min(所有声明置信度)
    ↓
报告置信度 = 分析置信度 * 引用覆盖率
```

前端展示：

```
┌─────────────────────────────────────────┐
│ 质量评估                                    │
├─────────────────────────────────────────┤
│ 报告置信度：82%                           │
│ 引用覆盖率：96% (48/50 claims)           │
│ 幻觉率：2% (1/50 claims)                │
│ 逻辑冲突：0                              │
├─────────────────────────────────────────┤
│ ⚠️ 低置信声明 (1)                         │
│   "预计 2026 年市场份额达 45%"            │
│   来源于单一年份预测模型                   │
│   建议结合多家机构预测综合判断              │
└─────────────────────────────────────────┘
```

#### 2.5.7 设计决策

```
问：为什么不只用 RAGAS，而还要保留 Reflection Agent？
答：两者解决的是不同层的问题。
    1. RAGAS 适合离线评估，用来跑基准集，衡量检索层和生成层的整体质量。
    2. Reflection Agent 适合在线运行时校验，用来决定当前会话是否需要重规划。
    3. 前者回答“系统总体表现怎样”，后者回答“这次执行要不要拦下来重做”。
    所以这里不是二选一，而是离线评估用 RAGAS / Hit@K / MRR，
    在线治理继续用 Reflection 的 citation_coverage / overall_confidence / needs_revision。
```

---

## 3. 技术选型矩阵

### 3.1 Agent Orchestration Framework

| 维度 | LangGraph | LangChain | AutoGen | CrewAI |
|------|-----------|-----------|---------|--------|
| **架构模型** | 状态机编译器 | 链式集成层 | 对话式 Agent | 角色扮演团队 |
| **DAG + 循环** | ✅ 原生 | ❌ 链式难以表达 | ⚠️ 有限 | ❌ 无 |
| **检查点持久化** | ✅ PostgresSaver | ✅ Memory | ✅ 有限 | ❌ 无 |
| **条件分支** | ✅ 确定性路由 | ⚠️ 受限 | ⚠️ 消息驱动 | ⚠️ 有限 |
| **流式输出** | ✅ 原生 | ✅ 支持 | ✅ 支持 | ✅ 支持 |
| **面试价值** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| **生产成熟度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |

**最终选择：LangGraph ✅**

---

### 3.2 LLM 选型

| 维度 | Qwen3.6 Plus | DeepSeek V3.2 | GPT-5.4 | Claude Opus 4.6 |
|------|-------------|--------------|---------|-----------------|
| **工具调用** | ⭐⭐⭐⭐⭐ (48.2% MCPMark) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **中文能力** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **成本** | $0.29/1M | $0.28/1M | $15/1M | $5/1M |
| **综合推荐** | **首选** | 备选 | 不推荐 | 备选 |

**最终选择：Qwen3.6 Plus（主力）+ DeepSeek V3.2（备选）✅**

---

### 3.3 Browser Automation - Browser Use 5-Capability Pipeline

> **面试亮点**: Browser Use = AI Agent 最热门方向之一（对标 Operator / Manus / Computer Use）

```
┌──────────────────────────────────────────────────────────────┐
│  Browser Use = AI Agent 最热门方向之一                         │
│                                                              │
│  本系统实现了完整的 5 步 Browser Use 范式：                     │
│                                                              │
│  1. OPEN     - 自主打开任意 URL                               │
│  2. SCROLL   - 智能滚动加载动态内容                           │
│  3. EXTRACT  - 提取结构化数据                                │
│  4. ANALYZE  - AI 理解页面内容                               │
│  5. NAVIGATE - 链式页面导航                                  │
└──────────────────────────────────────────────────────────────┘
```

| 维度 | Playwright | Puppeteer | Selenium |
|------|-----------|-----------|----------|
| **API 模型** | Async 原生 | Async 原生 | Sync（需包装） |
| **Auto-wait** | ✅ 内置 | ⚠️ 需手动 | ❌ 需显式等待 |
| **无障碍快照** | ✅ | ❌ | ❌ |
| **面试热度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| **5 步能力** | ✅ 全支持 | ⚠️ 部分 | ❌ |

#### 3.3.1 Browser Use 5 步详解

**Step 1: OPEN - 自主 URL 导航**
- Query → URL 转换（搜索引擎 / Wikipedia / 知乎）
- 重试机制（最多 2 次）
- 反爬虫检测规避（`--disable-blink-features=AutomationControlled`）

**Step 2: SCROLL - 智能滚动**
- 自动检测页面滚动区域
- 平滑滚动 + 等待内容加载（800ms）
- 自动检测并点击"加载更多"按钮
- 检测页面底部防止无限滚动（最多 10 次）

**Step 3: EXTRACT - 结构化数据提取**
- 三级提取策略：Snippet(1K) → Skim(4K) → Deep(8K)
- 表格提取（`<table>` → 二维数组）
- JSON-LD 提取（`<script type="application/ld+json">`）
- 列表、元数据、外链提取

**Step 4: ANALYZE - AI 理解页面**
- LLM 分析页面内容，制定提取计划
- 判断页面类型（news/article/product/forum/table）
- 提取关键信息 + 决定下一步导航
- 对比 Operator/Manus：直接用 AI 决策，而非硬编码规则

**Step 5: NAVIGATE - 链式导航**
- 从当前页面提取相关外链
- 继续访问子页面，深入研究
- 支持多页面并发浏览

#### 3.3.2 上下文爆炸问题解决

| 问题 | 方案 | 收益 |
|------|------|------|
| 长网页 100K tokens | 三级渐进提取 | Token 减少 70-90% |
| 无关内容干扰 | AI 分析后定向提取 | 有效数据密度 +35pp |
| 动态无限滚动 | SmartScroller 底部检测 | 避免死循环 |

**最终选择：Playwright + 5-Capability Browser Use ✅**

---

### 3.4 Vector DB

| 维度 | pgvector | Qdrant | Chroma |
|------|----------|--------|--------|
| **部署复杂度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **混合检索** | ✅ SQL JOIN | ✅ 多步 | ❌ 需外部 |
| **运维成本** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**最终选择：pgvector ✅**

---

### 3.5 技术选型汇总

| 组件 | 选择 | 理由 |
|------|------|------|
| Agent Orchestration | **LangGraph** | 状态机编译器，DAG+循环+检查点 |
| LLM（主力） | **Qwen3.6 Plus** | 工具调用最强，中文优秀，成本低 |
| LLM（备选） | **DeepSeek V3.2** | 性价比极高 |
| Browser | **Playwright** | Async 原生 + 无障碍快照 |
| Vector DB | **pgvector** | 一个 DB 做所有事 |
| Rerank | **BGE-reranker-v2-m3** | 开源可控，多语言 |
| Backend | **FastAPI + sse-starlette** | SSE 原生 |
| Cache | **Redis** | 会话缓存 + TTL |

---

## 4. 系统详细设计

### 4.1 五大主题的工程实现映射

| 架构主题 | 核心文件 | 关键类/函数 |
|---------|---------|------------|
| **Autonomous Research Workflow** | `app/graph/compiler.py` | `compile_research_graph()`, `run_research_workflow()` |
| **Research DAG Generation** | `app/agents/planner.py` | `PlannerAgent.create_plan()`, DAG 节点生成 |
| **Tool-driven Multi-Agent** | `app/agents/*.py` + `app/tools/*.py` | 各 Agent 的工具调用 + Tool 定义 |
| **Long-running Stateful Agent** | `app/graph/state.py` + `app/db/migrate.py` | `ResearchState`, PostgresSaver 检查点 |
| **Self-Reflection & Verification** | `app/agents/reflection.py` | `ReflectionAgent.reflect()`, `ReflectionResult` |

### 4.2 项目结构

```
deepintel/
├── app/
│   ├── main.py                     # FastAPI 入口
│   ├── config.py                   # 配置管理
│   ├── agents/                     # Agent 实现
│   │   ├── planner.py            # [主题 2] DAG 生成
│   │   ├── search.py             # [主题 3] 搜索工具
│   │   ├── browser.py            # [主题 3] 浏览器工具
│   │   ├── rag.py               # [主题 3] RAG 工具
│   │   ├── analyst.py           # [主题 3] 分析工具
│   │   ├── reflection.py       # [主题 5] 自校验
│   │   └── report.py            # 报告生成
│   ├── graph/                    # LangGraph 工作流
│   │   ├── state.py            # [主题 4] 状态定义 + 检查点
│   │   ├── compiler.py        # [主题 1] 工作流编排
│   │   ├── nodes.py           # 节点定义
│   │   └── edges.py            # 边路由
│   ├── tools/                   # 工具定义
│   │   ├── search_tools.py
│   │   ├── browser_tools.py
│   │   └── retrieval_tools.py
│   ├── rag/                     # RAG 模块
│   │   ├── embedder.py
│   │   ├── retriever.py       # [主题 2] 混合检索
│   │   └── reranker.py
│   ├── db/                      # 数据库
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── migrate.py         # [主题 4] Schema 迁移
│   ├── api/                     # API 层
│   │   ├── research.py        # [主题 1] SSE 流式
│   │   └── health.py
│   └── observability/           # 可观测性
│       ├── sse_manager.py      # [主题 1] SSE 管理
│       └── trace.py
├── metrics/                     # 五大主题各自的度量
│   ├── langgraph_workflow/    # [主题 1] 工作流度量
│   ├── research_dag/           # [主题 2] DAG 度量
│   ├── multi_agent/           # [主题 3] Agent 协作度量
│   ├── stateful_agent/        # [主题 4] 状态持久化度量
│   └── reflection/            # [主题 5] 校验度量
├── tests/                      # 测试
│   ├── agents/
│   ├── graph/
│   └── integration/
├── frontend/                   # 前端
└── SPEC.md
```

---

## 5. 开发路线图

### 阶段一：LangGraph 核心引擎（Day 1-7）
**对应主题**：Autonomous Research Workflow + Long-running Stateful Agent

- LangGraph 环境搭建
- ResearchState 定义 + 检查点配置
- 工作流编排（planner → sub-agents → analyst → reflection → report）
- 会话持久化验证

### 阶段二：Research DAG Generation（Day 8-14）
**对应主题**：Research DAG Generation

- Planner Agent 实现（动态 DAG 生成）
- 节点/边路由函数
- 条件分支实现
- DAG 可视化追踪

### 阶段三：Tool-driven Multi-Agent（Day 15-21）
**对应主题**：Tool-driven Multi-Agent Collaboration

- 各 Agent 工具集实现
- Search / Browser / RAG 工具
- 工具调用追踪
- 并行执行验证

### 阶段四：Self-Reflection（Day 22-28）
**对应主题**：Self-Reflection & Verification

- Reflection Agent 实现
- 幻觉检测机制
- 重规划循环
- 置信度传播

### 阶段五：前端 + 可观测性（Day 29-35）
**对应主题**：Autonomous Research Workflow（展示）

- React 前端
- SSE 实时流
- Agent Trace + Tool Trace 展示
- 报告 Markdown 渲染

---

## 6. 评估指标体系

### 6.1 五大主题各自的度量

| 架构主题 | 核心指标 | 目标 | 采集方法 |
|---------|---------|------|---------|
| **Autonomous Research Workflow** | 工作流成功率 | ≥85% | 完成率统计 |
| | 端到端时长 P95 | <10min | SSE timestamp |
| **Research DAG Generation** | DAG 生成质量 | 覆盖率 >90% | Planner 输出分析 |
| | DAG 执行效率 | 并行度 >2x | 节点执行统计 |
| **Tool-driven Multi-Agent** | 工具调用成功率 | >90% | Tool trace |
| | 工具调用效率 | 有效调用 >80% | 工具结果分析 |
| **Long-running Stateful Agent** | 检查点恢复成功率 | >95% | 故障注入测试 |
| | 会话隔离完整性 | 零数据泄露 | 隔离测试 |
| **Self-Reflection** | 幻觉率 | <5% | Reflection 输出 |
| | 置信度准确性 | 预测 vs 实际 >0.7 | 事后标注对比 |
| | 重规划效率 | ≤3 次达成质量 | 循环计数 |

### 6.2 RAG 分层评估

RAG 评估建议拆成两层，而不是把所有问题都归到最终答案质量。

**第一层：检索层评估**

- `Hit@K`：Top-K 结果里是否命中正确 chunk，回答“找到没”（单 gold doc 场景）。
- `Recall@K`：Top-K 里召回了多少比例的正确 chunk，回答“找全没”（多 gold doc 场景）。
- `MRR`：正确 chunk 排在第几名，回答“多快找到的”。
- `Context Recall`：回答问题所需信息是否被检索结果覆盖完全。
- `Context Precision`：检索结果里相关内容是否排在靠前位置。

这一层主要用于定位 embedding、chunking、多路召回和 rerank 的问题。

**第二层：生成层评估**

- `Faithfulness`：答案是否忠实于检索到的上下文，主要看幻觉。
- `Answer Relevancy`：答案是否真正回答了用户问题，主要看是否跑题。

这一层可结合 RAGAS 一类 LLM-as-a-Judge 框架做离线抽样评估。

**Embedding 选型与按 query 类型分组诊断**

Embedding 选型不能只看 MTEB / C-MTEB 榜单。榜单测的是通用题，企业 RAG 面对的是内部工单、合同、代码库、客服记录这类“公司自己的题”，公开榜单靠前的模型换到内部语料上命中率可能明显回落。因此榜单只做第一轮粗筛（把候选砍到三五个），最终选择必须由业务测试集决定：

- 用 50 条真实 query + 标注 gold doc 作为最小起步集，每条标 1\~3 篇标准资料，跑通后再扩到 200。
- 判断顺序固定为：先看 `Hit@K` / `Recall@K`（找不找得到），再看 `MRR`（排得靠不靠前），最后看失败集中在哪类问题。
- 给每条 query 打类型标签，按类型聚合 `Recall@10`，让弱项一眼可见。重点覆盖五类“麻烦问题”：同义改写、缩写术语、跨语言、数字代码、长 query。
- 失败样例（Hit 为 0）单独 trace 出来，区分是切分不对、模型不认识内部词，还是 gold doc 标错。

工程落地：`RAGEvalExample.query_type` 把类型带进每条样本，`RAGEvaluationCollector` 的 `record_retrieval_eval` 同时记录 `hit` / `recall_at_k` / `reciprocal_rank`，`get_metrics()` 返回 `summary`（整体）、`by_query_type`（分组诊断）与 `failures`（失败 trace）。典型结论是分类型对症下药——缩写与数字代码加 BM25 / 关键词精确兜底，长 query 加 rerank，同义改写先不动——而不是笼统地“换更大的 embedding”。

### 6.3 在线与离线的分工

- 离线评估：`Hit@K`、`Recall@K`、`MRR`、`Context Recall`、`Context Precision`、`Faithfulness`、`Answer Relevancy`（其中检索层指标支持 `by_query_type` 分组与 `failures` trace）
- 在线验收：点击率、转人工率、引用覆盖率、整体置信度、重规划触发率

离线指标负责快速定位问题在哪一层，线上指标负责验证真实用户效果是否改善。

### 6.4 综合评分

| 维度 | 权重 |
|------|------|
| Autonomous Research Workflow | 25% |
| Research DAG Generation | 20% |
| Tool-driven Multi-Agent | 20% |
| Long-running Stateful Agent | 15% |
| Self-Reflection | 20% |

---

*文档版本：v2.6 | 现状更新：2026-10-21 | 核心思想更新：2026-10-15 | 核心思想：简洁性、透明度、可靠 ACI | 工程能力：5 大主题*


2026-10-21 后续实施策略由用户改为“全部实现后再做验证”。7.4 关系时间／地域、7.5 代表成果深读、7.6 演进与条件情景的数据契约、原文定位、既有 Analyst、本人证据只读预览及报告／界面已在代码接入，尚未运行接口、模型、浏览器、构建或其他检查，运行服务仍为之前加载的版本。7.4 的接口缺失基线发生于策略调整前，不作为新实现通过证据。具体状态见 [TODO](OPTIMIZATION_TODO.md)、[关系 ACI](organization-relationships.md)、[深读 ACI](organization-technical-reading.md)、[趋势 ACI](organization-trends.md)。含验收要求的 OpenSpec 任务暂未勾选，已完成复合任务基线保持29/34；继续按顺序实施7.7、7.8及其他ORG／OPT，最后统一端到端验收。
