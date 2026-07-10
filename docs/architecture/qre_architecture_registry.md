# QRE Architecture Registry

## Purpose

`docs/architecture/qre_architecture_registry.v1.json` is the machine-readable registry of known QRE architecture surfaces. It records each surface's role, maturity level, ownership claims, artifacts, allowed and forbidden outputs, provider scope, authority flags, and operator-decision status.

PR 1 was classification-only. PR 2 turns the registry into a static closed-world audit gate: unknown or duplicate architecture claims become explicit audit failures, while runtime behavior remains unchanged.

## Safety Scope

The registry does not run research, create candidates, create strategies, create presets, create campaigns, run screening, mutate frozen outputs, grant synthesis authority, grant shadow/paper/live authority, or grant broker/risk/order/capital authority.

Frozen legacy outputs remain protected:

```text
research/research_latest.json
research/strategy_matrix.csv
```

## Roles

```text
canonical_loop
provider_adapter
legacy_surface
observability_only
fixture_only
governance_only
```

- `canonical_loop`: owns provider-agnostic contract semantics or the canonical loop once explicitly settled.
- `provider_adapter`: bridges provider-specific data into canonical contracts without owning canonical semantics.
- `legacy_surface`: protected historical or reporting path that must not silently become modern canonical ownership.
- `observability_only`: read-only digest, dashboard, report, or operator summary surface.
- `fixture_only`: test or smoke fixture that may prove behavior but cannot count as empirical research evidence.
- `governance_only`: policy, audit, readiness, roadmap, or operator-trust surface with no runtime research authority.

## Maturity Levels

```text
scaffold
working_capability
operator_trusted_capability
synthesis_consideration
shadow_ready
paper_ready
live_ready
blocked
reference_only
```

Addendum 4 maturity remains gated. A working loop is not automatically operator-trusted, an operator-trusted loop is not automatically a strategy engine, and a strategy engine is not automatically deployment-ready.

## Authority Flags

Every entry must explicitly set all authority flags:

```text
audit_only
classification_only
runtime_behavior_changed
creates_candidates
creates_strategies
creates_presets
creates_campaigns
runs_screening
runs_validation
strategy_synthesis_authority
trading_authority
shadow_authority
paper_authority
live_authority
broker_authority
risk_authority
order_authority
capital_allocation_authority
dashboard_mutation_authority
empirical_evidence_authority
research_object_producer_authority
```

PR 1 keeps runtime, synthesis, trading, shadow, paper, live, broker, risk, order, capital allocation, and dashboard mutation authority disabled.

## Registered Surfaces

The initial v1 registry classifies:

```text
canonical_contract_vocabulary
tiingo_hypothesis_candidate_research_mini_loop
daily_status_digest_observability
run_research_registry_matrix
alpha_discovery_generated_lifecycle
empirical_research_flywheel_v7_1
bounded_strategy_synthesis_readiness
funnel_architecture_audit
test_smoke_fixture_paths
canonical_funnel_verification
```

Operator-decision entries are explicit in the JSON. PR 2 must respect them rather than silently resolving irreversible ownership or maturity decisions.

## Operator Decision Closure

PR 5 settles or conservatively bounds the remaining operator-decision surfaces:

- `run_research_registry_matrix` is settled as a protected legacy compatibility
  surface. It owns no modern canonical objects, has no research-object producer
  authority, and mutation of `research/research_latest.json` or
  `research/strategy_matrix.csv` remains separately forbidden.
- `alpha_discovery_generated_lifecycle` remains explicitly bounded as
  governance-only until canonical bridge ownership is separately proven. It may
  consume canonical contracts and emit bridge/readiness read models only; it has
  no independent canonical loop ownership or synthesis execution authority.
- `empirical_research_flywheel_v7_1` is settled as an operator-trusted
  governance read model for the v7.1 trust slice only. It preserves
  trust/evidence artifacts but has no independent canonical loop, deployment,
  paper, shadow, live, or broker authority.
- `bounded_strategy_synthesis_readiness` remains explicitly bounded as
  governance-only synthesis consideration. It requires an operator decision for
  any future escalation and grants no executable synthesis, shadow, paper, live,
  broker, risk, order, or capital authority.

`canonical_funnel_verification` is registered as governance-only static
fixture verification. It consumes canonical object names to prove route order
but owns no canonical semantics, creates no research objects, and grants no
execution or synthesis authority.

## Validation

`packages/qre_research/architecture_registry.py` validates:

- schema version and registry kind
- required entry fields
- known role and maturity vocabularies
- explicit known authority flags
- duplicate entry ids
- observability-only entries do not have research object producer authority
- fixture-only entries do not have empirical evidence authority
- provider adapters do not own canonical object semantics
- legacy surfaces do not silently own modern canonical semantics
- high-risk maturity claims require explicit operator-decision status
- frozen legacy outputs are identified as protected

## Closed-World Audit Gate

`tools/qre_funnel_architecture_audit.py` includes a `closed_world_audit` section backed by `packages/qre_research.architecture_registry`.

The gate fails static validation for:

- unregistered producer modules
- unregistered artifact paths
- unknown canonical object owners
- duplicate canonical object owners
- observability-only surfaces with research object producer authority
- provider adapters that claim canonical semantics directly
- fixture-only surfaces that claim empirical evidence authority
- legacy surfaces that claim modern canonical ownership without `operator_decision_required`
- unknown maturity claims
- unknown authority flags

This remains audit-only. It does not run research, create candidates, create strategies, create campaigns, run screening, mutate frozen outputs, grant strategy synthesis authority, grant shadow/paper/live authority, or grant broker/risk/order/capital authority.

## Addendum 4 Maturity Gate

`packages/qre_research/maturity_gate.py` makes the Addendum 4 maturity doctrine machine-checkable. The registry JSON carries `addendum_4_maturity_policy`, including the evidence requirements for operator-trusted claims:

```text
persistent_artifacts
explainable_decisions
repeatable_outputs
evidence_backed_disposition
policy_auditable_lineage
contradiction_visibility
failure_traceability
operator_verifiable_summary
```

The gate enforces that working capability does not imply strategy or deployment authority, operator-trusted capability is slice-specific and evidence-backed, synthesis consideration remains non-executable, shadow readiness requires an explicit default-disabled gate, and paper/live readiness remain blocked in this architecture-control-plane sequence.
