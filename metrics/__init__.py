"""
Metrics package - Five core architecture themes.

Each submodule collects metrics for its corresponding architecture theme:
- langgraph_workflow: Theme 1 - Autonomous Research Workflow
- research_dag: Theme 2 - Research DAG Generation
- multi_agent: Theme 3 - Tool-driven Multi-Agent Collaboration
- stateful_agent: Theme 4 - Long-running Stateful Agent
- reflection_agent: Theme 5 - Self-Reflection & Verification
"""

from metrics.langgraph_workflow.collector import LangGraphMetricsCollector
from metrics.research_dag.collector import DAGMetricsCollector
from metrics.multi_agent.collector import MultiAgentMetricsCollector
from metrics.stateful_agent.collector import StatefulAgentMetricsCollector
from metrics.reflection_agent.collector import ReflectionMetricsCollector

__all__ = [
    "LangGraphMetricsCollector",
    "DAGMetricsCollector",
    "MultiAgentMetricsCollector",
    "StatefulAgentMetricsCollector",
    "ReflectionMetricsCollector",
]
