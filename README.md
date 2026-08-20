# CLEMENT_STUDIO_OMNIROUTE

P0-03 - certification deterministe d'OmniRoute pour CLEMENT STUDIO.

## Objectifs

- classifier sans ambiguite les endpoints `LOCAL`, `PROXY`, `CLOUD` ;
- garantir que `http://localhost:20128/v1` (OmniRoute) reste `PROXY` ;
- garantir que `http://localhost:1234/v1` (LM Studio) reste `LOCAL` ;
- garantir qu'OpenRouter reste `CLOUD` ;
- baser la comptabilite sur le fournisseur final reel, jamais uniquement sur le point d'entree ;
- conserver les tokens techniques tout en mettant les tokens facturables a zero pour un fournisseur final local ;
- rendre un verdict `INCONCLUSIVE` si un proxy ne revele pas son fournisseur final.

## Regles de comptabilite

| Endpoint d'entree | Fournisseur final | Billing mode | Billable tokens |
|---|---|---|---:|
| LOCAL | LOCAL | LOCAL_UNLIMITED | 0 |
| PROXY | LOCAL | LOCAL_UNLIMITED | 0 |
| PROXY | CLOUD | METERED | technical_tokens |
| PROXY | inconnu | INCONCLUSIVE | 0 tant que non resolu |
| CLOUD | CLOUD | METERED | technical_tokens |

## Certification cible

La campagne Shadow doit couvrir : health, models, routing, latency, tokens, fallback, failover, tools, context et errors, puis produire `OMNIROUTE_CERTIFICATION.md`.

## Developpement

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

Aucun merge, tag ou release n'est implique par cette branche feature.
