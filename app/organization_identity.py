"""Source-backed names from a selected organization's own language entrances."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

VERSION = 'official-language-v1'
GENERIC_NAMES = {'home','homepage','official','website','welcome','university','college',
    'school','institute','laboratory','research','company','corporation','english',
    'of','the','a','an','and','for','at',
    '中文','首页','官网','大学','学院','研究院','研究所','实验室','公司'}


def language_link(label):
    return str(label or '').strip().casefold() in {
        'en', 'english', 'english version', '中文', '简体中文', 'chinese',
        'français', 'deutsch', 'español', '日本語', '한국어',
    }


def secure_language_url(url):
    """Try only TLS for the same explicit language-link target; never use HTTP."""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme == 'http' and parsed.hostname and not parsed.username and not parsed.password
                and parsed.port in (None, 80)):
            authority = parsed.netloc[:-3] if parsed.netloc.endswith(':80') else parsed.netloc
            return parsed._replace(scheme='https', netloc=authority).geturl()
    except ValueError:
        pass
    return url


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
                try:host = urlsplit(url).hostname or ''
                except ValueError:continue
                if any(host == item or host.endswith('.' + item) for item in hosts):
                    allowed.add(request_url_identity(url))
                    allowed.add(request_url_identity(secure_language_url(url)))
        result[entity['entity_id']] = [row['evidence_id'] for row in rows
            if locations(row) & allowed and within_hosts(row, hosts)]
    return result


def title_names_alias(source, alias):
    """Require page branding, rather than a name mentioned in article prose."""
    normalize = lambda text: re.sub(r'\W+', ' ', text.casefold()).strip()
    title, name = normalize(source.get('source_title') or ''), normalize(alias)
    distinctive = any(term not in GENERIC_NAMES for term in re.findall(r'[^\W_]+',name))
    return bool(distinctive and (title == name or title in {'home ' + name, name + ' home'}))


def official_title_claims(configuration, evidence):
    """Propose literal branding mechanically, then use the normal proof checks.

    A model leaving identity_aliases empty must not discard an already acquired
    official name. Generic titles cannot become broad affiliation substrings.
    """
    anchors = identity_sources(configuration, evidence)
    by_id = {item['evidence_id']: item for item in evidence}
    claims = []
    for entity_id, identifiers in anchors.items():
        for identifier in identifiers:
            source = by_id[identifier]
            title = str(source.get('source_title') or '').strip()
            terms = re.findall(r'[^\W_]+',title.casefold())
            if not 2 <= len(title) <= 300 or not any(term not in GENERIC_NAMES for term in terms):
                continue
            # A document URL fallback or a heading absent from the acquired
            # text is not a literal institutional name.
            try:
                if urlsplit(title).scheme or not title_names_alias(source,title):continue
            except ValueError:
                continue
            pattern = r'\s+'.join(re.escape(word) for word in title.split())
            match = re.search(pattern,source.get('content','')[:1600],re.I)
            if match:
                claims.append({'entity_id':entity_id,'alias':title,
                    'proof':{'evidence_id':identifier,'quote':match.group()}})
    return claims
