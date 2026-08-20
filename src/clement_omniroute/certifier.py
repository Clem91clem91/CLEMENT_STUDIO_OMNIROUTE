from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .core import EndpointKind, EndpointSpec, classify_endpoint


@dataclass(frozen=True)
class ProbeResult:
    name: str
    base_url: str
    kind: str
    reachable: bool
    status_code: int | None
    latency_ms: float | None
    models_endpoint: str
    model_count: int | None
    error: str | None


@dataclass(frozen=True)
class CertificationResult:
    generated_at: str
    verdict: str
    probes: tuple[ProbeResult, ...]
    invariants: dict[str, bool]
    reasons: tuple[str, ...]


def _models_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base + "/models"
    return base + "/v1/models"


def probe_endpoint(
    spec: EndpointSpec,
    *,
    timeout: float = 5.0,
    headers: dict[str, str] | None = None,
    opener: Callable[..., object] = urlopen,
) -> ProbeResult:
    kind = classify_endpoint(spec)
    url = _models_url(spec.base_url)
    request = Request(url, headers=headers or {})
    started = time.perf_counter()
    status: int | None = None
    body = b""
    error: str | None = None
    reachable = False

    try:
        with opener(request, timeout=timeout) as response:  # type: ignore[misc]
            status = int(getattr(response, "status", 200))
            body = response.read()
            reachable = 200 <= status < 500
    except HTTPError as exc:
        status = int(exc.code)
        reachable = 400 <= status < 500
        error = f"HTTP {status}: {exc.reason}"
        try:
            body = exc.read()
        except Exception:
            body = b""
    except (URLError, TimeoutError, OSError) as exc:
        error = str(exc)

    latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
    model_count: int | None = None
    if body:
        try:
            payload = json.loads(body.decode("utf-8"))
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, list):
                model_count = len(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

    return ProbeResult(
        name=spec.name,
        base_url=spec.base_url,
        kind=kind.value,
        reachable=reachable,
        status_code=status,
        latency_ms=latency_ms,
        models_endpoint=url,
        model_count=model_count,
        error=error,
    )


def certify_endpoints(
    *,
    lm_studio_url: str = "http://127.0.0.1:1234",
    omniroute_url: str = "http://127.0.0.1:20128",
    openrouter_url: str = "https://openrouter.ai/api",
    openrouter_api_key: str | None = None,
    timeout: float = 5.0,
    opener: Callable[..., object] = urlopen,
) -> CertificationResult:
    specs = (
        EndpointSpec("LM Studio", lm_studio_url),
        EndpointSpec("OmniRoute", omniroute_url),
        EndpointSpec("OpenRouter", openrouter_url),
    )
    headers_by_name: dict[str, dict[str, str]] = {
        "OpenRouter": ({"Authorization": f"Bearer {openrouter_api_key}"} if openrouter_api_key else {}),
    }

    probes = tuple(
        probe_endpoint(
            spec,
            timeout=timeout,
            headers=headers_by_name.get(spec.name),
            opener=opener,
        )
        for spec in specs
    )
    by_name = {probe.name: probe for probe in probes}
    invariants = {
        "lm_studio_is_local": by_name["LM Studio"].kind == EndpointKind.LOCAL.value,
        "omniroute_is_proxy": by_name["OmniRoute"].kind == EndpointKind.PROXY.value,
        "omniroute_is_not_local": by_name["OmniRoute"].kind != EndpointKind.LOCAL.value,
        "openrouter_is_cloud": by_name["OpenRouter"].kind == EndpointKind.CLOUD.value,
        "lm_studio_reachable": by_name["LM Studio"].reachable,
        "omniroute_reachable": by_name["OmniRoute"].reachable,
    }

    reasons: list[str] = []
    required = (
        "lm_studio_is_local",
        "omniroute_is_proxy",
        "omniroute_is_not_local",
        "openrouter_is_cloud",
        "lm_studio_reachable",
        "omniroute_reachable",
    )
    if all(invariants[name] for name in required):
        verdict = "PASS"
    else:
        verdict = "FAIL"
        reasons.extend(name for name in required if not invariants[name])

    if not by_name["OpenRouter"].reachable:
        reasons.append("openrouter_reachability_not_proven")
        if verdict == "PASS":
            verdict = "PARTIAL"

    return CertificationResult(
        generated_at=datetime.now(timezone.utc).isoformat(),
        verdict=verdict,
        probes=probes,
        invariants=invariants,
        reasons=tuple(reasons),
    )


def render_markdown(result: CertificationResult) -> str:
    lines = [
        "# OmniRoute Certification",
        "",
        f"Generated: `{result.generated_at}`",
        f"Verdict: **{result.verdict}**",
        "",
        "## Endpoint probes",
        "",
        "| Endpoint | Kind | Reachable | HTTP | Latency ms | Models |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for probe in result.probes:
        lines.append(
            f"| {probe.name} | {probe.kind} | {str(probe.reachable).lower()} | "
            f"{probe.status_code if probe.status_code is not None else '-'} | "
            f"{probe.latency_ms if probe.latency_ms is not None else '-'} | "
            f"{probe.model_count if probe.model_count is not None else '-'} |"
        )
    lines.extend(["", "## Invariants", ""])
    for name, value in sorted(result.invariants.items()):
        lines.append(f"- [{'x' if value else ' '}] `{name}`")
    if result.reasons:
        lines.extend(["", "## Reasons", ""])
        lines.extend(f"- {reason}" for reason in result.reasons)
    return "\n".join(lines) + "\n"


def write_report(result: CertificationResult, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(result), encoding="utf-8")
    return target


def to_json(result: CertificationResult) -> str:
    return json.dumps(asdict(result), indent=2, ensure_ascii=False)
