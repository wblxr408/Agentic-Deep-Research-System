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

import asyncio
from datetime import datetime
import time
from typing import Any

from langgraph.constants import END, START, Send
from langgraph.graph import StateGraph

from app.graph.state import (
    ResearchState,
    DAGDefinition,
    PlanNode,
    PlanEdge,
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
from app.guardrails import (
    build_answer_gate_message,
    build_evidence_gate,
    build_guardrail_decision,
    is_tool_allowed,
    record_guardrail_event,
)

TOOL_NODE_TYPES = {"search", "browser", "rag"}
WEB_NODE_TYPES = {"search", "browser"}


def _enforce_internal_first_dag(dag: DAGDefinition, user_query: str) -> DAGDefinition:
    """Ensure every web retrieval node runs only after internal RAG has been checked."""
    rag_nodes = [node for node in dag.nodes if node.node_type == "rag"]
    if not rag_nodes:
        rag_node = PlanNode(
            node_id="internal_rag_first",
            node_type="rag",
            query=f"内部知识库检索：{user_query}",
            depends_on=[],
            parallel=True,
        )
        dag.nodes.insert(0, rag_node)
        rag_nodes = [rag_node]

    rag_ids = [node.node_id for node in rag_nodes]
    existing_edges = {(edge.from_node, edge.to_node) for edge in dag.edges}
    for node in dag.nodes:
        if node.node_type not in WEB_NODE_TYPES:
            continue
        for rag_id in rag_ids:
            if rag_id == node.node_id or rag_id in node.depends_on:
                continue
            node.depends_on.append(rag_id)
            if (rag_id, node.node_id) not in existing_edges:
                dag.edges.append(PlanEdge(from_node=rag_id, to_node=node.node_id, edge_type="sequential"))
                existing_edges.add((rag_id, node.node_id))

    return dag


def _result_count(node: PlanNode) -> int:
    if not node.result:
        return 0
    results = node.result.get("results")
    return len(results) if isinstance(results, list) else 0


def _skip_pending_web_nodes(dag: DAGDefinition) -> list[str]:
    skipped: list[str] = []
    for node in dag.nodes:
        if node.node_type in WEB_NODE_TYPES and node.status == StepStatus.PENDING:
            node.status = StepStatus.SKIPPED
            skipped.append(node.node_id)
    return skipped


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
            agent_str = agent_type.value
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
                start_time = time.perf_counter()
                result = await func(state, *args, **kwargs)
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "success"
                    state["tool_histories"][-1]["tool_calls"][-1]["completed_at"] = datetime.utcnow().isoformat()
                    state["tool_histories"][-1]["tool_calls"][-1]["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
                    state["tool_histories"][-1]["tool_calls"][-1]["result_summary"] = str(result)[:200]
                return result
            except Exception as e:
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "error"
                    state["tool_histories"][-1]["tool_calls"][-1]["completed_at"] = datetime.utcnow().isoformat()
                    state["tool_histories"][-1]["tool_calls"][-1]["error"] = str(e)
                raise

        def sync_wrapper(state: ResearchState, *args, **kwargs) -> dict:
            agent_str = agent_type.value
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
            try:
                start_time = time.perf_counter()
                result = func(state, *args, **kwargs)
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "success"
                    state["tool_histories"][-1]["tool_calls"][-1]["completed_at"] = datetime.utcnow().isoformat()
                    state["tool_histories"][-1]["tool_calls"][-1]["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
                    state["tool_histories"][-1]["tool_calls"][-1]["result_summary"] = str(result)[:200]
                return result
            except Exception as e:
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "error"
                    state["tool_histories"][-1]["tool_calls"][-1]["completed_at"] = datetime.utcnow().isoformat()
                    state["tool_histories"][-1]["tool_calls"][-1]["error"] = str(e)
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _make_tool_history(
    *,
    agent_type: AgentType,
    tool_name: str,
    task_id: str | None,
    query: str,
) -> dict[str, Any]:
    """Create a structured tool history entry for a single tool invocation."""
    history = ToolInvocationHistory(
        agent_type=agent_type,
        tool_calls=[ToolCallRecord(
            agent_type=agent_type,
            tool_name=tool_name,
            args={
                "task_id": task_id,
                "query": query,
            },
            status="running",
        )],
    )
    return history.model_dump()


def _append_trace_event(
    state: ResearchState,
    event_type: EventType,
    agent: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit both agent trace and SSE-friendly state updates for the UI."""
    from app.graph.state import AgentEvent

    event = AgentEvent(agent=agent, event_type=event_type.value, content=content).model_dump()
    if metadata:
        event.update(metadata)
    state.setdefault("agent_trace", []).append(event)
    return event


def _finish_tool_history(
    history: dict[str, Any],
    *,
    status: str,
    result_summary: str | None = None,
    error: str | None = None,
) -> None:
    """Finalize a structured tool history entry."""
    tool_call = history["tool_calls"][-1]
    tool_call["status"] = status
    tool_call["completed_at"] = datetime.utcnow().isoformat()
    started_at = datetime.fromisoformat(tool_call["started_at"])
    tool_call["duration_ms"] = int((datetime.utcnow() - started_at).total_seconds() * 1000)
    if result_summary is not None:
        tool_call["result_summary"] = result_summary[:200]
    if error is not None:
        tool_call["error"] = error


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
    dag = _enforce_internal_first_dag(dag, state["user_query"])
    decision = build_guardrail_decision(state["user_query"], user_confirmed=state.get("user_confirmed", False))
    record_guardrail_event(
        state,
        agent="planner",
        event_type="guardrail_decision",
        content="planner routed",
        metadata=decision.model_dump(),
    )

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
        "guardrail_decision": decision.model_dump(),
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
                if node and node.node_type in TOOL_NODE_TYPES and node.status in (StepStatus.PENDING, StepStatus.RUNNING):
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
    from app.observability.trace import EventType

    dag = deserialize_dag(state["dag"])
    current_nodes = set(state.get("current_executing_nodes", []))

    # 更新节点状态为 DONE
    for node in dag.nodes:
        if node.node_id in current_nodes:
            node.status = StepStatus.DONE

    completed = list(set(state.get("completed_nodes", [])) | current_nodes)
    retrieval_policy = dict(state.get("retrieval_policy") or {})
    retrieval_policy.setdefault("mode", "internal_first")
    retrieval_policy.setdefault("allow_web_after_rag_hit", bool(state.get("allow_web_after_rag_hit", False)))
    retrieval_policy.setdefault("rag_group", state.get("rag_group"))

    rag_hit_count = sum(
        _result_count(node)
        for node in dag.nodes
        if node.node_type == "rag" and node.status == StepStatus.DONE
    )
    retrieval_policy["rag_hit_count"] = rag_hit_count

    skipped_web_nodes: list[str] = []
    if current_nodes and all(
        (node.node_type == "rag")
        for node in dag.nodes
        if node.node_id in current_nodes
    ):
        if rag_hit_count > 0:
            if retrieval_policy["allow_web_after_rag_hit"]:
                retrieval_policy["web_search_required"] = True
                retrieval_policy["web_search_reason"] = "rag_hit_user_allowed_web"
            else:
                retrieval_policy["web_search_required"] = False
                retrieval_policy["web_search_reason"] = "rag_hit_user_skipped_web"
                skipped_web_nodes = _skip_pending_web_nodes(dag)
                completed = list(set(completed) | set(skipped_web_nodes))
        else:
            retrieval_policy["web_search_required"] = True
            retrieval_policy["web_search_reason"] = "rag_empty_auto_web"

    trace = []
    if skipped_web_nodes:
        trace.append(_append_trace_event(
            state,
            EventType.AGENT_COMPLETE,
            "retrieval_policy",
            f"Internal RAG found {rag_hit_count} chunks; skipped {len(skipped_web_nodes)} web nodes by user policy.",
            {
                "retrieval_policy": retrieval_policy,
                "skipped_web_nodes": skipped_web_nodes,
            },
        ))
    elif current_nodes and any(node.node_type == "rag" for node in dag.nodes if node.node_id in current_nodes):
        trace.append(_append_trace_event(
            state,
            EventType.AGENT_COMPLETE,
            "retrieval_policy",
            f"Internal RAG found {rag_hit_count} chunks; web search policy: {retrieval_policy.get('web_search_reason')}.",
            {"retrieval_policy": retrieval_policy},
        ))

    return {
        "dag": serialize_dag(dag),
        "completed_nodes": completed,
        "retrieval_policy": retrieval_policy,
        "agent_trace": trace,
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
    pending = [
        n for n in dag.nodes
        if n.node_type in TOOL_NODE_TYPES
        and n.node_id not in completed
        and n.status != StepStatus.SKIPPED
    ]

    if pending:
        return "continue"
    return "analyst"


# ==============================================================
# 主题 3: 工具 Agent Nodes - Search / Browser / RAG
# ==============================================================

def search_node(state: ResearchState) -> dict:
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
    from app.guardrails import record_guardrail_event, validate_tool_invocation

    dag = deserialize_dag(state["dag"])
    executing_nodes = state.get("executing_nodes", state.get("current_executing_nodes", []))

    # 找出当前批次中分配给 search 的节点
    search_nodes = [
        n for n in dag.nodes
        if n.node_id in executing_nodes and n.node_type == "search"
    ]

    if not search_nodes:
        return {"collected_evidence": [], "tool_histories": [], "agent_trace": []}

    trace = [
        _append_trace_event(state, EventType.AGENT_START, "search", f"Executing {len(search_nodes)} search nodes")
    ]

    agent = SearchAgent()
    all_evidence = []
    tool_histories = []

    for node in search_nodes:
        trace.append(_append_trace_event(
            state,
            EventType.TOOL_START,
            "search",
            f"Searching: {node.query}",
            {"tool_name": "duckduckgo_search", "args": {"query": node.query}},
        ))
        tool_history = _make_tool_history(
            agent_type=AgentType.SEARCH,
            tool_name="execute_search",
            task_id=state.get("task_id"),
            query=node.query,
        )
        valid, reason = validate_tool_invocation("duckduckgo_search", {"query": node.query})
        if not valid:
            _finish_tool_history(tool_history, status="error", error=reason or "invalid_args")
            record_guardrail_event(
                state,
                agent="search",
                event_type="tool_blocked",
                content=reason or "invalid_args",
                metadata={"tool": "duckduckgo_search", "query": node.query},
            )
            tool_histories.append(tool_history)
            continue
        # 更新节点状态为 RUNNING
        node.status = StepStatus.RUNNING

        try:
            results = agent.execute_search(node.query)
            node.result = {"results": [r.model_dump() for r in results]}
            node.confidence = 0.9 if results else 0.0
            _finish_tool_history(
                tool_history,
                status="success" if results else "error",
                result_summary=f"{len(results)} search results",
                error=None if results else "no_search_results",
            )

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

            trace.append(_append_trace_event(
                state,
                EventType.TOOL_COMPLETE if results else EventType.TOOL_ERROR,
                "search",
                f"Found {len(results)} results for: {node.query}" if results else f"No web search results for: {node.query}",
                {
                    "tool_name": "duckduckgo_search",
                    "status": "success" if results else "error",
                    "result_summary": f"{len(results)} search results",
                    "error": None if results else "no_search_results",
                },
            ))
        except Exception as e:
            node.status = StepStatus.FAILED
            node.retry_count += 1
            trace.append(_append_trace_event(
                state,
                EventType.TOOL_ERROR,
                "search",
                f"Search failed: {str(e)}",
                {"tool_name": "duckduckgo_search", "status": "error", "error": str(e)},
            ))
            _finish_tool_history(tool_history, status="error", error=str(e))
        tool_histories.append(tool_history)

    trace.append(AgentEvent(
        agent="search",
        event_type="agent_complete",
        content=f"Collected {len(all_evidence)} evidence from search"
    ).model_dump())

    return {
        "collected_evidence": [e.model_dump() for e in all_evidence],
        "tool_histories": tool_histories,
        "agent_trace": trace,
    }


def browser_node(state: ResearchState) -> dict:
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
    from app.guardrails import record_guardrail_event, validate_tool_invocation

    dag = deserialize_dag(state["dag"])
    executing_nodes = state.get("executing_nodes", state.get("current_executing_nodes", []))

    browser_nodes = [
        n for n in dag.nodes
        if n.node_id in executing_nodes and n.node_type == "browser"
    ]

    if not browser_nodes:
        return {"collected_evidence": [], "tool_histories": [], "agent_trace": []}

    trace = [
        _append_trace_event(state, EventType.AGENT_START, "browser", f"Executing {len(browser_nodes)} browser nodes")
    ]

    agent = BrowserAgent()
    all_evidence = []
    tool_histories = []

    for node in browser_nodes:
        trace.append(_append_trace_event(
            state,
            EventType.TOOL_START,
            "browser",
            f"Browsing: {node.query}",
            {"tool_name": "browse_webpage", "args": {"query": node.query, "url": node.query}},
        ))
        tool_history = _make_tool_history(
            agent_type=AgentType.BROWSER,
            tool_name="execute_browse",
            task_id=state.get("task_id"),
            query=node.query,
        )
        valid, reason = validate_tool_invocation("browse_webpage", {"url": node.query, "max_chars": 2000})
        if not valid:
            _finish_tool_history(tool_history, status="error", error=reason or "invalid_args")
            record_guardrail_event(
                state,
                agent="browser",
                event_type="tool_blocked",
                content=reason or "invalid_args",
                metadata={"tool": "browse_webpage", "url": node.query},
            )
            tool_histories.append(tool_history)
            continue
        node.status = StepStatus.RUNNING

        try:
            results = agent.execute_browse(node.query)
            node.result = {"results": [r.model_dump() for r in results]}
            node.confidence = 0.85 if results else 0.0
            _finish_tool_history(
                tool_history,
                status="success",
                result_summary=f"{len(results)} browser pages",
            )

            for r in results:
                evidence = Evidence(
                    content=r.extracted_content,
                    source_url=r.url,
                    source_title=r.title,
                    source_type="web",
                    collected_by=AgentType.BROWSER,
                )
                all_evidence.append(evidence)

            trace.append(_append_trace_event(
                state, EventType.TOOL_COMPLETE, "browser",
                f"Extracted {len(results)} pages for: {node.query}",
                {"tool_name": "browse_webpage", "status": "success", "result_summary": f"{len(results)} browser pages"},
            ))
        except Exception as e:
            node.status = StepStatus.FAILED
            node.retry_count += 1
            trace.append(_append_trace_event(
                state,
                EventType.TOOL_ERROR,
                "browser",
                f"Browse failed: {str(e)}",
                {"tool_name": "browse_webpage", "status": "error", "error": str(e)},
            ))
            _finish_tool_history(tool_history, status="error", error=str(e))
        tool_histories.append(tool_history)

    trace.append(AgentEvent(
        agent="browser",
        event_type="agent_complete",
        content=f"Collected {len(all_evidence)} evidence from browser"
    ).model_dump())

    return {
        "collected_evidence": [e.model_dump() for e in all_evidence],
        "tool_histories": tool_histories,
        "agent_trace": trace,
    }


def rag_node(state: ResearchState) -> dict:
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
    from app.guardrails import record_guardrail_event, validate_tool_invocation

    dag = deserialize_dag(state["dag"])
    executing_nodes = state.get("executing_nodes", state.get("current_executing_nodes", []))

    rag_nodes = [
        n for n in dag.nodes
        if n.node_id in executing_nodes and n.node_type == "rag"
    ]

    if not rag_nodes:
        return {"collected_evidence": [], "tool_histories": [], "agent_trace": []}

    trace = [
        _append_trace_event(state, EventType.AGENT_START, "rag", f"Executing {len(rag_nodes)} RAG nodes")
    ]

    agent = RAGAgent()
    all_evidence = []
    tool_histories = []

    for node in rag_nodes:
        trace.append(_append_trace_event(
            state,
            EventType.TOOL_START,
            "rag",
            f"Retrieving: {node.query}",
            {"tool_name": "knowledge_base_search", "args": {"query": node.query}},
        ))
        tool_history = _make_tool_history(
            agent_type=AgentType.RAG,
            tool_name="execute_retrieval",
            task_id=state.get("task_id"),
            query=node.query,
        )
        valid, reason = validate_tool_invocation("knowledge_base_search", {"query": node.query, "top_k": 10})
        if not valid:
            _finish_tool_history(tool_history, status="error", error=reason or "invalid_args")
            record_guardrail_event(
                state,
                agent="rag",
                event_type="tool_blocked",
                content=reason or "invalid_args",
                metadata={"tool": "knowledge_base_search", "query": node.query},
            )
            tool_histories.append(tool_history)
            continue
        node.status = StepStatus.RUNNING

        try:
            results = agent.execute_retrieval(
                node.query,
                state["user_query"],
                group=state.get("rag_group"),
            )
            node.result = {"results": [r.model_dump() for r in results]}
            node.confidence = 0.88 if results else 0.0
            _finish_tool_history(
                tool_history,
                status="success",
                result_summary=f"{len(results)} rag chunks",
            )

            for r in results:
                evidence = Evidence(
                    content=r.content,
                    source_url=r.metadata.get("url") if r.metadata else None,
                    source_title=r.metadata.get("title") if r.metadata else None,
                    source_type="knowledge_base",
                    collected_by=AgentType.RAG,
                )
                all_evidence.append(evidence)

            trace.append(_append_trace_event(
                state, EventType.TOOL_COMPLETE, "rag",
                f"Retrieved {len(results)} chunks for: {node.query}",
                {"tool_name": "knowledge_base_search", "status": "success", "result_summary": f"{len(results)} rag chunks"},
            ))
        except Exception as e:
            node.status = StepStatus.FAILED
            node.retry_count += 1
            trace.append(_append_trace_event(
                state,
                EventType.TOOL_ERROR,
                "rag",
                f"RAG retrieval failed: {str(e)}",
                {"tool_name": "knowledge_base_search", "status": "error", "error": str(e)},
            ))
            _finish_tool_history(tool_history, status="error", error=str(e))
        tool_histories.append(tool_history)

    trace.append(AgentEvent(
        agent="rag",
        event_type="agent_complete",
        content=f"Collected {len(all_evidence)} evidence from RAG"
    ).model_dump())

    return {
        "collected_evidence": [e.model_dump() for e in all_evidence],
        "tool_histories": tool_histories,
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
    decision = state.get("guardrail_decision") or {}
    enabled_tools = set(decision.get("enabled_tools", ["search", "browser", "rag"]))
    sends = []

    # 子节点在 LangGraph 中接收到的是 Send payload，不一定包含完整 state。
    # 显式带上后续节点需要的上下文，避免子节点丢失 dag / query / session。
    node_payload = {
        "dag": state.get("dag"),
        "task_id": state.get("task_id"),
        "user_query": state.get("user_query"),
        "session": state.get("session", {}),
        "guardrail_decision": state.get("guardrail_decision"),
        "allow_web_after_rag_hit": state.get("allow_web_after_rag_hit", False),
        "rag_group": state.get("rag_group"),
        "retrieval_policy": state.get("retrieval_policy"),
    }

    for node_id in executing_nodes:
        node = next((n for n in dag.nodes if n.node_id == node_id), None)
        if not node:
            continue

        # 根据节点类型分发
        if node.node_type in ("search", "browser", "rag") and node.node_type in enabled_tools:
            sends.append(Send(node.node_type, {
                **node_payload,
                "executing_nodes": [node_id],
                "current_executing_nodes": [node_id],
            }))

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
    evidence_gate = build_evidence_gate(evidence_list)
    decision = state.get("guardrail_decision") or {}
    reject_if_no_evidence = bool(decision.get("reject_if_no_evidence", True))

    start_event = _append_trace_event(
        state, EventType.AGENT_START, "analyst",
        f"Analyzing {len(evidence_list)} evidence items"
    )

    if not evidence_gate.allowed and reject_if_no_evidence:
        message = build_answer_gate_message(evidence_gate)
        record_guardrail_event(
            state,
            agent="analyst",
            event_type="answer_gate",
            content=message,
            metadata=evidence_gate.model_dump(),
        )
        trace = [start_event, AgentEvent(
            agent="analyst",
            event_type="agent_complete",
            content=message,
        ).model_dump()]
        return {
            "analysis": message,
            "evidence_status": evidence_gate.model_dump(),
            "revision_needed": False,
            "agent_trace": trace,
        }

    agent = AnalystAgent()
    analysis_text = agent.analyze(state["user_query"], evidence_list)

    complete_content = (
        "Analysis complete without external evidence"
        if not evidence_gate.allowed
        else "Analysis complete"
    )
    complete_event = _append_trace_event(state, EventType.AGENT_COMPLETE, "analyst", complete_content)

    trace = [start_event, complete_event, AgentEvent(
        agent="analyst",
        event_type="agent_complete",
        content=f"Generated {len(analysis_text)} chars of analysis from {len(evidence_list)} evidence items"
    ).model_dump()]

    return {
        "analysis": analysis_text,
        "evidence_status": evidence_gate.model_dump(),
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


async def report_node(state: ResearchState) -> dict:
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
    from app.observability.sse_manager import get_sse_manager

    evidence_list = [deserialize_evidence(e) for e in state.get("collected_evidence", [])]
    evidence_gate = build_evidence_gate(evidence_list)
    decision = state.get("guardrail_decision") or {}
    reject_if_no_evidence = bool(decision.get("reject_if_no_evidence", True))
    verification = state.get("verification")
    session_id = state.get("task_id")
    sse = get_sse_manager()
    pending_tasks = []

    start_event = _append_trace_event(state, EventType.AGENT_START, "report", "Generating final report")

    if not evidence_gate.allowed and reject_if_no_evidence:
        message = build_answer_gate_message(evidence_gate)
        record_guardrail_event(
            state,
            agent="report",
            event_type="answer_gate",
            content=message,
            metadata=evidence_gate.model_dump(),
        )
        trace = [start_event, AgentEvent(
            agent="report",
            event_type="agent_complete",
            content=message,
        ).model_dump()]
        session = state.get("session", {})
        session["status"] = TaskStatus.COMPLETED.value
        session["completed_at"] = datetime.utcnow().isoformat()
        return {
            "final_report": f"# Research Report\n\n{message}\n",
            "citations": [],
            "status": TaskStatus.COMPLETED.value,
            "session": session,
            "review_status": {
                "blocked": True,
                **evidence_gate.model_dump(),
            },
            "agent_trace": trace,
        }

    agent = ReportAgent()

    def on_chunk(chunk: str) -> None:
        if session_id:
            pending_tasks.append(asyncio.create_task(
                sse.publish(session_id, EventType.REPORT_CHUNK.value, {
                    "agent": "report",
                    "chunk": chunk,
                    "is_partial": True,
                })
            ))

    def on_citation(citation) -> None:
        if session_id:
            pending_tasks.append(asyncio.create_task(
                sse.publish(session_id, EventType.REPORT_CITATION.value, {
                    "agent": "report",
                    "citation_id": citation.citation_id,
                    "source": citation.source_title or citation.source_url or "",
                    "source_url": citation.source_url,
                    "source_title": citation.source_title,
                })
            ))

    report, citations = agent.generate_stream(
        user_query=state["user_query"],
        analysis=state["analysis"],
        evidence_list=evidence_list,
        reflection=verification,
        on_chunk=on_chunk,
        on_citation=on_citation,
    )

    if pending_tasks:
        await asyncio.gather(*pending_tasks)

    # 更新会话状态
    session = state.get("session", {})
    session["status"] = TaskStatus.COMPLETED.value
    session["completed_at"] = datetime.utcnow().isoformat()

    complete_event = _append_trace_event(state, EventType.AGENT_COMPLETE, "report", f"Report generated: {len(report)} chars")

    trace = [start_event, complete_event, AgentEvent(
        agent="report",
        event_type="agent_complete",
        content=f"Report: {len(report)} chars, {len(citations)} citations"
    ).model_dump()]

    return {
        "final_report": report,
        "citations": [c.model_dump() for c in citations],
        "status": TaskStatus.COMPLETED.value,
        "session": session,
        "review_status": {
            "blocked": False,
            **evidence_gate.model_dump(),
            "verification": verification,
        },
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
