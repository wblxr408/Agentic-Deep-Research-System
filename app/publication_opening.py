"""Bounded printed-title and numbered-author readings of one primary opening.

Only explicit characters in this opening may supply values. These readings do
not establish affiliation semantics, source permission, scope or entailment.
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from urllib.parse import urlsplit

from app.publication_literals import literal_pattern


def printed_title(opening, proposed):
    """Keep a unique complete title across at most four printed lines."""
    if not isinstance(proposed,str) or not 3<=len(proposed)<=300:return None
    expected=re.sub(r'\s','',proposed).casefold()
    lines=list(re.finditer(r'[^\r\n]+',opening[:6000]))
    candidates=[]
    for index,line in enumerate(lines):
        for last in lines[index:index+4]:
            quote=opening[line.start():last.end()].strip()
            if len(quote)>300:break
            if re.sub(r'\s','',quote).casefold()==expected:
                candidates.append(quote)
    return candidates[0] if len(candidates)==1 else None


def current_arxiv_date(source, opening):
    """A PDF's explicit current version stamp, never its first release date."""
    acquisition=source.get('acquisition') or {}
    if acquisition.get('format')!='pdf' or acquisition.get('coverage')!='full_text':return None
    # A printed version and this acquired arXiv locator must agree. Do not use
    # a requested URL, a bibliography link or another retained representation.
    path=urlsplit(source.get('source_url','')).path
    locator=re.fullmatch(r'/(?:pdf|abs|html)/(\d{4}\.\d{4,5})(v\d+)?(?:\.pdf)?/?',path,re.I)
    if not locator or (urlsplit(source['source_url']).hostname or '').lower() not in {'arxiv.org','export.arxiv.org'}:return None
    stamps=list(re.finditer(r'(?im)^\s*arxiv:\s*(\d{4}\.\d{4,5})(v\d+)\s*\[[^\]\r\n]{1,40}\]\s*'
        r'(\d{1,2})[ \t]+([A-Za-z]{3,9})[ \t]+(\d{4})\s*$',opening[:6000]))
    if len(stamps)!=1:return None
    stamp=stamps[0]
    if stamp[1]!=locator[1] or locator[2] and stamp[2].lower()!=locator[2].lower():return None
    months={name.casefold():index for index in range(1,13)
        for name in (calendar.month_abbr[index],calendar.month_name[index])}
    try:value=date(int(stamp[5]),months[stamp[4].casefold()],int(stamp[3])).isoformat()
    except (ValueError,KeyError):return None
    return {'publication_date':value,'quote':stamp[0].strip(),
        'arxiv_id':stamp[1],'version':stamp[2],'basis':'literal_preprint_version_date_not_first_release'}


def numbered_affiliation(opening,title,author,affiliation):
    """Return a continuous author→institution quote for unambiguous labels.

    A numbered layout that mentions the proposed author/address but disagrees
    returns invalid, preventing the legacy co-occurrence path from accepting it.
    Unsupported layouts remain unknown; no author or institution is generated.
    """
    if not all(isinstance(value,str) and value.strip() for value in (opening,title,author,affiliation)):return None
    if not re.search(literal_pattern(title),opening,re.I):return None
    author=re.sub(r'[ \t]*[0-9*∗†‡]+$','',author).rstrip()
    if not author:return None
    authors=list(re.finditer(r'(?<!\w)'+literal_pattern(author)+r'(?![^\W\d_])',opening,re.I))
    addresses=list(re.finditer(literal_pattern(affiliation),opening,re.I))
    # Institution declarations begin at a line or follow a completed declared
    # institution on the same line; the latter is bounded below by its label.
    declarations=list(re.finditer(r'(?m)(?:^[ \t]*|(?<=[ \t]))(\d{1,2})[ \t]*(?=[A-Z\u3400-\u9fff])',opening))
    if not declarations:
        numeric_hint=len(authors)==1 and re.match(r'[ \t]*[*∗†‡]*[ \t]*[0-9¹²³⁴⁵⁶⁷⁸⁹⁰]',opening[authors[0].end():])
        if numeric_hint:return {'status':'invalid','reason':'numbered_institution_format_unsupported'}
        return None
    if len(authors)!=1 or len(addresses)!=1:return {'status':'invalid','reason':'author_or_address_not_unique'}
    person,address=authors[0],addresses[0]
    marker=re.match(r'[ \t]*[*∗†‡]*[ \t]*(\d{1,4}(?:[ \t]*,[ \t]*\d{1,2})*)[*∗†‡]*',opening[person.end():])
    line_start=opening.rfind('\n',0,address.start())+1
    declared_address=any(line_start<=item.start(1)<item.end(1)<=address.start() for item in declarations)
    if not marker and not declared_address:return None
    declarations=[item for item in declarations if item.start(1)>person.end()]
    first=declarations[0].start(1) if declarations else None
    if not declarations or len(declarations)>12:return {'status':'invalid','reason':'institution_labels_ambiguous'}
    labels=[item[1] for item in declarations]
    if len(set(labels))!=len(labels):return {'status':'invalid','reason':'institution_labels_not_unique'}
    if not marker or person.end()>=first:return {'status':'invalid','reason':'author_numeric_marker_unavailable'}
    # Parse fused labels only when exactly one segmentation is possible.
    def splits(text):
        if not text:return [()]
        paths=[]
        for label in labels:
            if text.startswith(label):
                for tail in splits(text[len(label):]):
                    path=(label,*tail)
                    if len(set(path))==len(path):paths.append(path)
                    if len(paths)>1:return paths
        return paths
    decoded=[]
    for token in re.split(r'[ \t]*,[ \t]*',marker[1]):
        paths=splits(token)
        if len(paths)!=1:return {'status':'invalid','reason':'author_marker_ambiguous'}
        decoded.extend(paths[0])
    matches=[]
    for index,item in enumerate(declarations):
        end=declarations[index+1].start(1) if index+1<len(declarations) else len(opening)
        if item.end(1)<=address.start()<address.end()<=end:matches.append(item[1])
    if len(matches)!=1 or matches[0] not in decoded:return {'status':'invalid','reason':'author_institution_marker_mismatch'}
    quote=opening[person.start():address.end()]
    if len(quote)>1600:return {'status':'invalid','reason':'numbered_affiliation_span_exceeds_bound'}
    return {'status':'resolved','quote':quote,'author_name':person.group(),
        'author_labels':decoded,'institution_label':matches[0]}


def auxiliary_identity_source(source):
    """An explicitly labelled CV/profile is a lead, not a primary work list."""
    title=source.get('source_title') or ''
    text=(source.get('content') or '')[:1800]
    path=urlsplit(source.get('source_url') or '').path
    return bool(re.search(r'(?:^|/)(?:cv|resume|curriculum[-_ ]vitae)(?:[./_-]|$)',path,re.I)
        or re.search(r'(?im)^\s*(?:curriculum vitae|résumé|resume|个人简历|学术简历)\s*$',text)
        or re.search(r'\b(?:curriculum vitae|résumé)\b',title,re.I))
