"""Bounded organization scope and attributed output views; no I/O or model calls."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import date
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, StringConstraints, model_validator

OrganizationType = Literal["university", "laboratory", "company"]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Sources = Annotated[tuple[AnyHttpUrl, ...], Field(min_length=1, max_length=20)]


class ScopeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OrganizationEntity(ScopeRecord):
    entity_id: Identifier
    name: Label
    type: OrganizationType
    unit_kind: Literal["organization", "department"] = "organization"
    aliases: tuple[Label, ...] = Field(default=(), max_length=30)
    source_urls: Sources
    resolution_status: Literal["pending", "confirmed"] = "pending"

    @model_validator(mode="after")
    def validate_unit(self):
        if self.unit_kind == "department" and self.type != "university":
            raise ValueError("department units must belong to the university type")
        return self


class OrganizationResearchScope(ScopeRecord):
    organization_types: tuple[OrganizationType, ...] = Field(
        default=("university", "laboratory", "company"), min_length=1, max_length=3
    )
    entities: tuple[OrganizationEntity, ...] = Field(default=(), max_length=200)
    disciplines: tuple[Label, ...] = Field(min_length=1, max_length=20)
    topic: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_scope(self):
        if len(set(self.organization_types)) != len(self.organization_types):
            raise ValueError("organization_types must be unique")
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        ids = [entity.entity_id for entity in self.entities]
        if len(set(ids)) != len(ids):
            raise ValueError("selected entity_id values must be unique")
        if any(entity.type not in self.organization_types for entity in self.entities):
            raise ValueError("selected entity type is outside organization_types")
        return self


class OrganizationRelationship(ScopeRecord):
    parent_id: Identifier
    child_id: Identifier
    relation_type: Literal["part_of"] = "part_of"
    source_urls: Sources
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.parent_id == self.child_id:
            raise ValueError("an organization cannot be its own parent")
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("relationship valid_from must not be after valid_to")
        return self

    def applies_at(self, when: date) -> bool:
        # No dated beginning means historical applicability is not established.
        return self.valid_from is not None and self.valid_from <= when and (
            self.valid_to is None or when <= self.valid_to
        )


class AffiliationRecord(ScopeRecord):
    author_id: Identifier
    entity_id: Identifier
    raw_affiliation: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    source_urls: Sources

    @model_validator(mode="after")
    def validate_raw_affiliation(self):
        if not self.raw_affiliation.strip():
            raise ValueError("raw_affiliation must not be blank")
        return self


class ResearchOutput(ScopeRecord):
    output_id: Identifier
    title: Label
    published_on: date
    published_until: date | None = None
    date_precision: Literal['day', 'month', 'year'] = 'day'
    source_urls: Sources
    affiliations: tuple[AffiliationRecord, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def valid_date_bounds(self):
        if self.published_until and self.published_until < self.published_on:
            raise ValueError('publication date bounds are reversed')
        return self


class ResearchFamily(ScopeRecord):
    family_id: Identifier
    output_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=1000)
    source_urls: Sources

    @model_validator(mode="after")
    def unique_members(self):
        if len(set(self.output_ids)) != len(self.output_ids):
            raise ValueError("family output_ids must be unique")
        return self


class OutputRelation(ScopeRecord):
    output_id: Identifier
    kind: Literal["coauthorship", "funding", "citation"]
    entity_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=200)
    source_urls: Sources

    @model_validator(mode="after")
    def unique_entities(self):
        if len(set(self.entity_ids)) != len(self.entity_ids):
            raise ValueError("relation entity_ids must be unique")
        if self.kind == "coauthorship" and len(self.entity_ids) < 2:
            raise ValueError("organization coauthorship requires at least two entities")
        return self


class OrganizationScopePreviewRequest(ScopeRecord):
    scope: OrganizationResearchScope
    candidate_entities: tuple[OrganizationEntity, ...] = Field(default=(), max_length=200)
    relationships: tuple[OrganizationRelationship, ...] = Field(default=(), max_length=500)
    outputs: tuple[ResearchOutput, ...] = Field(default=(), max_length=1000)
    current_affiliations: tuple[AffiliationRecord, ...] = Field(default=(), max_length=1000)
    research_families: tuple[ResearchFamily, ...] = Field(default=(), max_length=1000)
    output_relations: tuple[OutputRelation, ...] = Field(default=(), max_length=2000)

    @model_validator(mode="after")
    def validate_references(self):
        entities: dict[str, OrganizationEntity] = {}
        for entity in (*self.scope.entities, *self.candidate_entities):
            previous = entities.get(entity.entity_id)
            if previous is not None and previous != entity:
                raise ValueError(f"conflicting records for entity_id: {entity.entity_id}")
            entities[entity.entity_id] = entity
        output_ids = [output.output_id for output in self.outputs]
        if len(set(output_ids)) != len(output_ids):
            raise ValueError("output_id values must be unique")
        family_ids: set[str] = set()
        linked: set[str] = set()
        for family in self.research_families:
            if family.family_id in family_ids:
                raise ValueError("family_id values must be unique")
            family_ids.add(family.family_id)
            for key in family.output_ids:
                if key not in output_ids:
                    raise ValueError(f"unknown family output_id: {key}")
                if key in linked:
                    raise ValueError("a publication cannot belong to multiple research families")
                linked.add(key)
        for relation in self.output_relations:
            if relation.output_id not in output_ids:
                raise ValueError("relation must reference a provided output")
            if any(key not in entities for key in relation.entity_ids):
                raise ValueError("relation must reference provided entities")
        for affiliation in (*self.current_affiliations,
                            *(item for output in self.outputs for item in output.affiliations)):
            if affiliation.entity_id not in entities:
                raise ValueError(f"unknown affiliation entity_id: {affiliation.entity_id}")

        children: dict[str, set[str]] = defaultdict(set)
        indegree = dict.fromkeys(entities, 0)
        for relationship in self.relationships:
            if relationship.parent_id not in entities or relationship.child_id not in entities:
                raise ValueError("relationship endpoints must reference provided entities")
            if relationship.child_id not in children[relationship.parent_id]:
                children[relationship.parent_id].add(relationship.child_id)
                indegree[relationship.child_id] += 1
        queue = deque(key for key, count in indegree.items() if count == 0)
        visited = 0
        while queue:
            parent = queue.popleft()
            visited += 1
            for child in children[parent]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if visited != len(entities):
            raise ValueError("organization parent relationships must not contain cycles")
        return self


class OrganizationDiscoveryQuery(ScopeRecord):
    organization_types: tuple[OrganizationType, ...]
    disciplines: tuple[Label, ...]
    topic: str
    start_date: date
    end_date: date


class PublicationCounts(ScopeRecord):
    publication_count: int
    research_family_ids: tuple[str, ...]
    research_family_count: int
    unlinked_publication_count: int
    counting_method: Literal["full"] = "full"


class OrganizationOutputView(PublicationCounts):
    entity_id: str
    name: str
    type: OrganizationType
    output_ids: tuple[str, ...]
    direct_output_ids: tuple[str, ...]
    inherited_output_ids: tuple[str, ...]
    output_count: int


class OutputSummary(PublicationCounts):
    output_ids: tuple[str, ...]
    output_count: int


class ExcludedCandidate(ScopeRecord):
    entity_id: str
    reason: Literal["type_out_of_scope", "not_selected"]


class PreviewVerification(ScopeRecord):
    source_status: Literal["provided_records_only"] = "provided_records_only"
    external_sources_checked: Literal[False] = False


class OrganizationScopePreview(ScopeRecord):
    schema_version: Literal["2"] = "2"
    scope: OrganizationResearchScope
    selection_mode: Literal["named_entities", "candidate_discovery"]
    discovery_query: OrganizationDiscoveryQuery | None
    selected_entities: tuple[OrganizationEntity, ...]
    pending_entity_ids: tuple[str, ...]
    excluded_candidates: tuple[ExcludedCandidate, ...]
    views: tuple[OrganizationOutputView, ...]
    summary: OutputSummary
    outputs: tuple[ResearchOutput, ...]
    relationships: tuple[OrganizationRelationship, ...]
    current_affiliations: tuple[AffiliationRecord, ...]
    undated_relationship_count: int
    research_families: tuple[ResearchFamily, ...]
    output_relations: tuple[OutputRelation, ...]
    relation_counts: dict[str, int]
    verification: PreviewVerification = Field(default_factory=PreviewVerification)


def preview_organization_scope(request: OrganizationScopePreviewRequest) -> OrganizationScopePreview:
    """Filter provided records and aggregate dated affiliations; never fetch sources."""
    scope = request.scope
    catalog = {item.entity_id: item for item in request.candidate_entities}
    catalog.update((item.entity_id, item) for item in scope.entities)
    selected = scope.entities or tuple(
        item for item in catalog.values() if item.type in scope.organization_types
    )
    selected_ids = {item.entity_id for item in selected}
    excluded = tuple(ExcludedCandidate(
        entity_id=item.entity_id,
        reason="type_out_of_scope" if item.type not in scope.organization_types else "not_selected",
    ) for item in request.candidate_entities if item.entity_id not in selected_ids)

    direct: dict[str, set[str]] = defaultdict(set)
    inherited: dict[str, set[str]] = defaultdict(set)
    membership = {key: "family:" + family.family_id
                  for family in request.research_families for key in family.output_ids}

    def counts(keys):
        families = tuple(sorted({membership.get(key, "publication:" + key) for key in keys}))
        return dict(publication_count=len(keys), research_family_ids=families,
                    research_family_count=len(families),
                    unlinked_publication_count=sum(key not in membership for key in keys))
    outputs = tuple(item for item in request.outputs if scope.start_date <= item.published_on
                    and (item.published_until or item.published_on) <= scope.end_date)
    parents_by_date = {}
    for output in outputs:
        bounds = (output.published_on, output.published_until or output.published_on)
        parents = parents_by_date.get(bounds)
        if parents is None:
            parents = defaultdict(set)
            for relationship in request.relationships:
                if relationship.applies_at(bounds[0]) and relationship.applies_at(bounds[1]):
                    parents[relationship.child_id].add(relationship.parent_id)
            parents_by_date[bounds] = parents
        for affiliation in output.affiliations:
            if affiliation.entity_id in selected_ids:
                direct[affiliation.entity_id].add(output.output_id)
            pending = list(parents.get(affiliation.entity_id, ()))
            seen: set[str] = set()
            while pending:
                parent = pending.pop()
                if parent in seen:
                    continue
                seen.add(parent)
                if parent in selected_ids:
                    inherited[parent].add(output.output_id)
                pending.extend(parents.get(parent, ()))

    views = tuple(OrganizationOutputView(
        entity_id=item.entity_id, name=item.name, type=item.type,
        output_ids=tuple(sorted(direct[item.entity_id] | inherited[item.entity_id])),
        direct_output_ids=tuple(sorted(direct[item.entity_id])),
        inherited_output_ids=tuple(sorted(inherited[item.entity_id] - direct[item.entity_id])),
        output_count=len(direct[item.entity_id] | inherited[item.entity_id]),
        **counts(direct[item.entity_id] | inherited[item.entity_id]),
    ) for item in selected)
    all_outputs = tuple(sorted({key for view in views for key in view.output_ids}))
    discovery = None if scope.entities else OrganizationDiscoveryQuery(
        organization_types=scope.organization_types, disciplines=scope.disciplines,
        topic=scope.topic, start_date=scope.start_date, end_date=scope.end_date,
    )
    return OrganizationScopePreview(
        scope=scope, selection_mode="named_entities" if scope.entities else "candidate_discovery",
        discovery_query=discovery, selected_entities=selected,
        pending_entity_ids=tuple(item.entity_id for item in selected if item.resolution_status == "pending"),
        excluded_candidates=excluded, views=views,
        summary=OutputSummary(output_ids=all_outputs, output_count=len(all_outputs), **counts(all_outputs)),
        outputs=outputs, relationships=request.relationships, current_affiliations=request.current_affiliations,
        undated_relationship_count=sum(item.valid_from is None for item in request.relationships),
        research_families=request.research_families,
        output_relations=tuple(item for item in request.output_relations if item.output_id in all_outputs),
        relation_counts={kind: len({(item.output_id, tuple(sorted(item.entity_ids)))
                                   for item in request.output_relations
                                   if item.kind == kind and item.output_id in all_outputs})
                         for kind in ("coauthorship", "funding", "citation")},
    )
