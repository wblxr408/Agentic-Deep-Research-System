"""Server-configured model routing; never grants endpoints, keys or tools."""
from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.llm_budget import TokenBudgetExceeded

VERSION='adrs-model-routing-v1'
STAGES=('planner','analyst','reflection','report','render')


class RouteCandidate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    route_id:str=Field(min_length=1,max_length=80)
    provider:str=Field(min_length=1,max_length=40)
    model:str=Field(min_length=1,max_length=100)
    stages:list[Literal['planner','analyst','reflection','report','render']]=Field(min_length=1,max_length=5)
    capabilities:set[Literal['json','stream','text']]=Field(default_factory=lambda:{'text'})
    quality_tier:int=Field(default=2,ge=1,le=5)
    data_classes:set[Literal['public','private','confidential','regulated']]=Field(default_factory=lambda:{'public'})
    context_tokens:int=Field(default=128000,ge=2048,le=2000000)
    input_usd_per_million:float|None=Field(default=None,ge=0,allow_inf_nan=False)
    output_usd_per_million:float|None=Field(default=None,ge=0,allow_inf_nan=False)
    price_source:str|None=Field(default=None,max_length=400)


class RoutingPolicy(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled:bool=False
    candidates:list[RouteCandidate]=Field(default_factory=list,max_length=32)
    allow_private_fallback:bool=False
    endpoint_data_classes:set[Literal['public','private','confidential','regulated']]=Field(default_factory=lambda:{'public','private'})
    fallback_data_classes:set[Literal['public','private','confidential','regulated']]=Field(default_factory=lambda:{'public','private'})
    max_capability_upgrades:int=Field(default=1,ge=0,le=2)

    @model_validator(mode='after')
    def distinct(self):
        if len({item.route_id for item in self.candidates})!=len(self.candidates):
            raise ValueError('duplicate_model_route_id')
        if self.enabled and not self.candidates:raise ValueError('model_routes_required')
        return self


def policy_data(policy):
    value=policy.model_dump(mode='json')
    for key in ('endpoint_data_classes','fallback_data_classes'):value[key]=sorted(value[key])
    for candidate in value['candidates']:
        candidate['capabilities']=sorted(candidate['capabilities'])
        candidate['data_classes']=sorted(candidate['data_classes'])
    return value


def _endpoint_identity(config):
    from app.query_understanding import identity
    from app.endpoint_resolver import resolve_endpoint
    base=config.get('api_base')
    parsed=urlsplit(base) if base else None
    if parsed and (parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('model_endpoint_requires_clean_base_url')
    endpoint=resolve_endpoint(str(config['provider']),str(config.get('api_key') or ''),base)
    parsed=urlsplit(str(endpoint.base_url))
    if parsed.scheme not in {'http','https'} or not parsed.hostname:
        raise ValueError('model_endpoint_requires_http_base_url')
    # No URL userinfo/query, key or headers are written into task state.
    return identity({'provider':config['provider'],'scheme':parsed.scheme,'host':parsed.hostname if parsed else None,
        'port':parsed.port if parsed else None,'path':parsed.path if parsed else None})


def freeze_model_routing(*, private:bool, deep:bool, complexity:str='moderate',data_class:str|None=None):
    from app.llm_client import get_llm_client_config
    config=get_llm_client_config()
    policy=RoutingPolicy.model_validate(config.get('routing') or {})
    return {'schema_version':VERSION,'policy':policy_data(policy),
        'endpoint_identity':_endpoint_identity(config),'provider':config['provider'],'primary_model':config['model'],
        'fallback_provider':config.get('fallback_provider'),'fallback_model':config.get('fallback_model'),
        'data_class':data_class or ('private' if private else 'public'),'deep':deep,'complexity':complexity,
        'authority':'configured_primary_endpoint_only_no_model_granted_egress'}


class BoundModelClient:
    """Non-secret route metadata survives provider budget wrappers/options."""
    def __init__(self,client,route_info,validator):
        self._client=client;self.route_info=route_info;self._validator=validator
    def __getattr__(self,name):return getattr(self._client,name)
    def validate_dispatch(self):self._validator()
    def with_options(self,**options):
        return BoundModelClient(self._client.with_options(**options),self.route_info,self._validator)


def validate_current(snapshot):
    from app.llm_client import get_llm_client_config
    config=get_llm_client_config()
    try:
        endpoint=_endpoint_identity(config)
        policy=policy_data(RoutingPolicy.model_validate(config.get('routing') or {}))
    except ValueError as error:
        raise TokenBudgetExceeded('model_routing_configuration_invalid') from error
    if (endpoint!=snapshot['endpoint_identity'] or config['model']!=snapshot['primary_model']
            or config.get('fallback_provider')!=snapshot.get('fallback_provider')
            or config.get('fallback_model')!=snapshot.get('fallback_model')
            or policy!=policy_data(RoutingPolicy.model_validate(snapshot['policy']))):
        error=TokenBudgetExceeded('model_routing_configuration_changed')
        error.routing_change={'expected':{'provider':snapshot.get('provider'),'model':snapshot.get('primary_model')},
            'current':{'provider':config.get('provider'),'model':config.get('model')},
            'endpoint_changed':endpoint!=snapshot['endpoint_identity'],
            'fallback_changed':(config.get('fallback_provider'),config.get('fallback_model'))!=
                (snapshot.get('fallback_provider'),snapshot.get('fallback_model')),
            'policy_changed':policy!=policy_data(RoutingPolicy.model_validate(snapshot['policy']))}
        raise error


def routed_binding(stage,snapshot,*,minimum_tier=0,minimum_context=0,exclude_models=(),preferred_route=None):
    from app.llm_client import get_llm_client_config,_create_client_for_config
    if stage not in STAGES or snapshot.get('schema_version')!=VERSION:
        raise TokenBudgetExceeded('model_route_contract_unavailable')
    config=get_llm_client_config()
    validate_current(snapshot)
    if _endpoint_identity(config)!=snapshot['endpoint_identity'] or config['provider']!=snapshot['provider']:
        raise TokenBudgetExceeded('model_endpoint_changed')
    policy=RoutingPolicy.model_validate(snapshot['policy'])
    private=snapshot['data_class']!='public'
    if snapshot['data_class'] not in policy.endpoint_data_classes:
        raise TokenBudgetExceeded('model_endpoint_data_class_not_allowed')
    required={'json'}|({'stream'} if stage=='report' else set())
    demanding=snapshot['deep'] or snapshot.get('complexity')=='complex'
    floor=3 if demanding and stage in {'analyst','reflection','report'} else (
        1 if stage=='render' or stage=='planner' and snapshot.get('complexity')=='simple' else 2)
    floor=max(floor,minimum_tier)
    context_need=max(minimum_context,{'planner':56000,'analyst':46000,'reflection':24000,'report':70000,'render':24000}[stage])
    excluded=[];eligible=[]
    for item in policy.candidates:
        reason=None
        if item.model in exclude_models:reason='already_used_model'
        elif preferred_route and item.route_id!=preferred_route:reason='different_pinned_route'
        elif item.provider!=config['provider']:reason='different_configured_provider'
        elif stage not in item.stages:reason='different_stage'
        elif snapshot['data_class'] not in item.data_classes:reason='data_egress_not_allowed'
        elif not required<=item.capabilities:reason='required_capability_missing'
        elif item.quality_tier<floor:reason='configured_quality_tier_too_low'
        elif item.context_tokens<context_need:reason='declared_context_too_small'
        if reason:excluded.append({'route_id':item.route_id,'reason':reason})
        else:eligible.append(item)
    if policy.enabled and not eligible:raise TokenBudgetExceeded('no_eligible_model_route')
    priced=[item for item in eligible if item.price_source and item.input_usd_per_million is not None
        and item.output_usd_per_million is not None]
    if policy.enabled:
        chosen=min(priced,key=lambda item:item.input_usd_per_million*context_need+item.output_usd_per_million*4096) if priced else next(
            (item for item in eligible if item.model==snapshot['primary_model']),eligible[0])
        model=chosen.model
        info={'route_id':chosen.route_id,'stage':stage,'provider':chosen.provider,'model':model,
            'quality_tier':chosen.quality_tier,
            'reason':'lowest_configured_price_among_eligible' if priced else 'eligible_price_unknown',
            'quality_basis':'configured_tier_not_task_quality_certification','data_class':snapshot['data_class'],
            'context_tokens':chosen.context_tokens,'excluded':excluded,
            'price':{'input_per_million':chosen.input_usd_per_million,'output_per_million':chosen.output_usd_per_million,
                'source':chosen.price_source} if chosen in priced else None}
    else:
        model=snapshot['primary_model']
        info={'route_id':'configured-primary','stage':stage,'provider':snapshot['provider'],'model':model,
            'reason':'routing_disabled_existing_primary','data_class':snapshot['data_class'],'price':None}
    info['requirements']={'configured_quality_floor':floor,'capabilities':sorted(required),
        'context_need':context_need,'complexity':snapshot.get('complexity')}
    client=BoundModelClient(_create_client_for_config({**config,'model':model}),info,lambda:validate_current(snapshot))
    fallback=None
    fallback_candidates=[item for item in policy.candidates if item.provider==config.get('fallback_provider')
        and item.model==config.get('fallback_model') and stage in item.stages
        and snapshot['data_class'] in item.data_classes and required<=item.capabilities
        and item.quality_tier>=floor and item.context_tokens>=context_need]
    fallback_capable=not policy.enabled or bool(fallback_candidates)
    if (config.get('fallback_api_key') and config.get('fallback_provider')==snapshot.get('fallback_provider')
            and config.get('fallback_model')==snapshot.get('fallback_model') and config.get('fallback_model')
            and fallback_capable and snapshot['data_class'] in policy.fallback_data_classes
            and (not private or policy.allow_private_fallback)):
        fallback_config={'provider':config['fallback_provider'],'model':config['fallback_model'],
            'api_key':config['fallback_api_key'],'api_base':None}
        fallback_info={'route_id':'configured-service-fallback','stage':stage,'provider':config['fallback_provider'],
            'model':config['fallback_model'],'reason':'service_failure_only','data_class':snapshot['data_class'],'price':None}
        if fallback_candidates:
            candidate=fallback_candidates[0]
            fallback_info['context_tokens']=candidate.context_tokens
            if candidate.price_source and candidate.input_usd_per_million is not None and candidate.output_usd_per_million is not None:
                fallback_info['price']={'input_per_million':candidate.input_usd_per_million,
                    'output_per_million':candidate.output_usd_per_million,'source':candidate.price_source}
        fallback=(BoundModelClient(_create_client_for_config(fallback_config),fallback_info,lambda:validate_current(snapshot)),config['fallback_model'])
    return client,model,fallback


def data_bound_snapshot(snapshot,context):
    from app.data_governance import RANK,model_class
    if context and RANK[context['data_class']]>RANK[snapshot['data_class']]:
        return {**snapshot,'data_class':model_class(context['data_class'])}
    return snapshot


def initialize_agent_client(agent,stage):
    snapshot=getattr(agent,'model_routing',None)
    if snapshot is None:return False
    context=getattr(getattr(agent,'request_budget',None),'data_governance',None)
    snapshot=data_bound_snapshot(snapshot,context)
    agent.model_routing=snapshot
    history=getattr(getattr(agent,'request_budget',None),'upgrade_history',[])
    prior=[item for item in history if item.get('stage')==stage and item.get('status')=='prepared']
    pinned=prior[-1].get('to_route') if prior else None
    agent._client,agent.model,agent.routed_fallback=routed_binding(stage,snapshot,preferred_route=pinned)
    if getattr(agent,'request_budget',None) is not None:
        agent.request_budget.context_limit=agent._client.route_info.get('context_tokens')
    if prior and prior[-1].get('trigger')=='context_gap':agent.context_expansion_bytes=72000
    if hasattr(agent,'provider'):agent.provider=snapshot['provider']
    return True


def prepare_capability_upgrade(agent,stage,trigger,*,evidence_present,details=None,required_tokens=2048):
    """One trusted, persisted decision; no confidence or permission authority."""
    from app.query_understanding import identity
    budget=getattr(agent,'request_budget',None);snapshot=getattr(agent,'model_routing',None) or {}
    decision={'stage':stage,'trigger':trigger,'status':'declined','details':details or {}}
    def finish(reason):
        decision['reason']=reason
        if budget is not None:budget.routing_decisions.append(dict(decision))
        return False
    if budget is None or not snapshot.get('policy',{}).get('enabled'):return finish('routing_not_enabled')
    if trigger=='entity_ambiguity':return finish('identity_clarification_required_not_model_guess')
    if trigger=='evidence_gap':return finish('acquire_or_retrieve_evidence_before_model_upgrade')
    if trigger not in {'format_failure','output_truncated','source_conflict','context_gap'}:
        return finish('unsupported_upgrade_trigger')
    if not evidence_present:return finish('retained_evidence_required')
    prior=[*budget.upgrade_history,*budget.capability_upgrades]
    maximum=int(snapshot['policy'].get('max_capability_upgrades',0))
    if len({item['upgrade_id'] for item in prior})>=maximum:return finish('root_upgrade_limit')
    current=getattr(getattr(agent,'_client',None),'route_info',None) or {}
    if current.get('provider')!=snapshot.get('provider') or current.get('quality_tier') is None:
        return finish('current_model_not_comparable')
    purpose='report' if stage in {'report','render'} else 'research'
    if budget.available(purpose)<required_tokens:return finish('original_allowance_insufficient')
    deadline=budget.call_deadline(purpose)
    import time
    if deadline is None or time.monotonic()>=deadline:return finish('original_deadline_exhausted')
    context=trigger=='context_gap'
    available=budget.limit-budget.spent-budget.inflight-(budget.audit_reserve if purpose!='audit' else 0)
    if context and available<=int(current.get('context_tokens') or 0):
        return finish('root_budget_not_model_capacity_is_limiting')
    try:
        client,model,fallback=routed_binding(stage,snapshot,
            minimum_tier=int(current['quality_tier'])+(0 if context else 1),
            minimum_context=int(current.get('context_tokens') or 0)+1 if context else 0,
            exclude_models=(current['model'],))
    except TokenBudgetExceeded as error:return finish(error.reason)
    callback=getattr(agent,'on_capability_upgrade',None)
    if callback is None:return finish('durable_upgrade_callback_required')
    decision.update(status='prepared',reason='larger_declared_context' if context else 'higher_configured_quality_tier',
        from_route=current['route_id'],from_model=current['model'],to_route=client.route_info['route_id'],to_model=model)
    decision['upgrade_id']='upgrade-'+identity({'history':[item['upgrade_id'] for item in prior],**decision})[:32]
    client.route_info['capability_upgrade']={key:decision[key] for key in ('upgrade_id','trigger','reason','from_model')}
    budget.capability_upgrades.append(dict(decision));budget.routing_decisions.append(dict(decision))
    # Durable root write precedes the new provider dispatch. A failed write
    # leaves the original client active and cannot silently spend a new call.
    callback(dict(decision))
    agent._client,agent.model,agent.routed_fallback=client,model,None
    budget.context_limit=client.route_info.get('context_tokens')
    if context:agent.context_expansion_bytes=72000
    return True
