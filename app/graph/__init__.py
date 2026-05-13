"""
LangGraph StateGraph workflow for autonomous research.

Components:
- state: TypedDict schema and Pydantic models for research state
- compiler: StateGraph compilation with nodes, edges, and conditional routing
- nodes: Individual node function implementations
- edges: Edge routing functions
"""

from app.graph.state import (
    ResearchState,
    PlanStep,
    PlanNode,
    PlanEdge,
    DAGDefinition,
    Evidence,
    Citation,
    SearchResult,
    BrowserResult,
    RAGResult,
    VerificationResult,
    ReflectionResult,
    AgentEvent,
    ErrorRecord,
    TaskStatus,
    StepStatus,
    AgentType,
    PageType,
    VerificationDimension,
    SessionMetadata,
    ClaimEvidence,
    HallucinatedClaim,
    ClaimConflict,
    ToolCallRecord,
    ToolInvocationHistory,
    create_initial_state,
    serialize_dag,
    deserialize_dag,
    deserialize_steps,
    deserialize_evidence,
)
from app.graph.compiler import compile_research_graph

__all__ = [
    "ResearchState",
    "PlanStep",
    "PlanNode",
    "PlanEdge",
    "DAGDefinition",
    "Evidence",
    "Citation",
    "SearchResult",
    "BrowserResult",
    "RAGResult",
    "VerificationResult",
    "ReflectionResult",
    "AgentEvent",
    "ErrorRecord",
    "TaskStatus",
    "StepStatus",
    "AgentType",
    "PageType",
    "VerificationDimension",
    "SessionMetadata",
    "ClaimEvidence",
    "HallucinatedClaim",
    "ClaimConflict",
    "ToolCallRecord",
    "ToolInvocationHistory",
    "create_initial_state",
    "serialize_dag",
    "deserialize_dag",
    "deserialize_steps",
    "deserialize_evidence",
    "compile_research_graph",
]
