# QRE Roadmap v6 + Addendum — ADE Operating Manual

## 1\. Purpose

This document translates **Roadmap v6** and the **Roadmap v6 Addendum** into an operational manual for ADE/Claude-driven roadmap execution.

It does **not** replace Roadmap v6.
It does **not** replace the Addendum.
It does **not** grant trading, broker, capital-allocation, live-risk, paper, shadow, or execution authority.

Its purpose is to make QRE roadmap execution:

* structured
* phase-gated
* deterministic
* auditable
* operator-controllable
* CI-governed
* architecture-safe
* resistant to scope drift

The central operating rule is:

```text
ADE governs how development work is proposed, classified, executed, tested, reviewed, merged, and reported.
QRE Roadmap v6 governs what product functionality is built.
The Addendum extends QRE research intelligence with diagnostics and public-data intake.
Diagnostics do not trade.
```

\---

## 2\. Canonical source hierarchy

When documents appear to overlap, use this hierarchy.

### 2.1 Product roadmap source

```text
Roadmap v6
```

Roadmap v6 is the canonical QRE product roadmap. It defines the semantic maturity sequence:

```text
v3.x — Research Intelligence \& Autonomous Discovery
v4.x — Shadow Trading \& Real-Time Behavioral Validation
v5.x — Paper Trading \& Simulated Capital Deployment
v6.x — Live Trading \& Capital Allocation
```

Roadmap v6 also defines the strategic shift from a deterministic research execution system toward an autonomous market behavior research system.

### 2.2 Product-roadmap extension source

```text
Roadmap v6 Addendum — Mechanistic Behavior Diagnostics \& External Intelligence Intake
```

The Addendum extends Roadmap v6 with:

* External Intelligence Intake
* Mechanistic Behavior Diagnostics Layer
* Behavior Diagnostics Library / Research Diagnostics Primitives
* diagnostic-aware routing
* diagnostic-aware sampling
* diagnostic-aware observability
* diagnostic-seeded hypothesis discovery
* deterministic failure-to-action mappings

The Addendum does not alter the Roadmap v6 phase order.

### 2.3 Development-governance source

```text
Autonomous Development Track
```

The Autonomous Development Track governs ADE/Claude development safety:

* execution authority classification
* approval gates
* PR/CI workflow
* proposal queue behavior
* read-only operator surfaces
* development readiness
* separation between development authority and trading/research execution authority

It is not QRE product functionality.

### 2.4 Repository operating guardrails

```text
AGENTS.md
CLAUDE.md
repo governance docs
```

These define operational constraints such as:

* no direct work on `main`
* no force pushes
* no hook bypass
* no test weakening
* PR lifecycle required
* `registry.py` remains strategy-registration source of truth
* `research/run\_research.py` remains central orchestrator
* `research\_latest.json` and `strategy\_matrix.csv` remain frozen public contracts

\---

## 3\. Mandatory domain split

The following distinction is non-negotiable.

|Domain|Meaning|Examples|Authority source|
|-|-|-|-|
|ADE|Development governance and operator control|classify work, expose queue state, create PRs, run CI, report status|Autonomous Development Track|
|QRE Feature Build|Product roadmap implementation|routing, sampling, diagnostics, hypothesis discovery, evidence policy|Roadmap v6 + Addendum|
|Trading/research execution|Running strategies, campaigns, orders, paper/shadow/live behavior, broker/risk/capital logic|live broker calls, order placement, risk envelope, capital allocation|Explicit future QRE phase only|

ADE may govern QRE development work.
ADE may not become trading execution authority.
QRE diagnostics may influence research prioritization.
QRE diagnostics may not directly trade.

\---

## 4\. Current strategic state

Roadmap v6 defines the current QRE as a:

```text
Deterministic Quant Research Operating System
```

The already-solved or substantially present areas include:

* deterministic orchestration
* campaign policy governance
* funnel semantics
* exploratory screening
* promotion separation
* evidence ledgering
* economics-aware reporting
* stop-condition governance
* dead-zone intelligence
* autonomous queue discipline
* candidate lifecycle governance
* observability surfaces
* paper validation infrastructure primitives

The next bottleneck is:

```text
upstream research intelligence
```

Specifically:

* hypothesis quality
* behavior-level exploration
* orthogonal discovery
* opportunity prioritization
* intelligent exploration ordering
* mechanistic reasoning

Therefore, the near-term QRE Feature Build Track should remain focused on v3.x research intelligence before any premature jump to shadow, paper, or live functionality.

\---

## 5\. Target architecture

### 5.1 Roadmap v6 architecture

```text
Market Behavior Layer
↓
Hypothesis Discovery Layer
↓
Strategy Layer
↓
Preset Layer
↓
Campaign Layer
↓
Funnel Layer
↓
Evidence Layer
↓
Policy Layer
↓
Shadow / Paper / Live
```

### 5.2 Addendum-extended architecture

```text
External Intelligence Intake
↓
Mechanistic Behavior Diagnostics Layer
↓
Market Behavior Layer
↓
Hypothesis Discovery Layer
↓
Strategy Mapping
↓
Preset Layer
↓
Campaign Layer
↓
Funnel Layer
↓
Evidence Layer
↓
Policy Layer
↓
Shadow / Paper / Live
```

### 5.3 Key architectural interpretation

External/public data is an **unvalidated prior**.
Diagnostics are **research primitives**.
Market behaviors are **research objects**.
Strategies and presets are **mappings**.
Campaigns are **research execution units**.
Evidence and policy govern **promotion, rejection, cooldown, and follow-up**.
Shadow/paper/live stages validate increasingly realistic deployment behavior.

\---

## 6\. Global hard invariants

These constraints apply to all roadmap work unless an explicit future roadmap phase and operator approval state otherwise.

### 6.1 Source-of-truth invariants

```text
registry.py = strategy registration source of truth
research/run\_research.py = central research orchestrator
artifacts = source of truth for generated research state
frontend = UI only
backend = control surface
engine/research modules = research logic
```

### 6.2 Frozen contracts

Do not mutate the schema or semantics of:

```text
research\_latest.json
strategy\_matrix.csv
```

New information must go into:

* sidecar artifacts
* versioned diagnostic artifacts
* read-only reports
* control-surface endpoints
* dashboards that consume sidecars without changing frozen contracts

### 6.3 Layering constraints

Do not place:

* business logic in the frontend
* research logic in API/dashboard code
* orchestration policy inside strategies
* hidden mutable state in UI
* direct trading behavior inside diagnostics
* broker/order/risk behavior inside research intelligence phases

### 6.4 Reproducibility constraints

All research-intelligence additions must be:

* deterministic
* inspectable
* artifact-driven
* versioned where appropriate
* testable
* reproducible
* non-black-box

\---

## 7\. Core Addendum principle: diagnostics do not trade

This principle must be included in every phase prompt involving diagnostics.

```text
Diagnostics do not trade.
```

A diagnostic may influence:

* hypothesis priority
* campaign routing
* sampling strategy
* evidence scoring
* cooldown
* confirmation requirements
* suppression
* escalation
* observability
* failure-action mapping

A diagnostic may not:

* create executable strategies directly
* place trades
* mutate live risk
* allocate capital
* bypass policy governance
* bypass promotion gates
* change frozen output contracts
* become a hidden ML/RL selector
* become stochastic strategy mutation

\---

## 8\. Behavior Diagnostics Library

Do not call this a “Core Math Engine.”

Use one of:

```text
Behavior Diagnostics Library
Research Diagnostics Primitives
```

Reason: “Core Math Engine” suggests a central strategy/execution engine and risks architecture drift. The intended role is narrower:

* pure deterministic diagnostic primitives
* artifact-producing behavior analysis
* no strategy generation
* no execution behavior
* no hidden state

### 8.1 Diagnostic families

The Addendum introduces or reserves diagnostic families for:

* tails / power laws
* entropy / information density
* criticality / phase transitions
* barrier pressure / breakout probability proxies
* resonance / cycle confluence
* null models / Brownian/random-walk/surrogate tests
* networks / correlation graph / contagion
* adversarial market behavior
* control stability
* seismic shocks and aftershocks
* liquidity turbulence
* independent evidence quorum
* market language diagnostics

### 8.2 Sidecar artifact principle

Diagnostic outputs should be written to versioned sidecars, for example:

```text
artifacts/diagnostics/behavior\_diagnostics\_latest.v1.json
artifacts/diagnostics/diagnostic\_quality\_latest.v1.json
artifacts/diagnostics/diagnostic\_hypothesis\_seeds\_latest.v1.json
artifacts/external\_intelligence/external\_intelligence\_latest.v1.json
artifacts/external\_intelligence/public\_data\_quality\_latest.v1.json
artifacts/external\_intelligence/public\_hypothesis\_seed\_candidates\_latest.v1.json
```

Do not mutate:

```text
research\_latest.json
strategy\_matrix.csv
```

\---

## 9\. External Intelligence Intake

External/public data is not alpha.

It is an unvalidated prior.

Only QRE-validated, OOS-stable, cost-aware, execution-realistic, policy-approved behavior can become edge.

### 9.1 Allowed for now

* public/free market data
* public/free macro data
* public/free filings/event data
* repo-resident manifests
* small seed snapshots where license permits
* derived diagnostic artifacts
* reproducible fetch instructions

### 9.2 Not allowed for now

* paid data feeds
* vendor alpha
* commercial signal libraries
* private alternative-data vendors
* non-reproducible scraping
* social/NLP-heavy pipelines before quality gates exist

### 9.3 Required source manifest fields

Every source manifest should include:

```text
source\_id
source\_type
access\_method
expected\_latency
expected\_freshness
asset\_coverage
timeframe\_coverage
allowed\_use
known\_limitations
license\_terms\_reference
reproducibility\_method
quality\_gates
```

### 9.4 Required public-data quality gates

* freshness check
* missing data check
* timestamp monotonicity
* duplicate bar check
* outlier check
* coverage check
* source-agreement check where possible
* license/terms metadata present

No hypothesis seed should be promoted from public data without passing source quality checks.

\---

## 10\. Authority matrix

### 10.1 Generally allowed within scoped roadmap work

Allowed when within active phase scope and normal repo governance:

```text
read-only reporting
sidecar artifacts
deterministic classifiers
diagnostic primitives
quality checks
tests
documentation
operator-facing summaries
non-breaking observability
bounded hashes/status fields
sample decision checks
```

### 10.2 Requires operator approval or explicit governance phase

```text
canonical governance edits
roadmap status flips
protected-path changes
approval semantics changes
HIGH-risk policy behavior
UNKNOWN-risk changes
frozen contract changes
changes to .claude/\*\*
dashboard mutation routes
approval-inbox mutation behavior
```

### 10.3 Permanently denied unless explicitly unlocked by future roadmap and operator approval

```text
broker/order placement changes
live capital allocation
execution-layer mutation
risk-engine mutation
hidden ML/RL selector
genetic programming
stochastic strategy mutation
automatic indicator invention
random preset switching
PID position sizing during research phase
frontend business logic
research\_latest.json schema mutation
strategy\_matrix.csv schema mutation
test weakening
CI weakening
force push
branch protection bypass
hook bypass
```

\---

## 11\. Roadmap execution sequence

The immediate QRE Feature Build Track should resume at:

```text
v3.15.16 — Intelligent Routing Layer
```

Then proceed:

```text
v3.15.17 — Sampling Intelligence
v3.15.18 — Research Observability Expansion
v3.15.19 — Hypothesis Discovery Engine
v3.15.20 — Failure → Action Mapping
v3.16.x  — Adaptive Research Learning
v4.x     — Shadow Trading
v5.x     — Paper Trading
v6.x     — Live Trading
```

Do not jump to:

* shadow execution
* paper execution
* live execution
* broker integration
* risk engine changes
* capital allocation

unless the corresponding Roadmap v6 phase is explicitly active and operator-approved.

\---

## 12\. Standard phase execution protocol

Each roadmap phase must follow this lifecycle.

### Step 1 — Inspect

Read only the files relevant to the active phase.

Confirm:

* current system state
* applicable governance constraints
* allowed/forbidden surfaces
* frozen contracts
* artifact contracts
* existing test coverage
* relevant sidecar patterns

### Step 2 — Plan

Produce a compact concrete plan containing:

* scope
* file map
* architecture choices
* diagnostic/addendum integration if applicable
* risks
* test strategy
* Definition of Done

### Step 3 — Build

Implement only the smallest coherent release for the phase.

Use small atomic commits.

Do not broaden scope into adjacent roadmap phases.

### Step 4 — Test

Run targeted tests first, then broader suites appropriate to the change.

Minimum expected validation:

```text
targeted tests
relevant unit tests
smoke tests where available
governance lint where available
frozen contract diff/check where relevant
artifact validity check where relevant
```

### Step 5 — Validate behavior

Do not treat “tests pass” as sufficient.

Validate:

* frozen contracts intact
* sidecar artifacts valid
* no mutation routes introduced accidentally
* no protected paths touched
* no live/paper/shadow/risk/broker/execution paths touched outside phase
* operator-facing outputs are readable and explainable

### Step 6 — PR and handoff

Follow repo PR lifecycle.

Do not directly push to main.
Do not force push.
Do not bypass hooks.
Do not weaken tests.

Final handoff must include:

* branch
* PR
* files changed
* behavior changed
* tests run
* validation results
* frozen-contract status
* known limitations
* next recommended phase

\---

## 13\. Phase cards

## 13.1 v3.15.16 — Intelligent Routing Layer

### Product goal

Make campaign routing behavior-aware instead of preset-count-aware.

The system should prioritize:

```text
most informative exploration
```

instead of:

```text
most available preset
```

### Addendum integration

Add diagnostic-aware routing:

* entropy-aware routing
* tail-aware routing
* criticality-aware routing
* network-aware routing
* quorum-aware routing
* external-intelligence-aware routing
* dead-zone suppression by diagnostic failure

Routing should prioritize:

* highest expected information gain
* most orthogonal behavior hypothesis
* best public-data quality
* lowest dead-zone risk
* strongest independent diagnostic support

### In scope

* deterministic routing signals
* policy-backed prioritization
* read-only explainability artifacts
* sidecar outputs if needed
* tests proving routing decisions are stable and explainable

### Out of scope

* new executable strategies
* strategy explosion
* live/paper/shadow changes
* broker/risk/order changes
* frozen contract mutation
* hidden ML selector

### DoD

* routing decisions deterministic
* duplicate exploration reduced or explicitly scored
* diagnostic/public-data inputs treated as priors only
* artifacts valid
* tests green
* frozen contracts intact
* PR/handoff complete

\---

## 13.2 v3.15.17 — Sampling Intelligence

### Product goal

Improve research efficiency through deterministic intelligent sampling.

The system should stop brute-forcing large parameter grids and focus on high-information exploration.

### Addendum integration

Add:

* tail-aware sampling
* entropy-stratified sampling
* phase-transition-zone sampling
* barrier-condition sampling
* resonance-window sampling
* network-regime sampling
* post-shock sampling
* null-model control sampling

Sampling should answer:

* where does this hypothesis contain the most information?
* where is it most likely to fail?
* where is it most likely overfit?
* where does regime/context materially change behavior?

### In scope

* deterministic sampling plans
* coverage metrics
* low-information suppression
* diagnostic-conditioned sampling metadata
* sampling tests

### Out of scope

* stochastic search
* genetic programming
* free-form indicator generation
* live/paper/shadow execution
* frozen contract mutation

### DoD

* sampling is reproducible
* high/low-information regions are explainable
* null/control samples can be represented
* tests green
* artifacts valid

\---

## 13.3 v3.15.18 — Research Observability Expansion

### Product goal

Make research reasoning transparent to the operator.

The operator should understand:

```text
WHY the engine explored something
WHY it failed or survived
```

### Addendum integration

Expose observable surfaces for:

* diagnostic contribution explanation
* external data lineage
* public data quality status
* hypothesis seed provenance
* null-model comparison
* quorum status
* network state
* entropy/tail/criticality regime
* physics/complex-systems diagnostic surfaces

### In scope

* read-only reporting
* explanation artifacts
* lineage/provenance summaries
* diagnostic health/status outputs
* UI/API read-only surfaces if already safe and within governance

### Out of scope

* mutation routes
* approval buttons
* business logic in frontend
* trading/paper/shadow/live changes
* hidden selector behavior

### DoD

* operator can explain why a campaign/hypothesis was explored
* operator can see supporting and contradicting diagnostics
* source quality is visible
* failures/survivors are traceable
* tests and smoke checks green

\---

## 13.4 v3.15.19 — Hypothesis Discovery Engine

### Product goal

Introduce the first true autonomous research-front-door layer.

The engine begins deciding:

```text
WHAT deserves research
```

rather than merely executing research well.

### Base planned modules

```text
research/hypothesis\_discovery/behavior\_catalog.py
research/hypothesis\_discovery/behavior\_hypotheses.py
research/hypothesis\_discovery/opportunity\_scoring.py
research/hypothesis\_discovery/preset\_feasibility.py
research/hypothesis\_discovery/campaign\_seed\_proposer.py
```

### Addendum modules

```text
research/hypothesis\_discovery/external\_intelligence\_catalog.py
research/hypothesis\_discovery/public\_data\_seed\_registry.py
research/hypothesis\_discovery/physics\_behavior\_catalog.py
research/hypothesis\_discovery/mechanistic\_behavior\_catalog.py
research/hypothesis\_discovery/diagnostic\_hypothesis\_adapter.py
```

### Addendum hypothesis seed examples

```text
tail\_asymmetry\_crypto\_4h\_v0
low\_entropy\_trend\_continuation\_equities\_daily\_v0
post\_shock\_volatility\_decay\_btc\_1h\_v0
network\_contagion\_equities\_daily\_v0
barrier\_pressure\_breakout\_crypto\_15m\_v0
liquidity\_turbulence\_breakout\_failure\_v0
quorum\_confirmed\_volatility\_transition\_v0
market\_language\_compression\_expansion\_v0
```

### Required scoring interpretation

`opportunity\_probability\_score` means expected research value.

It is not:

* prediction certainty
* ML confidence
* alpha certainty

It estimates:

* feasibility
* expected signal density
* orthogonality
* prior evidence alignment
* regime compatibility
* expected information gain
* compute efficiency
* historical survival similarity

### In scope

* deterministic hypothesis proposals
* behavior-first hypothesis objects
* explainable opportunity scoring
* feasible preset/campaign seed mapping
* sidecar artifacts
* tests for determinism and explainability

### Out of scope

* auto-writing executable strategies
* hidden AI logic
* stochastic mutation
* direct promotion to trade/paper/live
* executable alpha generation

### DoD

* hypotheses are behavior-first
* scoring is explainable
* seed provenance is preserved
* campaign seed proposals are reviewable
* no hidden strategy invention
* tests and artifact validation green

\---

## 13.5 v3.15.20 — Failure → Action Mapping

### Product goal

Convert research failures into deterministic adaptive actions.

The engine should evolve from:

```text
static preset exploration
```

into:

```text
closed-loop adaptive exploration
```

### Base examples

```text
insufficient\_trades -> higher timeframe
high\_drawdown -> volatility normalization
weak\_stability -> regime segmentation
```

### Addendum mappings

```text
high\_entropy -> suppress directional strategy mapping
weak\_tail\_fit -> do not prioritize tail-convex hypothesis
left\_tail\_fragility -> require stronger confirmation
phase\_transition\_unstable -> require regime segmentation
barrier\_false\_positive\_high -> increase confirmation requirement
resonance\_not\_persistent -> downgrade cycle-confluence hypothesis
network\_concentration\_high -> suppress portfolio-overlapping campaigns
post\_shock\_aftershock\_unstable -> cooldown new campaigns
liquidity\_turbulence\_high -> defer execution-sensitive mappings to shadow/paper validation
quorum\_insufficient -> keep as hypothesis seed, do not escalate
null\_model\_not\_beaten -> reject or demote hypothesis family
```

### In scope

* deterministic failure taxonomy
* action mapping table
* cooldown/suppression/escalation recommendations
* evidence-backed failure explanations
* tests proving mappings are stable and non-executional

### Out of scope

* live risk mutation
* paper/shadow/live execution changes
* random mutation
* automatic indicator invention
* direct candidate promotion

### DoD

* each failure maps to an explicit action
* mappings are deterministic and testable
* diagnostics influence research behavior only
* no execution authority introduced
* tests green

\---

## 13.6 v3.16.x — Adaptive Research Learning

### Product goal

Introduce closed-loop research learning.

The engine evolves from:

```text
run -> record -> reject
```

into:

```text
run -> learn -> reroute
```

### Addendum integration

Track:

* diagnostic utility
* behavior-family fitness by diagnostic family
* quorum effectiveness
* public source usefulness
* diagnostic false positives
* diagnostic dead-zone suppression

### In scope

* adaptive routing policy signals
* strategy/behavior fitness scoring
* regime intelligence
* candidate clustering
* robustness filtering
* portfolio intelligence research layer

### Out of scope

* live/paper/shadow execution unless the specific subphase allows it
* capital allocation
* broker integration
* live risk mutation

### DoD

* learning is deterministic and evidence-backed
* behavior-family feedback is auditable
* diagnostics can be evaluated for usefulness
* false positives are tracked
* policy remains inspectable

\---

## 13.7 v4.x — Shadow Trading

### Product goal

Validate behavior realism in real-time conditions without real capital and without paper execution assumptions.

### Addendum integration

Add diagnostic parity checks:

* tail/entropy/criticality/network state parity
* liquidity turbulence observed vs expected
* post-shock response parity
* signal decay under adversarial regimes

### In scope

* real-time signal parity
* live market replay
* shadow execution state
* reconciliation infrastructure
* timing drift analysis
* shadow kill-switches and anomaly detection in appropriate subphases

### Out of scope

* real capital
* live broker orders
* broad rollout
* bypassing candidate governance

### DoD

* shadow behavior is observable
* parity is testable
* drift and signal decay are measurable
* operational controls exist before further promotion

\---

## 13.8 v5.x — Paper Trading

### Product goal

Validate economic viability under simulated capital deployment.

### Addendum integration

Add diagnostics for:

* tail dependency under simulated capital
* expected shortfall under diagnostic regimes
* drawdown governance informed by diagnostics
* paper degradation by entropy/network/turbulence regimes
* quorum-confirmed candidate paper behavior

### In scope

* automated paper promotion
* paper lifecycle governance
* simulated position sizing
* drawdown governance
* portfolio exposure control
* live expectancy tracking
* execution-adjusted viability

### Out of scope

* real capital
* broker live execution
* diagnostics directly trading
* bypassing paper readiness gates

### DoD

* paper behavior is governed
* simulated capital risks are bounded
* degradation is observable
* candidates can be demoted/retired based on evidence

\---

## 13.9 v6.x — Live Trading

### Product goal

Deploy validated behaviors with controlled capital, operational governance, and execution safety.

### Addendum integration

Diagnostics may support:

* live risk governance context
* kill-switch context
* approved risk-envelope decisions
* capital scaling only through approved policy

Diagnostics may not:

* directly create live trades
* bypass whitelist
* bypass reconciliation
* bypass kill switches
* mutate capital allocation outside approved policy

### In scope

* controlled live deployment
* tiny-capital deployment
* guarded live execution
* deployment gates
* live risk governance
* broker integration in the appropriate v6 subphase
* reconciliation
* emergency halts
* adaptive capital allocation only after validation

### Out of scope

* broad live rollout
* unbounded capital allocation
* unapproved risk mutation
* hidden execution behavior
* diagnostics as trade triggers

### DoD

* live is small, controlled, rollbackable
* whitelist/reconciliation/kill switches exist
* capital scaling is policy-governed
* live behavior is auditable
* rollback path is tested

\---

## 14\. Standard handoff template

Use after each completed phase or PR.

```text
# Handoff — <phase / PR title>

## Status
<Complete / In progress / Blocked>

## Active track
<ADE / QRE Feature Build>

## Phase
<roadmap phase>

## Branch / PR
<branch>
<PR link or number>

## Summary
<what changed>

## Files changed
- <file>: <reason>

## Behavior changed
- <operator-visible behavior>
- <system behavior>

## Tests run
- <command>: <result>

## Validation
- Frozen contracts: <intact / not touched / issue>
- Sidecar artifacts: <valid / not applicable>
- Governance lint: <pass / not run / fail>
- Smoke tests: <pass / not run / fail>
- Protected paths: <not touched / touched with approval>
- Execution paths: <not touched / touched under phase authority>

## Risks / limitations
- <risk>

## Next recommended action
<next phase or remediation>
```

\---

## 15\. Claude/ADE master prompt contract

Use this contract as the base for any implementation session.

```text
You are working in the QRE repository.

Read first:
- AGENTS.md
- CLAUDE.md
- docs/roadmap/Roadmap v6.md
- docs/roadmap/Roadmap v6 Addendum.md
- docs/roadmap/autonomous\_development.txt
- relevant governance docs for the active phase

Active track:
<QRE Feature Build Track or Autonomous Development Track>

Active phase:
<phase name>

Goal:
<phase goal>

Hard constraints:
- Do not work on main directly.
- Create a new branch following repo convention.
- Follow the PR lifecycle.
- No force push.
- No hook bypass.
- No test weakening.
- No branch-protection bypass.
- registry.py remains source of truth for strategy registration.
- research/run\_research.py remains central orchestrator.
- research\_latest.json and strategy\_matrix.csv remain frozen contracts.
- Frontend remains UI only.
- Diagnostics do not trade.
- External/public data is an unvalidated prior, not alpha.
- Do not modify live/paper/shadow/risk/broker/execution behavior unless this exact active phase explicitly authorizes it.
- Do not introduce hidden ML/RL selectors, genetic programming, stochastic strategy mutation, or automatic indicator invention.

Workflow:
1. Inspect relevant files only.
2. Report current state and constraints.
3. Give a compact implementation plan.
4. Implement the smallest coherent phase slice.
5. Add or update tests.
6. Run targeted tests.
7. Run governance/smoke/full tests appropriate to the change.
8. Validate frozen contracts and sidecar artifacts.
9. Open PR.
10. Produce handoff with files, tests, validation, risks, and next action.

Approval rules:
- Proceed autonomously for low-risk in-scope development work.
- Ask operator approval for protected paths, canonical governance edits, frozen contract changes, high-risk policy changes, or irreversible/breaking changes.
- Never self-authorize permanently denied work.
```

\---

## 16\. Success criteria for this operating manual

This manual is successful when:

1. Roadmap v6 remains the canonical QRE product roadmap.
2. The Addendum is integrated as a diagnostic/external-intelligence extension, not a separate competing roadmap.
3. ADE remains development-governance infrastructure, not trading execution.
4. Diagnostics are prohibited from direct trading or capital/risk mutation.
5. v3.15.16 through v3.15.20 have concrete implementation cards.
6. v3.16/v4/v5/v6 have clear later-stage diagnostic roles without premature live use.
7. Claude/ADE can execute phases with consistent branch, PR, CI, validation, and handoff discipline.
8. Frozen contracts remain protected.
9. The operator can understand what is allowed, what requires approval, and what is forbidden.

