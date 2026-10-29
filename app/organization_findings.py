"""Source-anchored organization records and deterministic sampled comparisons.

Models propose records in the existing Analyst call. These ordinary functions
check source text/references and compute views; they never fetch or call models.
"""
from __future__ import annotations

import calendar
import json
import re
from collections import defaultdict
from datetime import date
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field
from app.bibliography import bibtex_entries

from app.research_evaluation import OutputType
from app.research_scope import (
    AffiliationRecord, Identifier, Label, OrganizationEntity, OrganizationRelationship,
    OrganizationResearchScope, OrganizationScopePreviewRequest, OutputRelation,
    ResearchFamily, ResearchOutput, ScopeRecord, preview_organization_scope,
)


class Proof(ScopeRecord):
    evidence_id: Identifier
    quote: str = Field(min_length=3, max_length=600)


class CandidateClaim(ScopeRecord):
    entity_id: Identifier
    name: Label
    type: Literal['university', 'laboratory', 'company']
    aliases: tuple[Label, ...] = ()
    proof: Proof


class IdentityAliasClaim(ScopeRecord):
    entity_id: Identifier
    alias: Label
    proof: Proof


class AffiliationProof(Proof):
    quote: str = Field(min_length=3, max_length=1600)


class AffiliationClaim(ScopeRecord):
    entity_id: Identifier
    author_name: Label
    raw_affiliation: Label
    proof: AffiliationProof


class PublicationClaim(ScopeRecord):
    output_id: Identifier
    title: Label
    output_type: OutputType
    publication_date: str | None = None
    title_proof: Proof
    date_proof: Proof | None = None
    affiliations: tuple[AffiliationClaim, ...] = Field(default=(), max_length=50)
    venue: Label | None = None
    venue_proof: Proof | None = None


class FamilyClaim(ScopeRecord):
    family_id: Identifier
    output_ids: tuple[Identifier, ...] = Field(min_length=2, max_length=100)
    proof: Proof


class ParentClaim(ScopeRecord):
    parent_id: Identifier
    child_id: Identifier
    valid_from: date | None = None
    valid_to: date | None = None
    proof: Proof


class RelationClaim(ScopeRecord):
    output_id: Identifier
    kind: Literal['funding', 'citation']
    entity_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=200)
    proof: Proof


class Interpretation(ScopeRecord):
    entity_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=2000)
    kind: Literal['inference', 'recommendation']
    basis: tuple[Proof, ...] = Field(min_length=1, max_length=10)


EXTRACTION_INSTRUCTIONS = """
Return one JSON object with root fields analysis_text (concise Markdown narrative)
and organization_data (REQUIRED structured object). The following is the shape of
organization_data, which must be nested under that exact root key, not prose:
{
 "identity_aliases": [{"entity_id":"SELECTED ID","alias":"literal official page title","proof":{"evidence_id":"ev-...","quote":"literal official name"}}],
 "candidate_entities": [{"entity_id":"new-id","name":"exact source name","type":"university|laboratory|company","aliases":[],"proof":{"evidence_id":"ev-...","quote":"exact source excerpt"}}],
 "outputs": [{"output_id":"stable-within-this-response","title":"full publication title","output_type":"conference_paper|journal_article|preprint|book|software|dataset","publication_date":"YYYY or YYYY-MM or YYYY-MM-DD, null if unknown","title_proof":{"evidence_id":"ev-...","quote":"exact full title"},"date_proof":{"evidence_id":"ev-...","quote":"actual publication date/year or BibTeX year"},"venue":"source venue, or null","venue_proof":{"evidence_id":"ev-...","quote":"source venue text"},"affiliations":[{"entity_id":"ID FROM SELECTED SCOPE, or a candidate ID","author_name":"source author","raw_affiliation":"source organization text","proof":{"evidence_id":"ev-...","quote":"author AND organization together in the publication author list"}}]}],
 "research_families":[{"family_id":"id","output_ids":["id1","id2"],"proof":{"evidence_id":"ev-...","quote":"explicit version relationship containing both titles"}}],
 "relationships":[{"parent_id":"id","child_id":"id","valid_from":null,"valid_to":null,"proof":{"evidence_id":"ev-...","quote":"explicit part-of relationship"}}],
 "output_relations":[{"output_id":"id","kind":"funding|citation","entity_ids":["id"],"proof":{"evidence_id":"ev-...","quote":"explicit funding/citation, never coauthor inference"}}],
 "interpretations":[{"entity_ids":["selected-id"],"statement":"analysis or suggested next action, not verified fact","kind":"inference|recommendation","basis":[{"evidence_id":"ev-...","quote":"supporting source excerpt"}]}]
}
Use only provided evidence IDs and literal excerpts, never citation:N in proof IDs.
No proof means omit/leave unknown. Empty arrays are valid and will be reported as gaps.
Preserve SELECTED entity IDs exactly. Do not list selected IDs as new candidates.
Resolve another-language selected name only from a provided official identity
entrance whose page title names that alias; put the literal name in identity_aliases.
Do not translate a raw affiliation or proof to match the selected object's language.
One affiliation record represents ONE author. Copy the original author and institution
spelling and one continuous excerpt containing both, including numbered affiliations
when used. It may be up to 1600 characters; never insert ellipses, join disjoint text,
or concatenate several authors into author_name. Keep their affiliation markers.
Extract the actual primary work on a publication page, not unrelated bibliography entries.
Title, date and author affiliation must refer to the same primary work; quote the
publication author list, not a biography or present-day appointment. If only a year
is known return that year; never invent January 1 or a publication day/month.
Use the finest publication precision actually supported. A primary conference
paper's proceedings cover or ACM reference block such as July 10–12, 2024
supports proceedings month 2024-07, not a precise publication day. Preserve that
literal date range in date_proof. Received/accepted/revised dates, later errata,
and dates of works in the bibliography are not this work's publication date.
If a reference block supplies only a year, return only YYYY; a conference name
or edition cannot supply an absent month. A preprint's version date is not proof
of its first release; keep the source's actual date and distinguish that basis.
Do not use retrieval timestamps as publication dates. Do not manufacture grants,
formal partnerships, venue IDs, family links, metrics, totals or rankings.
Each selected object should have a source-backed interpretation/recommendation
when requested, with explicit uncertainty. Facts and sample counts are computed
separately from accepted records, and do not mean the real-world publication census.
Keep analysis_text concise enough to return the COMPLETE organization_data in the
same response. Never put organization_data in a Markdown code block inside analysis_text.
"""


def _text(value: str) -> str:
    return ' '.join(value.casefold().split())


def _contains(text: str, value: str) -> bool:
    return _text(value) in _text(text)


def _date_bounds(value: str):
    if not re.fullmatch(r'\d{4}(?:-\d{2}){0,2}', value):
        raise ValueError('unknown publication date precision')
    parts = [int(part) for part in value.split('-')]
    year = parts[0]
    if not 1800 <= year <= 2200:
        raise ValueError('publication year out of range')
    if len(parts) == 1:
        return date(year, 1, 1), date(year, 12, 31), 'year'
    if len(parts) == 2:
        month = parts[1]
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), 'month'
    exact = date(*parts)
    return exact, exact, 'day'


def _publication_url(value: str) -> str:
    split = urlsplit(value)
    query = [(key, val) for key, val in parse_qsl(split.query) if not key.startswith('utm_') and key not in {'gclid', 'fbclid'}]
    return urlunsplit((split.scheme, split.netloc.lower(), split.path.rstrip('/'), urlencode(query), ''))


def _publication_opening(source: dict) -> str:
    acquisition = source.get('acquisition') or {}
    opening_end = 3000
    if acquisition.get('format') == 'pdf':
        pages = acquisition.get('pages') or []
        opening_end = min(16000, max((page.get('end', 0) for page in pages[:2]), default=3000))
    opening = source['content'][:opening_end]
    abstract = re.search(r'(?im)^[ \t]*(?:abstract|摘要|(?:1\.?\s+)?introduction|引言)(?:[.：:\s—–-]|$)', opening)
    return opening[:abstract.start()] if abstract else opening


def _literal_date_support(quote: str, value: str, *, proceedings: bool) -> tuple[str, str] | None:
    """Match a literal calendar date without requiring its ISO spelling in prose.

    A conference range establishes an issue month/year, never a publication day.
    Multiple different dates in one excerpt remain ambiguous rather than picking
    the one matching the model proposal. No coarse proposal is silently refined.
    """
    if re.search(r'\b(?:received|accepted|revised|correction|erratum)\b', quote, re.I):
        return None
    lower, upper, precision = _date_bounds(value)
    names = {name.casefold(): index for index in range(1, 13)
             for name in (calendar.month_name[index], calendar.month_abbr[index])}
    months = '|'.join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    patterns = (
        rf'\b(?P<month>{months})\.?\s+(?P<day>\d{{1,2}})(?:\s*[-–—]\s*(?P<last>\d{{1,2}}))?,?\s+(?P<year>\d{{4}})\b',
        rf'\b(?P<day>\d{{1,2}})(?:\s*[-–—]\s*(?P<last>\d{{1,2}}))?\s+(?P<month>{months})\.?\s+(?P<year>\d{{4}})\b',
        rf'\b(?P<month>{months})\.?\s+(?P<year>\d{{4}})\b',
        r'(?<![\w/-])(?P<year>\d{4})[-/](?P<month_number>\d{1,2})(?:[-/](?P<day>\d{1,2}))?(?![\w/-])',
    )
    candidates = {}
    occupied = []
    for pattern in patterns:
        for match in re.finditer(pattern, quote, re.I):
            # A month-year substring inside a complete date is the same date,
            # not a second conflicting calendar interval.
            if any(start <= match.start() and match.end() <= end for start, end in occupied):
                continue
            fields = match.groupdict()
            try:
                year = int(fields['year'])
                month = int(fields['month_number']) if fields.get('month_number') else names[fields['month'].casefold()]
                day = int(fields['day']) if fields.get('day') else 1
                last = int(fields['last']) if fields.get('last') else day if fields.get('day') else calendar.monthrange(year, month)[1]
                start, end = date(year, month, day), date(year, month, last)
                if end < start:
                    return None
            except (KeyError, ValueError):
                return None
            candidates[(start, end)] = (match[0], bool(fields.get('last')))
            occupied.append(match.span())
    if not candidates:
        # A standalone year remains a year. Do not match digits inside another
        # date, an identifier, or a longer number.
        years=set(re.findall(r'(?<![\w/-])(?:18|19|20|21|22)\d{2}(?![\w/-])',quote))
        if precision == 'year' and years == {value}:
            return value, 'literal_publication_year'
        return None
    if len(candidates) != 1:
        return None
    (start, end), (literal, explicit_range) = next(iter(candidates.items()))
    if not lower <= start <= end <= upper:
        return None
    if explicit_range and not proceedings:
        return None
    if proceedings:
        if precision == 'day':
            return None
        return literal, 'conference_proceedings_' + precision
    return literal, 'literal_publication_date'


def _publisher_date_fields(source: dict, title: str, value: str) -> list[str]:
    """Recognize provider date formats without interpreting a model paraphrase."""
    parts = value.split('-')
    for entry in bibtex_entries(source['content']):
        if not _contains(entry.replace('{', '').replace('}', ''), title):
            continue
        year = re.search(r'\byear\s*=\s*[{"]?(\d{4})', entry, re.I)
        month = re.search(r'\bmonth\s*=\s*[{"]?([A-Za-z]+|\d{1,2})', entry, re.I)
        if not year or year[1] != parts[0]:
            continue
        if len(parts) == 1:
            return [year[0]]
        if len(parts) == 2 and month:
            names = {name.casefold(): index for index, name in enumerate(calendar.month_abbr) if name}
            names.update({name.casefold(): index for index, name in enumerate(calendar.month_name) if name})
            number = int(month[1]) if month[1].isdigit() else names.get(month[1].casefold())
            if number == int(parts[1]):
                return [year[0], month[0]]
    # Citation metadata accepts only the explicitly supplied ISO precision.
    match = re.search(r'(?m)^citation_(?:publication_)?date:\s*([^\n]+)', source['content'])
    if match and re.match(re.escape(value) + r'(?:$|[ /-])', match[1].strip().replace('/', '-')):
        return [match[0]]
    # Publisher-labelled dates are distinct from Received/Accepted, corrections
    # and dates in the bibliography. Use the first explicit publication label;
    # never search later labels for one that happens to fit the model's date.
    names = {name.casefold(): index for index, name in enumerate(calendar.month_name) if name}
    names.update({name.casefold(): index for index, name in enumerate(calendar.month_abbr) if name})
    months = '|'.join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    labelled = re.search(r'(?im)(?:^|[;\n])\s*[>*-]?\s*(?:Published(?: online)?|Publication date)\s*:\s*('
                         + r'(?:' + months + r')\s+\d{1,2},?\s+\d{4}'
                         + r'|\d{1,2}\s+(?:' + months + r')\s+\d{4}'
                         + r'|\d{4}[-/]\d{2}[-/]\d{2})\b', source['content'])
    if labelled:
        raw = labelled[1]
        tokens = raw.replace(',', '').split()
        try:
            if len(tokens) == 3:
                month_first = tokens[0].casefold() in names
                month = names[tokens[0 if month_first else 1].casefold()]
                day = int(tokens[1 if month_first else 0])
                parsed = date(int(tokens[2]), month, day)
            else:
                parsed = date.fromisoformat(raw.replace('/', '-'))
            if parsed.isoformat().startswith(value):
                return [labelled[0].strip()]
        except (KeyError, ValueError):
            pass
    return []


def build_organization_findings(configuration: dict | None, evidence: list[dict], proposed: dict | None) -> dict | None:
    if configuration is None:
        return None
    from app.organization_runtime import organization_evidence_views

    result = organization_evidence_views(configuration, evidence)
    scope = OrganizationResearchScope.model_validate(configuration['scope'])
    sources = {item['evidence_id']: item for item in evidence if item.get('source_url')}
    primary_documents = defaultdict(list)
    for item in sources.values():
        if (item.get('acquisition') or {}).get('format') == 'pdf':
            primary_documents[_publication_url(item['source_url'])].append((item, _publication_opening(item)))
    proposed = proposed if isinstance(proposed, dict) else {}
    pending, proofs = [], []
    if not proposed:
        pending.append({'kind': 'extraction', 'reason': 'No structured extraction available; empty sample counts do not establish absence of real outputs.'})

    def check(proof: Proof):
        source = sources.get(proof.evidence_id)
        if source is None:
            raise ValueError('unknown or unavailable evidence ID')
        if (source.get('acquisition') or {}).get('coverage') == 'discovery_only':
            raise ValueError('discovery snippets are leads, not acquired primary publication proof')
        # Tolerate whitespace/layout only; retain original character offsets/text.
        pattern = r'\s+'.join(re.escape(word) for word in proof.quote.split())
        match = re.search(pattern, source['content'], re.I)
        if not match:
            raise ValueError('quoted text not found in acquired source')
        checked = {'evidence_id': proof.evidence_id, 'source_url': source['source_url'],
                   'start': match.start(), 'end': match.end(), 'quote': match.group()}
        if checked not in proofs:
            proofs.append(checked)
        return source

    def records(key, model, limit):
        values = proposed.get(key, [])
        if not isinstance(values, list):
            pending.append({'kind': key, 'reason': 'expected an array'})
            return
        if len(values) > limit:
            pending.append({'kind': key, 'reason': f'{len(values) - limit} records exceed the bounded extraction limit'})
        for index, value in enumerate(values[:limit]):
            try:
                yield model.model_validate(value)
            except ValueError as error:
                pending.append({'kind': key, 'index': index, 'reason': str(error)[:500]})

    catalog = {entity.entity_id: entity for entity in scope.entities}
    from app.organization_identity import identity_sources, title_names_alias, official_title_claims
    identity_anchors = identity_sources(configuration, evidence)
    identity_aliases = []
    proposed = {**proposed,'identity_aliases':[
        *official_title_claims(configuration,evidence),
        *(proposed.get('identity_aliases') if isinstance(proposed.get('identity_aliases'),list) else [])]}
    for claim in records('identity_aliases', IdentityAliasClaim, 100):
        try:
            source = check(claim.proof)
            entity = catalog.get(claim.entity_id)
            if (entity is None or source['evidence_id'] not in identity_anchors.get(claim.entity_id, [])
                    or not _contains(claim.proof.quote, claim.alias)
                    or not title_names_alias(source, claim.alias)):
                raise ValueError('alias has no selected official language entrance and literal page title')
            if any(other.entity_id != entity.entity_id and any(_text(claim.alias) == _text(name)
                    for name in (other.name, *other.aliases)) for other in catalog.values()):
                raise ValueError('alias conflicts with another selected identity')
            aliases = tuple(dict.fromkeys((*entity.aliases, claim.alias)))
            if len(aliases) > 30:raise ValueError('identity alias limit exceeded')
            catalog[entity.entity_id] = entity.model_copy(update={'aliases': aliases})
            record={'entity_id': entity.entity_id, 'alias': claim.alias,
                'proof': claim.proof.model_dump(), 'basis': 'selected_official_language_entrance_title'}
            if record not in identity_aliases:identity_aliases.append(record)
        except ValueError as error:
            pending.append({'kind': 'identity_alias', 'reason': str(error)})
    scope = scope.model_copy(update={'entities': tuple(catalog[item.entity_id] for item in scope.entities)})
    candidates = []
    for candidate in records('candidate_entities', CandidateClaim, 200):
        try:
            source = check(candidate.proof)
            if candidate.entity_id in catalog or not _contains(candidate.proof.quote, candidate.name):
                raise ValueError('candidate identity conflicts or is not named by its proof')
            if len(candidate.aliases)>30 or any(not _contains(candidate.proof.quote, alias) for alias in candidate.aliases):
                raise ValueError('candidate aliases require literal identity proof')
            entity = OrganizationEntity(entity_id=candidate.entity_id, name=candidate.name, type=candidate.type,
                aliases=candidate.aliases, source_urls=(source['source_url'],), resolution_status='pending')
            catalog[entity.entity_id] = entity
            candidates.append(entity)
        except ValueError as error:
            pending.append({'kind': 'candidate', 'id': candidate.entity_id, 'reason': str(error)})

    outputs, publications, canonical = [], {}, {}
    publication_meta = {}
    for publication in records('outputs', PublicationClaim, 1000):
        reason_code = None
        try:
            source = check(publication.title_proof)
            if not _contains(publication.title_proof.quote, publication.title):
                # A short model excerpt may identify the page; locate the full
                # declared title in that same acquired source before accepting it.
                check(Proof(evidence_id=publication.title_proof.evidence_id, quote=publication.title))
            acquisition=source.get('acquisition') or {}
            title_field=source.get('source_title') or ''
            opening=_publication_opening(source)
            locator_title=urlsplit(title_field).scheme in {'http','https'}
            primary_fields=[title_field]
            if acquisition.get('format')=='pdf' or not title_field or locator_title:
                primary_fields.append(opening)
            # A PDF reader's fallback title is often its URL. It must not
            # override a literal primary title retained on the opening pages.
            if not any(_contains(value,publication.title) for value in primary_fields):
                raise ValueError('source does not identify this primary publication')
            metadata = (source.get('acquisition') or {}).get('publisher_metadata')
            if metadata and _text(metadata['title']) == _text(publication.title):
                lower, upper, precision = date.fromisoformat(metadata['published_on']), date.fromisoformat(metadata['published_until']), metadata['date_precision']
                provider_fields = [item['quote'] for key, item in metadata['literal_fields'].items() if key in {'year', 'month'}]
            else:
                if not publication.publication_date:
                    raise ValueError('publication date is unknown')
                lower, upper, precision = _date_bounds(publication.publication_date)
                provider_fields = _publisher_date_fields(source, publication.title, publication.publication_date)
            date_evidence_id = publication.title_proof.evidence_id
            date_basis = 'publisher_fields'
            if provider_fields:
                for field in provider_fields:
                    check(Proof(evidence_id=date_evidence_id, quote=field))
            else:
                if publication.date_proof is None:
                    raise ValueError('publication date has no publisher fields or literal proof')
                date_source = check(publication.date_proof)
                if not _contains(date_source['content'], publication.title):
                    raise ValueError('date proof is not tied to the same publication')
                date_opening = date_source['content'][:16000 if (date_source.get('acquisition') or {}).get('format') == 'pdf' else 4000]
                proceedings = publication.output_type == 'conference_paper' and bool(
                    re.search(r'\b(?:proceedings|ACM reference format)\b', date_opening, re.I))
                supported = _literal_date_support(publication.date_proof.quote, publication.publication_date,
                                                  proceedings=proceedings)
                if not supported or (proceedings and not _contains(date_opening, supported[0])):
                    raise ValueError('publication date was not present at its declared precision')
                date_basis = supported[1]
                if publication.output_type == 'preprint' and re.search(r'\barxiv:\s*\d{4}\.\d{4,5}v\d+\b',
                        publication.date_proof.quote,re.I):
                    date_basis = 'literal_preprint_version_date_not_first_release'
                date_evidence_id = publication.date_proof.evidence_id
            from app.organization_corpus import date_membership, PUBLICATION_ALIAS_VERSIONS
            membership = date_membership(lower, upper, scope.start_date, scope.end_date)
            if membership != 'within':
                reason_code = 'publication_date_out_of_scope' if membership == 'outside' else 'date_precision_overlaps_scope'
                raise ValueError('publication date interval is outside scope' if membership == 'outside' else 'publication date precision cannot resolve scope membership')
            requested_types = (configuration.get('corpus') or {}).get('output_types', [])
            if requested_types and publication.output_type not in requested_types:
                reason_code = 'output_type_out_of_scope'
                raise ValueError('proposed output type is outside the requested types')
            affiliations = []
            evidence_ids = {publication.title_proof.evidence_id, date_evidence_id}
            for affiliation in publication.affiliations:
                try:
                    if re.search(r'[;；\n]',affiliation.author_name):
                        raise ValueError('one affiliation record must name one author')
                    affiliation_source = check(affiliation.proof)
                    entity = catalog.get(affiliation.entity_id)
                    if entity is None or not _contains(affiliation_source['content'], publication.title):
                        raise ValueError('unknown entity or affiliation source belongs to another work')
                    if not _contains(affiliation.proof.quote, affiliation.author_name) or not _contains(affiliation.proof.quote, affiliation.raw_affiliation):
                        raise ValueError('author and original affiliation must occur together in proof')
                    names = [entity.name, *entity.aliases]
                    if not any(_contains(affiliation.raw_affiliation, name) for name in names):
                        raise ValueError('original affiliation does not match the selected identity')
                    matching_entities = {other.entity_id for other in catalog.values()
                        if any(_contains(affiliation.raw_affiliation, name) for name in [other.name, *other.aliases])}
                    if len(matching_entities) != 1:
                        raise ValueError('ambiguous affiliation identity; keep entities separate')
                    affiliations.append(AffiliationRecord(author_id=affiliation.author_name, entity_id=entity.entity_id,
                        raw_affiliation=affiliation.raw_affiliation, source_urls=(affiliation_source['source_url'],)))
                    evidence_ids.add(affiliation.proof.evidence_id)
                except ValueError as error:
                    pending.append({'kind': 'affiliation', 'output_id': publication.output_id, 'entity_id': affiliation.entity_id, 'reason': str(error)})
            if not affiliations:
                raise ValueError('no source-supported publication affiliations')
            venue = None
            if publication.venue and publication.venue_proof:
                check(publication.venue_proof)
                if _contains(publication.venue_proof.quote, publication.venue):
                    venue = publication.venue
            source_key = _publication_url(source['source_url'])
            key = source_key
            alias_enabled = (configuration.get('corpus') or {}).get('rule_version') in PUBLICATION_ALIAS_VERSIONS
            identity_links = []
            if alias_enabled:
                # Only literal URL tokens before the primary abstract/introduction;
                # never follow a link or infer identity from a similar title.
                linked = {}
                for document, primary_opening in primary_documents.get(source_key, []):
                    if not _contains(primary_opening, publication.title):
                        continue
                    if document['evidence_id'] != publication.title_proof.evidence_id and (
                            not publication.date_proof or not _contains(primary_opening, publication.date_proof.quote)):
                        continue
                    opening_tokens = set(primary_opening.split())
                    for candidate in sources.values():
                        candidate_url = candidate['source_url']
                        publisher = (candidate.get('acquisition') or {}).get('publisher_metadata') or {}
                        if (candidate_url not in opening_tokens or len(candidate_url) > 600
                                or _text(publisher.get('title', '')) != _text(publication.title)
                                or publisher.get('published_on') != lower.isoformat()
                                or publisher.get('published_until') != upper.isoformat()
                                or not publisher.get('literal_fields')):
                            continue
                        linked[_publication_url(candidate_url)] = (candidate, document)
                if len(linked) == 1:
                    linked_key, (candidate, document) = next(iter(linked.items()))
                    try:
                        check(Proof(evidence_id=document['evidence_id'], quote=candidate['source_url']))
                        for field in candidate['acquisition']['publisher_metadata']['literal_fields'].values():
                            check(Proof(evidence_id=candidate['evidence_id'], quote=field['quote']))
                    except ValueError as error:
                        pending.append({'kind': 'publication_alias', 'output_id': publication.output_id,
                            'source_url': source['source_url'], 'publisher_url': candidate['source_url'], 'reason': str(error)})
                    else:
                        key = linked_key
                        evidence_ids.update((document['evidence_id'], candidate['evidence_id']))
                        identity_links.append({'source_evidence_id': document['evidence_id'],
                            'publisher_evidence_id': candidate['evidence_id'], 'publisher_url': candidate['source_url']})
            source_urls = tuple(dict.fromkeys([source['source_url'], *(link['publisher_url'] for link in identity_links)]))
            previous = canonical.get(key)
            if previous:
                if _text(previous.title) != _text(publication.title):
                    raise ValueError('same source page cannot stand for unrelated primary publications')
                if (previous.published_on, previous.published_until) != (lower, upper):
                    raise ValueError('conflicting date bounds for the same publication source')
                if alias_enabled and publication_meta[previous.output_id]['output_type'] != publication.output_type:
                    raise ValueError('conflicting output types for the same publication source')
                if publication.output_id in publications and publications[publication.output_id].output_id != previous.output_id:
                    raise ValueError('conflicting publication IDs')
                merged = list(previous.affiliations)
                for affiliation in affiliations:
                    if affiliation not in merged:
                        merged.append(affiliation)
                if len(merged) > 50:
                    raise ValueError('merged affiliations exceed record limit')
                source_urls = tuple(dict.fromkeys([*(str(url) for url in previous.source_urls), *source_urls]))
                updated = ResearchOutput.model_validate({**previous.model_dump(),
                    'affiliations': tuple(merged), 'source_urls': source_urls})
                outputs[outputs.index(previous)] = updated
                for alias, item in list(publications.items()):
                    if item.output_id == previous.output_id:
                        publications[alias] = updated
                for alias, item in list(canonical.items()):
                    if item.output_id == previous.output_id:
                        canonical[alias] = updated
                canonical[key] = canonical[source_key] = updated
                publications[publication.output_id] = updated
                meta = publication_meta[previous.output_id]
                meta['evidence_ids'] = sorted(set(meta['evidence_ids']) | evidence_ids)
                if venue and not meta.get('venue'):
                    meta['venue'] = venue
                if identity_links:
                    meta['identity_basis'] = 'explicit_primary_cover_link'
                    meta.setdefault('identity_links', []).extend(identity_links)
                continue
            if publication.output_id in publications:
                raise ValueError('conflicting publication IDs')
            output = ResearchOutput(output_id=publication.output_id, title=publication.title,
                published_on=lower, published_until=upper, date_precision=precision,
                source_urls=source_urls, affiliations=tuple(affiliations))
            outputs.append(output)
            publications[publication.output_id] = output
            canonical[key] = canonical[source_key] = output
            publication_meta[output.output_id] = {'output_type': publication.output_type, 'venue': venue,
                'year': lower.year, 'evidence_ids': sorted(evidence_ids),
                'identity_basis': 'explicit_primary_cover_link' if identity_links else 'primary_source_url',
                'canonical_primary_url': key, 'identity_links': identity_links,
                'date_basis': date_basis, 'proposed_publication_date': publication.publication_date}
        except ValueError as error:
            pending.append({'kind': 'publication', 'id': publication.output_id, 'title': publication.title,
                'reason': str(error), 'reason_code': reason_code, 'proposed_record': publication.model_dump(mode='json')})

    families, linked = [], set()
    for family in records('research_families', FamilyClaim, 1000):
        try:
            source = check(family.proof)
            members = {publications[key].output_id for key in family.output_ids if key in publications}
            if len(members) < 2 or any(key not in publications for key in family.output_ids) or linked & members or any(item.family_id == family.family_id for item in families):
                raise ValueError('family members missing, repeated or already linked')
            if not re.search(r'extended version|earlier version|conference version|扩展版|早期版本', family.proof.quote, re.I):
                raise ValueError('no explicit research-version relationship')
            if not all(_contains(family.proof.quote, publications[key].title) for key in family.output_ids):
                raise ValueError('version proof does not identify all member publications')
            families.append(ResearchFamily(family_id=family.family_id, output_ids=tuple(sorted(members)), source_urls=(source['source_url'],)))
            linked.update(members)
        except ValueError as error:
            pending.append({'kind': 'family', 'id': family.family_id, 'reason': str(error)})

    relationships = []
    for parent in records('relationships', ParentClaim, 500):
        try:
            source = check(parent.proof)
            if parent.parent_id not in catalog or parent.child_id not in catalog:
                raise ValueError('unknown parent/child identity')
            if not all(_contains(parent.proof.quote, catalog[key].name) for key in (parent.parent_id, parent.child_id)):
                raise ValueError('part-of proof must identify both organizations')
            if not re.search(r'part of|belongs to|department of|laboratory of|at the|隶属|下属', parent.proof.quote, re.I):
                raise ValueError('an explicit part-of relationship is required')
            for value in (parent.valid_from, parent.valid_to):
                if value and value.isoformat() not in parent.proof.quote.replace('/', '-'):
                    raise ValueError('dated relationship lacks source-backed exact bounds')
            relation = OrganizationRelationship(parent_id=parent.parent_id, child_id=parent.child_id,
                valid_from=parent.valid_from, valid_to=parent.valid_to, source_urls=(source['source_url'],))
            OrganizationScopePreviewRequest(scope=scope, candidate_entities=tuple(candidates), relationships=tuple([*relationships, relation]))
            relationships.append(relation)
        except ValueError as error:
            pending.append({'kind': 'parent_relationship', 'reason': str(error)})

    relations = []
    for output in outputs:
        identities = tuple(sorted({item.entity_id for item in output.affiliations}))
        if len(identities) >= 2:
            relations.append(OutputRelation(output_id=output.output_id, kind='coauthorship', entity_ids=identities, source_urls=output.source_urls))
    for relation in records('output_relations', RelationClaim, 2000):
        try:
            source = check(relation.proof)
            output = publications.get(relation.output_id)
            if not output or any(key not in catalog for key in relation.entity_ids):
                raise ValueError('relationship references unavailable records')
            if not _contains(source['content'], output.title) or not all(_contains(relation.proof.quote, catalog[key].name) for key in relation.entity_ids):
                raise ValueError('relationship source does not identify its work and organizations')
            if relation.kind == 'funding' and not re.search(r'funded|supported by|grant|资助|基金', relation.proof.quote, re.I):
                raise ValueError('coauthorship is not funding evidence')
            relations.append(OutputRelation(output_id=output.output_id, kind=relation.kind,
                entity_ids=relation.entity_ids, source_urls=(source['source_url'],)))
        except ValueError as error:
            pending.append({'kind': 'output_relation', 'reason': str(error)})

    scoped = preview_organization_scope(OrganizationScopePreviewRequest(scope=scope,
        candidate_entities=tuple(candidates), outputs=tuple(outputs), research_families=tuple(families),
        relationships=tuple(relationships), output_relations=tuple(relations)))
    selected_ids = {entity.entity_id for entity in scoped.selected_entities}
    accepted_output_ids = {output.output_id for output in scoped.outputs}
    interpretations = []
    for item in records('interpretations', Interpretation, 200):
        try:
            if not set(item.entity_ids) <= selected_ids:
                raise ValueError('interpretation is outside the selected objects')
            for proof in item.basis:
                check(proof)
            interpretations.append({'entity_ids': list(item.entity_ids), 'statement': item.statement,
                'kind': item.kind, 'evidence_ids': [proof.evidence_id for proof in item.basis],
                'verification_status': 'model_interpretation_requires_review'})
        except ValueError as error:
            pending.append({'kind': 'interpretation', 'reason': str(error)})

    groups = defaultdict(lambda: defaultdict(set))
    member_map = {key: 'family:' + family.family_id for family in families for key in family.output_ids}
    for view in scoped.views:
        for key in view.output_ids:
            meta = publication_meta[key]
            group = (tuple(scope.disciplines), meta['output_type'], meta['year'])
            groups[group][view.entity_id].add(member_map.get(key, 'publication:' + key))
    comparisons = [{'disciplines': list(key[0]), 'discipline_basis': 'requested_scope', 'output_type': key[1],
        'publication_year': key[2], 'measure': 'source_supported_sample_family_count_not_quality',
        'objects': [{'entity_id': entity.entity_id, 'research_family_count': len(objects.get(entity.entity_id, set()))}
                    for entity in scoped.selected_entities], 'ranking': None}
        for key, objects in groups.items()]
    result.update({'schema_version': 'adrs-organization-findings-v1', 'scope_result': scoped.model_dump(mode='json'),
        'publication_metadata': publication_meta, 'comparison_groups': comparisons,
        'publication_id_aliases': {alias: item.output_id for alias, item in publications.items()
            if item.output_id in accepted_output_ids},
        'source_checks': {'status': 'source_quote_and_reference_checked_not_independent_semantic_review',
            'accepted_output_count': len(scoped.outputs), 'proofs': proofs, 'available_evidence_ids': list(sources)},
        'identity_aliases': identity_aliases,
        'pending_records': pending, 'inferences': [item for item in interpretations if item['kind'] == 'inference'],
        'recommendations': [item for item in interpretations if item['kind'] == 'recommendation'],
        'relationship_coverage': {kind: 'source_supported_sample' if scoped.relation_counts[kind] else 'not_established'
                                  for kind in ('coauthorship', 'funding', 'citation')},
        'coverage': 'retrieved_sample_not_real_world_census'})
    result['candidate_discovery_status'] = ('named_entities' if scope.entities
        else 'source_backed_candidates_pending_disambiguation' if candidates else 'no_candidates_established')
    result['attribution_status'] = 'source_supported_sample' if scoped.summary.publication_count else 'no_attributed_sample_established'
    if 'relationships' in configuration.get('modules', []):
        from app.organization_relationships import build_relationship_view
        result['relationship_view'] = build_relationship_view(configuration, result, evidence, proposed)
    if 'deep_dive' in configuration.get('modules', []):
        from app.organization_deep_dive import build_technical_cards
        result['technical_reading'] = build_technical_cards(configuration, result, evidence, proposed)
    if {'evolution','validation'} & set(configuration.get('modules', [])):
        from app.organization_trends import build_trend_view
        result['trend_view'] = build_trend_view(configuration, result, evidence, proposed)
    if 'actions' in configuration.get('modules', []):
        result['action_proposals']={'action_cards':proposed.get('action_cards',[])[:20] if isinstance(proposed.get('action_cards',[]),list) else []}
    return result


def findings_context(result: dict | None) -> str:
    if not result or 'scope_result' not in result:
        return ''
    scoped = result['scope_result']
    from app.organization_relationships import relationship_context
    from app.organization_deep_dive import technical_context
    from app.organization_trends import trend_context
    from app.organization_actions import action_context
    # This context has one consumer: the report writer. Operational adoption
    # errors, raw sample totals and version identities remain in the root record;
    # the writer receives only its separate computed-statistics registry.
    data={
        'outputs': scoped['outputs'][:30], 'recommendations': result['recommendations'],
        'classification': {key: (result.get('classification') or {}).get(key) for key in
            ('taxonomy', 'annual', 'interpretation', 'unobserved_years')},
        'relationship_view': relationship_context(result.get('relationship_view')),
        'technical_reading': technical_context(result.get('technical_reading')),
        'trend_view': trend_context(result.get('trend_view')),
        'actions': action_context(result.get('actions')),
    }
    sections=['\n\n报告分析所用的成果、实验条件与研究依据；样本数值仅使用另行提供的统计注册表。']
    labels={'outputs':'成果与发表署名','technical_reading':'逐项技术条件',
        'relationship_view':'关系依据','trend_view':'演进与交叉验证依据','actions':'行动依据',
        'classification':'学科分类','recommendations':'建议前提'}
    for key,value in data.items():
        if value is None:continue
        sections.append('## '+labels.get(key,key))
        records=[]
        if key=='technical_reading':
            for card in value.get('cards',[]):
                experimental=('experimental_design','baselines','conditions','results')
                measurements={field:statement for field,statement in card.get('fields',{}).items()
                    if field in experimental and statement.get('text')}
                if measurements:
                    records.append({'output_id':card['output_id'],'title':card['title'],
                        'field':'experiment_context_bundle','fields':measurements,
                        'missing_fields':[field for field in experimental if field not in measurements],
                        'interpretation':'retain_result_and_conditions_together_not_cross_paper_ranking'})
                for field,statement in card.get('fields',{}).items():
                    if field not in experimental and statement.get('text'):
                        records.append({'output_id':card['output_id'],'title':card['title'],'field':field,**statement})
        elif isinstance(value,list):records=value
        elif isinstance(value,dict):
            for field,items in value.items():
                if isinstance(items,list):records.extend({'field':field,'record':item} for item in items)
                else:records.append({'field':field,'value':items})
        else:records=[value]
        sections.extend(json.dumps({'record_type':key,'record':record},ensure_ascii=False) for record in records)
    # Separate complete records let the existing paragraph/section packer
    # preserve different questions instead of dropping one giant JSON blob.
    return '\n\n'.join(sections)


def findings_markdown(result: dict | None, evidence: list[dict], *, include_recommendations: bool = True) -> str:
    if not result or 'scope_result' not in result:
        return ''
    scoped = result['scope_result']
    citation = {item['evidence_id']: index for index, item in enumerate(evidence, 1)}
    def safe(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    lines = ['\n\n## 可复核样本与对象比较',
        '计数由结构化记录计算，仅覆盖本次取得并通过原文校验的样本；未链接版本暂按单条发表独立计数。',
        '| 对象 | 发表记录 | 研究家族 |', '| --- | ---: | ---: |']
    for view in scoped['views']:
        lines.append(f"| {safe(view['name'])} | {view['publication_count']} | {view['research_family_count']} |")
    summary = scoped['summary']
    lines += [f"| 去重汇总 | {summary['publication_count']} | {summary['research_family_count']} |",
        '相同成果可分别归属多个对象，合并总量取成果／家族并集，不相加各对象行。',
        '### 同口径样本比较']
    for group in result['comparison_groups'][:30]:
        lines += [f"{safe(group['publication_year'])}／{safe(group['output_type'])}；学科口径来自请求：{safe('、'.join(group['disciplines']))}。仅比较该组已取得样本，不作科研质量排序。",
            '| 对象 | 本组研究家族数 |', '| --- | ---: |']
        names = {view['entity_id']: view['name'] for view in scoped['views']}
        lines += [f"| {safe(names[item['entity_id']])} | {item['research_family_count']} |" for item in group['objects']]
    if not result['comparison_groups']:
        lines.append('未确立可比的有来源成果组。')
    lines.append('### 已纳入成果与依据')
    for output in scoped['outputs'][:50]:
        meta = result['publication_metadata'][output['output_id']]
        refs = ' '.join(f'[citation:{citation[key]}]' for key in meta['evidence_ids'] if key in citation)
        lines.append(f"- {safe(output['title'])}；日期区间 {output['published_on']} 至 {output['published_until']}（{output['date_precision']} 精度）；{refs}")
    if len(scoped['outputs']) > 50 or len(result['comparison_groups']) > 30:
        lines.append('本报告列出前 50 条成果／30 个比较组；完整记录保存在本次结果快照。')
    lines += ['### 缺口与解释边界',
        f"待核记录 {len(result['pending_records'])} 项；未确立的关系：" + '、'.join(kind for kind, status in result['relationship_coverage'].items() if status == 'not_established') + '。未取得证据不表示关系不存在。',
        '机构署名按所选名称／别名与发表来源对照；不推出当前任职、正式协议、内部研发投入或科研质量优劣。跨载体／年份不汇成统一质量榜。']
    lines += [f"- 待核：{safe(item.get('title') or item.get('id') or item['kind'])}：{safe(item['reason'])}" for item in result['pending_records'][:20]]
    if result['recommendations'] and include_recommendations:
        lines.append('### 后续评估建议（模型判断，待复核）')
        for item in result['recommendations'][:20]:
            refs = ' '.join(f'[citation:{citation[key]}]' for key in item['evidence_ids'] if key in citation)
            lines.append(f"- {safe(item['statement'])} {refs}")
    return '\n'.join(lines) + '\n'
