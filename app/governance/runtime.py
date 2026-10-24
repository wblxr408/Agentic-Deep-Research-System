from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.core.time import utc_now_naive
from app.db.connection import get_db_pool
from app.db.json import dumps_json
from app.graph.state import RuntimeStatus


def _stable_json_hash(value: Any) -> str | None:
    if value is None:
        return None
    payload = dumps_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def public_status_from_runtime(runtime_status: str | None) -> str:
    if runtime_status in (RuntimeStatus.AWAITING_APPROVAL.value,RuntimeStatus.BUDGET_EXHAUSTED.value,
                          RuntimeStatus.ANALYSIS_PAUSED.value,RuntimeStatus.REPORT_PAUSED.value):
        return "paused"
    if runtime_status in (
        RuntimeStatus.PENDING.value,
        RuntimeStatus.APPROVED.value,
    ):
        return "pending"
    if runtime_status in (
        RuntimeStatus.RUNNING.value,
        RuntimeStatus.RETRYABLE_FAILED.value,
    ):
        return "running"
    if runtime_status in (
        RuntimeStatus.TERMINAL_FAILED.value,
    ):
        return "failed"
    if runtime_status==RuntimeStatus.CANCELED.value:return 'canceled'
    if runtime_status == RuntimeStatus.COMPLETED.value:
        return "completed"
    return "running"


def _timestamp(value):
    if value is None:
        return None
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if result.tzinfo is not None:
        result = result.astimezone(UTC).replace(tzinfo=None)
    return result


def build_runtime_review_status(
    *,
    review_status: dict[str, Any] | None,
    runtime_status: str,
    pending_approval_count: int,
    budget_state: dict[str, Any] | None,
    last_error_category: str | None = None,
    tool_audit_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(review_status or {})
    merged["runtime_status"] = runtime_status
    merged["pending_approval_count"] = pending_approval_count
    if budget_state is not None:
        merged["budget_state"] = budget_state
    if last_error_category and not merged.get('last_error_category'):
        merged["last_error_category"] = last_error_category
    if tool_audit_summary is not None:
        merged["tool_audit_summary"] = tool_audit_summary
    return merged


def normalize_tool_audit_rows(
    *,
    session_id: str,
    tool_histories: list[dict[str, Any]],
    node_outcomes: list[dict[str, Any]],
) -> list[tuple[Any, ...]]:
    outcomes_by_call_id: dict[str, dict[str, Any]] = {}
    for outcome in node_outcomes:
        if not isinstance(outcome, dict):
            continue
        call_id = outcome.get("tool_call_id")
        if call_id:
            outcomes_by_call_id[str(call_id)] = outcome

    rows: list[tuple[Any, ...]] = []
    for history in tool_histories:
        if not isinstance(history, dict):
            continue
        agent_type = history.get("agent_type")
        for call in history.get("tool_calls", []):
            if not isinstance(call, dict):
                continue
            call_id = str(call.get("call_id"))
            if not call_id:
                continue
            outcome = outcomes_by_call_id.get(call_id, {})
            args_json = call.get("args") or {}
            result_summary = call.get("result_summary")
            safety_json = call.get("safety_json") or {}
            usage_source = "provider"
            estimated = False
            if call.get("usage_estimated") or outcome.get("usage_estimated"):
                usage_source = "estimated"
                estimated = True
            rows.append((
                call_id,
                session_id,
                outcome.get("node_id"),
                agent_type,
                call.get("tool_name"),
                dumps_json(args_json),
                _stable_json_hash(args_json),
                call.get("status") or "pending",
                outcome.get("error_category"),
                outcome.get("error_message") or call.get("error"),
                int(outcome.get("retry_count") or 0),
                result_summary,
                _stable_json_hash(result_summary),
                int(call.get("tokens_used") or outcome.get("tokens_used") or 0),
                float(call.get("cost_usd") or outcome.get("cost_usd") or 0.0),
                call.get("decision_id"),
                call.get("approved_by"),
                call.get("server_fingerprint"),
                dumps_json(safety_json),
                usage_source,
                estimated,
                _timestamp(call.get("started_at")),
                _timestamp(call.get("completed_at")),
            ))
    return rows


class RuntimePersistence:
    """Crash-safe persistence for runtime state, audits, approvals, and budgets."""
    async def persist_analysis_checkpoint(self, session_id: str, state: dict[str, Any]) -> int | None:
        return await self.persist_model_checkpoint(session_id,state)

    async def persist_model_checkpoint(self, session_id: str, state: dict[str, Any]) -> int | None:
        """Save model progress before dispatch without replacing the evidence ledger."""
        session=state.get('session') or {}
        owner,execution=session.get('owner_id'),session.get('execution_id')
        if (not owner or not execution or str(state.get('task_id'))!=str(session_id)
                or str(session.get('session_id'))!=str(session_id)):return None
        pool=await get_db_pool()
        async with pool.acquire() as conn,conn.transaction():
            binding=await conn.fetchrow('''SELECT owner_id,execution_id,status FROM research_sessions
                WHERE id=$1::uuid FOR UPDATE''',session_id)
            if (not binding or str(binding['owner_id'])!=str(owner) or str(binding['execution_id'])!=str(execution)
                    or binding['status']!='running'):return None
            from app.db.execution_control import receipt_budget
            budget=await receipt_budget(conn,session_id,owner,dict(state.get('budget_state') or {}))
            state['budget_state']=budget
            session.update(total_tokens=int(budget.get('used_total_tokens') or 0),
                total_cost_usd=float(budget.get('used_cost_usd') or 0))
            sequence=await conn.fetchval('''UPDATE session_runtime_state SET
                state_snapshot_json=jsonb_set(jsonb_set(jsonb_set(jsonb_set(jsonb_set(state_snapshot_json,
                    '{analysis_workflow}',$2::jsonb,true),'{budget_state}',$3::jsonb,true),
                    '{session}',$4::jsonb,true),'{session,checkpoint_seq}',to_jsonb(checkpoint_seq+1),true),
                    '{organization_result}',$7::jsonb,true)||'{"status":"running","runtime_status":"running"}'::jsonb,
                runtime_status='running',public_status='running',
                checkpoint_seq=checkpoint_seq+1,last_heartbeat_at=NOW()
                WHERE session_id=$1::uuid AND state_snapshot_json->'session'->>'execution_id'=$5
                    AND COALESCE(state_snapshot_json->'plan_manifest'->>'plan_version','')=$6
                RETURNING checkpoint_seq''',session_id,dumps_json(state.get('analysis_workflow') or {}),
                dumps_json(state.get('budget_state') or {}),dumps_json(session),str(execution),
                str((state.get('plan_manifest') or {}).get('plan_version') or ''),dumps_json(state.get('organization_result')))
            if sequence is None:return None
            await conn.execute('''UPDATE research_sessions SET total_tokens=$2,
                review_status=jsonb_set(jsonb_set(COALESCE(review_status,'{}'::jsonb),'{budget_state}',$3::jsonb,true),
                    '{runtime_status}','"running"'::jsonb,true),
                updated_at=NOW() WHERE id=$1::uuid''',session_id,
                int((state.get('budget_state') or {}).get('used_total_tokens') or 0),dumps_json(state.get('budget_state') or {}))
            return sequence

    async def persist_runtime_snapshot(
        self,
        *,
        session_id: str,
        state: dict[str, Any],
        current_batch: list[str] | None = None,
        checkpoint_ref: str | None = None,
    ) -> bool:
        pool = await get_db_pool()
        runtime_status = state.get("runtime_status", RuntimeStatus.RUNNING.value)
        public_status = public_status_from_runtime(runtime_status)
        # A failed tool does not end the graph while it is still synthesizing.
        # Only the root workflow publishes its final failure/completion state.
        if state.get("status") in {"pending", "running", "completed", "failed", "paused"}:
            public_status = state["status"]
        budget_state = dict(state.get("budget_state") or {})
        pending_approvals = [
            approval for approval in state.get("pending_approvals", [])
            if isinstance(approval, dict)
        ]
        tool_histories = [
            history for history in state.get("tool_histories", [])
            if isinstance(history, dict)
        ]
        node_outcomes = [
            outcome for outcome in state.get("node_outcomes", [])
            if isinstance(outcome, dict)
        ]

        tool_audit_rows = normalize_tool_audit_rows(
            session_id=session_id,
            tool_histories=tool_histories,
            node_outcomes=node_outcomes,
        )
        tool_call_total = sum(
            len(history.get("tool_calls", []))
            for history in tool_histories
        )
        tool_call_errors = sum(
            sum(1 for call in history.get("tool_calls", []) if call.get("status") == "error")
            for history in tool_histories
        )
        last_error_category = None
        for outcome in reversed(node_outcomes):
            if outcome.get("error_category"):
                last_error_category = outcome.get("error_category")
                break

        review_status = build_runtime_review_status(
            review_status=state.get("review_status"),
            runtime_status=runtime_status,
            pending_approval_count=len(pending_approvals),
            budget_state=budget_state,
            last_error_category=last_error_category,
            tool_audit_summary={
                "total_calls": tool_call_total,
                "error_calls": tool_call_errors,
                "persisted_calls": len(tool_audit_rows),
            },
        )

        if state.get("organization_research") is not None:
            review_status["organization_research"] = state["organization_research"]
        if state.get('organization_result') is not None:
            review_status['organization_result']=state['organization_result']
        now = utc_now_naive()
        review_status['query_understanding'] = state.get('query_understanding')
        for key in ('plan_manifest', 'plan_history', 'iteration_control', 'planning_policy'):
            if state.get(key) is not None:
                review_status[key] = state[key]
        async with pool.acquire() as conn, conn.transaction():
                execution_id = state.get("session", {}).get("execution_id")
                binding=await conn.fetchrow('SELECT owner_id,execution_id,status FROM research_sessions WHERE id=$1::uuid FOR UPDATE',session_id)
                if not binding:
                    return False
                if binding['status']=='canceled' and public_status!='canceled':return False
                actual_execution=str(binding['execution_id']) if binding['execution_id'] else None
                if actual_execution != (str(execution_id) if execution_id else None):return False
                actual_owner=str(binding['owner_id']) if binding['owner_id'] else None
                requested_owner=state.get('session',{}).get('owner_id')
                if requested_owner and str(requested_owner)!=actual_owner:
                    raise ValueError('runtime_owner_binding_conflict')
                if state.get('task_id') and str(state['task_id'])!=str(session_id):
                    raise ValueError('runtime_session_binding_conflict')
                stored=await conn.fetchrow('''SELECT state_snapshot_json,checkpoint_seq FROM session_runtime_state
                    WHERE session_id=$1::uuid FOR UPDATE''',session_id)
                previous=json.loads(stored['state_snapshot_json']) if stored and isinstance(stored['state_snapshot_json'],str) else (
                    stored['state_snapshot_json'] if stored else {})
                latest=(previous or {}).get('analysis_workflow') or {}
                incoming=state.get('analysis_workflow') or {}
                same_execution=(previous or {}).get('session',{}).get('execution_id')==execution_id
                missing_completed=not set(latest.get('completed') or {})<=set(incoming.get('completed') or {})
                newer_attempts=any(count>(incoming.get('attempts') or {}).get(key,0)
                    for key,count in (latest.get('attempts') or {}).items())
                newer_status=(latest.get('status') in {'paused','completed'} and incoming.get('status')=='running'
                    and latest.get('attempts')==incoming.get('attempts'))
                stale_phase=bool(latest and same_execution and (not incoming or (
                    latest.get('binding')==incoming.get('binding') and (missing_completed or newer_attempts or newer_status))))
                prior_budget=(previous or {}).get('budget_state') or {}
                paid_progress=bool(same_execution and (
                    int(prior_budget.get('used_total_tokens') or 0)>int(budget_state.get('used_total_tokens') or 0)
                    or len(prior_budget.get('model_requests') or [])>len(budget_state.get('model_requests') or [])
                    or not {item.get('upgrade_id') for item in prior_budget.get('capability_upgrades') or []}
                        <={item.get('upgrade_id') for item in budget_state.get('capability_upgrades') or []}))
                if stale_phase or paid_progress:
                    # An earlier graph value can arrive while the analyst is
                    # saving phases. Keep newer phase results and paid usage;
                    # final graph values with equal/newer phases still replace.
                    state['analysis_workflow']=latest
                    budget_state={**(previous.get('budget_state') or {}),
                        'elapsed_wall_clock_seconds':max(int(budget_state.get('elapsed_wall_clock_seconds') or 0),
                            int((previous.get('budget_state') or {}).get('elapsed_wall_clock_seconds') or 0))}
                    state['budget_state']=budget_state
                    state['session']={**state.get('session',{}),**previous.get('session',{})}
                    review_status['budget_state']=budget_state
                    if paid_progress:
                        state['organization_result']=previous.get('organization_result')
                        review_status['organization_result']=previous.get('organization_result')
                if stored:
                    state.setdefault('session',{})['checkpoint_seq']=max(int(stored['checkpoint_seq'] or 0),
                        int(state.get('session',{}).get('checkpoint_seq') or 0))
                if actual_owner:
                    from app.db.execution_control import receipt_budget
                    budget_state=await receipt_budget(conn,session_id,actual_owner,budget_state)
                    state['budget_state']=budget_state
                    review_status['budget_state']=budget_state
                    state.setdefault('session',{}).update(total_tokens=int(budget_state.get('used_total_tokens') or 0),
                        total_cost_usd=float(budget_state.get('used_cost_usd') or 0))
                    from app.evidence_ingestion import reconcile_evidence_ledger
                    prior=await conn.fetchval("SELECT state_snapshot_json->'evidence_ledger' FROM session_runtime_state WHERE session_id=$1::uuid",session_id)
                    prior=json.loads(prior) if isinstance(prior,str) else prior
                    state['evidence_ledger']=reconcile_evidence_ledger(state,prior,owner_id=actual_owner,session_id=str(session_id))
                    review_status['ingestion']=state['evidence_ledger']['summary']
                    from app.db.report_delivery import retain_report_version
                    report_version=await retain_report_version(conn,state,review_status,owner_id=actual_owner,session_id=str(session_id))
                    if report_version:review_status['report_version_id']=report_version
                state['review_status']=review_status
                await conn.execute(
                    """
                    INSERT INTO session_runtime_state (
                        session_id,
                        runtime_status,
                        public_status,
                        current_batch_json,
                        retryable_failure_count,
                        terminal_failure_reason,
                        pending_approval_count,
                        checkpoint_seq,
                        last_checkpoint_ref,
                        last_heartbeat_at,
                        harness_state_version,
                        state_snapshot_json
                    )
                    VALUES (
                        $1::uuid, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10, $11, $12::jsonb
                    )
                    ON CONFLICT (session_id) DO UPDATE SET
                        runtime_status = EXCLUDED.runtime_status,
                        public_status = EXCLUDED.public_status,
                        current_batch_json = EXCLUDED.current_batch_json,
                        retryable_failure_count = EXCLUDED.retryable_failure_count,
                        terminal_failure_reason = EXCLUDED.terminal_failure_reason,
                        pending_approval_count = EXCLUDED.pending_approval_count,
                        checkpoint_seq = GREATEST(session_runtime_state.checkpoint_seq, EXCLUDED.checkpoint_seq),
                        last_checkpoint_ref = EXCLUDED.last_checkpoint_ref,
                        last_heartbeat_at = EXCLUDED.last_heartbeat_at,
                        harness_state_version = EXCLUDED.harness_state_version,
                        state_snapshot_json = jsonb_set(EXCLUDED.state_snapshot_json,'{session,checkpoint_seq}',
                            to_jsonb(GREATEST(session_runtime_state.checkpoint_seq, EXCLUDED.checkpoint_seq)),true)
                    """,
                    session_id,
                    runtime_status,
                    public_status,
                    dumps_json(current_batch or state.get("current_executing_nodes", [])),
                    sum(1 for outcome in node_outcomes if outcome.get("status") == "retryable_error"),
                    budget_state.get("hard_stop_reason") or last_error_category,
                    len(pending_approvals),
                    int(state.get("session", {}).get("checkpoint_seq", 0) or 0),
                    checkpoint_ref,
                    now,
                    int(state.get("session", {}).get("harness_state_version", 1) or 1),
                    dumps_json(state),
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
                        estimated_usage_count,
                        updated_at
                    )
                    VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
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
                        estimated_usage_count = EXCLUDED.estimated_usage_count,
                        updated_at = EXCLUDED.updated_at
                    """,
                    session_id,
                    int(budget_state.get("max_total_tokens", 0) or 0),
                    float(budget_state.get("max_cost_usd", 0.0) or 0.0),
                    int(budget_state.get("max_tool_calls", 0) or 0),
                    int(budget_state.get("max_wall_clock_seconds", 0) or 0),
                    int(budget_state.get("max_retries_per_tool", 0) or 0),
                    int(budget_state.get("used_total_tokens", 0) or 0),
                    float(budget_state.get("used_cost_usd", 0.0) or 0.0),
                    int(budget_state.get("used_tool_calls", 0) or 0),
                    int(budget_state.get("elapsed_wall_clock_seconds", 0) or 0),
                    budget_state.get("hard_stop_reason"),
                    int(sum(1 for usage in budget_state.get("llm_usage", []) if usage.get("estimated"))),
                    now,
                )
                await conn.execute(
                    """
                    UPDATE research_sessions
                    SET status = CASE WHEN $1 = 'completed' AND final_report IS NULL THEN status ELSE $1 END,
                        review_status = $2::jsonb,
                        total_tokens = $3,
                        total_cost_usd = $4,
                        updated_at = $5
                    WHERE id = $6::uuid
                    """,
                    public_status,
                    dumps_json(review_status),
                    int(state.get("session", {}).get("total_tokens", budget_state.get("used_total_tokens", 0)) or 0),
                    float(state.get("session", {}).get("total_cost_usd", budget_state.get("used_cost_usd", 0.0)) or 0.0),
                    now,
                    session_id,
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
                if pending_approvals:
                    await conn.executemany(
                        """
                        INSERT INTO approval_requests (
                            approval_id,
                            session_id,
                            node_id,
                            tool_name,
                            risk_level,
                            reason,
                            request_payload_json,
                            status,
                            requested_at,
                            resolved_at,
                            resolved_by,
                            comment
                        )
                        VALUES ($1, $2::uuid, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12)
                        ON CONFLICT (approval_id) DO UPDATE SET
                            node_id = EXCLUDED.node_id,
                            tool_name = EXCLUDED.tool_name,
                            risk_level = EXCLUDED.risk_level,
                            reason = EXCLUDED.reason,
                            request_payload_json = EXCLUDED.request_payload_json,
                            status = EXCLUDED.status,
                            resolved_at = EXCLUDED.resolved_at,
                            resolved_by = EXCLUDED.resolved_by,
                            comment = EXCLUDED.comment
                        WHERE approval_requests.status IN ('pending', 'awaiting_approval')
                        """,
                        [
                            (
                                approval["approval_id"],
                                session_id,
                                approval.get("node_id"),
                                approval.get("tool_name"),
                                approval.get("risk_level", "high"),
                                approval.get("reason"),
                                dumps_json(approval.get("request_payload") or {}),
                                approval.get("status", "pending"),
                                _timestamp(approval.get("requested_at")) or now,
                                _timestamp(approval.get("resolved_at")),
                                approval.get("resolved_by"),
                                approval.get("comment"),
                            )
                            for approval in pending_approvals
                            if approval.get("approval_id")
                        ],
                    )
        return True
