"""Deterministic source selection shared by planning and pending execution."""

from app.graph.state import DAGDefinition, PlanEdge, PlanNode


def apply_source_policy(
    dag: DAGDefinition,
    query: str,
    *,
    use_internal_docs: bool = False,
    ensure_sources: bool = True,
) -> DAGDefinition:
    """Keep public research available and private retrieval explicitly selected."""
    dag = dag.model_copy(deep=True)
    if not use_internal_docs:
        dag.nodes = [node for node in dag.nodes if node.node_type != "rag"]

    def add_source(node_type: str, prefix: str, source_query: str) -> None:
        existing_ids = {node.node_id for node in dag.nodes}
        node_id = prefix
        while node_id in existing_ids:
            node_id += "_source"
        dag.nodes.insert(0, PlanNode(node_id=node_id, node_type=node_type, query=source_query))
        for node in dag.nodes:
            if node.node_type == "analyst":
                node.depends_on.append(node_id)

    if ensure_sources:
        if not any(node.node_type in {"search", "browser"} for node in dag.nodes):
            add_source("search", "public_web", query)
        if use_internal_docs and not any(node.node_type == "rag" for node in dag.nodes):
            add_source("rag", "internal_documents", query)

    node_ids = {node.node_id for node in dag.nodes}
    rag_ids = {node.node_id for node in dag.nodes if node.node_type == "rag"}
    # Dependency lists govern scheduling. Remove obsolete RAG gates and keep
    # their edge representation consistent for downstream topological traversal.
    for node in dag.nodes:
        node.depends_on = [
            dep for dep in node.depends_on
            if dep in node_ids and not (node.node_type in {"search", "browser"} and dep in rag_ids)
        ]
    existing_edges = {
        (edge.from_node, edge.to_node): edge
        for edge in dag.edges
    }
    dag.edges = [
        existing_edges.get((dep, node.node_id)) or PlanEdge(from_node=dep, to_node=node.node_id)
        for node in dag.nodes for dep in node.depends_on
    ]
    return dag
