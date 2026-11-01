"""Provider receipts and disjoint token prices; this module owns no quota or cache."""
from __future__ import annotations

import math
from typing import Any

VERSION = 'adrs-provider-usage-v1'


def _mapping(value: Any) -> dict:
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if hasattr(value, 'model_dump'):
        return _mapping(value.model_dump(mode='json'))
    return _mapping(vars(value)) if hasattr(value, '__dict__') else {}


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return _mapping(value)


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def normalize_usage(usage: Any, *, protocol: str | None = None) -> dict:
    """Missing breakdowns remain unknown even when the logical total is known.

    Chat/Responses inputs include cached tokens. Anthropic input_tokens excludes
    cache reads and creation. DeepSeek hit/miss fields partition prompt_tokens;
    a miss is billed as uncached input, not a second cache-write token charge.
    """
    wrapper = _mapping(usage)
    raw = _mapping(wrapper.get('provider_native_usage', usage))
    protocol = protocol or wrapper.get('provider_usage_protocol')
    if protocol is None:
        if 'cache_read_input_tokens' in raw or 'cache_creation_input_tokens' in raw:
            protocol = 'anthropic_messages'
        elif 'prompt_cache_hit_tokens' in raw or 'prompt_cache_miss_tokens' in raw:
            protocol = 'deepseek_chat'
        elif 'prompt_tokens' in raw:
            protocol = 'chat_completions'
        elif 'input_tokens' in raw:
            protocol = 'responses'
        else:
            protocol = 'unknown'
    errors = []
    for key in ('total_tokens','cache_read_input_tokens','cache_creation_input_tokens',
                'prompt_cache_hit_tokens','prompt_cache_miss_tokens'):
        if key in raw and raw[key] is not None and _count(raw[key]) is None:
            errors.append('invalid_' + key)
    read = write = ordinary = None
    ttl_writes = None
    write_accounting = 'not_reported'
    if protocol == 'anthropic_messages':
        ordinary = _count(raw.get('input_tokens'))
        read = _count(raw.get('cache_read_input_tokens'))
        write = _count(raw.get('cache_creation_input_tokens'))
        completion = _count(raw.get('output_tokens'))
        prompt = sum((ordinary, read, write)) if all(v is not None for v in (ordinary, read, write)) else None
        creation = _mapping(raw.get('cache_creation'))
        if creation:
            ttl_writes = {'5m': _count(creation.get('ephemeral_5m_input_tokens')),
                          '1h': _count(creation.get('ephemeral_1h_input_tokens'))}
            if any(v is None for v in ttl_writes.values()) or sum(ttl_writes.values()) != write:
                errors.append('cache_write_lifetime_breakdown_inconsistent')
                ttl_writes = None
        write_accounting = 'separate_input_category'
    else:
        prompt = _count(raw.get('prompt_tokens' if 'prompt_tokens' in raw else 'input_tokens'))
        completion = _count(raw.get('completion_tokens' if 'completion_tokens' in raw else 'output_tokens'))
        if protocol == 'deepseek_chat':
            read = _count(raw.get('prompt_cache_hit_tokens'))
            ordinary = _count(raw.get('prompt_cache_miss_tokens'))
            # The native miss rate includes cache population; do not add it twice.
            write = 0
            write_accounting = 'included_in_uncached_input_rate'
            if prompt is not None:
                if read is not None and ordinary is None and read <= prompt:
                    ordinary = prompt - read
                elif ordinary is not None and read is None and ordinary <= prompt:
                    read = prompt - ordinary
        else:
            details = _mapping(raw.get('prompt_tokens_details') or raw.get('input_tokens_details'))
            for key in ('cached_tokens','cache_write_tokens'):
                if key in details and details[key] is not None and _count(details[key]) is None:
                    errors.append('invalid_' + key)
            read = _count(details.get('cached_tokens'))
            write = _count(details.get('cache_write_tokens'))
            if prompt is not None and read is not None and write is not None and read + write <= prompt:
                ordinary = prompt - read - write
            if write is not None:
                write_accounting = 'separate_input_category'
    breakdown_complete = (prompt is not None and all(v is not None for v in (ordinary, read, write))
                          and ordinary + read + write == prompt)
    if prompt is not None and sum(value for value in (read, write) if value is not None) > prompt:
        errors.append('reported_cache_input_exceeds_prompt')
    if all(v is not None for v in (prompt, ordinary, read, write)) and not breakdown_complete:
        errors.append('input_categories_do_not_partition_prompt')
    reported = _count(raw.get('total_tokens'))
    valid = prompt is not None and completion is not None
    total = max(prompt + completion, reported or 0) if valid else None
    if reported is not None and valid and reported != prompt + completion:
        errors.append('reported_total_differs_from_input_plus_output')
    return {'schema_version': VERSION, 'provider_usage_protocol': protocol,
            'provider_native_usage': raw, 'usage_valid': valid, 'prompt_tokens': prompt,
            'completion_tokens': completion, 'total_tokens': total,
            'provider_reported_total_tokens': reported,
            'input_tokens': {'uncached': ordinary, 'cache_read': read, 'cache_write': write,
                             'cache_write_by_ttl': ttl_writes, 'cache_write_accounting': write_accounting},
            'input_breakdown_complete': breakdown_complete,
            'cache_observation': 'inconsistent' if errors else 'reported' if breakdown_complete else 'not_fully_reported',
            'usage_issues': errors}


def usage_from_response(response: Any) -> dict:
    usage = response.get('usage') if isinstance(response, dict) else getattr(response, 'usage', None)
    return normalize_usage(usage)


def price_usage(usage: dict, price: dict | None, *, interrupted: bool = False) -> dict:
    """Configured quotes yield estimates, never an invoice or a root refund.

    Return a known subtotal even when another rate, TTL, or count is missing.
    The legacy cost field contains that subtotal and cost_known distinguishes it
    from a complete token estimate. No undocumented discount is inferred.
    """
    price = price or {}
    parts = {}
    inputs = usage['input_tokens']
    categories = {'uncached_input': (inputs['uncached'], price.get('input_per_million')),
                  'cache_read': (inputs['cache_read'], price.get('cache_read_per_million')),
                  'output': (usage['completion_tokens'], price.get('output_per_million'))}
    ttl_writes = inputs['cache_write_by_ttl']
    ttl_rates = price.get('cache_write_per_million_by_ttl') or {}
    if ttl_writes:
        for ttl, count in ttl_writes.items():
            categories['cache_write_' + ttl] = (count, ttl_rates.get(ttl, price.get('cache_write_per_million')))
    else:
        categories['cache_write'] = (inputs['cache_write'], price.get('cache_write_per_million'))
    source = price.get('source')
    for name, (count, rate) in categories.items():
        valid_rate = (isinstance(rate, (int, float)) and not isinstance(rate, bool)
                      and math.isfinite(rate) and rate >= 0 and bool(source))
        known = not interrupted and count is not None and (count == 0 or valid_rate)
        parts[name] = {'tokens': count, 'usd_per_million': rate,
                       'cost_usd': count * rate / 1000000 if known and count else 0.0 if known else None}
    # An inconsistent category decomposition cannot produce a trusted input subtotal.
    if usage['cache_observation'] == 'inconsistent':
        for name, part in parts.items():
            if name != 'output':
                part['cost_usd'] = None
    subtotal = round(sum(part['cost_usd'] for part in parts.values() if part['cost_usd'] is not None), 6)
    complete = (usage['usage_valid'] and usage['input_breakdown_complete'] and not usage['usage_issues']
                and not interrupted and all(part['cost_usd'] is not None for part in parts.values()))
    return {'cost_usd': subtotal, 'cost_known': complete, 'known_token_cost_subtotal_usd': subtotal,
            'token_cost_components': parts, 'price_source': source,
            'cost_basis': ('static_reference' if price.get('basis') == 'static_reference' else
                           'configured_price_estimate_not_invoice') if complete else 'partial_or_unknown_token_price',
            'cost_scope': 'token_rates_only_not_provider_invoice'}
