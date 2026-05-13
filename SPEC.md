# Agentic Deep Research System — 技术规格文档

> 版本：v2.0 | 日期：2026-05-12 | 状态：设计完成，待实现

> **架构核心**：本系统以 5 个核心技术主题为架构支柱，每个主题都是独立的工程能力维度，共同构成完整的 Agent 系统。

---

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

**一句话定位**：一个展示 **Agent Engineering** 核心能力（自主工作流、自动 DAG 生成、工具协作、状态持久化、自校验验证）的生产级 AI 研究平台。

**目标用户**：希望展示 AI Agent 系统设计能力的技术候选人。

### 1.2 五大核心能力映射

| 主题 | 核心能力 | 面试价值 |
|------|---------|---------|
| Autonomous Research Workflow | 用户输入 → 全自动端到端研究，无需人工干预 | 展示 Agent 自主性 |
| Research DAG Generation | 动态生成研究计划 DAG，支持循环与条件分支 | 区别于 LangChain 链式结构 |
| Tool-driven Multi-Agent | 多个专业 Agent 通过工具调用协作，非角色扮演 | 展示工具调用设计 |
| Long-running Stateful Agent | 检查点持久化 + 会话恢复 + 长时间运行 | 区别于单次 API 调用 |
| Self-Reflection & Verification | 反思循环 + 证据校验 + 质量门控 | 展示 Agent 自优化能力 |

### 1.3 功能范围

**核心范围**
- 自主研究工作流：从查询到报告的完全自动化
- 动态研究计划生成（支持迭代重规划）
- 工具驱动多智能体协作（Search / Browser / RAG / Analyst / Reflection）
- 检查点持久化（PostgresSaver + Redis）
- 流式输出（SSE + 实时 Thought Trace）
- 自校验与幻觉检测（Reflection Loop）

**不做**
- 微服务拆分、复杂前端、模型训练

---

## 2. 五大核心架构主题

---

### 2.1 Autonomous Research Workflow（自主研究工作流）

#### 2.1.1 概念定义

**Autonomous Research Workflow** 是指：用户输入一个研究查询后，整个研究过程完全由 Agent 系统自主完成，无需人工介入，最终输出结构化报告。

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
                   ├─检索节点 (step-3, 与 step-2 并行)
                   └─分析节点 (依赖 step-1,2,3)
```

#### 2.2.2 DAG 的结构

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
      "query": "充电桩技术路线对比",
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
| **RAG Agent** | 向量检索、BM25检索、混合检索 | 3 | 中 |
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
START → Planner → [检查点恢复] → Analyst → ...
                              ↑
                          从此处继续，无需重做
```

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
        "thread_id": session_id,  # 会话隔离
        "checkpoint_id": None,      # 从最新检查点恢复
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
问：为什么不使用 RAGAS 或其他评估框架？
答：RAGAS 是事后评估框架，用于评估已生成的 RAG 系统。
    本系统需要：
    1. 实时校验（在生成过程中）
    2. 可干预（校验失败 → 重规划）
    3. 可解释（每个声明的置信度来源）
    这些需要内置的 Reflection Agent，而非外部评估。
    Reflection Agent 本质上是"Agent 版本的单元测试"。
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

### 6.2 综合评分

| 维度 | 权重 |
|------|------|
| Autonomous Research Workflow | 25% |
| Research DAG Generation | 20% |
| Tool-driven Multi-Agent | 20% |
| Long-running Stateful Agent | 15% |
| Self-Reflection | 20% |

---

*文档版本：v2.0 | 最后更新：2026-05-12 | 架构核心：5 大主题*
