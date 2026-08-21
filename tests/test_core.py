from clement_omniroute import (
    EndpointKind,
    EndpointSpec,
    classify_endpoint,
    classify_final_provider,
    decide_accounting,
)


def test_omniroute_loopback_is_proxy_even_if_explicit_local() -> None:
    spec = EndpointSpec(
        name="OmniRoute",
        base_url="http://localhost:20128/v1",
        explicit_kind=EndpointKind.LOCAL,
    )
    assert classify_endpoint(spec) is EndpointKind.PROXY


def test_omniroute_name_is_proxy() -> None:
    assert classify_endpoint(
        EndpointSpec("CLEMENT OmniRoute", "http://127.0.0.1:9999")
    ) is EndpointKind.PROXY


def test_lm_studio_is_local() -> None:
    assert classify_endpoint(
        EndpointSpec("LM Studio", "http://127.0.0.1:1234/v1")
    ) is EndpointKind.LOCAL


def test_port_1234_loopback_is_local() -> None:
    assert classify_endpoint(
        EndpointSpec("Local inference", "http://localhost:1234/v1")
    ) is EndpointKind.LOCAL


def test_openrouter_is_cloud() -> None:
    assert classify_endpoint(
        EndpointSpec("OpenRouter", "https://openrouter.ai/api/v1")
    ) is EndpointKind.CLOUD


def test_unknown_loopback_is_not_assumed_local() -> None:
    assert classify_endpoint(
        EndpointSpec("Mystery proxy", "http://127.0.0.1:8080")
    ) is EndpointKind.UNKNOWN


def test_explicit_kind_used_after_hard_invariants() -> None:
    assert classify_endpoint(
        EndpointSpec("Private endpoint", "https://example.invalid/v1", EndpointKind.CLOUD)
    ) is EndpointKind.CLOUD


def test_antigravity_final_provider_is_cloud() -> None:
    assert classify_final_provider("antigravity") is EndpointKind.CLOUD


def test_lm_studio_final_provider_is_local() -> None:
    assert classify_final_provider("lm-studio") is EndpointKind.LOCAL


def test_unknown_final_provider_is_fail_closed() -> None:
    assert classify_final_provider("future-provider") is EndpointKind.UNKNOWN


def test_direct_local_accounting_is_unlimited() -> None:
    result = decide_accounting(
        endpoint_kind=EndpointKind.LOCAL,
        final_provider_kind=EndpointKind.LOCAL,
        technical_tokens=12345,
    )
    assert result.verdict == "PASS"
    assert result.billing_mode == "LOCAL_UNLIMITED"
    assert result.technical_tokens == 12345
    assert result.billable_tokens == 0
    assert result.quota_used == 0
    assert result.cost_eur == 0.0


def test_proxy_resolved_to_local_is_unlimited() -> None:
    result = decide_accounting(
        endpoint_kind=EndpointKind.PROXY,
        final_provider_kind=EndpointKind.LOCAL,
        technical_tokens=900,
    )
    assert result.billing_mode == "LOCAL_UNLIMITED"
    assert result.billable_tokens == 0


def test_proxy_resolved_to_cloud_is_metered() -> None:
    result = decide_accounting(
        endpoint_kind=EndpointKind.PROXY,
        final_provider_kind=EndpointKind.CLOUD,
        technical_tokens=900,
        reported_cost_eur=0.12,
    )
    assert result.verdict == "PASS"
    assert result.billing_mode == "METERED"
    assert result.billable_tokens == 900
    assert result.quota_used == 900
    assert result.cost_eur == 0.12


def test_unresolved_proxy_is_inconclusive() -> None:
    result = decide_accounting(
        endpoint_kind=EndpointKind.PROXY,
        final_provider_kind=None,
        technical_tokens=500,
    )
    assert result.verdict == "INCONCLUSIVE"
    assert result.billing_mode == "INCONCLUSIVE"
    assert result.billable_tokens == 0
    assert result.cost_eur is None


def test_negative_usage_is_clamped() -> None:
    result = decide_accounting(
        endpoint_kind=EndpointKind.LOCAL,
        final_provider_kind=EndpointKind.LOCAL,
        technical_tokens=-50,
    )
    assert result.technical_tokens == 0
