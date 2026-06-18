# Roadmap v6 Addendum 2
## State, Sequential, Knowledge & Retrieval Intelligence

## Execution Status (as of 2026-05-21)

Status: **DEFERRED — REFERENCE-ONLY**

Implementation-scope sections: **NOT ACTIVE**

Doctrine and §9 "Not Allowed" sections: **ACTIVE PROJECT-WIDE**

Current QRE implementation sequencing is governed by
[`docs/roadmap/qre_maturity_roadmap_to_100.md`](qre_maturity_roadmap_to_100.md).
This addendum remains supporting doctrine and historical reference only
unless the maturity roadmap or a future operator-approved ADR explicitly
incorporates a subsection.

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

- State models do not trade.
- Retrieval is context, not authority.
- Knowledge graphs are lineage, not truth.
- The §9 "Not Allowed" list remains project-wide invariant.

---

## 1. Purpose

This addendum extends:

```text
Roadmap v6 Addendum — Mechanistic Behavior Diagnostics & External Intelligence Intake
```

It is a direct follow-up addendum, not a replacement.

The first addendum introduced:

```text
External Intelligence Intake
Mechanistic Behavior Diagnostics Layer
Behavior Diagnostics Library / Research Diagnostics Primitives
physics-informed diagnostics
complex-systems diagnostics
public-data hypothesis seeds
```

This second addendum adds a complementary capability family:

```text
State, Sequential, Knowledge & Retrieval Intelligence
```

The purpose is to make the QRE better at:

```text
modeling market state transitions
recognizing latent regimes
tracking regime duration
building deterministic lifecycle state machines
falsifying hypotheses against no-edge processes
organizing research memory
retrieving prior evidence
connecting hypotheses, diagnostics, data sources and failures
```

This addendum keeps the same core philosophy:

```text
Diagnostics do not trade.
Retrieval does not decide trades.
Knowledge graphs do not certify truth.
Sequence models do not authorize capital.
```

The QRE should not become:

```text
Markov-only trading system
HMM alpha engine
black-box sequence predictor
RNN/LSTM/Transformer price model
RLAIF self-optimizing agent
GNN price-prediction engine
autonomous strategy inventor
```

The QRE should become:

```text
deterministic market-behavior research system
with state-aware diagnostics and searchable research memory
```

---

## 2. Relationship to Addendum 1

Addendum 1 introduced the following extended architecture:

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

Addendum 2 inserts one additional intelligence layer between external/public data and diagnostics:

```text
External Intelligence Intake
↓
Research Knowledge & Retrieval Layer
↓
State & Sequential Diagnostics Layer
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

Interpretation:

```text
External Intelligence Intake
= public/free source ingestion and source manifests

Research Knowledge & Retrieval Layer
= research memory, ontology, entity resolution, retrieval and lineage

State & Sequential Diagnostics Layer
= Markov/state transition, HMM, Semi-Markov, FSM, queueing and null-process diagnostics

Mechanistic Behavior Diagnostics Layer
= tail, entropy, criticality, network, adversarial, seismic, turbulence, quorum and language diagnostics
```

---

## 3. Core Rules

Add these rules to the Addendum 1 principles.

```text
State models do not trade.
```

A state model may influence:

```text
hypothesis priority
campaign routing
sampling regions
regime compatibility
evidence scoring
cooldown duration
suppression
confirmation requirements
shadow parity checks
```

A state model may not:

```text
place trades
authorize live/paper/shadow deployment
allocate capital
mutate live risk
promote a candidate by itself
bypass policy governance
bypass null-model validation
change frozen output contracts
```

```text
Retrieval is context, not authority.
```

Retrieval may:

```text
find prior hypotheses
find prior failures
find related diagnostics
find source lineage
find comparable campaigns
support operator explanation
support bounded hypothesis expansion
```

Retrieval may not:

```text
rank trades
rank live candidates by itself
authorize promotion
auto-generate executable strategies
override evidence policy
replace deterministic scoring
```

```text
Knowledge graphs are lineage, not truth.
```

Knowledge graphs may:

```text
link assets, hypotheses, diagnostics, sources, campaigns, evidence, failures and policy actions
expose contradictions
support duplicate suppression
support provenance and explainability
```

Knowledge graphs may not:

```text
certify alpha
certify causality
replace out-of-sample validation
replace null-model testing
replace policy gates
```

---

## 4. New Roadmap Components

Add under the Addendum 1 architecture:

```text
Research Knowledge & Retrieval Layer
State & Sequential Diagnostics Layer
```

### 4.1 Research Knowledge & Retrieval Layer

Purpose:

```text
Make QRE research memory searchable, deduplicated, linkable and explainable.
```

This layer stores and retrieves:

```text
canonical entities
asset aliases
source metadata
behavior taxonomies
hypothesis lineage
diagnostic evidence
campaign outcomes
failure memory
policy actions
contradictory evidence
similar prior research paths
```

### 4.2 State & Sequential Diagnostics Layer

Purpose:

```text
Model market and research behavior as deterministic, inspectable state processes.
```

This layer estimates:

```text
state transition probabilities
latent regime probabilities
state persistence
regime dwell time
transition entropy
state-conditioned signal density
queue pressure
lifecycle state validity
no-edge/null-process baselines
```

---

## 5. Proposed Repo Structure

Planned architecture only; implementation should happen in scoped roadmap phases.

```text
research/
  diagnostics/
    state_transitions.py       # Markov chains / transition matrices
    latent_regimes.py          # HMM / latent regime diagnostics, later
    regime_duration.py         # Semi-Markov / dwell-time diagnostics
    sequence_diagnostics.py    # higher-order state sequence diagnostics
    null_processes.py          # martingale / random walk / surrogate baselines
    state_machines.py          # deterministic lifecycle / policy FSM helpers
    queueing.py                # research queue / throughput diagnostics

research/
  knowledge/
    ontology.py                # canonical behavior/entity taxonomy
    entity_resolution.py       # ticker/source/behavior alias normalization
    knowledge_graph.py         # nodes/edges for hypotheses/evidence/failures
    graph_export.py            # repo-resident graph artifact writer
    lineage.py                 # source → hypothesis → campaign → evidence lineage

research/
  retrieval/
    keyword_index.py           # deterministic sparse/keyword search
    hybrid_index.py            # dense+sparse scaffold, optional later
    rank_fusion.py             # Reciprocal Rank Fusion
    rerank.py                  # optional cross-encoder interface, later
    retrieval_artifacts.py     # sidecar output writer

research/
  hypothesis_discovery/
    state_hypothesis_adapter.py
    knowledge_context_adapter.py
    retrieval_context_adapter.py

artifacts/
  state_diagnostics/
    state_transition_latest.v1.json
    latent_regime_latest.v1.json
    regime_duration_latest.v1.json
    null_processes_latest.v1.json
    queueing_diagnostics_latest.v1.json

artifacts/
  knowledge/
    ontology_latest.v1.json
    entity_resolution_latest.v1.json
    knowledge_graph_latest.v1.json
    lineage_latest.v1.json

artifacts/
  retrieval/
    retrieval_index_latest.v1.json
    retrieval_quality_latest.v1.json
    fused_search_results_latest.v1.json
```

Do not mutate:

```text
research_latest.json
strategy_matrix.csv
```

New state, knowledge and retrieval information must live in sidecar artifacts.

---

# 6. State & Sequential Diagnostics Mapping

## 6.1 Summary Table

| Concept | Verdict | Roadmap Fit | Allowed Form |
|---|---:|---:|---|
| Markov Chains | Strong | Add | state-transition diagnostic |
| Hidden Markov Models | Very strong later | Add later | latent regime diagnostic |
| Semi-Markov Processes | Strong | Add later | regime-duration / dwell-time diagnostic |
| Higher-Order Markov Chains | Useful, risky | Add limited | short-order sequence diagnostic |
| Particle Filters / SMC | Interesting later | Reserve | online regime belief tracking in shadow/paper |
| Martingales | Very useful | Add | no-edge baseline diagnostic |
| Random Walks | Required | Add | null-model / surrogate baseline |
| Finite State Machines | Very strong | Add | deterministic lifecycle/policy state framework |
| Queueing Theory | Strong | Add | research throughput / queue-pressure diagnostic |
| RNN/LSTM | Not now | Exclude from v3.x | future benchmark only |
| Transformers for price prediction | Not now | Exclude | possible document intelligence later |
| State Space Models / Mamba | Not now | Park | future long-sequence research-memory benchmark |

---

## 6.2 Markov Chains / State Transition Diagnostics

Layer:

```text
Market Behavior Layer
Hypothesis Discovery Layer
Intelligent Routing
Sampling Intelligence
Evidence Layer
Policy Layer
Shadow later
```

Applied to:

```text
volatility state transitions
compression → expansion
range → breakout
trend → exhaustion
shock → aftershock
low entropy → high entropy
liquidity calm → liquidity turbulence
asset/network regime shifts
```

Outputs:

```text
state_transition_matrix
state_persistence_score
transition_entropy
dominant_transition_path
regime_switch_probability_proxy
state_conditioned_signal_density
null_transition_edge_gap
```

Downstream use:

```text
prioritize hypotheses with stable transition structure
suppress hypotheses in high-transition-entropy regimes
route campaigns toward high-information transition zones
sample around unstable state boundaries
compare transition behavior against shuffled/null models
validate transition parity in shadow later
```

Rule:

```text
Markov diagnostics estimate state-transition structure.
They do not predict the next candle or authorize trades.
```

Example states:

```text
S0 = low_vol_range
S1 = low_vol_uptrend
S2 = high_vol_uptrend
S3 = high_vol_downtrend
S4 = post_shock_aftershock
S5 = high_entropy_noise
S6 = liquidity_turbulence
```

Example interpretation:

```text
low_entropy_compression
→ volatility_expansion
→ continuation_probability_proxy = 0.63
→ expected_information_gain = high
→ route campaign toward breakout/continuation hypothesis
```

---

## 6.3 Hidden Markov Models / Latent Regime Diagnostics

Status:

```text
Add later, primarily in v3.16.2 Regime Intelligence.
```

Layer:

```text
Market Behavior Layer
Regime Intelligence
Hypothesis Discovery Layer
Evidence Layer
Policy Layer
Shadow/Paper later
```

Applied to:

```text
latent volatility regimes
trend/range regimes
risk-on/risk-off regimes
liquidity stress regimes
post-shock regimes
entropy/noise regimes
```

Outputs:

```text
latent_regime_probabilities
most_likely_regime
regime_persistence_score
regime_transition_probability
regime_uncertainty_score
regime_conditioned_signal_density
```

Downstream use:

```text
route campaigns only to compatible regimes
suppress hypotheses with high regime uncertainty
compare strategy behavior across inferred regimes
detect regime mismatch before promotion
validate shadow/paper degradation by regime
```

Rule:

```text
HMM regimes are context, not trade signals.
No HMM-only strategy promotion.
```

---

## 6.4 Semi-Markov / Regime Duration Diagnostics

Layer:

```text
Market Behavior Layer
Sampling Intelligence
Evidence Layer
Policy Layer
Seismology / Aftershock Diagnostics
```

Applied to:

```text
trend duration
volatility cluster duration
post-shock cooldown duration
range persistence
liquidity stress duration
high-entropy noise duration
```

Outputs:

```text
state_dwell_time_distribution
expected_remaining_state_duration
regime_half_life
duration_anomaly_score
cooldown_duration_recommendation
```

Downstream use:

```text
determine whether a regime is early, mature or exhausted
avoid entering hypotheses near regime exhaustion
set research cooldown after shock events
sample regime-duration buckets
support aftershock decay modeling
```

Rule:

```text
Duration diagnostics may recommend cooldown or segmentation.
They may not directly stop or start live trading in v3.x.
```

---

## 6.5 Higher-Order State Sequence Diagnostics

Layer:

```text
Market Behavior Layer
Hypothesis Discovery Layer
Market Language Diagnostics
Evidence Layer
```

Applied to:

```text
compression → expansion → continuation
shock → expansion → pullback
range → false breakout → reversal
low entropy → barrier pressure → breakout failure
```

Outputs:

```text
sequence_transition_probability
state_sequence_rarity
sequence_persistence_score
sequence_null_edge_gap
sparse_transition_warning
```

Downstream use:

```text
seed sequence-aware behavior hypotheses
identify structured market sequences
compare sequences against null/surrogate baselines
suppress sparse overfit transition paths
```

Guardrails:

```text
Use only short order initially, e.g. order-2.
Order-3 requires explicit data-density checks.
Reject sparse transition tables.
Require null-model comparison.
```

Rule:

```text
Sequence rarity is not alpha.
Sequence rarity is only a hypothesis seed.
```

---

## 6.6 Particle Filters / Sequential Monte Carlo

Status:

```text
Reserve for v4/v5 after deterministic regime diagnostics are mature.
```

Layer:

```text
Shadow v4
Paper v5
Live-risk context v6 only after approval
```

Applied to:

```text
real-time regime belief
live degradation tracking
signal parity drift
post-shock uncertainty
liquidity stress belief
```

Outputs:

```text
online_regime_belief
belief_uncertainty
belief_drift
particle_degeneracy_warning
shadow_regime_parity_gap
```

Downstream use:

```text
monitor real-time regime uncertainty
track drift between backtest/shadow/paper behavior
support later risk-context observability
```

Rule:

```text
Particle filters are not part of v3.x research-intelligence core.
They are reserved for real-time validation phases.
```

---

## 6.7 Martingale / No-Edge Baseline Diagnostics

Layer:

```text
Evidence Layer
Funnel Layer
Policy Layer
Null Models
```

Applied to:

```text
conditional expected return
no-edge hypothesis testing
optional stopping risk
overfit expectancy detection
random-entry baseline comparison
```

Outputs:

```text
martingale_consistency_score
conditional_drift_edge
no_edge_warning
expected_value_gap
optional_stopping_risk_flag
```

Downstream use:

```text
reject hypotheses that do not beat a no-edge baseline
detect strategies relying on optional stopping illusion
flag overfit expectancy
compare candidate return path to martingale-like behavior
```

Rule:

```text
A candidate that cannot beat a martingale/no-edge baseline should not escalate.
```

---

## 6.8 Random Walk / Surrogate Process Diagnostics

Layer:

```text
Market Behavior Layer
Evidence Layer
Funnel/Policy Layer
```

Applied to:

```text
shuffled returns
bootstrapped paths
Brownian/geometric Brownian simulations
randomized signal timings
random-entry baselines
surrogate transition matrices
```

Outputs:

```text
null_model_edge_gap
random_walk_similarity
surrogate_test_pass
noise_baseline_excess_return
false_discovery_warning
```

Downstream use:

```text
reject hypotheses that do not beat simple null models
detect overfit behavior
provide baseline for Markov/HMM/sequence diagnostics
challenge every exotic diagnostic against random behavior
```

Rule:

```text
Every state or sequence diagnostic should eventually face a null-model challenge.
```

---

## 6.9 Finite State Machines / Deterministic Lifecycle Governance

Layer:

```text
Campaign Layer
Funnel Layer
Evidence Layer
Policy Layer
Governance
Research Observability
```

Applied to:

```text
campaign lifecycle
candidate lifecycle
hypothesis escalation
promotion/demotion
cooldown/retirement
policy state validity
failure-action state transitions
```

Outputs:

```text
current_state
allowed_transitions
blocked_transition_reason
next_policy_action
state_audit_trail
invalid_transition_warning
```

Downstream use:

```text
enforce deterministic lifecycle transitions
make policy transitions auditable
prevent accidental promotion bypass
explain blocked transitions
support operator-readable governance state
```

Example transitions:

```text
hypothesis_seed → campaign_candidate
campaign_candidate → exploratory_screening
exploratory_pass → promotion_candidate
promotion_fail → cooldown
repeated_fail → retire
diagnostic_fail → suppress
```

Rule:

```text
FSMs are governance primitives, not alpha models.
```

---

## 6.10 Queueing / Research Throughput Diagnostics

Layer:

```text
Campaign Layer
Intelligent Routing
Sampling Intelligence
Research Observability
Autonomous Development reporting where appropriate
```

Applied to:

```text
campaign queue
worker lease/admission control
compute budget allocation
research throughput
backlog latency
dead-zone congestion
operator-inbox pressure
```

Outputs:

```text
queue_pressure
expected_wait_time
worker_utilization
throughput_rate
dead_zone_queue_load
admission_control_reason
queue_starvation_warning
```

Downstream use:

```text
prioritize high-information campaigns
avoid queue saturation by low-value runs
route compute away from dead zones
explain why a campaign waits
detect research bottlenecks
support no-touch campaign discipline
```

Rule:

```text
Queueing diagnostics optimize research throughput.
They do not allocate trading capital.
```

---

## 6.11 Excluded Sequence Models for v3.x

Do not add to v3.x core:

```text
RNNs
LSTMs
Transformers for price prediction
State Space Models / Mamba for price prediction
open-ended sequence-model alpha generators
```

Reason:

```text
black-box risk
data hunger
overfit risk
harder falsification
harder explainability
architecture drift risk
potential violation of deterministic, inspectable, artifact-driven constraints
```

Possible future allowed uses:

```text
document summarization
filing/event classification
research report parsing
artifact sequence compression
research-memory benchmark
operator-facing explanation support
```

Not allowed:

```text
price direction prediction
trade selection
candidate promotion
capital allocation
live risk mutation
```

---

# 7. Research Knowledge & Retrieval Mapping

## 7.1 Summary Table

| Concept | Verdict | Roadmap Fit | Allowed Form |
|---|---:|---:|---|
| Knowledge Graphs | Very strong | Add | research memory / lineage graph |
| Ontologies | Very strong | Add | canonical taxonomy |
| Entity Resolution / Coreference | Strong | Add | canonicalization and duplicate suppression |
| Hybrid Search | Strong | Add scaffold | research retrieval infra |
| Reciprocal Rank Fusion | Strong | Add | deterministic rank fusion |
| Cross-Encoder Rerankers | Useful later | Add optional later | retrieval precision only |
| Bayesian Networks | Strong later | Add later | evidence dependency graph |
| Graph Neural Networks | Not now | Reserve | future benchmark, not price predictor |
| Tree/Graph-of-Thoughts | Risky | Add only bounded | graph-of-hypotheses expansion |
| RLAIF | Not now | Exclude | replace with deterministic feedback metrics |
| SSM/Mamba | Not now | Park | future document/research-memory benchmark |

---

## 7.2 Knowledge Graphs / Research Memory Graph

Layer:

```text
External Intelligence Intake
Research Knowledge & Retrieval Layer
Hypothesis Discovery Layer
Evidence Layer
Policy Layer
Research Observability
Adaptive Research Learning
```

Applied to:

```text
asset relationships
behavior families
diagnostic lineage
public data sources
hypothesis provenance
campaign outcomes
evidence support and contradiction
failure memory
policy actions
```

Outputs:

```text
knowledge_graph_latest.v1.json
node_count
edge_count
orphan_node_warning
contradiction_edges
lineage_path
related_hypothesis_ids
```

Example nodes:

```text
Asset: BTC/EUR
Behavior: volatility_compression_expansion
Diagnostic: entropy_score
Diagnostic: tail_asymmetry
Dataset: binance_public_klines
Hypothesis: low_entropy_breakout_continuation_crypto_1h_v0
Campaign: campaign_2026_05_12_001
Evidence: exploratory_pass
Failure: high_entropy_false_positive
PolicyAction: suppress_directional_mapping
```

Example edges:

```text
Asset HAS_BEHAVIOR Behavior
Hypothesis USES_DIAGNOSTIC Diagnostic
Dataset SUPPORTS Hypothesis
Campaign TESTS Hypothesis
Evidence CONTRADICTS Hypothesis
Failure TRIGGERS PolicyAction
Behavior BELONGS_TO Family
```

Downstream use:

```text
retrieve related prior hypotheses
suppress duplicate research paths
expose provenance and lineage
connect failures to policy actions
surface contradictory evidence
support adaptive research learning
```

Rule:

```text
Knowledge graphs expose relationships and lineage.
They do not certify edge or causality.
```

---

## 7.3 Ontologies / Canonical Taxonomy

Layer:

```text
External Intelligence Intake
Research Knowledge & Retrieval Layer
Hypothesis Discovery Layer
Research Observability
```

Applied to:

```text
asset taxonomy
behavior taxonomy
diagnostic taxonomy
source taxonomy
failure taxonomy
policy-action taxonomy
regime taxonomy
```

Outputs:

```text
ontology_latest.v1.json
canonical_entity_id
canonical_behavior_id
canonical_diagnostic_id
alias_resolution_table
unknown_taxonomy_term_warning
```

Downstream use:

```text
normalize public data sources
prevent duplicate hypotheses
map aliases to canonical entities
make retrieval precise
make lineage explainable
```

Rule:

```text
Ontology is a controlled vocabulary, not a prediction system.
```

---

## 7.4 Entity Resolution / Cross-Document Coreference

Layer:

```text
External Intelligence Intake
Research Knowledge & Retrieval Layer
Hypothesis Discovery Layer
Adaptive Research Learning
```

Applied to:

```text
ticker aliases
exchange symbol normalization
asset names
behavior synonyms
source aliases
event identifiers
filing/company identifiers
```

Examples:

```text
BTC = Bitcoin = BTC/EUR = BTCUSDT = XBT
volatility compression = squeeze = low realized volatility = range compression
tail risk = left-tail fragility = crash risk = expected shortfall concern
```

Outputs:

```text
entity_resolution_latest.v1.json
canonical_id
resolved_aliases
ambiguous_entity_warning
duplicate_hypothesis_warning
single_source_dependency_flag
```

Downstream use:

```text
deduplicate hypotheses
merge evidence correctly
avoid duplicate failures
connect external data to internal artifacts
improve retrieval quality
```

Rule:

```text
Prefer deterministic alias maps first.
ML-assisted entity matching is optional later.
```

---

## 7.5 Hybrid Search / Research Retrieval

Layer:

```text
Research Knowledge & Retrieval Layer
External Intelligence Intake
Hypothesis Discovery Layer
Failure → Action Mapping
Research Observability
Adaptive Research Learning
```

Applied to:

```text
prior hypothesis search
failure precedent search
public source lookup
diagnostic precedent retrieval
campaign similarity search
artifact lineage search
operator explanation support
```

Initial implementation should prefer simple deterministic retrieval:

```text
JSONL metadata index
SQLite FTS5
keyword/sparse search
metadata filters
canonical ID filters
```

Optional later:

```text
vector index
local embeddings
Qdrant or equivalent vector DB
cross-encoder reranking
```

Outputs:

```text
retrieval_index_latest.v1.json
retrieval_quality_latest.v1.json
retrieved_context_ids
retrieval_method_breakdown
retrieval_lineage
```

Downstream use:

```text
find comparable research paths
find prior failures before rerunning similar campaigns
support hypothesis discovery context
support operator-facing explanations
reduce redundant exploration
```

Rule:

```text
Retrieval supplies context.
It does not rank candidates for deployment.
```

---

## 7.6 Reciprocal Rank Fusion / Deterministic Rank Fusion

Layer:

```text
Research Retrieval
Hypothesis Discovery
Research Observability
```

Applied to:

```text
keyword search results
metadata search results
graph-neighbor results
optional vector search results
optional reranker results
```

Outputs:

```text
fused_search_results_latest.v1.json
rrf_score
source_rank_breakdown
retrieval_method_coverage
conflicting_rank_warning
```

Downstream use:

```text
combine multiple retrieval methods fairly
make retrieval more robust
support deterministic context selection
expose why a context item was selected
```

Rule:

```text
RRF is allowed because it is deterministic, simple and explainable.
```

---

## 7.7 Cross-Encoder Rerankers

Status:

```text
Optional later retrieval-quality layer.
```

Layer:

```text
Research Retrieval
Research Observability
External Intelligence Intake
```

Allowed use:

```text
rerank documents
rerank research notes
rerank public-source metadata
rerank prior failures for operator/research context
```

Not allowed:

```text
rerank trades
rerank live candidates
rerank capital allocation
replace evidence scoring
replace policy decisions
```

Rule:

```text
Rerankers may improve document retrieval precision.
They may not become candidate promotion logic.
```

---

## 7.8 Bayesian Networks / Evidence Dependency Graphs

Status:

```text
Add later, after simpler evidence scoring and diagnostics are mature.
```

Layer:

```text
Evidence Layer
Policy Layer
Hypothesis Discovery Layer
Research Observability
Adaptive Research Learning
```

Applied to:

```text
conditional evidence support
confounder tracking
diagnostic dependency
evidence contradiction
causal-assumption visibility
posterior hypothesis support
```

Outputs:

```text
conditional_evidence_score
posterior_hypothesis_support
evidence_dependency_graph
confounder_warning
causal_assumption_flag
```

Downstream use:

```text
combine multiple evidence signals explicitly
explain why support increased or decreased
flag correlated evidence sources
avoid double-counting diagnostics
adjust confirmation requirements
```

Rule:

```text
Bayesian Networks estimate evidence support.
They do not certify truth or authorize trades.
```

---

## 7.9 Graph Neural Networks

Status:

```text
Reserve for future benchmarking only.
Do not add as v3.x core capability.
```

Allowed precursor:

```text
deterministic graph diagnostics
correlation graphs
MST / clustering
knowledge graph lineage
network fragility scores
```

Potential future use:

```text
graph ML benchmark for network/portfolio intelligence
research-memory graph embedding benchmark
```

Not allowed now:

```text
GNN price prediction
GNN candidate promotion
GNN live allocation
black-box graph alpha
```

Rule:

```text
Build deterministic graph diagnostics first.
Do not jump to GNNs.
```

---

## 7.10 Tree-of-Thoughts / Graph-of-Thoughts

Status:

```text
Allow only as bounded graph-of-hypotheses expansion.
```

Layer:

```text
Hypothesis Discovery Layer
Failure → Action Mapping
Adaptive Research Learning
Research Observability
```

Allowed use:

```text
generate a bounded set of deterministic follow-up research branches
explain alternatives
map branch → evidence requirement
map branch → failure condition
map branch → allowed next action
```

Example:

```text
Hypothesis seed:
low_entropy_breakout_continuation_crypto_1h

Allowed bounded variants:
1. higher timeframe check
2. regime segmentation check
3. null-model challenge
```

Outputs:

```text
hypothesis_graph
branch_reason
branch_required_evidence
branch_failure_condition
allowed_next_action
```

Not allowed:

```text
open-ended agent reasoning
unbounded search trees
LLM-generated executable strategies
self-directed strategy invention
hidden thought scoring
```

Rule:

```text
Graph-of-hypotheses is allowed only when bounded, deterministic and artifact-backed.
```

---

## 7.11 RLAIF

Status:

```text
Explicitly excluded for now.
```

Reason:

```text
opaque feedback loops
reward hacking risk
harder reproducibility
hidden ranking risk
governance bypass risk
```

Allowed replacement:

```text
deterministic research feedback metrics
```

Examples:

```text
diagnostic_utility_score
source_usefulness_score
hypothesis_survival_rate
false_positive_rate
quorum_effectiveness
null_model_failure_rate
```

Rule:

```text
Do not add RLAIF to v3.x.
Use deterministic evidence-backed feedback instead.
```

---

## 7.12 State Space Models / Mamba

Status:

```text
Park for future research-memory or document-intelligence benchmarks.
Not part of v3.x core.
```

Possible future use:

```text
long-document research summarization
large artifact sequence compression
filing/event document processing
research-memory benchmark
```

Not allowed:

```text
price prediction
trade selection
candidate promotion
capital allocation
live risk mutation
```

Rule:

```text
SSM/Mamba architectures are not needed until deterministic retrieval and knowledge layers are mature.
```

---

# 8. Changes to Roadmap v6 Phases

## v3.15.16 — Intelligent Routing Layer

Add:

```text
state-transition-aware routing
transition-entropy-aware routing
queue-pressure-aware routing
knowledge-context-aware routing
prior-failure-aware routing
retrieval-supported duplicate suppression
```

Routing should consider:

```text
state persistence
transition entropy
state-conditioned signal density
prior similar failures
retrieved contradictory evidence
queue pressure
expected information gain
```

Not allowed:

```text
Markov-only route promotion
retrieval-only candidate escalation
black-box sequence scoring
```

---

## v3.15.17 — Sampling Intelligence

Add:

```text
state-boundary sampling
state-duration bucket sampling
transition-matrix coverage sampling
null/surrogate control sampling
queue-aware compute sampling
retrieval-informed duplicate avoidance
```

Sampling should answer:

```text
which state boundaries are most informative?
which transition paths are under-tested?
which regimes have enough data density?
which hypotheses duplicate prior dead zones?
```

---

## v3.15.18 — Research Observability Expansion

Add observable surfaces for:

```text
state transition matrices
transition entropy
state persistence
regime duration
dwell-time distributions
queue pressure
retrieval lineage
knowledge graph lineage
entity resolution decisions
prior similar hypotheses
prior similar failures
fused retrieval result explanations
```

The operator should see:

```text
which market state the system believes it is analyzing
which transitions made a hypothesis interesting
which prior failures were retrieved
which entities were canonicalized
why a campaign was queued, delayed, suppressed or escalated
```

---

## v3.15.19 — Hypothesis Discovery Engine

Extend planned modules with:

```text
state_hypothesis_adapter.py
knowledge_context_adapter.py
retrieval_context_adapter.py
```

New hypothesis seed examples:

```text
state_transition_compression_to_expansion_crypto_1h_v0
transition_entropy_suppression_equities_daily_v0
post_shock_aftershock_duration_btc_15m_v0
latent_regime_trend_persistence_v0
state_sequence_false_breakout_reversal_v0
queue_aware_dead_zone_suppression_v0
retrieval_prior_failure_avoidance_v0
knowledge_graph_behavior_duplicate_suppression_v0
```

Scoring may consider:

```text
state transition stability
state-conditioned signal density
regime persistence
null transition edge gap
prior similar failures
retrieved supporting evidence
retrieved contradictory evidence
entity resolution confidence
```

Important:

```text
opportunity_probability_score still means expected research value.
It does not mean prediction certainty, alpha certainty or ML confidence.
```

---

## v3.15.20 — Failure → Action Mapping

Add deterministic mappings:

```text
high_transition_entropy
→ suppress state-transition hypothesis

low_state_persistence
→ require regime segmentation

sparse_transition_table
→ collect more data or demote sequence hypothesis

null_transition_edge_gap_negative
→ reject state-transition hypothesis

regime_duration_exhausted
→ reduce follow-up priority or require cooldown

prior_failure_retrieved
→ require differentiated hypothesis or suppress duplicate

entity_resolution_ambiguous
→ block hypothesis escalation until canonicalization is resolved

queue_pressure_high_low_value_campaign
→ defer campaign

queue_starvation_high_value_campaign
→ raise routing priority

retrieval_contradiction_strong
→ require stronger confirmation quorum
```

---

## v3.16.0 — Campaign Feedback Loop

Add:

```text
state-transition outcome feedback
retrieval usefulness feedback
knowledge graph lineage feedback
null-process failure feedback
queue-throughput feedback
```

The engine should learn:

```text
which transition hypotheses survive
which retrieved contexts helped avoid repeated failures
which state definitions produced false positives
which queue policies reduced dead-zone compute burn
```

---

## v3.16.1 — Strategy Fitness Scoring

Add:

```text
state-conditioned survival rate
transition-diagnostic utility
retrieval-supported survival similarity
knowledge graph family fitness
null-process challenge pass rate
```

Fitness remains:

```text
research viability
```

not:

```text
capital allocation
live ranking
```

---

## v3.16.2 — Regime Intelligence

Add:

```text
HMM/latent regime diagnostics
Semi-Markov regime duration
state persistence scoring
regime uncertainty scoring
regime-conditioned compatibility
```

Guardrail:

```text
Latent regimes are research context, not trade signals.
```

---

## v3.16.3 — Candidate Clustering

Add:

```text
state-transition signature similarity
latent-regime signature similarity
retrieval-context similarity
knowledge-graph family similarity
null-model failure similarity
```

---

## v3.16.4 — Robustness Filtering

Add:

```text
state-transition robustness
regime-duration robustness
null-process challenge
retrieval contradiction checks
single-source dependency checks
entity-resolution confidence checks
```

---

## v3.16.5 — Portfolio Intelligence

Add:

```text
cross-asset state-transition similarity
network-state transition alignment
knowledge-graph portfolio overlap
retrieval-supported behavior interaction evidence
```

---

## v4.x — Shadow Trading

Add:

```text
state-transition parity
latent-regime parity
transition entropy drift
online regime-belief tracking candidate
particle-filter research candidate
shadow queue/latency diagnostics
```

Use only after candidates exist.

---

## v5.x — Paper Trading

Add:

```text
paper degradation by state regime
paper degradation by latent regime
state-conditioned expected shortfall
regime-duration drawdown analysis
paper transition parity
```

---

## v6.x — Live Trading

Add only after validation and explicit approval:

```text
state/latent-regime diagnostics may inform live risk context
transition anomalies may support kill-switch context
state diagnostics may not directly create trades
state diagnostics may not bypass whitelist/reconciliation/kill switches
retrieval/knowledge outputs may not drive capital allocation
```

---

# 9. Not Allowed

Add this explicit section to Addendum 2.

```text
Not allowed before explicit future roadmap approval:

- Markov-only trading strategies
- HMM-only trading strategies
- Semi-Markov direct trade triggers
- sequence-model candidate promotion
- RNN/LSTM price prediction
- Transformer price prediction
- SSM/Mamba price prediction
- GNN price prediction
- RLAIF
- open-ended Tree-of-Thought agents
- unbounded Graph-of-Thought search
- LLM-generated executable strategies
- retrieval-based live candidate ranking
- cross-encoder candidate promotion
- Bayesian Network trade authorization
- knowledge graph alpha certification
- live/paper/shadow/risk/broker/execution changes in v3.x
- capital allocation from diagnostics
- mutation of research_latest.json
- mutation of strategy_matrix.csv
```

---

# 10. Definition of Done for This Addendum

Roadmap v6 + Addendum 1 are successfully extended when:

```text
1. Addendum 2 is explicitly named as a follow-up to Addendum 1.

2. Roadmap v6 includes State & Sequential Diagnostics as an extension
   to the Mechanistic Behavior Diagnostics architecture.

3. Roadmap v6 includes Research Knowledge & Retrieval Layer as an extension
   to External Intelligence Intake and Hypothesis Discovery.

4. Markov Chains are added as state-transition diagnostics, not trading strategies.

5. HMMs are reserved for Regime Intelligence, not direct alpha generation.

6. Semi-Markov diagnostics are mapped to regime duration and cooldown reasoning.

7. Martingale and Random Walk processes are mapped to null/no-edge baselines.

8. Finite State Machines are mapped to lifecycle and policy governance.

9. Queueing Theory is mapped to research throughput and campaign queue discipline.

10. Knowledge Graphs, Ontologies and Entity Resolution are mapped to research memory,
    lineage, deduplication and explainability.

11. Hybrid Search and RRF are allowed as deterministic research retrieval infrastructure.

12. Cross-Encoder Rerankers are optional later retrieval-quality tools only.

13. Bayesian Networks are reserved for later evidence dependency modeling.

14. GNNs, RLAIF, RNNs, LSTMs, Transformers for price prediction and SSM/Mamba
    price prediction are explicitly excluded from v3.x core.

15. All new outputs go to sidecar artifacts.

16. Frozen contracts remain protected.

17. Diagnostics, retrieval and knowledge systems are prohibited from direct trading,
    live capital allocation, broker behavior, execution mutation or policy bypass.

18. The operator-light/no-touch intent is preserved through deterministic,
    artifact-driven, inspectable and policy-governed research intelligence.
```

---

# 11. One-Sentence Addendum Summary

```text
Roadmap v6 Addendum 2 extends Addendum 1 by adding state-transition diagnostics,
latent regime reasoning, deterministic lifecycle state machines, null-process baselines,
queueing diagnostics and research knowledge/retrieval infrastructure so the QRE can
remember, retrieve, link, falsify and route behavior-level research more intelligently
without becoming a black-box sequence predictor or trading engine.
```
