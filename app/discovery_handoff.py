"""Turn retained public leads into bounded reads in the existing root plan."""
from __future__ import annotations

from copy import deepcopy
import re
from urllib.parse import urlsplit

from app.graph.state import PlanNode, PlanEdge, StepStatus
from app.planning_control import PlanningPolicy, dependency_batches
from app.query_understanding import identity

VERSION = 'adrs-discovery-handoff-v1'
FOCUSED_VERSION = 'adrs-discovery-handoff-v2'
PRIMARY_VERSION = 'adrs-discovery-handoff-v3'
REPRESENTATION_VERSION = 'adrs-discovery-handoff-v4'
TRANSPORT_VERSION = 'adrs-discovery-handoff-v5'
PRIMARY_VERSIONS = {PRIMARY_VERSION, REPRESENTATION_VERSION, TRANSPORT_VERSION}
FOCUSED_VERSIONS = {FOCUSED_VERSION, *PRIMARY_VERSIONS}


def _arxiv_document(url):
    """Compare actual linked representations, never generate a download URL."""
    try:parsed=urlsplit(url)
    except (TypeError,ValueError):return None
    if parsed.hostname not in {'arxiv.org','www.arxiv.org','export.arxiv.org'}:return None
    match=re.fullmatch(r'/(abs|html|pdf)/((?:\d{4}\.\d{4,5}|[a-z][a-z.\-]+/\d{7}))(v\d+)?(?:\.pdf)?/?',parsed.path,re.I)
    return (match[2].casefold(),match[3],match[1].casefold()) if match else None


def _same_arxiv_document(source,target):
    left,right=_arxiv_document(source),_arxiv_document(target)
    return bool(left and right and left[0]==right[0] and
                (not left[1] or not right[1] or left[1].casefold()==right[1].casefold()))


def _sharing_action(url):
    from urllib.parse import parse_qs
    try:parsed=urlsplit(url)
    except (TypeError,ValueError):return True
    return bool(parsed.path.casefold().rstrip('/') in {
        '/submit','/share','/sharer','/sharer.php','/sharing/share-offsite','/intent/tweet'}
        and set(parse_qs(parsed.query)) & {'url','u','text','title','status','link'})


def independent_search_plan(dag, strategy, rejection):
    """Retain unconditional root searches, never repair an unknown condition.

    The original compiler still validates the reduced plan and tool grants.
    Browser/dependent/conditional nodes from the rejected plan are not reused.
    """
    if ((strategy or {}).get('source_followup') or {}).get('version')!=TRANSPORT_VERSION:
        return None
    if rejection!='plan_missing_condition':return None
    incoming={edge.to_node for edge in dag.edges}
    nodes=[node.model_copy(deep=True) for node in dag.nodes if node.node_type=='search'
        and node.condition=='always' and not node.depends_on and node.node_id not in incoming]
    if not nodes or len({node.node_id for node in nodes})!=len(nodes):return None
    return dag.model_copy(update={'nodes':nodes,'edges':[]},deep=True)


def topic_terms(query, entities):
    """Selection hints from the actual question, excluding explicit entity names."""
    from app.evidence_selection import _terms
    names = {name for entity in entities for name in [entity.get('name', ''), *entity.get('aliases', [])] if name}
    text = query.casefold()
    for name in sorted(names, key=len, reverse=True):
        text = re.sub(re.escape(name.casefold()), ' ', text)
    text = re.sub(r'研究|调研|分析|领域|方向|相关|团队|布局|近年来|论文|科研|发展', ' ', text)
    return [term for term in _terms(text) if term not in {
        'university', 'company', 'laboratory', 'study', 'studies', 'analysis', 'papers', 'paper', 'team'}][:40]


def anchor_plan(dag, query, strategy, configuration, *, adjustments=None):
    """Keep the original topic in open organization discovery; never reset nodes."""
    followup = (strategy or {}).get('source_followup') or {}
    if (followup.get('version') not in FOCUSED_VERSIONS or
            strategy.get('investigation') != 'organization_and_work' or
            ((configuration or {}).get('corpus') or {}).get('collection_mode') == 'seeds_only'):
        return dag
    dag = dag.model_copy(deep=True)
    known = {node.node_id:node for node in dag.nodes}
    if len(known) != len(dag.nodes) or any(edge.from_node not in known or edge.to_node not in known for edge in dag.edges):
        return dag  # The original compiler owns invalid-plan rejection/fallback.
    for edge in dag.edges:
        if edge.from_node not in known[edge.to_node].depends_on:
            known[edge.to_node].depends_on.append(edge.from_node)
    from app.planning_control import PlanningError
    try:
        dependency_batches(dag.nodes)
    except PlanningError:
        return dag
    # A model can exceed its requested initial discovery breadth. For ordinary
    # static searches, keep one original, one work and one team question before
    # following sources. Conditional or evidence-bound searches stay intact.
    searches = [node for node in dag.nodes if node.node_type == 'search']
    simple = (followup.get('initial_search_limit') == 3 and
              len(((configuration or {}).get('scope') or {}).get('entities', [])) <= 1 and
              all(node.condition == 'always' and not node.evidence_ids for node in searches) and
              all(set(node.depends_on) <= {item.node_id for item in searches} for node in searches) and
              not any(edge.condition or edge.edge_type == 'conditional' for edge in dag.edges))
    if simple:
        from app.evidence_selection import _terms
        focus = set(followup.get('topic_terms') or [])
        original = next((node for node in searches if node.query.strip() == query.strip()), None)
        original = original or PlanNode(node_id='discover_'+identity({'query':query})[:20],
                                       node_type='search',query=query,parallel=True,max_retries=2)
        selected = [original]
        for role, pattern in [('work', r'papers?|publication|preprint|arxiv|publisher|论文|成果|出版'),
                              ('team', r'team|faculty|author|laborator|团队|作者|师资|实验室')]:
            candidates = [node for node in searches if node not in selected and re.search(pattern,node.query,re.I)]
            chosen = max(candidates, key=lambda node: (
                bool(followup.get('version') in PRIMARY_VERSIONS and role == 'work' and
                     re.search(r'[\u3400-\u9fff]',query) and not re.search(r'[\u3400-\u9fff]',node.query)),
                bool(followup.get('version')==TRANSPORT_VERSION and role=='work' and
                     re.search(r'\bpapers?\b|preprint|arxiv|publisher|论文|成果|出版',node.query,re.I)),
                len(focus & set(_terms(node.query))),
                bool(re.search(r'[\u3400-\u9fff]',query)) and not bool(re.search(r'[\u3400-\u9fff]',node.query))
            ),default=None)
            if chosen is None:
                text = query + (' 论文 publications research papers' if role == 'work' else ' 研究团队 作者主页')
                chosen = PlanNode(node_id='discover_'+identity({'query':text})[:20],node_type='search',
                                  query=text,parallel=True,max_retries=2)
            selected.append(chosen)
        selected_ids = {node.node_id for node in selected}
        removed = {node.node_id for node in searches} - selected_ids
        for node in selected:
            node.depends_on = []
        retained = [node for node in dag.nodes if node.node_type != 'search']
        for node in retained:
            if removed & set(node.depends_on):
                node.depends_on = list(dict.fromkeys([item for item in node.depends_on if item not in removed] +
                                                    [item.node_id for item in selected]))
        dag.nodes = selected + retained
        # Retain explicit edges among retained non-search nodes. Dependencies
        # on omitted static searches now point to the selected discovery batch.
        dag.edges = [edge for edge in dag.edges if edge.from_node not in removed and
                     edge.to_node not in removed and edge.to_node not in selected_ids]
        if adjustments is not None:
            adjustments.append({'reason':'initial_discovery_then_source_reading',
                'search_limit':3,'selected_queries':[node.query for node in selected],
                'omitted_initial_queries':[node.query for node in searches if node.node_id in removed],
                'root_budget_changed':False})
        return dag
    queries = [query, query + ' 论文 publications research papers']
    existing = {node.query.strip().casefold() for node in dag.nodes if node.node_type == 'search'}
    added = []
    for text in queries:
        if text.strip().casefold() in existing:
            continue
        node_id = 'discover_' + identity({'query': text})[:20]
        if any(node.node_id == node_id for node in dag.nodes):
            continue
        added.append(PlanNode(node_id=node_id, node_type='search', query=text,
                              depends_on=[], parallel=True, max_retries=2))
    dag.nodes = added + dag.nodes
    for node in dag.nodes:
        if node.node_type == 'analyst':
            node.depends_on += [item.node_id for item in added]
    return dag


def extend_reads(state, dag, *, remaining_calls, remaining_seconds, allowed_tools):
    manifest = state.get('plan_manifest') or {}
    policy = ((state.get('query_understanding') or {}).get('research_strategy') or {}).get('source_followup') or {}
    if policy.get('version') not in {VERSION, *FOCUSED_VERSIONS} or 'browser' not in allowed_tools or not manifest:
        return dag, manifest, []
    focused = policy.get('version') in FOCUSED_VERSIONS
    primary = policy.get('version') in PRIMARY_VERSIONS
    representations = policy.get('version') in {REPRESENTATION_VERSION,TRANSPORT_VERSION}
    transport = policy.get('version') == TRANSPORT_VERSION
    diverse = transport and policy.get('work_selection')=='distinct_primary_works_v1'
    expanded=transport and policy.get('collection_capacity_policy')=='primary_work_capacity_v1'
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
    from app.external_evidence import request_url_identity, PUBLIC_TRANSPORTS
    from app.data_governance import source_observation, authorize_network, network_context, sensitive_url
    from app.channels.models import ChannelError

    previous = manifest.get('source_reads') or []
    # Let the current parents yield their links before spending the next slots
    # on another first-level batch. Pending failures keep their existing retries.
    previous_ids = {row['node_id'] for row in previous}
    if focused and any(node.node_id in previous_ids and (
            node.status in {StepStatus.PENDING, StepStatus.RUNNING} or
            node.status == StepStatus.FAILED and not node.terminal_failure and node.retry_count < node.max_retries)
            for node in dag.nodes):
        return dag, manifest, []
    past_read_nodes={row['node_id'] for row in (state.get('accepted_tool_operations') or {}).values()
                     if str(row.get('node_id','')).startswith('read_')}
    plan_policy = PlanningPolicy.model_validate(state.get('planning_policy') or {})
    consumed_nodes=past_read_nodes | {row['node_id'] for row in previous}
    available_sources = max(0, min(24 if expanded else 12, int(policy.get('max_sources', 12))) - len(consumed_nodes))
    capacity = min(3, available_sources, plan_policy.max_plan_nodes - len(dag.nodes), remaining_calls)
    if capacity <= 0:
        return dag, manifest, []
    maximum_depth = min(3 if focused else 2, max(1, int(policy.get('max_depth', 2))))
    depths = {row['node_id']: row['depth'] for row in previous}
    requested = {request_url_identity(node.query) for node in dag.nodes if node.node_type == 'browser'}
    browser_nodes = {request_url_identity(node.query): node for node in dag.nodes
                     if node.node_type == 'browser' and node.status == StepStatus.DONE}
    searches = [node.node_id for node in dag.nodes if node.node_type == 'search' and node.status == StepStatus.DONE]
    terms = set(_terms(state['user_query']))
    focus = set(policy.get('topic_terms') or []) if focused else set()
    official_hosts = {urlsplit(url).hostname.removeprefix('www.') for entity in (config.get('scope') or {}).get('entities', [])
                      for url in entity.get('source_urls', []) if urlsplit(url).hostname}
    context = network_context(state)
    acquired_work_hints=set()
    target_names=[]
    if diverse:
        # Identifier grouping is only an acquisition priority. It never merges
        # publication versions, dates, authors, evidence or statistics.
        for source in state.get('collected_evidence') or []:
            meta=source.get('acquisition') or {}
            hint=_arxiv_document(source.get('source_url') or '')
            if (hint and meta.get('coverage')=='full_text' and source.get('content')
                    and source.get('source_backend') in PUBLIC_TRANSPORTS
                    and source_observation(source)['data_class']=='public'):
                acquired_work_hints.add(hint[0])
        target_names=[name for entity in (config.get('scope') or {}).get('entities',[])
            for name in [entity.get('name'),*(entity.get('aliases') or [])] if isinstance(name,str) and name.strip()]
        from app.organization_identity import official_title_claims
        target_names += [row['alias'] for row in official_title_claims(config,state.get('collected_evidence') or [])]
        target_names=list(dict.fromkeys(target_names))[:80]
    candidates = {}
    for source in state.get('collected_evidence') or []:
        if source_observation(source)['data_class'] != 'public':
            continue
        meta = source.get('acquisition') or {}
        source_url = source.get('source_url') or ''
        origin = browser_nodes.get(request_url_identity(source_url))
        discovery = meta.get('coverage') == 'discovery_only'
        if transport and not discovery and source.get('source_backend') in PUBLIC_TRANSPORTS:
            # Redirect provenance comes from this acquisition, not a guessed DOI
            # conversion or a cross-task alias. A final URL alone is insufficient.
            try:
                if request_url_identity(meta.get('final_url',''))==request_url_identity(source_url):
                    origin=origin or browser_nodes.get(request_url_identity(meta.get('requested_url','')))
            except (ValueError,TypeError):pass
            if origin:requested.add(request_url_identity(source_url))
        if discovery:
            if not searches:
                continue
            links = [{'url': source_url, 'label': source.get('source_title', '')}]
            parents, depth = searches, 1
        elif origin:
            parents, depth = [origin.node_id], depths.get(origin.node_id, 0) + 1
            links = list((meta.get('research_link_records') if focused else None) or meta.get('public_link_records') or [])
            if not links:
                links = [{'url': url, 'label': ''} for url in meta.get('public_links', [])]
            if representations:
                # A long reference list can fill the ranked research-link view
                # before a page-header download. Its literal original-order
                # record is still retained separately; do not discard it.
                entrances=[row for row in (meta.get('public_link_records') or [])[:200]
                    if isinstance(row,dict) and isinstance(row.get('url'),str)
                    and _same_arxiv_document(source_url,row['url'])]
                links=[*entrances,*links]
            documents = [*meta.get('pdf_links', []), *(meta.get('document_links', []) if focused else [])]
            links += [{'url': url, 'label': source.get('source_title', ''), 'pdf': True}
                      for url in documents]
        else:
            continue
        if depth > maximum_depth:
            continue
        source_text = (source.get('source_title', '') + ' ' + source.get('content', '')[:3000]).casefold()
        for link in links[:300]:
            url = link.get('url') if isinstance(link, dict) else None
            if not isinstance(url, str) or len(url) > 2048 or sensitive_url(url):
                continue
            if representations and _sharing_action(url):
                continue
            work_hint=_arxiv_document(url) if diverse else None
            if work_hint and work_hint[0] in acquired_work_hints:
                continue
            label = str(link.get('label') or '')
            from app.organization_identity import language_link, secure_language_url
            try:host = urlsplit(url).hostname or ''
            except ValueError:continue
            identity_language = bool(policy.get('entity_identity') == 'official-language-v1' and
                not discovery and any(host == item or host.endswith('.' + item) for item in official_hosts)
                and language_link(label) and any(
                    request_url_identity(source_url) == request_url_identity(str(seed))
                    for entity in (config.get('scope') or {}).get('entities', [])
                    for seed in entity.get('source_urls', [])))
            source_link_url = url
            if identity_language and policy.get('identity_transport') == 'https_same_target_v1':
                url = secure_language_url(url)
            key = request_url_identity(url)
            if key in requested or 'read_'+identity({'url':key})[:20] in past_read_nodes:
                continue
            try:
                admit_corpus_request(url, config or None)
                authorize_network(url, context, operation='read')
            except (ChannelError, ValueError):
                continue
            description = (url + ' ' + label + (' ' + source_text if discovery else '')).casefold()
            hits = terms & set(_terms(description))
            host = urlsplit(url).hostname or ''
            official = any(host == item or host.endswith('.' + item) for item in official_hosts)
            academic = bool(re.search(r'research|publication|faculty|people|laborator|\.pdf(?:$|\?)|科研|学术|师资|论文|团队', description))
            # Inspect the actual href before the lexical gate. Numeric paper
            # URLs and labels such as "Read PDF" need their parent's context.
            target_path=urlsplit(url).path if representations else url
            pdf_url = bool(re.search(r'\.pdf(?:$|[?#])|/(?:pdf|epdf)/',target_path,re.I))
            primary_landing = bool(re.search(r'/(?:abs|doi|html)/',target_path,re.I) or transport and
                host.casefold() in {'doi.org','www.doi.org','dx.doi.org'} and
                re.match(r'^/10\.\d{4,9}/\S+',target_path,re.I))
            explicit_document = (link.get('pdf') or focused and link.get('kind') == 'full_text' or
                                 primary and (pdf_url or primary_landing))
            if not hits and not identity_language and not (official and academic) and not (explicit_document and terms & set(_terms(source_text))):
                continue
            score = len(hits) + 2 * official + 2 * academic + 3 * bool(link.get('pdf'))
            signals = {}
            if focused:
                # Entity matches and domain reputation cannot replace the topic.
                direct_hits = focus & set(_terms(url + ' ' + label))
                topic_hits = focus & set(_terms(description))
                pdf = bool(link.get('pdf') or link.get('kind') == 'full_text' or
                           re.search(r'\.pdf(?:$|[?#])|/(?:pdf|epdf)/', target_path, re.I))
                same_document=bool(representations and not discovery and _same_arxiv_document(source_url,url))
                download_label=bool(representations and not discovery and pdf and (
                    link.get('kind')=='full_text' or link.get('navigation') and re.fullmatch(
                        r'\s*(?:(?:(?:view|download|read)\s+)?(?:pdf|full[ -]?text|(?:full\s+)?paper)|(?:下载)?(?:PDF|全文))\s*',label,re.I)))
                representation_link=bool(same_document or download_label)
                work = bool(pdf or primary and primary_landing or re.search(
                    r'\bpaper\b|publication|/abs/|/doi/|full.?text|论文|研究成果|出版', url + ' ' + label, re.I))
                inherited = bool(not discovery and (pdf or primary and primary_landing) and
                                 focus & set(_terms(source_text)))
                relevant = bool(topic_hits or inherited or not focus and hits)
                # Navigation can be useful as an entrance; it cannot outrank
                # actual article links just by repeating the topic in a menu.
                role = 'work' if relevant and work and (not link.get('navigation') or representation_link) else 'topic' if relevant else 'identity'
                if primary:
                    specific={term for term in focus if re.search(r'[a-z0-9]',term)}
                    specific_tokens=topic_hits | (set(_terms(source_text)) if inherited else set())
                    specific_hit=any(term in specific_tokens or term+'s' in specific_tokens for term in specific)
                    # A generic service mention in a journal shell must not
                    # outrank a page matching the distinctive technical term.
                    if role=='work' and specific and not specific_hit:
                        role='topic'
                    if policy.get('topic_gate')=='distinctive_literal_v1' and specific and not specific_hit:
                        role='identity'
                if role == 'identity' and not (identity_language or official and academic):
                    continue
                score = (16 * (role == 'work') + 6 * (role == 'topic') +
                         4 * len(direct_hits) + 2 * len(topic_hits) +
                         4 * pdf + int(official) + 2 * (not discovery and role == 'work'))
                signals = {'source_role': role, 'topic_terms': sorted(topic_hits),
                           'direct_topic_terms': sorted(direct_hits), 'explicit_full_text_link': pdf,
                           'parent_topic_used': inherited,
                           'selection_basis': 'question_topic_and_source_role_not_affiliation_or_support'}
                if primary:
                    signals.update(source_priority=4 if identity_language else 3 if role=='work' and pdf else
                        2 if role=='work' and primary_landing else
                        1 if role=='work' or role=='topic' and official and academic else
                        0 if role=='topic' else -1,
                        primary_link_inherited=bool(inherited and primary_landing),
                        identity_language_entrance=identity_language,
                        source_link_url=source_link_url,
                        transport_upgrade='https_same_target_v1' if url != source_link_url else None,
                        selection_basis='explicit_fulltext_then_primary_landing_then_target_entrance_then_topic')
                    if representations:
                        signals.update(same_document_representation=same_document,explicit_primary_download=download_label,
                            source_priority=6 if identity_language else 5 if role=='work' and representation_link and pdf else
                                4 if role=='work' and same_document else signals['source_priority'],
                            selection_basis='same_document_or_primary_download_before_cited_documents_then_topic')
            candidate = {'url': url, 'evidence_id': source['evidence_id'], 'depends_on': parents,
                         'depth': depth, 'score': score, 'host': host, 'label': label[:240], **signals}
            if diverse:
                name_text=description if discovery else description+' '+source_text
                mentions=[name for name in target_names if re.search(
                    r'\s+'.join(re.escape(word) for word in name.split()),name_text,re.I)]
                if expanded and not discovery and origin and (
                        signals.get('same_document_representation') or signals.get('explicit_primary_download')):
                    parent=next((row for row in previous if row['node_id']==origin.node_id),{})
                    mentions=list(dict.fromkeys([*mentions,*(parent.get('target_name_hints') or [])]))
                candidate.update(work_hint_id=work_hint[0] if work_hint else None,
                    target_name_hints=mentions[:8],work_selection='distinct_primary_works_v1')
            if transport and not discovery and origin:
                candidate.update(parent_requested_url=origin.query,parent_final_url=source_url)
            if key not in candidates or score > candidates[key]['score']:
                candidates[key] = candidate
    if transport:
        # Discovery rows can precede their acquired redirected version in the
        # ledger. Remove any candidate now known to be already read this task.
        candidates={key:row for key,row in candidates.items() if key not in requested}
    chosen, hosts, chosen_work_hints = [], {}, set()
    identity_count = sum(row.get('source_role') == 'identity' for row in previous)
    while candidates and len(chosen) < capacity:
        key = max(candidates, key=lambda key: (
            bool(diverse and candidates[key].get('identity_language_entrance')),
            bool(expanded and candidates[key].get('source_role')=='work' and candidates[key].get('explicit_full_text_link')),
            bool(diverse and candidates[key].get('source_role')=='work' and candidates[key].get('target_name_hints')),
            candidates[key].get('source_priority',0),
            candidates[key]['score'] - 2 * hosts.get(candidates[key]['host'], 0)))
        row = candidates.pop(key)
        if diverse and row.get('work_hint_id'):
            if row['work_hint_id'] in chosen_work_hints:continue
            chosen_work_hints.add(row['work_hint_id'])
        if focused and row['source_role'] == 'identity':
            if identity_count >= 4:
                continue
            identity_count += 1
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
                     'discovery_basis': {'evidence_id': row['evidence_id'],
                         'url': row.get('source_link_url',row['url']), 'read_url': row['url'], 'label': row['label']},
                     'depth': row['depth'], **{key: row[key] for key in (
                         'source_role', 'topic_terms', 'direct_topic_terms', 'explicit_full_text_link',
                         'parent_topic_used', 'selection_basis','source_priority','primary_link_inherited',
                         'identity_language_entrance','source_link_url','transport_upgrade',
                         'parent_requested_url','parent_final_url','work_hint_id','target_name_hints',
                         'work_selection') if key in row}})
    if not rows:
        return dag, manifest, []
    for node in dag.nodes:
        if node.node_type == 'analyst':
            node.depends_on += [row['node_id'] for row in rows]
    dag.edges = [PlanEdge(from_node=dependency, to_node=node.node_id)
                 for node in dag.nodes for dependency in node.depends_on]
    updated = deepcopy(manifest)
    updated.update(parent_plan_version=manifest['plan_version'], revision=int(manifest.get('revision', 0)) + 1,
                   reason='retained_discovery_requires_source_read', source_read_version=policy['version'],
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
