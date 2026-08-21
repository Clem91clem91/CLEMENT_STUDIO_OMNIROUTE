from clement_omniroute.core import EndpointKind
from clement_omniroute.routing import RouteAttempt, certify_route


def test_empty_route_evidence_is_inconclusive():
    result = certify_route([])
    assert result.verdict == "INCONCLUSIVE"


def test_direct_local_route_is_unlimited_and_non_billable():
    result = certify_route([
        RouteAttempt(
            "local",
            EndpointKind.LOCAL,
            EndpointKind.LOCAL,
            True,
            200,
            technical_tokens=1000,
            tool_count=5,
            context_limit=32768,
        )
    ], require_tools=True, required_context=16000)
    assert result.verdict == "PASS"
    assert result.accounting is not None
    assert result.accounting.billing_mode == "LOCAL_UNLIMITED"
    assert result.accounting.billable_tokens == 0
    assert result.accounting.technical_tokens == 1000


def test_proxy_to_cloud_is_metered_by_final_provider():
    result = certify_route([
        RouteAttempt(
            "omniroute",
            EndpointKind.PROXY,
            EndpointKind.CLOUD,
            True,
            500,
            technical_tokens=800,
            reported_cost_eur=0.04,
        )
    ])
    assert result.verdict == "PASS"
    assert result.accounting is not None
    assert result.accounting.billing_mode == "METERED"
    assert result.accounting.billable_tokens == 800


def test_proxy_without_final_provider_is_inconclusive():
    result = certify_route([
        RouteAttempt("omniroute", EndpointKind.PROXY, None, True, 300, technical_tokens=50)
    ])
    assert result.verdict == "INCONCLUSIVE"
    assert "final_provider_accounting_inconclusive" in result.reasons


def test_failover_is_proven_by_second_successful_attempt():
    result = certify_route([
        RouteAttempt("primary", EndpointKind.PROXY, None, False, 100, error_type="timeout", error_message="deadline"),
        RouteAttempt("fallback", EndpointKind.CLOUD, EndpointKind.CLOUD, True, 600, technical_tokens=250),
    ])
    assert result.verdict == "PASS"
    assert result.selected_attempt == 1
    assert result.fallback_count == 1
    assert result.failover_exercised is True
    assert result.errors_observed == ("timeout:deadline",)


def test_missing_required_tools_fails_even_if_route_succeeds():
    result = certify_route([
        RouteAttempt("local", EndpointKind.LOCAL, EndpointKind.LOCAL, True, 100, tool_count=0)
    ], require_tools=True, minimum_tool_count=1)
    assert result.verdict == "FAIL"
    assert "tool_capability_not_proven" in result.reasons


def test_all_attempts_fail():
    result = certify_route([
        RouteAttempt("a", EndpointKind.LOCAL, EndpointKind.LOCAL, False, 100, error_type="500"),
        RouteAttempt("b", EndpointKind.CLOUD, EndpointKind.CLOUD, False, 200, error_type="timeout"),
    ])
    assert result.verdict == "FAIL"
    assert result.selected_attempt is None
    assert "all_route_attempts_failed" in result.reasons
