"""Retain literal balanced publisher BibTeX entries without panel wrappers."""
import re


def bibtex_entries(text: str):
    for match in re.finditer(r'@(inproceedings|article|book|misc)\s*\{', text, re.I):
        depth, end = 1, match.end()
        while end < len(text) and depth:
            if text[end] == '{' and text[end - 1] != '\\':
                depth += 1
            elif text[end] == '}' and text[end - 1] != '\\':
                depth -= 1
            end += 1
        if not depth:
            yield text[match.start():end]
