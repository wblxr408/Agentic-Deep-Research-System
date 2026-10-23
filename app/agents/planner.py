"""
Planner Agent: decomposes user research queries into executable DAGs.

===============================================================
主题 2 - Research DAG Generation
===============================================================

Planner Agent 的核心职责是：用户查询 → DAGDefinition

- DAGDefinition 包含 PlanNode（节点）和 PlanEdge（边）
- 每个节点有 depends_on 依赖关系
- get_executable_order() 计算拓扑序
- 支持并行执行（parallel=True 的节点可同时执行）

这将"研究计划"从"静态步骤列表"升级为"可执行的有向无环图"。

===============================================================
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from app.config import get_settings
from app.llm_budget import budgeted_client, TokenBudgetExceeded
from app.graph.source_policy import apply_source_policy
from app.graph.state import (
    DAGDefinition,
    PlanEdge,
    PlanNode,
    StepStatus,
)
from app.guardrails import (
    TaskIntent,
    build_guardrail_decision,
    build_prompt_profile_message,
)
from app.llm_client import (
    call_chat_with_fallback,
    collect_usage_metrics,
    create_fallback_llm_client,
)
from app.security.prompt_security import untrusted_context

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)


class PlannerAgent:
    """
    Research DAG Generator.

    对应主题 2：Research DAG Generation

    职责：
    1. 分析用户查询，理解研究目标
    2. 生成 DAG 结构（节点 + 边）
    3. 识别并行执行的节点
    4. 定义节点间的依赖关系

    输出：DAGDefinition（可序列化的 DAG）
    """

    SYSTEM_PROMPT = """You are an expert AI research planner specializing in DAG-based research planning.

## Your Task
Decompose complex research queries into an executable Directed Acyclic Graph (DAG) of research steps.

## Core Concepts

### DAG Structure
- **Nodes**: Individual research steps, each representing a specific information need
- **Edges**: Dependencies between nodes (a node can only execute after its dependencies complete)
- **Parallel Execution**: Nodes with no dependencies between them can execute in parallel

### Node Types
Choose the appropriate agent for each step:
- `search`: Quick factual lookups, statistics, market data, news
- `browser`: Deep research, full article reading, official sources, dynamic pages
- `rag`: Optional retrieval from user-maintained internal documents; use only when Internal Documents is enabled. Do not assume background material or prior reports are indexed.
- `mcp`: Trusted external MCP tools behind policy proxy
- `analyst`: (auto-assigned) Synthesis and analysis after data collection

### Research Dimensions
Cover only the user's question, frozen scope, selected purpose and modules.
Use the smallest evidence collection plan that can answer those questions.
Universities and laboratories can be studied independently. Market sizing,
competitors, commercial products and cooperation recommendations are included
only when requested. Do not impose a universal recent-news window on history.

## DAG Design Principles

1. **Granularity**: Each tool node is a bounded evidence operation, not an independent full research agent
2. **Independence**: Minimize dependencies to maximize parallelism
3. **Coverage**: Address the selected questions and identify missing evidence without inventing coverage
4. **Ordering**: Put factual lookups before deep analysis
5. **Sources**: Public research uses search/browser by default. Internal retrieval supplements web evidence and must not gate search/browser. Never stop web research because internal documents return results.

## Response Format

Return a JSON object with the following structure:

```json
{
  "dag_name": "Brief name for this research DAG",
  "nodes": [
    {
      "node_id": "n1",
      "node_type": "search|browser|rag",
      "query": "Specific query or URL",
      "depends_on": [],
      "parallel": true
    }
  ],
  "edges": [
    {
      "from_node": "n1",
      "to_node": "n2",
      "edge_type": "sequential|conditional"
    }
  ]
}
```

## Example DAG

For query "分析 2025 年中国新能源汽车市场" with Internal Documents enabled:
```json
{
  "dag_name": "China EV Market Analysis 2025",
  "nodes": [
    {"node_id": "n1", "node_type": "search", "query": "2025年中国新能源汽车市场规模统计", "depends_on": [], "parallel": true},
    {"node_id": "n2", "node_type": "search", "query": "2025年充电桩保有量及增长", "depends_on": [], "parallel": true},
    {"node_id": "n3", "node_type": "browser", "query": "工信部新能源汽车年度报告", "depends_on": ["n1"], "parallel": false},
    {"node_id": "n4", "node_type": "rag", "query": "新能源汽车技术路线对比", "depends_on": [], "parallel": true},
    {"node_id": "n5", "node_type": "search", "query": "2025年最新政策补贴", "depends_on": [], "parallel": true}
  ],
  "edges": [
    {"from_node": "n1", "to_node": "n3", "edge_type": "sequential"},
    {"from_node": "n2", "to_node": "n3", "edge_type": "sequential"}
  ]
}
```

Note: The "analyst" node type is automatically added at the end by the system."""


    USER_TEMPLATE = """Research Topic: {query}

Generate a bounded evidence collection DAG for this question and its frozen contract.
Keep explicit entity, discipline, time, purpose, module and source limits.
Use search for discovery, browser only for a real HTTP(S) URL, and rag only
when enabled. A browser query is never a prose instruction or placeholder URL.
Separate independent objects or questions when useful; retain real dependencies.
Do not add market, product, cooperation or recent-news tasks unless requested.
The root workflow owns synthesis, review, rendering, state and budget.

Return a JSON object with dag_name, nodes, and edges."""


    def __init__(self):
        settings = get_settings()
        self.model = settings.llm.model
        self.provider = settings.llm.provider
        self._client: OpenAI | None = None
        self.last_usage: dict | None = None
        self.request_budget = None
        self.last_plan_reason: str = 'not_started'

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            from app.model_routing import initialize_agent_client
            if initialize_agent_client(self,'planner'):
                return budgeted_client(self._client,self.request_budget,'research')
            from app.llm_client import create_llm_client, get_llm_model
            self._client = create_llm_client()
            self.model = get_llm_model()
        return budgeted_client(self._client,self.request_budget,'research')

    def _is_openai_compatible(self) -> bool:
        """Check if the current provider supports response_format parameter."""
        return self.provider in ("openai", "qwen") and not self.client.base_url

    def _extract_json_object(self, content: str) -> dict:
        """
        Extract a JSON object from model output.

        Some providers occasionally wrap JSON in prose or code fences even when
        the prompt requests JSON only. We try strict parsing first, then fall
        back to fenced blocks and balanced-object extraction.
        """
        text = content.strip()
        if not text:
            raise json.JSONDecodeError("empty content", content, 0)

        candidates = [text]

        if "```json" in text:
            start = text.find("```json") + len("```json")
            end = text.find("```", start)
            if end > start:
                candidates.append(text[start:end].strip())

        if "{" in text and "}" in text:
            candidates.append(text[text.find("{"): text.rfind("}") + 1].strip())

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                parsed, _ = decoder.raw_decode(text[match.start():])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        raise json.JSONDecodeError("unable to extract JSON object", content, 0)

    def create_dag(
        self,
        query: str,
        planning_hints: str | None = None,
        skill_prompt: str | None = None,
        planner_hints: list[str] | None = None,
        use_internal_docs: bool = False,
        rag_group: str | None = None,
        organization_research: dict | None = None,
        planning_strategy: str = 'hybrid',
        query_contract: str | None = None,
        query_type: str | None = None,
        analysis_depth: str = 'auto',
    ) -> DAGDefinition:
        """
        Generate a research DAG for the given query.

        对应主题 2: Research DAG Generation

        Args:
            query: The user's research query

        Returns:
            DAGDefinition object containing nodes and edges
        """
        logger.info(f"Planner: Generating DAG for query: {query[:100]}")
        self.last_usage = None
        from app.organization_corpus import seed_only_dag, corpus_instructions
        declared_plan = seed_only_dag(organization_research)
        if declared_plan is not None:
            self.last_usage = None
            self.last_plan_reason = 'declared_seed_only_fixed_workflow'
            return apply_source_policy(declared_plan, query, use_internal_docs=use_internal_docs)

        if planning_strategy == 'fixed':
            self.last_plan_reason = 'explicit_fixed_workflow'
            return apply_source_policy(self._fixed_research_dag(query, organization_research), query, use_internal_docs=use_internal_docs)

        decision = build_guardrail_decision(query)
        if (planning_strategy != 'dynamic' and not organization_research and analysis_depth != 'deep'
                and (query_type == 'fact' or query_type is None and decision.intent == TaskIntent.FACT_LOOKUP)):
            self.last_plan_reason = 'direct_fact_fixed_workflow'
            return apply_source_policy(self._fact_lookup_dag(query), query, use_internal_docs=use_internal_docs)

        system_prompt = f"{build_prompt_profile_message(decision, query)}\n\n{self.SYSTEM_PROMPT}"
        system_prompt += (
            "\n\nInternal Documents: enabled. Include a supplementary rag retrieval without blocking public web collection."
            if use_internal_docs else
            "\n\nInternal Documents: disabled. Use public sources; do not include rag nodes."
        )
        from app.organization_purpose import analysis_instructions
        system_prompt += analysis_instructions(organization_research)
        system_prompt += corpus_instructions(organization_research)
        user_prompt = self.USER_TEMPLATE.format(query=query)
        if query_contract:
            if len(query_contract) > 48000:
                raise ValueError('task_contract_exceeds_planner_context_limit')
            user_prompt += '\n\n' + untrusted_context('frozen_research_contract', query_contract)
        if use_internal_docs and rag_group:
            user_prompt += f"\n\n{untrusted_context('internal_document_group', rag_group)}"
        if skill_prompt:
            user_prompt = f"{user_prompt}\n\n{untrusted_context('skill_content', skill_prompt)}"
        if planning_hints:
            user_prompt = f"{user_prompt}\n\nSession Planning Hints:\n{planning_hints}"
        if planner_hints:
            user_prompt = (
                f"{user_prompt}\n\nPlanner Skill Instructions:\n"
                + "\n".join(f"- {item}" for item in planner_hints if item and item.strip())
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            active_client=self.client
            create_kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 4096,
            }

            if self._is_openai_compatible():
                create_kwargs["response_format"] = {"type": "json_object"}

            response, response_model, fallback_used = call_chat_with_fallback(
                active_client,
                self.model,
                self.routed_fallback if hasattr(self,'routed_fallback') else create_fallback_llm_client(),
                **{key: value for key, value in create_kwargs.items() if key != "model"},
            )
            if fallback_used:
                self.model = response_model
            self.last_usage = collect_usage_metrics(
                response=response,
                model=response_model,
                messages=messages,
                completion_text=response.choices[0].message.content if response.choices else "",
            )

            content = response.choices[0].message.content
            if not content:
                self.last_plan_reason = 'empty_model_plan_fixed_fallback'
                return apply_source_policy(self._fixed_research_dag(query, organization_research), query, use_internal_docs=use_internal_docs)

            try:
                data = self._extract_json_object(content)
            except json.JSONDecodeError as parse_error:
                self.last_plan_reason = 'non_json_model_plan_fixed_fallback'
                logger.warning(f"Planner: non-JSON output received, using fallback parser: {parse_error}")
                return apply_source_policy(self._fixed_research_dag(query, organization_research), query, use_internal_docs=use_internal_docs)
            dag = self._parse_dag(data, query)

            logger.info(
                f"Planner: Generated DAG '{dag.dag_name}' with {len(dag.nodes)} nodes, "
                f"execution_order={dag.get_executable_order()}"
            )
            self.last_plan_reason = 'bounded_model_plan'
            return apply_source_policy(dag, query, use_internal_docs=use_internal_docs)

        except TokenBudgetExceeded:
            raise
        except (OSError, RuntimeError, TypeError, ValueError, KeyError, AttributeError) as e:
            logger.error(f"Planner error: {e}")
            self.last_plan_reason = 'model_plan_failed_fixed_fallback'
            return apply_source_policy(self._fixed_research_dag(query, organization_research), query, use_internal_docs=use_internal_docs)

    def _parse_dag(self, data: dict, query: str) -> DAGDefinition:
        """
        Parse LLM output into DAGDefinition.

        Handles various output formats gracefully.
        """
        dag_name = data.get("dag_name", f"Research-{query[:30]}")

        # Parse nodes
        nodes = []
        for i, node_data in enumerate(data.get("nodes", [])):
            node_data.setdefault("node_id", f"n{i+1}")
            node_data.setdefault("node_type", "search")
            node_data.setdefault("depends_on", [])
            node_data.setdefault("parallel", True)
            node_data.setdefault("status", StepStatus.PENDING.value)
            node_data.setdefault("retry_count", 0)
            node_data.setdefault("timeout_seconds", 300)

            # Validate node_type
            if node_data["node_type"] not in ("search", "browser", "rag", "mcp", "analyst", "reflection", "report"):
                raise ValueError('plan_unknown_node_type')

            try:
                node = PlanNode.model_validate(node_data)
                nodes.append(node)
            except (OSError, RuntimeError, TypeError, ValueError, KeyError, AttributeError) as e:
                raise ValueError('invalid_plan_node') from e

        # Parse edges
        edges = []
        for edge_data in data.get("edges", []):
            edge_data.setdefault("edge_type", "sequential")
            edge_data.setdefault("condition", None)

            try:
                edge = PlanEdge.model_validate(edge_data)
                edges.append(edge)
            except (OSError, RuntimeError, TypeError, ValueError, KeyError, AttributeError) as e:
                raise ValueError('invalid_plan_edge') from e

        # Ensure analyst node at the end
        analyst_exists = any(n.node_type == "analyst" for n in nodes)
        if not analyst_exists:
            # Add analyst node that depends on all other nodes
            other_node_ids = [n.node_id for n in nodes]
            analyst_node = PlanNode(
                node_id="analyst",
                node_type="analyst",
                query=f"综合分析：{query}",
                depends_on=other_node_ids,
                parallel=False,
            )
            nodes.append(analyst_node)

        return DAGDefinition(
            dag_name=dag_name,
            nodes=nodes,
            edges=edges,
        )

    def _fixed_research_dag(self, query: str, organization: dict | None) -> DAGDefinition:
        entities = ((organization or {}).get('scope') or {}).get('entities') or []
        questions = [f"{item['name']} {query}" for item in entities] or [query]
        nodes = [PlanNode(node_id=f'fixed_{index+1}', node_type='search', query=text,
            depends_on=[], parallel=True) for index, text in enumerate(questions)]
        return DAGDefinition(dag_name='固定问题取证流程', nodes=nodes)

    def _fallback_dag(self, query: str) -> DAGDefinition:
        """
        Generate a minimal fallback DAG when LLM fails.

        Ensures the system can still make progress with basic research.
        """
        logger.warning("Planner: Using fallback DAG")

        return DAGDefinition(
            dag_name=f"Fallback-Research-{query[:20]}",
            nodes=[
                PlanNode(
                    node_id="n1",
                    node_type="search",
                    query=f"核心事实和数据：{query}",
                    depends_on=[],
                    parallel=True,
                ),
                PlanNode(
                    node_id="n2",
                    node_type="browser",
                    query=f"权威文章深度阅读：{query}",
                    depends_on=["n1"],
                    parallel=False,
                ),
                PlanNode(
                    node_id="n4",
                    node_type="analyst",
                    query=f"综合分析：{query}",
                    depends_on=["n1", "n2"],
                    parallel=False,
                ),
            ],
            edges=[
                PlanEdge(from_node="n1", to_node="n2", edge_type="sequential"),
                PlanEdge(from_node="n2", to_node="n4", edge_type="sequential"),
            ],
        )

    def _fact_lookup_dag(self, query: str) -> DAGDefinition:
        """Generate a minimal DAG for simple fact lookup questions."""
        return DAGDefinition(
            dag_name=f"Fact-Lookup-{query[:20]}",
            nodes=[
                PlanNode(
                    node_id="n2",
                    node_type="search",
                    query=query,
                    depends_on=[],
                    parallel=True,
                ),
                PlanNode(
                    node_id="n3",
                    node_type="analyst",
                    query=f"回答事实问题：{query}",
                    depends_on=["n2"],
                    parallel=False,
                ),
            ],
            edges=[
                PlanEdge(from_node="n2", to_node="n3", edge_type="sequential"),
            ],
        )

    # === Backward compatibility ===
    def create_plan(self, query: str) -> list[dict]:
        """
        Backward compatible method.

        Converts DAGDefinition to list of step dicts for existing code.
        """
        dag = self.create_dag(query)
        return [n.model_dump() for n in dag.nodes]
