**逐项判断**

1. **自主研究工作流** ：**基本实现，但不算完全**

* 有完整 LangGraph 主流程：**planner -> dag_executor -> search/browser/rag -> analyst -> reflection -> report**，并带重规划分支，见 app/graph/compiler.py (line 753)。
* 但后端启动时数据库初始化失败也不会阻止服务继续启动，这意味着“工作流可用性”并不稳，见 app/main.py (line 49) 和数据库初始化错误来源 app/db/connection.py (line 53)。

1. **Research DAG 生成** ：**已实现主体，但验证不完整**

* Planner 确实会让 LLM 生成 DAG，并有 fallback DAG，见 app/agents/planner.py (line 171) 和 app/agents/planner.py (line 283)。
* **DAGDefinition.get_executable_order()** 也实现了拓扑批次执行，见 app/graph/state.py (line 192)。
* 但测试明显落后于当前图结构，仍在断言 **search -> analyst** 这种旧边，和现实现不一致，见 tests/integration/test_workflow.py (line 213)。这说明“已验证完成”不能成立。

1. **Self-Reflection 校验** ：**部分实现，不完全**

* Reflection Agent 确实存在，也会返回 **citation_coverage / overall_confidence / needs_revision**，见 app/agents/reflection.py (line 104)。
* 但它本质上还是一次 LLM 审核；更大的问题是 **一旦反思失败，默认结果竟然是 **needs_revision=False**** ，等于失败时会“放过”，见 app/agents/reflection.py (line 212)。
* 所以它不是可靠的“校验闭环”，只能算“有校验模块”。

1. **工具驱动多 Agent** ：**有架构，但落地不完整**

* **search / browser / rag** 三类 Agent 都有，DAG 也会按节点类型分发，见 app/graph/compiler.py (line 430) 和 app/agents/search.py (line 23)、app/agents/browser.py (line 1)、app/agents/rag.py (line 21)。
* 但 **track_tool_call()** 只是定义了， **没有真正装饰到这些节点上** ，见 app/graph/compiler.py (line 65)。
* 结果是工具调用可观测性更多靠 **emit_event** 文本事件，而不是完整的结构化 **tool_histories**。

1. **流式输出** ：**未完全实现**

* SSE 通道和前端 **useSSE** 都有，见 app/api/research.py (line 49) 和 app/observability/sse_manager.py (line 67)。
* 但“报告以 Markdown 形式流式生成”这一点 **没有真正打通** ：**report_chunk** 和 **report_citation** 事件只是定义了，项目里没有实际调用，见 app/observability/trace.py (line 163)。
* **report_node** 也是一次性生成完整报告再返回，不是 chunk streaming，见 app/graph/compiler.py (line 697)。

1. **引用溯源** ：**部分实现**

* 报告 Agent 会构造 citation 列表，报告里也要求用 **[citation:N]**，见 app/agents/report.py (line 123) 和 app/agents/report.py (line 171)。
* 前端也会把 **[citation:N]** 渲染成链接，见 frontend/src/components/ReportPreview.tsx (line 50)。
* 但数据库里虽然有独立 **citations** 表， **实际没有写入逻辑** ，只有 **research_sessions.citations** 这个 JSON 字段被保存，见 app/db/migrate.py (line 80) 和 app/api/research.py (line 286)。
* 所以“可点击引用”有了，但“完整溯源链路”没完全落地。

**总评**

* 如果按“有无模块”看：六点 **基本都有代码入口** 。
* 如果按“功能闭环 + 稳定运行 + 已验证”看： **没有完全实现** 。
* 我给的评级是：
  * **自主研究工作流**: 70%
  * **Research DAG 生成**: 75%
  * **Self-Reflection 校验**: 50%
  * **工具驱动多 Agent**: 60%
  * **流式输出**: 35%
  * **引用溯源**: 55%

**当前最明确的 bug / 缺口**

* 之前担心过 **RAG** 向量索引操作符是否写错，但当前代码实际已经使用 **vector_cosine_ops**，见 app/db/connection.py (line 67) 和 app/db/migrate.py (line 50)。这一项不应再作为现存 bug 对外表述。
* **Reflection** 失败时默认 **needs_revision=False**，会导致误判通过，见 app/agents/reflection.py (line 212)。
* **report_chunk** 没有接入真实生成流程，所以“流式报告”名不副实。
* **tool_histories** 追踪框架存在，但没有完整接线。
