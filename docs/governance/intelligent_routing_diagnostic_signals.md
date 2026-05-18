# Intelligent Routing — Diagnostic-aware Routing Signals (v3.15.16, schema/projector)

> **Status:** Implemented as a read-only schema and deterministic
> projector. **No routing mutation, no campaign queue mutation, no
> strategy generation, no trading behaviour.**
>
> **Module:** [`reporting/intelligent_routing_diagnostic_signals.py`](../../reporting/intelligent_routing_diagnostic_signals.py)
> **Artefact:** `logs/intelligent_routing_diagnostic_signals/latest.json`
>
> **A20e unit anchor:** `u_v3_15_16_diagnostic_routing_signals_schema_001`
> **Phase:** v3.15.16 — Intelligent Routing Layer.
> **Authority class on merge:** `AUTO_ALLOWED` (LOW risk, `operator_gate = none`,
> `requires_operator_go = false`).

---

## 1. Purpose

Roadmap v6 §v3.15.16 mandates that campaign routing become
**behavior-aware** instead of preset-count-aware. The Roadmap v6
Addendum §9 v3.15.16 extends this with **diagnostic-aware** routing
signals (entropy / tail / criticality / network / quorum /
external-intelligence / dead-zone suppression / null-model /
barrier / resonance / adversarial / seismic / turbulence /
market-language).

This unit ships the **first** of the routing-related artefacts:
the schema and deterministic projector for the routing signals
themselves. The projector emits a closed-vocabulary description
of each signal family — what it advises, what it forbids, which
upstream input it depends on, what to do when that input is
missing — without performing any actual routing decision.

This is a **schema/projector foundation**. It exists so that a
future operator-approved unit can implement the actual deterministic
routing integration on top of a stable, pinned signal vocabulary.

---

## 2. Relationship to v3.15.16 Intelligent Routing Layer

The intelligent-routing build path is:

```
schema + projector  (this unit)
   ↓
deterministic routing-signal evaluation  (future unit, operator-go)
   ↓
campaign routing integration  (future unit, operator-go)
   ↓
routing-decision explanation reporter  (future unit, operator-go)
```

Today this unit only declares **what a signal looks like and what
it may / may not do**. The next units in the A20b decomposition
list (`u_v3_15_16_routing_explanation_reporter_001`,
`u_v3_15_16_routing_governance_doc_001`) consume the signal schema
once that ordering is unblocked by an A20a/A20b status update.

---

## 3. Schema / projector only

This unit ships:

- a closed `ROUTING_SIGNAL_FAMILY` vocabulary covering 14 Roadmap v6
  + Addendum 1 diagnostic families;
- closed vocabularies for `ROUTING_SIGNAL_STATUS`,
  `ROUTING_SIGNAL_DIRECTION`, `ROUTING_SIGNAL_SOURCE`,
  `ROUTING_SIGNAL_TARGET_LAYER`;
- one `RoutingDiagnosticSignal` record per family (today);
- a deterministic `RoutingSignalProjection` artefact at
  `logs/intelligent_routing_diagnostic_signals/latest.json`;
- a CLI with `--no-write`, `--status`, `--indent` flags following
  the same shape as the A20-series modules.

It does **not** ship:

- any actual routing-priority computation;
- any campaign queue update;
- any campaign execution change;
- any research-runtime behaviour change;
- any strategy-mapping output;
- any trading / paper / shadow / live behaviour.

---

## 4. No actual routing mutation is implemented yet

Every signal in this projection lands at `status="schema_only"`.
The `direction` field describes the *routing priority effect* the
signal would have once a future integration unit consumes it — it
is never a buy/sell direction and it is never executed.

The module's `projection_invariants` block pins this loudly on
every artefact:

- `no_routing_mutation = true`
- `no_campaign_queue_mutation = true`
- `no_strategy_generation = true`
- `no_research_runtime_change = true`

The status hard-codes to `schema_only` inside `_normalise_signal`
so that a future seed entry cannot drift its own status without
operator review. Per-signal status lifecycle is reserved for a
future operator-approved unit.

---

## 5. Diagnostics do not trade

Verbatim from Roadmap v6 Addendum §2 (Core Rule):

> *Diagnostics do not trade. A diagnostic may influence hypothesis
> priority, sampling, routing, evidence scoring, cooldown,
> confirmation, suppression or observability. A diagnostic may not
> directly create strategies, place trades, mutate live risk,
> allocate capital, bypass policy governance, or change frozen
> output contracts.*

This unit's `projection_invariants` block pins
`diagnostics_do_not_trade = true` on every emitted artefact.

Every emitted signal carries a **baseline** `forbidden_use[]`
list, prepended verbatim to every record:

- diagnostics may not place trades
- diagnostics may not mutate live risk
- diagnostics may not allocate capital
- diagnostics may not write to `live/**` or `paper/**` or `shadow/**` paths
- diagnostics may not write to `broker/**` or `agent/risk/**` or `agent/execution/**` paths
- diagnostics may not mutate `research/research_latest.json` or `research/strategy_matrix.csv`
- diagnostics may not be used as a direct trade trigger
- diagnostics may not bypass policy governance
- diagnostics may not bypass promotion gates
- diagnostics may not produce executable strategy code

Per-signal `extra_forbidden_use` entries are appended after the
baseline; duplicates are deterministically de-duplicated; order
is stable. Tests pin each of these properties.

---

## 6. External data is not alpha

Verbatim from Roadmap v6 Addendum §8.1 (External Intelligence
Intake Principle):

> *External / public data is not alpha. It is an unvalidated
> prior. Only QRE-validated, OOS-stable, cost-aware,
> execution-realistic, policy-approved behavior can become edge.*

The `projection_invariants` block pins
`external_data_is_not_alpha = true`. The
`rs_external_intelligence_routing` signal carries an explicit
`extra_forbidden_use` entry that diagnostics may not treat
external data as alpha and may not call paid feeds or vendor-alpha
endpoints.

---

## 7. Signal families included

Exactly 14 signal records ship today, one per family:

| `family` | `id` | `target_layer` | `direction` |
|---|---|---|---|
| `entropy` | `rs_entropy_information_density` | `campaign` | `deprioritize` |
| `tail` | `rs_tail_power_law` | `evidence` | `require_confirmation` |
| `criticality` | `rs_criticality_phase_transition` | `policy` | `deprioritize` |
| `network` | `rs_network_correlation_graph` | `campaign` | `suppress` |
| `quorum` | `rs_quorum_independent_evidence` | `evidence` | `require_confirmation` |
| `external_intelligence` | `rs_external_intelligence_routing` | `campaign` | `require_confirmation` |
| `dead_zone` | `rs_dead_zone_suppression` | `campaign` | `suppress` |
| `null_model` | `rs_null_model_falsification` | `evidence` | `deprioritize` |
| `barrier` | `rs_barrier_breakout_pressure` | `strategy_mapping` | `require_confirmation` |
| `resonance` | `rs_resonance_cycle_confluence` | `preset` | `require_confirmation` |
| `adversarial` | `rs_adversarial_market_behavior` | `evidence` | `require_confirmation` |
| `seismic` | `rs_seismic_shock_aftershock` | `campaign` | `suppress` |
| `turbulence` | `rs_turbulence_liquidity` | `policy` | `deprioritize` |
| `market_language` | `rs_market_language_grammar` | `hypothesis_discovery` | `neutral` |

Each signal record includes:

- five **bounded-prose effect** fields describing the routing
  effect on `expected_information_gain`, `dead_zone_risk`,
  `orthogonality`, `public_data_quality`, and
  `confirmation_requirement`. These are operator-readable
  explanatory hints, not authority-bearing decision fields. Tests
  pin them as non-empty, ≤200 chars, no newline, and free of
  authority-granting / trade / execute / order / capital-allocation
  semantics;
- a closed-vocab `family`, `source`, `target_layer`, `direction`,
  `status`;
- a non-empty `allowed_use` list;
- a `forbidden_use` list that carries the full baseline + any
  per-signal extras;
- a non-empty `required_inputs` list;
- a non-empty `missing_input_behavior` string.

---

## 8. Allowed uses

Per Roadmap v6 Addendum §2, a routing signal **may**:

- influence hypothesis priority;
- influence sampling strategy;
- influence routing prioritisation, deprioritisation, and
  suppression;
- influence evidence scoring (raise confirmation requirement);
- influence cooldown and dead-zone suppression;
- support observability and operator-readable explanation;
- support failure-to-action mapping (v3.15.20 scope).

Each signal record records the relevant subset of these uses in
its `allowed_use[]` list.

---

## 9. Forbidden uses

Per Roadmap v6 Addendum §2 and §8.1, a routing signal **must not**:

- create executable strategies directly;
- place trades, mutate live risk, allocate capital;
- bypass policy governance or promotion gates;
- change frozen output contracts;
- be used as a hidden ML / RL selector;
- be used as stochastic strategy mutation;
- be treated as alpha;
- call paid feeds or vendor-alpha endpoints;
- write to live / paper / shadow / trading / broker / risk /
  execution paths.

The baseline `forbidden_use[]` list pins these on every emitted
signal. Signal-family extras pin family-specific forbids on top
of the baseline (for example, the network signal's "may not
migrate capital across assets" extra; the language signal's "may
not mine candle patterns" extra).

---

## 10. Missing-input behaviour

Every signal declares its `required_inputs[]` list and a
`missing_input_behavior` string. The universal pattern is **fail
closed**: if any required input is missing, the signal status falls
to `suppressed` and the signal contributes neutral effect — no
authority is granted, no routing decision is made, no escalation
fires. The string explicitly describes the fall-back behaviour for
the specific signal.

This is consistent with the A20 fail-closed contract that the
roadmap-to-task pipeline already enforces upstream: ambiguity →
no positive action.

---

## 11. Sidecar artefact path

The projection is written to:

```
logs/intelligent_routing_diagnostic_signals/latest.json
```

The atomic-write helper refuses every path outside that directory
(`logs/intelligent_routing_diagnostic_signals/`). Frozen-contract
paths (`research/research_latest.json`,
`research/strategy_matrix.csv`) are rejected explicitly. Tests pin
the allowlist + frozen-contract refusal.

The artefact is gitignored under `logs/` and is produced on demand
by the CLI:

```sh
python -m reporting.intelligent_routing_diagnostic_signals          # writes + stdout
python -m reporting.intelligent_routing_diagnostic_signals --no-write
python -m reporting.intelligent_routing_diagnostic_signals --status
python -m reporting.intelligent_routing_diagnostic_signals --indent 2
```

The `--status` and `--no-write` modes never write any file.

---

## 12. Likely follow-up units

A20b's hand-encoded `_UNIT_SEED` already lists the two next
v3.15.16 follow-up units that depend on this schema:

- `u_v3_15_16_routing_explanation_reporter_001` — read-only
  routing-decision explanation reporter (LOW risk, AUTO_ALLOWED
  candidate, depends on this unit). Once this unit is merged,
  A20e will surface that follow-up as eligible after an A20b
  `status="merged"` update is staged for this unit.
- `u_v3_15_16_routing_governance_doc_001` — governance doc for
  the routing signals (LOW risk, AUTO_ALLOWED candidate). Closely
  related to this doc; may be folded in or kept separate per a
  future operator decision.

Beyond v3.15.16, the actual deterministic-routing integration
unit (consuming the signal schema to produce campaign-priority
projections) is **not** in A20b's seed today. Adding it requires
an A20b seed-data amendment under operator-go, plus the new
unit's own schema + module + tests + governance doc PR.

Until those follow-up units land, the signals shipped in this
artefact are advisory-only schema records: they describe the
intended routing-signal contract, they do not perform any routing
decision.

---

## 13. Authority pins carried forward

The `projection_invariants` block on every emitted artefact pins:

- `diagnostics_do_not_trade = true`
- `external_data_is_not_alpha = true`
- `read_only = true`
- `no_runtime_trading_authority = true`
- `no_campaign_queue_mutation = true`
- `no_strategy_generation = true`
- `no_routing_mutation = true`
- `no_research_runtime_change = true`
- `no_step5_runtime = true`
- `no_level6 = true`
- `no_production_merge_authority = true`
- `no_branch_creation = true`
- `no_pr_creation = true`
- `no_merge_or_deploy = true`
- `no_mutation_routes = true`
- `no_approval_buttons = true`
- `step5_implementation_allowed = false`

Step 5 implementation remains BLOCKED. Autonomy-ladder Level 6
remains permanently disabled. N5b Phase 4 production merge
remains permanently denied for ADE. ADE remains development
workflow automation only.

---

## 14. Test coverage

Pinned in [`tests/unit/test_intelligent_routing_diagnostic_signals.py`](../../tests/unit/test_intelligent_routing_diagnostic_signals.py):

- Closed vocabularies are exact.
- Schema field tuples are exact and ordered.
- All 14 Roadmap v6 + Addendum 1 signal families are represented.
- Every emitted signal has non-empty `allowed_use`,
  `forbidden_use`, `required_inputs`, and `missing_input_behavior`.
- Effect fields are bounded prose: non-empty, ≤200 chars, no
  newline, no authority-granting / trade / execute / order /
  capital-allocation phrases.
- `status="schema_only"` is hard-coded in `_normalise_signal`
  (a synthetic seed with a different status still emits
  `schema_only`).
- Baseline `forbidden_use` is prepended on every signal;
  per-signal extras are appended without replacing the baseline;
  duplicates are deterministically de-duplicated; order is
  stable across runs.
- All projection invariants pin at `True` (or `False` for
  `step5_implementation_allowed`).
- Deterministic byte-identical output for identical input with
  injected `generated_at_utc`.
- Atomic-write allowlist refuses every path outside
  `logs/intelligent_routing_diagnostic_signals/`, including
  frozen-contract paths.
- CLI `--no-write` and `--status` modes do not write any file.
- Module-source scan: stdlib only; no `subprocess`, no `socket`,
  no `urllib`, no `http`, no `requests`, no `gh`, no `git`, no
  `os.system`, no `eval(`, no `exec(`, no GitHub API host, no
  LLM endpoint, no `dashboard` / `automation` / `broker` /
  `agent.risk` / `agent.execution` / `research` / `live` /
  `paper` / `shadow` / `trading` / `reporting.execution_authority`
  / A20-pipeline import.

---

## 15. Cross-references

- [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md) — §v3.15.16 Intelligent Routing Layer.
- [`docs/roadmap/Roadmap v6 Addendum.md`](../roadmap/Roadmap%20v6%20Addendum.md) — §9 v3.15.16 diagnostic-aware routing.
- [`docs/governance/roadmap_task_catalog.md`](roadmap_task_catalog.md) — the A20 roadmap-to-task pipeline that selected this unit.
- [`docs/governance/ade_development_lane_doctrine.md`](ade_development_lane_doctrine.md) — ADE remains development workflow automation only.
- [`docs/governance/execution_authority.md`](execution_authority.md) — canonical agent execution authority policy (untouched by this PR).
