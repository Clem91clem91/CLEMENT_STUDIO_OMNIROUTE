from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class EndpointKind(str, Enum):
    LOCAL = "LOCAL"
    PROXY = "PROXY"
    CLOUD = "CLOUD"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EndpointSpec:
    name: str
    base_url: str
    explicit_kind: EndpointKind | None = None


@dataclass(frozen=True)
class AccountingDecision:
    endpoint_kind: EndpointKind
    final_provider_kind: EndpointKind
    billing_mode: str
    technical_tokens: int
    billable_tokens: int
    quota_used: int
    cost_eur: float | None
    verdict: str
    reason: str


def _normalized_host(url: str) -> tuple[str, int | None]:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    host = (parsed.hostname or "").strip().lower()
    return host, parsed.port


def classify_endpoint(spec: EndpointSpec) -> EndpointKind:
    """Classify an endpoint while preserving CLEMENT's routing invariants.

    Critical invariants:
    - OmniRoute on localhost:20128 is PROXY, never LOCAL.
    - LM Studio on localhost:1234 is LOCAL.
    - OpenRouter is CLOUD.
    - An explicit kind is accepted only after the hard invariants above.
    """

    name = (spec.name or "").strip().lower()
    host, port = _normalized_host(spec.base_url)
    loopback = host in {"127.0.0.1", "localhost", "::1"}

    if "omniroute" in name or (loopback and port == 20128):
        return EndpointKind.PROXY
    if "lm studio" in name or "lm_studio" in name or (loopback and port == 1234):
        return EndpointKind.LOCAL
    if "openrouter" in name or host == "openrouter.ai" or host.endswith(".openrouter.ai"):
        return EndpointKind.CLOUD

    if spec.explicit_kind is not None:
        return spec.explicit_kind

    # Unknown loopback services are deliberately not assumed LOCAL because a
    # local listener may itself be a proxy to a paid remote provider.
    return EndpointKind.UNKNOWN


def decide_accounting(
    *,
    endpoint_kind: EndpointKind,
    final_provider_kind: EndpointKind | None,
    technical_tokens: int,
    reported_cost_eur: float | None = None,
) -> AccountingDecision:
    """Decide billing from the actual final provider, not the entry endpoint.

    A PROXY endpoint is only an ingress classification. Billing remains
    inconclusive until the proxy resolves the final provider as LOCAL or CLOUD.
    """

    tokens = max(0, int(technical_tokens))
    final_kind = final_provider_kind or endpoint_kind

    if endpoint_kind == EndpointKind.PROXY and final_provider_kind in {None, EndpointKind.PROXY, EndpointKind.UNKNOWN}:
        return AccountingDecision(
            endpoint_kind=endpoint_kind,
            final_provider_kind=final_kind,
            billing_mode="INCONCLUSIVE",
            technical_tokens=tokens,
            billable_tokens=0,
            quota_used=0,
            cost_eur=None,
            verdict="INCONCLUSIVE",
            reason="Proxy route did not expose a resolved final provider.",
        )

    if final_kind == EndpointKind.LOCAL:
        return AccountingDecision(
            endpoint_kind=endpoint_kind,
            final_provider_kind=EndpointKind.LOCAL,
            billing_mode="LOCAL_UNLIMITED",
            technical_tokens=tokens,
            billable_tokens=0,
            quota_used=0,
            cost_eur=0.0,
            verdict="PASS",
            reason="Final provider is local; technical usage is preserved but non-billable.",
        )

    if final_kind == EndpointKind.CLOUD:
        return AccountingDecision(
            endpoint_kind=endpoint_kind,
            final_provider_kind=EndpointKind.CLOUD,
            billing_mode="METERED",
            technical_tokens=tokens,
            billable_tokens=tokens,
            quota_used=tokens,
            cost_eur=reported_cost_eur,
            verdict="PASS",
            reason="Final provider is cloud; technical tokens remain billable.",
        )

    return AccountingDecision(
        endpoint_kind=endpoint_kind,
        final_provider_kind=final_kind,
        billing_mode="INCONCLUSIVE",
        technical_tokens=tokens,
        billable_tokens=0,
        quota_used=0,
        cost_eur=None,
        verdict="INCONCLUSIVE",
        reason="Final provider kind is unknown.",
    )
