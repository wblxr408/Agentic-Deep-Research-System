"""Source-located mechanism graphs, independent of runtime DAG scheduling."""
from __future__ import annotations

from copy import deepcopy
from typing import Literal
from pydantic import Field,model_validator
from app.research_scope import ScopeRecord,Identifier
from app.organization_relationships import RelationProof

POLICY='adrs-source-mechanism-graph-v1'
RELATIONS={'data_flow':'向其传递数据','control_flow':'控制或触发','dependency':'依赖','feedback':'向其反馈'}


class MechanismNode(ScopeRecord):
    node_id:Identifier
    label:str=Field(min_length=1,max_length=100)
    proofs:tuple[RelationProof,...]=Field(min_length=1,max_length=3)


class MechanismEdge(ScopeRecord):
    source:Identifier
    target:Identifier
    relation:Literal['data_flow','control_flow','dependency','feedback']
    label:str=Field(min_length=1,max_length=100)
    proofs:tuple[RelationProof,...]=Field(min_length=1,max_length=3)


class MechanismProposal(ScopeRecord):
    status:Literal['available','original_figure','insufficient_evidence']='insufficient_evidence'
    reason:str=Field(default='',max_length=500)
    figure_label:str|None=Field(default=None,min_length=2,max_length=120)
    nodes:tuple[MechanismNode,...]=Field(default=(),max_length=8)
    edges:tuple[MechanismEdge,...]=Field(default=(),max_length=12)

    @model_validator(mode='after')
    def valid_graph(self):
        import re
        ids={row.node_id for row in self.nodes}
        if len(ids)!=len(self.nodes):raise ValueError('mechanism_node_identity_duplicate')
        if any(edge.source not in ids or edge.target not in ids for edge in self.edges):
            raise ValueError('mechanism_edge_endpoint_missing')
        if self.status=='available' and (len(ids)<2 or not self.edges):raise ValueError('mechanism_graph_incomplete')
        if self.status=='original_figure' and (not self.figure_label or self.nodes or self.edges):
            raise ValueError('mechanism_original_requires_label_without_duplicate_graph')
        if self.status=='original_figure' and re.match(r'^(?:table\s*|表)',self.figure_label.strip(),re.I):
            raise ValueError('mechanism_original_requires_figure_not_table')
        if self.status=='insufficient_evidence' and (not self.reason.strip() or self.nodes or self.edges):
            raise ValueError('mechanism_gap_requires_reason_without_invented_graph')
        return self


def locate_graph(proposal,output,locate):
    if proposal.status=='original_figure':return {'policy':POLICY,'status':'source_figure_requested',
        'figure_label':proposal.figure_label,'reason':proposal.reason}
    if proposal.status!='available':return {'policy':POLICY,'status':proposal.status,'reason':proposal.reason}
    nodes=[{'id':row.node_id,'label':row.label,'proofs':[locate(proof,output,True) for proof in row.proofs]}
        for row in proposal.nodes]
    edges=[{**row.model_dump(exclude={'proofs'}),'proofs':[locate(proof,output,True) for proof in row.proofs]}
        for row in proposal.edges]
    return {'policy':POLICY,'status':'source_located_requires_semantic_review','nodes':nodes,'edges':edges,
        'reason':proposal.reason,'origin':'source_based_system_redrawing_not_original_paper_image'}


def _positions(nodes,edges):
    # Layout order is a display choice, not evidence for stages or causality.
    # Feedback/cyclic edges are retained; this is not a DAG admission check.
    outgoing={row['id']:[] for row in nodes};incoming={key:0 for key in outgoing};levels={key:0 for key in outgoing}
    for edge in edges:
        if edge['relation'] not in {'dependency','feedback'} and edge['source']!=edge['target']:
            outgoing[edge['source']].append(edge['target']);incoming[edge['target']]+=1
    queue=[key for key,value in incoming.items() if not value]
    for key in queue:
        for other in outgoing[key]:
            levels[other]=max(levels[other],levels[key]+1);incoming[other]-=1
            if not incoming[other]:queue.append(other)
    if any(incoming.values()) or max(levels.values(),default=0)>3 or not max(levels.values(),default=0) and len(nodes)>3:
        levels={row['id']:index//3 for index,row in enumerate(nodes)}
    columns={}
    for row in nodes:columns.setdefault(levels[row['id']],[]).append(row['id'])
    count=max(levels.values(),default=0)
    result={}
    for column,members in columns.items():
        for index,key in enumerate(members):
            result[key]={'x':.5 if not count else .14+.72*column/count,
                'y':.5 if len(members)==1 else .15+.7*index/(len(members)-1)}
    return result


def figure_label_key(value):
    import re
    value=re.sub(r'\([a-z]\)$','',value.strip(),flags=re.I).casefold()
    prefix=re.match(r'^(figure|fig\.?|table|图|表)\s*(.+)$',value)
    if not prefix:return re.sub(r'\s+','',value)
    kind='fig' if prefix[1] in {'figure','fig','fig.','图'} else 'table'
    return kind+re.sub(r'\s+','',prefix[2])


def build_mechanism_charts(findings,citations,used,quality,media):
    refs={row.get('locator',{}).get('evidence_id'):row['citation_id'] for row in citations
        if isinstance(row.get('locator'),dict) and row.get('citation_id')}
    metadata=findings.get('publication_metadata') or {};charts=[];requirements=[]
    coverage=quality.get('work_coverage') or []
    main={row['output_id'] for row in coverage if row.get('destination')=='main'}
    for card in (findings.get('technical_reading') or {}).get('cards',[]):
        source_ids=set((metadata.get(card['output_id']) or {}).get('evidence_ids') or [])
        source_ids.update(proof['evidence_id'] for field in card.get('fields',{}).values() for proof in field.get('proofs') or [])
        if not any(refs.get(key) in used for key in source_ids):continue
        if quality.get('coverage_complete') is not True or card['output_id'] not in main:continue
        graph=card.get('mechanism_graph') or {};contract=card.get('reading_contract') or {}
        profile=contract.get('profile','unknown') if contract.get('status')=='source_located_planning_judgment' else 'unknown'
        required=profile not in {'theoretical','synthesis'} and bool((card.get('fields',{}).get('mechanism') or {}).get('text'))
        requirement={'requirement_id':'mechanism:'+card['output_id'],'output_id':card['output_id'],
            'kind':'flow','module':'deep_dive','required':required,'status':'not_available',
            'reason':graph.get('reason') or 'structured_mechanism_not_acquired',
            'scope':'cited_work_mechanism_projection_not_complete_visual_requirements'}
        requirements.append(requirement)
        if graph.get('policy')==POLICY and graph.get('status')=='source_figure_requested':
            reference=graph.get('original_reference') or {}
            found=next(((page,figure) for page in (media or {}).get('pages') or []
                if card['output_id'] in page.get('output_ids',[]) for figure in page.get('figures') or []
                if figure_label_key(figure['label'])==figure_label_key(graph['figure_label'])),None)
            proof=reference.get('proof') or {};ref=refs.get(proof.get('evidence_id'))
            if found and ref:
                page,figure=found
                requirement.update(status='source_figure_referenced_pending_semantic_and_visual_review',
                    source_figure_id=figure['figure_id'],asset_id=page['asset_id'],page=page['page'],
                    source_claim=card['title']+'中的'+reference['label']+'用于展示其机制或架构。',
                    citation_ids=[ref],original_reference=deepcopy(reference),reason=None)
            else:requirement['reason']='mechanism_original_figure_unavailable'
            continue
        if graph.get('policy')!=POLICY or graph.get('status')!='source_located_requires_semantic_review':continue
        proofs=[proof for node in graph['nodes'] for proof in node['proofs']]+[proof for edge in graph['edges'] for proof in edge['proofs']]
        if not all(refs.get(proof['evidence_id']) for proof in proofs):
            requirement['reason']='mechanism_source_citation_unavailable';continue
        positions=_positions(graph['nodes'],graph['edges'])
        def sourced(row):return {**deepcopy(row),'citation_ids':list(dict.fromkeys(refs[p['evidence_id']] for p in row['proofs']))}
        chart_id='mechanism:'+card['output_id']
        charts.append({'chart_id':chart_id,'title':card['title']+'：来源机制／模块图','kind':'flow','module':'deep_dive',
            'output_id':card['output_id'],'mechanism_policy':POLICY,'unit_label':'来源组件与有向交互',
            'nodes':[{**sourced(row),**positions[row['id']]} for row in graph['nodes']],
            'edges':[sourced(row) for row in graph['edges']],
            'citation_ids':list(dict.fromkeys(refs[p['evidence_id']] for p in proofs)),
            'note':'按原文组件及有向关系重绘；数据／控制／依赖／反馈见连线说明，位置用于排版。'})
        requirement.update(status='descriptor_available_pending_review',chart_id=chart_id,reason=None)
    return charts,requirements


def checked_proofs(proofs,evidence,citation_sources,citations):
    expected=set();spans={}
    if not proofs:raise ValueError('mechanism_proofs_missing')
    for proof in proofs:
        source=evidence.get(proof['evidence_id']);start,end=proof.get('start'),proof.get('end')
        if (not source or type(start) is not int or type(end) is not int or not 0<=start<end<=len(source.content)
                or source.content[start:end]!=proof.get('quote') or source.source_url!=proof.get('source_url')
                or (source.acquisition or {}).get('coverage')=='discovery_only'):
            raise ValueError('mechanism_source_proof_changed')
        expected.add(proof['evidence_id']);spans.setdefault(proof['evidence_id'],[]).append(('mechanism',start,end))
    if {citation_sources.get(ref) for ref in citations}!=expected:raise ValueError('mechanism_citation_binding_changed')
    return spans
