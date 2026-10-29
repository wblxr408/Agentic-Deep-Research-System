"""Channel selection, bounded fallback, result validation and passive maintenance."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from app.channels.backends import Backends
from app.channels.catalog import CATALOG
from app.channels.execution import CommandRunner, ExecutionBudget, HttpReader, public_url
from app.channels.models import Attempt, ChannelConfig, ChannelError, CollectionRequest, CollectionResult, SourceItem
from app.channels.store import ChannelStore

STOP_ERRORS = {"auth_required", "account_risk", "rate_limited", "domain_blocked", "disabled",
               "unsupported_input", "not_found", "budget_exceeded", "output_limit",
               'personal_connection_changed','personal_connection_unavailable','personal_connection_redirect_blocked','github_redirect_blocked',
               'credential_url_requires_direct_pinned_source_reader','access_credentials_cannot_be_external_query_data',
               'credential_url_requires_direct_read_not_search_or_proxy'}
PUBLIC_SEARCH_BACKENDS = frozenset({'duckduckgo','bing-rss','exa-mcp'})


class ChannelService:
    def __init__(self, owner_id: str | None = None, *, store=None, commands=None, http=None, legacy_search=None):
        self.owner_id = owner_id
        self.store = store or ChannelStore()
        self.backends = Backends(commands or CommandRunner(), http or HttpReader(), legacy_search)

    def configure(self, channel: str, config: ChannelConfig) -> dict:
        if self.owner_id is None:
            raise ValueError("authenticated owner required")
        spec = CATALOG[channel]
        if len(set(config.backends)) != len(config.backends) or any(b not in (*spec.backends, *spec.optional_backends) for b in config.backends):
            raise ValueError("backend must belong to the selected channel and be unique")
        for feed in config.feeds:
            public_url(feed)
        self.store.configure(self.owner_id, channel, config.model_dump())
        return config.model_dump()

    def catalog(self) -> list[dict]:
        state = self.store.read(self.owner_id)
        return [{"name": spec.name, "label": spec.label, "operations": list(spec.operations),
                 "backends": list(spec.backends), "optional_backends": list(spec.optional_backends),
                 "setup": spec.setup, "config": ChannelConfig(**state["configs"].get(spec.name, {})).model_dump(),
                 "last_attempt": next((a for a in reversed(state["history"]) if a["channel"] == spec.name), None),
                 "verification": "not_checked" if not any(a["channel"] == spec.name for a in state["history"]) else "content_attempt_recorded"}
                for spec in CATALOG.values()]

    def history(self) -> list[dict]:
        return self.store.read(self.owner_id)["history"]

    @staticmethod
    def _items(items, request, spec, backend, timestamp, *, authenticated=False):
        from app.data_governance import classify_source,maximum,text_class
        normalized, seen = [], set()
        for item in items:
            host, _ = public_url(item["url"])
            if spec.domains and not any(host == d or host.endswith("." + d) for d in spec.domains):
                continue
            if item["url"] in seen or not item["content"].strip():
                continue
            seen.add(item["url"])
            governance=classify_source(backend=backend,channel=request.channel,url=item['url'],content=item['content'])
            governance['data_class']=maximum(governance['data_class'],text_class(request.query)[0],
                                              'internal' if authenticated else 'public')
            if authenticated: governance['reasons'].append('personal_authenticated_transport')
            normalized.append(SourceItem(url=item['url'],title=item['title'],content=item['content'][:request.max_chars],
                channel=request.channel,backend=backend,collected_at=timestamp,data_governance=governance))
            if len(normalized) >= request.limit:
                break
        return normalized

    def collect(self, request: CollectionRequest, *, max_calls: int = 8, timeout_seconds: float | None = None,
                public_search_failover: bool = False) -> CollectionResult:
        from app.execution_control import check_execution
        check_execution()
        spec = CATALOG[request.channel]
        provider_scoped=bool(public_search_failover and request.channel=='web' and request.operation=='search')
        config = ChannelConfig(**self.store.read(self.owner_id)["configs"].get(request.channel, {}))
        result = CollectionResult()
        partial_items = []
        timestamp = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()
        deadline = started + min(config.timeout_seconds, timeout_seconds if timeout_seconds is not None else config.timeout_seconds)
        budget = ExecutionBudget(deadline, max_calls)
        selected = config.backends or list(spec.backends)
        # Legacy gh selections never inherit a host login for a personal research request.
        if request.channel == 'github': selected = ['github-api']
        if not config.backends and request.channel == "bilibili" and request.operation == "read":
            selected = ["opencli", "bili", "bilibili-api"]
        if request.operation == "read" and request.channel == "web":
            selected = [b for b in selected if b == "jina"]
        if request.operation == "search" and request.channel in ("web", "linkedin"):
            selected = [b for b in selected if b != "jina"]
        try:
            from app.data_governance import authorize_network
            authorize_network(request.query,None,operation=request.operation)
            if not config.enabled:
                raise ChannelError("disabled")
            if request.operation not in spec.operations:
                raise ChannelError("unsupported_operation")
            github_status = self.store.github_status(self.owner_id) if request.channel=='github' and self.owner_id else {}
            authenticated = bool(github_status.get('enabled'))
            def github_credential():
                credential = self.store.github_credential(self.owner_id,github_status.get('updated_at'))
                if not credential: raise ChannelError('personal_connection_changed')
                return credential
            if request.operation == "read":
                host, _ = public_url(request.query)
                if spec.domains and not any(host == d or host.endswith("." + d) for d in spec.domains):
                    raise ChannelError("unsupported_input")
            history=self.history()
            recent = next((a for a in reversed(history) if a["channel"] == request.channel), None)
            if not provider_scoped and recent and recent.get("error_category") == "rate_limited" and (datetime.now(timezone.utc) - datetime.fromisoformat(recent["timestamp"])).total_seconds() < 60:
                raise ChannelError("rate_limited")
        except ChannelError as exc:
            result.attempts.append(Attempt(channel=request.channel, backend="policy", status="failed", error_category=exc.category))
        else:
            backends=selected[:config.max_attempts]
            for position,backend in enumerate(backends):
                attempt_started = time.monotonic()
                calls_before = budget.used
                try:
                    # Respect this provider's existing cooldown, without making
                    # an unrelated public service inherit the upstream limit.
                    # No same-provider retry, new backend or extra budget here.
                    if provider_scoped and backend in PUBLIC_SEARCH_BACKENDS:
                        recent_backend=next((a for a in reversed(history)
                            if a['channel']==request.channel and a.get('backend')==backend
                            and a.get('call_count',1)>0),None)
                        if recent_backend and recent_backend.get('error_category')=='rate_limited':
                            age=(datetime.now(timezone.utc)-datetime.fromisoformat(recent_backend['timestamp'])).total_seconds()
                            if 0<=age<60:raise ChannelError('rate_limited')
                    from app.data_governance import sensitive_url
                    if request.operation=='read' and sensitive_url(request.query):
                        raise ChannelError('credential_url_requires_direct_pinned_source_reader')
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ChannelError("budget_exceeded")
                    # Fallbacks share one existing deadline and call ledger.
                    # A first upstream must not consume every later option.
                    available_calls=max(0,budget.max_calls-budget.used)
                    attempts_left=max(1,min(len(backends)-position,available_calls))
                    budget.attempt_deadline=time.monotonic()+remaining/attempts_left
                    budget.attempt_max_calls=budget.max_calls-min(attempts_left-1,max(0,available_calls-1))
                    items = (self.backends.collect(request, backend, config, remaining, budget, github_credential=github_credential)
                             if backend=='github-api' and authenticated else self.backends.collect(request, backend, config, remaining, budget))
                    budget.remaining()
                    normalized = self._items(items, request, spec, backend, timestamp,authenticated=authenticated and backend=='github-api')
                    if request.operation=='search' and request.required_terms:
                        from app.evidence_selection import matches_query_terms
                        normalized=[item for item in normalized if matches_query_terms(
                            item.title+' '+item.content,request.required_terms)]
                        if not normalized:
                            raise ChannelError('irrelevant_results')
                    if request.channel == 'web' and request.operation == 'search':
                        from app.evidence_selection import _terms
                        terms=set(_terms(request.query))
                        if terms and normalized:
                            matching=[item for item in normalized if terms & set(_terms(item.title+' '+item.content+' '+item.url))]
                            if not matching:
                                raise ChannelError('irrelevant_results')
                            normalized=matching
                    if not normalized:
                        raise ChannelError("empty_content")
                    result.items = normalized
                    result.attempts.append(Attempt(channel=request.channel, backend=backend, status="success", result_count=len(normalized), duration_ms=int((time.monotonic()-attempt_started)*1000), call_count=budget.used-calls_before))
                    break
                except ChannelError as exc:
                    if exc.partial_items:
                        partial_items = self._items(exc.partial_items, request, spec, backend, timestamp,authenticated=authenticated and backend=='github-api')
                        if request.operation=='search' and request.required_terms:
                            from app.evidence_selection import matches_query_terms
                            partial_items=[item for item in partial_items if matches_query_terms(
                                item.title+' '+item.content,request.required_terms)]
                    result.attempts.append(Attempt(channel=request.channel, backend=backend, status="failed", error_category=exc.category, duration_ms=int((time.monotonic()-attempt_started)*1000), call_count=budget.used-calls_before))
                    independent_limit=provider_scoped and backend in PUBLIC_SEARCH_BACKENDS and exc.category=='rate_limited'
                    if exc.category in STOP_ERRORS and not independent_limit:
                        break
                finally:
                    budget.attempt_deadline=None
                    budget.attempt_max_calls=None
        result.call_count = budget.used
        result.status = "success" if result.items else ("partial" if partial_items else ("empty" if result.attempts and all(a.error_category == "empty_content" for a in result.attempts) else "failed"))
        if not result.items and partial_items:
            result.items = partial_items
        self.store.record(self.owner_id, [a.model_dump() for a in result.attempts], timestamp)
        return result
