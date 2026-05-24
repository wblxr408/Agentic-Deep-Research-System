# Agentic Deep Research System 面试拷打文档

> 版本：v1.0 | 适用场景：技术面试深度提问

---

## 目录

1. [技术选型决策](#1-技术选型决策)
2. [架构设计细节](#2-架构设计细节)
3. [核心实现原理](#3-核心实现原理)
4. [性能与优化](#4-性能与优化)
5. [度量指标体系](#5-度量指标体系)
6. [生产级考量](#6-生产级考量)
7. [高难度拷打问题](#7-高难度拷打问题)

---

## 1. 技术选型决策

### 1.1 Agent 框架：为什么选择 LangGraph？

**Q: 为什么不用 LangChain / AutoGen / CrewAI？**

| 维度 | LangGraph | LangChain | AutoGen | CrewAI |
|------|-----------|-----------|---------|--------|
| **架构模型** | 状态机编译器 | 链式集成层 | 对话式 Agent | 角色扮演团队 |
| **DAG + 循环** | ✅ 原生支持 | ❌ 链式难以表达 | ⚠️ 有限 | ❌ 无 |
| **检查点持久化** | ✅ PostgresSaver | ⚠️ Memory | ⚠️ 有限 | ❌ 无 |
| **条件分支** | ✅ 确定性路由 | ⚠️ 受限 | ⚠️ 消息驱动 | ⚠️ 有限 |
| **并行执行** | ✅ Send API | ❌ 需手动 | ⚠️ 需编排 | ❌ 无 |

**核心答案：**

```
研究任务的本质是 DAG（有向无环图），不是 Chain（链）。

LangChain 的 Chain 模型：
  Input → Step1 → Step2 → Step3 → Output
  问题：无法表达并行、条件分支、循环

研究任务的真实结构：
                    ┌─ Search Agent (并行)
  Query → Planner ──┼─ Browser Agent (并行) → Analyst → Reflection
                    └─ RAG Agent (并行)       ↑
                              └──────────────┘ (循环重规划)

LangGraph 的 StateGraph 天然支持：
1. 节点（Node）：Agent 的执行单元
2. 边（Edge）：节点间的依赖关系
3. 条件边（Conditional Edge）：if-then-else 分支
4. Send API：并行分发
5. Checkpointer：状态持久化

这就是为什么选 LangGraph —— 它是"研究工作流的编译器"。
```

**追杀问题：**

**Q: LangGraph 的 StateGraph 和 DAG 有什么区别？StateGraph 支持循环吗？**

```
DAG（有向无环图）：不能有循环
StateGraph：可以有循环（通过条件边实现）

本系统的重规划循环：
  Analyst → Reflection → [需要修订?] → Planner → Search → ...
                                ↓
                           [不需要] → Report → END

这是 StateGraph 的核心优势 —— 它是一个"可循环的状态机"，
而不仅仅是 DAG。循环通过 should_revise() 条件路由实现。
```

---

### 1.2 LLM 选型：为什么是 Qwen3.6 Plus？

**Q: 为什么不用 GPT-4 / Claude？**

| 维度 | Qwen3.6 Plus | GPT-4o | Claude 3.5 |
|------|-------------|--------|------------|
| **工具调用** | ⭐⭐⭐⭐⭐ (48.2% MCPMark) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **中文能力** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **成本** | $0.29/1M tokens | $15/1M tokens | $5/1M tokens |
| **推理能力** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**核心答案：**

```
工具调用能力是 Agent 系统的核心：
- Planner 需要生成结构化 JSON (DAG)
- Search/Browser/RAG Agent 需要解析工具输出
- Reflection Agent 需要输出结构化校验结果

Qwen3.6 Plus 在 MCPMark（工具调用评测）中得分 48.2%，
接近 GPT-4 水平，但成本只有 1/50。

对于研究任务，中文能力也很关键：
- 用户查询可能是中文
- 搜索结果可能是中文网页
- 最终报告需要中文输出

成本考量：
- 一次完整研究约消耗 50K tokens
- GPT-4: $0.75/次
- Qwen3.6: $0.015/次
- 成本差距 50 倍，对于高频使用场景至关重要
```

**追杀问题：**

**Q: 如果 Qwen API 不可用，如何快速切换到备选模型？**

```python
# app/config.py
class LLMConfig:
    provider: Literal["qwen", "deepseek", "openai"] = "qwen"
    
    @property
    def api_base(self) -> str:
        bases = {
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "openai": "https://api.openai.com/v1",
        }
        return bases[self.provider]

# 切换只需修改环境变量
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxx
```

---

### 1.3 浏览器自动化：为什么是 Playwright？

**Q: 为什么不用 Puppeteer / Selenium？**

| 维度 | Playwright | Puppeteer | Selenium |
|------|-----------|-----------|----------|
| **API 模型** | Async 原生 | Async 原生 | Sync（需包装） |
| **Auto-wait** | ✅ 内置 | ⚠️ 需手动 | ❌ 需显式等待 |
| **无障碍快照** | ✅ 支持 | ❌ 不支持 | ❌ 不支持 |
| **多浏览器** | ✅ Chromium/FF/WebKit | ❌ 仅 Chromium | ✅ 全支持 |
| **反检测** | ✅ 内置 | ⚠️ 需配置 | ❌ 需第三方 |

**核心答案：**

```
Browser Use 是当前 AI Agent 最热门方向之一（对标 Operator / Manus）。

本系统实现了完整的 5 步 Browser Use 范式：
1. OPEN   - 自主打开任意 URL
2. SCROLL - 智能滚动加载动态内容
3. EXTRACT - 提取结构化数据
4. ANALYZE - AI 理解页面内容
5. NAVIGATE - 链式页面导航

Playwright 的核心优势：
1. Auto-wait：自动等待元素可交互，避免竞态条件
2. 无障碍快照：accessibility snapshot 用于元素定位
3. 反检测：内置 --disable-blink-features=AutomationControlled
4. 并发控制：浏览器池管理多页面并发

代码示例：
```python
# SmartScroller 智能滚动
async def auto_scroll(self, page: Page) -> dict:
    for i in range(self.max_scrolls):
        # 滚动到底部
        await page.evaluate(
            "window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})"
        )
        await asyncio.sleep(0.8)  # 等待内容加载
        
        # 检测并点击"加载更多"
        more_btn = await self._find_load_more_button(page)
        if more_btn:
            await more_btn.click()
```
```

**追杀问题：**

**Q: 如何处理动态加载页面（无限滚动）？如何避免死循环？**

```python
# SmartScroller 的死循环防护
class SmartScroller:
    max_scrolls: int = 10  # 最大滚动次数限制
    
    async def auto_scroll(self, page: Page) -> dict:
        last_height = 0
        
        for i in range(self.max_scrolls):
            current_height = await page.evaluate("document.body.scrollHeight")
            
            # 检测是否到达底部
            at_bottom = await page.evaluate(
                "(window.innerHeight + window.scrollY) >= document.body.scrollHeight - 100"
            )
            
            if at_bottom and current_height == last_height:
                # 高度不再变化 + 到达底部 → 终止
                break
            
            last_height = current_height

# 三级提取策略控制 token 消耗
class BrowserAgent:
    async def _extract_snippet(self, page, max_chars=1000):
        """Snippet: 仅 meta 标签，~1K chars"""
        
    async def _extract_skim(self, page, max_chars=4000):
        """Skim: 主要段落，~4K chars"""
        
    async def _extract_deep(self, page, max_chars=8000):
        """Deep: 完整内容，~8K chars"""
```

---

### 1.4 向量数据库：为什么是 pgvector？

**Q: 为什么不用 Qdrant / Chroma / Pinecone？**

| 维度 | pgvector | Qdrant | Chroma | Pinecone |
|------|----------|--------|--------|----------|
| **部署复杂度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | SaaS |
| **混合检索** | ✅ SQL JOIN | ✅ 多步 | ❌ 需外部 | ⚠️ 有限 |
| **运维成本** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | $$ |
| **ACID** | ✅ 完整 | ❌ 无 | ❌ 无 | ❌ 无 |

**核心答案：**

```
pgvector 的核心优势：一个数据库做所有事。

传统方案需要：
- PostgreSQL: 存储文档元数据
- Qdrant: 向量检索
- Elasticsearch: 全文搜索
→ 三套系统，数据同步复杂

pgvector 方案：
- 文档存储: documents 表
- 向量检索: pgvector ivfflat 索引
- 全文搜索: PostgreSQL tsvector
- 混合检索: 单条 SQL 完成

混合检索 SQL 示例：
```sql
-- 向量 + BM25 混合检索
WITH vector_results AS (
    SELECT id, content, 
           1 - (embedding <=> query_vector) AS score
    FROM documents
    ORDER BY embedding <=> query_vector
    LIMIT 30
),
bm25_results AS (
    SELECT id, content,
           ts_rank(to_tsvector('chinese', content), query) AS score
    FROM documents
    WHERE to_tsvector('chinese', content) @@ query
    LIMIT 30
)
-- RRF 融合
SELECT id, content, 
       (1/(60 + v_rank)) + (1/(60 + b_rank)) AS rrf_score
FROM ...
```

ACID 事务的重要性：
- 插入文档 + 向量索引更新必须在同一事务
- 检查点保存需要原子性
- Qdrant/Chroma 无法保证
```

---

## 2. 架构设计细节

### 2.1 状态机设计

**Q: ResearchState 的设计思路是什么？为什么用 TypedDict 而不是 Pydantic Model？**

```python
# ResearchState 定义
class ResearchState(TypedDict):
    task_id: str
    user_query: str
    dag: dict | None                    # DAGDefinition
    current_executing_nodes: list[str]
    completed_nodes: list[str]
    tool_histories: Annotated[list[dict], add_messages]
    collected_evidence: Annotated[list[dict], add_messages]
    verification: dict | None
    revision_needed: bool
    revision_count: int
    analysis: str
    final_report: str
    # ...

```

**核心答案：**

```
为什么用 TypedDict：

1. LangGraph 要求：StateGraph 的 state 必须是 TypedDict
2. Annotated 支持：add_messages reducer 实现消息累积
3. 序列化友好：直接 JSON 序列化，用于检查点保存

设计原则：
- 主题 1: task_id, user_query, status（工作流状态）
- 主题 2: dag, current_executing_nodes, completed_nodes（DAG 执行）
- 主题 3: tool_histories, collected_evidence（工具调用）
- 主题 4: session, checkpoint_id（长生命周期）
- 主题 5: verification, revision_needed（自校验）

Annotated[list[dict], add_messages] 的作用：
- 每个节点返回 {"agent_trace": [new_event]}
- add_messages reducer 自动将 new_event 追加到 agent_trace
- 无需手动合并状态
```

---

### 2.2 DAG 生成与执行

**Q: Planner Agent 如何生成 DAG？如何保证 DAG 的正确性（无环、可执行）？**

```python
# DAG 数据结构
class PlanNode(BaseModel):
    node_id: str
    node_type: Literal["search", "browser", "rag", "analyst"]
    query: str
    depends_on: list[str] = []      # 依赖关系
    parallel: bool = True           # 是否可并行
    status: StepStatus = StepStatus.PENDING

class DAGDefinition(BaseModel):
    nodes: list[PlanNode]
    edges: list[PlanEdge]
    
    def get_executable_order(self) -> list[list[str]]:
        """拓扑排序：返回 [[batch1], [batch2], ...]"""
        # Kahn 算法
        in_degree = {n.node_id: len(n.depends_on) for n in self.nodes}
        batches = []
        
        while True:
            # 入度为 0 的节点 = 当前可并行执行
            batch = [n.node_id for n in self.nodes 
                     if in_degree[n.node_id] == 0 and n.node_id not in processed]
            if not batch:
                break
            batches.append(batch)
            
            # 更新入度
            for node_id in batch:
                for edge in self.edges:
                    if edge.from_node == node_id:
                        in_degree[edge.to_node] -= 1
        
        return batches
```

**核心答案：**

```
DAG 正确性保证：

1. 无环检测：
   - 拓扑排序过程中，如果最终 processed 数量 < 节点总数
   - 说明存在环，LLM 生成的 DAG 有问题
   - 此时使用 fallback_dag() 降级

2. 依赖完整性：
   - 每个 node.depends_on 必须指向存在的 node_id
   - _parse_dag() 中会过滤无效依赖

3. 自动补充 Analyst 节点：
   - 如果 LLM 忘记生成 analyst 节点
   - 系统自动追加，depends_on 设置为所有其他节点

执行流程：
1. Planner 生成 DAG (JSON)
2. 解析为 DAGDefinition
3. get_executable_order() 计算执行顺序
4. 按批次执行：[[n1,n2,n3], [n4], [n5]]
5. 同一批次内使用 Send API 并行执行
```

---

### 2.3 工具调用追踪

**Q: 如何追踪每次工具调用？如何计算成本？**

```python
# 工具调用记录
@dataclass
class ToolCallRecord:
    call_id: str
    agent_type: AgentType
    tool_name: str
    args: dict[str, Any]
    started_at: str
    completed_at: str | None
    duration_ms: int | None
    status: Literal["pending", "running", "success", "error", "timeout"]
    result_summary: str | None
    cost_usd: float = 0.0
    tokens_used: int = 0

# 追踪装饰器
def track_tool_call(agent_type: AgentType, tool_name: str):
    def decorator(func):
        async def wrapper(state: ResearchState, *args, **kwargs):
            record = ToolCallRecord(
                agent_type=agent_type,
                tool_name=tool_name,
                args={"query": state.get("user_query")},
                status="running",
            )
            
            start_time = time.time()
            try:
                result = await func(state, *args, **kwargs)
                record.status = "success"
                record.duration_ms = int((time.time() - start_time) * 1000)
                return result
            except Exception as e:
                record.status = "error"
                record.error = str(e)
                raise
            finally:
                state["tool_histories"].append(record)
        return wrapper
    return decorator
```

**成本计算：**

```python
# LLM 成本追踪
class LLMCostTracker:
    PRICING = {
        "qwen-plus": {"input": 0.29/1e6, "output": 1.16/1e6},
        "deepseek-v3": {"input": 0.28/1e6, "output": 1.10/1e6},
        "gpt-4o": {"input": 2.50/1e6, "output": 10.00/1e6},
    }
    
    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = self.PRICING[model]
        return (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])

# 单次研究成本估算
# - Planner: ~2K input + 2K output
# - Search Agent x3: ~3K input + 0 output
# - Browser Agent x2: ~4K input + 0 output
# - Analyst: ~10K input + 3K output
# - Reflection: ~8K input + 1K output
# - Report: ~10K input + 5K output
# 总计: ~40K tokens ≈ $0.01 (Qwen)
```

---

## 3. 核心实现原理

### 3.1 Reflection Agent：幻觉检测

**Q: 如何检测幻觉？检测逻辑是什么？**

```python
# 幻觉检测流程
class ReflectionAgent:
    def reflect(self, user_query: str, analysis: str, evidence_list: list[Evidence]) -> ReflectionResult:
        """
        校验维度：
        1. 事实性 (Factuality): 声明是否与证据一致
        2. 数值准确性 (Numerical): 数字/日期是否正确
        3. 时效性 (Temporal): 数据是否在合理时间范围
        4. 一致性 (Consistency): 是否存在自相矛盾
        5. 完整性 (Completeness): 是否覆盖所有研究维度
        6. 引用覆盖率 (Citation): 每个声明是否有引用支撑
        """
        
        # 构建校验 Prompt
        prompt = f"""
        Research Question: {user_query}
        
        Analysis to Validate:
        {analysis}
        
        Evidence Sources:
        {self._format_evidence(evidence_list)}
        
        Perform a rigorous quality check and return structured JSON.
        """
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        
        result = ReflectionResult.model_validate(json.loads(response.content))
        
        # 决策逻辑
        if result.overall_confidence >= 0.85 and result.citation_coverage >= 0.95:
            result.needs_revision = False
        elif result.hallucination_rate > 0.05:
            result.needs_revision = True
            result.revision_focus = f"Found {len(result.hallucinated_claims)} hallucinated claims"
        
        return result
```

**幻觉检测示例：**

```
Evidence: "2024年中国新能源汽车销量为 950 万辆"

Analysis Claim: "2024年中国新能源汽车销量突破 1200 万辆"
  → 数量级差异过大 (1200/950 = 1.26 > 1.2 threshold)
  → 标记为 hallucinated, severity="high"

Analysis Claim: "预计 2025 年市场份额达 45%"
  → 预测性声明，无确凿证据
  → 标记为 hallucinated, severity="low", suggested_fix="注明为预测"
```

---

### 3.2 RRF 融合检索

**Q: 什么是 RRF (Reciprocal Rank Fusion)？为什么用 RRF？**

```python
# RRF 算法
def reciprocal_rank_fusion(
    result_lists: list[list[tuple[str, float]]],
    k: int = 60
) -> list[tuple[str, float]]:
    """
    RRF 公式: score(d) = Σ 1/(k + rank(d))
    
    为什么用 RRF：
    1. 无需归一化：不同检索系统的分数范围不同，RRF 基于排名
    2. 对异常值鲁棒：单个高分不会主导结果
    3. 实现简单：无需训练参数
    
    示例：
    Vector Search: [doc1, doc2, doc3]
    BM25 Search:   [doc2, doc1, doc4]
    
    RRF Score:
    - doc1: 1/(60+1) + 1/(60+2) = 0.0164 + 0.0161 = 0.0325
    - doc2: 1/(60+2) + 1/(60+1) = 0.0161 + 0.0164 = 0.0325
    - doc3: 1/(60+3) + 0       = 0.0159
    - doc4: 0        + 1/(60+3) = 0.0159
    
    排序后: [doc1, doc2, doc3, doc4]
    """
    scores: dict[str, float] = {}
    
    for result_list in result_lists:
        for rank, (doc_id, _) in enumerate(result_list, start=1):
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
    
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

---

### 3.3 检查点机制

**Q: LangGraph 的 Checkpointer 如何工作？如何实现故障恢复？**

```python
# 检查点配置
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver(connection_string)

# 编译时注入
graph = builder.compile(checkpointer=checkpointer)

# 执行时指定 thread_id（会话隔离）
result = graph.invoke(
    initial_state,
    config={"configurable": {"thread_id": session_id}}
)
```

**检查点内容：**

```json
{
  "thread_id": "session-2025-ev-001",
  "checkpoint_id": "ckpt-20250512-143022",
  "created_at": "2025-05-12T14:30:22Z",
  "state": {
    "dag": {...},
    "completed_nodes": ["n1", "n2"],
    "collected_evidence": [...],
    "analysis": "...",
    "revision_count": 1
  },
  "next_node": "reflection"
}
```

**故障恢复流程：**

```
正常执行：
START → Planner → Search → Browser → [Analyst CRASH]
                                          ↑
                                     检查点已保存

恢复后：
从最新 checkpoint 读取 state → 从 "Analyst" 继续执行
→ 无需重做 Planner/Search/Browser
```

---

## 4. 性能与优化

### 4.1 并行执行优化

**Q: 如何实现多 Agent 并行执行？Send API 如何工作？**

```python
# Send API 并行分发
def execute_tool_batch(state: ResearchState) -> list[Send]:
    """
    LangGraph 的 Send API 实现 Fan-out：
    - 返回多个 Send 对象
    - 每个 Send 触发一个目标节点
    - 目标节点并行执行
    """
    executing_nodes = state.get("current_executing_nodes", [])
    dag = deserialize_dag(state["dag"])
    sends = []
    
    for node_id in executing_nodes:
        node = next(n for n in dag.nodes if n.node_id == node_id)
        
        if node.node_type == "search":
            sends.append(Send("search", {"executing_nodes": [node_id]}))
        elif node.node_type == "browser":
            sends.append(Send("browser", {"executing_nodes": [node_id]}))
        elif node.node_type == "rag":
            sends.append(Send("rag", {"executing_nodes": [node_id]}))
    
    return sends

# 图定义中的条件边
builder.add_conditional_edges(
    "dag_executor",
    execute_tool_batch,        # 返回 [Send("search", ...), Send("browser", ...), ...]
    ["search", "browser", "rag"],  # 可能的目标节点
)
```

**性能对比：**

```
顺序执行：
Search(3s) → Browser(5s) → RAG(2s) = 10s

并行执行：
max(Search(3s), Browser(5s), RAG(2s)) = 5s

加速比：2x
```

---

### 4.2 Token 优化策略

**Q: 如何控制 Token 消耗？**

本项目现在把输出长度做成了显式档位，而不是只靠单个 max_tokens 硬截断：

- `short`：适合简单问题，搜索次数少，证据数少，生成预算最低。
- `medium`：默认档位，兼顾覆盖率和成本。
- `long`：适合复杂问题，放宽搜索、RAG、报告生成预算。

这不是单纯“多给 token”，而是同步限制搜索次数、RAG 召回量、引用数量和报告长度，避免长输出把流程拖慢。

```python
# 三级提取策略
class BrowserAgent:
    async def open_and_browse(self, query: str, extraction_level: str = "skim"):
        """
        Snippet (~1K chars, ~250 tokens):
          - 仅 meta 标签
          - 用于快速判断相关性
        
        Skim (~4K chars, ~1K tokens):
          - 主要段落
          - 用于一般性内容收集
        
        Deep (~8K chars, ~2K tokens):
          - 完整内容
          - 用于深度分析
        """
        content = await {
            "snippet": self._extract_snippet,
            "skim": self._extract_skim,
            "deep": self._extract_deep,
        }[extraction_level](page, max_chars)
        
        return BrowserResult(extracted_content=content)

# RAG 重排序优化
class RAGAgent:
    async def execute_async(self, ...):
        # 1. 初步检索：30 个候选
        candidates = await self._hybrid_search(query, top_k=30)
        
        # 2. Reranker 重排：取 15 个
        reranked = await self.reranker.rerank(query, candidates, top_n=15)
        
        # 3. 只将重排后的结果加入 context
        # Token 节省：30 → 15，减少 50%
```

### 4.2.1 知识库源管理

前端已经补了内部知识库源的 CRUD 和分组管理入口。

- 可以手动新建、修改、删除知识库组。
- 可以向组内上传文档并入库。
- 支持的上传格式：`json`、`md`、`docx`、`pdf`、`txt`。
- 入库流程包含切分、embedding 和向量写入，不是只存原文件。

面试时要明确一点：

- 这套内部 RAG 不是自动帮你“联网查答案”。
- 如果内部知识库没有命中，才走联网搜索。
- 如果命中了内部知识，是否继续联网搜索取决于任务策略和人工判断。

---

### 4.3 数据库优化

**Q: pgvector 索引如何选择？IVFFlat vs HNSW？**

```sql
-- IVFFlat 索引（适合中规模数据）
CREATE INDEX ON documents 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- HNSW 索引（适合大规模数据，高精度）
CREATE INDEX ON documents 
USING hnsw (embedding vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);

-- 选择依据：
-- 数据量 < 100万：IVFFlat（构建快，内存占用低）
-- 数据量 > 100万：HNSW（查询快，精度高）
-- 本系统选择 IVFFlat，因为知识库规模可控
```

---

## 5. 度量指标体系

### 5.1 五大主题核心指标

| 主题 | 核心指标 | 目标值 | 采集方法 |
|------|---------|--------|---------|
| **Autonomous Workflow** | 工作流成功率 | ≥85% | 完成状态统计 |
| | 端到端时长 P95 | <10min | SSE timestamp |
| **Research DAG** | DAG 生成质量 | 覆盖率 >90% | Planner 输出分析 |
| | DAG 执行效率 | 并行度 >2x | 节点执行统计 |
| **Tool-driven Agent** | 工具调用成功率 | >90% | Tool trace |
| | 工具调用效率 | 有效调用 >80% | 结果分析 |
| **Long-running Agent** | 检查点恢复成功率 | >95% | 故障注入测试 |
| | 会话隔离完整性 | 零数据泄露 | 隔离测试 |
| **Self-Reflection** | 幻觉率 | <5% | Reflection 输出 |
| | 置信度准确性 | 预测vs实际 >0.7 | 事后标注对比 |
| | 重规划效率 | ≤3 次达成质量 | 循环计数 |

### 5.2 指标采集实现

```python
# metrics/langgraph_workflow/collector.py
class LangGraphMetricsCollector:
    def record_workflow_start(self, session_id: str, query: str):
        self._workflows[session_id] = {
            "query": query,
            "start_time": time.time(),
            "status": "running",
            "nodes_executed": [],
        }
    
    def record_node_end(self, session_id: str, node_name: str, status: str):
        self._workflows[session_id]["nodes_executed"].append({
            "node": node_name,
            "status": status,
            "duration_ms": ...,
        })
    
    def get_metrics(self) -> dict:
        return {
            "summary": {
                "total_workflows": len(self._workflows),
                "completed": sum(1 for w in self._workflows.values() if w["status"] == "completed"),
                "failed": sum(1 for w in self._workflows.values() if w["status"] == "failed"),
            },
            "node_stats": self._aggregate_node_stats(),
            "latency_p50": self._calculate_percentile(50),
            "latency_p95": self._calculate_percentile(95),
        }
```

---

## 6. 生产级考量

### 6.1 容错设计

**Q: 各环节如何容错？**

```python
# 1. LLM 调用容错
class PlannerAgent:
    def create_dag(self, query: str) -> DAGDefinition:
        try:
            response = self.client.chat.completions.create(...)
            return self._parse_dag(response.content)
        except Exception as e:
            logger.error(f"Planner error: {e}")
            return self._fallback_dag(query)  # 降级为最小 DAG

# 2. 浏览器容错
class BrowserAgent:
    async def _navigate_with_retry(self, page: Page, url: str, retries: int = 2):
        for attempt in range(retries + 1):
            try:
                await page.goto(url, timeout=30000)
                return
            except TimeoutError:
                if attempt < retries:
                    await asyncio.sleep(1)
                else:
                    raise

# 3. RAG 容错
class RAGAgent:
    async def execute_async(self, ...):
        try:
            pool = await self._get_db_pool()
            # ...
        except Exception as e:
            logger.error(f"RAG error: {e}")
            return []  # 返回空结果，不阻塞工作流

# 4. 整体工作流容错
# Reflection 失败时，使用默认结果继续
# Analyst 失败时，生成 fallback 分析
# Report 失败时，生成 fallback 报告
```

---

### 6.2 安全考量

**Q: 如何防止 Prompt Injection？如何保护敏感数据？**

```python
# 1. 输入验证
class ResearchRequest(BaseModel):
    query: str = Field(min_length=5, max_length=500)
    
    @validator('query')
    def sanitize_query(cls, v):
        # 移除潜在危险字符
        if any(kw in v.lower() for kw in ["ignore previous", "system:", "ignore all"]):
            raise ValueError("Invalid query")
        return v.strip()

# 2. 工具调用隔离
# 每个工具调用在独立进程中执行，限制资源
@track_tool_call
def execute_browser_sandbox(query: str) -> BrowserResult:
    # 使用 Docker 容器隔离
    # 限制网络访问白名单
    # 限制文件系统访问
    pass

# 3. 敏感数据处理
# API Key 存储在环境变量，不进入日志
# 用户数据在会话结束后清理
# Redis 使用 TTL 自动过期
```

---

## 7. 高难度拷打问题

### 7.1 架构设计

**Q: 如果研究任务需要 1 小时才能完成，如何保证系统稳定性？**

```
关键挑战：
1. 内存：长时间运行会导致状态膨胀
2. 网络：SSE 连接可能中断
3. 进程：服务重启会导致任务丢失

解决方案：
1. 检查点持久化
   - 每个节点执行后保存状态到 PostgreSQL
   - 服务重启后从最新检查点恢复
   
2. 断点续传
   - SSE 断开后，客户端可重新连接
   - 通过 session_id 获取最新状态
   - 继续接收后续事件
   
3. 状态压缩
   - collected_evidence 超过阈值时，调用 LLM 摘要
   - tool_histories 只保留最近 100 条
   - agent_trace 定期归档到文件
   
4. 资源限制
   - 单会话 token 上限
   - 单会话成本上限
   - 超限后优雅终止，返回当前进度
```

**Q: 如何处理 100 个并发研究请求？**

```
1. 无状态设计
   - 后端服务可水平扩展
   - 所有状态存储在 PostgreSQL + Redis
   - 使用 Kubernetes HPA 自动扩缩容

2. 任务队列
   - 研究请求进入 Redis 队列
   - Worker 从队列取任务执行
   - 避免瞬时请求压垮系统

3. 资源隔离
   - 浏览器池：每个 Worker 3 个浏览器实例
   - LLM 限流：每秒最多 10 个请求
   - 数据库连接池：动态调整

4. 降级策略
   - 高负载时，限制并发数
   - 超出容量返回 503 + 预计等待时间
   - 优雅降级到简化模式（减少并行度）
```

---

### 7.2 算法实现

**Q: DAG 执行时，如何处理某个节点失败的情况？**

```python
# 节点失败处理策略
class DAGExecutor:
    def execute_node(self, node: PlanNode) -> NodeResult:
        for attempt in range(node.max_retries):
            try:
                result = self._execute_single(node)
                node.status = StepStatus.DONE
                return result
            except Exception as e:
                node.retry_count += 1
                logger.warning(f"Node {node.node_id} failed (attempt {attempt+1}): {e}")
        
        # 重试耗尽
        node.status = StepStatus.FAILED
        
        # 判断是否影响后续节点
        if self._is_critical_node(node):
            # 关键节点失败 → 整个 DAG 失败
            raise CriticalNodeFailureError(node.node_id)
        else:
            # 非关键节点 → 跳过，继续执行
            node.status = StepStatus.SKIPPED
            return NodeResult(status="skipped", error=str(e))
    
    def _is_critical_node(self, node: PlanNode) -> bool:
        """判断是否为关键节点"""
        # Analyst 节点必须成功
        if node.node_type == "analyst":
            return True
        # 检查是否有其他节点依赖此节点
        dependents = [n for n in self.dag.nodes if node.node_id in n.depends_on]
        return len(dependents) > 0
```

**Q: Reflection Agent 如何避免"过度校验"导致无限循环？**

```python
# 重规划控制
MAX_REVISIONS = 3

def should_revise(state: ResearchState) -> str:
    revision_count = state.get("revision_count", 0)
    needs_revision = state.get("revision_needed", False)
    
    if needs_revision and revision_count < MAX_REVISIONS:
        return "replan"
    
    if revision_count >= MAX_REVISIONS:
        logger.warning("Max revisions reached, forcing report generation")
    
    return "generate_report"

#{}

# Reflection 置信度调整
class ReflectionAgent:
    def reflect(self, ...):
        # 每次重规划后，降低通过阈值
        dynamic_threshold = 0.85 - (revision_count * 0.05)
        
        if result.overall_confidence >= dynamic_threshold:
            result.needs_revision = False
        
        return result
```

---

### 7.3 性能优化

**Q: 如何优化 LLM 调用延迟？**

```python
# 1. 流式输出
async def stream_analysis(self, query: str, evidence: list[Evidence]):
    stream = await self.client.chat.completions.create(
        model=self.model,
        messages=[...],
        stream=True,  # 启用流式
    )
    
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

# 2. 缓存
class LLMCache:
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def get_or_compute(self, prompt: str, compute_fn):
        cache_key = f"llm:{hash(prompt)}"
        cached = await self.redis.get(cache_key)
        
        if cached:
            return json.loads(cached)
        
        result = await compute_fn()
        await self.redis.setex(cache_key, 3600, json.dumps(result))
        return result

# 3. 并行调用
async def execute_parallel(self, queries: list[str]):
    tasks = [self._single_query(q) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if not isinstance(r, Exception)]

# 4. 模型选择
# 简单任务用小模型
if task_complexity == "low":
    model = "qwen-turbo"  # 更快、更便宜
else:
    model = "qwen-plus"   # 更准确
```

**Q: 如何减少 Browser Agent 的内存占用？**

```python
# 1. 浏览器池复用
class BrowserPool:
    def __init__(self, pool_size: int = 3):
        self._pool = asyncio.Queue()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> Browser:
        return await self._pool.get()
    
    async def release(self, browser: Browser):
        await self._pool.put(browser)

# 2. 页面及时关闭
async def open_and_browse(self, url: str):
    page = await browser.new_page()
    try:
        result = await self._extract(page)
        return result
    finally:
        await page.close()  # 必须关闭
        
# 3. 定期清理
async def cleanup_idle_browsers(self):
    while True:
        await asyncio.sleep(60)
        # 关闭空闲超过 5 分钟的浏览器实例
        # 限制最大实例数

# 4. 无头模式 + 禁用非必要资源
