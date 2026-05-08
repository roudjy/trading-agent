# QRE Roadmap v6 + Addendum — Claude/ADE Phase Prompts

## Purpose

This document contains ready-to-use prompts for Claude Code or ADE-guided development sessions.

Use these prompts together with:

- `docs/roadmap/qre_roadmap_v6_ade_operating_manual.md`
- Roadmap v6
- Roadmap v6 Addendum
- `AGENTS.md`
- `CLAUDE.md`
- current governance docs

Each prompt assumes the repository PR lifecycle applies:

```text
new branch -> implementation -> tests -> PR -> CI -> review/merge protocol -> post-merge checks
```

Do not paste all prompts at once. Use only the prompt for the active phase.

---

# Global prefix for every Claude Code session

```text
You are working in the QRE repository.

Read first:
- AGENTS.md
- CLAUDE.md
- docs/roadmap/Roadmap v6.md
- docs/roadmap/Roadmap v6 Addendum.md
- docs/roadmap/autonomous_development.txt
- docs/roadmap/qre_roadmap_v6_ade_operating_manual.md
- relevant governance docs for this phase

Follow the repository PR lifecycle.
Do not work directly on main.
Create exactly one new branch for this phase.
Do not force push.
Do not bypass hooks.
Do not weaken tests.
Do not bypass branch protection.

Hard architecture constraints:
- registry.py remains the source of truth for strategy registration.
- research/run_research.py remains the central research orchestrator.
- research_latest.json and strategy_matrix.csv are frozen public contracts.
- New research/diagnostic information must go into sidecar artifacts or read-only reports.
- Frontend remains UI only.
- Backend remains a control surface.
- Research/engine modules own research logic.
- Diagnostics do not trade.
- External/public data is an unvalidated prior, not alpha.

Forbidden unless this exact phase explicitly authorizes it:
- live/paper/shadow/risk/broker/execution behavior changes
- order placement
- capital allocation
- live risk mutation
- hidden ML/RL selector
- genetic programming
- stochastic strategy mutation
- automatic indicator invention
- strategy explosion
- mutation of research_latest.json or strategy_matrix.csv
- approval-inbox mutation
- dashboard mutation routes
- .claude/** writes

Workflow:
1. Inspect relevant files only.
2. Summarize current state and constraints.
3. Produce a compact implementation plan.
4. Implement the smallest coherent phase slice.
5. Add/update tests.
6. Run targeted tests.
7. Run governance/smoke/full checks appropriate to the change.
8. Validate frozen contracts and sidecar artifacts.
9. Open a PR against main.
10. Produce a handoff note with files, tests, validation, risks, and next action.
```

---

# Prompt 1 — v3.15.16 Intelligent Routing Layer

```text
Continue the QRE Feature Build Track.

Active phase:
v3.15.16 — Intelligent Routing Layer

Goal:
Make campaign routing behavior-aware instead of preset-count-aware.
The system should prioritize the most informative exploration, not merely the most available preset.

Roadmap v6 product requirements:
- smarter campaign prioritization
- behavior-aware routing
- orthogonality-aware queue discipline
- dead-zone-aware routing suppression
- information-gain prioritization
- reduced duplicate exploration
- improved compute allocation

Addendum requirements:
Add diagnostic-aware routing signals where architecturally appropriate:
- entropy-aware routing
- tail-aware routing
- criticality-aware routing
- network-aware routing
- quorum-aware routing
- external-intelligence-aware routing
- dead-zone suppression by diagnostic failure

Routing should consider:
- expected information gain
- behavior orthogonality
- public-data quality where present
- dead-zone risk
- independent diagnostic support

Important constraints:
- Diagnostics are research-routing inputs only; diagnostics do not trade.
- Do not add executable strategies.
- Do not mutate frozen contracts.
- Do not modify live/paper/shadow/risk/broker/execution paths.
- Do not introduce hidden ML, stochastic ranking, genetic programming, or opaque selectors.
- Keep routing deterministic, inspectable, artifact-backed, and testable.

Expected deliverables:
- deterministic routing/prioritization implementation or phase-appropriate scaffold
- tests proving deterministic routing decisions
- read-only explanation/reporting artifacts if needed
- no frozen contract changes
- handoff note

Validation expectations:
- targeted routing tests
- relevant unit tests
- smoke/governance checks where available
- frozen contract check or explicit not-touched statement
- protected/execution paths not touched
```

---

# Prompt 2 — v3.15.17 Sampling Intelligence

```text
Continue the QRE Feature Build Track.

Active phase:
v3.15.17 — Sampling Intelligence

Goal:
Improve research efficiency through deterministic intelligent sampling.
The system should reduce brute-force parameter-grid exploration and focus on high-information coverage.

Roadmap v6 product requirements:
- stratified sampling
- adaptive deterministic coverage
- low-information-region suppression
- exploratory breadth balancing
- signal-density-aware sampling
- reduced wasted compute
- better coverage efficiency

Addendum requirements:
Add diagnostic-aware sampling where appropriate:
- tail-aware sampling
- entropy-stratified sampling
- phase-transition-zone sampling
- barrier-condition sampling
- resonance-window sampling
- network-regime sampling
- post-shock sampling
- null-model control sampling

Sampling should answer:
- where does the hypothesis contain the most information?
- where is it most likely to fail?
- where is it likely overfit?
- where does regime/context materially change behavior?

Important constraints:
- Sampling must be deterministic and reproducible.
- No stochastic search.
- No genetic programming.
- No automatic indicator invention.
- No live/paper/shadow/risk/broker/execution changes.
- Do not mutate frozen contracts.

Expected deliverables:
- deterministic sampling planner or phase-appropriate scaffold
- coverage/selection metadata
- tests for stable sampling output
- diagnostic-conditioned sampling metadata where appropriate
- handoff note

Validation expectations:
- targeted sampling tests
- relevant unit tests
- smoke/governance checks where available
- artifact validity checks where artifacts are added
- frozen contracts intact
```

---

# Prompt 3 — v3.15.18 Research Observability Expansion

```text
Continue the QRE Feature Build Track.

Active phase:
v3.15.18 — Research Observability Expansion

Goal:
Make research reasoning transparent to the operator.
The operator should understand why the engine explored something and why it failed or survived.

Roadmap v6 product requirements:
- behavior-level diagnostics
- exploration lineage visualization
- campaign decomposition
- hypothesis traceability
- information-gain surfaces
- explanation artifacts
- failure clustering visibility

Addendum requirements:
Expose read-only surfaces for:
- diagnostic contribution explanation
- external data lineage
- public data quality status
- hypothesis seed provenance
- null-model comparison
- quorum status
- network state
- entropy/tail/criticality regime
- supporting and contradicting diagnostics

Important constraints:
- Read-only only unless explicitly approved.
- Do not add dashboard mutation routes.
- Do not add approval buttons.
- Do not put business logic in the frontend.
- Do not modify live/paper/shadow/risk/broker/execution behavior.
- Do not mutate frozen contracts.

Expected deliverables:
- explanation artifacts or read-only reports
- tests for observability/reporting correctness
- operator-readable summaries
- no mutation endpoints
- handoff note

Validation expectations:
- targeted reporting/observability tests
- smoke/governance checks where available
- verify no mutation routes added
- verify protected paths and frozen contracts intact
```

---

# Prompt 4 — v3.15.19 Hypothesis Discovery Engine

```text
Continue the QRE Feature Build Track.

Active phase:
v3.15.19 — Hypothesis Discovery Engine

Goal:
Introduce the first true autonomous research-front-door layer.
The engine should begin proposing behavior-first research hypotheses and deciding what deserves research, not merely executing preset campaigns.

Roadmap v6 planned modules:
- research/hypothesis_discovery/behavior_catalog.py
- research/hypothesis_discovery/behavior_hypotheses.py
- research/hypothesis_discovery/opportunity_scoring.py
- research/hypothesis_discovery/preset_feasibility.py
- research/hypothesis_discovery/campaign_seed_proposer.py

Addendum extension modules, if appropriate for the implementation slice:
- research/hypothesis_discovery/external_intelligence_catalog.py
- research/hypothesis_discovery/public_data_seed_registry.py
- research/hypothesis_discovery/physics_behavior_catalog.py
- research/hypothesis_discovery/mechanistic_behavior_catalog.py
- research/hypothesis_discovery/diagnostic_hypothesis_adapter.py

Hypotheses must be behavior-first, for example:
- volatility compression -> expansion -> continuation reflexivity
- tail asymmetry in crypto 4h regimes
- low-entropy trend continuation
- post-shock volatility decay
- network contagion in equities
- barrier-pressure breakout failure
- liquidity turbulence breakout failure
- quorum-confirmed volatility transition
- market-language compression expansion

Scoring rule:
`opportunity_probability_score` means expected research value.
It is not prediction certainty, alpha certainty, or ML confidence.

It may consider:
- feasibility
- expected signal density
- orthogonality
- prior evidence alignment
- regime compatibility
- expected information gain
- compute efficiency
- historical survival similarity

Important constraints:
- Deterministic, inspectable, artifact-driven, explainable, non-black-box.
- Do not auto-write executable strategy code.
- Do not invent hidden strategies.
- Do not introduce hidden AI logic or stochastic mutation.
- Do not promote directly to trading, paper, shadow, or live.
- Do not mutate frozen contracts.

Expected deliverables:
- behavior hypothesis data structures
- deterministic opportunity scoring
- feasibility/campaign seed proposal scaffold or implementation
- sidecar artifacts where appropriate
- tests for determinism and explainability
- handoff note

Validation expectations:
- hypothesis discovery unit tests
- deterministic output tests
- artifact schema/validity tests if artifacts are added
- governance/smoke checks where available
- frozen contracts intact
```

---

# Prompt 5 — v3.15.20 Failure → Action Mapping

```text
Continue the QRE Feature Build Track.

Active phase:
v3.15.20 — Failure → Action Mapping

Goal:
Convert research failures into deterministic adaptive actions.
The engine should begin forming closed-loop adaptive exploration instead of static preset exploration.

Roadmap v6 base examples:
- insufficient_trades -> higher timeframe
- high_drawdown -> volatility normalization
- weak_stability -> regime segmentation

Addendum mappings to incorporate where appropriate:
- high_entropy -> suppress directional strategy mapping
- weak_tail_fit -> do not prioritize tail-convex hypothesis
- left_tail_fragility -> require stronger confirmation
- phase_transition_unstable -> require regime segmentation
- barrier_false_positive_high -> increase confirmation requirement
- resonance_not_persistent -> downgrade cycle-confluence hypothesis
- network_concentration_high -> suppress portfolio-overlapping campaigns
- post_shock_aftershock_unstable -> cooldown new campaigns
- liquidity_turbulence_high -> defer execution-sensitive mappings to shadow/paper validation
- quorum_insufficient -> keep as hypothesis seed, do not escalate
- null_model_not_beaten -> reject or demote hypothesis family

Important constraints:
- Mappings must be deterministic and testable.
- Mappings may affect research routing, suppression, escalation, cooldown, or confirmation requirements.
- Mappings may not mutate live risk, place trades, allocate capital, or bypass policy.
- Do not modify live/paper/shadow/risk/broker/execution behavior.
- Do not mutate frozen contracts.

Expected deliverables:
- explicit failure taxonomy
- deterministic action mapping implementation or scaffold
- tests for failure-to-action behavior
- operator-readable explanations
- handoff note

Validation expectations:
- targeted failure-action tests
- relevant unit tests
- governance/smoke checks where available
- frozen contracts intact
- execution paths not touched
```

---

# Prompt 6 — v3.16.0 Campaign Feedback Loop

```text
Continue the QRE Feature Build Track.

Active phase:
v3.16.0 — Campaign Feedback Loop

Goal:
Make campaign outcomes directly influence future exploration policy.
The engine should evolve from run -> run into run -> learn -> reroute.

Roadmap v6 requirements:
- policy adaptation
- exploration suppression
- follow-up escalation
- behavior-level reinforcement
- campaign memory integration
- reduced redundant exploration
- faster convergence toward useful hypothesis spaces

Addendum requirements:
Begin tracking diagnostic utility and false-positive behavior where appropriate:
- which diagnostics improve survivor quality
- which diagnostics create false positives
- which public sources produce useful hypothesis seeds
- which behavior families deserve more compute

Important constraints:
- Learning must be deterministic and evidence-backed.
- No hidden ML/RL selector.
- No capital allocation.
- No live/paper/shadow/risk/broker/execution changes unless explicitly in scope.
- Do not mutate frozen contracts.

Expected deliverables:
- campaign feedback signal integration
- deterministic memory/policy update behavior
- tests for feedback behavior
- reporting/observability updates where appropriate
- handoff note

Validation expectations:
- feedback-loop tests
- policy/memory tests
- governance/smoke checks where available
- frozen contracts intact
```

---

# Prompt 7 — v3.16.1 Strategy Fitness Scoring

```text
Continue the QRE Feature Build Track.

Active phase:
v3.16.1 — Strategy Fitness Scoring

Goal:
Quantify long-term research viability for strategies and behavior classes.

Roadmap v6 requirements:
Fitness scoring should consider:
- survival rate
- exploratory pass frequency
- near-pass frequency
- promotion success
- regime stability
- cross-asset robustness
- information efficiency

Addendum extension:
Where appropriate, include diagnostic-family utility signals:
- diagnostic-supported survival rate
- diagnostic false-positive contribution
- diagnostic dead-zone association
- quorum effectiveness
- public source usefulness

Important constraints:
- Fitness is research viability, not live allocation.
- Do not use fitness to allocate capital.
- Do not introduce live/paper/shadow/risk/broker/execution changes.
- Do not mutate frozen contracts.

Expected deliverables:
- deterministic fitness score implementation or scaffold
- tests for scoring correctness and stability
- operator-readable explanation of score components
- handoff note

Validation expectations:
- scoring unit tests
- deterministic output tests
- governance/smoke checks where available
- frozen contracts intact
```

---

# Prompt 8 — v3.16.2 Regime Intelligence

```text
Continue the QRE Feature Build Track.

Active phase:
v3.16.2 — Regime Intelligence

Goal:
Make the engine regime-aware at the behavior level.
The engine should learn when a behavior should not run.

Roadmap v6 requirements:
- regime classification
- regime compatibility scoring
- regime-conditioned activation
- regime-conditioned routing
- volatility-state awareness

Addendum extension:
Where appropriate, use diagnostics as regime context:
- entropy regimes
- tail regimes
- criticality/instability regimes
- network concentration regimes
- liquidity turbulence regimes
- post-shock regimes

Important constraints:
- Regime intelligence is research/policy context only.
- Do not mutate live risk.
- Do not allocate capital.
- Do not place trades.
- Do not modify live/paper/shadow/risk/broker/execution behavior.
- Do not mutate frozen contracts.

Expected deliverables:
- deterministic regime classification/scoring implementation or scaffold
- tests for regime classification and compatibility
- observability/reporting where appropriate
- handoff note

Validation expectations:
- regime tests
- deterministic output tests
- governance/smoke checks where available
- frozen contracts intact
```

---

# Prompt 9 — v3.16.3 Candidate Clustering

```text
Continue the QRE Feature Build Track.

Active phase:
v3.16.3 — Candidate Clustering

Goal:
Prevent overfitting through behavior-family grouping.
The engine should reason in behavior-equivalent candidate groups instead of isolated strategies.

Roadmap v6 requirements:
Cluster:
- strategies
- presets
- campaigns

into behavior-equivalent candidate groups.

Addendum extension:
Where appropriate, use diagnostic signatures to support grouping:
- entropy/tail/criticality signature similarity
- network-regime similarity
- barrier/resonance behavior similarity
- failure-action similarity
- null-model failure similarity

Important constraints:
- Clustering supports research robustness and evidence interpretation.
- Clustering does not promote candidates directly.
- No live/paper/shadow/risk/broker/execution changes.
- No frozen contract mutation.

Expected deliverables:
- deterministic clustering implementation or scaffold
- tests for stable cluster assignment
- explainable cluster metadata
- handoff note

Validation expectations:
- clustering tests
- stability/determinism tests
- governance/smoke checks where available
- frozen contracts intact
```

---

# Prompt 10 — v3.16.4 Robustness Filtering

```text
Continue the QRE Feature Build Track.

Active phase:
v3.16.4 — Robustness Filtering

Goal:
Force candidate quality above exploratory quality.
Candidates should survive only if they are robust across assets, regimes, parameters, and periods.

Roadmap v6 requirements:
Filter for:
- multi-asset stability
- multi-regime stability
- persistence
- low parameter fragility
- non-dependence on isolated periods

Addendum extension:
Where appropriate, include diagnostic robustness:
- tail fragility checks
- entropy regime robustness
- criticality stability
- null-model challenge
- quorum confirmation
- single-source dependency flags

Important constraints:
- Robustness filtering governs research/candidate quality.
- It does not allocate capital or trigger live deployment.
- No live/paper/shadow/risk/broker/execution changes unless the phase explicitly allows downstream integration.
- Do not mutate frozen contracts.

Expected deliverables:
- robustness filter implementation or scaffold
- tests for pass/fail decisions
- explanation artifacts
- handoff note

Validation expectations:
- robustness filter tests
- null-model/quorum tests where applicable
- governance/smoke checks where available
- frozen contracts intact
```

---

# Prompt 11 — v3.16.5 Portfolio Intelligence

```text
Continue the QRE Feature Build Track.

Active phase:
v3.16.5 — Portfolio Intelligence

Goal:
Move beyond single-edge thinking into portfolio-level research reasoning before shadow/paper/live deployment.

Roadmap v6 requirements:
- lightweight portfolio construction
- edge correlation analysis
- diversification-aware candidate selection
- behavior interaction modeling

Addendum extension:
Where appropriate, include:
- network diagnostics
- correlation graph concentration
- contagion warnings
- diversification breakdown flags
- cluster-level behavior interactions

Important constraints:
- This is portfolio intelligence for research/candidate validation, not live capital allocation.
- Do not place trades.
- Do not modify live risk.
- Do not modify broker/order execution.
- Do not mutate frozen contracts.

Expected deliverables:
- portfolio research intelligence implementation or scaffold
- tests for correlation/diversification behavior
- operator-readable reporting
- handoff note

Validation expectations:
- portfolio intelligence tests
- deterministic output tests
- governance/smoke checks where available
- frozen contracts intact
```

---

# Prompt 12 — v4.0 Shadow Infrastructure

```text
Continue the QRE Feature Build Track only if v4.0 is explicitly active and operator-approved.

Active phase:
v4.0 — Shadow Infrastructure

Goal:
Validate behavior realism in real-time conditions without real capital and without paper execution assumptions.

Roadmap v6 requirements:
- real-time signal parity
- live market replay
- shadow execution state
- reconciliation infrastructure
- timing drift analysis

Addendum extension:
Prepare for diagnostic parity:
- tail/entropy/criticality/network state parity
- liquidity turbulence observed vs expected
- post-shock response parity
- adversarial signal decay context

Important constraints:
- No real capital.
- No live broker orders.
- No broad rollout.
- Do not bypass candidate governance.
- Shadow must be observable and reversible.

Expected deliverables:
- shadow infrastructure implementation or scaffold
- parity tests
- reconciliation/timing drift tests where appropriate
- operator-visible shadow status
- handoff note

Validation expectations:
- shadow infrastructure tests
- parity tests
- smoke/governance checks
- frozen contracts intact unless explicitly approved otherwise
```

---

# Prompt 13 — v4.1 Shadow Candidate Lifecycle

```text
Continue the QRE Feature Build Track only if v4.1 is explicitly active and operator-approved.

Active phase:
v4.1 — Shadow Candidate Lifecycle

Goal:
Introduce automatic candidate -> shadow promotion under governed lifecycle rules.

Requirements:
- automatic candidate to shadow promotion
- shadow behavior tracking
- live-like evidence accumulation
- candidate governance preservation

Addendum extension:
Track diagnostic behavior in shadow:
- diagnostic state parity
- signal decay by diagnostic regime
- post-shock behavior
- network/turbulence regime behavior

Important constraints:
- Shadow is not live.
- No real capital.
- No live broker orders.
- No bypass of whitelist/governance/promotion gates.

Expected deliverables:
- shadow lifecycle state handling
- tests for promotion/demotion behavior
- read-only shadow reporting
- handoff note

Validation expectations:
- lifecycle tests
- governance tests
- parity/status tests
- frozen contracts intact unless explicitly approved otherwise
```

---

# Prompt 14 — v4.2 Execution Realism

```text
Continue the QRE Feature Build Track only if v4.2 is explicitly active and operator-approved.

Active phase:
v4.2 — Execution Realism

Goal:
Model execution realism in shadow conditions before paper or live deployment.

Requirements:
- slippage realism
- liquidity realism
- latency-aware diagnostics
- signal decay measurement

Addendum extension:
Use liquidity turbulence diagnostics and adversarial market behavior diagnostics as context:
- liquidity_turbulence_score
- slippage_convexity_proxy
- flow_break_risk
- post_signal_decay
- adverse_selection_score

Important constraints:
- Still no real capital.
- Still no live broker orders.
- Diagnostics inform realism; diagnostics do not trade.
- Do not mutate live risk or capital allocation.

Expected deliverables:
- execution realism model/scaffold
- tests for slippage/liquidity/latency behavior
- shadow reporting updates
- handoff note

Validation expectations:
- execution realism tests
- shadow parity tests
- governance/smoke checks
```

---

# Prompt 15 — v4.3 Operational Resilience

```text
Continue the QRE Feature Build Track only if v4.3 is explicitly active and operator-approved.

Active phase:
v4.3 — Operational Resilience

Goal:
Add shadow operational controls before paper trading.

Requirements:
- shadow kill-switches
- realtime anomaly detection
- parity integrity validation

Addendum extension:
Use diagnostics for context only:
- criticality warnings
- turbulence warnings
- network fragility
- aftershock instability
- data integrity anomalies

Important constraints:
- Kill-switches protect shadow operation.
- No real capital.
- No live order placement.
- No capital allocation.

Expected deliverables:
- operational resilience controls
- anomaly/parity tests
- read-only operator surfaces
- handoff note

Validation expectations:
- resilience tests
- kill-switch tests
- parity integrity tests
- governance/smoke checks
```

---

# Prompt 16 — v5.0 Automated Paper Promotion

```text
Continue the QRE Feature Build Track only if v5.0 is explicitly active and operator-approved.

Active phase:
v5.0 — Automated Paper Promotion

Goal:
Validate economic viability under simulated capital deployment by promoting qualified candidates to paper under governed rules.

Requirements:
- candidate -> paper automation
- paper lifecycle governance
- paper deployment queue

Addendum extension:
Diagnostics may provide paper-readiness context:
- quorum-confirmed candidate behavior
- tail dependency warnings
- entropy/network/turbulence regime context

Important constraints:
- Paper is simulated capital, not real capital.
- No live broker orders.
- Do not bypass paper readiness gates.
- Diagnostics do not directly trigger trades.

Expected deliverables:
- paper promotion lifecycle implementation or scaffold
- tests for paper queue/promotion behavior
- operator-readable paper readiness reporting
- handoff note

Validation expectations:
- paper promotion tests
- lifecycle tests
- governance/smoke checks
```

---

# Prompt 17 — v5.1 Paper Risk Layer

```text
Continue the QRE Feature Build Track only if v5.1 is explicitly active and operator-approved.

Active phase:
v5.1 — Paper Risk Layer

Goal:
Introduce simulated position sizing, drawdown governance, and portfolio exposure control for paper trading.

Requirements:
- simulated position sizing
- drawdown governance
- portfolio exposure control

Addendum extension:
Diagnostics may inform simulated risk context:
- tail dependency
- expected shortfall under diagnostic regimes
- entropy/network/turbulence degradation
- left-tail fragility

Important constraints:
- Paper risk is simulated.
- Do not mutate live risk.
- Do not place live broker orders.
- Do not use diagnostics as direct trade triggers.

Expected deliverables:
- paper risk controls
- tests for drawdown/exposure behavior
- reporting updates
- handoff note

Validation expectations:
- paper risk tests
- drawdown/exposure tests
- governance/smoke checks
```

---

# Prompt 18 — v5.2 Paper Performance Intelligence

```text
Continue the QRE Feature Build Track only if v5.2 is explicitly active and operator-approved.

Active phase:
v5.2 — Paper Performance Intelligence

Goal:
Track live expectancy, deployment degradation, and execution-adjusted viability under simulated capital.

Requirements:
- live expectancy tracking
- deployment degradation analysis
- execution-adjusted viability

Addendum extension:
Analyze degradation by:
- entropy regime
- network regime
- liquidity turbulence
- criticality
- post-shock behavior
- quorum status

Important constraints:
- Paper performance intelligence does not authorize live deployment by itself.
- No live broker orders.
- No live capital allocation.
- Keep outputs deterministic and auditable.

Expected deliverables:
- paper performance analytics
- tests for expectancy/degradation calculations
- operator-facing reporting
- handoff note

Validation expectations:
- performance intelligence tests
- deterministic output tests
- governance/smoke checks
```

---

# Prompt 19 — v5.3 Portfolio Paper Engine

```text
Continue the QRE Feature Build Track only if v5.3 is explicitly active and operator-approved.

Active phase:
v5.3 — Portfolio Paper Engine

Goal:
Validate multi-edge paper deployment and portfolio behavior under simulated capital.

Requirements:
- multi-edge paper deployment
- portfolio behavior tracking
- edge interaction validation

Addendum extension:
Include diagnostics for:
- network concentration
- diversification breakdown
- tail co-dependence
- turbulence-driven degradation
- quorum-confirmed portfolio behavior

Important constraints:
- Simulated capital only.
- No live broker orders.
- No live capital allocation.
- Diagnostics are context, not trade triggers.

Expected deliverables:
- portfolio paper engine implementation or scaffold
- tests for multi-edge interactions
- portfolio reporting
- handoff note

Validation expectations:
- portfolio paper tests
- exposure/interaction tests
- governance/smoke checks
```

---

# Prompt 20 — v6.0 Controlled Live Deployment

```text
Continue the QRE Feature Build Track only if v6.0 is explicitly active and operator-approved.

Active phase:
v6.0 — Controlled Live Deployment

Goal:
Deploy validated behaviors with tiny capital, guarded execution, and deployment gates.

Requirements:
- tiny-capital deployment
- guarded live execution
- deployment gates

Addendum extension:
Diagnostics may provide live governance context only:
- tail fragility context
- entropy/criticality warnings
- network fragility
- liquidity turbulence
- quorum status

Important constraints:
- Live is small, controlled, rollbackable.
- Diagnostics may not directly create live trades.
- Diagnostics may not bypass whitelist, reconciliation, kill switches, or deployment gates.
- No broad live rollout.
- Operator approval required for any real-capital enablement.

Expected deliverables:
- controlled live deployment implementation according to active governance
- tests for gates and rollback behavior
- operator-visible live status
- handoff note

Validation expectations:
- live gate tests
- rollback tests
- reconciliation/whitelist checks where applicable
- governance/security checks
```

---

# Prompt 21 — v6.1 Live Risk Governance

```text
Continue the QRE Feature Build Track only if v6.1 is explicitly active and operator-approved.

Active phase:
v6.1 — Live Risk Governance

Goal:
Introduce live risk governance under controlled capital deployment.

Requirements:
- max drawdown enforcement
- portfolio risk caps
- live anomaly detection
- emergency halts

Addendum extension:
Diagnostics may support kill-switch context and risk-governance observability:
- criticality warnings
- tail fragility
- liquidity turbulence
- network contagion
- aftershock instability

Important constraints:
- Diagnostics do not directly mutate live exposure.
- Any capital/risk change must occur only through approved risk envelope policy.
- Emergency halts must be deterministic, auditable, and tested.
- Operator approval required for high-risk policy changes.

Expected deliverables:
- live risk governance implementation
- tests for drawdown/risk caps/halts
- operator-visible risk reporting
- handoff note

Validation expectations:
- live risk tests
- halt tests
- governance/security checks
```

---

# Prompt 22 — v6.2 Execution Layer

```text
Continue the QRE Feature Build Track only if v6.2 is explicitly active and operator-approved.

Active phase:
v6.2 — Execution Layer

Goal:
Introduce broker integration, order placement, slippage-aware routing, and execution reconciliation under controlled governance.

Requirements:
- broker integration
- order placement
- slippage-aware routing
- execution reconciliation

Addendum extension:
Diagnostics may provide execution-risk context only through approved policy:
- liquidity turbulence
- slippage convexity proxy
- adverse selection
- signal decay

Important constraints:
- This phase touches high-risk execution behavior and requires explicit operator authorization.
- No broad rollout.
- No hidden order behavior.
- No bypass of whitelist, reconciliation, kill switches, or risk envelope.
- Diagnostics may not directly place orders.

Expected deliverables:
- broker/execution implementation under explicit phase authority
- reconciliation tests
- slippage/routing tests
- emergency halt/rollback tests
- security/governance validation
- handoff note

Validation expectations:
- execution tests
- broker adapter tests/mocks
- reconciliation tests
- risk/kill-switch tests
- governance/security checks
```

---

# Prompt 23 — v6.3 Adaptive Capital Allocation

```text
Continue the QRE Feature Build Track only if v6.3 is explicitly active and operator-approved.

Active phase:
v6.3 — Adaptive Capital Allocation

Goal:
Introduce capital weighting, live edge ranking, and deployment scaling logic after controlled live validation.

Requirements:
- capital weighting
- live edge ranking
- deployment scaling logic

Addendum extension:
Diagnostics may inform capital scaling only through approved risk-envelope policy:
- tail fragility
- entropy regime degradation
- network concentration
- liquidity turbulence
- quorum status
- paper/live degradation evidence

Important constraints:
- Capital allocation is high risk and requires explicit operator authorization.
- No diagnostics-direct capital movement.
- No equity-curve chasing.
- No hidden ML/RL allocator.
- No bypass of risk caps, kill switches, whitelist, or reconciliation.

Expected deliverables:
- adaptive allocation implementation under explicit phase authority
- tests for caps, scaling, demotion, rollback
- operator-visible allocation explanation
- handoff note

Validation expectations:
- capital allocation tests
- risk cap tests
- rollback tests
- governance/security checks
```

---

# Prompt 24 — Autonomous Development Track A3

```text
Continue Autonomous Development Track hardening.

Do not start QRE Feature Build work yet.
Do not modify live/paper/shadow/risk/trading/broker/execution behavior.
Do not modify .claude/**, dashboard/dashboard.py, or frozen contracts.

Active task:
A3 — Read-only Execution Authority reporting/PWA exposure

Goal:
Make the operator able to see that Agent Execution Authority is present, healthy, deterministic, and policy-backed.

Use as canonical pair:
- docs/governance/execution_authority.md
- reporting/execution_authority.py

Allowed:
- read-only reporting/status integration
- tests for reporting health
- bounded hashes/status fields
- sample decision checks
- read-only JSON/status output
- read-only PWA display only if supported by existing safe surfaces

Not allowed:
- mutation routes
- approval decisions
- approval-inbox mutation
- dashboard POST/PUT/PATCH/DELETE routes
- dashboard/dashboard.py direct change unless explicitly approved
- direct main push
- force push
- branch protection bypass
- test weakening
- live/paper/shadow/risk/trading/broker/execution changes

Desired fields:
- execution_authority_present: OK|FAIL
- policy_doc_present: OK|FAIL
- classifier_present: OK|FAIL
- policy_source
- classifier_source
- policy_doc_hash
- classifier_hash
- unit_test_reference
- sample_decisions_ok
- last_validation_status
- last_validation_timestamp if available

Expected sample decisions:
- file_read + doc_non_policy + LOW -> AUTO_ALLOWED
- canonical_policy_doc edit + HIGH -> NEEDS_HUMAN
- live_broker_call -> PERMANENTLY_DENIED
- frozen_contract_mutate -> PERMANENTLY_DENIED
- unknown action/risk -> NEEDS_HUMAN

Open a PR against main.
Do not merge automatically.
```

---

# Prompt 25 — Autonomous Development Track A4

```text
Continue Autonomous Development Track hardening.

Active task:
A4 — Roadmap structure correction

Goal:
Repair semantic drift caused by mixing Autonomous Development Track work into the QRE product roadmap.
The roadmap must explicitly separate:
- Part I — Autonomous Development Track
- Part II — QRE Feature Build Track

Required statements:
- Autonomous Development Track is temporary hardening work required before resuming product feature development.
- QRE Feature Build Track remains governed by the original Roadmap v6.
- The operator maintains Roadmap v6 locally and will provide it as needed.
- After Autonomous Development Track completion, the next QRE Feature Build Track phase is v3.15.16 — Intelligent Routing Layer.

Do not reconstruct the full Roadmap v6 product plan unless explicitly requested by the operator.

Important constraints:
- This may be HIGH risk if canonical roadmap/governance docs change.
- Ask for operator approval if required by execution authority classification.
- Do not modify live/paper/shadow/risk/trading/broker/execution behavior.
- Do not mutate frozen contracts.

Expected deliverables:
- roadmap structure correction
- governance-compatible tests/checks
- handoff note

Validation expectations:
- governance_lint if available
- smoke tests if available
- no product roadmap reconstruction beyond required pointer
```

---

# Prompt 26 — Autonomous Development Track A5

```text
Continue Autonomous Development Track hardening.

Active task:
A5 — Proposal queue and loop-closure false-positive cleanup

Goal:
Reduce operator-inbox noise so NEEDS_HUMAN and blockers represent real decisions.

Known issue:
loop closure open / BLOCKED, human_needed approximately 183, likely from active-doc heading/preamble noise rather than true execution blockers.

Allowed:
- read-only proposal detection refinement
- false-positive filtering for H1/H2/preamble text
- archive-folder suppression already established
- tests proving real proposals still surface
- tests proving false positives are suppressed

Not allowed:
- broad suppression of governance proposals
- hiding real NEEDS_HUMAN items
- approval mutation
- dashboard mutation
- frozen contract mutation
- live/paper/shadow/risk/trading/broker/execution changes

Required behavior:
Continue detecting:
- explicit proposal blocks
- canonical governance changes
- roadmap changes requiring operator decision
- HIGH risk changes
- UNKNOWN risk changes
- protected-path changes

Suppress:
- plain document titles
- H1/H2 headings without actionable proposal payload
- introductory/preamble text
- archived roadmap/doc historical content
- stale already-resolved artifacts

Expected deliverables:
- refined proposal detection
- tests for true positives and false positives
- report of human_needed reduction if measurable
- handoff note

Validation expectations:
- relevant proposal queue tests
- governance_lint if available
- smoke tests if available
```

---

# Prompt 27 — Autonomous Development Track A6

```text
Continue Autonomous Development Track hardening.

Active task:
A6 — Autonomous backlog discipline

Goal:
Make the backlog actionable by the new authority model.

The system should distinguish:
- AUTO_ALLOWED low-risk work
- NEEDS_HUMAN operator-gated work
- PERMANENTLY_DENIED prohibited work
- stale/false-positive noise
- unknown/fail-safe items

Allowed:
- read-only classification of backlog/proposal items
- summary reports
- operator-visible queue grouping
- tests for classification correctness

Not allowed:
- automatic approval execution
- mutation of approval inbox
- direct main pushes
- force pushes
- branch-protection bypass
- test weakening
- live/paper/shadow/risk/trading/broker/execution behavior

Desired grouping:
1. Permanently denied
2. Needs human
3. Auto-allowed candidate work
4. Stale/resolved/noise
5. Unknown/fail-safe

Expected deliverables:
- backlog/reporting grouping
- tests for classification correctness
- operator-facing summary
- handoff note

Validation expectations:
- reporting/backlog tests
- governance_lint if available
- smoke tests if available
```

---

# Prompt 28 — Autonomous Development Track A7

```text
Continue Autonomous Development Track hardening.

Active task:
A7 — Final Autonomous Development readiness check

Goal:
Declare the Autonomous Development Track complete only after the control plane is coherent and observable.

Completion checklist:
1. Agent authority policy exists and is canonical.
2. Agent authority classifier exists and is tested exhaustively.
3. Classifier health is visible read-only in reporting/PWA.
4. Roadmap explicitly separates Autonomous Development Track from QRE Feature Build Track.
5. Proposal queue no longer produces major false-positive blocker noise.
6. Loop-closure blockers are real or cleared.
7. Operator inbox is actionable.
8. Governance/frozen/deploy/approval/authority health is visible.
9. Claude understands that the next product phase is v3.15.16 Intelligent Routing Layer from Roadmap v6.
10. No live/paper/shadow/risk/trading/broker/execution behavior has been changed during Autonomous Development hardening.

Final output:
Autonomous Development Track complete.
Return to QRE Feature Build Track.
Next product phase: v3.15.16 — Intelligent Routing Layer.
Canonical product-roadmap source: operator-provided Roadmap v6.

Expected deliverables:
- readiness report or handoff marker
- tests/checks appropriate to changed files
- no protected path violation
- no product execution behavior changes

Open a PR if repo files are changed.
Do not merge automatically unless the active governance permits it.
```

---

# Minimal Claude Code repo-integration prompt for these two docs

Use this prompt if the two documents were drafted outside the repo and need to be added.

```text
Create a new branch.

Add these docs exactly from the supplied content:
- docs/roadmap/qre_roadmap_v6_ade_operating_manual.md
- docs/roadmap/qre_roadmap_v6_phase_prompts.md

This is documentation-only.
Do not modify code.
Do not modify .claude/**.
Do not modify dashboard/dashboard.py.
Do not modify research_latest.json.
Do not modify strategy_matrix.csv.
Do not modify live/paper/shadow/risk/broker/execution paths.

Run governance/smoke checks appropriate for documentation-only changes if available.
Open a PR against main.
Do not merge automatically.
Return a handoff with branch, PR, files changed, checks run, and any limitations.
```
