from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .core import AccountingDecision, EndpointKind, decide_accounting


@dataclass(frozen=True)
class RouteAttempt:
    route_name: str
    entry_kind: EndpointKind
    final_provider_kind: EndpointKind | None
    success: bool
    latency_ms: float
    technical_tokens: int = 0
    reported_cost_eur: float | None = None
    tool_count: int | None = None
    context_limit: int | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class RouteCertification:
    verdict: str
    attempts: tuple[RouteAttempt, ...]
    selected_attempt: int | None
    fallback_count: int
    failover_exercised: bool
    accounting: AccountingDecision | None
    tools_verified: bool | None
    context_verified: bool | None
    errors_observed: tuple[str, ...]
    reasons: tuple[str, ...]


def certify_route(
    attempts: Iterable[RouteAttempt],
    *,
    require_tools: bool = False,
    minimum_tool_count: int = 1,
    required_context: int | None = None,
) -> RouteCertification:
    items = tuple(attempts)
    if not items:
        return RouteCertification(
            verdict="INCONCLUSIVE",
            attempts=(),
            selected_attempt=None,
            fallback_count=0,
            failover_exercised=False,
            accounting=None,
            tools_verified=None,
            context_verified=None,
            errors_observed=(),
            reasons=("no_route_attempt_evidence",),
        )

    selected_index: int | None = None
    for index, item in enumerate(items):
        if item.success:
            selected_index = index
            break

    errors = tuple(
        f"{item.error_type or 'error'}:{item.error_message or ''}".rstrip(":")
        for item in items
        if not item.success
    )
    fallback_count = selected_index if selected_index is not None else max(0, len(items) - 1)
    failover_exercised = selected_index is not None and selected_index > 0

    if selected_index is None:
        return RouteCertification(
            verdict="FAIL",
            attempts=items,
            selected_attempt=None,
            fallback_count=fallback_count,
            failover_exercised=False,
            accounting=None,
            tools_verified=None,
            context_verified=None,
            errors_observed=errors,
            reasons=("all_route_attempts_failed",),
        )

    selected = items[selected_index]
    accounting = decide_accounting(
        endpoint_kind=selected.entry_kind,
        final_provider_kind=selected.final_provider_kind,
        technical_tokens=selected.technical_tokens,
        reported_cost_eur=selected.reported_cost_eur,
    )

    tools_verified: bool | None
    if not require_tools:
        tools_verified = None
    elif selected.tool_count is None:
        tools_verified = False
    else:
        tools_verified = selected.tool_count >= minimum_tool_count

    context_verified: bool | None
    if required_context is None:
        context_verified = None
    elif selected.context_limit is None:
        context_verified = False
    else:
        context_verified = selected.context_limit >= required_context

    reasons: list[str] = []
    if accounting.verdict == "INCONCLUSIVE":
        reasons.append("final_provider_accounting_inconclusive")
    if require_tools and tools_verified is not True:
        reasons.append("tool_capability_not_proven")
    if required_context is not None and context_verified is not True:
        reasons.append("context_capacity_not_proven")

    if any(reason in {"tool_capability_not_proven", "context_capacity_not_proven"} for reason in reasons):
        verdict = "FAIL"
    elif accounting.verdict == "INCONCLUSIVE":
        verdict = "INCONCLUSIVE"
    else:
        verdict = "PASS"

    return RouteCertification(
        verdict=verdict,
        attempts=items,
        selected_attempt=selected_index,
        fallback_count=fallback_count,
        failover_exercised=failover_exercised,
        accounting=accounting,
        tools_verified=tools_verified,
        context_verified=context_verified,
        errors_observed=errors,
        reasons=tuple(reasons),
    )
