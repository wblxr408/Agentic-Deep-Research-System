"""Root-derived model allowances at the provider boundary, with no prompt authority."""
from __future__ import annotations

import json
import threading
import time
from uuid import uuid4
from types import SimpleNamespace
from typing import Any


class TokenBudgetExceeded(RuntimeError):
    def __init__(self, reason: str = 'token_budget_exhausted'):
        self.reason = reason
        super().__init__(reason)


def request_token_bound(messages: list[dict], **extra: Any) -> int:
    """Conservative text admission, not a claim of exact provider tokenization.

    UTF-8 bytes plus framing avoid the old Chinese chars/4 underestimate.
    Multimodal calls require their own admission adapter before using this path.
    """
    for message in messages:
        if not isinstance(message.get('content'), (str, type(None))):
            raise TokenBudgetExceeded('unsupported_token_accounting_input')
    encoded = json.dumps({'messages':messages, **extra}, ensure_ascii=False)
    return len(encoded.encode('utf-8')) + 256 + 64 * len(messages)


class ModelTokenBudget:
    def __init__(self, limit: int, *, audit_reserve: int = 0,
                 deadline: float | None = None, audit_seconds: float = 0):
        self.limit = max(0, int(limit))
        self.audit_reserve = min(self.limit, max(0, int(audit_reserve)))
        self.deadline = deadline
        self.audit_seconds = max(0, audit_seconds)
        self.calls: list[dict] = []
        self.spent = 0
        self.inflight = 0
        self.stop_reason: str | None = None
        self.context_limit: int | None = None
        self.upgrade_history:list[dict]=[]
        self.capability_upgrades:list[dict]=[]
        self.routing_decisions:list[dict]=[]
        self.phase_events:list[dict]=[]
        self.data_events:list[dict]=[]
        self.data_governance:dict|None=None
        self._lock = threading.Lock()

    def available(self, purpose: str = 'research') -> int:
        held = self.audit_reserve if purpose != 'audit' else 0
        remaining=max(0, self.limit - self.spent - self.inflight - held)
        return min(remaining,self.context_limit) if self.context_limit else remaining

    def call_deadline(self, purpose: str) -> float | None:
        return None if self.deadline is None else self.deadline - (self.audit_seconds if purpose != 'audit' else 0)

    def complete_audit(self,audit:dict) -> bool:
        """Release a finished phase's hold; never add allowance or move deadline."""
        if (not audit or audit.get('needs_review',True) or audit.get('audit_incomplete')
                or audit.get('budget_incomplete')):return False
        with self._lock:
            if self.inflight:return False
            if self.audit_reserve or self.audit_seconds:
                self.phase_events.append({'phase':'audit','status':'completed_reservation_released',
                    'released_tokens':self.audit_reserve,'released_seconds':self.audit_seconds,
                    'limit_unchanged':True,'original_deadline_unchanged':True})
                self.audit_reserve=0;self.audit_seconds=0
        return True

    def reserve(self, request: dict, purpose: str, route: dict | None = None) -> tuple[dict, dict]:
        request = dict(request)
        if request.get('n', 1) != 1:
            raise TokenBudgetExceeded('unsupported_multiple_completions')
        prompt_bound = request_token_bound(request.get('messages') or [],
            **{key:request[key] for key in ('tools','response_format') if key in request})
        if route and route.get('context_tokens') and prompt_bound+int(request.get('max_tokens') or 1024)>route['context_tokens']:
            raise TokenBudgetExceeded('model_context_capability_exceeded')
        with self._lock:
            if self.stop_reason == 'provider_usage_exceeded_reservation':
                raise TokenBudgetExceeded(self.stop_reason)
            deadline = self.call_deadline(purpose)
            if deadline is not None and time.monotonic() >= deadline:
                self.stop_reason = 'model_time_reservation_exhausted'
                raise TokenBudgetExceeded(self.stop_reason)
            available = self.available(purpose)
            completion_cap = min(int(request.get('max_tokens') or 1024), available - prompt_bound)
            minimum_output = min(int(request.get('max_tokens') or 1024),128 if purpose == 'audit' else 1024)
            if completion_cap < minimum_output:
                self.stop_reason = 'token_budget_exhausted'
                raise TokenBudgetExceeded(self.stop_reason)
            request['max_tokens'] = completion_cap
            reservation = prompt_bound + completion_cap
            self.inflight += reservation
            record = {'call_id':str(uuid4()),'started_monotonic':time.monotonic(),
                'purpose':purpose, 'model':request.get('model'), 'prompt_bound':prompt_bound,
                'output_cap':completion_cap,'reserved_tokens':reservation,'status':'inflight'}
            if route:record['routing']=dict(route)
            self.calls.append(record)
        return request, record

    def settle(self, record: dict, response: Any = None, *, interrupted: bool = False):
        usage = getattr(response, 'usage', None)
        if isinstance(response, dict):
            usage = response.get('usage')
        getter = usage.get if isinstance(usage, dict) else lambda key: getattr(usage, key, None)
        prompt, completion, total = (getter(key) for key in ('prompt_tokens','completion_tokens','total_tokens'))
        valid = all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in (prompt,completion))
        if valid:
            total = max(prompt + completion, total if isinstance(total, int) and total >= 0 else 0)
        else:
            total = None
        from app.llm_client import estimate_cost_usd, MODEL_PRICING_USD_PER_1K
        with self._lock:
            if record['status'] != 'inflight':
                return
            started=record.pop('started_monotonic',None)
            record['duration_ms']=max(0,round((time.monotonic()-started)*1000)) if started is not None else None
            charge = total if total is not None and not interrupted else max(total or 0, record['reserved_tokens'])
            self.inflight -= record['reserved_tokens']
            self.spent += charge
            price=(record.get('routing') or {}).get('price')
            configured_price=bool(price and price.get('source') and price.get('input_per_million') is not None
                and price.get('output_per_million') is not None)
            known_price = (configured_price or record['model'] in MODEL_PRICING_USD_PER_1K) and valid and not interrupted
            cost=(prompt*price['input_per_million']+completion*price['output_per_million'])/1000000 if configured_price and valid else (
                estimate_cost_usd(record['model'],prompt_tokens=prompt,completion_tokens=completion) if known_price else 0.0)
            record.update(status='unknown' if interrupted or not valid else 'settled',
                total_tokens=charge, reported_tokens=total, prompt_tokens=prompt if valid else record['prompt_bound'],
                completion_tokens=completion if valid else record['output_cap'], estimated=interrupted or not valid,
                cost_known=known_price, cost_usd=round(cost,6) if known_price else 0.0,
                cost_basis='configured_price_estimate_not_invoice' if configured_price else 'static_reference' if known_price else 'unknown')
            if self.spent > self.limit or (total is not None and total > record['reserved_tokens']):
                self.stop_reason = 'provider_usage_exceeded_reservation'
                raise TokenBudgetExceeded(self.stop_reason)

    def usage(self) -> dict:
        settled = [row for row in self.calls if row['status'] != 'inflight']
        return {'total_tokens':self.spent,'capability_upgrades':list(self.capability_upgrades),
            'phase_events':list(self.phase_events),
            'data_governance_events':list(self.data_events[-64:]),
            'routing_decisions':list(self.routing_decisions[-32:]),'prompt_tokens':sum(row['prompt_tokens'] for row in settled),
            'completion_tokens':sum(row['completion_tokens'] for row in settled),
            'reported_total_tokens':sum(row['reported_tokens'] or 0 for row in settled),
            'cost_usd':sum(row['cost_usd'] for row in settled),
            'cost_known':bool(settled) and all(row['cost_known'] for row in settled),
            'estimated':any(row['estimated'] for row in settled),
            'model_requests':[dict(row) for row in self.calls],
            'model_stop_reason':self.stop_reason}


class BudgetedClient:
    def __init__(self, client: Any, budget: ModelTokenBudget, purpose: str):
        self.route_info=getattr(client,'route_info',None)
        self._client = client._client if isinstance(client, BudgetedClient) else client
        self.budget, self.purpose = budget, purpose
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def __getattr__(self, name):
        return getattr(self._client, name)

    def with_options(self, **options):
        client = self._client.with_options(**options) if hasattr(self._client,'with_options') else self._client
        result=BudgetedClient(client,self.budget,self.purpose)
        result.route_info=self.route_info
        return result

    def create(self, **request):
        validator=getattr(self._client,'validate_dispatch',None)
        if validator is not None:validator()
        from app.data_governance import provider_request
        try:
            request,admission=provider_request(request,self.budget.data_governance,self.route_info)
        except TokenBudgetExceeded as error:
            self.budget.data_events.append({'stage':(self.route_info or {}).get('stage',self.purpose),
                'status':'blocked_before_dispatch','reason':error.reason})
            raise
        self.budget.data_events.append({**admission,'stage':(self.route_info or {}).get('stage',self.purpose),'status':'admitted'})
        request, record = self.budget.reserve(request,self.purpose,self.route_info)
        record['data_governance']=admission
        deadline = self.budget.call_deadline(self.purpose)
        options: dict = {'max_retries':0}
        if deadline is not None:
            options['timeout'] = max(0.1,deadline-time.monotonic())
        client = self._client
        try:
            if hasattr(client,'with_options'):
                client = client.with_options(**options)
            if request.get('stream'):
                request['stream_options'] = {'include_usage':True}
            response = client.chat.completions.create(**request)
        except BaseException:
            self.budget.settle(record,interrupted=True)
            raise
        if not request.get('stream'):
            self.budget.settle(record,response)
            return response

        def stream():
            last_usage = None
            try:
                for event in response:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise TokenBudgetExceeded('model_time_reservation_exhausted')
                    if getattr(event,'usage',None) is not None:
                        last_usage = event
                    yield event
                self.budget.settle(record,last_usage)
            except BaseException:
                self.budget.settle(record,last_usage,interrupted=True)
                raise
            finally:
                close = getattr(response,'close',None)
                if close:
                    close()
        return stream()


def budgeted_client(client, budget: ModelTokenBudget | None, purpose: str):
    return BudgetedClient(client,budget,purpose) if budget is not None else client
