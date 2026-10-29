"""Source-backed names from a selected organization's own language entrances."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

VERSION = 'official-language-v1'


def language_link(label):
    return str(label or '').strip().casefold() in {
        'en', 'english', 'english version', '中文', '简体中文', 'chinese',
        'français', 'deutsch', 'español', '日本語', '한국어',
    }


def identity_sources(configuration, evidence):
    """Bind an acquired page to an explicit entrance or its literal language link.

    This is a naming anchor, not a network grant or an affiliation verdict.
    Same-host links on an arbitrary paper or search snippet cannot create it.
    """
    from app.external_evidence import request_url_identity
    rows = [item for item in evidence if
            (item.get('acquisition') or {}).get('coverage') != 'discovery_only']
    def locations(row):
        meta = row.get('acquisition') or {}
        return {request_url_identity(value) for value in
            (row.get('source_url'), meta.get('requested_url')) if isinstance(value,str) and value}
    def within_hosts(row, hosts):
        final = (row.get('acquisition') or {}).get('final_url') or row.get('source_url', '')
        host = urlsplit(final).hostname or ''
        return any(host == item or host.endswith('.' + item) for item in hosts)
    result = {}
    for entity in (configuration.get('scope') or {}).get('entities', []):
        seeds = {request_url_identity(str(url)) for url in entity.get('source_urls', [])}
        hosts = {urlsplit(url).hostname.removeprefix('www.') for url in seeds if urlsplit(url).hostname}
        allowed = set(seeds)
        for row in rows:
            if not locations(row) & seeds or not within_hosts(row, hosts):
                continue
            meta = row.get('acquisition') or {}
            for link in meta.get('public_link_records') or []:
                if not isinstance(link, dict) or not language_link(link.get('label')):
                    continue
                url = link.get('url')
                if not isinstance(url, str):continue
                host = urlsplit(url).hostname or ''
                if any(host == item or host.endswith('.' + item) for item in hosts):
                    allowed.add(request_url_identity(url))
        result[entity['entity_id']] = [row['evidence_id'] for row in rows
            if locations(row) & allowed and within_hosts(row, hosts)]
    return result


def title_names_alias(source, alias):
    """Require page branding, rather than a name mentioned in article prose."""
    normalize = lambda text: re.sub(r'\W+', ' ', text.casefold()).strip()
    title, name = normalize(source.get('source_title') or ''), normalize(alias)
    return bool(name and (title == name or title in {'home ' + name, name + ' home'}))
