"""Versioned preference configuration and deterministic matching; no retrieval."""
from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field, FiniteFloat, model_validator

from app.research_evaluation import (
    EvaluationRecord, EvaluationRequest, EvaluationSource, OutputType, PAPER_METRICS, RANKS, SchemeId, applicability,
)
from app.research_scope import Identifier, Label, OrganizationEntity, OrganizationResearchScope, ScopeRecord

Dimension = Literal["topic_relevance", "research_alignment", "output_performance",
                    "evidence_completeness", "recency", "cooperation_complementarity"]
Group = Literal["venue", "paper"]
ORDERED_GRADES = {**RANKS, "icore": ("A*", "A", "B", "C")}


class Weight(ScopeRecord):
    weight: FiniteFloat = Field(ge=0, strict=True)
    enabled: bool = True


class GradeMapping(ScopeRecord):
    scheme_id: SchemeId
    version: Label
    scores: dict[str, FiniteFloat] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def preserve_order(self):
        order = ORDERED_GRADES.get(self.scheme_id)
        if order is None or set(self.scores) != set(order):
            raise ValueError("mapping must cover exactly the ordered grades of this scheme")
        values = [self.scores[key] for key in order]
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("mapping preference scores must be between zero and one")
        if any(left < right for left, right in zip(values, values[1:])):
            raise ValueError("mapping must preserve the scheme's grade order")
        return self


WeightInput = Weight | Annotated[FiniteFloat, Field(strict=True)]


def weight_objects(values) -> dict[str, Weight]:
    result = {}
    for key, value in values.items():
        if isinstance(value, Weight):
            result[key] = value
        else:
            if isinstance(value, bool) or value < 0:
                raise ValueError("weights must be finite non-negative numeric values")
            result[key] = Weight(weight=value)
    return result


def normalized(values: dict[str, Weight]) -> dict[str, float]:
    active = {key: item.weight if item.enabled else 0 for key, item in values.items()}
    maximum = max(active.values(), default=0)
    if maximum <= 0:
        raise ValueError("an active weight level must contain at least one positive weight")
    # Scaling before summation keeps valid 1e308 + 1e308 inputs finite.
    total = math.fsum(value / maximum for value in active.values())
    return {key: (value / maximum) / total for key, value in active.items()}


class PresetCatalogue(ScopeRecord):
    version: Label
    presets: dict[Literal['research_development', 'cooperation_discovery'],
                  dict[Dimension, Annotated[FiniteFloat, Field(ge=0, strict=True)]]]

    @model_validator(mode='after')
    def complete_defaults(self):
        if set(self.presets) != {'research_development', 'cooperation_discovery'}:
            raise ValueError('both organization presets are required')
        for values in self.presets.values():
            if set(values) != set(Dimension.__args__):
                raise ValueError('a preset must declare every matching dimension')
            normalized(weight_objects(values))
        return self


def load_preset_catalogue() -> PresetCatalogue:
    path = Path(__file__).resolve().parents[1] / 'config/organization-presets.json'
    return PresetCatalogue.model_validate_json(path.read_text(encoding='utf-8'))


class WeightConfigurationRequest(ScopeRecord):
    preset: Literal["research_development", "cooperation_discovery", "custom"] = "research_development"
    config_version: Label = "user-config-v1"
    weights: dict[Dimension, WeightInput] = Field(default_factory=dict, max_length=6)
    performance_groups: dict[Group, WeightInput] = Field(default_factory=lambda: {"venue": 1, "paper": 1})
    metric_weights: dict[SchemeId, WeightInput] = Field(default_factory=dict, max_length=20)
    mappings: tuple[GradeMapping, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def validate_levels(self):
        root = self.root_weights()
        normalized(root)
        groups = weight_objects(self.performance_groups)
        metrics = weight_objects(self.metric_weights)
        active_performance = root.get("output_performance", Weight(weight=0))
        if active_performance.enabled and active_performance.weight > 0:
            normalized(groups)
            for group in groups:
                members = {key: value for key, value in metrics.items()
                           if ("paper" if key in PAPER_METRICS else "venue") == group}
                if members and groups[group].enabled and groups[group].weight > 0:
                    normalized(members)
        ids = [mapping.scheme_id for mapping in self.mappings]
        if len(ids) != len(set(ids)):
            raise ValueError("only one mapping version per scheme in a configuration")
        return self

    def root_weights(self, catalogue: PresetCatalogue | None = None) -> dict[str, Weight]:
        original = {} if self.preset == "custom" else (catalogue or load_preset_catalogue()).presets[self.preset]
        return weight_objects({**original, **self.weights})


class WeightConfigurationPreview(ScopeRecord):
    rule_version: Literal["adrs-weight-rules-v1"] = "adrs-weight-rules-v1"
    preset_version: Label = "adrs-presets-v1"
    config_version: str
    raw_config: dict
    effective_weights: dict[str, float]
    effective_groups: dict[str, float]
    effective_metric_weights: dict[str, float]
    mappings: tuple[GradeMapping, ...]
    semantics: Literal["preference_configuration_only"] = "preference_configuration_only"


def preview_weights(request: WeightConfigurationRequest, catalogue: PresetCatalogue | None = None) -> WeightConfigurationPreview:
    catalogue = catalogue or load_preset_catalogue()
    root = request.root_weights(catalogue)
    groups = weight_objects(request.performance_groups)
    metrics = weight_objects(request.metric_weights)
    effective_root = normalized(root)
    effective_groups = normalized(groups) if effective_root.get("output_performance", 0) else dict.fromkeys(groups, 0.0)
    effective_metrics = dict.fromkeys(metrics, 0.0)
    for group in groups:
        members = {key: value for key, value in metrics.items()
                   if ("paper" if key in PAPER_METRICS else "venue") == group}
        if members and effective_groups[group] and effective_root.get("output_performance", 0):
            effective_metrics.update(normalized(members))
    mappings = request.mappings or tuple(GradeMapping(
        scheme_id=key, version="adrs-preference-map-v1",
        scores={grade: 1 - index / len(order) for index, grade in enumerate(order)},
    ) for key, order in ORDERED_GRADES.items())
    return WeightConfigurationPreview(
        preset_version=catalogue.version,
        config_version=request.config_version,
        raw_config={"preset": request.preset, "weights": {key: value.model_dump() for key, value in root.items()},
                    "performance_groups": {key: value.model_dump() for key, value in groups.items()},
                    "metric_weights": {key: value.model_dump() for key, value in metrics.items()}},
        effective_weights=effective_root, effective_groups=effective_groups,
        effective_metric_weights=effective_metrics, mappings=mappings,
    )


Score = Annotated[FiniteFloat, Field(ge=0, le=1, strict=True)]
Rule = Literal["provided_v1", "token_overlap_v1", "linear_recency_v1", "confirmed_sources_v1"]
RelationKind = Literal["funding", "coauthorship", "project", "joint_lab"]


class MatchingEvidence(ScopeRecord):
    evidence_id: Identifier
    source_url: AnyHttpUrl
    retrieved_on: date
    verification_status: Literal["confirmed", "unreviewed"] = "unreviewed"


class MatchingFeature(ScopeRecord):
    value: Score | None
    evidence_ids: tuple[Identifier, ...] = Field(default=(), max_length=50)
    reason: Label

    @model_validator(mode="after")
    def known_requires_evidence(self):
        if self.value is not None and not self.evidence_ids:
            raise ValueError("a known feature needs referenced evidence")
        return self


class MetricRule(ScopeRecord):
    provider: Label
    edition: Label
    normalization_version: Label
    citation_cutoff: date | None = None


class ComparisonGroup(ScopeRecord):
    group_id: Identifier
    discipline: Label
    output_type: OutputType
    metric_year: int = Field(ge=1800, le=2200)
    category: Label
    feature_rules: dict[Dimension, Rule] = Field(default_factory=dict, max_length=5)
    metric_rules: dict[SchemeId, MetricRule] = Field(default_factory=dict, max_length=20)
    performance_applicable: bool = False

    @model_validator(mode="after")
    def valid_rule_assignment(self):
        automatic = {"token_overlap_v1": "topic_relevance", "linear_recency_v1": "recency",
                     "confirmed_sources_v1": "evidence_completeness"}
        for dimension, rule in self.feature_rules.items():
            if dimension == "output_performance" or (rule in automatic and automatic[rule] != dimension):
                raise ValueError("feature rule does not apply to this dimension; performance uses metric rules")
        context = EvaluationRequest(disciplines=(self.discipline,), output_type=self.output_type,
            target_id="comparison-context", publication_year=self.metric_year,
            metric_year=self.metric_year, use_public_snapshots=False)
        if any(not applicability(scheme, context)[0] for scheme in self.metric_rules):
            raise ValueError("metric scheme is not applicable to the group's discipline and output type")
        return self


class MatchingMetric(ScopeRecord):
    record: EvaluationRecord
    normalized_value: Score | None = None
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    reason: Label


class MatchingObservation(ScopeRecord):
    family_id: Identifier
    group_id: Identifier
    published_on: date | None = None
    published_until: date | None = None
    date_precision: Literal['day', 'month', 'year'] = 'day'
    title: Label
    abstract: Annotated[str, Field(max_length=12000)] = ""
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=50)
    features: dict[Dimension, MatchingFeature] = Field(default_factory=dict, max_length=5)
    metrics: dict[SchemeId, MatchingMetric] = Field(default_factory=dict, max_length=20)

    @model_validator(mode='after')
    def valid_date_interval(self):
        if self.published_until and (not self.published_on or self.published_until < self.published_on):
            raise ValueError('observation publication interval is invalid')
        return self


class MatchingFact(ScopeRecord):
    value: bool | None = None
    verification_status: Literal["confirmed", "unknown", "contradicted"] = "unknown"
    evidence_ids: tuple[Identifier, ...] = Field(default=(), max_length=50)


class MatchingCandidate(ScopeRecord):
    entity: OrganizationEntity
    observations: tuple[MatchingObservation, ...] = Field(default=(), max_length=1000)
    facts: dict[RelationKind, MatchingFact] = Field(default_factory=dict, max_length=4)


class MetricCondition(ScopeRecord):
    scheme_id: SchemeId
    allowed_values: tuple[Label, ...] = Field(default=(), max_length=10)
    minimum: FiniteFloat | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def one_condition(self):
        if bool(self.allowed_values) == (self.minimum is not None):
            raise ValueError("metric condition needs exactly allowed_values or minimum")
        return self


class MatchingSnapshotInput(ScopeRecord):
    scope: OrganizationResearchScope
    evidence_cutoff: date
    evaluation_versions: dict[SchemeId, Label] = Field(default_factory=dict, max_length=20)
    evidence: tuple[MatchingEvidence, ...] = Field(min_length=1, max_length=10000)
    groups: tuple[ComparisonGroup, ...] = Field(min_length=1, max_length=50)
    candidates: tuple[MatchingCandidate, ...] = Field(min_length=1, max_length=200)
    required_relations: tuple[RelationKind, ...] = Field(default=(), max_length=4)
    required_metrics: tuple[MetricCondition, ...] = Field(default=(), max_length=20)
    session_id: UUID | None = None
    schema_version: Literal["matching-evidence-v1"] = "matching-evidence-v1"
    origin: Literal['explicit_records', 'saved_research', 'running_research'] = 'explicit_records'
    source_execution_id: UUID | None = None
    bridge_version: Literal['adrs-session-matching-v1'] | None = None
    bridge_notes: tuple[Label, ...] = Field(default=(), max_length=50)

    @model_validator(mode="after")
    def consistent_snapshot(self):
        if self.origin in {'saved_research','running_research'} and not (self.session_id and self.source_execution_id and self.bridge_version):
            raise ValueError('saved research snapshots require server provenance')
        evidence = {item.evidence_id: item for item in self.evidence}
        groups = {item.group_id: item for item in self.groups}
        entities = {item.entity.entity_id: item for item in self.candidates}
        if len(evidence) != len(self.evidence) or len(groups) != len(self.groups) or len(entities) != len(self.candidates):
            raise ValueError("evidence, group and candidate IDs must each be unique")
        if any(item.retrieved_on > self.evidence_cutoff for item in self.evidence):
            raise ValueError("evidence cannot be retrieved after the frozen cutoff")
        if sum(len(item.observations) for item in self.candidates) > 5000:
            raise ValueError("snapshot supports at most 5000 observations")

        def check_refs(keys):
            if any(key not in evidence for key in keys):
                raise ValueError("unknown evidence reference")

        for selected in self.scope.entities:
            candidate = entities.get(selected.entity_id)
            if candidate is None or candidate.entity != selected:
                raise ValueError("named scope entities must match the frozen candidate records")
        for candidate in self.candidates:
            seen = set()
            for fact in candidate.facts.values():
                check_refs(fact.evidence_ids)
                if fact.verification_status == "confirmed" and (fact.value is None or not fact.evidence_ids):
                    raise ValueError("confirmed facts require a value and evidence")
            for observation in candidate.observations:
                group = groups.get(observation.group_id)
                identity = (observation.group_id, observation.family_id)
                if not group or identity in seen:
                    raise ValueError("unknown group or repeated research family within one comparable group")
                seen.add(identity)
                check_refs(observation.evidence_ids)
                for dimension, feature in observation.features.items():
                    check_refs(feature.evidence_ids)
                    if group.feature_rules.get(dimension) != "provided_v1":
                        raise ValueError("provided features require an explicit provided_v1 group rule")
                for scheme, metric in observation.metrics.items():
                    check_refs(metric.evidence_ids)
                    rule = group.metric_rules.get(scheme)
                    record = metric.record
                    # Reuse the source adapter's raw-grade/numeric validation at this second input boundary.
                    EvaluationSource(source_id=record.source_id, scheme_id=record.scheme_id,
                        edition=record.edition, metric_year=record.metric_year, provider=record.provider,
                        source_url=record.source_url, retrieved_on=record.retrieved_on,
                        access="public", records=(record,))
                    if (not rule or record.scheme_id != scheme or record.metric_year != group.metric_year
                            or record.category != group.category or record.provider != rule.provider
                            or record.edition != rule.edition or record.citation_cutoff != rule.citation_cutoff):
                        raise ValueError("metric differs from the frozen comparison context")
                    if record.retrieved_on > self.evidence_cutoff:
                        raise ValueError("metric was retrieved after the evidence cutoff")
                    if record.status != "available" and metric.normalized_value is not None:
                        raise ValueError("a missing metric cannot have a normalized value")
                    if scheme in ORDERED_GRADES and metric.normalized_value is not None:
                        raise ValueError("ordered grades are mapped at preview time, not pre-scored")
                    if scheme in PAPER_METRICS and (not observation.published_on or
                            record.publication_year != observation.published_on.year):
                        raise ValueError("paper metric publication year differs from its observation")
        return self


class MatchingPreviewRequest(ScopeRecord):
    snapshot_id: UUID
    configuration: WeightConfigurationRequest


class MatchingSnapshotCreated(ScopeRecord):
    snapshot_id: UUID
    evidence_cutoff: date
    schema_version: str


class MatchingPreview(ScopeRecord):
    snapshot_id: str
    evidence_cutoff: date
    evaluation_versions: dict[str, str]
    configuration: WeightConfigurationPreview
    rule_version: Literal['adrs-matching-v1', 'adrs-matching-v2'] = 'adrs-matching-v1'
    groups: tuple[dict, ...]
    excluded: tuple[dict, ...]
    excluded_observations: tuple[dict, ...]
    cross_group_ranking: Literal[False] = False
    external_requests: Literal[0] = 0
    verification: Literal['frozen_owner_provided_evidence', 'frozen_saved_research_evidence','frozen_run_evidence'] = 'frozen_owner_provided_evidence'


def _terms(text: str) -> set[str]:
    # English words and Chinese bigrams; a transparent recall heuristic, not semantic truth.
    latin = set(re.findall(r"[a-z0-9]+", text.casefold()))
    for word in re.findall(r"[\u4e00-\u9fff]+", text):
        latin.update(word[index:index + 2] for index in range(max(1, len(word) - 1)))
    return latin


def _feature(snapshot, group, observation, dimension, evidence):
    rule = group.feature_rules.get(dimension)
    value, reason, refs = None, "No observation for this configured feature", ()
    if rule == "provided_v1":
        provided = observation.features.get(dimension)
        if provided:
            value, reason, refs = provided.value, provided.reason, provided.evidence_ids
    elif rule == "token_overlap_v1":
        query = _terms(snapshot.scope.topic)
        value = len(query & _terms(observation.title + " " + observation.abstract)) / len(query) if query else None
        reason, refs = "Fraction of distinct query terms found in title/abstract", observation.evidence_ids
    elif rule == "linear_recency_v1" and observation.published_on:
        span = (snapshot.scope.end_date - snapshot.scope.start_date).days
        lower = (observation.published_on - snapshot.scope.start_date).days / span if span else 1.0
        upper = ((observation.published_until or observation.published_on) - snapshot.scope.start_date).days / span if span else 1.0
        value = lower if lower == upper else (lower, upper)
        reason, refs = "Publication interval within the frozen inclusive time range; precision retained", observation.evidence_ids
    elif rule == "confirmed_sources_v1":
        refs = tuple(set(observation.evidence_ids))
        value = sum(evidence[key].verification_status == "confirmed" for key in refs) / len(refs)
        reason = "Fraction of explicitly expected observation sources confirmed by the owner"
    return value, reason, refs, rule or "not_configured"


def _aggregate(values, weight, version):
    count = len(values)
    known = [value for value, _, _, _ in values if value is not None]
    lower = math.fsum(value[0] if isinstance(value, tuple) else value for value in known) / count
    upper = (math.fsum(value[1] if isinstance(value, tuple) else value for value in known) + count - len(known)) / count
    return {"weight": weight, "lower_value": lower, "upper_value": upper,
            "lower_contribution": 100 * weight * lower, "upper_contribution": 100 * weight * upper,
            "coverage": len(known) / count, "rule_version": version,
            "evidence_ids": sorted({key for _, _, refs, _ in values for key in refs}),
            "reasons": list(dict.fromkeys(reason for _, reason, _, _ in values))}


def _group_configuration(group, configuration):
    root = configuration.root_weights()
    root = {key: value for key, value in root.items()
            if key in group.feature_rules or (key == "output_performance" and (group.metric_rules or group.performance_applicable))}
    if not any(value.enabled and value.weight > 0 for value in root.values()):
        return {}, {}, {}, tuple(configuration.root_weights())
    effective = normalized(root)
    metrics = weight_objects(configuration.metric_weights)
    metrics = {key: value for key, value in metrics.items() if key in group.metric_rules}
    groups = weight_objects(configuration.performance_groups)
    group_weights = {key: value for key, value in groups.items()
                     if any(("paper" if scheme in PAPER_METRICS else "venue") == key and
                            item.enabled and item.weight > 0 for scheme, item in metrics.items())}
    # No configured applicable metrics leaves the performance dimension unknown, not reallocated.
    metric_weights = {}
    if group_weights and any(item.enabled and item.weight > 0 for item in group_weights.values()):
        group_weights = normalized(group_weights)
        for key, group_weight in group_weights.items():
            members = {scheme: value for scheme, value in metrics.items()
                       if ("paper" if scheme in PAPER_METRICS else "venue") == key}
            if group_weight:
                for scheme, local in normalized(members).items():
                    metric_weights[scheme] = local * group_weight
    omitted = tuple(key for key in configuration.root_weights() if key not in root)
    return effective, metric_weights, groups, omitted


def score_matching_snapshot(snapshot: MatchingSnapshotInput, configuration: WeightConfigurationRequest,
                            snapshot_id: str) -> MatchingPreview:
    evidence = {item.evidence_id: item for item in snapshot.evidence}
    group_by_id = {item.group_id: item for item in snapshot.groups}
    selected_ids = {item.entity_id for item in snapshot.scope.entities}
    excluded, excluded_observations = [], []
    eligible: dict[str, list[tuple[MatchingCandidate, list[MatchingObservation]]]] = {}

    def confirmed(keys):
        return bool(keys) and all(evidence[key].verification_status == "confirmed" for key in keys)

    for candidate in snapshot.candidates:
        key, reasons = candidate.entity.entity_id, []
        if candidate.entity.type not in snapshot.scope.organization_types:
            reasons.append("entity_type_out_of_scope")
        if selected_ids and key not in selected_ids:
            reasons.append("not_selected")
        for kind in snapshot.required_relations:
            fact = candidate.facts.get(kind)
            if not fact or fact.verification_status != "confirmed" or not confirmed(fact.evidence_ids):
                reasons.append(f"required_relation_unverified:{kind}")
            elif fact.value is not True:
                reasons.append(f"required_relation_false:{kind}")
        if reasons:
            excluded.append({"entity_id": key, "reasons": reasons})
            continue
        by_group: dict[str, list] = {}
        for observation in candidate.observations:
            group = group_by_id[observation.group_id]
            reason = None
            if group.discipline not in snapshot.scope.disciplines:
                reason = "discipline_out_of_scope"
            elif not observation.published_on:
                reason = "publication_time_unknown"
            elif not (snapshot.scope.start_date <= observation.published_on and
                      (observation.published_until or observation.published_on) <= snapshot.scope.end_date):
                reason = "time_out_of_scope"
            for condition in snapshot.required_metrics:
                metric = observation.metrics.get(condition.scheme_id)
                if reason:
                    break
                if not metric or metric.record.status != "available" or not confirmed(metric.evidence_ids):
                    reason = f"required_metric_unverified:{condition.scheme_id}"
                elif condition.allowed_values and metric.record.raw_value not in condition.allowed_values:
                    reason = f"required_metric_not_satisfied:{condition.scheme_id}"
                elif condition.minimum is not None and (isinstance(metric.record.raw_value, bool) or
                        not isinstance(metric.record.raw_value, (int, float)) or metric.record.raw_value < condition.minimum):
                    reason = f"required_metric_not_satisfied:{condition.scheme_id}"
            if reason:
                excluded_observations.append({"entity_id": key, "family_id": observation.family_id, "reason": reason})
            else:
                by_group.setdefault(group.group_id, []).append(observation)
        if not by_group:
            excluded.append({"entity_id": key, "reasons": ["no_observations_in_scope"]})
        for group_id, observations in by_group.items():
            eligible.setdefault(group_id, []).append((candidate, observations))

    mappings = {item.scheme_id: item for item in preview_weights(configuration).mappings}
    output_groups = []
    for group in snapshot.groups:
        if group.group_id not in eligible:
            continue
        effective, metric_weights, _, omitted = _group_configuration(group, configuration)
        complete, pending = [], []
        for candidate, observations in eligible[group.group_id]:
            contributions = {}
            for dimension, weight in effective.items():
                if not weight:
                    continue
                if dimension != "output_performance":
                    values = [_feature(snapshot, group, item, dimension, evidence) for item in observations]
                    contributions[dimension] = _aggregate(values, weight, group.feature_rules[dimension])
                    continue
                metric_contributions = {}
                for scheme, metric_weight in metric_weights.items():
                    values = []
                    for observation in observations:
                        metric = observation.metrics.get(scheme)
                        value, refs, reason = None, (), "Configured metric missing in this research family"
                        if metric:
                            refs, reason = metric.evidence_ids, metric.reason
                            if metric.record.status == "available":
                                value = (mappings[scheme].scores.get(metric.record.raw_value) if scheme in mappings
                                         else metric.normalized_value)
                        values.append((value, reason, refs, group.metric_rules[scheme].normalization_version))
                    metric_contributions[scheme] = _aggregate(values, weight * metric_weight,
                        mappings[scheme].version if scheme in mappings else group.metric_rules[scheme].normalization_version)
                if metric_contributions:
                    lower = math.fsum(item["lower_contribution"] for item in metric_contributions.values())
                    upper = math.fsum(item["upper_contribution"] for item in metric_contributions.values())
                    coverage = math.fsum(item["coverage"] * metric_weights[key] for key, item in metric_contributions.items())
                    if all(item["coverage"] == 1 for item in metric_contributions.values() if item["weight"] > 0):
                        coverage = 1.0
                else:
                    lower, upper, coverage = 0.0, 100 * weight, 0.0
                contributions[dimension] = {"weight": weight, "lower_contribution": lower,
                    "upper_contribution": upper, "coverage": coverage, "rule_version": "bounded-performance-v1",
                    "metric_contributions": metric_contributions,
                    "evidence_ids": sorted({key for item in metric_contributions.values() for key in item["evidence_ids"]})}
            coverage = math.fsum(item["weight"] * item["coverage"] for item in contributions.values())
            lower = math.fsum(item["lower_contribution"] for item in contributions.values())
            upper = math.fsum(item["upper_contribution"] for item in contributions.values())
            known = bool(effective) and all(item["coverage"] == 1 and
                abs(item['lower_contribution'] - item['upper_contribution']) < 1e-10 for item in contributions.values())
            result = {"entity_id": candidate.entity.entity_id, "name": candidate.entity.name,
                "type": candidate.entity.type, "family_count": len(observations),
                "family_ids": sorted(item.family_id for item in observations), "coverage": coverage,
                "lower_bound": lower if effective else None, "upper_bound": upper if effective else None,
                "score": lower if known else None,
                "contributions": contributions, "facts": {key: item.model_dump(mode="json") for key, item in candidate.facts.items()},
                "missing_dimensions": [key for key, item in contributions.items() if item["coverage"] < 1]}
            (complete if known else pending).append(result)
        complete.sort(key=lambda item: (-item["score"], item["entity_id"]))
        pending.sort(key=lambda item: item["entity_id"])
        all_results = [*complete, *pending]
        better = [{"better": left["entity_id"], "worse": right["entity_id"]}
                  for left in all_results for right in all_results
                  if effective and left["lower_bound"] > right["upper_bound"] + 1e-9]
        output_groups.append({"group_id": group.group_id, "context": group.model_dump(mode="json"),
            "comparison_status": "comparable" if effective else "no_applicable_dimensions",
            "effective_weights": effective, "effective_metric_weights": metric_weights,
            "not_applicable_dimensions": omitted, "complete": complete, "pending_evidence": pending,
            "definitely_better": better, "aggregation": "equal_research_family_weight"})
    return MatchingPreview(snapshot_id=snapshot_id, evidence_cutoff=snapshot.evidence_cutoff,
        rule_version='adrs-matching-v2' if any(group.performance_applicable for group in snapshot.groups) or
            any(item.published_until and item.published_until != item.published_on for candidate in snapshot.candidates for item in candidate.observations)
            else 'adrs-matching-v1',
        evaluation_versions=snapshot.evaluation_versions, configuration=preview_weights(configuration),
        groups=tuple(output_groups), excluded=tuple(excluded), excluded_observations=tuple(excluded_observations),
        verification='frozen_saved_research_evidence' if snapshot.origin == 'saved_research' else
            'frozen_run_evidence' if snapshot.origin == 'running_research' else 'frozen_owner_provided_evidence')
