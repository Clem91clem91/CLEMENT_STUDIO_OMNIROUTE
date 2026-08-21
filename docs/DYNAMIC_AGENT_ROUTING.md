# Dynamic per-agent model routing

This workstream extends OmniRoute so the Orchestrator can request a model route per agent instead of using one global model choice.

## Inputs

Each `AgentRoutingRequest` may specify:

- required and preferred capabilities;
- context requirement;
- tool requirement;
- maximum latency;
- VRAM budget / currently available VRAM;
- local preference;
- cloud permission;
- deterministic scoring weights.

Each `ModelCandidate` carries machine-supplied metadata such as:

- model/provider identity;
- entry endpoint kind;
- resolved final-provider kind for proxies;
- health;
- quality score;
- latency;
- context limit;
- tool support;
- VRAM estimate;
- estimated cloud cost.

## Fail-closed rules

- unhealthy models are ineligible;
- missing required capabilities are ineligible;
- context/tool/latency/VRAM violations are ineligible;
- cloud is rejected when not allowed;
- an unresolved proxy final provider is rejected by default;
- ties are deterministic by model ID.

A proxy is not treated as local merely because its listener runs on localhost. Its final provider must be resolved as `LOCAL` before local semantics apply.

## Output

`AgentRoutePlan` contains:

- `primary_model_id`;
- ordered fallbacks;
- complete ranked candidate evidence;
- eligibility reasons;
- score components;
- PASS or INCONCLUSIVE verdict.

The router does not manage GPU reservations itself. Live reservation and preemption belong to `CLEMENT_STUDIO_GPU_MANAGER`; OmniRoute consumes resource-budget signals only.
