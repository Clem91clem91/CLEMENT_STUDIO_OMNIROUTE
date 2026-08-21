from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .core import EndpointKind


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    model_id: str
    provider_id: str
    endpoint_kind: EndpointKind
    capabilities: frozenset[str] = frozenset()
    quality_score: float = 0.5
    latency_ms: float = 1000.0
    context_limit: int = 0
    supports_tools: bool = False
    estimated_vram_mb: int = 0
    estimated_cost_per_million_eur: float | None = None
    healthy: bool = True
    final_provider_kind: EndpointKind | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def effective_provider_kind(self) -> EndpointKind:
        if self.endpoint_kind is EndpointKind.PROXY and self.final_provider_kind not in {None, EndpointKind.PROXY}:
            return self.final_provider_kind or EndpointKind.UNKNOWN
        return self.endpoint_kind


@dataclass(frozen=True, slots=True)
class AgentRoutingRequest:
    agent_id: str
    required_capabilities: frozenset[str] = frozenset()
    preferred_capabilities: frozenset[str] = frozenset()
    required_context: int = 0
    require_tools: bool = False
    max_latency_ms: float | None = None
    max_vram_mb: int | None = None
    available_vram_mb: int | None = None
    prefer_local: bool = True
    allow_cloud: bool = True
    allow_unknown_provider: bool = False
    quality_weight: float = 0.40
    capability_weight: float = 0.15
    latency_weight: float = 0.15
    locality_weight: float = 0.15
    cost_weight: float = 0.05
    context_weight: float = 0.05
    resource_weight: float = 0.05

    def weights(self) -> tuple[float, ...]:
        return (
            self.quality_weight,
            self.capability_weight,
            self.latency_weight,
            self.locality_weight,
            self.cost_weight,
            self.context_weight,
            self.resource_weight,
        )


@dataclass(frozen=True, slots=True)
class CandidateScore:
    model_id: str
    provider_id: str
    eligible: bool
    score: float
    reasons: tuple[str, ...]
    effective_provider_kind: EndpointKind
    components: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class AgentRoutePlan:
    agent_id: str
    verdict: str
    primary_model_id: str | None
    fallback_model_ids: tuple[str, ...]
    ranked: tuple[CandidateScore, ...]
    reasons: tuple[str, ...]


class DynamicAgentRouter:
    """Deterministic per-agent model selector.

    The router only ranks candidates from machine-supplied model metadata. It
    never probes providers itself and it deliberately fails closed when a
    proxy does not expose a known final-provider kind.
    """

    def score_candidate(self, request: AgentRoutingRequest, candidate: ModelCandidate) -> CandidateScore:
        reasons: list[str] = []
        components: dict[str, float] = {}
        effective_kind = candidate.effective_provider_kind

        if not candidate.healthy:
            reasons.append("MODEL_UNHEALTHY")
        missing = sorted(request.required_capabilities - candidate.capabilities)
        if missing:
            reasons.append("MISSING_REQUIRED_CAPABILITIES=" + ",".join(missing))
        if request.required_context > 0 and candidate.context_limit < request.required_context:
            reasons.append(
                f"CONTEXT_TOO_SMALL required={request.required_context} actual={candidate.context_limit}"
            )
        if request.require_tools and not candidate.supports_tools:
            reasons.append("TOOLS_REQUIRED_NOT_SUPPORTED")
        if request.max_latency_ms is not None and candidate.latency_ms > request.max_latency_ms:
            reasons.append(
                f"LATENCY_OVER_BUDGET max={request.max_latency_ms} actual={candidate.latency_ms}"
            )
        if request.max_vram_mb is not None and candidate.estimated_vram_mb > request.max_vram_mb:
            reasons.append(
                f"MODEL_VRAM_OVER_BUDGET max={request.max_vram_mb} actual={candidate.estimated_vram_mb}"
            )
        if request.available_vram_mb is not None and candidate.estimated_vram_mb > request.available_vram_mb:
            reasons.append(
                f"MODEL_VRAM_OVER_AVAILABLE available={request.available_vram_mb} actual={candidate.estimated_vram_mb}"
            )
        if effective_kind is EndpointKind.CLOUD and not request.allow_cloud:
            reasons.append("CLOUD_NOT_ALLOWED")
        if effective_kind is EndpointKind.UNKNOWN and not request.allow_unknown_provider:
            reasons.append("UNKNOWN_FINAL_PROVIDER_FAIL_CLOSED")
        if candidate.endpoint_kind is EndpointKind.PROXY and candidate.final_provider_kind in {None, EndpointKind.PROXY, EndpointKind.UNKNOWN} and not request.allow_unknown_provider:
            if "UNKNOWN_FINAL_PROVIDER_FAIL_CLOSED" not in reasons:
                reasons.append("UNKNOWN_FINAL_PROVIDER_FAIL_CLOSED")

        if reasons:
            return CandidateScore(
                model_id=candidate.model_id,
                provider_id=candidate.provider_id,
                eligible=False,
                score=0.0,
                reasons=tuple(reasons),
                effective_provider_kind=effective_kind,
                components={},
            )

        quality = _clamp01(candidate.quality_score)
        preferred_total = len(request.preferred_capabilities)
        preferred_hit = len(request.preferred_capabilities & candidate.capabilities)
        preferred_ratio = 1.0 if preferred_total == 0 else preferred_hit / preferred_total
        required_total = len(request.required_capabilities)
        surplus = max(0, len(candidate.capabilities) - required_total - preferred_hit)
        capability = _clamp01(0.75 + 0.25 * preferred_ratio - min(0.20, surplus * 0.01))

        latency = _clamp01(1.0 - max(0.0, candidate.latency_ms) / 10000.0)
        locality = _locality_score(effective_kind, request.prefer_local)
        cost = _cost_score(effective_kind, candidate.estimated_cost_per_million_eur)
        context = _context_score(request.required_context, candidate.context_limit)
        resource = _resource_score(candidate.estimated_vram_mb, request.available_vram_mb or request.max_vram_mb)

        components.update(
            quality=quality,
            capability=capability,
            latency=latency,
            locality=locality,
            cost=cost,
            context=context,
            resource=resource,
        )

        weights = request.weights()
        if any(weight < 0 for weight in weights):
            raise ValueError("ROUTING_WEIGHT_NEGATIVE")
        weight_total = sum(weights)
        if weight_total <= 0:
            raise ValueError("ROUTING_WEIGHT_TOTAL_ZERO")

        raw = (
            quality * request.quality_weight
            + capability * request.capability_weight
            + latency * request.latency_weight
            + locality * request.locality_weight
            + cost * request.cost_weight
            + context * request.context_weight
            + resource * request.resource_weight
        )
        score = raw / weight_total

        reasons.append(f"EFFECTIVE_PROVIDER_KIND={effective_kind.value}")
        reasons.append(f"SCORE={score:.6f}")
        return CandidateScore(
            model_id=candidate.model_id,
            provider_id=candidate.provider_id,
            eligible=True,
            score=score,
            reasons=tuple(reasons),
            effective_provider_kind=effective_kind,
            components=components,
        )

    def route(self, request: AgentRoutingRequest, candidates: Iterable[ModelCandidate]) -> AgentRoutePlan:
        scored = [self.score_candidate(request, candidate) for candidate in candidates]
        ranked = tuple(sorted(scored, key=lambda item: (not item.eligible, -item.score, item.model_id)))
        eligible = [item for item in ranked if item.eligible]
        if not eligible:
            return AgentRoutePlan(
                agent_id=request.agent_id,
                verdict="INCONCLUSIVE",
                primary_model_id=None,
                fallback_model_ids=(),
                ranked=ranked,
                reasons=("NO_ELIGIBLE_MODEL_WITH_MACHINE_PROVEN_CONSTRAINTS",),
            )
        return AgentRoutePlan(
            agent_id=request.agent_id,
            verdict="PASS",
            primary_model_id=eligible[0].model_id,
            fallback_model_ids=tuple(item.model_id for item in eligible[1:]),
            ranked=ranked,
            reasons=("DETERMINISTIC_RANKING",),
        )

    def route_agents(
        self,
        requests: Iterable[AgentRoutingRequest],
        candidates: Iterable[ModelCandidate],
    ) -> dict[str, AgentRoutePlan]:
        candidate_pool = tuple(candidates)
        plans: dict[str, AgentRoutePlan] = {}
        for request in requests:
            if request.agent_id in plans:
                raise ValueError(f"DUPLICATE_AGENT_ID={request.agent_id}")
            plans[request.agent_id] = self.route(request, candidate_pool)
        return plans


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _locality_score(kind: EndpointKind, prefer_local: bool) -> float:
    if prefer_local:
        return {
            EndpointKind.LOCAL: 1.0,
            EndpointKind.PROXY: 0.65,
            EndpointKind.CLOUD: 0.25,
            EndpointKind.UNKNOWN: 0.0,
        }[kind]
    return {
        EndpointKind.LOCAL: 0.75,
        EndpointKind.PROXY: 0.80,
        EndpointKind.CLOUD: 0.85,
        EndpointKind.UNKNOWN: 0.0,
    }[kind]


def _cost_score(kind: EndpointKind, cost_per_million_eur: float | None) -> float:
    if kind is EndpointKind.LOCAL:
        return 1.0
    if cost_per_million_eur is None:
        return 0.50 if kind is EndpointKind.PROXY else 0.35
    cost = max(0.0, float(cost_per_million_eur))
    return _clamp01(1.0 - cost / 50.0)


def _context_score(required_context: int, context_limit: int) -> float:
    if required_context <= 0:
        return 1.0
    ratio = context_limit / required_context
    return _clamp01(0.5 + min(0.5, max(0.0, ratio - 1.0) / 3.0))


def _resource_score(estimated_vram_mb: int, budget_mb: int | None) -> float:
    if estimated_vram_mb <= 0 or budget_mb is None or budget_mb <= 0:
        return 1.0
    ratio = estimated_vram_mb / budget_mb
    return _clamp01(1.0 - ratio * 0.5)
