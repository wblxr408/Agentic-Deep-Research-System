"""
LangGraph StateGraph compiler for the research workflow.

===============================================================
五大核心主题在编译器中的映射
===============================================================

主题 1 - Autonomous Research Workflow:
    - compile_research_graph() 构建完整工作流
    - 从 START → Planner → DAG执行 → Analyst → Reflection → Report → END
    - 整个工作流由 LangGraph 编排，无需人工干预

主题 2 - Research DAG Generation:
    - planner_node 调用 PlannerAgent 生成 DAG
    - dag_node 执行 DAG（按拓扑序执行可并行节点）
    - after_planner 分发 DAG 节点到对应的工具 Agent
    - DAG 执行顺序由 get_executable_order() 计算

主题 3 - Tool-driven Multi-Agent Collaboration:
    - 每个节点执行前/后记录 ToolCallRecord
    - tool_histories 存储每个 Agent 的工具调用历史
    - send_node() 工具调用封装器

主题 4 - Long-running Stateful Agent:
    - PostgresSaver checkpointer 保存状态快照
    - session 字段存储会话元数据
    - revision_count 追踪重规划次数

主题 5 - Self-Reflection & Verification:
    - reflection_node 调用 ReflectionAgent
    - verification_result 决定是否需要重规划
    - 重规划循环最多 3 次

===============================================================
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from langgraph.constants import END, START, Send
from langgraph.graph import StateGraph

from app.graph.state import (
    ResearchState,
    DAGDefinition,
    PlanNode,
    StepStatus,
    TaskStatus,
    AgentType,
    ToolCallRecord,
    ToolInvocationHistory,
    VerificationResult,
    serialize_dag,
    deserialize_dag,
)
from app.config import get_settings


# ==============================================================
# 主题 2 & 3: 工具调用追踪装饰器
# ==============================================================

def track_tool_call(agent_type: AgentType, tool_name: str):
    """
    装饰器：追踪工具调用（主题 3）。

    在节点函数执行时记录 ToolCallRecord，
    方便后续分析和优化工具使用效率。
    """
    def decorator(func):
        async def async_wrapper(state: ResearchState, *args, **kwargs) -> dict:
            call_record = ToolCallRecord(
                agent_type=agent_type,
                tool_name=tool_name,
                args={"task_id": state.get("task_id"), "query": state.get("user_query")},
                status="running",
            )

            # 记录开始
            state.setdefault("tool_histories", [])
            history = ToolInvocationHistory(
                agent_type=agent_type,
                tool_calls=[call_record],
            )
            state["tool_histories"].append(history.model_dump())

            try:
                result = await func(state, *args, **kwargs)
                # Update call result - agent_type stored as string via model_dump()
                agent_str = agent_type.value
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "success"
                    state["tool_histories"][-1]["tool_calls"][-1]["result_summary"] = str(result)[:200]
                return result
            except Exception as e:
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "error"
                    state["tool_histories"][-1]["tool_calls"][-1]["error"] = str(e)
                raise

        def sync_wrapper(state: ResearchState, *args, **kwargs) -> dict:
            call_record = ToolCallRecord(
                agent_type=agent_type,
                tool_name=tool_name,
                args={"task_id": state.get("task_id"), "query": state.get("user_query")},
                status="running",
            )

            state.setdefault("tool_histories", [])
            history = ToolInvocationHistory(
                agent_type=agent_type,
                tool_calls=[call_record],
            )
            state["tool_histories"].append(history.model_dump())
            agent_str = agent_type.value

            try:
                result = func(state, *args, **kwargs)
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "success"
                    state["tool_histories"][-1]["tool_calls"][-1]["result_summary"] = str(result)[:200]
                return result
            except Exception as e:
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "error"
                    state["tool_histories"][-1]["tool_calls"][-1]["error"] = str(e)
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ==============================================================
# 主题 1 & 2: Planner Node - DAG 生成
# ==============================================================

def planner_node(state: ResearchState) -> dict:
    """
    Planner Agent: 将用户查询转换为可执行的 DAG（主题 1 & 2）。

    主题 1: 这是自主研究工作流的起点
    主题 2: Planner 生成研究计划的 DAG 结构

    输入: user_query
    输出: dag（序列化的 DAGDefinition）, agent_trace
    """
    from app.agents.planner import PlannerAgent
    from app.observability.trace import emit_event, EventType

    # 追踪事件
    emit_event(state, EventType.AGENT_START, "planner", f"Planning research for: {state['user_query']}")

    # 调用 Planner Agent 生成 DAG
    agent = PlannerAgent()
    dag: DAGDefinition = agent.create_dag(state["user_query"])

    # 追踪 DAG 生成
    emit_event(
        state, EventType.AGENT_COMPLETE, "planner",
        f"Generated DAG '{dag.dag_name}' with {len(dag.nodes)} nodes, "
        f"execution order: {dag.get_executable_order()}"
    )

    # 更新会话元数据
    session = state.get("session", {})
    session["updated_at"] = datetime.utcnow().isoformat()

    return {
        "dag": serialize_dag(dag),
        "status": TaskStatus.RUNNING.value,
        "session": session,
    }


# ==============================================================
# 主题 1 & 2: DAG 执行 Node - 按拓扑序执行
# ==============================================================

def dag_executor_node(state: ResearchState) -> dict:
    """
    DAG 执行器：按拓扑序分发 DAG 节点（主题 1 & 2）。

    主题 2: 根据 DAG 的节点依赖关系，分发到对应的工具 Agent
    主题 3: 使用 Send API 实现并行执行

    输入: dag（DAGDefinition）
    输出: current_executing_nodes, agent_trace
    """
    from app.observability.trace import emit_event, EventType

    dag = deserialize_dag(state["dag"])
    execution_order = dag.get_executable_order()

    # 当前批次节点
    all_completed = set(state.get("completed_nodes", []))
    current_batch = []

    for batch in execution_order:
        # 找出当前批次中未完成的节点
        for node_id in batch:
            if node_id not in all_completed:
                node = next((n for n in dag.nodes if n.node_id == node_id), None)
                if node and node.status in (StepStatus.PENDING, StepStatus.RUNNING):
                    current_batch.append(node_id)

        if current_batch:
            break

    if not current_batch:
        # 所有节点都已执行完成
        emit_event(state, EventType.AGENT_COMPLETE, "dag_executor", "All DAG nodes completed")
        return {"current_executing_nodes": [], "agent_trace": []}

    emit_event(
        state, EventType.AGENT_START, "dag_executor",
        f"Executing batch: {current_batch} (parallel)"
    )

    return {
        "current_executing_nodes": current_batch,
    }


def dag_results_aggregator(state: ResearchState) -> dict:
    """
    DAG 结果聚合器：收集工具 Agent 的结果，更新 DAG 状态（主题 2）。

    当一批并行节点执行完成后，调用此函数更新 DAG 状态。
    """
    dag = deserialize_dag(state["dag"])
    current_nodes = set(state.get("current_executing_nodes", []))

    # 更新节点状态为 DONE
    for node in dag.nodes:
        if node.node_id in current_nodes:
            node.status = StepStatus.DONE

    completed = list(set(state.get("completed_nodes", [])) | current_nodes)

    return {
        "dag": serialize_dag(dag),
        "completed_nodes": completed,
    }


def should_continue_dag(state: ResearchState) -> str:
    """
    判断 DAG 是否还有未执行的节点（主题 1 & 2）。

    返回:
    - "continue": 还有节点需要执行
    - "analyst": 所有节点都已执行，进入分析阶段
    """
    dag = deserialize_dag(state["dag"])
    completed = set(state.get("completed_nodes", []))
    pending = [n for n in dag.nodes if n.node_id not in completed and n.status != StepStatus.SKIPPED]

    if pending:
        return "continue"
    return "analyst"


# ==============================================================
# 主题 3: 工具 Agent Nodes - Search / Browser / RAG
# ==============================================================

def search_node(state: ResearchState, executing_nodes: list[str]) -> dict:
    """
    Search Agent: 执行搜索工具（主题 3）。

    主题 3: 工具驱动多 Agent
    - 从 DAG 获取当前批次中类型为 search 的节点
    - 执行搜索工具
    - 记录工具调用历史

    输入: dag, current_executing_nodes
    输出: collected_evidence, tool_histories, agent_trace
    """
    from app.agents.search import SearchAgent
    from app.graph.state import Evidence, AgentEvent
    from app.observability.trace import emit_event, EventType

    dag = deserialize_dag(state["dag"])

    # 找出当前批次中分配给 search 的节点
    search_nodes = [
        n for n in dag.nodes
        if n.node_id in executing_nodes and n.node_type == "search"
    ]

    if not search_nodes:
        return {"collected_evidence": [], "tool_histories": [], "agent_trace": []}

    emit_event(state, EventType.AGENT_START, "search", f"Executing {len(search_nodes)} search nodes")

    agent = SearchAgent()
    all_evidence = []

    for node in search_nodes:
        emit_event(state, EventType.TOOL_START, "search", f"Searching: {node.query}")

        # 更新节点状态为 RUNNING
        node.status = StepStatus.RUNNING

        try:
            results = agent.execute_search(node.query)
            node.result = {"results": [r.model_dump() for r in results]}
            node.confidence = 0.9 if results else 0.0

            # 转换为 Evidence
            for r in results:
                evidence = Evidence(
                    content=f"{r.title}: {r.snippet}",
                    source_url=r.url,
                    source_title=r.title,
                    source_type="web",
                    collected_by=AgentType.SEARCH,
                )
                all_evidence.append(evidence)

            emit_event(
                state, EventType.TOOL_COMPLETE, "search",
                f"Found {len(results)} results for: {node.query}"
            )
        except Exception as e:
            node.status = StepStatus.FAILED
            node.retry_count += 1
            emit_event(state, EventType.ERROR, "search", f"Search failed: {str(e)}")

    # 更新 DAG
    dag_serialized = serialize_dag(dag)

    trace = [AgentEvent(
        agent="search",
        event_type="agent_complete",
        content=f"Collected {len(all_evidence)} evidence from search"
    ).model_dump()]

    return {
        "dag": dag_serialized,
        "collected_evidence": [e.model_dump() for e in all_evidence],
        "agent_trace": trace,
    }


def browser_node(state: ResearchState, executing_nodes: list[str]) -> dict:
    """
    Browser Agent: 执行浏览器工具（主题 3）。

    主题 3: 工具驱动多 Agent
    - 从 DAG 获取当前批次中类型为 browser 的节点
    - 执行 Playwright 浏览器工具
    - 支持深度页面提取

    输入: dag, current_executing_nodes
    输出: collected_evidence, tool_histories, agent_trace
    """
    from app.agents.browser import BrowserAgent
    from app.graph.state import Evidence, AgentEvent
    from app.observability.trace import emit_event, EventType

    dag = deserialize_dag(state["dag"])

    browser_nodes = [
        n for n in dag.nodes
        if n.node_id in executing_nodes and n.node_type == "browser"
    ]

    if not browser_nodes:
        return {"collected_evidence": [], "tool_histories": [], "agent_trace": []}

    emit_event(state, EventType.AGENT_START, "browser", f"Executing {len(browser_nodes)} browser nodes")

    agent = BrowserAgent()
    all_evidence = []

    for node in browser_nodes:
        emit_event(state, EventType.TOOL_START, "browser", f"Browsing: {node.query}")

        node.status = StepStatus.RUNNING

        try:
            results = agent.execute_browse(node.query)
            node.result = {"results": [r.model_dump() for r in results]}
            node.confidence = 0.85 if results else 0.0

            for r in results:
                evidence = Evidence(
                    content=r.extracted_content,
                    source_url=r.url,
                    source_title=r.title,
                    source_type="web",
                    collected_by=AgentType.BROWSER,
                )
                all_evidence.append(evidence)

            emit_event(
                state, EventType.TOOL_COMPLETE, "browser",
                f"Extracted {len(results)} pages for: {node.query}"
            )
        except Exception as e:
            node.status = StepStatus.FAILED
            node.retry_count += 1
            emit_event(state, EventType.ERROR, "browser", f"Browse failed: {str(e)}")

    dag_serialized = serialize_dag(dag)

    trace = [AgentEvent(
        agent="browser",
        event_type="agent_complete",
        content=f"Collected {len(all_evidence)} evidence from browser"
    ).model_dump()]

    return {
        "dag": dag_serialized,
        "collected_evidence": [e.model_dump() for e in all_evidence],
        "agent_trace": trace,
    }


def rag_node(state: ResearchState, executing_nodes: list[str]) -> dict:
    """
    RAG Agent: 执行混合检索工具（主题 3）。

    主题 3: 工具驱动多 Agent
    - 从 DAG 获取当前批次中类型为 rag 的节点
    - 执行混合检索（Rerank + Citation）
    - 使用 pgvector 向量检索

    输入: dag, current_executing_nodes
    输出: collected_evidence, tool_histories, agent_trace
    """
    from app.agents.rag import RAGAgent
    from app.graph.state import Evidence, AgentEvent
    from app.observability.trace import emit_event, EventType

    dag = deserialize_dag(state["dag"])

    rag_nodes = [
        n for n in dag.nodes
        if n.node_id in executing_nodes and n.node_type == "rag"
    ]

    if not rag_nodes:
        return {"collected_evidence": [], "tool_histories": [], "agent_trace": []}

    emit_event(state, EventType.AGENT_START, "rag", f"Executing {len(rag_nodes)} RAG nodes")

    agent = RAGAgent()
    all_evidence = []

    for node in rag_nodes:
        emit_event(state, EventType.TOOL_START, "rag", f"Retrieving: {node.query}")

        node.status = StepStatus.RUNNING

        try:
            results = agent.execute_retrieval(node.query, state["user_query"])
            node.result = {"results": [r.model_dump() for r in results]}
            node.confidence = 0.88 if results else 0.0

            for r in results:
                evidence = Evidence(
                    content=r.content,
                    source_url=r.metadata.get("url") if r.metadata else None,
                    source_title=r.metadata.get("title") if r.metadata else None,
                    source_type="knowledge_base",
                    collected_by=AgentType.RAG,
                )
                all_evidence.append(evidence)

            emit_event(
                state, EventType.TOOL_COMPLETE, "rag",
                f"Retrieved {len(results)} chunks for: {node.query}"
            )
        except Exception as e:
            node.status = StepStatus.FAILED
            node.retry_count += 1
            emit_event(state, EventType.ERROR, "rag", f"RAG retrieval failed: {str(e)}")

    dag_serialized = serialize_dag(dag)

    trace = [AgentEvent(
        agent="rag",
        event_type="agent_complete",
        content=f"Collected {len(all_evidence)} evidence from RAG"
    ).model_dump()]

    return {
        "dag": dag_serialized,
        "collected_evidence": [e.model_dump() for e in all_evidence],
        "agent_trace": trace,
    }


# ==============================================================
# 主题 1 & 3: 批量执行 - Fan-out / Fan-in
# ==============================================================

def execute_tool_batch(state: ResearchState) -> list[Send]:
    """
    批量执行工具（主题 1 & 3）。

    主题 1: 自主工作流的并行执行
    主题 3: 工具驱动的多 Agent 协作

    从当前批次节点中，根据节点类型分发到对应的工具 Agent。
    返回 Send 列表，实现并行执行。
    """
    executing_nodes = state.get("current_executing_nodes", [])

    if not executing_nodes:
        return []

    dag = deserialize_dag(state["dag"])
    sends = []

    for node_id in executing_nodes:
        node = next((n for n in dag.nodes if n.node_id == node_id), None)
        if not node:
            continue

        # 根据节点类型分发
        if node.node_type in ("search", "browser", "rag"):
            sends.append(Send(node.node_type, {"executing_nodes": [node_id]}))

    return sends


# ==============================================================
# 主题 1 & 5: Analyst / Reflection / Report Nodes
# ==============================================================

def analyst_node(state: ResearchState) -> dict:
    """
    Analyst Agent: 综合证据生成分析（主题 1）。

    主题 1: 自主工作流中的分析阶段
    输入所有收集到的证据，生成结构化分析

    输入: collected_evidence
    输出: analysis, agent_trace
    """
    from app.agents.analyst import AnalystAgent
    from app.graph.state import deserialize_evidence, Evidence, AgentEvent
    from app.observability.trace import emit_event, EventType

    evidence_list = [deserialize_evidence(e) for e in state.get("collected_evidence", [])]

    emit_event(
        state, EventType.AGENT_START, "analyst",
        f"Analyzing {len(evidence_list)} evidence items"
    )

    agent = AnalystAgent()
    analysis_text = agent.analyze(state["user_query"], evidence_list)

    emit_event(state, EventType.AGENT_COMPLETE, "analyst", "Analysis complete")

    trace = [AgentEvent(
        agent="analyst",
        event_type="agent_complete",
        content=f"Generated {len(analysis_text)} chars of analysis from {len(evidence_list)} evidence items"
    ).model_dump()]

    return {
        "analysis": analysis_text,
        "agent_trace": trace,
    }


def reflection_node(state: ResearchState) -> dict:
    """
    Reflection Agent: 自校验与验证（主题 1 & 5）。

    主题 5: Self-Reflection & Verification
    - 校验分析的事实性、一致性、完整性
    - 检测幻觉声明
    - 决定是否需要重规划

    输入: analysis, collected_evidence
    输出: verification, revision_needed, agent_trace
    """
    from app.agents.reflection import ReflectionAgent
    from app.graph.state import deserialize_evidence, Evidence, AgentEvent
    from app.observability.trace import emit_event, EventType

    evidence_list = [deserialize_evidence(e) for e in state.get("collected_evidence", [])]

    emit_event(
        state, EventType.AGENT_START, "reflection",
        f"Validating analysis with {len(evidence_list)} evidence items"
    )

    agent = ReflectionAgent()
    verification: VerificationResult = agent.reflect(
        state["user_query"],
        state["analysis"],
        evidence_list
    )

    # 追踪校验结果
    if verification.needs_revision:
        emit_event(
            state, EventType.AGENT_COMPLETE, "reflection",
            f"Verification failed: confidence={verification.overall_confidence:.2f}, "
            f"hallucination_rate={verification.hallucination_rate:.2%}, "
            f"needs_revision=True"
        )
    else:
        emit_event(
            state, EventType.AGENT_COMPLETE, "reflection",
            f"Verification passed: confidence={verification.overall_confidence:.2f}, "
            f"citation_coverage={verification.citation_coverage:.2%}"
        )

    trace = [AgentEvent(
        agent="reflection",
        event_type="agent_complete",
        content=f"Verification: confidence={verification.overall_confidence:.2f}, "
                f"needs_revision={verification.needs_revision}"
    ).model_dump()]

    return {
        "verification": verification.model_dump(),
        "revision_needed": verification.needs_revision,
        "agent_trace": trace,
    }


def should_revise(state: ResearchState) -> str:
    """
    条件路由：判断是否需要重规划（主题 5）。

    主题 5: 自校验失败 → 重规划循环
    - 检查 verification.needs_revision
    - 检查 revision_count < max_revisions
    """
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("session", {}).get("max_revisions", 3)

    if state.get("revision_needed") and revision_count < max_revisions:
        return "replan"
    return "generate_report"


def replan_node(state: ResearchState) -> dict:
    """
    重规划节点：增加重规划计数，重置 DAG（主题 1 & 5）。

    主题 5: 重新调用 Planner Agent 生成新的 DAG
    主题 1: 自主工作流的迭代循环
    """
    revision_count = state.get("revision_count", 0) + 1

    session = state.get("session", {})
    session["revision_count"] = revision_count
    session["updated_at"] = datetime.utcnow().isoformat()

    # 重置 DAG 执行状态
    dag = deserialize_dag(state["dag"])
    for node in dag.nodes:
        if node.status in (StepStatus.PENDING, StepStatus.FAILED):
            node.status = StepStatus.PENDING

    from app.observability.trace import emit_event, EventType
    emit_event(
        state, EventType.AGENT_START, "replan",
        f"Replanning (attempt {revision_count})"
    )

    return {
        "revision_count": revision_count,
        "session": session,
        "dag": serialize_dag(dag),
        "completed_nodes": [],
        "current_executing_nodes": [],
        "collected_evidence": [],
        "analysis": "",
    }


def report_node(state: ResearchState) -> dict:
    """
    Report Generator: 生成最终报告（主题 1）。

    主题 1: 自主工作流的输出阶段
    - 基于分析、证据、引用生成 Markdown 报告
    - 添加置信度和来源信息

    输入: analysis, collected_evidence, verification
    输出: final_report, status
    """
    from app.agents.report import ReportAgent
    from app.graph.state import deserialize_evidence, AgentEvent
    from app.observability.trace import emit_event, EventType

    evidence_list = [deserialize_evidence(e) for e in state.get("collected_evidence", [])]
    verification = state.get("verification")

    emit_event(state, EventType.AGENT_START, "report", "Generating final report")

    agent = ReportAgent()
    report, citations = agent.generate(
        user_query=state["user_query"],
        analysis=state["analysis"],
        evidence_list=evidence_list,
        verification=verification,
    )

    # 更新会话状态
    session = state.get("session", {})
    session["status"] = TaskStatus.COMPLETED.value
    session["completed_at"] = datetime.utcnow().isoformat()

    emit_event(state, EventType.AGENT_COMPLETE, "report", f"Report generated: {len(report)} chars")

    trace = [AgentEvent(
        agent="report",
        event_type="agent_complete",
        content=f"Report: {len(report)} chars, {len(citations)} citations"
    ).model_dump()]

    return {
        "final_report": report,
        "citations": [c.model_dump() for c in citations],
        "status": TaskStatus.COMPLETED.value,
        "session": session,
        "agent_trace": trace,
    }


# ==============================================================
# 主题 1: Graph 编译
# ==============================================================

def compile_research_graph() -> StateGraph:
    """
    编译并返回完整的研究 StateGraph（主题 1）。

    架构（5 大主题的整合）：

    START → planner (生成 DAG)
           ↓ (主题 2: DAG 生成)
      dag_executor (分发节点批次)
           ↓ (Send API: 主题 1 & 3 并行执行)
      search / browser / rag (工具调用)
           ↓ (主题 2: 结果聚合)
      should_continue_dag (条件路由)
           ↓ continue / analyst
      analyst (综合分析)
           ↓ (主题 5: 自校验)
      reflection (验证)
           ↓ (主题 5: 条件分支)
      replan ← (重规划循环，最多 3 次)
           ↓ generate_report
      report (报告生成)
           ↓
          END
    """
    settings = get_settings()

    # 构建图
    builder = StateGraph(ResearchState)

    # === 节点定义 ===
    builder.add_node("planner", planner_node)
    builder.add_node("dag_executor", dag_executor_node)
    builder.add_node("dag_aggregator", dag_results_aggregator)
    builder.add_node("analyst", analyst_node)
    builder.add_node("reflection", reflection_node)
    builder.add_node("replan", replan_node)
    builder.add_node("report", report_node)

    # 工具节点（通过 Send API 调用）
    builder.add_node("search", search_node)
    builder.add_node("browser", browser_node)
    builder.add_node("rag", rag_node)

    # === 边定义 ===
    # 入口
    builder.add_edge(START, "planner")

    # Planner → DAG 执行器
    builder.add_edge("planner", "dag_executor")

    # DAG 执行器 → 工具节点（并行）
    builder.add_conditional_edges(
        "dag_executor",
        execute_tool_batch,
        ["search", "browser", "rag"],
    )

    # 工具节点 → 结果聚合
    builder.add_edge("search", "dag_aggregator")
    builder.add_edge("browser", "dag_aggregator")
    builder.add_edge("rag", "dag_aggregator")

    # 结果聚合 → 判断是否继续 DAG 或进入分析
    builder.add_conditional_edges(
        "dag_aggregator",
        should_continue_dag,
        {
            "continue": "dag_executor",  # 继续执行下一批节点
            "analyst": "analyst",         # DAG 全部完成，进入分析
        },
    )

    # 分析 → 反思
    builder.add_edge("analyst", "reflection")

    # 反思 → 重规划或报告（条件分支）
    builder.add_conditional_edges(
        "reflection",
        should_revise,
        {
            "replan": "replan",
            "generate_report": "report",
        },
    )

    # 重规划 → DAG 执行器（重新开始）
    builder.add_edge("replan", "dag_executor")

    # 报告 → 结束
    builder.add_edge("report", END)

    # === 检查点配置（主题 4）===
    checkpointer = None

    if settings.redis.url:
        try:
            from langgraph.checkpoint.redis import RedisSaver
            import redis as sync_redis
            r = sync_redis.from_url(settings.redis.url)
            checkpointer = RedisSaver(r)
        except Exception:
            pass

    if not checkpointer:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)
