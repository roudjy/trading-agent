# Intelligent Routing — Diagnostic-aware Routing Signals (v3.15.16, schema + projector + governance)

> **Status:** Three v3.15.16 routing-layer units have merged on
> `main`. This doc covers all three. Each is **read-only by
> construction**. No campaign routing mutation. No campaign queue
> mutation. No strategy generation. No trading / paper / shadow /
> live behaviour.
>
> **Implemented modules:**
>
> * [`reporting/intelligent_routing_diagnostic_signals.py`](../../reporting/intelligent_routing_diagnostic_signals.py) — schema + projector for 14 routing-signal families (PR #250).
> * [`reporting/routing_explanation.py`](../../reporting/routing_explanation.py) — read-only routing-decision explanation reporter (PR #252).
>
> **Sidecar artefacts:**
>
> * `logs/intelligent_routing_diagnostic_signals/latest.json`
> * `logs/routing_explanation/latest.json`
>
> **A20e unit anchors:**
>
> * `u_v3_15_16_diagnostic_routing_signals_schema_001` — schema + projector (PR #250, merge SHA `fcb1abb`).
> * `u_v3_15_16_routing_explanation_reporter_001` — explanation reporter (PR #252, merge SHA `6f588a8`).
> * `u_v3_15_16_routing_governance_doc_001` — this governance doc (the unit this PR completes; A20b seed `expected_files = ("docs/governance/intelligent_routing_diagnostic_signals.md",)`, so the governance-doc unit extends the same file PR #250 created).
>
> **Phase:** v3.15.16 — Intelligent Routing Layer.
> **Authority class on each merge:** `AUTO_ALLOWED` (LOW risk, `operator_gate = none`, `requires_operator_go = false`).

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

## 12. v3.15.16 Routing-Layer Governance (governance-doc unit)

This section completes the third v3.15.16 routing-layer unit
selected by A20e: **`u_v3_15_16_routing_governance_doc_001`**.
The unit is **documentation only**. It adds no module, no test,
no runtime behaviour, no routing decision, no campaign queue
mutation. The A20b seed deliberately lists this unit's
`expected_files` as the same governance doc PR #250 created, so
the governance-doc unit extends the existing file rather than
creating a parallel one.

### 12.1 Relationship to v3.15.16 Intelligent Routing Layer

Roadmap v6 §v3.15.16 mandates **behaviour-aware** campaign
routing. Roadmap v6 Addendum §9 v3.15.16 extends this with
**diagnostic-aware** routing signals (entropy / tail /
criticality / network / quorum / external-intelligence / dead-zone
suppression / null-model / barrier / resonance / adversarial /
seismic / turbulence / market-language).

This document is the **governance anchor** for the v3.15.16
routing-layer build path. It pins the doctrine that every unit
in that path inherits: read-only, deterministic, diagnostic-driven
research-routing context only — never a trade signal, never a
campaign-queue mutator, never an executable strategy.

### 12.2 Currently implemented surface

Two implementation units have merged on `main` for v3.15.16:

| Unit | PR | Merge SHA | Module | Sidecar |
|---|---|---|---|---|
| `u_v3_15_16_diagnostic_routing_signals_schema_001` | [#250](https://github.com/roudjy/trading-agent/pull/250) | `fcb1abb` | [`reporting/intelligent_routing_diagnostic_signals.py`](../../reporting/intelligent_routing_diagnostic_signals.py) | `logs/intelligent_routing_diagnostic_signals/latest.json` |
| `u_v3_15_16_routing_explanation_reporter_001` | [#252](https://github.com/roudjy/trading-agent/pull/252) | `6f588a8` | [`reporting/routing_explanation.py`](../../reporting/routing_explanation.py) | `logs/routing_explanation/latest.json` |

Both are read-only deterministic projections. Each module's
status flip in A20b's `_UNIT_SEED` was applied as a small
follow-up queue-status PR (PR #251 and PR #253 respectively) so
the A20e selector advances past them. See
[`docs/governance/roadmap_task_catalog.md`](roadmap_task_catalog.md)
§11.1 Queue progression log.

#### 12.2.1 The signal schema (PR #250)

[`reporting/intelligent_routing_diagnostic_signals.py`](../../reporting/intelligent_routing_diagnostic_signals.py)
emits a closed-vocabulary `RoutingSignalProjection`. One
`RoutingDiagnosticSignal` record per Roadmap v6 + Addendum 1
diagnostic family. Each signal declares its `family`,
`target_layer`, `direction` (routing-priority effect; never a
buy/sell verb), `allowed_use[]`, `forbidden_use[]` (10-entry
doctrine baseline prepended on every signal), `required_inputs[]`,
and `missing_input_behavior` (fail-closed). Every signal lands
at `status="schema_only"` — the schema unit ships no actual
routing decision. See §3, §4, §5, §6, §7 of this doc for the
full schema-unit treatment.

#### 12.2.2 The explanation reporter (PR #252)

[`reporting/routing_explanation.py`](../../reporting/routing_explanation.py)
consumes the schema projection in-process and emits one
`RoutingExplanation` per signal. Each explanation carries three
deterministic reasons (`direction_advice`, family-specific,
`missing_input_fallback`) and three aggregate booleans
(`supports_exploration`, `suppresses_exploration`,
`requires_confirmation`) derived from a closed direction-aggregate
map. Every explanation row carries `read_only=True` and
`mutation_allowed=False`. The reporter never makes an actual
routing decision; the operator reads the explanations to
understand which diagnostic signal would advise what, and why.

### 12.3 Diagnostics do not trade

Verbatim from Roadmap v6 Addendum §2 (Core Rule):

> *Diagnostics do not trade. A diagnostic may influence hypothesis
> priority, sampling, routing, evidence scoring, cooldown,
> confirmation, suppression or observability. A diagnostic may not
> directly create strategies, place trades, mutate live risk,
> allocate capital, bypass policy governance, or change frozen
> output contracts.*

Both implemented modules pin `diagnostics_do_not_trade = True` in
their `projection_invariants` block on every artefact. Their
10-entry baseline `forbidden_use[]` list (see §9) enforces the
same posture on every emitted signal / explanation row.

### 12.4 External data is not alpha

Verbatim from Roadmap v6 Addendum §8.1:

> *External / public data is not alpha. It is an unvalidated
> prior. Only QRE-validated, OOS-stable, cost-aware,
> execution-realistic, policy-approved behavior can become edge.*

The `rs_external_intelligence_routing` signal and the matching
explanation row both pin `external_data_is_not_alpha = True`.
External-intelligence inputs may inform routing priority through
quality-gate verdicts; they may not be treated as a trade signal
or as alpha.

### 12.5 Diagnostic signals are read-only research-routing context

Every emitted signal carries:

- `status = "schema_only"` (hard-coded in `_normalise_signal`);
- a closed-vocab `direction` from
  `{prioritize, deprioritize, suppress, require_confirmation, neutral}`
  — never a buy/sell verb;
- the 10-entry baseline `forbidden_use[]` list (no trades, no
  live risk mutation, no capital allocation, no live/paper/shadow
  path writes, no broker/risk/execution writes, no frozen-contract
  mutation, no direct trade trigger, no policy-governance bypass,
  no promotion-gate bypass, no executable strategy code).

The signal projection is **research-routing context only**.

### 12.6 Routing explanations are operator-readable only

Every emitted explanation carries:

- `read_only = True`;
- `mutation_allowed = False`;
- one of five closed `status` values (`advisory_prioritize`,
  `advisory_deprioritize`, `advisory_suppress`,
  `advisory_require_confirmation`, `advisory_neutral`) — none of
  which authorises any action;
- three deterministic reasons sourced verbatim from upstream
  schema fields (no fuzzy parsing, no LLM, no hidden scoring).

The explanation projection is **operator-readable display only**.
The operator inspects it (via `--status` or by reading
`logs/routing_explanation/latest.json`); no other consumer is
authorised to take action on its content.

### 12.7 Allowed uses (governance-wide for v3.15.16)

The implemented routing-layer surface (signals + explanations)
may:

- **explain routing context** — describe why a diagnostic family
  would advise prioritise / deprioritise / suppress / require
  confirmation;
- **support future deterministic prioritisation** — a future
  operator-approved unit may consume the schema to produce a
  deterministic priority ranking for campaigns;
- **support future suppression / escalation / confirmation
  logic** — a future unit may use the closed-vocab directions to
  drive suppression cooldowns, confirmation-requirement
  escalation, or dead-zone routing avoidance;
- **support operator observability** — the operator can read both
  sidecar artefacts via the existing AAC aggregator or via the
  modules' own `--status` CLIs.

### 12.8 Forbidden uses (governance-wide for v3.15.16)

The implemented routing-layer surface **must not**:

- **direct routing mutation in this unit** — this governance-doc
  unit (and the two underlying implementation units) make no
  campaign-routing decision and no routing-policy update;
- **campaign enqueueing** — no write to
  `docs/development_work_queue/*.jsonl`, no mutation of any
  proposal queue, no campaign-queue admission decision;
- **strategy generation** — no executable strategy code, no
  free-form indicator generation, no stochastic strategy mutation,
  no genetic programming;
- **order placement** — no `broker/**` write, no `automation/live_gate.py`
  write, no order-placement code path of any kind;
- **paper / shadow / live activation** — no `paper/**`, `shadow/**`,
  `live/**`, or `trading/**` path created, modified, or imported;
- **broker / risk / execution changes** — no `broker/**`,
  `agent/risk/**`, or `agent/execution/**` modifications;
- **frozen-contract mutation** — neither
  `research/research_latest.json` nor
  `research/strategy_matrix.csv` is read, written, or referenced
  by any routing-layer module's atomic-write helper;
- **Step 5 activation** — `step5_implementation_allowed`
  remains `Final[bool] = False` everywhere in the routing layer;
- **Level 6 activation** — autonomy-ladder Level 6 stays
  permanently disabled per ADR-015 §Doctrine 1;
- **production-merge authority** — no `gh pr merge` invocation,
  no `--admin`, no force push, no hook bypass anywhere in any
  routing-layer module.

### 12.9 Sidecar artefact paths (both implemented modules)

| Module | Artefact path |
|---|---|
| `reporting.intelligent_routing_diagnostic_signals` | `logs/intelligent_routing_diagnostic_signals/latest.json` |
| `reporting.routing_explanation` | `logs/routing_explanation/latest.json` |

Both artefacts are gitignored under `logs/` and produced on demand
by their respective module CLIs (`python -m reporting.<module>`).
Each module's atomic-write helper refuses every path outside its
own `logs/<module>/` directory; frozen-contract paths are
explicitly rejected.

### 12.10 What is explicitly NOT implemented yet

The v3.15.16 routing layer is intentionally narrow today. The
following are out of scope for the three currently-merged units
and will require **separate operator-approved units** before any
runtime behaviour change:

- **Actual deterministic routing policy** — a module that
  consumes the schema projection and produces a campaign-priority
  ranking does not exist in A20b's seed today. Adding it requires
  an A20b seed-data amendment under operator-go, plus the new
  unit's own schema + module + tests + governance doc PR.
- **Campaign queue integration** — the existing campaign queues
  (`reporting/development_work_queue.py`, A18a generated lane)
  are unchanged. No routing-layer module imports or writes to
  any queue.
- **AAC / dashboard extension for these specific v3.15.16
  signals** — the AAC aggregator was extended to surface the
  A20 roadmap-to-task pipeline (per A20d), but it has not been
  extended to surface either the
  `intelligent_routing_diagnostic_signals` or `routing_explanation`
  artefacts as work-item rows. Adding them would require an
  AAC aggregator cardinality change under operator-go (same
  pattern A20d used).
- **A20 status auto-advancement** — A20 projections are
  deterministic / read-only and do not auto-discover merged PRs.
  Each merged unit's `status` flip in A20b's `_UNIT_SEED`
  continues to be applied as a small follow-up `chore/a20-*`
  queue-status PR (see PR #251 and PR #253 for the pattern).

### 12.11 Future follow-up units likely required

After this governance-doc unit merges, the deterministic A20e
selector will pick the next eligible unit (likely
`u_v3_15_17_sampling_plan_reporter_001` from v3.15.17 — the next
phase). Independently of phase progression, the following
v3.15.16 routing-layer follow-ups will need to be added to A20b's
seed under operator-go before any actual routing behaviour
emerges:

1. **Deterministic routing-policy integration unit** — consumes
   the schema's closed-vocab signals + the explanation reporter's
   aggregate booleans, and produces a deterministic campaign-
   priority projection. Read-only by construction. No
   campaign-queue mutation.
2. **Read-only routing-summary reporter** (optional) — if the
   queue selects it, this would aggregate per-campaign routing
   verdicts across families into a single operator-readable
   summary. Read-only.
3. **Queue-status update after this doc merges** — the small
   `chore/a20-mark-routing-governance-doc-merged` PR that flips
   this unit's `status` from `"not_started"` to `"merged"` in
   A20b's `_UNIT_SEED` (same pattern as PR #251 and PR #253).
   After that lands, A20e advances to the next phase.

---

## 13. Likely follow-up units (schema-unit perspective, retained from PR #250)

A20b's hand-encoded `_UNIT_SEED` lists the two next v3.15.16
follow-up units that depend on the schema unit:

- `u_v3_15_16_routing_explanation_reporter_001` — **merged via
  PR #252** (see §12.2.2 above).
- `u_v3_15_16_routing_governance_doc_001` — **this unit**
  (extends the existing governance doc with §12; see §12).

Beyond v3.15.16, the actual deterministic-routing integration
unit (consuming the signal schema to produce campaign-priority
projections) is **not** in A20b's seed today (see §12.11).

Until those further follow-up units land, the signals shipped in
the schema artefact and the explanations shipped in the reporter
artefact are advisory-only records: they describe and explain the
intended routing-signal contract; they do not perform any routing
decision.

---

## 14. Authority pins carried forward

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

## 15. Test coverage

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

## 16. Cross-references

- [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md) — §v3.15.16 Intelligent Routing Layer.
- [`docs/roadmap/Roadmap v6 Addendum.md`](../roadmap/Roadmap%20v6%20Addendum.md) — §9 v3.15.16 diagnostic-aware routing.
- [`docs/governance/roadmap_task_catalog.md`](roadmap_task_catalog.md) — the A20 roadmap-to-task pipeline that selected this unit.
- [`docs/governance/ade_development_lane_doctrine.md`](ade_development_lane_doctrine.md) — ADE remains development workflow automation only.
- [`docs/governance/execution_authority.md`](execution_authority.md) — canonical agent execution authority policy (untouched by this PR).
