# Agentic Deep Research System (ADRS)

> 基于 LangGraph 的自主研究 Agent 平台，展示五大核心架构能力。

---

## 五大核心架构主题

本系统以 **5 个核心技术主题** 为架构支柱，每个主题都是独立的工程能力维度：

| # | 主题 | 核心能力 | 面试价值 |
|---|------|---------|---------|
| 1 | **Autonomous Research Workflow** | 用户输入 → 全自动端到端研究，无需人工干预 | 展示 Agent 自主性 |
| 2 | **Research DAG Generation** | 动态生成研究计划 DAG，支持并行与条件分支 | 区别于 LangChain 链式结构 |
| 3 | **Tool-driven Multi-Agent** | 多个专业 Agent 通过工具调用协作，非角色扮演 | 展示工具调用设计 |
| 4 | **Long-running Stateful Agent** | 检查点持久化 + 会话恢复 + 长时间运行 | 区别于单次 API 调用 |
| 5 | **Self-Reflection & Verification** | 反思循环 + 证据校验 + 质量门控 | 展示 Agent 自优化能力 |

---

## 一句话定位

**一个能证明你具备 Agent Engineering 能力的系统。**

不是 CRUD，不是简单的 RAG 演示，而是：
- **五大架构主题**：自主工作流、DAG 生成、工具协作、状态持久化、自校验
- **LangGraph 状态机**：DAG + 循环 + 检查点 + 重规划
- **Browser Agent**：Playwright 自动化网页研究
- **Advanced RAG**：Hybrid Retrieval + Rerank + Citation
- **生产级可观测性**：SSE 流式输出 + Agent Thought Trace

---

## 技术栈

| 组件 | 选型 | 理由 |
|------|------|------|
| Agent Orchestration | **LangGraph** | 状态机编译器，支持 DAG+循环+检查点 |
| LLM（主力） | **Qwen3.6 Plus** | 工具调用最强（48.2% MCPMark），成本极低 |
| LLM（备选） | **DeepSeek V3.2** | 性价比极高 |
| Browser Automation | **Playwright** | 异步原生 + 无障碍快照 |
| Vector DB | **pgvector** | 一个 DB 做所有事 |
| Rerank | **BGE-reranker-v2-m3** | 开源可控，多语言 |
| Backend | **FastAPI + sse-starlette** | SSE 原生支持 |
| Cache | **Redis** | 会话缓存 + 检查点 |

详细技术选型分析见 [SPEC.md](SPEC.md)。

---

## 架构预览

```mermaid
flowchart TB
    UI[React Frontend] --> SSE[SSE Stream]
    SSE --> API[FastAPI]

    subgraph LangGraph["LangGraph Runtime"]
        P[Planner<br/>主题 2: DAG生成]
        DAGExec[DAG Executor<br/>主题 2: 执行调度]
        S[Search Agent<br/>主题 3]
        B[Browser Agent<br/>主题 3]
        R[RAG Agent<br/>主题 3]
        A[Analyst Agent]
        F[Reflection Agent<br/>主题 5: 自校验]
        RP[Report Gen]
    end

    API --> P
    P --> DAGExec

    DAGExec -->|"并行"| S
    DAGExec -->|"并行"| B
    DAGExec -->|"并行"| R

    S --> A
    B --> A
    R --> A

    A --> F
    F -->|"通过"| RP
    F -->|"重规划"| P

    RP --> END[(END)]
```

**五大主题的工程实现**：

- `app/agents/planner.py` → **主题 2**：DAG 生成
- `app/graph/compiler.py` → **主题 1 & 2**：工作流编排 + DAG 执行
- `app/agents/search.py`, `browser.py`, `rag.py` → **主题 3**：工具驱动协作
- `app/graph/state.py` → **主题 4**：检查点状态定义
- `app/agents/reflection.py` → **主题 5**：自校验

---

## 面试价值锚点

| 主题 | 面试问题 | 核心回答 |
|------|---------|---------|
| **LangGraph vs LangChain** | "为什么不用 LangChain？" | 链式 vs 状态机，DAG + 循环 + 检查点 |
| **Research DAG** | "DAG 和固定流程有什么区别？" | 动态生成 + 拓扑序并行 + 条件分支 |
| **Tool-driven** | "Agent 之间怎么协作？" | 工具调用而非角色对话，有明确输入输出 |
| **Stateful Agent** | "怎么实现故障恢复？" | PostgresSaver 检查点 + 会话元数据 |
| **Self-Reflection** | "怎么降低幻觉？" | 五维度校验 + 置信度传播 + 重规划 |

---

## 快速开始

### 环境要求

- Python 3.11+
- PostgreSQL 15+（需启用 pgvector 扩展）
- Redis 6+
- Node.js 18+（前端）

### 1. 安装依赖

```bash
git clone https://github.com/your-username/deepintel.git
cd deepintel
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入 API Key 和数据库连接
```

必需的环境变量：

```env
# LLM 配置
LLM_PROVIDER=qwen
QWEN_API_KEY=sk-xxx
QWEN_MODEL=qwen-plus

# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/deepintel
REDIS_URL=redis://localhost:6379/0

# RAG
EMBED_MODEL=BAAI/bge-zh-qwen2-int8
RERANK_MODEL=BAAI/bge-reranker-v2-m3
```

### 3. 初始化数据库

```bash
createdb deepintel
psql -d deepintel -c "CREATE EXTENSION IF NOT EXISTS vector;"
python -m app.db.migrate
```

### 4. 启动服务

```bash
# 后端
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev
```

### 5. 验证安装

访问 `http://localhost:5173`，输入研究查询：

> "分析 2025 年中国新能源汽车充电桩市场格局"

应该能看到：
- Agent Trace 实时显示各 Agent 的思考过程
- Tool Trace 显示搜索、浏览器、检索调用
- 报告以 Markdown 形式流式生成
- 每个结论附带 Citation 引用

---

## 项目结构

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
│   │   ├── analyst.py           # 分析工具
│   │   ├── reflection.py       # [主题 5] 自校验
│   │   └── report.py           # 报告生成
│   ├── graph/                    # LangGraph 工作流
│   │   ├── state.py            # [主题 4] 状态定义 + 检查点
│   │   ├── compiler.py        # [主题 1 & 2] 工作流 + DAG 执行
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

## 开发路线图

| 阶段 | 周期 | 主题 | 目标 |
|------|------|------|------|
| 第一阶段 | Day 1-7 | 主题 1 & 4 | LangGraph 核心 + 检查点持久化 |
| 第二阶段 | Day 8-14 | 主题 2 | DAG 生成 + 拓扑序执行 |
| 第三阶段 | Day 15-21 | 主题 3 | 工具驱动多 Agent 协作 |
| 第四阶段 | Day 22-28 | 主题 5 | 自校验 + 重规划循环 |
| 第五阶段 | Day 29-35 | 主题 1 | 前端 + 可观测性 + SSE |

---

## 评估指标

每个主题都有独立的度量文件夹（`metrics/`），采集以下指标：

| 主题 | 核心指标 | 目标 |
|------|---------|------|
| **主题 1** | 工作流成功率、端到端时长 P95 | ≥85%, <10min |
| **主题 2** | DAG 生成质量、并行度 | 覆盖率 >90%, >2x |
| **主题 3** | 工具调用成功率、效率 | >90%, >80% |
| **主题 4** | 检查点恢复成功率、会话隔离 | >95%, 零泄露 |
| **主题 5** | 幻觉率、置信度准确性、重规划效率 | <5%, >0.7, ≤3次 |

---

## 参考资料

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [Playwright Python API](https://playwright.dev/python/)
- [pgvector + PostgreSQL 指南](https://supabase.com/docs/guides/ai/vector-columns)
- [BGE Reranker v2 M3](https://huggingface.co/BAAI/bge-reranker-v2-m3)
- [RRF 融合算法论文](https://plg.uwaterloo.ca/~gclark/papers/reciprocal_rank.pdf)

---

## License

MIT
