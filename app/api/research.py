"""
Research API endpoints: SSE streaming and research session management.
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from app.channels.models import ChannelName
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.core.time import utc_now_naive
from app.db.connection import get_db_pool
from app.db.json import dumps_json
from app.db.matching import load_matching_snapshot, save_matching_snapshot
from app.db.presets import PresetInput, PresetUpdate, load_preset, insert_preset, preset_record
from app.db.report_delivery import TemplateSave,load_template,save_template,template_record
from app.disclosure import projection,redact_text,report_history_projection,VERSION as DISCLOSURE_VERSION
from app.research_quality import QualityFeedback,quality_view,compare_quality
from app.db.research_quality import load_quality_state,load_feedback,save_feedback
from app.execution_control import controlled_execution,current_control,check_execution,signal_cancellation
from app.db.execution_control import cancel_execution,receipt_budget
from app.governance import RuntimePersistence
from app.governance.runtime import normalize_tool_audit_rows, public_status_from_runtime
from app.graph.compiler import compile_research_graph
from app.graph.state import (
    RuntimeStatus,
    TaskStatus,
    create_initial_state,
)
from app.guardrails import (
    build_guardrail_decision,
    build_review_status,
    compose_guardrail_prompt,
    get_research_budget,
    normalize_research_length,
)
from app.observability.sse_manager import get_sse_manager
from app.research_scope import (
    OrganizationScopePreview,
    OrganizationScopePreviewRequest,
    preview_organization_scope,
)
from app.research_evaluation import (
    EvaluationContext, EvaluationPreview, EvaluationRequest, OpenAlexNormalization, OpenAlexNormalizationRequest,
    applicability, normalize_openalex, preview_evaluation, public_sources, scheme_catalogue,
)
from app.research_matching import (
    MatchingPreview, MatchingPreviewRequest, MatchingSnapshotCreated, MatchingSnapshotInput,
    WeightConfigurationPreview, WeightConfigurationRequest, load_preset_catalogue, preview_weights, score_matching_snapshot,
)
from app.security.auth import Principal, require_principal
from app.model_scope import bind_owner_model, owner_model_execution
from app.organization_runtime import OrganizationResearchRequest, freeze_organization_request
from app.organization_taxonomy import ReclassificationRequest, freeze_taxonomy, classify_publications
from app.organization_relationships import RelationshipPreviewRequest, build_relationship_view
from app.organization_deep_dive import TechnicalPreviewRequest, build_technical_cards
from app.organization_trends import TrendPreviewRequest, build_trend_view
from app.organization_actions import ActionPreviewRequest, build_action_view
from app.organization_statistics import build_statistics, apply_statistics
from app.skills import get_skill_registry
from app.query_understanding import QueryOptions, DeliveryRequest, interpret_query, context_entities, identity
from app.planning_control import PlanningPolicy
from app.skills.stages import compile_stage_skills, preparation_view

logger = logging.getLogger(__name__)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


router = APIRouter(prefix="/api/v1/research", tags=["research"], dependencies=[Depends(require_principal)])
principal_dependency = Depends(require_principal)

from app.api.layout_samples import router as layout_samples_router
router.include_router(layout_samples_router)


@router.get('/analysis/catalog')
def organization_analysis_catalogue():
    """Read-only question/module options; no new data or tool permissions."""
    from app.organization_purpose import analysis_catalogue
    return analysis_catalogue()


@router.get('/delivery-templates')
async def list_delivery_templates(principal:Principal=principal_dependency):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        rows=await conn.fetch('''SELECT DISTINCT ON(template_id) * FROM research_delivery_templates
            WHERE owner_id=$1::uuid ORDER BY template_id,version DESC''',_principal_id(principal))
    return {'items':[template_record(row) for row in rows],'scope':'current_owner_only_project_label_is_not_shared_acl'}


@router.post('/delivery-templates',status_code=201)
async def create_delivery_template(request:TemplateSave,principal:Principal=principal_dependency):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        try:return await save_template(conn,_principal_id(principal),request)
        except ValueError as error:raise HTTPException(409,str(error)) from error


@router.get('/delivery-templates/{template_id}/versions')
async def delivery_template_versions(template_id:uuid.UUID,principal:Principal=principal_dependency):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        rows=await conn.fetch('''SELECT * FROM research_delivery_templates WHERE owner_id=$1::uuid
            AND template_id=$2::uuid ORDER BY version DESC''',_principal_id(principal),str(template_id))
    if not rows:raise HTTPException(404,'Template not found')
    return {'items':[template_record(row) for row in rows]}


@router.get('/delivery-templates/{template_id}')
async def get_delivery_template(template_id:uuid.UUID,version:int|None=Query(default=None,ge=1),principal:Principal=principal_dependency):
    pool=await get_db_pool()
    async with pool.acquire() as conn:result=await load_template(conn,_principal_id(principal),template_id,version)
    if not result:raise HTTPException(404,'Template not found')
    return result


@router.put('/delivery-templates/{template_id}')
async def revise_delivery_template(template_id:uuid.UUID,request:TemplateSave,principal:Principal=principal_dependency):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        try:return await save_template(conn,_principal_id(principal),request,template_id)
        except ValueError as error:raise HTTPException(404 if str(error)=='template_not_found' else 409,str(error)) from error


@router.post('/presets', status_code=201)
async def create_personal_preset(request: PresetInput, principal: Principal = principal_dependency):
    pool = await get_db_pool()
    async with pool.acquire() as connection:
        return await insert_preset(connection, principal.id, request)


@router.get('/presets')
async def list_personal_presets(principal: Principal = principal_dependency):
    pool = await get_db_pool()
    async with pool.acquire() as connection:
        rows = await connection.fetch('SELECT DISTINCT ON (preset_id) * FROM organization_weight_presets WHERE owner_id=$1::uuid ORDER BY preset_id,version DESC', principal.id)
    return {'items': [preset_record(row) for row in rows]}


@router.get('/presets/{preset_id}')
async def get_personal_preset(preset_id: uuid.UUID, version: int | None = Query(default=None, ge=1), principal: Principal = principal_dependency):
    pool = await get_db_pool()
    async with pool.acquire() as connection:
        result = await load_preset(connection, principal.id, str(preset_id), version)
    if result is None:
        raise HTTPException(status_code=404, detail='Preset not found')
    return result


@router.get('/presets/{preset_id}/versions')
async def personal_preset_versions(preset_id: uuid.UUID, principal: Principal = principal_dependency):
    pool = await get_db_pool()
    async with pool.acquire() as connection:
        rows = await connection.fetch('SELECT * FROM organization_weight_presets WHERE preset_id=$1::uuid AND owner_id=$2::uuid ORDER BY version DESC', str(preset_id), principal.id)
    if not rows:
        raise HTTPException(status_code=404, detail='Preset not found')
    return {'items': [preset_record(row) for row in rows]}


@router.put('/presets/{preset_id}')
async def update_personal_preset(preset_id: uuid.UUID, request: PresetUpdate, principal: Principal = principal_dependency):
    pool = await get_db_pool()
    async with pool.acquire() as connection, connection.transaction():
        # One owner's edits serialize on its existing identity row. Old revisions
        # are immutable, and an expected version prevents a stale second writer.
        await connection.fetchval('SELECT id FROM auth_principals WHERE id=$1::uuid FOR UPDATE', principal.id)
        latest = await load_preset(connection, principal.id, str(preset_id))
        if latest is None:
            raise HTTPException(status_code=404, detail='Preset not found')
        if request.expected_version != latest['version']:
            raise HTTPException(status_code=409, detail='Preset version changed')
        return await insert_preset(connection, principal.id, request, identifier=str(preset_id), version=latest['version'] + 1)


@router.post("/scope/preview", response_model=OrganizationScopePreview)
def preview_research_scope(request: OrganizationScopePreviewRequest) -> OrganizationScopePreview:
    """Validate supplied organization records and preview attribution without I/O."""
    return preview_organization_scope(request)


@router.post("/evaluation/preview", response_model=EvaluationPreview)
def preview_research_evaluation(request: EvaluationRequest) -> EvaluationPreview:
    """Apply exact-identity evaluation adapters to public snapshots or provided records."""
    return preview_evaluation(request)


@router.post("/evaluation/openalex/normalize", response_model=OpenAlexNormalization)
def normalize_openalex_evaluation(request: OpenAlexNormalizationRequest) -> OpenAlexNormalization:
    """Convert a supplied OpenAlex work into provider-specific paper metrics."""
    return normalize_openalex(request)


@router.post("/weights/preview", response_model=WeightConfigurationPreview)
def preview_research_weights(request: WeightConfigurationRequest) -> WeightConfigurationPreview:
    """Normalize versioned preference weights without fetching or ranking candidates."""
    return preview_weights(request)


@router.get('/weights/catalog')
def weight_editor_catalogue():
    """Read the same versioned defaults as research creation, without model/network I/O."""
    catalogue = load_preset_catalogue()
    return {'version': catalogue.version, 'presets': {
        key: preview_weights(WeightConfigurationRequest(preset=key), catalogue).model_dump(mode='json')
        for key in catalogue.presets}}


@router.post('/evaluation/applicability')
def evaluation_context(request: EvaluationContext):
    """Classify context without inventing a work identity or pretending to query it."""
    sources = public_sources()
    return {'request': request.model_dump(mode='json'), 'live_fetch': False,
        'exact_identity_checked': False, 'items': [
            {**scheme.model_dump(mode='json'), 'applicable': applicability(scheme.scheme_id, request)[0],
             'reason': applicability(scheme.scheme_id, request)[1],
             'source_access': 'public_sample' if any(source.scheme_id == scheme.scheme_id for source in sources) else 'import_only',
             'source_versions': [{'edition': source.edition, 'metric_year': source.metric_year,
                                  'provider': source.provider, 'source_url': str(source.source_url)}
                                 for source in sources if source.scheme_id == scheme.scheme_id]}
            for scheme in scheme_catalogue()]}


@router.post("/matching/snapshots", response_model=MatchingSnapshotCreated, status_code=201)
async def create_matching_snapshot(request: MatchingSnapshotInput, principal: Principal = principal_dependency):
    """Freeze explicitly supplied evidence; optional session binding must belong to this owner."""
    if request.origin != 'explicit_records' or request.source_execution_id or request.bridge_version or request.bridge_notes:
        raise HTTPException(status_code=422, detail='研究来源标记只能由保存会话生成，不能由调用方声明。')
    pool = await get_db_pool()
    async with pool.acquire() as connection:
        identifier = await save_matching_snapshot(connection, principal.id, request)
    if identifier is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return MatchingSnapshotCreated(snapshot_id=identifier, evidence_cutoff=request.evidence_cutoff,
                                   schema_version=request.schema_version)


@router.post("/matching/preview", response_model=MatchingPreview)
async def preview_research_matching(request: MatchingPreviewRequest, principal: Principal = principal_dependency):
    """Reweight the owner's frozen snapshot without collection, models or writes."""
    pool = await get_db_pool()
    async with pool.acquire() as connection:
        snapshot = await load_matching_snapshot(connection, principal.id, str(request.snapshot_id))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Matching snapshot not found")
    return await asyncio.to_thread(score_matching_snapshot, snapshot, request.configuration, str(request.snapshot_id))


@router.post('/{session_id}/matching/snapshot')
async def create_session_matching_snapshot(session_id: uuid.UUID, principal: Principal = principal_dependency):
    """Freeze this owner's saved outputs once per completed execution, without collection."""
    from app.research_matching_bridge import BRIDGE_VERSION, snapshot_from_research
    pool = await get_db_pool()
    async with pool.acquire() as connection, connection.transaction():
        row = await connection.fetchrow('''SELECT id,status,execution_id,completed_at,review_status,final_report
            FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',str(session_id),principal.id)
        if row is None:
            raise HTTPException(status_code=404, detail='Session not found')
        if row['status'] != 'completed' or not row['final_report'] or row['completed_at'] is None:
            raise HTTPException(status_code=409, detail='请等本次研究完成，再冻结证据重排。')
        review = _json_object(row['review_status'])
        config = review.get('organization_research')
        if not config:
            raise HTTPException(status_code=409, detail='这份会话不是组织研究。')
        identifier = await connection.fetchval('''SELECT id FROM research_matching_snapshots
            WHERE session_id=$1::uuid AND owner_id=$2::uuid AND payload->>'bridge_version'=$3
              AND payload->>'source_execution_id'=$4 LIMIT 1''',str(session_id),principal.id,BRIDGE_VERSION,str(row['execution_id']))
        if identifier:
            snapshot = await load_matching_snapshot(connection,principal.id,str(identifier))
        else:
            state = _json_object(await connection.fetchval('SELECT state_snapshot_json FROM session_runtime_state WHERE session_id=$1::uuid',str(session_id)))
            try:
                snapshot = snapshot_from_research(str(session_id),str(row['execution_id']),row['completed_at'],
                    config,review.get('organization_result'),state)
            except (ValueError, KeyError, TypeError) as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            identifier = await save_matching_snapshot(connection,principal.id,snapshot)
    return {'snapshot_id':str(identifier),'snapshot':snapshot.model_dump(mode='json'),
            'initial_configuration':config['effective_weights']}


ACCUMULATING_STATE_KEYS = {
    "agent_trace",
    "tool_histories",
    "collected_evidence",
    "search_results",
    "browser_results",
    "rag_results",
    "aggregated_evidence",
    "node_outcomes",
    "pending_approvals",
}

KNOWN_STATE_KEYS = {
    'tool_handoffs', 'tool_result_envelopes', 'accepted_tool_operations',
    'planning_policy', 'plan_manifest', 'plan_history', 'iteration_control',
    'query_understanding',
    'evidence_ledger',
    'evidence_access_gaps',
    "organization_research",
    "organization_result",
    "task_id",
    "user_query",
    "created_at",
    "status",
    "session",
    "dag",
    "current_executing_nodes",
    "completed_nodes",
    "node_outcomes",
    "tool_histories",
    "collected_evidence",
    "search_results",
    "browser_results",
    "rag_results",
    "aggregated_evidence",
    "verification",
    "revision_needed",
    "revision_count",
    "analysis",
    "final_report",
    "citations",
    "guardrail_decision",
    "evidence_status",
    "review_status",
    "user_confirmed",
    "use_internal_docs",
    "rag_group",
    "retrieval_policy",
    "runtime_status",
    "budget_state",
    "pending_approvals",
    "agent_trace",
    "guardrail_trace",
    "errors",
}


def _principal_id(principal: Principal | Any) -> str | None:
    """Keep direct unit calls compatible; HTTP requests always receive a Principal."""
    return principal.id if isinstance(principal, Principal) else None


def _iter_state_updates(chunk: dict[str, Any]):
    """Yield state update mappings from raw LangGraph stream chunks."""
    if any(key in KNOWN_STATE_KEYS for key in chunk):
        yield chunk
        return

    for value in chunk.values():
        if isinstance(value, dict):
            yield value


def _normalize_citations(value: Any) -> list[dict[str, Any]]:
    """Return citations as a list of dicts regardless of stored shape."""
    if isinstance(value,str):
        try:value=json.loads(value)
        except ValueError:return []
    if isinstance(value, list):
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(item)
            else:
                normalized.append({"value": item})
        return normalized
    if isinstance(value, dict):
        return [value]
    return []


def _normalize_tool_audit_rows(
    session_id: str,
    tool_histories: list[dict[str, Any]],
    node_outcomes: list[dict[str, Any]],
) -> list[tuple[Any, ...]]:
    """Backward-compatible wrapper around governance runtime normalization."""
    return normalize_tool_audit_rows(
        session_id=session_id,
        tool_histories=tool_histories,
        node_outcomes=node_outcomes,
    )


# ==============================================================
# Request/Response Models
# ==============================================================

class ResearchRequest(BaseModel):
    """Request body for starting a research task."""
    query: str = Field(..., min_length=5, max_length=2000, description="Research query")
    channels: list[ChannelName] = Field(default_factory=list, max_length=8)
    organization_research: OrganizationResearchRequest | None = None
    query_options: QueryOptions = Field(default_factory=QueryOptions)
    delivery: DeliveryRequest = Field(default_factory=DeliveryRequest)
    query_preview_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    planning_policy: PlanningPolicy = Field(default_factory=PlanningPolicy)

    @field_validator('query')
    @classmethod
    def nonblank_query(cls, value):
        if len(value.strip()) < 5:
            raise ValueError('query needs at least five non-padding characters')
        return value.strip()

    @model_validator(mode='after')
    def constrained_corpus_channels(self):
        if self.organization_research and self.organization_research.corpus.source_scope:
            if any(channel != 'web' for channel in self.channels):
                raise ValueError('restricted corpus currently supports web transport; choose source groups independently')
        return self

    @field_validator("channels")
    @classmethod
    def unique_channels(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("channels must be unique")
        return value
    session_id: str | None = Field(default=None, description="Optional new session ID; existing IDs may only confirm their original pending request")
    max_revision: int = Field(default=3, ge=1, le=5, description="Max revision loops")
    user_confirmed: bool = Field(default=False, description="User confirmed high-risk task")
    use_internal_docs: bool = Field(
        default=False,
        description="Supplement public web research with the current user's internal documents.",
    )
    rag_group: str | None = Field(
        default=None,
        max_length=100,
        description="Internal document group filter, used only when use_internal_docs is true.",
    )
    output_length: str = Field(
        default="medium",
        description="Output length: short, medium, long.",
    )
    enabled_skill_ids: list[str] = Field(
        default_factory=list, max_length=32,
        description="Explicitly enable selected skill IDs for this session.",
    )
    disabled_skill_ids: list[str] = Field(
        default_factory=list, max_length=32,
        description="Explicitly disable selected skill IDs for this session.",
    )
    skill_tenant_id: str | None = Field(
        default=None,
        max_length=100,
        description="Optional tenant scope for skill resolution.",
    )
    skill_project_id: str | None = Field(
        default=None,
        max_length=100,
        description="Optional project scope for skill resolution.",
    )


class ResearchStatus(BaseModel):
    """Response for research status query."""
    session_id: str
    status: str
    created_at: str
    updated_at: str | None = None
    runtime_status: str | None = None
    requires_confirmation: bool = False
    pending_approval_count: int = 0
    budget_state: dict[str, Any] | None = None
    last_error_category: str | None = None
    execution_id:str|None=None
    cancellation:dict[str,Any]|None=None


class CancellationRequest(BaseModel):
    request_id:uuid.UUID
    execution_id:uuid.UUID|None


def _same_research_request(stored, current):
    """Only omit newly introduced defaults for legacy pending confirmations."""
    previous, actual = dict(stored), dict(current)
    defaults = {'query_options': QueryOptions().model_dump(mode='json'),
        'delivery': DeliveryRequest().model_dump(mode='json'), 'query_preview_id': None,
        'planning_policy': PlanningPolicy().model_dump(mode='json')}
    for key, default in defaults.items():
        if key not in previous and actual.get(key) == default:
            actual.pop(key, None)
        elif isinstance(previous.get(key), dict) and isinstance(actual.get(key), dict) and isinstance(default, dict):
            narrowed = dict(actual[key])
            for field, fallback in default.items():
                if field not in previous[key] and narrowed.get(field) == fallback:
                    narrowed.pop(field, None)
            actual[key] = narrowed
    return previous == actual


def _task_tool_allowlist(skill_context: dict, decision_tools: list[str]) -> list[str]:
    compilation = skill_context.get('stage_compilation')
    if compilation is not None:
        return list(compilation.get('dispatch_tools', [])) if compilation.get('ready') else []
    return skill_context.get('effective_tool_allowlist') or decision_tools


class ResearchResponse(BaseModel):
    """Response for research creation."""
    session_id: str
    status: str
    message: str
    requires_confirmation: bool = False
    output_length: str = "medium"
    budget: dict[str, int | float] = Field(default_factory=dict)
    skill_context: dict[str, Any] = Field(default_factory=dict)


class ToolCallAuditRecord(BaseModel):
    """Single persisted tool call audit row."""
    call_id: str
    session_id: str
    node_id: str | None = None
    agent_type: str
    tool_name: str
    args_json: dict[str, Any] = Field(default_factory=dict)
    args_hash: str | None = None
    status: str
    error_category: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    result_summary: str | None = None
    result_hash: str | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    decision_id: str | None = None
    approved_by: str | None = None
    server_fingerprint: str | None = None
    safety_json: dict[str, Any] = Field(default_factory=dict)
    usage_source: str | None = None
    estimated: bool = False
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None


class ApprovalRequestRecord(BaseModel):
    approval_id: str
    session_id: str
    node_id: str | None = None
    tool_name: str
    risk_level: str
    reason: str | None = None
    request_payload_json: dict[str, Any] = Field(default_factory=dict)
    status: str
    requested_at: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None
    comment: str | None = None


class ApprovalActionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    approved_by: str = Field(..., min_length=1, max_length=100)
    comment: str | None = Field(default=None, max_length=1000)


# ==============================================================
# SSE Event Streaming
# ==============================================================

async def research_event_generator(
    session_id: str,
    *, authorize=None,execution_id=None,enforce_execution=False,last_event_id=None,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    SSE event generator for research progress.
    Yields events as SSE-compatible dictionaries.
    """
    sse = get_sse_manager()

    try:
        # Stream events from the queue
        options={'authorize':authorize,'last_event_id':last_event_id}
        if enforce_execution:options['execution_id']=execution_id
        async for event in sse.stream(session_id,**options):
            yield event
    except asyncio.CancelledError:
        logger.info(f"SSE stream cancelled for session {session_id}")
        raise


async def _owned_session_exists(session_id: str, owner_id: str) -> bool:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return bool(await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM research_sessions WHERE id = $1::uuid AND owner_id = $2::uuid)",
            session_id,
            owner_id,
        ))


@router.get("/stream/{session_id}")
async def stream_research(session_id: str, request: Request, principal: Principal = principal_dependency):
    """
    SSE endpoint for real-time research progress streaming.

    Clients should connect with:
        const eventSource = new EventSource(`/api/v1/research/stream/${sessionId}`);

    Event types:
    - connected: Initial connection confirmation
    - agent_start/end: Agent execution lifecycle
    - thought: LLM reasoning process
    - tool_call/result/error: Tool invocations
    - state_update: Workflow state changes
    - reflection: Reflection result
    - report_chunk: Report content chunks
    - done: Task completion
    - workflow_error: Workflow/business error occurred
    """
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        binding=await conn.fetchrow('SELECT execution_id FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid',session_id,principal.id)
    if binding is None:raise HTTPException(status_code=404,detail='Session not found')
    execution_id=str(binding['execution_id']) if binding['execution_id'] else None
    from app.security.auth import stream_principal_valid
    return EventSourceResponse(
        research_event_generator(session_id,execution_id=execution_id,enforce_execution=True,
            last_event_id=request.headers.get('last-event-id'),
            authorize=lambda: stream_principal_valid(principal, session_id,execution_id=execution_id,enforce_execution=True)),
        media_type="text/event-stream",
    )


# ==============================================================
# Research Task Management
# ==============================================================

async def _prepare_query_understanding(conn, request: ResearchRequest, principal: Principal,
        skill_context: dict, budget: dict, decision):
    selected_preset = None
    selected_template = None
    if request.delivery.copied_from_template:
        origin=request.delivery.copied_from_template
        selected_template=await load_template(conn,_principal_id(principal),origin.template_id,origin.version)
        if not selected_template:
            raise HTTPException(404,'Template origin not found')
    if request.organization_research and request.organization_research.weight_preset:
        reference = request.organization_research.weight_preset
        selected_preset = await load_preset(conn, principal.id, str(reference.preset_id), reference.version)
        if selected_preset is None:
            raise HTTPException(status_code=404, detail='Preset not found')
    organization = freeze_organization_request(request.organization_research, selected_preset)
    context = None
    if request.query_options.context_session_id:
        row = await conn.fetchrow('''SELECT review_status,request_payload,execution_id FROM research_sessions
            WHERE id=$1::uuid AND owner_id=$2::uuid''', str(request.query_options.context_session_id), principal.id)
        if not row:
            raise HTTPException(status_code=404, detail='Context session not found')
        try:
            context = context_entities(_json_object(row['review_status']), _json_object(row['request_payload']))
            context['configuration_id'] += ':' + str(row['execution_id'] or '')
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
    base_tools = set(decision.enabled_tools)
    if not request.use_internal_docs:
        base_tools.discard('rag')
    needed_stages = base_tools | {'planner','analyst','reflection','report'}
    if (request.delivery.template != 'markdown-v1' or request.delivery.drawing_mode != 'builtin'
            or any(format != 'markdown' for format in request.delivery.formats)):
        needed_stages.add('render')
    try:
        compilation = compile_stage_skills(skill_context, task_tools=base_tools,
            disciplines=list(((organization or {}).get('scope') or {}).get('disciplines') or request.query_options.disciplines),
            template=request.delivery.template, char_budget=request.planning_policy.stage_context_chars,
            needed_stages=needed_stages)
    except ValueError:
        raise HTTPException(status_code=422, detail='stage_skill_configuration_unavailable') from None
    skill_context['stage_compilation'] = compilation
    skill_context['effective_tool_allowlist'] = list(compilation['dispatch_tools'])
    from app.document_structure import VERSION as DOCUMENT_PARSER_VERSION
    parsing=get_settings().document_parsing
    rag_settings=get_settings().rag
    internal_settings={}
    if 'sparse' in request.query_options.internal_channels:
        internal_settings['sparse']={'model':rag_settings.sparse_model,'revision':rag_settings.sparse_revision,
            'max_input_tokens':rag_settings.sparse_max_input_tokens,'top_k':rag_settings.sparse_top_k}
    if set(request.query_options.internal_channels)&{'paired','late'}:
        from app.multivector import paired_configuration
        try:internal_settings['paired']=paired_configuration()
        except ValueError:internal_settings['paired']={'status':'unconfigured'}
    if 'image' in request.query_options.internal_channels:
        from app.multimodal import configuration as multimodal_configuration
        try:internal_settings['image']=multimodal_configuration()
        except ValueError:internal_settings['image']={'status':'unconfigured'}
    if 'beam' in request.query_options.internal_channels:
        from app.retrieval_beam import policy as beam_policy
        internal_settings['beam']=beam_policy()
    limits = {'budget': budget, 'max_revision': request.max_revision,
        'document_parser_policy':{'schema_version':DOCUMENT_PARSER_VERSION,**{key:getattr(parsing,key)
            for key in ('ocr_enabled','ocr_language','max_ocr_pages','max_chars','timeout_seconds')}},
        'planning_policy': request.planning_policy.model_dump(mode='json'),
        'skill_compilation_id': compilation['compilation_id'],
        'output_length': normalize_research_length(request.output_length).value,
        'channels': list(request.channels), 'use_internal_docs': request.use_internal_docs,
        'internal_retrieval_settings':internal_settings,
        'rag_group': request.rag_group if request.use_internal_docs else None,
        'effective_tool_allowlist': compilation['dispatch_tools']}
    try:
        snapshot = interpret_query(request.query, request.query_options, request.delivery,
            owner_id=principal.id, organization=organization, skill_context=skill_context,
            request_limits=limits, context=context)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    if selected_template:
        try:
            original=DeliveryRequest.model_validate(selected_template['configuration']).model_dump(mode='json')
        except ValueError:
            # A historical revision can remain a valid origin even if its old
            # configuration needs adjustment before a new task can use it.
            original=deepcopy(selected_template['configuration'])
        effective=request.delivery.model_dump(mode='json')
        # Origin metadata is not part of the editable layout itself. The task
        # keeps its actual layout/drawing configuration alongside this revision.
        original.pop('copied_from_template',None);effective.pop('copied_from_template',None)
        snapshot['delivery']['template_revision']={
            'template_id':selected_template['template_id'],'version':selected_template['version'],
            'modified_for_task':original!=effective,
            'effective_configuration':'frozen_in_this_delivery_snapshot'}
    snapshot['context_candidates'] = (context or {}).get('entities', [])
    conflicts = [*compilation['conflicts'], *[{'stage': stage, **conflict}
        for stage, profile in compilation['profiles'].items() for conflict in profile['conflicts']]]
    snapshot['execution_preparation'] = {'skill_compilation_id': compilation['compilation_id'],
        'ready': compilation['ready'], 'conflicts': conflicts,
        'stages':preparation_view(compilation,skill_context),
        'planning_policy': request.planning_policy.model_dump(mode='json')}
    if not compilation['ready']:
        snapshot['ready'] = False
        names = {item['skill_id']: item.get('name', item['skill_id']) for item in skill_context.get('resolved_skills', [])}
        reasons = {'required_tools_not_permitted': '需要的工具不在当前许可内',
            'manual_skill_selected_and_excluded': '同时选择了启用和禁用',
            'explicit_skill_disables_stage_tool': '手选方法限制了本阶段需要的工具',
            'required_skill_context_exceeds_budget': '必要技能内容超出上下文预算',
            'registered_inline_reference_missing': '缺少已声明的内联参考内容',
            'manual_skill_unavailable_or_not_resolved': '手选技能不可用或尚未成功解析',
            'manual_skill_has_no_requested_stage': '手选技能不适用于本次执行阶段',
            'discipline_not_matched': '适用学科与本次研究不一致', 'discipline_not_declared': '缺少技能要求的学科信息',
            'different_template': '所选模板与技能适用模板不同',
            'registered_skill_sections_ambiguous': '已注册技能包含重复指令或参考章节'}
        for conflict in conflicts:
            snapshot['clarifications'].append({'id': 'stage_skill_conflict',
                'message': f"技能“{names.get(conflict.get('skill_id'), '当前选择')}”：{reasons.get(conflict['reason'], '配置无法生效')}。请调整技能选择、范围或上下文预算。",
                'skill_conflict': conflict})
    if not compilation['dispatch_tools']:
        snapshot['ready'] = False
        snapshot['clarifications'].append({'id': 'no_eligible_evidence_tools',
            'message': '当前任务与技能限制的交集中没有可用取证工具，请调整选择；系统不会扩大许可启动研究。'})
    snapshot['interpretation_id'] = identity({'query_contract': snapshot['interpretation_id'],
        'skill_compilation_id': compilation['compilation_id'],
        **({'template_revision':snapshot['delivery']['template_revision']} if selected_template else {})})
    return organization, snapshot


@router.post('/understanding')
async def preview_query_understanding(request: ResearchRequest, principal: Principal = principal_dependency):
    """Read-only interpretation; no new research, tools or model calls."""
    try:
        async with asyncio.timeout(15):
            decision = build_guardrail_decision(request.query + '\n' + request.query_options.additional_constraints, user_confirmed=request.user_confirmed)
            skill_context = (await get_skill_registry(principal.id).resolve_for_session(
                query=request.query, manually_enabled_skill_ids=request.enabled_skill_ids,
                manually_disabled_skill_ids=request.disabled_skill_ids,
                tenant_id=request.skill_tenant_id, project_id=request.skill_project_id)).as_dict()
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                _, snapshot = await _prepare_query_understanding(conn, request, principal, skill_context,
                    get_research_budget(normalize_research_length(request.output_length)), decision)
    except TimeoutError:
        raise HTTPException(status_code=503, detail='query_preview_temporarily_unavailable') from None
    return snapshot


@router.post("", response_model=ResearchResponse)
async def create_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
    principal: Principal = principal_dependency,
):
    """
    Start a new research task.

    Creates a research session, saves it to the database,
    and dispatches the LangGraph workflow to run in background.
    """
    await bind_owner_model(principal.id)
    from app.llm_client import get_llm_client_config
    try:
        model_config = get_llm_client_config()
        if not model_config.get('api_key') and model_config.get('provider') != 'ollama':
            raise ValueError('personal_model_configuration_required')
    except ValueError:
        raise HTTPException(409, 'personal_model_configuration_required') from None
    # Generate or use provided session ID
    session_id = request.session_id or str(uuid.uuid4())
    execution_id = str(uuid.uuid4())
    decision = build_guardrail_decision(request.query + '\n' + request.query_options.additional_constraints, user_confirmed=request.user_confirmed)
    output_length = normalize_research_length(request.output_length)
    budget = get_research_budget(output_length)
    skill_context = (await get_skill_registry(_principal_id(principal)).resolve_for_session(
        query=request.query,
        manually_enabled_skill_ids=request.enabled_skill_ids,
        manually_disabled_skill_ids=request.disabled_skill_ids,
        tenant_id=request.skill_tenant_id,
        project_id=request.skill_project_id,
    )).as_dict()

    logger.info(f"Creating research session: {session_id}, query: {request.query[:50]}")

    # Save to database
    pool = await get_db_pool()
    request_payload = request.model_dump(mode="json", exclude={"session_id", "user_confirmed"})
    if request.organization_research and request.organization_research.weight_preset:
        request_payload['organization_research']['weight_preset'] = request.organization_research.weight_preset.model_dump(mode='json')
        request_payload['organization_research'].pop('weights', None)
    async with pool.acquire() as conn, conn.transaction():
        pending = None
        if request.session_id and request.user_confirmed:
            pending = await conn.fetchrow('''SELECT status,review_status,request_payload,skill_context FROM research_sessions
                WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',session_id,principal.id)
        if (pending and pending['status'] == 'pending'
                and _json_object(pending['review_status']).get('requires_confirmation')
                and _same_research_request(_json_object(pending['request_payload']), request_payload)):
            original_review = _json_object(pending['review_status'])
            # A pending request keeps the budget offered at creation.
            # Pending records predating frozen budgets keep the prior v2 policy.
            budget = deepcopy(original_review.get('initial_budget') or {**budget,'budget_policy_version':2})
            organization_research = original_review.get('organization_research')
            query_understanding = original_review.get('query_understanding')
            skill_context = _json_object(pending['skill_context'])
        else:
            try:
                async with asyncio.timeout(15):
                    organization_research, query_understanding = await _prepare_query_understanding(
                        conn, request, principal, skill_context, budget, decision)
            except TimeoutError:
                raise HTTPException(status_code=503, detail='query_configuration_temporarily_unavailable') from None
            if not query_understanding['ready']:
                raise HTTPException(status_code=409, detail={'category':'query_clarification_required','understanding':query_understanding})
            if request.query_preview_id and request.query_preview_id != query_understanding['interpretation_id']:
                raise HTTPException(status_code=409, detail={'category':'query_preview_changed','understanding':query_understanding})
        review_status = build_review_status(
            blocked=decision.must_confirm and not request.user_confirmed,
            requires_confirmation=decision.must_confirm and not request.user_confirmed,
            approved=request.user_confirmed or not decision.must_confirm,
            reason="pending_confirmation" if decision.must_confirm and not request.user_confirmed else None,
            risk_level=decision.risk_level,
            intent=decision.intent,
            prompt_profile=decision.prompt_profile,
        )
        review_status["organization_research"] = organization_research
        review_status['query_understanding'] = query_understanding
        review_status['initial_budget'] = deepcopy(budget)
        inserted = await conn.fetchrow(
            """
            INSERT INTO research_sessions (id, user_query, status, guardrail_decision, guardrail_trace,
                                           evidence_status, review_status, prompt_profile, prompt_template,
                                            enabled_tools, skill_context, owner_id, created_at, updated_at, request_payload, execution_id)
            VALUES ($1::uuid, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb, $8, $9, $10::jsonb, $11::jsonb, $12::uuid, $13, $13, $14::jsonb, $15::uuid)
            ON CONFLICT (id) DO NOTHING
            RETURNING id
            """,
            session_id,
            request.query,
            "pending" if decision.must_confirm and not request.user_confirmed else "running",
            dumps_json(decision.model_dump()),
            dumps_json([]),
            dumps_json(None),
            dumps_json(review_status),
            decision.prompt_profile.value,
            compose_guardrail_prompt(request.query, decision),
            dumps_json(_task_tool_allowlist(skill_context, decision.enabled_tools)),
            dumps_json(skill_context),
            _principal_id(principal),
            utc_now_naive(),
            dumps_json(request_payload),
            execution_id,
        )
        if not inserted:
            existing = await conn.fetchrow(
                "SELECT status, review_status, request_payload, skill_context FROM research_sessions WHERE id = $1::uuid AND owner_id = $2::uuid FOR UPDATE",
                session_id, _principal_id(principal),
            )
            if not existing:
                raise HTTPException(status_code=404, detail="Session not found")
            if not (request.user_confirmed and existing["status"] == "pending"
                    and _json_object(existing["review_status"]).get("requires_confirmation")
                    and _same_research_request(_json_object(existing["request_payload"]), request_payload)):
                raise HTTPException(status_code=409, detail="session_already_exists")
            skill_context = _json_object(existing["skill_context"])
            original_review = _json_object(existing["review_status"])
            budget = deepcopy(original_review.get('initial_budget') or {**budget,'budget_policy_version':2})
            review_status['initial_budget'] = deepcopy(budget)
            organization_research = original_review.get("organization_research")
            review_status["organization_research"] = organization_research
            query_understanding = _json_object(existing['review_status']).get('query_understanding')
            review_status['query_understanding'] = query_understanding
            await conn.execute(
                "UPDATE research_sessions SET status = 'running', review_status = $1::jsonb, updated_at = $2, execution_id = $5::uuid WHERE id = $3::uuid AND owner_id = $4::uuid AND status = 'pending'",
                dumps_json(review_status), utc_now_naive(), session_id, _principal_id(principal), execution_id,
            )

    if decision.must_confirm and not request.user_confirmed:
        return ResearchResponse(
            session_id=session_id,
            status="pending_confirmation",
            message="High-risk request requires user confirmation before execution.",
            requires_confirmation=True,
            output_length=output_length.value,
            budget=budget,
            skill_context=skill_context,
        )

    # Start background execution
    background_tasks.add_task(
        run_research_workflow,
        session_id=session_id,
        query=request.query,
        max_revision=request.max_revision,
        user_confirmed=request.user_confirmed,
        use_internal_docs=request.use_internal_docs,
        rag_group=request.rag_group if request.use_internal_docs else None,
        output_length=output_length.value,
        skill_context=skill_context,
        owner_id=_principal_id(principal),
        channels=request.channels,
        execution_id=execution_id,
        organization_research=organization_research,
        query_understanding=query_understanding,
        initial_budget=budget,
    )

    return ResearchResponse(
        session_id=session_id,
        status="running",
        message=f"Research task started. Connect to /api/v1/research/stream/{session_id} for updates.",
        requires_confirmation=False,
        output_length=output_length.value,
        budget=budget,
        skill_context=skill_context,
    )


@router.get("/status/{session_id}", response_model=ResearchStatus)
async def get_research_status(session_id: str, principal: Principal = principal_dependency):
    """Get the current status of a research session."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT rs.id, rs.execution_id, rs.user_query, rs.status, rs.review_status, rs.created_at, rs.updated_at, rs.completed_at,
                   sbs.max_total_tokens, sbs.max_cost_usd, sbs.max_tool_calls, sbs.max_wall_clock_seconds,
                   sbs.used_total_tokens, sbs.used_cost_usd, sbs.used_tool_calls,
                   sbs.elapsed_wall_clock_seconds, sbs.hard_stop_reason
            FROM research_sessions
            rs
            LEFT JOIN session_budget_state sbs ON sbs.session_id = rs.id
            WHERE rs.id = $1::uuid AND rs.owner_id = $2::uuid
            """,
            session_id, _principal_id(principal),
        )

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    review_status = _json_object(row.get("review_status"))
    budget_state = review_status.get("budget_state")
    if row.get("max_tool_calls") is not None:
        budget_state = {
            **(budget_state or {}),
            "max_total_tokens": int(row.get("max_total_tokens") or 0),
            "max_cost_usd": float(row.get("max_cost_usd") or 0.0),
            "max_tool_calls": int(row.get("max_tool_calls") or 0),
            "max_wall_clock_seconds": int(row.get("max_wall_clock_seconds") or 0),
            "used_total_tokens": int(row.get("used_total_tokens") or 0),
            "used_cost_usd": float(row.get("used_cost_usd") or 0.0),
            "used_tool_calls": int(row.get("used_tool_calls") or 0),
            "elapsed_wall_clock_seconds": int(row.get("elapsed_wall_clock_seconds") or 0),
            "hard_stop_reason": row.get("hard_stop_reason"),
        }
    pending_approval_count = int(review_status.get("pending_approval_count", 0) or 0)
    return ResearchStatus(
        session_id=str(row["id"]),
        execution_id=str(row['execution_id']) if row['execution_id'] else None,
        cancellation=projection(review_status.get('cancellation')),
        status=row["status"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
        runtime_status=review_status.get("runtime_status"),
        requires_confirmation=bool(review_status.get("requires_confirmation", False)),
        pending_approval_count=pending_approval_count,
        budget_state=budget_state,
        last_error_category=review_status.get("last_error_category"),
    )


@router.get('/{session_id}/classifications')
async def get_classification_versions(session_id: uuid.UUID, principal: Principal = principal_dependency):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT review_status FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid',
            str(session_id), _principal_id(principal))
    if row is None:
        raise HTTPException(404, 'Session not found')
    review = _json_object(row['review_status'])
    findings=review.get('organization_result') or {}
    initial = findings.get('classification')
    if initial and findings.get('statistics'):
        initial={**initial,'statistics':findings['statistics']}
    return {'versions': ([initial] if initial else []) + review.get('classification_versions', [])}


@router.get('/{session_id}/ingestion')
async def get_ingestion_ledger(session_id:uuid.UUID,include_content:bool=False,principal:Principal=principal_dependency):
    """Only the authorized task's retained versions; never acquire or reindex."""
    from app.evidence_ingestion import reconcile_evidence_ledger, ledger_view
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        row=await conn.fetchrow('''SELECT s.owner_id,r.state_snapshot_json FROM research_sessions s
            LEFT JOIN session_runtime_state r ON r.session_id=s.id WHERE s.id=$1::uuid AND s.owner_id=$2::uuid''',
            str(session_id),_principal_id(principal))
    if row is None:raise HTTPException(404,'Session not found')
    state=_json_object(row['state_snapshot_json'])
    ledger=state.get('evidence_ledger');persisted=bool(ledger)
    owner_id=str(row['owner_id'])
    if ledger and (ledger.get('owner_id')!=owner_id or ledger.get('session_id')!=str(session_id)):
        raise HTTPException(409,'ingestion_scope_conflict')
    if not ledger:
        ledger=reconcile_evidence_ledger(state,None,owner_id=owner_id,session_id=str(session_id))
    config=state.get('organization_research') or {}
    corpus=(state.get('organization_result') or {}).get('corpus')
    return {'persisted':persisted,'origin':'saved_task_ledger' if persisted else 'explicit_legacy_snapshot_projection',
        'view':ledger_view(ledger,include_content=include_content),'corpus':corpus,
        'declared_scope':{key:config.get(key) for key in ('scope','corpus')},
        'effects':{'network_requests':0,'model_calls':0,'index_writes':0}}


async def _owned_retained_version(session_id,evidence_id,owner_id):
    from app.evidence_ingestion import reconcile_evidence_ledger
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        row=await conn.fetchrow('''SELECT r.state_snapshot_json FROM research_sessions s
            LEFT JOIN session_runtime_state r ON r.session_id=s.id WHERE s.id=$1::uuid AND s.owner_id=$2::uuid''',str(session_id),owner_id)
    if row is None:raise HTTPException(404,'Retained evidence not found')
    state=_json_object(row['state_snapshot_json'])
    ledger=state.get('evidence_ledger') or reconcile_evidence_ledger(state,None,owner_id=owner_id,session_id=str(session_id))
    if ledger.get('owner_id')!=owner_id or ledger.get('session_id')!=str(session_id):raise HTTPException(409,'retained_evidence_scope_conflict')
    event=ledger.get('events',{}).get(evidence_id)
    if not event:raise HTTPException(404,'Retained evidence not found')
    source=ledger['sources'][event['source_id']]
    return source,source['versions'][event['version_id']]


class ArchiveTaskEvidenceRequest(BaseModel):
    model_config={'extra':'forbid'}
    request_id:uuid.UUID
    version_id:str=Field(min_length=1,max_length=260)
    group_name:str=Field(min_length=1,max_length=100)
    name:str|None=Field(default=None,min_length=1,max_length=300)

    @field_validator('group_name','name')
    @classmethod
    def bounded_label(cls,value):
        if value is None:return None
        value=value.strip()
        if not value or any(ord(char)<32 for char in value):raise ValueError('archive label must be nonblank without control characters')
        return value


@router.post('/{session_id}/evidence/{evidence_id}/archive')
async def archive_task_evidence(session_id:uuid.UUID,evidence_id:str,payload:ArchiveTaskEvidenceRequest,
        principal:Principal=principal_dependency):
    from app.api.documents import _ingest_source
    from app.db.retrieval_indexes import IndexPolicy
    from app.retrieval_features import FeaturePolicy
    from app.source_lifecycle import RetentionPolicy,lock_owner,prior_operation,record_operation
    from app.organization_corpus import source_scope
    from app.channels.execution import public_url
    from app.channels.models import ChannelError
    owner=_principal_id(principal)
    source,version=await _owned_retained_version(session_id,evidence_id,owner)
    if version['version_id']!=payload.version_id:raise HTTPException(409,'retained_version_changed')
    if source['source_type']!='web' or version.get('coverage')=='discovery_only' or not version.get('content','').strip():
        raise HTTPException(422,'archive_requires_acquired_public_source_text_not_search_lead_or_generated_report')
    fingerprint=identity({'session_id':str(session_id),'evidence_id':evidence_id,**payload.model_dump(mode='json')})
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await lock_owner(conn,owner)
        try:previous=await prior_operation(conn,owner,payload.request_id,fingerprint)
        except ValueError as error:raise HTTPException(409,str(error)) from None
        if previous:return previous
        row=await conn.fetchrow('''SELECT r.state_snapshot_json FROM research_sessions s JOIN session_runtime_state r ON r.session_id=s.id
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid''',str(session_id),owner)
        if row is None:raise HTTPException(404,'Retained evidence not found')
        state=_json_object(row['state_snapshot_json'])
        from app.external_evidence import archive_version_allowed
        ledger=state.get('evidence_ledger') or {}
        if not archive_version_allowed(source,version,ledger.get('events') or {}):
            raise HTTPException(409,'archive_requires_confirmed_public_transport_acquisition')
        try:
            policy=source_scope(state.get('organization_research'))
            (policy.admit if policy else public_url)(source.get('source_url') or '')
        except (ChannelError,ValueError,TypeError):raise HTTPException(409,'current_public_source_scope_not_established') from None
        archived=await _ingest_source(name=payload.name or str(source.get('title') or source['source_url'])[:300],
            group_name=payload.group_name,source_type='web',file_ext='md',content=version['content'],owner_id=owner,connection=conn,
            index_policy=IndexPolicy(mode='direct'),feature_policy=FeaturePolicy(dense=False),
            retention_policy=RetentionPolicy(reuse_scope='group'),revision_intake_key=str(payload.request_id),
            metadata={'url':source['source_url'],'title':source.get('title'),
                'research_evidence_origin':{'session_id':str(session_id),'evidence_id':evidence_id,
                    'version_id':version['version_id'],'coverage':version.get('coverage'),
                    'collected_at':version.get('collected_at'),'acquisition':version.get('acquisition')},
                'archival_semantics':'acquired_retained_text_not_network_bytes_or_independent_fact_verification'})
        from hashlib import sha256
        result={**archived,'source_version_id':version['version_id'],
            'archived_content_hash':sha256(version['content'].encode('utf-8')).hexdigest(),'replayed':False,
            'effects':{'network_requests':0,'model_calls':0,'automatic_search_index':False},
            'retention':'owned_group_direct_only_explicitly_archived'}
        await record_operation(conn,owner,payload.request_id,fingerprint,archived['source_id'],
            'archive_task_evidence','explicit_user_archive_of_retained_source_text',result)
        return result


@router.get('/{session_id}/evidence/{evidence_id}')
async def get_retained_evidence_quote(session_id:uuid.UUID,evidence_id:str,start:int=0,end:int|None=None,
        principal:Principal=principal_dependency):
    source,version=await _owned_retained_version(session_id,evidence_id,_principal_id(principal))
    text=version['content'];end=min(start+2000,len(text)) if end is None else end
    if not 0<=start<=end<=len(text) or end-start>4000:raise HTTPException(422,'retained_quote_range_must_be_within_source_and_4000_chars')
    return {'session_id':str(session_id),'evidence_id':evidence_id,'version_id':version['version_id'],
        'source_url':source['source_url'],'source_title':source['title'],'text':text[start:end],'start':start,'end':end,
        'offset_unit':'task_retained_evidence_character','coverage':version['coverage'],
        'upstream_locator':{key:(version.get('acquisition') or {}).get(key) for key in ('source_document_id','parse_version_id','chunk_reference','returned_span')},
        'semantics':'retained_source_excerpt_not_fact_verification','effects':{'model_calls':0,'network_requests':0,'index_writes':0}}


@router.get('/{session_id}/evidence/{evidence_id}/chunks')
async def preview_retained_evidence_chunks(session_id:uuid.UUID,evidence_id:str,principal:Principal=principal_dependency):
    from app.evidence_chunks import build_chunk_plan
    source,version=await _owned_retained_version(session_id,evidence_id,_principal_id(principal))
    acquisition=version.get('acquisition') or {}
    view=build_chunk_plan(version['content'],acquisition.get('document_structure') or acquisition,version['version_id'],size=1800,overlap=150)
    return {'persisted':False,'origin':'current_chunk_policy_on_immutable_retained_version','view':view,
        'source_url':source['source_url'],'effects':{'model_calls':0,'network_requests':0,'index_writes':0,'original_report_modified':False}}


async def _owned_analysis_source(session_id: uuid.UUID, owner_id: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('''SELECT s.id,s.execution_id,s.completed_at,s.status,s.review_status,r.state_snapshot_json
            FROM research_sessions s LEFT JOIN session_runtime_state r ON r.session_id=s.id
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid''',str(session_id),owner_id)
    if row is None:
        raise HTTPException(404,'Session not found')
    if row['status']!='completed':
        raise HTTPException(409,'research_must_be_completed')
    review=_json_object(row['review_status'])
    review['analysis_source_context']={'session_id':str(row['id']),
        'execution_id':str(row['execution_id']) if row['execution_id'] else None,
        'completed_at':row['completed_at'].isoformat() if row['completed_at'] else None}
    if not review.get('organization_research'):
        raise HTTPException(409,'organization_research_required')
    return review, _json_object(row['state_snapshot_json']).get('collected_evidence',[])


@router.get('/{session_id}/relationships')
async def get_relationship_view(session_id: uuid.UUID, principal: Principal = principal_dependency):
    review,evidence=await _owned_analysis_source(session_id,_principal_id(principal))
    findings=review.get('organization_result') or {}
    if findings.get('relationship_view'):
        return {'persisted':True,'view':findings['relationship_view']}
    return {'persisted':False,'view':build_relationship_view(review['organization_research'],findings,evidence,
        origin='explicit_legacy_snapshot_projection')}


@router.post('/{session_id}/relationships/preview')
async def preview_relationship_claims(session_id: uuid.UUID,payload:RelationshipPreviewRequest,principal:Principal=principal_dependency):
    """Review bounded claims against this owner's original sources; never write facts."""
    review,evidence=await _owned_analysis_source(session_id,_principal_id(principal))
    if not evidence:
        raise HTTPException(409,'retained_source_evidence_unavailable')
    return {'persisted':False,'view':build_relationship_view(review['organization_research'],
        review.get('organization_result') or {},evidence,payload.model_dump(mode='json'),origin='caller_proposals_not_verified_facts')}


@router.get('/{session_id}/technical-reading')
async def get_technical_reading(session_id:uuid.UUID,principal:Principal=principal_dependency):
    review,evidence=await _owned_analysis_source(session_id,_principal_id(principal))
    findings=review.get('organization_result') or {}
    if findings.get('technical_reading'):return {'persisted':True,'view':findings['technical_reading']}
    return {'persisted':False,'view':build_technical_cards(review['organization_research'],findings,evidence)}


@router.post('/{session_id}/technical-reading/preview')
async def preview_technical_reading(session_id:uuid.UUID,payload:TechnicalPreviewRequest,principal:Principal=principal_dependency):
    review,evidence=await _owned_analysis_source(session_id,_principal_id(principal))
    if not evidence:raise HTTPException(409,'retained_source_evidence_unavailable')
    return {'persisted':False,'view':build_technical_cards(review['organization_research'],review.get('organization_result') or {},
        evidence,payload.model_dump(mode='json'))}


@router.get('/{session_id}/trends')
async def get_trend_view(session_id:uuid.UUID,principal:Principal=principal_dependency):
    review,evidence=await _owned_analysis_source(session_id,_principal_id(principal))
    findings=review.get('organization_result') or {}
    if findings.get('trend_view'):return {'persisted':True,'view':findings['trend_view']}
    return {'persisted':False,'view':build_trend_view(review['organization_research'],findings,evidence)}


@router.post('/{session_id}/trends/preview')
async def preview_trend_view(session_id:uuid.UUID,payload:TrendPreviewRequest,principal:Principal=principal_dependency):
    review,evidence=await _owned_analysis_source(session_id,_principal_id(principal))
    if not evidence:raise HTTPException(409,'retained_source_evidence_unavailable')
    return {'persisted':False,'view':build_trend_view(review['organization_research'],review.get('organization_result') or {},
        evidence,payload.model_dump(mode='json'))}


def _action_source_state(review,evidence):
    provenance=review['analysis_source_context']
    return {'task_id':provenance['session_id'],'session':{'execution_id':provenance['execution_id']},
        'status':'completed','completed_at':provenance['completed_at'],'collected_evidence':evidence}


@router.get('/{session_id}/statistics')
async def get_statistics(session_id:uuid.UUID,classification_snapshot_id:str|None=None,principal:Principal=principal_dependency):
    """Consume immutable counts; old snapshots get an explicitly read-only projection."""
    review,evidence=await _owned_analysis_source(session_id,_principal_id(principal))
    findings=review.get('organization_result') or {}
    initial=findings.get('classification') or {}
    if classification_snapshot_id and classification_snapshot_id!=initial.get('snapshot_id'):
        selected=next((item for item in review.get('classification_versions',[])
            if item['snapshot_id']==classification_snapshot_id),None)
        if selected is None:raise HTTPException(404,'Classification snapshot not found')
        if selected.get('statistics'):return {'persisted':True,'view':selected['statistics']}
        findings={**findings,'classification':selected}
    elif findings.get('statistics'):
        return {'persisted':True,'view':findings['statistics']}
    provenance=review['analysis_source_context']
    source_id=provenance['session_id']+':'+str(provenance['execution_id'] or 'execution-not-recorded')
    return {'persisted':False,'origin':'explicit_legacy_snapshot_projection',
        'view':build_statistics(review['organization_research'],findings,evidence,source_id=source_id)}


@router.get('/{session_id}/actions')
async def get_action_view(session_id:uuid.UUID,principal:Principal=principal_dependency):
    review,evidence=await _owned_analysis_source(session_id,_principal_id(principal))
    findings=review.get('organization_result') or {}
    if findings.get('actions'):return {'persisted':True,'view':findings['actions']}
    return {'persisted':False,'view':build_action_view(review['organization_research'],findings,evidence,
        findings.get('action_proposals'),state=_action_source_state(review,evidence))}


@router.post('/{session_id}/actions/preview')
async def preview_action_view(session_id:uuid.UUID,payload:ActionPreviewRequest,principal:Principal=principal_dependency):
    review,evidence=await _owned_analysis_source(session_id,_principal_id(principal))
    if not evidence:raise HTTPException(409,'retained_source_evidence_unavailable')
    return {'persisted':False,'view':build_action_view(review['organization_research'],review.get('organization_result') or {},
        evidence,{'action_cards':payload.model_dump(mode='json')['action_cards']},
        requirements=payload.requirements if 'requirements' in payload.model_fields_set else None,
        weights=payload.weights,state=_action_source_state(review,evidence))}


@router.post('/{session_id}/classifications', status_code=201)
async def reclassify_research(session_id: uuid.UUID, payload: ReclassificationRequest, principal: Principal = principal_dependency):
    """Same owner's retained evidence only; append versions without tools or model calls."""
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow('''SELECT status,review_status FROM research_sessions
            WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''', str(session_id), _principal_id(principal))
        if row is None:
            raise HTTPException(404, 'Session not found')
        if row['status'] != 'completed':
            raise HTTPException(409, 'research_must_be_completed')
        review = _json_object(row['review_status'])
        config, findings = review.get('organization_research'), review.get('organization_result') or {}
        if not config or not (findings.get('scope_result') or {}).get('outputs'):
            raise HTTPException(409, 'no_accepted_publication_sample')
        try:
            taxonomy = freeze_taxonomy(payload.taxonomy, config['scope']['disciplines'])
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        initial = findings.get('classification')
        saved = review.get('classification_versions', [])
        versions = ([initial] if initial else []) + saved
        for prior in versions:
            if prior['taxonomy']['version'] == taxonomy['version']:
                if prior['taxonomy'] != taxonomy:
                    raise HTTPException(409, 'taxonomy_version_already_has_different_rules')
                return prior
        if len(versions) >= 20:
            raise HTTPException(409, 'classification_version_limit_20')
        state = await conn.fetchval('SELECT state_snapshot_json FROM session_runtime_state WHERE session_id=$1::uuid', str(session_id))
        evidence = _json_object(state).get('collected_evidence', [])
        if not evidence:
            raise HTTPException(409, 'retained_source_evidence_unavailable')
        snapshot = classify_publications(taxonomy, findings, evidence, config['scope'], reason=payload.reason,
            previous=versions[-1] if versions else None)
        statistics=build_statistics(config,{**findings,'classification':snapshot},evidence,source_id=str(session_id))
        snapshot={**apply_statistics({**findings,'classification':snapshot},statistics)['classification'],
            'statistics':statistics}
        await conn.execute('''UPDATE research_sessions SET review_status=jsonb_set(review_status,'{classification_versions}',$3::jsonb)
            WHERE id=$1::uuid AND owner_id=$2::uuid''', str(session_id), _principal_id(principal), dumps_json(saved + [snapshot]))
    return snapshot


@router.get('/{session_id}/reports')
async def retained_report_versions(session_id:uuid.UUID,principal:Principal=principal_dependency):
    pool=await get_db_pool();owner=_principal_id(principal)
    async with pool.acquire() as conn:
        if not await conn.fetchval('SELECT 1 FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid',str(session_id),owner):
            raise HTTPException(404,'Session not found')
        rows=await conn.fetch('''SELECT report_id,sequence,created_at,payload->>'status' AS status,
            payload->>'kind' AS kind,payload->'audit'->>'supported_claims' AS supported_claims,
            payload->'audit'->>'total_claims' AS total_claims FROM research_report_versions
            WHERE session_id=$1::uuid AND owner_id=$2::uuid ORDER BY sequence DESC''',str(session_id),owner)
    return {'items':[{**dict(row),'created_at':row['created_at'].isoformat()} for row in rows],
        'effects':{'model_calls':0,'network_collection':0,'fact_ingestion':False}}


@router.get('/{session_id}/reports/{report_id}')
async def retained_report_version(session_id:uuid.UUID,report_id:str,principal:Principal=principal_dependency):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        row=await conn.fetchrow('''SELECT v.* FROM research_report_versions v JOIN research_sessions s ON s.id=v.session_id
            AND s.owner_id=v.owner_id WHERE v.session_id=$1::uuid AND v.owner_id=$2::uuid AND v.report_id=$3''',
            str(session_id),_principal_id(principal),report_id)
    if not row:raise HTTPException(404,'Report version not found')
    payload=report_history_projection(_json_object(row['payload']))
    from app.research_delivery import report_for_reading
    return {**payload,'reader_report':report_for_reading(payload['report'],payload.get('citations')) if payload['kind']=='report' else None,
        'report_id':row['report_id'],'sequence':row['sequence'],
        'created_at':row['created_at'].isoformat()}


@router.get('/quality/compare')
async def compare_retained_quality(session_ids:list[uuid.UUID]=Query(min_length=2,max_length=8),principal:Principal=principal_dependency):
    if len(set(session_ids))!=len(session_ids):raise HTTPException(422,'duplicate_quality_comparison_session')
    pool=await get_db_pool()
    try:
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
            states=[await load_quality_state(conn,value,_principal_id(principal)) for value in session_ids]
        return projection(compare_quality(states))
    except ValueError as error:raise HTTPException(404 if str(error)=='quality_task_not_found' else 409,str(error)) from error


@router.get('/{session_id}/quality')
async def retained_quality(session_id:uuid.UUID,principal:Principal=principal_dependency):
    pool=await get_db_pool();owner=_principal_id(principal)
    try:
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
            state=await load_quality_state(conn,session_id,owner)
            feedback=await load_feedback(conn,session_id,owner)
        return projection(quality_view(state,feedback))
    except ValueError as error:raise HTTPException(404 if str(error)=='quality_task_not_found' else 409,str(error)) from error


@router.post('/{session_id}/cancel')
async def cancel_research(session_id:uuid.UUID,payload:CancellationRequest,principal:Principal=principal_dependency):
    pool=await get_db_pool()
    try:
        async with pool.acquire() as conn,conn.transaction():
            result=await cancel_execution(conn,session_id,_principal_id(principal),payload)
    except ValueError as error:raise HTTPException(404 if str(error)=='cancel_task_not_found' else 409,str(error)) from error
    signal_cancellation(session_id,result['execution_id'])
    if not result.get('replayed') and result.get('transitioned'):
        await get_sse_manager().publish(str(session_id),'done',{**result,'runtime_status':'canceled'})
    return result


@router.post('/{session_id}/pause')
async def pause_research(session_id:uuid.UUID,payload:CancellationRequest,principal:Principal=principal_dependency):
    from app.db.research_pause import request_pause
    pool=await get_db_pool()
    try:
        async with pool.acquire() as conn,conn.transaction():
            result=await request_pause(conn,session_id,_principal_id(principal),payload)
    except ValueError as error:
        raise HTTPException(404 if str(error)=='pause_task_not_found' else 409,str(error)) from error
    if not result.get('replayed'):
        await get_sse_manager().publish(str(session_id),'control_update',result)
    return result


@router.post('/{session_id}/feedback')
async def retain_quality_feedback(session_id:uuid.UUID,payload:QualityFeedback,principal:Principal=principal_dependency):
    pool=await get_db_pool()
    try:
        async with pool.acquire() as conn,conn.transaction():
            return await save_feedback(conn,session_id,_principal_id(principal),payload)
    except ValueError as error:raise HTTPException(404 if str(error)=='quality_task_not_found' else 409,str(error)) from error


@router.get("/{session_id}")
async def get_research_result(session_id: str, principal: Principal = principal_dependency):
    """Get the final research result."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, execution_id, user_query, status, final_report, citations, agent_trace, review_status, created_at, completed_at
                 , skill_context, request_payload,
                   (SELECT state_snapshot_json -> 'dag' FROM session_runtime_state
                    WHERE session_id = research_sessions.id) AS execution_plan,
                   (SELECT state_snapshot_json -> 'analysis_workflow' FROM session_runtime_state
                    WHERE session_id = research_sessions.id) AS analysis_workflow,
                   (SELECT state_snapshot_json -> 'session' ->> 'report_resume_attempts' FROM session_runtime_state
                    WHERE session_id = research_sessions.id) AS report_resume_attempts,
                   (SELECT state_snapshot_json -> 'session' ->> 'audit_resume_attempts' FROM session_runtime_state
                    WHERE session_id = research_sessions.id) AS audit_resume_attempts,
                   (SELECT state_snapshot_json -> 'session' FROM session_runtime_state
                    WHERE session_id = research_sessions.id) AS root_session
            FROM research_sessions
            WHERE id = $1::uuid AND owner_id = $2::uuid
            """,
            session_id, _principal_id(principal),
        )
        citation_rows = await conn.fetch(
            """
            SELECT citation_id, source_url, source_title, source_type,
                   extracted_evidence, relevance_score, access_timestamp
            FROM citations
            WHERE session_id = $1::uuid
              AND EXISTS (SELECT 1 FROM research_sessions WHERE id = $1::uuid AND owner_id = $2::uuid)
            ORDER BY CAST(SPLIT_PART(citation_id, ':', 2) AS INTEGER)
            """,
            session_id, _principal_id(principal),
        )
        model_receipts=await conn.fetch('''SELECT payload FROM research_model_receipts
            WHERE session_id=$1::uuid AND owner_id=$2::uuid ORDER BY updated_at,call_id''',session_id,_principal_id(principal)) if row else []
        tool_receipts=await conn.fetch('''SELECT payload FROM research_tool_receipts
            WHERE session_id=$1::uuid AND owner_id=$2::uuid ORDER BY updated_at,operation_id''',session_id,_principal_id(principal)) if row else []

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    workflow=_json_object(row.get('analysis_workflow'))
    phase_failures=(workflow.get('failed_attempts') or {}).get(workflow.get('active_phase')) or []
    phase_admission=(phase_failures[-1].get('admission') if phase_failures else None)
    frozen_citations=_normalize_citations(row['citations'])
    locators={item.get('citation_id'):item.get('locator') for item in frozen_citations if item.get('locator')}
    citations = projection([{**dict(citation),'locator':locators.get(citation['citation_id'])} for citation in citation_rows] if citation_rows else frozen_citations)

    review_status = _json_object(row.get("review_status"))
    from app.skills.usage import method_usage_view
    method_usage=method_usage_view(_json_object(row.get('skill_context')),
        [_json_object(item['payload']) for item in model_receipts],
        [_json_object(item['payload']) for item in tool_receipts],row['status'])
    from app.research_diagnostics import diagnose_stop
    pause_diagnosis=diagnose_stop({'status':row['status'],'runtime_status':review_status.get('runtime_status'),
        'created_at':row['created_at'].isoformat(),'session':_json_object(row.get('root_session')),
        'review_status':review_status,'budget_state':review_status.get('budget_state'),
        'analysis_workflow':workflow,'pending_approvals':[{}]*min(1,int(review_status.get('pending_approval_count') or 0))})
    restart_source = _json_object(row.get('request_payload'))
    phase_modules=((review_status.get('organization_research') or restart_source.get('organization_research') or {}).get('modules') or [])
    def phase_order(item):
        # JSONB object ordering is not the order in which questions ran.
        parts=item[0].split(':')
        batch=int(parts[-1]) if parts[-1].isdigit() else 1
        if parts[0]=='extract_publications':return (0,0,batch,0,item[0])
        module=parts[1] if len(parts)>1 else ''
        return (1,phase_modules.index(module) if module in phase_modules else len(phase_modules),batch,
            int('conditions' in parts),item[0])
    from app.research_delivery import build_delivery_view
    delivery_view = build_delivery_view(task_id=str(row['id']), execution_id=str(row['execution_id']) if row['execution_id'] else None,
        query=row['user_query'], report=row['final_report'], citations=citations,
        understanding=review_status.get('query_understanding'), organization_result=review_status.get('organization_result'),
        audit=review_status.get('final_report_audit')) if row['status'] == 'completed' and row['final_report'] else None
    result = {
        "session_id": str(row["id"]),
        'execution_id':str(row['execution_id']) if row['execution_id'] else None,
        'cancellation':review_status.get('cancellation'),
        'user_control':review_status.get('user_control'),
        'pause_diagnosis':pause_diagnosis,
        'stop_reason':review_status.get('reason') or review_status.get('last_error_category') or workflow.get('stop_reason'),
        "query": row["user_query"],
        "status": row["status"],
        'classification_versions': review_status.get('classification_versions', []),
        "runtime_status": review_status.get("runtime_status"),
        "report": row["final_report"],
        'delivery_view': delivery_view,
        "citations": citations,
        "agent_trace": json.loads(row["agent_trace"]) if isinstance(row["agent_trace"], str) else row["agent_trace"],
        "tool_audit_summary": review_status.get("tool_audit_summary", {}),
        'ingestion':review_status.get('ingestion'),
        "skill_context": _json_object(row.get("skill_context")),
        'method_usage':method_usage,
        "organization_research": review_status.get("organization_research"),
        "organization_result": review_status.get("organization_result"),
        'query_understanding': review_status.get('query_understanding'),
        'plan_manifest': review_status.get('plan_manifest'),
        'plan_history': review_status.get('plan_history', []),
        'iteration_control': review_status.get('iteration_control'),
        'planning_policy': review_status.get('planning_policy'),
        'workflow_failure':projection(review_status.get('workflow_failure')),
        'operational_events':projection(review_status.get('operational_events',[])),
        'report_audit': review_status.get('final_report_audit'),
        'report_editorial': review_status.get('report_editorial'),
        'budget_state':review_status.get('budget_state'),
        "execution_plan": _json_object(row.get("execution_plan")),
        'analysis_progress':{'phase':workflow.get('active_phase'),'status':workflow.get('status'),
            'stop_reason':workflow.get('stop_reason'),'last_admission':projection(phase_admission),
            'completed_steps':len(workflow.get('completed') or {}),
            'phases':[{'phase':phase,'status':'completed' if phase in (workflow.get('completed') or {}) else
                'paused' if workflow.get('status')=='paused' else 'running',
                'attempts':attempts,'summary':str(((workflow.get('completed') or {}).get(phase) or {}).get('analysis_text') or '')[:320]}
                for phase,attempts in sorted((workflow.get('attempts') or {}).items(),key=phase_order)[:100]]} if workflow else None,
        'analysis_recovery_available':bool(row['status']=='paused' and workflow.get('status')=='paused'
            and workflow.get('schema_version')=='adrs-analysis-questions-v2'
            and workflow.get('stop_reason') in {'analysis_output_incomplete','analysis_provider_unavailable','model_output_limit','insufficient_context_budget'}
            and int((workflow.get('attempts') or {}).get(workflow.get('active_phase'),10))<10),
        'report_recovery_available':bool(row['status'] in {'failed','paused'} and workflow.get('status')=='completed'
            and review_status.get('output_stage')=='report' and review_status.get('report_payload_kind')=='partial_response'
            and (((review_status.get('organization_result') or {}).get('module_report') or {}).get('issues')
                or review_status.get('last_error_category')=='llm_stream_interrupted')
            and int(row.get('report_resume_attempts') or 0)<1),
        'audit_recovery_available':bool(row['status']=='paused' and workflow.get('status')=='completed'
            and review_status.get('output_stage')=='report' and review_status.get('report_payload_kind')=='report'
            and review_status.get('reason')=='final_audit_incomplete'
            and bool((review_status.get('final_report_audit') or {}).get('audit_incomplete'))
            and not (review_status.get('disclosure') or {}).get('requires_reaudit')
            and bool(pause_diagnosis and not pause_diagnosis.get('blockers')
                and (pause_diagnosis.get('remaining_seconds') or 0)>0
                and (pause_diagnosis.get('remaining_tokens') or 0)>=1024)
            and int(row.get('audit_resume_attempts') or 0)<1),
        "created_at": row["created_at"].isoformat(),
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
    }
    safe=projection(result)
    changed=safe.get('report')!=result.get('report')
    safe['disclosure']={'version':DISCLOSURE_VERSION,'report_redacted':changed,'requires_reaudit':changed}
    if changed:
        safe['report_audit']={**(safe.get('report_audit') or {}),'needs_review':True,'disclosure_requires_revision':True}
        safe['delivery_view']={**(safe.get('delivery_view') or {}),'delivery_complete':False}
    # Export is an explicit projection, never a copy of the owner-only restart
    # configuration or of the original retained-material endpoints.
    safe['export_view']={
        'schema_version':'adrs-report-export-v3','disclosure':safe['disclosure'],
        **{key:safe.get(key) for key in ('session_id','query','status','created_at','completed_at','report',
            'citations','delivery_view','organization_research','organization_result','classification_versions',
            'query_understanding','plan_manifest','plan_history','iteration_control','budget_state')},
        'research_record':{'stored_report':safe['report'],'report_audit':safe.get('report_audit'),
            'editorial':safe.get('report_editorial')},
    }
    safe['restart_parameters']={'query':row['user_query'],**{key:restart_source[key] for key in (
        'channels','max_revision','output_length','use_internal_docs','rag_group',
        'enabled_skill_ids','disabled_skill_ids','skill_tenant_id','skill_project_id','query_options','delivery','planning_policy',
        'organization_research') if key in restart_source}}
    return safe


@router.post('/{session_id}/layout-preview')
async def preview_report_layout(session_id:uuid.UUID, delivery:DeliveryRequest, principal:Principal=principal_dependency):
    """Preview one owner's completed report against a declarative layout, without a model or writes."""
    if delivery.layout is None:
        raise HTTPException(422,'layout_preview_requires_layout')
    retained=await get_research_result(str(session_id),principal)
    if retained.get('status')!='completed' or not retained.get('report'):
        raise HTTPException(409,'layout_preview_requires_completed_report')
    understanding=deepcopy(retained.get('query_understanding') or {})
    snapshot=delivery.model_dump(mode='json')
    understanding['delivery']={**snapshot,'descriptor_id':identity(snapshot)}
    from app.research_delivery import build_delivery_view
    view=build_delivery_view(task_id=str(session_id),execution_id=retained.get('execution_id'),
        query=retained.get('query') or '',report=retained['report'],citations=retained.get('citations') or [],
        understanding=understanding,organization_result=retained.get('organization_result'),audit=retained.get('report_audit'))
    return projection({'binding':view['layout_binding'],'charts':view['charts'],
        'effects':{'model_calls':0,'network_calls':0,'permissions_changed':False}})


@router.get("/{session_id}/tool-calls", response_model=list[ToolCallAuditRecord])
async def get_research_tool_calls(session_id: str, principal: Principal = principal_dependency):
    """Get persisted per-call tool audit rows for a research session."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        session_exists = await conn.fetchrow(
            "SELECT id FROM research_sessions WHERE id = $1::uuid AND owner_id = $2::uuid",
            session_id, _principal_id(principal),
        )
        if not session_exists:
            raise HTTPException(status_code=404, detail="Session not found")

        rows = await conn.fetch(
            """
            SELECT call_id, session_id, node_id, agent_type, tool_name,
                   args_json, args_hash, status, error_category, error_message,
                   retry_count, result_summary, result_hash, tokens_used, cost_usd,
                   decision_id, approved_by, server_fingerprint, safety_json, usage_source, estimated,
                   started_at, completed_at, created_at
            FROM tool_call_audit
            WHERE session_id = $1::uuid
              AND EXISTS (
                  SELECT 1 FROM research_sessions
                  WHERE id = $1::uuid AND owner_id = $2::uuid
              )
            ORDER BY created_at ASC, call_id ASC
            """,
            session_id,
            _principal_id(principal),
        )

    result: list[ToolCallAuditRecord] = []
    for row in rows:
        result.append(ToolCallAuditRecord(
            call_id=row["call_id"],
            session_id=str(row["session_id"]),
            node_id=row["node_id"],
            agent_type=row["agent_type"],
            tool_name=row["tool_name"],
            args_json=projection(_json_object(row["args_json"])),
            args_hash=row["args_hash"],
            status=row["status"],
            error_category=row["error_category"],
            error_message=redact_text(row["error_message"]),
            retry_count=int(row["retry_count"] or 0),
            result_summary=redact_text(row["result_summary"]),
            result_hash=row["result_hash"],
            tokens_used=int(row["tokens_used"] or 0),
            cost_usd=float(row["cost_usd"] or 0.0),
            decision_id=row["decision_id"],
            approved_by=row["approved_by"],
            server_fingerprint=row["server_fingerprint"],
            safety_json=projection(_json_object(row["safety_json"])),
            usage_source=row["usage_source"],
            estimated=bool(row["estimated"]),
            started_at=row["started_at"].isoformat() if row["started_at"] else None,
            completed_at=row["completed_at"].isoformat() if row["completed_at"] else None,
            created_at=row["created_at"].isoformat() if row["created_at"] else None,
        ))
    return result


@router.get("/{session_id}/approvals", response_model=list[ApprovalRequestRecord])
async def get_research_approvals(session_id: str, principal: Principal = principal_dependency):
    """Get approval requests for a research session."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        session_exists = await conn.fetchrow(
            "SELECT id FROM research_sessions WHERE id = $1::uuid AND owner_id = $2::uuid",
            session_id, _principal_id(principal),
        )
        if not session_exists:
            raise HTTPException(status_code=404, detail="Session not found")
        rows = await conn.fetch(
            """
            SELECT approval_id, session_id, node_id, tool_name, risk_level, reason,
                   request_payload_json, status, requested_at, resolved_at, resolved_by, comment
            FROM approval_requests
            WHERE session_id = $1::uuid
              AND EXISTS (
                  SELECT 1 FROM research_sessions
                  WHERE id = $1::uuid AND owner_id = $2::uuid
              )
            ORDER BY requested_at ASC, approval_id ASC
            """,
            session_id,
            _principal_id(principal),
        )
    return [
        ApprovalRequestRecord(
            approval_id=row["approval_id"],
            session_id=str(row["session_id"]),
            node_id=row["node_id"],
            tool_name=row["tool_name"],
            risk_level=row["risk_level"],
            reason=row["reason"],
            request_payload_json=row["request_payload_json"] or {},
            status=row["status"],
            requested_at=row["requested_at"].isoformat() if row["requested_at"] else None,
            resolved_at=row["resolved_at"].isoformat() if row["resolved_at"] else None,
            resolved_by=row["resolved_by"],
            comment=row["comment"],
        )
        for row in rows
    ]


@router.post("/{session_id}/approvals/{approval_id}")
async def resolve_research_approval(
    session_id: str,
    approval_id: str,
    request: ApprovalActionRequest,
    principal: Principal = principal_dependency,
    background_tasks: BackgroundTasks = None,
):
    """Resolve one bound decision; resume only after all decisions are final."""
    from app.graph.approval import resume_approved_state

    pool = await get_db_pool()
    state_snapshot = None
    approval_payload = None
    resolved_status = "approved" if request.action == "approve" else "rejected"
    execution_id = str(uuid.uuid4())
    async with pool.acquire() as conn, conn.transaction():
        session = await conn.fetchrow(
            """SELECT s.status, s.execution_id, r.state_snapshot_json
               FROM research_sessions s LEFT JOIN session_runtime_state r ON r.session_id = s.id
               WHERE s.id = $1::uuid AND s.owner_id = $2::uuid FOR UPDATE OF s""",
            session_id, principal.id,
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        approval = await conn.fetchrow(
            """SELECT approval_id, session_id, status, request_payload_json
               FROM approval_requests WHERE approval_id = $1 AND session_id = $2::uuid FOR UPDATE""",
            approval_id, session_id,
        )
        if not approval:
            raise HTTPException(status_code=404, detail="Approval request not found")
        if approval["status"] not in {"pending", "awaiting_approval"}:
            raise HTTPException(status_code=409, detail="Approval request already resolved")
        snapshot = _json_object(session["state_snapshot_json"])
        approval_payload = _json_object(approval["request_payload_json"])
        pending = {item["approval_id"]: item for item in snapshot.get("pending_approvals", [])}
        bound = pending.get(approval_id)
        if (session["status"] != "paused" or not bound
                or snapshot.get("session", {}).get("execution_id") != (str(session["execution_id"]) if session["execution_id"] else None)
                or bound.get("request_payload") != approval_payload):
            raise HTTPException(status_code=409, detail="approval_checkpoint_unavailable")
        # Validate before committing a decision, including the rejected case.
        proposed = {key: {**item, "status": resolved_status if key == approval_id else "approved"}
                    for key, item in pending.items()}
        try:
            resume_approved_state(snapshot, proposed, owner_id=principal.id, session_id=session_id)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=409, detail="invalid_approval_checkpoint") from exc
        await conn.execute(
            """UPDATE approval_requests SET status = $1, resolved_at = $2, resolved_by = $3, comment = $4
               WHERE approval_id = $5 AND session_id = $6::uuid AND status IN ('pending', 'awaiting_approval')""",
            resolved_status, utc_now_naive(), principal.username, request.comment, approval_id, session_id,
        )
        rows = await conn.fetch(
            "SELECT approval_id, status, request_payload_json, resolved_at, resolved_by, comment FROM approval_requests WHERE session_id = $1::uuid",
            session_id,
        )
        resolutions = {row["approval_id"]: {"status": row["status"], "request_payload": _json_object(row["request_payload_json"]),
                        "resolved_by": row.get("resolved_by"), "comment": row.get("comment")}
                       for row in rows if row["approval_id"] in pending}
        if all(key in resolutions and resolutions[key]["status"] in {"approved", "rejected"} for key in pending):
            try:
                state_snapshot = resume_approved_state(snapshot, resolutions, owner_id=principal.id, session_id=session_id)
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(status_code=409, detail="invalid_approval_checkpoint") from exc
            state_snapshot["session"]["execution_id"] = execution_id
            await conn.execute(
                "UPDATE research_sessions SET status = 'running', completed_at = NULL, execution_id = $3::uuid, updated_at = NOW() WHERE id = $1::uuid AND owner_id = $2::uuid",
                session_id, principal.id, execution_id,
            )
            await conn.execute(
                "UPDATE session_runtime_state SET state_snapshot_json = $2::jsonb, runtime_status = 'running', public_status = 'running', pending_approval_count = 0 WHERE session_id = $1::uuid",
                session_id, dumps_json(state_snapshot),
            )
    if state_snapshot is not None:
        kwargs = dict(
            session_id=session_id, query=state_snapshot["user_query"],
            max_revision=int(state_snapshot.get("session", {}).get("max_revisions", 3)),
            user_confirmed=bool(state_snapshot.get("user_confirmed", False)),
            use_internal_docs=bool(state_snapshot.get("use_internal_docs", False)),
            rag_group=state_snapshot.get("rag_group"), output_length=state_snapshot.get("output_length", "medium"),
            skill_context=state_snapshot["skill_context"], owner_id=principal.id,
            channels=state_snapshot.get("session", {}).get("channels", []),
            resume_state=state_snapshot, execution_id=execution_id,
        )
        if background_tasks is not None:
            background_tasks.add_task(run_research_workflow, **kwargs)
        else:
            asyncio.create_task(run_research_workflow(**kwargs))
    return {"approval_id": approval_id, "session_id": session_id, "status": resolved_status,
            "approved_by": principal.username, "request_payload": approval_payload,
            "resumed": state_snapshot is not None}


# ==============================================================
# Background Workflow Execution
# ==============================================================

@router.post('/{session_id}/analysis/resume')
async def resume_research_analysis(session_id: str, background_tasks: BackgroundTasks,
                                   principal: Principal = principal_dependency):
    """Continue retained questions inside the original root's allowance."""
    return await _resume_retained_synthesis(session_id, background_tasks, principal, stage='analysis')


@router.post('/{session_id}/resume')
async def resume_user_paused_research(session_id:uuid.UUID,payload:CancellationRequest,
        background_tasks:BackgroundTasks,principal:Principal=principal_dependency):
    from app.db.research_pause import RESUME_NODES
    from app.graph.compiler import _build_budget_state
    from app.source_lifecycle import current_synthesis_state
    from app.db.execution_control import task_budget
    from datetime import UTC,datetime
    session_id=str(session_id); owner=_principal_id(principal)
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        record=await conn.fetchrow('''SELECT s.status,s.execution_id,s.created_at,s.review_status,
            s.total_tokens,s.total_cost_usd,r.state_snapshot_json,r.checkpoint_seq
            FROM research_sessions s JOIN session_runtime_state r ON r.session_id=s.id
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid''',session_id,owner)
        if not record:raise HTTPException(404,'resume_task_not_found')
        budget=await receipt_budget(conn,session_id,owner,task_budget(record))
    state=deepcopy(_json_object(record['state_snapshot_json']))
    root=state.get('session') or {}; review=_json_object(record['review_status'])
    control=review.get('user_control') or {}; node=root.get('user_resume_node')
    if str(record['execution_id'])!=str(payload.execution_id):
        raise HTTPException(409,'resume_execution_changed_reload')
    if (record['status']!='paused' or state.get('runtime_status')!='user_paused'
            or control.get('state')!='paused' or node not in RESUME_NODES
            or control.get('resume_node')!=node or state.get('pending_approvals')
            or str(root.get('owner_id'))!=owner or str(state.get('task_id'))!=session_id
            or str(root.get('session_id'))!=session_id
            or str(root.get('execution_id'))!=str(record['execution_id'])):
        raise HTTPException(409,'resume_checkpoint_not_recoverable')
    if int(budget.get('inflight_model_requests') or 0):
        raise HTTPException(409,'resume_receipts_pending')
    current=await current_synthesis_state(state)
    if current.get('collected_evidence')!=state.get('collected_evidence'):
        raise HTTPException(409,'resume_sources_changed')
    try:
        started=datetime.fromisoformat(state.get('created_at') or root['created_at'])
        if started.tzinfo:started=started.astimezone(UTC).replace(tzinfo=None)
        database_start=record['created_at']
        if database_start.tzinfo:database_start=database_start.astimezone(UTC).replace(tzinfo=None)
        started=min(started,database_start)
        if started>utc_now_naive():raise ValueError('future_start')
    except (ValueError,TypeError,KeyError):
        raise HTTPException(409,'resume_original_deadline_unavailable')
    state['created_at']=started.isoformat();state['budget_state']=budget
    budget=_build_budget_state(state)
    if (budget.get('hard_stop_reason') or
            int(budget.get('used_total_tokens') or 0)>=int(budget.get('max_total_tokens') or 0) or
            (budget.get('max_cost_usd') is not None and
             float(budget.get('used_cost_usd') or 0)>=float(budget['max_cost_usd']))):
        raise HTTPException(409,'resume_original_allowance_exhausted')
    execution_id=str(uuid.uuid4())
    state.update(status='running',runtime_status='running',budget_state=budget)
    state['session']={**root,'status':'running','execution_id':execution_id}
    state['review_status']={**review,'runtime_status':'running','reason':None,'budget_state':budget,
        'user_control':{**control,'state':'resumed','resumed_at':utc_now_naive().isoformat(),
            'resume_request_id':str(payload.request_id),'execution_id':execution_id}}
    async with pool.acquire() as conn,conn.transaction():
        locked=await conn.fetchrow('''SELECT s.status,s.execution_id,r.checkpoint_seq
            FROM research_sessions s JOIN session_runtime_state r ON r.session_id=s.id
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid FOR UPDATE OF s,r''',session_id,owner)
        if (not locked or locked['status']!='paused' or locked['execution_id']!=record['execution_id']
                or locked['checkpoint_seq']!=record['checkpoint_seq']):
            raise HTTPException(409,'resume_checkpoint_changed')
        await conn.execute('''UPDATE research_sessions SET status='running',execution_id=$3::uuid,
            review_status=$4::jsonb,completed_at=NULL,updated_at=NOW()
            WHERE id=$1::uuid AND owner_id=$2::uuid''',session_id,owner,execution_id,dumps_json(state['review_status']))
        await conn.execute('''UPDATE session_runtime_state SET state_snapshot_json=$2::jsonb,
            public_status='running',runtime_status='running',last_heartbeat_at=NOW()
            WHERE session_id=$1::uuid''',session_id,dumps_json(state))
    await get_sse_manager().begin_run(session_id)
    background_tasks.add_task(run_research_workflow,session_id=session_id,query=state['user_query'],
        owner_id=owner,execution_id=execution_id,resume_state=state,resume_at='user_resume',
        max_revision=int(root.get('max_revisions',3)),user_confirmed=bool(state.get('user_confirmed')),
        use_internal_docs=bool(state.get('use_internal_docs')),rag_group=state.get('rag_group'),
        output_length=state.get('output_length','medium'),skill_context=state.get('skill_context'),
        channels=root.get('channels',[]))
    return {'session_id':session_id,'execution_id':execution_id,'status':'running','resumed':True}


@router.post('/{session_id}/report/resume')
async def resume_research_report(session_id: str, background_tasks: BackgroundTasks,
                                 principal: Principal = principal_dependency):
    """One bounded rewrite using completed analysis and the original allowance."""
    return await _resume_retained_synthesis(session_id, background_tasks, principal, stage='report')


@router.post('/{session_id}/audit/resume')
async def resume_research_audit(session_id: str, background_tasks: BackgroundTasks,
                                principal: Principal = principal_dependency):
    """Resume the unfinished review of this owner's unchanged draft once."""
    return await _resume_retained_synthesis(session_id, background_tasks, principal, stage='audit')


async def _resume_retained_synthesis(session_id, background_tasks, principal, *, stage):
    from datetime import UTC, datetime
    from app.graph.compiler import _build_budget_state, _stage_model_budget, _synthesis_question, _skill_prompt, _agent_skill_hints
    from app.graph.state import deserialize_evidence
    from app.research_context import analysis_binding, analysis_input_matches, workflow_packing_version
    from app.source_lifecycle import current_synthesis_state

    pool=await get_db_pool()
    async with pool.acquire() as conn:
        record=await conn.fetchrow('''SELECT s.status,s.execution_id,s.user_query,s.skill_context,s.created_at,
            r.state_snapshot_json,r.checkpoint_seq FROM research_sessions s
            JOIN session_runtime_state r ON r.session_id=s.id
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid''',session_id,principal.id)
    if not record:raise HTTPException(404,'Session not found')
    state=deepcopy(_json_object(record['state_snapshot_json']))
    root=state.get('session') or {}; workflow=state.get('analysis_workflow') or {}
    report_resume=stage=='report'
    audit_resume=stage=='audit'
    report_stage=report_resume or audit_resume
    review=state.get('review_status') or {}
    module_report=(state.get('organization_result') or {}).get('module_report') or {}
    phase=workflow.get('active_phase')
    reason=workflow.get('stop_reason')
    if report_stage:
        from app.db.report_delivery import report_binding
    if audit_resume:
        audit=review.get('final_report_audit') or {}
        recoverable=(record['status']=='paused' and state.get('status')=='paused'
            and state.get('runtime_status')=='report_paused' and review.get('output_stage')=='report'
            and review.get('report_payload_kind')=='report' and review.get('reason')=='final_audit_incomplete'
            and review.get('report_binding')==report_binding(state) and bool(audit.get('audit_incomplete'))
            and not (review.get('disclosure') or {}).get('requires_reaudit')
            and bool(state.get('final_report')) and bool(module_report.get('reading_structure'))
            and workflow.get('status')=='completed' and bool(state.get('analysis')))
    elif report_resume:
        recoverable=(record['status'] in {'failed','paused'} and state.get('status')==record['status']
            and state.get('runtime_status') in {'retryable_failed','report_paused'}
            and review.get('output_stage')=='report' and review.get('report_payload_kind')=='partial_response'
            and review.get('report_binding')==report_binding(state)
            and (module_report.get('issues') or review.get('last_error_category')=='llm_stream_interrupted')
            and workflow.get('status')=='completed' and bool(state.get('analysis')))
    else:
        recoverable=(record['status']=='paused' and state.get('status')=='paused'
            and state.get('runtime_status')=='analysis_paused' and workflow.get('status')=='paused'
            and isinstance(phase,str)
            and reason in {'analysis_output_incomplete','analysis_provider_unavailable','model_output_limit','insufficient_context_budget'})
    if (not recoverable or str(root.get('owner_id'))!=str(principal.id)
            or str(root.get('session_id'))!=session_id or str(state.get('task_id'))!=session_id
            or root.get('execution_id')!=str(record['execution_id'])
            or state.get('user_query')!=record['user_query']
            or state.get('skill_context')!=_json_object(record['skill_context'])
            or workflow.get('schema_version')!='adrs-analysis-questions-v2'
            or state.get('pending_approvals')):
        raise HTTPException(409,f'{stage}_checkpoint_not_recoverable')
    if report_resume and int(root.get('report_resume_attempts') or 0)>=1:
        raise HTTPException(409,'report_resume_attempt_limit')
    if audit_resume and int(root.get('audit_resume_attempts') or 0)>=1:
        raise HTTPException(409,'audit_resume_attempt_limit')
    if not report_stage and int((workflow.get('attempts') or {}).get(phase,0))>=10:
        raise HTTPException(409,'analysis_phase_attempt_limit')
    current=await current_synthesis_state(state)
    if current.get('collected_evidence')!=state.get('collected_evidence'):
        raise HTTPException(409,'analysis_sources_changed')
    if not analysis_input_matches(state,_synthesis_question(state),
            _skill_prompt(state,'analyst') or None,_agent_skill_hints(state,'analyst'),
            [deserialize_evidence(item) for item in state.get('collected_evidence',[])]):
        # Older synthesis filtered into public-then-private order locally,
        # while the graph retained acquisition order. Recover only that exact
        # historical view when its complete input binding still matches.
        retained=state.get('collected_evidence',[])
        legacy_order=[item for item in retained if item.get('source_type')!='knowledge_base']+[
            item for item in retained if item.get('source_type')=='knowledge_base']
        legacy_expected=analysis_binding(_synthesis_question(state),state.get('organization_research'),
            _skill_prompt(state,'analyst') or None,_agent_skill_hints(state,'analyst'),
            [deserialize_evidence(item) for item in legacy_order],packing_version=workflow_packing_version(workflow),
            research_strategy_version=workflow.get('research_strategy_version'))
        if workflow.get('binding')!=legacy_expected:
            raise HTTPException(409,'analysis_inputs_changed')
        state['collected_evidence']=legacy_order
        workflow['input_order_recovery']={
            'version':'adrs-retained-synthesis-order-v1',
            'reason':'exact_legacy_public_then_private_binding',
            'evidence_ids':[item.get('evidence_id') for item in legacy_order],
        }
    # Reject missing/future clock identities; never establish a fresh start time.
    try:
        started=datetime.fromisoformat(state.get('created_at') or root['created_at'])
        if started.tzinfo:started=started.astimezone(UTC).replace(tzinfo=None)
        database_start=record['created_at']
        if database_start.tzinfo:database_start=database_start.astimezone(UTC).replace(tzinfo=None)
        started=min(started,database_start)
        if started>utc_now_naive():raise ValueError('future_start')
    except (ValueError,TypeError,KeyError):
        raise HTTPException(409,'analysis_original_deadline_unavailable')
    state['created_at']=started.isoformat()
    budget=_build_budget_state(state)
    allowance=_stage_model_budget({**state,'budget_state':budget},'report' if report_stage else 'analyst')
    import time
    cost_exhausted=budget.get('max_cost_usd') is not None and float(budget.get('used_cost_usd') or 0)>=float(budget['max_cost_usd'])
    # This route never dispatches new acquisition. Tool exhaustion cannot
    # erase the separate remaining model allowance; cost/time still apply.
    if (budget.get('hard_stop_reason') not in {None,'tool_call_limit'} or cost_exhausted
            or allowance.available('audit' if audit_resume else 'research')<1024
            or allowance.deadline is None or time.monotonic()>=allowance.deadline):
        raise HTTPException(409,f'{stage}_original_allowance_exhausted')
    budget['model_stop_reason']=None
    state.update(status='running',runtime_status='running',budget_state=budget)
    state['review_status']={**(state.get('review_status') or {}),'blocked':False,'reason':None,
        'last_error_category':None,'runtime_status':'running','budget_state':budget}
    execution_id=str(uuid.uuid4())
    state['session']={**root,'status':'running','execution_id':execution_id}
    state['session']['audit_resume_mode']=audit_resume
    if report_resume:
        state['session']['report_resume_attempts']=int(root.get('report_resume_attempts') or 0)+1
        state['review_status']['report_resume_attempts']=state['session']['report_resume_attempts']
    if audit_resume:
        state['session']['audit_resume_attempts']=int(root.get('audit_resume_attempts') or 0)+1
        state['review_status']['audit_resume_attempts']=state['session']['audit_resume_attempts']
    async with pool.acquire() as conn,conn.transaction():
        locked=await conn.fetchrow('''SELECT s.status,s.execution_id,r.checkpoint_seq
            FROM research_sessions s JOIN session_runtime_state r ON r.session_id=s.id
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid FOR UPDATE OF s,r''',session_id,principal.id)
        if (not locked or locked['status']!=record['status'] or locked['execution_id']!=record['execution_id']
                or locked['checkpoint_seq']!=record['checkpoint_seq']):
            raise HTTPException(409,f'{stage}_checkpoint_changed')
        await conn.execute('''UPDATE research_sessions SET status='running',execution_id=$3::uuid,
            review_status=$4::jsonb,completed_at=NULL,updated_at=NOW()
            WHERE id=$1::uuid AND owner_id=$2::uuid''',session_id,principal.id,execution_id,dumps_json(state['review_status']))
        await conn.execute('''UPDATE session_runtime_state SET state_snapshot_json=$2::jsonb,
            runtime_status='running',public_status='running',last_heartbeat_at=NOW()
            WHERE session_id=$1::uuid''',session_id,dumps_json(state))
    await get_sse_manager().begin_run(session_id)
    background_tasks.add_task(run_research_workflow,session_id=session_id,query=state['user_query'],
        max_revision=int(root.get('max_revisions',3)),user_confirmed=bool(state.get('user_confirmed')),
        use_internal_docs=bool(state.get('use_internal_docs')),rag_group=state.get('rag_group'),
        output_length=state.get('output_length','medium'),skill_context=state.get('skill_context'),
        owner_id=principal.id,channels=root.get('channels',[]),resume_state=state,execution_id=execution_id,
        resume_at='report_resume' if report_stage else 'analysis_resume')
    return {'session_id':session_id,'execution_id':execution_id,'status':'running','resumed':True}

@controlled_execution
@owner_model_execution
async def run_research_workflow(
    session_id: str,
    query: str,
    max_revision: int = 3,
    user_confirmed: bool = False,
    use_internal_docs: bool = False,
    rag_group: str | None = None,
    output_length: str = "medium",
    skill_context: dict[str, Any] | None = None,
    owner_id: str | None = None,
    channels: list[ChannelName] | None = None,
    resume_state: dict[str, Any] | None = None,
    execution_id: str | None = None,
    organization_research: dict[str, Any] | None = None,
    query_understanding: dict[str, Any] | None = None,
    resume_at: str = 'approval_resume',
    initial_budget: dict[str, Any] | None = None,
):
    """
    Execute the LangGraph research workflow in background.

    This function:
    1. Compiles the StateGraph
    2. Creates the initial state
    3. Streams events via SSE
    4. Saves final results to the database
    """
    sse = get_sse_manager()
    runtime_persistence = RuntimePersistence()
    harness = None  # A file mirror failure cannot prevent root-state persistence.

    try:
        budget = deepcopy((resume_state or {}).get('budget_state') or initial_budget or get_research_budget(output_length))
        state = deepcopy(resume_state) if resume_state is not None else create_initial_state(query, session_id)
        await bind_owner_model(owner_id)
        if resume_state is None:
            from app.model_routing import freeze_model_routing
            from app.data_governance import model_class
            state['model_routing']=freeze_model_routing(private=use_internal_docs,
                data_class=model_class(((query_understanding or {}).get('data_governance') or {}).get('initial_class','internal' if use_internal_docs else 'public')),
                deep=((query_understanding or {}).get('slots') or {}).get('depth')=='deep',
                complexity=((query_understanding or {}).get('complexity') or {}).get('level','moderate'))
            state["organization_research"] = organization_research
            state['query_understanding'] = deepcopy(query_understanding)
            state['planning_policy'] = deepcopy((((query_understanding or {}).get('complexity') or {}).get('limits') or {}).get('planning_policy'))
            state["review_status"] = {"organization_research": organization_research, 'query_understanding':query_understanding}
            state.setdefault("session", {})["owner_id"] = owner_id
            state["session"]["channels"] = channels or []
            state["session"]["max_revisions"] = max_revision
            state["session"]["output_length"] = output_length
            extra_constraints = ((query_understanding or {}).get('slots') or {}).get('additional_constraints', '')
            decision = build_guardrail_decision(query + '\n' + extra_constraints, user_confirmed=user_confirmed)
            state["guardrail_decision"] = decision.model_dump()
            state["user_confirmed"] = user_confirmed
            state["use_internal_docs"] = use_internal_docs
            state["rag_group"] = rag_group if use_internal_docs else None
            state["output_length"] = output_length
            state["retrieval_policy"] = {
                "mode": "web_with_internal_docs" if use_internal_docs else "public_web",
                "use_internal_docs": use_internal_docs,
                "rag_group": state["rag_group"],
                "rag_hit_count": 0,
            }
            state["session"]["prompt_profile"] = decision.prompt_profile.value
            state["session"]["enabled_tools"] = _task_tool_allowlist(skill_context or {}, decision.enabled_tools)
            state["session"]["prompt_template"] = compose_guardrail_prompt(query, decision)
            state["runtime_status"] = RuntimeStatus.RUNNING.value
            state["skill_context"] = skill_context or {}
            state["budget_state"] = {
                "budget_profile": output_length,
                "estimated": True,
                **budget,
                "used_total_tokens": 0,
                "used_cost_usd": 0.0,
                "used_tool_calls": 0,
                "elapsed_wall_clock_seconds": 0,
                "hard_stop_reason": None,
                "warning": False,
            }
            state["session"]["harness_state_version"] = 1
            state["session"]["checkpoint_seq"] = 0
            state["session"]["skill_context"] = skill_context or {}
        state["session"]["execution_id"] = execution_id
        # The execution decorator has claimed a running root. Initial state
        # defaults are pending and must not undo that admission in the first save.
        state['status']=TaskStatus.RUNNING.value
        state['session']['status']=TaskStatus.RUNNING.value
        persisted = await runtime_persistence.persist_runtime_snapshot(
            session_id=session_id,
            state=state,
            current_batch=[],
            checkpoint_ref=None,
        )
        if persisted is False:
            return
        if resume_state is not None:
            await sse.begin_run(session_id)
        await sse.publish(session_id, "workflow_start", {
            "session_id": session_id, "query": state["user_query"],
            "organization_research": state.get("organization_research"),
            'query_understanding': {key: (state.get('query_understanding') or {}).get(key)
                for key in ('schema_version','interpretation_id','query_type','slots','temporal','complexity','notes')},
            "timestamp": utc_now_naive().isoformat(),
        })
        await current_control().mirror_runtime(harness)

        # Compile graph
        graph = compile_research_graph()

        # Run with streaming
        config = {
            'recursion_limit': min(4096, max(64,
                (PlanningPolicy.model_validate(state.get('planning_policy') or {}).max_plan_nodes + int(budget.get('max_tool_calls') or 0))*6
                + int(state.get('session', {}).get('max_revisions', 3))*16)),
            "configurable": {
                "thread_id": f"{session_id}:{uuid.uuid4()}",
            }
        }

        graph_input = state
        if resume_state is not None:
            if resume_at not in {'approval_resume','analysis_resume','report_resume','user_resume'}:
                raise ValueError('unsupported_resume_stage')
            graph.update_state(config, state, as_node=resume_at)
            graph_input = None
        accumulated_state = deepcopy(state)
        last_chunk = accumulated_state
        checkpoint_seq = int(state["session"].get("checkpoint_seq", 0))
        async for mode, chunk in graph.astream(graph_input, config, stream_mode=["updates", "values"]):
            check_execution()
            await current_control().flush_traces()
            if isinstance(chunk, dict):
                if mode == "updates":
                    for update in _iter_state_updates(chunk):
                        for key, value in update.items():
                            if key == "agent_trace":
                                for event in value:
                                    event_type = event.get("event_type", "trace") if isinstance(event, dict) else "trace"
                                    await sse.publish(session_id, event_type, event)
                            elif key in {'tool_result_envelopes','tool_handoffs','accepted_tool_operations'}:
                                await sse.publish(session_id, 'state_update', {'key':key,'count':len(value or {})})
                            else:
                                await sse.publish(session_id, "state_update", {"key": key, "value": str(projection(value))[:500] if value else ""})
                    continue
                accumulated_state = deepcopy(chunk)
                last_chunk = accumulated_state
                checkpoint_state = accumulated_state
                checkpoint_batch = checkpoint_state.get("current_executing_nodes", [])
                checkpoint_ref = None
                snapshot = None
                try:
                    snapshot = graph.get_state(config)
                    checkpoint_ref = getattr(snapshot, "config", None)
                except (OSError, RuntimeError, TypeError, ValueError):
                    checkpoint_ref = None
                checkpoint_seq += 1
                checkpoint_state.setdefault("session", {})
                checkpoint_state["session"]["checkpoint_seq"] = checkpoint_seq
                persisted = await runtime_persistence.persist_runtime_snapshot(
                    session_id=session_id,
                    state=checkpoint_state,
                    current_batch=checkpoint_batch,
                    checkpoint_ref=str(checkpoint_ref) if checkpoint_ref is not None else None,
                )
                if persisted is False:
                    return
                await current_control().mirror_runtime(harness)

                from app.db.research_pause import pause_at_boundary
                diagnosis=(checkpoint_state.get('review_status') or {}).get('pause_diagnosis')
                if diagnosis:
                    await sse.publish(session_id,'state_update',{'pause_diagnosis':diagnosis})
                paused=None
                if snapshot is not None:
                    pool=await get_db_pool()
                    async with pool.acquire() as conn,conn.transaction():
                        paused=await pause_at_boundary(conn,current_control().binding,
                            getattr(snapshot,'next',()))
                if paused:
                    await current_control().mirror_runtime(harness)
                    await sse.publish(session_id,'done',paused)
                    return

        # Full values snapshots preserve initial context and reducer semantics.
        final_state: dict[str, Any] = accumulated_state if accumulated_state else last_chunk
        check_execution()

        # Save results to database
        if final_state:
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                completed_at = utc_now_naive()
                citations = final_state.get("citations", [])
                tool_histories = final_state.get("tool_histories", [])
                tool_call_total = sum(
                    len(history.get("tool_calls", []))
                    for history in tool_histories
                    if isinstance(history, dict)
                )
                tool_call_errors = sum(
                    sum(1 for call in history.get("tool_calls", []) if call.get("status") == "error")
                    for history in tool_histories
                    if isinstance(history, dict)
                )
                pending_approval_count = len(final_state.get("pending_approvals", []))
                runtime_status = final_state.get("runtime_status", final_state.get("status", TaskStatus.COMPLETED.value))
                review_status = dict(final_state.get("review_status") or {})
                review_status["organization_research"] = final_state.get("organization_research")
                review_status["organization_result"] = final_state.get("organization_result")
                review_status['query_understanding'] = final_state.get('query_understanding')
                for key in ('plan_manifest', 'plan_history', 'iteration_control', 'planning_policy'):
                    review_status[key] = final_state.get(key)
                tool_audit_rows = normalize_tool_audit_rows(
                    session_id=session_id,
                    tool_histories=tool_histories,
                    node_outcomes=final_state.get("node_outcomes", []),
                )
                session_budget_state = dict(final_state.get("budget_state") or {})
                review_status.update({
                    "runtime_status": runtime_status,
                    "pending_approval_count": pending_approval_count,
                    "budget_state": session_budget_state,
                    "tool_audit_summary": {
                        "total_calls": tool_call_total,
                        "error_calls": tool_call_errors,
                        "persisted_calls": len(tool_audit_rows),
                    },
                })
                last_error_category = None
                for outcome in reversed(final_state.get("node_outcomes", [])):
                    if isinstance(outcome, dict) and outcome.get("error_category"):
                        last_error_category = outcome.get("error_category")
                        break
                if last_error_category and not review_status.get('last_error_category'):
                    review_status["last_error_category"] = last_error_category
                async with conn.transaction():
                    binding=await conn.fetchrow('SELECT owner_id,execution_id,status FROM research_sessions WHERE id=$1::uuid FOR UPDATE',session_id)
                    if (not binding or binding['status']=='canceled'
                            or (execution_id and str(binding['execution_id'])!=str(execution_id))
                            or (owner_id and str(binding['owner_id'])!=str(owner_id))):return
                    session_budget_state=await receipt_budget(conn,session_id,owner_id,session_budget_state)
                    final_state['budget_state']=session_budget_state
                    review_status['budget_state']=session_budget_state
                    final_state.setdefault('session',{}).update(total_tokens=int(session_budget_state.get('used_total_tokens') or 0),
                        total_cost_usd=float(session_budget_state.get('used_cost_usd') or 0))
                    if binding['owner_id']:
                        from app.evidence_ingestion import reconcile_evidence_ledger
                        from app.db.report_delivery import retain_report_version
                        retained=await conn.fetchval("SELECT state_snapshot_json->'evidence_ledger' FROM session_runtime_state WHERE session_id=$1::uuid",session_id)
                        retained=_json_object(retained)
                        archive_state={**final_state,'evidence_ledger':reconcile_evidence_ledger(final_state,retained or None,
                            owner_id=str(binding['owner_id']),session_id=str(session_id))}
                        report_version=await retain_report_version(conn,archive_state,review_status,
                            owner_id=str(binding['owner_id']),session_id=str(session_id))
                        if report_version:review_status['report_version_id']=report_version
                    await conn.execute(
                        """
                        UPDATE research_sessions
                        SET status = $1::varchar,
                            guardrail_decision = $2::jsonb,
                            guardrail_trace = $3::jsonb,
                            evidence_status = $4::jsonb,
                            review_status = $5::jsonb,
                            prompt_profile = $6,
                            prompt_template = $7,
                            enabled_tools = $8::jsonb,
                            final_report = $9,
                            citations = $10::jsonb,
                            agent_trace = $11::jsonb,
                            total_tokens = $12,
                            total_cost_usd = $13,
                            updated_at = $14::timestamp,
                            completed_at = CASE WHEN $1::varchar = 'completed' THEN $14::timestamp ELSE NULL END
                        WHERE id = $15::uuid
                        """,
                        final_state.get("status", TaskStatus.COMPLETED.value),
                        dumps_json(final_state.get("guardrail_decision")),
                        dumps_json(final_state.get("guardrail_trace", [])),
                        dumps_json(final_state.get("evidence_status")),
                        dumps_json(review_status),
                        final_state.get("session", {}).get("prompt_profile"),
                        final_state.get("session", {}).get("prompt_template"),
                        dumps_json(final_state.get("session", {}).get("enabled_tools", [])),
                        final_state.get("final_report", ""),
                        dumps_json(citations),
                        dumps_json(final_state.get("agent_trace", [])),
                        int(final_state.get("session", {}).get("total_tokens", session_budget_state.get("used_total_tokens", 0)) or 0),
                        float(final_state.get("session", {}).get("total_cost_usd", session_budget_state.get("used_cost_usd", 0.0)) or 0.0),
                        completed_at,
                        session_id,
                    )
                    await conn.execute(
                        """
                        INSERT INTO session_budget_state (
                            session_id,
                            max_total_tokens,
                            max_cost_usd,
                            max_tool_calls,
                            max_wall_clock_seconds,
                            max_retries_per_tool,
                            used_total_tokens,
                            used_cost_usd,
                            used_tool_calls,
                            elapsed_wall_clock_seconds,
                            hard_stop_reason,
                            updated_at
                        )
                        VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (session_id) DO UPDATE SET
                            max_total_tokens = EXCLUDED.max_total_tokens,
                            max_cost_usd = EXCLUDED.max_cost_usd,
                            max_tool_calls = EXCLUDED.max_tool_calls,
                            max_wall_clock_seconds = EXCLUDED.max_wall_clock_seconds,
                            max_retries_per_tool = EXCLUDED.max_retries_per_tool,
                            used_total_tokens = EXCLUDED.used_total_tokens,
                            used_cost_usd = EXCLUDED.used_cost_usd,
                            used_tool_calls = EXCLUDED.used_tool_calls,
                            elapsed_wall_clock_seconds = EXCLUDED.elapsed_wall_clock_seconds,
                            hard_stop_reason = EXCLUDED.hard_stop_reason,
                            updated_at = EXCLUDED.updated_at
                        """,
                        session_id,
                        int(session_budget_state.get("max_total_tokens", 0) or 0),
                        float(session_budget_state.get("max_cost_usd", 0.0) or 0.0),
                        int(session_budget_state.get("max_tool_calls", 0) or 0),
                        int(session_budget_state.get("max_wall_clock_seconds", 0) or 0),
                        int(session_budget_state.get("max_retries_per_tool", 0) or 0),
                        int(session_budget_state.get("used_total_tokens", 0) or 0),
                        float(session_budget_state.get("used_cost_usd", 0.0) or 0.0),
                        int(session_budget_state.get("used_tool_calls", 0) or 0),
                        int(session_budget_state.get("elapsed_wall_clock_seconds", 0) or 0),
                        session_budget_state.get("hard_stop_reason"),
                        completed_at,
                    )
                    await conn.execute(
                        "DELETE FROM citations WHERE session_id = $1::uuid",
                        session_id,
                    )
                    if citations:
                        await conn.executemany(
                            """
                            INSERT INTO citations (
                                session_id,
                                citation_id,
                                source_url,
                                source_title,
                                source_type,
                                extracted_evidence,
                                relevance_score,
                                access_timestamp
                            )
                            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
                            """,
                            [
                                (
                                    session_id,
                                    citation.get("citation_id"),
                                    citation.get("source_url"),
                                    citation.get("source_title"),
                                    citation.get("source_type", "web"),
                                    citation.get("extracted_evidence"),
                                    citation.get("relevance_score", 0.0),
                                    completed_at,
                                )
                                for citation in citations
                            ],
                        )
                    if tool_audit_rows:
                        await conn.executemany(
                            """
                            INSERT INTO tool_call_audit (
                                call_id,
                                session_id,
                                node_id,
                                agent_type,
                                tool_name,
                                args_json,
                                args_hash,
                                status,
                                error_category,
                                error_message,
                                retry_count,
                                result_summary,
                                result_hash,
                                tokens_used,
                                cost_usd,
                                decision_id,
                                approved_by,
                                server_fingerprint,
                                safety_json,
                                usage_source,
                                estimated,
                                started_at,
                                completed_at
                            )
                            VALUES (
                                $1, $2::uuid, $3, $4, $5, $6::jsonb, $7, $8, $9, $10,
                                $11, $12, $13, $14, $15, $16, $17, $18, $19::jsonb, $20, $21, $22, $23
                            )
                            ON CONFLICT (call_id) DO UPDATE SET
                                node_id = EXCLUDED.node_id,
                                agent_type = EXCLUDED.agent_type,
                                tool_name = EXCLUDED.tool_name,
                                args_json = EXCLUDED.args_json,
                                args_hash = EXCLUDED.args_hash,
                                status = EXCLUDED.status,
                                error_category = EXCLUDED.error_category,
                                error_message = EXCLUDED.error_message,
                                retry_count = EXCLUDED.retry_count,
                                result_summary = EXCLUDED.result_summary,
                                result_hash = EXCLUDED.result_hash,
                                tokens_used = EXCLUDED.tokens_used,
                                cost_usd = EXCLUDED.cost_usd,
                                decision_id = EXCLUDED.decision_id,
                                approved_by = EXCLUDED.approved_by,
                                server_fingerprint = EXCLUDED.server_fingerprint,
                                safety_json = EXCLUDED.safety_json,
                                usage_source = EXCLUDED.usage_source,
                                estimated = EXCLUDED.estimated,
                                started_at = EXCLUDED.started_at,
                                completed_at = EXCLUDED.completed_at
                            """,
                            tool_audit_rows,
                        )
                final_state["review_status"] = review_status
                persisted = await runtime_persistence.persist_runtime_snapshot(
                    session_id=session_id,
                    state=final_state,
                    current_batch=final_state.get("current_executing_nodes", []),
                    checkpoint_ref="final",
                )
                if persisted is False:
                    return
                await current_control().mirror_runtime(harness)

        # SSE holds its own owner/execution share lock through enqueue. Do not
        # hold a separate update lock while waiting on that publication gate.
        await sse.publish(session_id, "done", {
            "session_id": session_id,"status":final_state.get('status','completed'),
            "timestamp":utc_now_naive().isoformat()})

        logger.info(f"Research workflow completed: {session_id}")

    except Exception as exc:
        control=current_control()
        if control and control.reason in {'execution_canceled','execution_superseded'}:
            logger.info('Research execution stopped: %s',control.reason)
            return
        logger.exception("Research workflow error for %s", session_id)

        try:
            result=await control.persist_failure(exc,control.reason or 'workflow_error')
            if result is None:return
            await control.mirror_runtime(harness)
            event='workflow_error' if result['transitioned'] else 'done'
            await sse.publish(session_id,event,{
                'session_id':session_id,'status':result['status'],
                **({'error':result['failure']['message']} if result['transitioned'] else {}),
                'timestamp':utc_now_naive().isoformat()})
        except (OSError, RuntimeError, asyncpg.PostgresError) as db_error:
            logger.error('Workflow outcome persistence or notice unavailable for %s: %s',session_id,db_error)
