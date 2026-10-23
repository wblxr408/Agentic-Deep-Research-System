"""Versioned evaluation records and exact-identity adapters, without network I/O."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, model_validator

from app.research_scope import Identifier, Label, ScopeRecord

SchemeId = Literal[
    "ccf", "icore", "wos_scie", "wos_ssci", "wos_ahci", "wos_esci", "scopus",
    "jcr_jif", "jcr_quartile", "jcr_jci", "cas_partition", "citescore",
    "citescore_percentile", "sjr", "snip", "abdc", "ajg", "citation_percentile", "cnci", "fwci",
]
OutputType = Literal["journal_article", "conference_paper", "preprint", "book", "software", "dataset"]
PAPER_METRICS = {"citation_percentile", "cnci", "fwci"}
INDEXES = {"wos_scie", "wos_ssci", "wos_ahci", "wos_esci", "scopus"}
RANKS = {
    "ccf": ("A", "B", "C"), "icore": ("A*", "A", "B", "C", "Australasian B", "Australasian C", "Unranked"),
    "abdc": ("A*", "A", "B", "C"), "ajg": ("4*", "4", "3", "2", "1"),
    "jcr_quartile": ("Q1", "Q2", "Q3", "Q4"), "cas_partition": ("1", "2", "3", "4"),
}
SOURCES = {
    "ccf": "https://www.ccf.org.cn/Academic_Evaluation/By_category/",
    "icore": "https://portal.core.edu.au/conf-ranks/",
    "wos": "https://mjl.clarivate.com/", "jcr": "https://jcr.clarivate.com/",
    "scopus": "https://www.scopus.com/sources", "cas": "https://www.fenqubiao.com/",
    "sjr": "https://www.scimagojr.com/", "abdc": "https://abdc.edu.au/abdc-journal-quality-list/",
    "ajg": "https://charteredabs.org/academic-journal-guide",
    "openalex": "https://help.openalex.org/data/works/citations/",
    "cnci": "https://incites.help.clarivate.com/Content/Indicators-Handbook/ih-normalized-citation-impact.htm",
}


class EvaluationScheme(ScopeRecord):
    scheme_id: SchemeId
    family: Literal["index", "directory", "journal_metric", "paper_metric"]
    level: Literal["venue", "work"]
    source_url: AnyHttpUrl
    adapter: Literal["exact_catalogue", "authorized_metric", "paper_metric"]
    access_note: str
    editions: tuple[str, ...] = ()
    availability: Literal["public_sample", "import_only"] = "import_only"


def scheme_catalogue() -> tuple[EvaluationScheme, ...]:
    result = []
    for key in SchemeId.__args__:
        source = ("wos" if key.startswith("wos_") else "jcr" if key.startswith("jcr_")
                  else "cas" if key == "cas_partition" else "scopus" if key in
                  {"scopus", "citescore", "citescore_percentile", "snip"} else
                  "openalex" if key in {"fwci", "citation_percentile"} else key)
        family = ("index" if key in INDEXES else "directory" if key in {"ccf", "icore", "abdc", "ajg"}
                  else "paper_metric" if key in PAPER_METRICS else "journal_metric")
        result.append(EvaluationScheme(
            scheme_id=key, family=family, level="work" if key in PAPER_METRICS else "venue",
            source_url=SOURCES[source],
            adapter="paper_metric" if key in PAPER_METRICS else "exact_catalogue" if family == "directory" else "authorized_metric",
            access_note="Public snapshots are partial; authorized imports retain caller provenance. No live queries in preview.",
        ))
    return tuple(result)


class EvaluationDatum(ScopeRecord):
    target_id: Identifier
    track: Literal["main", "workshop", "journal", "work"]
    category: Label
    raw_value: str | float | bool | None
    status: Literal["available", "not_indexed", "data_missing"] = "available"
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    document_type: Label | None = None
    citation_cutoff: date | None = None


class EvaluationSource(ScopeRecord):
    source_id: Identifier
    scheme_id: SchemeId
    edition: Label
    metric_year: int = Field(ge=1800, le=2200)
    provider: Label
    source_url: AnyHttpUrl
    retrieved_on: date
    access: Literal["public", "authorized_import"]
    authorized: bool = False
    coverage: Literal["partial", "complete"] = "partial"
    provider_updated_at: Label | None = None
    records: tuple[EvaluationDatum, ...] = Field(default=(), max_length=10000)

    @model_validator(mode="after")
    def validate_source(self):
        if self.access == "authorized_import" and not self.authorized:
            raise ValueError("authorized_import requires an explicit authorization declaration")
        for record in self.records:
            if record.status != "available":
                if record.raw_value is not None:
                    raise ValueError("missing/not-indexed records must not contain a metric value")
                continue
            value = record.raw_value
            if self.scheme_id in RANKS:
                if not isinstance(value, str) or value not in RANKS[self.scheme_id]:
                    raise ValueError(f"invalid grade for {self.scheme_id}")
            elif self.scheme_id in INDEXES:
                if not isinstance(value, bool):
                    raise ValueError("index records require a boolean raw_value")
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("numeric metrics must be finite non-negative numbers")
            if self.scheme_id == "citation_percentile" and value > 1:
                raise ValueError("citation_percentile uses a 0–1 scale; preserve provider context")
            if self.scheme_id == "citescore_percentile" and value > 100:
                raise ValueError("CiteScore percentile uses a 0–100 scale")
            if self.scheme_id in PAPER_METRICS:
                if not record.publication_year or not record.document_type or not record.citation_cutoff:
                    raise ValueError("paper metrics require publication_year, document_type and citation_cutoff")
                if record.citation_cutoff > self.retrieved_on:
                    raise ValueError("citation cutoff cannot be after retrieval")
                if self.scheme_id == "cnci" and self.provider != "Clarivate InCites":
                    raise ValueError("CNCI requires Clarivate InCites provenance; do not relabel an approximation")
                if self.scheme_id == "fwci" and self.provider not in {"OpenAlex", "Elsevier SciVal"}:
                    raise ValueError("FWCI requires its named provider; OpenAlex and SciVal remain distinct")
        return self


class EvaluationContext(ScopeRecord):
    disciplines: tuple[Label, ...] = Field(min_length=1, max_length=20)
    output_type: OutputType


class EvaluationRequest(EvaluationContext):
    target_id: Identifier
    work_id: Identifier | None = None
    publication_year: int = Field(ge=1800, le=2200)
    metric_year: int = Field(ge=1800, le=2200)
    track: Literal["main", "workshop"] = "main"
    editions: dict[SchemeId, Label] = Field(default_factory=dict, max_length=20)
    sources: tuple[EvaluationSource, ...] = Field(default=(), max_length=100)
    use_public_snapshots: bool = True

    @model_validator(mode="after")
    def unique_sources(self):
        keys = [source.source_id for source in self.sources]
        if len(keys) != len(set(keys)):
            raise ValueError("source_id must be unique")
        return self


class EvaluationRecord(EvaluationDatum):
    scheme_id: SchemeId
    edition: str
    metric_year: int
    provider: str
    source_id: str
    source_url: AnyHttpUrl
    retrieved_on: date
    provider_updated_at: str | None = None
    match_basis: Literal["exact_identifier_and_track"] = "exact_identifier_and_track"
    evidence_status: Literal["caller_provided", "public_source_snapshot"]


class EvaluationResult(ScopeRecord):
    scheme_id: SchemeId
    applicable: bool
    availability: Literal["available", "not_indexed", "not_applicable", "data_missing", "source_unavailable", "conflict"]
    reason: str
    records: tuple[EvaluationRecord, ...] = ()


class EvaluationPreview(ScopeRecord):
    schema_version: Literal["1"] = "1"
    request: EvaluationRequest
    evaluations: tuple[EvaluationResult, ...]
    source_status: tuple[dict, ...]
    external_sources_checked: Literal[False] = False


def public_sources() -> tuple[EvaluationSource, ...]:
    path = Path(__file__).resolve().parents[1] / "config/evaluation/public-snapshots.json"
    # A checked-in release resource, not a caller-controlled filesystem path.
    return tuple(EvaluationSource.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8")))


def applicability(scheme: str, request: EvaluationContext) -> tuple[bool, str]:
    disciplines = {item.casefold().replace('_', ' ').strip() for item in request.disciplines}
    computing = bool(disciplines & {"computing", "computer science", "计算机", "计算机科学"})
    business = bool(disciplines & {"business", "economics", "management", "商科", "经济学", "管理学"})
    if scheme in {"ccf", "icore"} and not computing:
        return False, "Computing catalogue does not automatically apply to this discipline"
    if scheme in {"abdc", "ajg"} and not business:
        return False, "Business catalogue applicability requires a business-related discipline"
    if scheme in PAPER_METRICS:
        return request.output_type in {"journal_article", "conference_paper", "preprint"}, "Paper-level provider context required"
    if scheme == "icore":
        return request.output_type == "conference_paper", "ICORE is a conference catalogue"
    if scheme == "ccf":
        return request.output_type in {"journal_article", "conference_paper"}, "Exact venue and track required"
    if scheme == "scopus":
        return request.output_type in {"journal_article", "conference_paper", "book"}, "Source coverage must be evidenced"
    return request.output_type == "journal_article", "Journal-level metric/index; not a conference-paper grade"


def preview_evaluation(request: EvaluationRequest) -> EvaluationPreview:
    builtins = public_sources() if request.use_public_snapshots else ()
    sources = (*builtins, *request.sources)
    results = []
    for scheme in scheme_catalogue():
        key = scheme.scheme_id
        applicable, reason = applicability(key, request)
        if not applicable:
            results.append(EvaluationResult(scheme_id=key, applicable=False, availability="not_applicable", reason=reason))
            continue
        candidates = [item for item in sources if item.scheme_id == key]
        selected = [item for item in candidates if item.metric_year == request.metric_year and
                    (key not in request.editions or item.edition == request.editions[key])]
        target = (request.work_id or request.target_id) if key in PAPER_METRICS else request.target_id
        track = "work" if key in PAPER_METRICS else "journal" if request.output_type == "journal_article" else request.track
        records = tuple(EvaluationRecord(
            **record.model_dump(), scheme_id=key, edition=source.edition, metric_year=source.metric_year,
            provider=source.provider, source_id=source.source_id, source_url=source.source_url,
            retrieved_on=source.retrieved_on,
            provider_updated_at=source.provider_updated_at,
            evidence_status="public_source_snapshot" if source in builtins else "caller_provided",
        ) for source in selected for record in source.records if record.target_id == target and record.track == track)
        by_context: dict[tuple, set] = {}
        for record in records:
            # Provider, edition and cutoff identify separate measurements, not interchangeable numbers.
            context = (record.provider, record.category, record.edition, record.citation_cutoff)
            by_context.setdefault(context, set()).add((record.status, record.raw_value))
        if any(len(values) > 1 for values in by_context.values()):
            state, reason = "conflict", "Conflicting records in the same provider/category/edition context"
        elif any(item.status == "available" for item in records):
            state, reason = "available", "All matching categories retained; no highest-grade selection"
        elif records and all(item.status == "not_indexed" for item in records):
            state, reason = "not_indexed", "Explicit source-backed non-inclusion records"
        elif any(item.coverage == "complete" for item in selected) and not records:
            state, reason = "not_indexed", "Exact identity absent in the declared complete edition"
        elif candidates:
            state, reason = "data_missing", "Requested identity, track, category or historical edition not available"
        else:
            state, reason = "source_unavailable", "No source data connected; import authorized provider records"
        results.append(EvaluationResult(scheme_id=key, applicable=True, availability=state, reason=reason, records=records))
    status = tuple({"scheme_id": scheme.scheme_id,
                    "access": "public_sample" if any(s.scheme_id == scheme.scheme_id for s in builtins) else "import_only",
                    "editions": sorted({s.edition for s in sources if s.scheme_id == scheme.scheme_id}),
                    "source_url": str(scheme.source_url),
                    "coverage": "partial_or_caller_declared", "live_fetch": False}
                   for scheme in scheme_catalogue())
    return EvaluationPreview(request=request, evaluations=tuple(results), source_status=status)


class OpenAlexSubfield(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: AnyHttpUrl
    display_name: Label


class OpenAlexTopic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subfield: OpenAlexSubfield


class OpenAlexPercentile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: FiniteFloat | None = Field(default=None, ge=0, le=1)


class OpenAlexWork(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: Annotated[str, StringConstraints(pattern=r"^https://openalex\.org/W[0-9]+$")]
    publication_year: int = Field(ge=1800, le=2200)
    type: Label
    primary_topic: OpenAlexTopic
    updated_date: Label | None = None
    fwci: FiniteFloat | None = Field(default=None, ge=0)
    citation_normalized_percentile: OpenAlexPercentile | None = None


class OpenAlexNormalizationRequest(ScopeRecord):
    work: OpenAlexWork
    retrieved_on: date
    citation_cutoff: date

    @model_validator(mode="after")
    def valid_cutoff(self):
        if self.citation_cutoff > self.retrieved_on or self.citation_cutoff.year < self.work.publication_year:
            raise ValueError("citation cutoff must be between publication and retrieval")
        return self


class OpenAlexNormalization(ScopeRecord):
    sources: tuple[EvaluationSource, ...]
    provenance: Literal["caller_provided_openalex_payload"] = "caller_provided_openalex_payload"
    external_sources_checked: Literal[False] = False


def normalize_openalex(request: OpenAlexNormalizationRequest) -> OpenAlexNormalization:
    work = request.work
    key = work.id.rsplit("/", 1)[1]
    values = {"fwci": work.fwci, "citation_percentile": (
        work.citation_normalized_percentile.value if work.citation_normalized_percentile else None)}
    sources = tuple(EvaluationSource(
        source_id=f"openalex-{key}-{scheme}-{request.retrieved_on}", scheme_id=scheme,
        edition=f"OpenAlex snapshot {request.retrieved_on}", metric_year=request.retrieved_on.year,
        provider="OpenAlex", source_url=f"https://api.openalex.org/works/{key}",
        retrieved_on=request.retrieved_on, access="public", coverage="partial",
        provider_updated_at=work.updated_date,
        records=(EvaluationDatum(target_id=f"openalex:{key}", track="work",
            category=f"{work.primary_topic.subfield.id} | {work.primary_topic.subfield.display_name}",
            raw_value=value, status="available" if value is not None else "data_missing",
            publication_year=work.publication_year, document_type=work.type, citation_cutoff=request.citation_cutoff),),
    ) for scheme, value in values.items())
    return OpenAlexNormalization(sources=sources)
