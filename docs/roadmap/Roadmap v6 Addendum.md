Roadmap v6 Addendum
Mechanistic Behavior Diagnostics & External Intelligence Intake

## Execution Status (as of 2026-05-21)

Status: **DEFERRED — REFERENCE-ONLY**

Implementation-scope sections: **NOT ACTIVE**

Doctrine and §10 "Not Allowed" sections: **ACTIVE PROJECT-WIDE**

This addendum is preserved verbatim as architectural reference. It is
not active execution scope. No queue item, planner task, product-owner
backlog entry, or autonomous PR runner unit may be derived from this
addendum unless an explicit operator-approved ADR reactivates the
specific subsection. See
[`docs/governance/roadmap_scope_status.md`](../governance/roadmap_scope_status.md)
and
[`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](../adr/_drafts/ADR-018-roadmap-execution-reset.md)
for the reset record and reactivation gates.

Doctrine that remains binding regardless of execution status:

- Diagnostics do not trade.
- External/public data is not alpha.
- The §10 "Not Allowed" list remains project-wide invariant.

---

1. Purpose

This addendum extends Roadmap v6 with a first-class diagnostic layer for complex market behavior.

The QRE should not become:

indicator-combination factory
genetic alpha generator
black-box ML selector
random strategy mutator
live-risk optimizer

The QRE should become:

deterministic market-behavior research system

This addendum adds reusable diagnostics for:

tails
entropy
criticality
barriers
resonance
network structure
adversarial behavior
control stability
aftershocks
liquidity turbulence
evidence quorum
market language
null-model falsification

These diagnostics exist to:

explain
prioritize
falsify
route
sample
cool down
escalate
suppress
observe

They do not trade directly.

2. Core Rule

Add this principle to Roadmap v6:

Diagnostics do not trade.

A diagnostic may influence hypothesis priority, sampling, routing,
evidence scoring, cooldown, confirmation, suppression or observability.

A diagnostic may not directly create strategies, place trades,
mutate live risk, allocate capital, bypass policy governance,
or change frozen output contracts.

This is consistent with the existing strict layer mapping: Strategy Layer is signal generation only, Execution Layer owns order simulation/live execution and position sizing, and Evaluation/Orchestration remain separate.

3. New Roadmap Component

Add under Research Front Door Intelligence:

Mechanistic Behavior Diagnostics Layer

Placement:

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

Rationale:

Roadmap v6 already states the system must become behavior-first instead of indicator-first, reasoning about volatility transitions, trend persistence, liquidation reflexivity, continuation probability, exhaustion behavior, cross-asset structure, regime dependency and liquidity asymmetry. This addendum makes that behavior-first layer more explicit and operational.

4. Rename “Core Math Engine”

Do not call this a Core Math Engine.

Use:

Behavior Diagnostics Library

or:

Research Diagnostics Primitives

Reason:

Core Math Engine

sounds like a central strategy engine. That risks architecture drift.

The intended role is narrower:

pure deterministic diagnostic primitives
artifact-producing behavior analysis
no strategy generation
no execution behavior
no hidden state
5. Proposed Repo Structure

Planned architecture only; implementation should happen in scoped roadmap phases.

research/
  diagnostics/
    __init__.py

    tail.py              # power laws / tail asymmetry / fragility
    entropy.py           # information density / market orderliness
    criticality.py       # phase transitions / slowing down
    barrier.py           # probabilistic breakout / barrier pressure
    resonance.py         # cycle confluence / dominant periodicity
    null_models.py       # Brownian/random-walk/surrogate baselines

    network.py           # correlation graph / MST / contagion
    adversarial.py       # crowding / adverse selection / signal decay
    control.py           # policy stability / drift / oscillation
    seismic.py           # shock / aftershock / volatility decay
    turbulence.py        # liquidity turbulence / slippage convexity proxy
    quorum.py            # independent evidence quorum
    language.py          # tokenized market behavior / Zipf / grammar shift

research/
  external_intelligence/
    source_registry.py
    source_manifest_schema.py
    public_data_seed_registry.py
    freshness_checks.py
    quality_gates.py
    seed_artifact_writer.py

research/
  hypothesis_discovery/
    behavior_catalog.py
    behavior_hypotheses.py
    opportunity_scoring.py
    preset_feasibility.py
    campaign_seed_proposer.py

    external_intelligence_catalog.py
    physics_behavior_catalog.py
    mechanistic_behavior_catalog.py
    diagnostic_hypothesis_adapter.py

artifacts/
  diagnostics/
    behavior_diagnostics_latest.v1.json
    diagnostic_quality_latest.v1.json
    diagnostic_hypothesis_seeds_latest.v1.json

artifacts/
  external_intelligence/
    external_intelligence_latest.v1.json
    public_data_quality_latest.v1.json
    public_hypothesis_seed_candidates_latest.v1.json

Do not mutate:

research_latest.json
strategy_matrix.csv

New diagnostic information must live in sidecar artifacts.

6. Physics Concepts Mapping
6.1 Compact Mapping
Concept	Primary QRE Layer	Role
Power Laws	Market Behavior + Evidence + Policy	tail risk, convexity, fragility
Entropy	Market Behavior + Hypothesis Discovery	noise vs information, regime filter
Phase Transitions	Market Behavior + Policy	regime-switch / instability detection
Barrier / Tunneling	Strategy Mapping + Evidence	probabilistic breakout hypotheses
Resonance	Preset + Sampling Intelligence	cycle confluence / window selection
Brownian / Null Model	Evidence + Funnel/Policy	falsification baseline
6.2 Detailed Mapping
A. Power Laws

Layer:

Market Behavior Layer
Evidence Layer
Policy Layer
Shadow/Paper later

Applied to:

return tail exponent
drawdown tail exponent
volume spike distribution
winner/loss concentration
slippage/capacity tail growth
right-tail vs left-tail asymmetry

Outputs:

tail_alpha
tail_fit_quality
right_tail_dependency
left_tail_fragility
tail_asymmetry
expected_shortfall_proxy
outlier_dependency_flag

Downstream use:

prioritize convex/tail-aware hypotheses
detect hidden crash risk
suppress strategies dependent on one outlier
require stronger confirmation for left-tail-fragile candidates

Rule:

Power-law evidence may support a hypothesis.
It may not directly promote a candidate.
B. Entropy / Information Theory

Layer:

Market Behavior Layer
Hypothesis Discovery Layer
Evidence Layer
Policy Layer

Applied to:

Shannon entropy of returns/signals
approximate/sample entropy of price paths
entropy regime classification
signal information density
market orderliness

Outputs:

entropy_score
market_orderliness_score
noise_dominance_flag
information_density_score
entropy_regime

Downstream use:

suppress directional mappings in high-noise regimes
prioritize trend/continuation hypotheses in low-entropy regimes
measure whether a strategy extracts information or trades noise

Rule:

High entropy is not automatically bearish or bullish.
It is a research-routing and policy-diagnostic state.
C. Phase Transitions / Criticality

Layer:

Market Behavior Layer
Hypothesis Discovery Layer
Policy Layer
Shadow later

Applied to:

volatility regime transitions
autocorrelation drift
variance increase
critical slowing down
drawdown acceleration
regime switch warnings

Outputs:

criticality_score
regime_transition_probability_proxy
autocorrelation_drift
volatility_state_transition_flag
instability_warning

Downstream use:

propose regime-switch hypotheses
pause or suppress fragile campaigns near instability
require regime segmentation for unstable candidates

Rule:

Criticality diagnostics may trigger caution or segmentation.
They may not predict crashes as deterministic events.
D. Barrier / Tunneling

Treat “tunneling” as metaphorical/probabilistic barrier modeling, not literal quantum finance.

Layer:

Market Behavior Layer
Strategy Mapping
Preset Layer
Evidence Layer

Applied to:

support/resistance barrier crossing
volatility breakout through compression zones
range escape probability
barrier-crossing conditional on entropy/liquidity/compression

Outputs:

barrier_pressure_score
breakout_probability_proxy
failed_breakout_rate
post_breakout_decay
range_escape_score

Downstream use:

generate probabilistic breakout hypotheses
avoid hard deterministic support/resistance rules
test whether barrier breaks have continuation after costs

Rule:

Barrier diagnostics can seed breakout hypotheses.
They do not create direct breakout strategies.
E. Resonance / Harmonic Oscillators

Layer:

Market Behavior Layer
Preset Layer
Sampling Intelligence
Evidence Layer

Applied to:

cycle confluence
dominant period diagnostics
wavelet/Fourier-like periodicity proxies
multi-timeframe alignment
constructive/destructive interference proxies

Outputs:

dominant_cycle_period
cycle_stability_score
resonance_confluence_score
cycle_false_positive_rate
window_alignment_score

Downstream use:

adapt candidate preset windows to observed cycle regimes
prioritize hypotheses where short/long cycles align
suppress unstable cycle-fit overfitting

Rule:

Cycle fit must be checked against null models.
No “cycle = alpha” assumption.
F. Brownian / Random Walk / Null Models

Layer:

Market Behavior Layer
Evidence Layer
Funnel/Policy Layer

Applied to:

random-walk benchmarks
Brownian/geometric Brownian null simulations
shuffled-return tests
surrogate data tests
noise baselines

Outputs:

null_model_edge_gap
random_walk_similarity
surrogate_test_pass
noise_baseline_excess_return
false_discovery_warning

Downstream use:

reject hypotheses that do not beat simple null models
detect overfit behavior
provide baseline for entropy/tail/phase diagnostics

Rule:

Every exotic diagnostic should eventually face a null-model challenge.
7. Additional Complex-Systems Concepts Mapping
7.1 Summary Table
Concept	Verdict	Roadmap Fit	Allowed Form
Network Theory	Very strong	Add	cross-asset behavior diagnostic
Control Theory	Strong, later with guardrails	Add limited	stability/degradation diagnostics now; sizing later
Game Theory	Useful if reframed	Add	adversarial/liquidity diagnostic
Genetic Programming	Not now	Exclude	replace with deterministic evolutionary selection
Core Math Engine	Good idea, bad name	Rename	Behavior Diagnostics Library
Seismology / Aftershock	Strong	Add	shock/aftershock volatility diagnostics
Cybernetics / VSM	Strong	Add	governance/control-plane architecture
Fluid Dynamics / Turbulence	Good, later	Add limited	liquidity turbulence proxy; execution realism later
Biomimicry / Quorum	Useful if reframed	Add	independent evidence quorum
Linguistics / Info Foraging	Interesting, cautious	Add limited	pattern-language diagnostic, not candle mining
7.2 Network Theory

Layer:

Market Behavior Layer
Hypothesis Discovery Layer
Evidence Layer
Policy Layer
Portfolio Intelligence

Applied to:

correlation networks
minimum spanning trees
asset clustering
contagion
cross-asset lead/lag
correlation breakdown
risk-on/risk-off structure

Outputs:

correlation_density
mst_concentration
cluster_count
dominant_hub_asset
network_fragility_score
contagion_warning
diversification_breakdown_flag

Downstream use:

detect market-structure regime shifts
suppress overconcentrated campaigns
generate cross-asset behavior hypotheses
support portfolio intelligence and edge interaction analysis

Roadmap fit:

Roadmap v6 already includes cross-asset structure as a behavior-first research object and later v3.16.5 Portfolio Intelligence for edge correlation analysis, diversification-aware candidate selection and behavior interaction modeling.

7.3 Control Theory

Layer:

Policy Layer
Evidence Layer
Campaign Layer
Shadow later
Paper later
Live later

Applied now to:

policy stability
campaign throughput stability
expected vs observed outcome drift
signal-density drift
false-positive-rate drift
compute budget overshoot
policy oscillation

Outputs:

policy_error
evidence_drift
signal_density_drift
control_oscillation_flag
degradation_rate
throttle_recommendation

Downstream use now:

cool down unstable research paths
detect repeated overreaction by policy
prevent campaign allocation oscillation
monitor degradation before promotion

Allowed later:

paper exposure throttling
live risk-envelope feedback
drawdown throttle
kill-switch escalation

Not allowed now:

PID position sizing
automatic exposure increase
equity-curve chasing
live risk mutation

Roadmap fit:

v4/v5/v6 are the appropriate stages for real-time behavior validation, simulated capital deployment and controlled live capital. Roadmap v6 explicitly separates shadow realism, paper capital realism and live controlled deployment.

7.4 Game Theory

Reframe as:

Adversarial Market Behavior Diagnostics

Layer:

Market Behavior Layer
Hypothesis Discovery Layer
Evidence Layer
Policy Layer
Shadow later

Applied to:

crowding
adverse selection
liquidity traps
stop-hunt zones
fake breakouts
post-signal decay
predatory liquidity

Outputs:

adverse_selection_score
crowding_score
fake_breakout_rate
post_signal_decay
liquidity_trap_flag
predatory_regime_warning

Downstream use:

increase confirmation requirement
suppress fragile breakout hypotheses
route to liquidity-aware behavior families
evaluate signal decay in shadow

Not allowed:

random preset switching
mixed live strategies
stochastic orderflow hiding
unreproducible behavior

Rule:

Game theory is used to model adversarial market structure,
not to randomize the QRE.
7.5 Genetic Programming

Status:

Explicitly excluded for now.

Reason:

genetic programming tends to generate indicator combinations
Roadmap v6 wants persistent market behavior discovery
it risks strategy explosion, overfitting and black-box mutation

Allowed replacement:

Deterministic Evolutionary Selection

Layer:

Adaptive Research Learning
Failure → Action Mapping
Robustness Filtering
Candidate Clustering
Portfolio Intelligence

Allowed behavior:

behavior families survive, degrade, cool down or retire
mutation only through explicit Failure → Action rules
no free-form indicator generation
no stochastic genome search

Example:

insufficient_trades → higher timeframe
high_drawdown → volatility normalization
weak_stability → regime segmentation
left_tail_fragility → stricter confirmation
high_noise_entropy → suppress directional mapping

Roadmap fit:

Roadmap v6 already includes Failure → Action Mapping and later adaptive learning, strategy fitness scoring, candidate clustering and robustness filtering.

7.6 Seismology / Aftershock Modeling

Layer:

Market Behavior Layer
Hypothesis Discovery Layer
Evidence Layer
Policy Layer
Shadow later

Applied to:

market shocks
volatility aftershocks
post-crash decay
flash-move clustering
shock-induced continuation/reversal
cooldown periods

Outputs:

mainshock_detected
shock_magnitude_z
aftershock_decay_rate
volatility_half_life_bars
shock_cluster_intensity
post_shock_directional_bias
cooldown_recommended_until

Downstream use:

generate post-shock continuation/reversal hypotheses
cool down campaigns after extreme market events
test volatility decay profiles
validate real-time shock response in shadow

Rule:

Seismology diagnostics model shock processes.
They do not predict crashes deterministically.
7.7 Cybernetics / Viable System Model

Layer:

Architecture
Policy Layer
Governance
Observability
Autonomous Development Track
QRE Feature Build Track

Applied to:

recursive control
layer health
self-audit
escalation paths
authority boundaries
failure containment
operator-light governance

VSM mapping:

VSM System	QRE Equivalent
System 1	campaigns, diagnostics, research workers
System 2	queue coordination, worker leases, admission control
System 3	policy engine, compute allocator, failure memory
System 4	hypothesis discovery, external intelligence, adaptive learning
System 5	mission, governance, frozen contracts, operator constraints

Outputs:

layer_health_status
recursive_alarm
policy_boundary_violation
self_audit_required
governance_escalation_required

Downstream use:

detect when one layer’s failure requires another layer to audit itself
keep autonomous QRE behavior inside guardrails
separate development authority from trading/research execution authority

Roadmap/guardrail fit:

The Autonomous Development Track explicitly separates development authority from QRE trading/research execution authority and states that agent execution authority does not grant trading execution authority. It also prohibits live/paper/shadow/risk/trading/broker/execution behavior changes during autonomous-development hardening.

7.8 Fluid Dynamics / Turbulence

Layer:

Market Behavior Layer
Evidence Layer
v4 Shadow Execution Realism
v5 Paper Risk/Performance
v6 Live Risk/Execution

Applied now to proxies:

range/volume imbalance
realized volatility burst
wickiness
gap frequency
spread proxy where available
volume shock
liquidity depth proxy

Applied later to richer data:

order book depth
spread
market impact
slippage convexity
latency effects
order-size stress

Outputs:

liquidity_turbulence_score
laminar_regime_flag
slippage_convexity_proxy
flow_break_risk
order_size_stress_score

Downstream use:

classify execution-risk regimes
test candidate performance in turbulent vs laminar regimes
support shadow execution realism
inform paper/live risk envelopes later

Roadmap fit:

Roadmap v6 already places slippage realism, liquidity realism, latency-aware diagnostics and signal decay measurement in v4.2 Execution Realism.

7.9 Biomimicry / Quorum Sensing

Reframe as:

Independent Evidence Quorum

Layer:

Evidence Layer
Policy Layer
Hypothesis Discovery Layer
Adaptive Research Learning

Applied to:

multi-asset confirmation
multi-timeframe confirmation
multi-regime confirmation
multi-diagnostic confirmation
multi-source public data confirmation
OOS-window confirmation
null-model confirmation

Outputs:

independent_confirmations
required_confirmations
quorum_status
confirmation_diversity_score
single_source_dependency_flag

Downstream use:

escalate hypotheses only when independent evidence agrees
mark near-pass candidates
suppress single-diagnostic false positives
reduce dependency on one asset/timeframe/regime

Not allowed:

live ensemble voting
capital migration to “fruiting bodies”
mycelium-style capital allocation in research phase

Rule:

Quorum sensing is a promotion/evidence guardrail,
not a live trade trigger.
7.10 Linguistics / Information Foraging

Reframe as:

Market Language Diagnostics

Layer:

Market Behavior Layer
Hypothesis Discovery Layer
Evidence Layer
Observability Layer

Applied to:

tokenized return/volatility/volume states
sequence rarity
Zipf-like frequency distribution
grammar shifts
repetition/compression/burstiness
market vocabulary collapse

Outputs:

token_entropy
zipf_slope
sequence_rarity_score
grammar_shift_score
message_vs_noise_score
vocabulary_collapse_flag

Downstream use:

identify symbolic behavior regimes
seed hypotheses about compression → expansion sequences
explain market behavior in observable token language
compare sequence behavior against null models

Not allowed:

candle-pattern mining
rare-pattern-equals-alpha assumptions
NLP-heavy social pipeline before data quality gates exist

Rule:

Market language diagnostics must be null-model tested.
They are not candle folklore.
8. External Intelligence Intake
8.1 Principle

Add to Roadmap v6:

External/public data is not alpha.

External intelligence is an unvalidated prior.
Only QRE-validated, OOS-stable, cost-aware, execution-realistic,
policy-approved behavior can become edge.
8.2 No Paid Data for Now

For now:

no paid data feeds
no vendor alpha
no commercial signal libraries
no private alternative-data vendors

Allowed:

public/free market data
public/free macro data
public/free filings/event data
repo-resident manifests
small seed snapshots where license permits
derived diagnostic artifacts
reproducible fetch instructions
8.3 Public Data Sources
Source	Type	QRE Use
Yahoo/yfinance	equities, ETFs, index proxies	trend, volatility, entropy, null baselines
Stooq	historical market data	cross-check, long-history daily/hourly baselines
Binance public klines/data	crypto OHLCV	crypto tails, volatility, barrier, entropy, aftershocks
Bitvavo public candles	EUR crypto OHLCV	exchange-specific validation for EUR crypto pairs
CoinGecko public/free	crypto metadata, market cap, volume, dominance	broad crypto context, dominance regimes
FRED	macro/economic time series	macro regime context, rates/liquidity/inflation proxies
SEC EDGAR	filings/XBRL/company facts	equity event/fundamental context, event flags
8.4 Source Manifest Fields

Every source needs:

source_id
source_type
access_method
expected_latency
expected_freshness
asset_coverage
timeframe_coverage
allowed_use
known_limitations
license_terms_reference
reproducibility_method
quality_gates
8.5 Public Data Quality Gates

Required quality gates:

freshness check
missing data check
timestamp monotonicity
duplicate bar check
outlier check
coverage check
source agreement check where possible
license/terms metadata present

No hypothesis seed should be promoted from public data without passing source quality checks.

9. Changes to Roadmap v6 Phases
v3.15.16 — Intelligent Routing Layer

Add:

diagnostic-aware routing
external-intelligence-aware routing
network-aware routing
entropy-aware routing
tail-aware routing
criticality-aware routing
quorum-aware routing
dead-zone suppression by diagnostic failure

Routing should prioritize:

highest expected information gain
most orthogonal behavior hypothesis
best public-data quality
lowest dead-zone risk
strongest independent diagnostic support

Roadmap v6 already defines v3.15.16 as behavior-aware routing that prioritizes informative exploration instead of the most available preset.

v3.15.17 — Sampling Intelligence

Add:

tail-aware sampling
entropy-stratified sampling
phase-transition-zone sampling
barrier-condition sampling
resonance-window sampling
network-regime sampling
post-shock sampling
null-model control sampling

Sampling should answer:

Where does this hypothesis contain the most information?
Where is it most likely to fail?
Where is it most likely overfit?
Where does regime/context materially change behavior?

Roadmap v6 already frames this phase as deterministic intelligent sampling focused on high-information exploration instead of brute-forcing large grids.

v3.15.18 — Research Observability Expansion

Add observable surfaces for:

diagnostic contribution explanation
external data lineage
public data quality status
hypothesis seed provenance
physics/complex-systems diagnostic surfaces
null-model comparison
quorum status
network state
entropy/tail/criticality regime

The operator should see:

why the engine explored this
which diagnostics supported it
which diagnostics contradicted it
which public data source seeded it
whether source quality was acceptable
why the hypothesis failed or survived

Roadmap v6 already says this phase must make research reasoning transparent before autonomous hypothesis discovery, otherwise autonomous discovery becomes opaque.

v3.15.19 — Hypothesis Discovery Engine

Extend planned modules:

Existing:

behavior_catalog.py
behavior_hypotheses.py
opportunity_scoring.py
preset_feasibility.py
campaign_seed_proposer.py

Add:

external_intelligence_catalog.py
public_data_seed_registry.py
physics_behavior_catalog.py
mechanistic_behavior_catalog.py
diagnostic_hypothesis_adapter.py

New hypothesis seed examples:

tail_asymmetry_crypto_4h_v0
low_entropy_trend_continuation_equities_daily_v0
post_shock_volatility_decay_btc_1h_v0
network_contagion_equities_daily_v0
barrier_pressure_breakout_crypto_15m_v0
liquidity_turbulence_breakout_failure_v0
quorum_confirmed_volatility_transition_v0
market_language_compression_expansion_v0

Constraints remain:

deterministic
inspectable
artifact-driven
explainable
non-black-box
no hidden strategy invention
no executable strategy auto-writing

Roadmap v6 already states Hypothesis Discovery must propose market behavior hypotheses, plausible mechanisms, strategy mappings, feasible preset mappings and exploration priority — not prediction certainty or alpha certainty.

v3.15.20 — Failure → Action Mapping

Add deterministic mappings:

high_entropy
→ suppress directional strategy mapping

weak_tail_fit
→ do not prioritize tail-convex hypothesis

left_tail_fragility
→ require stronger confirmation

phase_transition_unstable
→ require regime segmentation

barrier_false_positive_high
→ increase confirmation requirement

resonance_not_persistent
→ downgrade cycle-confluence hypothesis

network_concentration_high
→ suppress portfolio-overlapping campaigns

post_shock_aftershock_unstable
→ cooldown new campaigns

liquidity_turbulence_high
→ defer execution-sensitive mappings to shadow/paper validation

quorum_insufficient
→ keep as hypothesis seed, do not escalate

null_model_not_beaten
→ reject or demote hypothesis family

This extends Roadmap v6’s existing Failure → Action Mapping direction, where failures become deterministic adaptive actions rather than static rejection.

v3.16.x — Adaptive Research Learning

Add:

diagnostic utility tracking
behavior-family fitness by diagnostic family
quorum effectiveness learning
public source usefulness scoring
diagnostic false-positive tracking
diagnostic dead-zone suppression

The system should learn:

which diagnostics actually improve survivor quality
which diagnostics cause false positives
which public data sources produce useful hypothesis seeds
which behavior families deserve more compute
v4.x — Shadow Trading

Add:

diagnostic parity in real-time
tail/entropy/criticality/network state parity
liquidity turbulence observed vs expected
post-shock response parity
signal decay under adversarial regimes

Use only after candidates exist.

Roadmap v6 defines v4 as real-time behavioral validation without real capital, focused on parity, signal integrity, timing realism and operational observability.

v5.x — Paper Trading

Add:

tail dependency under simulated capital
expected shortfall under diagnostic regimes
drawdown governance informed by diagnostics
paper degradation by entropy/network/turbulence regimes
quorum-confirmed candidate paper behavior

Roadmap v6 defines v5 as economic viability under simulated capital deployment.

v6.x — Live Trading

Add only after validation:

diagnostics may inform live risk governance
diagnostics may support kill-switch context
diagnostics may influence capital scaling only through approved risk envelope
diagnostics may not directly create live trades
diagnostics may not bypass whitelist/reconciliation/kill switches

Roadmap v6 defines live as deploying validated behaviors with controlled capital, operational governance and execution safety.

10. Not Allowed

Add this explicit section:

Not allowed before explicit future roadmap approval:

- paid data feeds
- vendor alpha signals
- genetic programming
- automatic indicator invention
- hidden ML/RL selector
- stochastic strategy mutation
- random preset switching
- PID position sizing in research phase
- live exposure control from diagnostics
- execution-layer behavior changes
- broker/order placement changes
- capital allocation changes
- mutation of research_latest.json
- mutation of strategy_matrix.csv
- frontend business logic
- non-reproducible hypothesis generation

This matches existing project discipline: no strategy explosion, no hidden black-box selection, deterministic/artifact-driven/reviewable behavior, and no unsafe execution/risk/live path changes.

11. Definition of Done for This Addendum

Roadmap v6 is successfully updated when:

1. Roadmap v6 includes External Intelligence Intake as public/free-data hypothesis seed input.

2. Roadmap v6 includes Mechanistic Behavior Diagnostics as first-class research diagnostics.

3. Physics concepts are mapped to QRE layers, diagnostic outputs and downstream uses.

4. Network, control, game-theoretic, seismic, cybernetic, turbulence,
   quorum and language concepts are mapped with guardrails.

5. Genetic programming is explicitly excluded for now.

6. Core Math Engine is renamed to Behavior Diagnostics Library or Research Diagnostics Primitives.

7. Diagnostics are explicitly prohibited from direct trading, live capital allocation,
   broker behavior, execution mutation or frozen contract mutation.

8. v3.15.16 through v3.15.20 are updated with diagnostic-aware routing,
   sampling, observability, hypothesis discovery and failure-action mappings.

9. v3.16.x, v4.x, v5.x and v6.x include later-stage validation roles
   for diagnostics without premature live use.

10. The operator-light/no-touch intent is preserved:
    the QRE can autonomously prioritize research, but only inside deterministic,
    artifact-driven, inspectable and policy-governed guardrails.
