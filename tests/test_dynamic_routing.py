from clement_omniroute.core import EndpointKind
from clement_omniroute.dynamic_routing import AgentRoutingRequest, DynamicAgentRouter, ModelCandidate


def candidate(
    model_id: str,
    *,
    kind: EndpointKind,
    quality: float = 0.8,
    latency: float = 500,
    caps=frozenset({"general"}),
    context=32768,
    tools=True,
    vram=0,
    final=None,
    healthy=True,
):
    return ModelCandidate(
        model_id=model_id,
        provider_id=model_id.split("/")[0],
        endpoint_kind=kind,
        final_provider_kind=final,
        capabilities=frozenset(caps),
        quality_score=quality,
        latency_ms=latency,
        context_limit=context,
        supports_tools=tools,
        estimated_vram_mb=vram,
        healthy=healthy,
    )


def test_prefers_local_when_models_are_comparable() -> None:
    router = DynamicAgentRouter()
    request = AgentRoutingRequest(agent_id="planner", required_capabilities=frozenset({"general"}), prefer_local=True)
    plan = router.route(
        request,
        [
            candidate("local/qwen", kind=EndpointKind.LOCAL, quality=0.80),
            candidate("cloud/gpt", kind=EndpointKind.CLOUD, quality=0.82),
        ],
    )
    assert plan.verdict == "PASS"
    assert plan.primary_model_id == "local/qwen"


def test_required_capability_is_hard_constraint() -> None:
    router = DynamicAgentRouter()
    request = AgentRoutingRequest(agent_id="code", required_capabilities=frozenset({"code"}))
    plan = router.route(
        request,
        [
            candidate("local/general", kind=EndpointKind.LOCAL, caps={"general"}),
            candidate("cloud/code", kind=EndpointKind.CLOUD, caps={"code"}),
        ],
    )
    assert plan.primary_model_id == "cloud/code"
    rejected = next(item for item in plan.ranked if item.model_id == "local/general")
    assert rejected.eligible is False
    assert any(reason.startswith("MISSING_REQUIRED_CAPABILITIES") for reason in rejected.reasons)


def test_proxy_with_real_local_final_provider_is_treated_local() -> None:
    router = DynamicAgentRouter()
    request = AgentRoutingRequest(agent_id="general", allow_cloud=False)
    proxied_local = candidate(
        "omniroute/qwen",
        kind=EndpointKind.PROXY,
        final=EndpointKind.LOCAL,
    )
    plan = router.route(request, [proxied_local])
    assert plan.verdict == "PASS"
    assert plan.ranked[0].effective_provider_kind is EndpointKind.LOCAL


def test_proxy_without_final_provider_fails_closed() -> None:
    router = DynamicAgentRouter()
    request = AgentRoutingRequest(agent_id="general")
    unresolved = candidate("omniroute/unknown", kind=EndpointKind.PROXY, final=None)
    plan = router.route(request, [unresolved])
    assert plan.verdict == "INCONCLUSIVE"
    assert plan.primary_model_id is None
    assert "UNKNOWN_FINAL_PROVIDER_FAIL_CLOSED" in plan.ranked[0].reasons


def test_tools_context_latency_and_vram_are_hard_constraints() -> None:
    router = DynamicAgentRouter()
    request = AgentRoutingRequest(
        agent_id="agent-3d",
        require_tools=True,
        required_context=64000,
        max_latency_ms=1500,
        available_vram_mb=12000,
    )
    bad = candidate(
        "local/bad",
        kind=EndpointKind.LOCAL,
        tools=False,
        context=32000,
        latency=2500,
        vram=16000,
    )
    good = candidate(
        "cloud/good",
        kind=EndpointKind.CLOUD,
        tools=True,
        context=128000,
        latency=900,
        vram=0,
    )
    plan = router.route(request, [bad, good])
    assert plan.primary_model_id == "cloud/good"
    bad_score = next(item for item in plan.ranked if item.model_id == "local/bad")
    assert bad_score.eligible is False
    assert len(bad_score.reasons) >= 4


def test_ranking_is_deterministic_on_tie() -> None:
    router = DynamicAgentRouter()
    request = AgentRoutingRequest(agent_id="verifier")
    plan = router.route(
        request,
        [
            candidate("local/z-model", kind=EndpointKind.LOCAL),
            candidate("local/a-model", kind=EndpointKind.LOCAL),
        ],
    )
    assert plan.primary_model_id == "local/a-model"
    assert plan.fallback_model_ids == ("local/z-model",)


def test_multiple_agents_are_routed_independently() -> None:
    router = DynamicAgentRouter()
    requests = [
        AgentRoutingRequest(agent_id="planner", required_capabilities=frozenset({"planning"})),
        AgentRoutingRequest(agent_id="code", required_capabilities=frozenset({"code"})),
    ]
    models = [
        candidate("local/planner", kind=EndpointKind.LOCAL, caps={"planning"}),
        candidate("local/code", kind=EndpointKind.LOCAL, caps={"code"}),
    ]
    plans = router.route_agents(requests, models)
    assert plans["planner"].primary_model_id == "local/planner"
    assert plans["code"].primary_model_id == "local/code"
