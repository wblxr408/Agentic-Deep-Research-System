"""Literal source matching, preserving words and every non-whitespace character."""
from __future__ import annotations

import re


def literal_pattern(value: str) -> str:
    """Return a regex, preserving adjacent word separation and punctuation.

    Whitespace may vary around punctuation. Never remove/join words, letters,
    symbols or PDF hyphens, translate, expand acronyms, or execute examples.
    """
    if not isinstance(value,str) or not value.strip() or len(value)>5000:
        raise ValueError('invalid_literal_pattern_input')
    tokens=re.findall(r'\w+|[^\w\s]',value,re.UNICODE)
    if not tokens:raise ValueError('invalid_literal_pattern_input')
    parts=[re.escape(tokens[0])]
    for left,right in zip(tokens,tokens[1:]):
        parts.append(r'\s+' if re.fullmatch(r'\w+',left) and re.fullmatch(r'\w+',right) else r'\s*')
        parts.append(re.escape(right))
    return ''.join(parts)


def source_pattern(value: str, configuration=None) -> str:
    """Only the new frozen field policy changes layout matching."""
    if (configuration or {}).get('publication_metadata_policy') in {'adrs-publication-fields-v3','adrs-publication-fields-v4'}:
        return literal_pattern(value)
    return r'\s+'.join(re.escape(token) for token in value.split())
