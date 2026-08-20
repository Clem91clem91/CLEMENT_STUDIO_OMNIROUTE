# CLEMENT_STUDIO_OMNIROUTE

P0-03 - OmniRoute certification and final-provider accounting.

## Invariants

- `http://localhost:20128` / OmniRoute is **PROXY**, never LOCAL.
- `http://localhost:1234` / LM Studio is **LOCAL**.
- OpenRouter is **CLOUD**.
- Unknown loopback endpoints are **UNKNOWN**, never assumed free/local.
- Billing is derived from the **resolved final provider**, not the ingress proxy.
- A proxy route without a resolved final provider is `INCONCLUSIVE`.
- A final LOCAL provider keeps technical usage but sets billable tokens/quota/cost to zero.

## Certification layers

1. `core.py` - endpoint classification and final-provider accounting.
2. `certifier.py` - live `/v1/models` reachability, latency and model-count probes.
3. `routing.py` - route attempts, fallback/failover evidence, tokens, tools, context and errors.
4. `scripts/certify_shadow.py` - live Shadow report generator.
5. `scripts/certify_shadow.ps1` - Windows PowerShell 5.1 wrapper.

The live report is written under `artifacts/OMNIROUTE_CERTIFICATION.md` and remains outside Git tracking.

## Shadow

```powershell
cd "C:\Users\Shadow\Documents\CLEMENT_STUDIO\04_TOOLS\CLEMENT_STUDIO_OMNIROUTE"
git pull --ff-only origin feat/p0-omniroute-certification
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\certify_shadow.ps1"
```

No merge, tag or release is performed by the certification scripts.
