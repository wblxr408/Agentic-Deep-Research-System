"""Turn retained public leads into bounded reads in the existing root plan."""
from __future__ import annotations

from copy import deepcopy
import re
from urllib.parse import urlsplit

from app.graph.state import PlanNode, PlanEdge, StepStatus
from app.planning_control import PlanningPolicy, dependency_batches
from app.query_understanding import identity

VERSION = 'adrs-discovery-handoff-v1'


def extend_reads(state, dag, *, remaining_calls, remaining_seconds, allowed_tools):
    manifest = state.get('plan_manifest') or {}
    policy = ((state.get('query_understanding') or {}).get('research_strategy') or {}).get('source_followup') or {}
    if policy.get('version') != VERSION or 'browser' not in allowed_tools or not manifest:
        return dag, manifest, []
    config = state.get('organization_research') or {}
    if (config.get('corpus') or {}).get('collection_mode') == 'seeds_only':
        return dag, manifest, []
    # Accept the whole discovery batch before changing its handoff version.
    if any(node.node_type == 'search' and node.status in {StepStatus.PENDING, StepStatus.RUNNING}
           for node in dag.nodes):
        return dag, manifest, []
    if remaining_seconds < 5 or remaining_calls < 1:
        return dag, manifest, []
    from app.evidence_selection import _terms
    from app.organization_corpus import admit_corpus_request
    from app.external_evidence import request_url_identity
    from app.data_governance import source_observation, authorize_network, network_context, sensitive_url
    from app.channels.models import ChannelError

    previous = manifest.get('source_reads') or []
    past_read_nodes={row['node_id'] for row in (state.get('accepted_tool_operations') or {}).values()
                     if str(row.get('node_id','')).startswith('read_')}
    plan_policy = PlanningPolicy.model_validate(state.get('planning_policy') or {})
    consumed_nodes=past_read_nodes | {row['node_id'] for row in previous}
    available_sources = max(0, min(12, int(policy.get('max_sources', 12))) - len(consumed_nodes))
    capacity = min(3, available_sources, plan_policy.max_plan_nodes - len(dag.nodes), remaining_calls)
    if capacity <= 0:
        return dag, manifest, []
    maximum_depth = min(2, max(1, int(policy.get('max_depth', 2))))
    depths = {row['node_id']: row['depth'] for row in previous}
    requested = {request_url_identity(node.query) for node in dag.nodes if node.node_type == 'browser'}
    browser_nodes = {request_url_identity(node.query): node for node in dag.nodes
                     if node.node_type == 'browser' and node.status == StepStatus.DONE}
    searches = [node.node_id for node in dag.nodes if node.node_type == 'search' and node.status == StepStatus.DONE]
    terms = set(_terms(state['user_query']))
    official_hosts = {urlsplit(url).hostname.removeprefix('www.') for entity in (config.get('scope') or {}).get('entities', [])
                      for url in entity.get('source_urls', []) if urlsplit(url).hostname}
    context = network_context(state)
    candidates = {}
    for source in state.get('collected_evidence') or []:
        if source_observation(source)['data_class'] != 'public':
            continue
        meta = source.get('acquisition') or {}
        source_url = source.get('source_url') or ''
        origin = browser_nodes.get(request_url_identity(source_url))
        discovery = meta.get('coverage') == 'discovery_only'
        if discovery:
            if not searches:
                continue
            links = [{'url': source_url, 'label': source.get('source_title', '')}]
            parents, depth = searches, 1
        elif origin:
            parents, depth = [origin.node_id], depths.get(origin.node_id, 0) + 1
            links = list(meta.get('public_link_records') or [])
            if not links:
                links = [{'url': url, 'label': ''} for url in meta.get('public_links', [])]
            links += [{'url': url, 'label': source.get('source_title', ''), 'pdf': True}
                      for url in meta.get('pdf_links', [])]
        else:
            continue
        if depth > maximum_depth:
            continue
        source_text = (source.get('source_title', '') + ' ' + source.get('content', '')[:3000]).casefold()
        for link in links[:300]:
            url = link.get('url') if isinstance(link, dict) else None
            if not isinstance(url, str) or len(url) > 2048 or sensitive_url(url):
                continue
            key = request_url_identity(url)
            if key in requested or 'read_'+identity({'url':key})[:20] in past_read_nodes:
                continue
            try:
                admit_corpus_request(url, config or None)
                authorize_network(url, context, operation='read')
            except (ChannelError, ValueError):
                continue
            label = str(link.get('label') or '')
            description = (url + ' ' + label + (' ' + source_text if discovery else '')).casefold()
            hits = terms & set(_terms(description))
            host = urlsplit(url).hostname or ''
            official = any(host == item or host.endswith('.' + item) for item in official_hosts)
            academic = bool(re.search(r'research|publication|faculty|people|laborator|\.pdf(?:$|\?)|科研|学术|师资|论文|团队', description))
            if not hits and not (official and academic) and not (link.get('pdf') and terms & set(_terms(source_text))):
                continue
            score = len(hits) + 2 * official + 2 * academic + 3 * bool(link.get('pdf'))
            candidate = {'url': url, 'evidence_id': source['evidence_id'], 'depends_on': parents,
                         'depth': depth, 'score': score, 'host': host, 'label': label[:240]}
            if key not in candidates or score > candidates[key]['score']:
                candidates[key] = candidate
    chosen, hosts = [], {}
    while candidates and len(chosen) < capacity:
        key = max(candidates, key=lambda key: candidates[key]['score'] - 2 * hosts.get(candidates[key]['host'], 0))
        row = candidates.pop(key)
        hosts[row['host']] = hosts.get(row['host'], 0) + 1
        chosen.append(row)
    if not chosen:
        return dag, manifest, []
    dag = dag.model_copy(deep=True)
    rows = []
    for row in chosen:
        node_id = 'read_' + identity({'url': request_url_identity(row['url'])})[:20]
        if any(node.node_id == node_id for node in dag.nodes):
            continue
        node = PlanNode(node_id=node_id, node_type='browser', query=row['url'],
                        depends_on=row['depends_on'], parallel=True,
                        timeout_seconds=max(1, min(90, int(remaining_seconds))), max_retries=2)
        dag.nodes.append(node)
        rows.append({'node_id': node_id, 'node_type': 'browser', 'query': row['url'],
                     'depends_on': row['depends_on'], 'parallel': True, 'condition': 'always',
                     'status': 'pending', 'purpose': '从已保留线索读取正文',
                     'discovery_basis': {'evidence_id': row['evidence_id'], 'url': row['url'], 'label': row['label']},
                     'depth': row['depth']})
    if not rows:
        return dag, manifest, []
    for node in dag.nodes:
        if node.node_type == 'analyst':
            node.depends_on += [row['node_id'] for row in rows]
    dag.edges = [PlanEdge(from_node=dependency, to_node=node.node_id)
                 for node in dag.nodes for dependency in node.depends_on]
    updated = deepcopy(manifest)
    updated.update(parent_plan_version=manifest['plan_version'], revision=int(manifest.get('revision', 0)) + 1,
                   reason='retained_discovery_requires_source_read', source_read_version=VERSION,
                   source_reads=[*previous, *rows], dependency_batches=dependency_batches(dag.nodes))
    existing = {node.node_id: node for node in dag.nodes}
    updated['steps'] = [{**row, 'depends_on': list(existing[row['node_id']].depends_on)}
                        for row in manifest.get('steps', [])] + rows
    updated['adjustments'] = [{'reason': 'read_retained_public_sources_before_analysis',
                              'node_ids': [row['node_id'] for row in rows], 'extra_model_calls': 0,
                              'root_budget_changed': False}]
    updated.pop('plan_version', None)
    updated['plan_version'] = identity(updated)
    return dag, updated, rows
