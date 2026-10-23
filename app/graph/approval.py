"""Server-owned approval bindings; a decision never grants blanket confirmation."""
from __future__ import annotations

from copy import deepcopy

from app.graph.state import StepStatus, deserialize_dag, serialize_dag


def action_payload(node, tool_name):
    if tool_name == "browse_webpage":
        return {"url": node.query, "max_chars": 2000}
    if tool_name == "knowledge_base_search":
        return {"query": node.query, "top_k": 10}
    if tool_name == "duckduckgo_search":
        return {"query": node.query}
    return None


def approved_action(state, node, tool_name, payload):
    for decision in state.get("approval_decisions", []):
        if (decision.get("status") == "approved"
                and decision.get("node_id") == node.node_id
                and decision.get("tool_name") == tool_name
                and decision.get("request_payload") == payload
                and decision.get("revision_count") == state.get("revision_count", 0)):
            return decision
    return None


def resume_approved_state(snapshot, resolutions, *, owner_id, session_id):
    state = deepcopy(snapshot)
    if (state.get("task_id") != session_id or not state.get("user_query")
            or state.get("runtime_status") != "awaiting_approval"
            or state.get("session", {}).get("owner_id") != owner_id
            or not isinstance(state.get("budget_state"), dict)
            or not isinstance(state.get("skill_context"), dict)):
        raise ValueError("invalid_approval_checkpoint")
    dag = deserialize_dag(state["dag"])
    completed = set(state.get("completed_nodes", []))
    decisions = list(state.get("approval_decisions", []))
    resolved_nodes = set()
    for approval in state.get("pending_approvals", []):
        resolved = resolutions.get(approval["approval_id"])
        if not resolved or resolved.get("status") not in {"approved", "rejected"}:
            raise ValueError("approval_decisions_incomplete")
        if resolved.get("request_payload") != approval.get("request_payload"):
            raise ValueError("approval_payload_changed")
        node = next((n for n in dag.nodes if n.node_id == approval.get("node_id")), None)
        if node is None or not node.waiting_approval or node.node_id in resolved_nodes:
            raise ValueError("approval_node_changed")
        expected = action_payload(node, approval["tool_name"])
        if expected is not None and expected != approval.get("request_payload"):
            raise ValueError("approval_payload_changed")
        if expected is None and (node.node_type != "mcp" or approval.get("bound_query") != node.query):
            raise ValueError("approval_node_changed")
        decisions.append({**approval, **resolved, "node_id": node.node_id, "revision_count": state.get("revision_count", 0)})
        node.waiting_approval = False
        node.last_error = None
        node.last_error_category = None
        if resolved["status"] == "rejected":
            node.status = StepStatus.SKIPPED
            completed.add(node.node_id)
        else:
            node.status = StepStatus.PENDING
            completed.discard(node.node_id)
        resolved_nodes.add(node.node_id)
    if not resolved_nodes:
        raise ValueError("approval_decisions_incomplete")
    state["dag"] = serialize_dag(dag)
    state["completed_nodes"] = list(completed)
    state["pending_approvals"] = []
    state["approval_decisions"] = decisions
    state["current_executing_nodes"] = []
    state["status"] = "running"
    state["runtime_status"] = "running"
    return state
