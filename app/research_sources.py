"""User-selected academic discovery and primary-source boundaries for local research."""
from __future__ import annotations

import ipaddress
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.channels.execution import public_url
from app.channels.models import ChannelError


CATALOG_VERSION = "2026-10-18.1"
# A visible starter catalog, not a claim of complete publisher coverage.
PUBLISHERS = (
    "dl.acm.org", "ieeexplore.ieee.org", "link.springer.com", "nature.com",
    "science.org", "sciencedirect.com", "onlinelibrary.wiley.com",
    "proceedings.mlr.press", "papers.nips.cc", "proceedings.neurips.cc",
    "ojs.aaai.org", "usenix.org", "openaccess.thecvf.com", "aclanthology.org",
    "openreview.net",
)
FIXED_DOMAINS = {"dblp": ("dblp.org", "dblp.uni-trier.de"),
                 "arxiv": ("arxiv.org",),
                 "google_scholar": ("scholar.google.com", "scholar.google.com.hk")}
USES = {"publishers": "paper_or_proceedings", "dblp": "bibliographic_metadata",
        "arxiv": "preprint_check_version_and_review_status", "google_scholar": "discovery_only",
        "official": "official_document_check_entity_and_claim"}
SourceGroup = Literal["publishers", "dblp", "arxiv", "google_scholar", "official"]


def _domain(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValueError("invalid domain") from None
    labels = value.split(".")
    # Common suffixes are rejected; this is not a public-suffix-list service.
    if (len(value) > 253 or len(labels) < 2 or value in {
        "co.uk", "ac.uk", "gov.uk", "com.cn", "edu.cn", "gov.cn", "org.cn",
        "com.au", "edu.au", "co.jp", "ac.jp", "co.in", "ac.in", "com.hk", "edu.hk",
    } or not labels[-1].isalpha() or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)):
        raise ValueError("use a specific domain, not a URL, wildcard or public suffix")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValueError("an organization domain is required")
    try:
        public_url("https://" + value)
    except ChannelError:
        raise ValueError("a public organization domain is required") from None
    return value


class ResearchSourceScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    groups: tuple[SourceGroup, ...] = Field(
        default=("publishers", "dblp", "arxiv", "google_scholar"), min_length=1, max_length=5)
    official_domains: tuple[str, ...] = Field(default=(), max_length=16)
    publisher_domains: tuple[str, ...] = Field(default=PUBLISHERS, min_length=1, max_length=32)

    @field_validator("official_domains", "publisher_domains")
    @classmethod
    def domains(cls, values):
        return tuple(dict.fromkeys(_domain(value) for value in values))

    @model_validator(mode="after")
    def selection(self):
        if len(set(self.groups)) != len(self.groups):
            raise ValueError("source groups must be unique")
        if "official" in self.groups and not self.official_domains:
            raise ValueError("official sources require explicit official_domains")
        if self.official_domains and "official" not in self.groups:
            raise ValueError("select official before configuring official_domains")
        return self

    def domains_by_group(self) -> dict[str, tuple[str, ...]]:
        domains = {**FIXED_DOMAINS, "publishers": self.publisher_domains,
                   "official": self.official_domains}
        return {group: domains[group] for group in self.groups}

    @staticmethod
    def _matches(host: str, domains) -> bool:
        return any(host == domain or host.endswith("." + domain) for domain in domains)

    def group_for(self, url: str) -> str:
        host, _ = public_url(url)
        # Known index/preprint hosts cannot be promoted to primary evidence by
        # adding their host to a custom publisher or official-domain entry.
        for group, domains in FIXED_DOMAINS.items():
            if self._matches(host, domains):
                if group in self.groups:
                    return group
                raise ChannelError("source_out_of_scope")
        for group, domains in self.domains_by_group().items():
            if self._matches(host, domains):
                return group
        raise ChannelError("source_out_of_scope")

    def admit(self, url: str, *, for_read: bool = True) -> str:
        group = self.group_for(url)
        if for_read and group == "google_scholar":
            raise ChannelError("discovery_only")
        return group

    def search_query(self, query: str) -> str:
        domains = dict.fromkeys(domain for values in self.domains_by_group().values() for domain in values)
        return query + " (" + " OR ".join("site:" + domain for domain in domains) + ")"

    def filter_leads(self, items) -> tuple[list[dict], list[dict]]:
        leads, rejected = [], []
        for item in items:
            try:
                group = self.admit(item.url, for_read=False)
            except ChannelError as exc:
                rejected.append({"url": item.url, "reason": exc.category})
                continue
            leads.append({"url": item.url, "title": item.title, "snippet": item.snippet[:1200],
                          "source_group": group, "source_use": USES[group]})
        return leads, rejected

    def snapshot(self) -> dict:
        return {"catalog_version": CATALOG_VERSION, "groups": list(self.groups),
                "domains_by_group": self.domains_by_group(), "source_uses": {g: USES[g] for g in self.groups}}
