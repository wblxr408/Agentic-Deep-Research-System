# 内部资料按需检索验证

验证日期：2026-10-14。变更：[make-internal-retrieval-optional](../openspec/changes/make-internal-retrieval-optional/proposal.md)。

公开研究默认联网。内部资料由 `use_internal_docs=true` 显式启用，`rag_group` 限定当前用户的资料范围。检索命中不决定联网状态；规划、事实查询、模型回退、重规划、Send 子任务及恢复调用均采用此契约。

## 行为证据

| 契约 | 观察到的原行为 | 完成后的验证 |
|---|---|---|
| 默认公开研究 | 原实现先分发 RAG，联网等待 | web-only、模型错误生成 RAG、仅 RAG 计划均分发公开搜索 |
| 显式内部资料 | 原实现强制串联 RAG 与联网 | opt-in 后两类取证同时可调度，私有检索收到正确 owner/group |
| 命中与空结果 | 原实现命中后跳过搜索与浏览 | 两种结果均保留待执行联网节点；旧策略字段不控制执行 |
| 许可边界 | 原执行入口未检查资料选择 | 未选择时不读取私有资料；技能许可不能替代用户开关，开关也不能扩大技能许可 |
| 恢复和重规划 | 原路径继续内部优先 | checkpoint/工作流接收新选项，旧状态缺省关闭，批准恢复及重规划保持来源选择 |
| 证据合并 | 旧顺序使两类证据难以同时取得 | 实际 LangGraph fan-out 接收公开与内部结果并合并；内部内容不被拼入公开搜索参数 |
| 单次剩余预算 | 调整过程发现内部检索可抢占唯一额度，断言缺少 web 证据 | 先分配主取证份额；额度为 1 时仅公开取证，额度为 2 时可合并两类证据 |
| 前端选择 | 原请求没有新选项 | 默认 false，启用后可编辑分组，关闭后分组禁用且请求提交 null，保留渠道选择 |

初始 RED：后端新增 17 个用例中 16 个预期行为断言失败、1 个合法私有路径通过；前端 3 个用例均因缺少新请求选项/控件失败。实现后新增行为用例通过；稀缺预算另行观察到缺少公开证据的失败断言后修正。

## 回归结果

最终后端选择 190 个用例，189 个在同次运行通过；既有渠道子进程回收用例 `test_timeout_reclaims_descendant_even_after_its_parent_has_exited` 在与前端构建并行期间，子进程未在 0.7 秒内完成连接，失败于测试前提。该用例此前通过，独立重跑后通过，未修改渠道执行器或放宽其断言；负载相关时序不稳定仍属于该既有测试的限制。

后端回归命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/graph tests/agents/test_agents.py tests/channels tests/api/test_research_sources.py tests/skills/test_skills.py tests/security/test_llm_resilience.py tests/rag/test_rag.py::TestHybridRetriever tests/rag/test_rag.py::test_knowledge_base_tool_refuses_unscoped_retrieval tests/rag/test_rag.py::test_rag_agent_refuses_unscoped_retrieval_without_initializing_dependencies tests/integration/test_workflow.py::TestResearchResultNormalization tests/integration/test_workflow.py::TestSSEIntegration tests/integration/test_workflow.py::TestAPIEndpoints -k 'not import and not compile_research_graph and not graph_has_required_nodes and not research_state_has_required_keys and not plan_step_defaults and not plan_step_serialization and not create_initial_state and not default_result and not health_endpoint and not research_status_model' -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/channels/test_channels.py::test_timeout_reclaims_descendant_even_after_its_parent_has_exited -q --tb=short
```

前端 `npm.cmd test`：7 个用户交互用例通过。最终 `npm.cmd run build` 与 `npm.cmd run lint` 通过；构建保留既有大 bundle 提示，后端保留 LangGraph 依赖的反序列化缺省策略弃用提示。

`openspec.cmd validate make-internal-retrieval-optional --strict` 通过。已人工审阅 README、技术规格、面试讲解、渠道、部署和模型文档与实际请求/路由的一致性。

最终回归排除 16 个 import、初始化/编译探针、静态状态字段/默认值、健康端点及单纯模型形态测试，没有以全仓 `pytest` 命令通过作为结论。一次较早的广泛回归误纳入了两个 SQL 形态断言用例（`tests/security/test_owner_scoping.py`）；它们未纳入最终功能回归命令或隔离证据。向量/BM25 owner 过滤沿用原实现，本次证明 owner/group 传递和缺少 owner 时拒绝，没有新增真实多用户数据库隔离实验。

联网、检索与规划模型的外部边界使用受控替身；本次未运行真实联网/真实模型的端到端研究，也没有据此声称报告质量或实际耗时提升。前端交互通过 jsdom 验证请求效果，没有执行原生浏览器视觉验收。

## 安全基线应用

引用 [设计中的完整基线评估](../openspec/changes/make-internal-retrieval-optional/design.md#baseline-application)。以下均为 A2ABreak 基线 v1.0 的“工程解决方案”“验收办法”在本地边界的应用，并非完整 A2A 修复声明。

- A2AB-03 / 上下文归属与跨租户隔离：验证可信 owner 经 API、恢复、Send 到内部检索的传递，以及未选择/缺少 owner 的拒绝。没有扩大成跨租户数据库验证。
- A2AB-08 / 结构化授权请求与权限不放大：资料选择与技能/工具许可交集在服务端执行；旧字段、分组和模型生成节点不能启用私有读取，合法启用仍可完成。
- A2AB-10 / 委派环路检测与全链预算：沿用调用预算及并行份额，验证额度耗尽、单次额度优先公开取证和合法并行证据合并。

## 工程记忆待捕获

本次形成的项目结论是：公开研究默认联网，内部资料必须显式启用；检索片段数量不能代表覆盖度；并行预算应优先满足主取证。Basic Memory MCP 及只读回退在本任务连接失败，无法完成去重和保存验证。这些结论暂保留在本地设计与验证记录，标记待捕获，不声称已写入索引。
