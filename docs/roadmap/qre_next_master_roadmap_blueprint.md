# QRE Next Master Roadmap Blueprint

## 1. Purpose

This is a **proposed** roadmap blueprint derived from:

- the current repository audit;
- current local artifacts and tests;
- canonical governance constraints;
- Roadmap v6 and its addenda.

It is:

- not yet operator-approved;
- not yet execution-authoritative;
- intended to structure the next roadmap at **epic = PR** and **user story = commit** granularity.

## 2. Principles

- data authority before factor evaluation
- evidence lineage before routing/sampling trust
- diagnostics do not trade
- external data is unvalidated prior
- no paper/shadow/live until maturity gates pass
- operator trust before autonomy expansion
- scaffolds do not count as operator-trusted capability
- current repository state overrides roadmap assumptions

## 3. Roadmap Tracks

### Track A — Source Manifest, License, PIT, Field Coverage

Likely epics:

1. Source Manifest Schema + License Policy hardening
2. Point-in-Time / Report-Lag / Restatement Policy
3. Factor Field Coverage Manifest
4. Fundamental Fixture / Manual Seed Snapshot
5. Recompute Readiness
6. Controlled Factor Eval Plan-Only Runner hardening

### Track B — Evidence Lineage and Readiness Closure

Likely epics:

1. Grid Candidate/Campaign Lineage Bridge
2. Source/Cache Sidecar Materialization
3. Targeted Readiness Rerun
4. Candidate Blocker Explainability
5. Evidence Complete Basket Closure

### Track C — Research Memory and Retrieval

Likely epics:

1. Ontology
2. Entity Resolution
3. Knowledge Graph
4. Lineage Graph
5. Keyword Index Hardening
6. Related Failure Retrieval Hardening
7. Contradiction Tracking

### Track D — Diagnostics and Null Models

Likely epics:

1. Null Model Baseline Framework
2. Entropy Diagnostics
3. Tail Diagnostics
4. Barrier Diagnostics
5. State Transition Diagnostics
6. Martingale / No-Edge Baseline
7. Diagnostic Utility Ledger

### Track E — Routing, Sampling, Hypothesis Maturity

Likely epics:

1. Routing Calibration on Real Evidence
2. Sampling Calibration on Real Evidence
3. Hypothesis Discovery v2
4. Failure → Action → Reroute
5. Behavior Fitness Scoring
6. Regime Intelligence

### Track F — Operator Trust and Governance

Likely epics:

1. Trusted Loop KPI Dashboard / Report
2. Operator Decision Journal / Valkuilenregister
3. Monthly Architecture Reset Report
4. Synthesis Gate Calibration
5. Final v3.x Readiness Review

### Track G — Deferred Runtime Phases

- Shadow v4.x
- Paper v5.x
- Controlled Live v6.x

## 4. Epic Template

For each future epic, use this template.

### Fields

- `epic_id`
- `title`
- `source_documents`
- `why_it_matters`
- `current_state`
- `definition_of_done`
- `forbidden_scope`
- `expected_pr_branch`
- `expected_files`
- `expected_tests`
- `expected_artifacts`
- `user_stories_commits`
- `dependencies`
- `risk_class`
- `operator_approval_required`

### Template

```text
epic_id:
title:
source_documents:
why_it_matters:
current_state:
definition_of_done:
forbidden_scope:
expected_pr_branch:
expected_files:
expected_tests:
expected_artifacts:
user_stories_commits:
dependencies:
risk_class:
operator_approval_required:
```

## 5. Suggested First 20 Epics

### 1. `EPIC-A01` — Point-in-Time / Report-Lag / Restatement Policy

- Source docs: Roadmap v6 Addendum 3, QRE_ADE How-To
- Why: blocks all credible factor readiness
- Current state: explicit blockers in readiness artifacts
- DoD:
  - closed policy vocabulary exists
  - deterministic policy artifact exists
  - readiness artifacts use specific policy blockers
- Forbidden scope:
  - no source activation
  - no factor evaluation
  - no provider fetching
- Expected branch: `fix/qre-pit-report-lag-restatement-policy`
- Expected files:
  - `research/data_readiness/...`
  - `artifacts/data_readiness/...`
- Expected tests:
  - policy unit tests
  - readiness integration tests
- Expected artifacts:
  - PIT/report-lag/restatement policy sidecars
- User stories / commits:
  - define vocabularies
  - add deterministic evaluators
  - wire into readiness

### 2. `EPIC-A02` — Factor Field Coverage Manifest

- Why: recipes and seeds remain blocked on field coverage
- Current state: factor-field coverage scaffold only
- DoD:
  - reviewed field-manifest schema exists
  - factor-to-field coverage rows are deterministic
  - readiness artifacts become more specific

### 3. `EPIC-A03` — SEC Companyfacts Source Manifest Hardening

- Why: top public fundamentals candidate
- Current state: stub manifest only
- DoD:
  - reviewed license classification
  - explicit PIT/report-lag/restatement posture
  - still no fetching

### 4. `EPIC-A04` — OpenFIGI Identity Manifest Hardening

- Why: identity/symbology trust path
- Current state: candidate manifest only
- DoD:
  - explicit identity-only trust scope
  - no fundamental readiness unlock

### 5. `EPIC-B01` — Grid Candidate/Campaign Lineage Bridge

- Why: current readiness still lacks lineage closure
- Current state: no dedicated bridge module verified
- DoD:
  - candidate/campaign lineage visibility is explicit per basket
  - blocker explanations improve

### 6. `EPIC-B02` — Source/Cache Sidecar Materialization

- Why: current local readiness depends on sidecar presence
- DoD:
  - source/cache status is explicit and reproducible
  - readiness reruns consume current local sidecars

### 7. `EPIC-B03` — Local Controlled Grid Artifact Refresh

- Why: local bridge currently sees no grid runs
- DoD:
  - local deterministic artifact state exists or current absence is made explicit in a refreshed report

### 8. `EPIC-B04` — Targeted Readiness Rerun

- Why: current local state differs from earlier VPS/history assumptions
- DoD:
  - refreshed readiness artifact
  - refreshed bridge artifact
  - explicit delta report

### 9. `EPIC-B05` — Candidate Blocker Explainability Closure

- Why: `candidate_blockers_explainable=false`
- DoD:
  - explainability becomes true or explicit blocking reason remains with exact gap list

### 10. `EPIC-B06` — Evidence Complete Basket Closure

- Why: no basket is evidence complete
- DoD:
  - at least one basket either becomes evidence-complete or exact blockers are fully enumerated with no unknowns

### 11. `EPIC-C01` — Research Memory Current Artifact Generation

- Why: modules exist but local artifacts are absent
- DoD:
  - current `logs/qre_research_memory_coverage/latest.json`
  - current `logs/qre_failure_retrieval/latest.json`

### 12. `EPIC-C02` — Ontology Scaffold

- Why: current memory uses lightweight tags only
- DoD:
  - closed-vocab ontology scaffold
  - no knowledge-authority overreach

### 13. `EPIC-C03` — Entity Resolution Scaffold

- Why: needed for cross-artifact lineage and retrieval
- DoD:
  - deterministic entity resolution rules
  - ambiguity remains visible

### 14. `EPIC-C04` — Related Failure Retrieval Hardening

- Why: current failure retrieval is lightweight
- DoD:
  - better similar-failure linkage over current artifacts

### 15. `EPIC-D01` — Null Model Baseline Framework

- Why: multiple future surfaces are blocked on missing null-model authority
- DoD:
  - read-only null-model baseline artifact
  - no trading authority

### 16. `EPIC-D02` — State Transition Diagnostics Scaffold

- Why: Addendum 2 topic remains absent
- DoD:
  - deterministic state-transition reporter
  - no runtime mutation

### 17. `EPIC-D03` — Tail / Entropy Hardening

- Why: currently more schema/reference than operator-trusted capability
- DoD:
  - actual evidence artifacts or explicit failure-closed reporters

### 18. `EPIC-E01` — Routing Calibration on Real Evidence

- Why: zero routing-ready should be backed by closed blockers
- DoD:
  - routing calibration report over current evidence

### 19. `EPIC-E02` — Sampling Calibration on Real Evidence

- Why: same for sampling
- DoD:
  - sampling calibration report over current evidence

### 20. `EPIC-F01` — Final v3.x Trusted Loop Review Packet

- Why: bridge from working capability to operator trust
- DoD:
  - consolidated trust review packet
  - explicit go/no-go criteria

## 6. Deferred Items

Do not build yet:

- strategy synthesis
- automatic strategy invention
- real factor evaluation without reviewed manifests and policies
- paper/shadow/live activation
- broker/risk/execution changes
- capital allocation
- paid/vendor data activation without approved source policy
- hidden ML/RL selectors
- opaque ranking presented as authority

## 7. Branch and Commit Granularity Guidance

### Epic = PR-sized

Each epic should be independently mergeable and bounded to one clear research/governance outcome.

### User story = commit-sized

Each user story should usually map to:

- one schema/policy addition;
- one integration step;
- one artifact writer or reporter;
- one targeted test slice.

Avoid mixing:

- policy definition;
- data integration;
- readiness unlocking;
- runtime behavior.

## 8. Approval Note

This blueprint is derived from the current-state audit only.

It does **not** become canonical execution authority until the operator approves a final master roadmap document.
