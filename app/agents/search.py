"""
Search Agent: performs web search with query expansion and deduplication.

Implements multi-query expansion and result ranking.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, unquote, urlparse

from app.config import get_settings
from app.graph.state import PlanStep, SearchResult

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)


class SearchAgent:
    """
    Handles search query execution with query rewriting and deduplication.

    Expands each plan step into multiple search queries, executes them,
    then deduplicates and ranks the results.
    """

    EXPAND_PROMPT = """Given the original research query, generate 3-5 diverse search queries covering:
1. Core facts and hard data (numbers, statistics)
2. Expert analysis and authoritative opinions
3. Latest news and developments (past 6 months)

Return JSON with a "queries" array of strings."""

    def __init__(self):
        settings = get_settings()
        self.model = settings.llm.model
        self._client: OpenAI | None = None
        self.last_channel_attempts: list[dict] = []
        self.last_fusion:dict={}

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            from app.llm_client import create_llm_client, get_llm_model
            self._client = create_llm_client()
            self.model = get_llm_model()
        return self._client

    def execute(self, plan_steps: list[PlanStep], user_query: str) -> list[SearchResult]:
        """
        Execute search for given plan steps.

        Args:
            plan_steps: Steps assigned to 'search' agent
            user_query: Original user query for context

        Returns:
            List of deduplicated SearchResult objects
        """
        logger.info(f"Search Agent: executing {len(plan_steps)} plan steps")

        all_results: list[SearchResult] = []

        for step in plan_steps:
            try:
                # Step 1: Expand the query
                expanded_queries = self._expand_query(step.target_query, user_query)

                # Step 2: Execute each expanded query
                for query in expanded_queries:
                    results = self._execute_search(query)
                    all_results.extend(results)
                    time.sleep(0.5)  # Rate limiting

            except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
                logger.error(f"Search step error for '{step.target_query}': {e}")
                continue

        # Step 3: Deduplicate and rank
        deduplicated = self._deduplicate(all_results)
        ranked = self._rank_results(deduplicated, user_query)

        logger.info(f"Search Agent: {len(ranked)} unique results after ranking")
        return ranked[:15]  # Top 15 results

    def _expand_query(self, query: str, user_query: str) -> list[str]:
        """Legacy caller has no frozen expansion options; retain its query."""
        return [query]

    def _execute_search(self, query: str) -> list[SearchResult]:
        """
        Execute a single search query.

        Uses DuckDuckGo HTML search for real web results, with the Instant
        Answer API only as a supplemental fallback.
        """
        from app.execution_control import check_execution
        check_execution()
        html_results = self._execute_duckduckgo_html_search(query)
        check_execution()
        if html_results:
            return html_results
        return self._execute_duckduckgo_instant_answer(query)

    def _execute_duckduckgo_html_search(self, query: str) -> list[SearchResult]:
        """Fetch and parse DuckDuckGo's HTML results page."""
        from app.execution_control import check_execution
        check_execution()
        try:
            import requests

            url = "https://html.duckduckgo.com/html/"
            params = {
                "q": query,
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            response = requests.get(url, params=params, headers=headers, timeout=10)
            check_execution()
            if response.status_code != 200:
                logger.warning("DuckDuckGo HTML search returned status %s", response.status_code)
                return []

            return self._parse_duckduckgo_html(response.text, query)

        except (OSError, RuntimeError, TypeError, ValueError, KeyError, AttributeError) as e:
            check_execution()
            logger.warning(f"DuckDuckGo HTML search failed for '{query}': {e}")
            return []

    def _execute_duckduckgo_instant_answer(self, query: str) -> list[SearchResult]:
        """Fallback to DuckDuckGo Instant Answer API."""
        from app.execution_control import check_execution
        check_execution()
        try:
            import requests

            url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            }
            response = requests.get(url, params=params, timeout=10)
            check_execution()
            if response.status_code != 200:
                return []

            data = response.json()
            results: list[SearchResult] = []

            # Extract related topics
            for topic in data.get("RelatedTopics", [])[:8]:
                if "Text" in topic and "URL" in topic:
                    results.append(SearchResult(
                        url=topic["URL"],
                        title=self._clean_html(data.get("Heading", query)),
                        snippet=self._clean_html(topic["Text"])[:300],
                        relevance_score=0.5,
                    ))

            # Extract abstract
            if data.get("AbstractText"):
                results.insert(0, SearchResult(
                    url=data.get("AbstractURL", ""),
                    title=data.get("Heading", query),
                    snippet=data["AbstractText"][:300],
                    relevance_score=0.9,
                ))

            return results

        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
            check_execution()
            logger.warning(f"DuckDuckGo instant answer failed for '{query}': {e}")
            return []

    def _parse_duckduckgo_html(self, html_text: str, query: str) -> list[SearchResult]:
        """Parse title, URL and snippet from DuckDuckGo HTML without extra deps."""
        from html.parser import HTMLParser

        class ResultsParser(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.rows = []
                self.capture = None
                self.parts = []
                self.url = ""

            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                classes = attributes.get("class", "").split()
                if tag == "a" and "result__a" in classes:
                    self.capture, self.parts = "title", []
                    self.url = attributes.get("href", "")
                elif tag in ("a", "div") and "result__snippet" in classes:
                    self.capture, self.parts = "snippet", []

            def handle_data(self, data):
                if self.capture:
                    self.parts.append(data)

            def handle_endtag(self, tag):
                if self.capture == "title" and tag == "a":
                    self.rows.append({"url": self.url, "title": "".join(self.parts), "snippet": ""})
                    self.capture = None
                elif self.capture == "snippet" and tag in ("a", "div"):
                    if self.rows:
                        self.rows[-1]["snippet"] = "".join(self.parts)
                    self.capture = None

        parser = ResultsParser()
        parser.feed(html_text)
        results: list[SearchResult] = []
        for row in parser.rows:
            url = self._normalize_duckduckgo_url(row["url"])
            title = self._clean_html(row["title"])
            snippet = self._clean_html(row["snippet"])
            if not url.startswith("https://") or not title:
                continue
            results.append(SearchResult(url=url, title=title, snippet=snippet[:300] or title,
                                        relevance_score=0.7, domain=urlparse(url).netloc))
            if len(results) >= 10:
                break

        if not results:
            logger.info("DuckDuckGo HTML search parsed 0 results for query: %s", query)
        return results

    def _normalize_duckduckgo_url(self, raw_url: str) -> str:
        """Resolve DuckDuckGo redirect URLs to target URLs."""
        if raw_url.startswith("//"):
            raw_url = f"https:{raw_url}"
        parsed = urlparse(raw_url)
        qs = parse_qs(parsed.query)
        if qs.get("uddg"):
            return unquote(qs["uddg"][0])
        return raw_url

    def _clean_html(self, text: str) -> str:
        """Remove HTML entities and excess whitespace."""
        import html
        import re
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _deduplicate(self, results: list[SearchResult]) -> list[SearchResult]:
        """Remove duplicate URLs, keeping highest-scoring entry."""
        seen: dict[str, SearchResult] = {}
        for r in results:
            if r.url and r.url not in seen or r.url in seen and r.relevance_score > seen[r.url].relevance_score:
                seen[r.url] = r
        return list(seen.values())

    def _rank_results(self, results: list[SearchResult], user_query: str) -> list[SearchResult]:
        """Re-rank results by relevance to the user query."""
        keywords = set(user_query.lower().split())
        for r in results:
            score = r.relevance_score
            title_words = set(r.title.lower().split())
            snippet_words = set(r.snippet.lower().split())
            overlap = len(keywords & title_words) + 0.5 * len(keywords & snippet_words)
            r.relevance_score = score + 0.1 * overlap
        return sorted(results, key=lambda r: r.relevance_score, reverse=True)

    def execute_search(self, query: str, *, channels: list[str] | None = None, owner_id: str | None = None, limit: int = 10, max_calls: int = 24, timeout_seconds: float = 90,
                       query_variants:list[str]|None=None,fusion:dict|None=None,query_type:str|None=None,source_policy=None,
                       required_terms:list[str]|None=None) -> list[SearchResult]:
        """
        Execute a single search query (主题 3 工具接口).

        直接执行单个搜索查询，供 DAG executor 调用。
        """
        from app.channels import ChannelService, CollectionRequest
        from app.channels.catalog import route_query

        channel, operation, routed_query = route_query(query)
        self.last_channel_attempts = []
        self.last_fusion={}
        from app.candidate_fusion import FusionPolicy,fuse_candidates
        from app.external_evidence import request_url_identity
        fusion_policy=FusionPolicy.model_validate(fusion or {}).model_dump(mode='json')
        if not 1<=limit<=100:raise ValueError('search_result_limit_out_of_range')
        fusion_policy['global_top_k']=min(limit,fusion_policy['global_top_k'])
        explicit = channel != "web" or operation == "read" or query.startswith("web:")
        selected = [channel] if explicit else (channels or [channel])
        if len(selected) > 8 or len(selected) != len(set(selected)):
            raise ValueError("select at most eight unique channels")
        # Preserve the existing plain-web interface and its fallback behavior.
        if selected == ["web"] and operation == "search" and not channels and owner_id is None and query_variants is None and fusion is None and source_policy is None and not required_terms:
            return self._execute_search(routed_query)
        service = ChannelService(owner_id, legacy_search=self._execute_search)
        import time
        deadline = time.monotonic() + timeout_seconds
        used_calls = 0
        variants=query_variants if query_variants is not None else [query]
        if not 1<=len(variants)<=4 or len(set(variants))!=len(variants):raise ValueError('invalid_query_variant_count')
        requests=[]
        for variant in variants:
            variant_channel,variant_operation,variant_query=route_query(variant)
            if variant_channel!=channel or variant_operation!=operation:raise ValueError('query_variant_changed_transport')
            requests.extend((name,variant_query) for name in selected)
        fusion_channels={f'{"web" if name=="web" else "platform"}:{position}:{name}':[] for position,(name,_) in enumerate(requests)}
        fusion_status={name:{'status':'not_attempted'} for name in fusion_channels}
        observations={}; scope_rejected=[]
        for position,(name,actual_query) in enumerate(requests):
            remaining=max_calls-used_calls
            seconds=deadline-time.monotonic()
            if remaining<=0 or seconds<=0:break
            slots=len(requests)-position
            share=max(1,remaining//slots)
            result = service.collect(CollectionRequest(channel=name, operation=operation, query=actual_query,
                required_terms=required_terms or [],limit=min(fusion_policy['per_route_top_k'], 20)),
                max_calls=share, timeout_seconds=max(0,seconds/slots))
            used_calls += result.call_count
            self.last_channel_attempts.extend({**a.model_dump(),'query':actual_query,'allocated_calls':share,
                'allocated_seconds':max(0,seconds/slots)} for a in result.attempts)
            group=[SearchResult(url=i.url, title=i.title, snippet=i.content,
                                       domain=urlparse(i.url).netloc, relevance_score=0.7,
                                       channel=i.channel, backend=i.backend, collected_at=i.collected_at,data_governance=i.data_governance)
                          for i in result.items]
            provider_ranks={id(item):rank for rank,item in enumerate(group,1)}
            if source_policy:
                admitted,rejected=source_policy.filter_leads(group)
                scope_rejected.extend(rejected)
                admitted_urls={item['url'] for item in admitted}
                group=[item for item in group if item.url in admitted_urls]
            route=f'{"web" if name=="web" else "platform"}:{position}:{name}'
            fusion_status[route]={'status':result.status}
            for item in group:
                rank=provider_ranks[id(item)]
                try:key=request_url_identity(item.url)
                except (ValueError,TypeError):continue
                fusion_channels[route].append({'id':key,'score':None,'score_direction':'unscored',
                    'provider_rank':rank,
                    'score_meaning':'provider_order_no_comparable_score','content':item.title+' '+item.snippet,
                    'source_key':key,'record':item})
                observations.setdefault(key,[]).append({'route':route,'query':actual_query,'provider_rank':rank,
                    'url':item.url,'channel':item.channel,'backend':item.backend,'collected_at':item.collected_at,
                    'title':item.title[:500],'snippet':item.snippet[:1000]})
            if used_calls >= max_calls or time.monotonic() >= deadline:
                break
        fused,self.last_fusion=fuse_candidates(fusion_channels,fusion_policy,query=query,query_type=query_type,route_status=fusion_status)
        self.last_fusion.update(scope_rejected=scope_rejected,requested_limit=limit,returned_count=len(fused),
            shortfall=max(0,limit-len(fused)),effective_per_route_limit=min(20,fusion_policy['per_route_top_k']))
        output=[]
        for row in fused:
            item=row['record'].model_copy(deep=True)
            item.candidate_fusion={'version':self.last_fusion['version'],'score':row['fusion_score'],
                'memberships':row['fusion_routes'],'observations':observations[row['id']],
                'scope':'discovery_leads_not_full_text_or_support','identity':'version_and_query_preserving_public_URL',
                'duplicate_groups':[group for group in self.last_fusion['near_duplicate_groups'] if row['id'] in group['candidate_ids']]}
            output.append(item)
        return output

    def execute_for_node(self, node_query: str, context: str = "") -> list[SearchResult]:
        """兼容接口：根据节点 query 执行搜索。"""
        return self.execute_search(node_query)
