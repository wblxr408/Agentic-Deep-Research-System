"""Bounded repairs of explicit primary-source author fields, never new people."""
from __future__ import annotations

import re

from app.publication_literals import literal_pattern


def direct_cover_pair(opening,title,author,affiliation):
    """Only an explicit literal 'Author, Institution' on this work's opening."""
    if not all(isinstance(value,str) and value.strip() for value in (opening,title,author,affiliation)):return None
    if not re.search(literal_pattern(title),opening,re.I):return None
    if re.search(r'[,，;；\n]',author):return None
    pattern=r'(?<!\w)'+literal_pattern(author)+r'\s*,\s*'+literal_pattern(affiliation)+r'(?!\w)'
    matches=list(re.finditer(pattern,opening,re.I))[:2]
    if len(matches)!=1 or len(matches[0].group())>1600:return None
    return matches[0].group()


def shared_author_names(quote,title,author,affiliation):
    """Expand only an explicit complete >=3-name list with one common address.

    Every name is already supplied. All words in the current literal proof must
    be explained by that title, the ordered names and that single institution.
    No other author, address or narrative is silently removed or inferred.
    """
    if not all(isinstance(value,str) and value.strip() for value in (quote,title,author,affiliation)):return None
    if re.search(literal_pattern(author),quote,re.I):return None
    names=re.split(r'\s*[,，]\s*',author.strip())
    if not 3<=len(names)<=12 or len({name.casefold() for name in names})!=len(names):return None
    if any(not 2<=len(name.split())<=5 or re.search(r'[;；\n0-9]',name) for name in names):return None
    # A bare author-only source proof is permitted; a declared title, when
    # present, must be a single literal prefix, not a cut-and-paste assembly.
    residue=quote
    title_match=re.match(r'^\s*'+literal_pattern(title),residue,re.I)
    if title_match:residue=residue[title_match.end():]
    cursor=0;spans=[]
    for name in names:
        matches=list(re.finditer(r'(?<!\w)'+literal_pattern(name)+r'(?!\w)',residue,re.I))[:2]
        if len(matches)!=1 or matches[0].start()<cursor:return None
        spans.append((matches[0].start(),matches[0].end()));cursor=matches[0].end()
    institutions=list(re.finditer(literal_pattern(affiliation),residue,re.I))[:2]
    if len(institutions)!=1 or institutions[0].start()<cursor:return None
    spans.append((institutions[0].start(),institutions[0].end()))
    for start,end in reversed(spans):residue=residue[:start]+residue[end:]
    # Only typography remains. In particular, words from a second institution
    # or an omitted author make the grouped proposal ineligible for repair.
    if re.sub(r'[\s,，;；*∗†‡¹²³⁴⁵⁶⁷⁸⁹⁰]','',residue):return None
    return names
