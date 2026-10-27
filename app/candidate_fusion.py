"""Bounded candidate organization. Fusion relevance never establishes a fact."""
from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Literal

from pydantic import Field, model_validator
from app.research_scope import ScopeRecord

VERSION = 'adrs-candidate-fusion-v1'
ROUTES = {'literal', 'bm25', 'fts', 'dense', 'structure', 'stem', 'learned_sparse', 'paired_dense', 'late_interaction', 'multimodal', 'beam', 'web', 'platform'}


class FusionPolicy(ScopeRecord):
    method: Literal['rrf', 'borda', 'min_max', 'z_score'] = 'rrf'
    set_mode: Literal['union', 'intersection'] = 'union'
    per_route_top_k: int = Field(default=40, ge=1, le=100)
    global_top_k: int = Field(default=30, ge=1, le=100)
    route_minimum: int = Field(default=1, ge=0, le=3)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    weights: dict[str, float] = Field(default_factory=dict, max_length=16)
    query_aware: bool = True
    diversity: Literal['none', 'mmr'] = 'mmr'
    relevance_weight: float = Field(default=.8, ge=0, le=1)
    near_duplicate_threshold: float = Field(default=.92, ge=.5, le=1)

    @model_validator(mode='after')
    def bounded_weights(self):
        if any(key not in ROUTES or not math.isfinite(value) or not 0 < value <= 10
               for key, value in self.weights.items()):
            raise ValueError('fusion_weights_require_known_routes_and_positive_finite_values')
        return self


def freeze_policy(policy: FusionPolicy | dict | None) -> dict:
    from app.query_understanding import identity
    value = policy if isinstance(policy, FusionPolicy) else FusionPolicy.model_validate(policy or {})
    body = {'version': VERSION, 'policy': value.model_dump(mode='json')}
    return {**body, 'policy_id': identity(body), 'learning_to_rank': {
        'status': 'not_enabled', 'reason': 'no_versioned_authorized_query_candidate_relevance_labels_or_trained_model'}}


def frozen_policy(snapshot: dict | None) -> dict:
    if not snapshot:
        return FusionPolicy().model_dump(mode='json')
    if snapshot.get('version') != VERSION:
        raise ValueError('unsupported_frozen_fusion_version')
    frozen = freeze_policy(snapshot.get('policy'))
    if frozen['policy_id'] != snapshot.get('policy_id'):
        raise ValueError('frozen_fusion_identity_mismatch')
    return frozen['policy']


def _tokens(text):
    # Bounded lexical overlap, explicitly not an embedding/semantic equivalence.
    text = str(text or '')[:4000].casefold()
    return set(re.findall(r'[a-z0-9_]+|[\u3400-\u9fff]', text)[:512])


def _overlap(left, right):
    return len(left & right) / len(left | right) if left and right else 0.


def fuse_candidates(channels: dict[str, list[dict]], policy: dict | None = None, *,
                    query: str = '', query_type: str | None = None,
                    route_status: dict | None = None) -> tuple[list[dict], dict]:
    """Each input carries scoped id, raw score/direction, content and source key.

    ID coalescing preserves every membership; similar bodies retain their own IDs.
    No retrieval, model, authority widening, cross-owner state, or mutation here.
    """
    cfg = FusionPolicy.model_validate(policy or {})
    if len(channels) > 32 or any(len(rows) > 100 for rows in channels.values()):
        raise ValueError('fusion_input_exceeds_bounded_route_capacity')
    candidates = {}; memberships = defaultdict(list); routes = {}; rules = []
    for route, input_rows in channels.items():
        family = route.split(':', 1)[0]
        if family not in ROUTES:
            raise ValueError('fusion_unknown_route_family')
        weight = cfg.weights.get(family, 1.)
        if cfg.query_aware:
            if query.strip().startswith(('chunk:', 'source:', 'entity:', 'phrase:', '"', '“')) and family == 'literal':
                weight *= 2; rules.append({'route': route, 'rule': 'explicit_literal_selector', 'multiplier': 2})
            elif query_type == 'aggregate' and family in {'literal', 'structure'}:
                weight *= 1.5; rules.append({'route': route, 'rule': 'aggregate_structured_route', 'multiplier': 1.5})
        unique = []; seen = set(); rejected = 0
        for original_rank, row in enumerate(input_rows, 1):
            key = row.get('id')
            if not isinstance(key, str) or not key or len(key) > 2500:
                raise ValueError('fusion_requires_bounded_scoped_candidate_id')
            if key in seen: continue
            seen.add(key)
            if len(unique) >= cfg.per_route_top_k: break
            raw = row.get('score'); direction = row.get('score_direction', 'higher')
            if direction not in {'higher', 'lower', 'unscored'}:
                raise ValueError('fusion_unknown_score_direction')
            usable = isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(raw) and abs(raw)<=1e12 and direction != 'unscored'
            if raw is not None and not usable: rejected += 1
            item = {'id': key, 'rank': original_rank, 'raw_score': raw if usable else None,
                'provider_rank':row.get('provider_rank',original_rank),
                'score_direction': direction, 'score_meaning': row.get('score_meaning'),
                'aligned_score': float(raw) * (-1 if direction == 'lower' else 1) if usable else None}
            unique.append(item)
            candidates.setdefault(key, dict(row))
        values = [item['aligned_score'] for item in unique if item['aligned_score'] is not None]
        low, high = (min(values), max(values)) if values else (None, None)
        mean = sum(values)/len(values) if values else None
        sigma = math.sqrt(sum((value-mean)**2 for value in values)/len(values)) if values else None
        effective = cfg.method
        if effective in {'min_max', 'z_score'} and len(values) != len(unique): effective = 'rrf'
        routes[route] = {'family': family, 'status': (route_status or {}).get(route, {}).get('status', 'completed' if unique else 'empty'),
            'input_count': len(input_rows), 'retained_count': len(unique), 'weight': weight,
            'requested_method': cfg.method, 'effective_method': effective,
            'fallback_reason': 'unscored_or_invalid_route_uses_rank_only' if effective != cfg.method else None,
            'score_statistics': {'n': len(values), 'minimum': low, 'maximum': high, 'mean': mean, 'population_stddev': sigma},
            'rejected_scores': rejected, 'per_route_top_k': cfg.per_route_top_k}
        for position, item in enumerate(unique):
            rank = item['rank']
            # Rank normalization gives each route comparable maximum mass.
            if effective == 'rrf': normalized = (cfg.rrf_k+1)/(cfg.rrf_k+rank)
            elif effective == 'borda': normalized = (len(unique)-position)/max(1, len(unique))
            elif effective == 'min_max': normalized = (item['aligned_score']-low)/(high-low) if high != low else .5
            else:
                z = (item['aligned_score']-mean)/sigma if sigma else 0.
                item['z_score'] = z
                normalized = .5*(1+math.erf(z/math.sqrt(2)))
            item.update(route=route, normalized_score=normalized, weighted_score=normalized*weight)
            memberships[item['id']].append(item)
    required = set(channels)
    admitted = [key for key, entries in memberships.items()
        if cfg.set_mode == 'union' or {entry['route'] for entry in entries} == required]
    total_weight = sum(route['weight'] for route in routes.values()) or 1.
    for key in admitted:
        row = candidates[key]
        row['fusion_score'] = sum(item['weighted_score'] for item in memberships[key])/total_weight
        row['fusion_routes'] = memberships[key]
    ordered = sorted((candidates[key] for key in admitted), key=lambda row: (-row['fusion_score'], row['id']))
    # Work only over the bounded global candidate pool for lexical diversity.
    reserved = []; reserved_ids = set()
    for position in range(cfg.route_minimum):
        for route in routes:
            matches = [row for row in ordered if any(entry['route'] == route for entry in row['fusion_routes'])]
            if position < len(matches) and matches[position]['id'] not in reserved_ids and len(reserved) < cfg.global_top_k:
                reserved.append(matches[position]); reserved_ids.add(matches[position]['id'])
    pool = (reserved + [row for row in ordered if row['id'] not in reserved_ids])[:cfg.global_top_k]
    signatures = {row['id']: _tokens(row.get('content')) for row in pool}
    duplicate_groups = []; assigned = set()
    for index, row in enumerate(pool):
        if row['id'] in assigned: continue
        peers = [other['id'] for other in pool[index+1:] if other['id'] not in assigned
            and _overlap(signatures[row['id']], signatures[other['id']]) >= cfg.near_duplicate_threshold]
        if peers:
            group = [row['id'], *peers]; assigned.update(group)
            duplicate_groups.append({'representative_id': row['id'], 'candidate_ids': group,
                'meaning': 'bounded_lexical_overlap_not_same_document_or_independent_corroboration', 'automatic_removal': False})
    selected = []; remaining = list(pool); covered = defaultdict(int); selections = []
    while remaining:
        outstanding = [route for route in routes if covered[route] < cfg.route_minimum
            and any(any(entry['route'] == route for entry in row['fusion_routes']) for row in remaining)]
        eligible = [row for row in remaining if not outstanding
            or any(entry['route'] in outstanding for entry in row['fusion_routes'])]
        def value(row):
            redundancy = max((_overlap(signatures[row['id']], signatures[prior['id']]) for prior in selected), default=0.)
            score = (cfg.relevance_weight*row['fusion_score']-(1-cfg.relevance_weight)*redundancy
                if cfg.diversity == 'mmr' else row['fusion_score'])
            return score, redundancy
        chosen = min(eligible, key=lambda row: (-value(row)[0], row['id']))
        score, redundancy = value(chosen)
        selections.append({'id': chosen['id'], 'position': len(selected)+1, 'selection_score': score,
            'lexical_redundancy': redundancy, 'route_quota_applied': bool(outstanding)})
        selected.append(chosen); remaining.remove(chosen)
        for entry in chosen['fusion_routes']: covered[entry['route']] += 1
    summary = {'version': VERSION, 'policy': cfg.model_dump(mode='json'), 'routes': routes, 'weight_rules': rules,
        'union_count': len(memberships), 'set_candidate_count': len(admitted), 'global_candidate_count': len(pool),
        'set_mode': cfg.set_mode, 'intersection_incomplete_routes': [name for name, route in routes.items() if route['status'] in {'failed','not_attempted','partial'}],
        'near_duplicate_groups': duplicate_groups, 'selection': selections, 'route_coverage': dict(covered),
        'source_groups': [{'source_key': key, 'candidate_ids': [row['id'] for row in pool if str(row.get('source_key') or row['id']) == key]}
            for key in sorted({str(row.get('source_key') or row['id']) for row in pool})],
        'independence': 'route_agreement_and_body_overlap_do_not_prove_independent_sources',
        'learning_to_rank': {'status': 'not_enabled', 'reason': 'requires_versioned_authorized_labels_and_model'},
        'diversity_scope': 'bounded_lexical_candidate_pool_before_optional_cross_encoder_not_semantic_deduplication'}
    return selected, summary
