from __future__ import annotations

import io

from clement_omniroute.certifier import certify_endpoints, probe_endpoint, render_markdown
from clement_omniroute.core import EndpointSpec


class Response:
    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._payload


def good_opener(request, timeout=5.0):
    url = request.full_url
    if "1234" in url:
        return Response(b'{"data":[{"id":"local-a"},{"id":"local-b"}]}')
    if "20128" in url:
        return Response(b'{"data":[{"id":"route-a"}]}')
    return Response(b'{"data":[]}')


def failing_openrouter(request, timeout=5.0):
    if "openrouter" in request.full_url:
        raise OSError("offline")
    return good_opener(request, timeout)


def test_probe_models_endpoint_and_count():
    result = probe_endpoint(EndpointSpec("LM Studio", "http://127.0.0.1:1234/v1"), opener=good_opener)
    assert result.kind == "LOCAL"
    assert result.models_endpoint.endswith("/v1/models")
    assert result.model_count == 2
    assert result.reachable is True


def test_certification_pass_when_all_endpoints_reachable():
    result = certify_endpoints(opener=good_opener)
    assert result.verdict == "PASS"
    assert result.invariants["omniroute_is_proxy"] is True
    assert result.invariants["omniroute_is_not_local"] is True
    assert result.invariants["lm_studio_is_local"] is True
    assert result.invariants["openrouter_is_cloud"] is True


def test_openrouter_offline_is_partial_not_false_local_failure():
    result = certify_endpoints(opener=failing_openrouter)
    assert result.verdict == "PARTIAL"
    assert "openrouter_reachability_not_proven" in result.reasons
    assert result.invariants["omniroute_is_proxy"] is True


def test_markdown_contains_invariants():
    result = certify_endpoints(opener=good_opener)
    report = render_markdown(result)
    assert "OmniRoute Certification" in report
    assert "`omniroute_is_proxy`" in report
    assert "**PASS**" in report
