# QRE Maturity Roadmap to 100

## Purpose

This document is the canonical roadmap for taking QRE from the current
read-only, fail-closed research posture toward a generic, bounded, reproducible research engine.

It is a roadmap and sequencing document only. It does not authorize new
runtime capability by itself.

## Current implementation authority

This document is the active canonical roadmap for current QRE
implementation sequencing.

Older Roadmap v6, Addendum, ADE, audit, and prompt-library documents are
historical or supporting references unless this roadmap explicitly
incorporates them. Where those documents conflict with this roadmap, use
this roadmap for current sequencing.

After the Phase 7B preset feasibility mapper and the roadmap-authority
alignment cleanup, the next implementation item is Phase 7C:
`feat: add routing score scaffold`.

The campaign-first scaffold-to-trust maturity program selected by
`ADE-QRE-016H` is documented in
`docs/roadmap/qre_trusted_research_intelligence_roadmap_manifest.md`.
That manifest governs the `ADE-QRE-017` trusted research intelligence program
without erasing historical Roadmap v6, Addendum, or prior ADE/QRE material.

## Current baseline

- QRE governance / infrastructure maturity: 65/100
- Evidence production maturity: 25/100
- Research intelligence maturity: 30/100
- Candidate quality maturity: 5/100
- Deployment/live readiness: 0/100

The recent PR sequence established a strong governance envelope:

- bounded evidence handling is fail-closed;
- alias decisions are explicit;
- artifact acceptance is explicit;
- operator action plans and trusted-loop reports are read-only;
- evidence completeness remains false unless real accepted artifacts exist.

## Strategic correction

The next phase is not to build more AAPL/NVDA-specific logic.
The next phase is to build a permanent, bounded-request-driven research
architecture that can be reused across baskets, presets, and timeframes.

The approved first batch remains AAPL/NVDA only as a fixture / smoke / operator-approved request input.
Core paths must stay bounded-request-driven and symbol-agnostic.

## Hard rules

- AAPL/NVDA may appear only as first-batch fixture, smoke, or
  operator-approved request input.
- No AAPL/NVDA special-case logic belongs in core code paths.
- The permanent architecture must be bounded-request-driven and
  symbol-agnostic.
- Generated reports are never source evidence.
- Context-only artifacts are never proof of lineage or OOS evidence.
- Missing evidence must remain explicit.

## Track 1 - Governance / Infrastructure Maturity

Current: 65/100
Target: 100/100

Governance/infrastructure is 100/100 when:

- every research action has a scope, authority, and artifact contract;
- no command can mutate without classification;
- frozen contracts stay protected;
- evidence, context, approval, and generation stay separate;
- operator-action plans are consistent;
- report modules are non-recursive and non-stale;
- all critical flows are traceable through sidecar artifacts and reason records.

### Epic G1 - Generic bounded request model

This is the immediate next implementation track.

The bounded request model should eventually define:

- basket_request_id
- symbols
- preset_id
- timeframe
- approval_ref
- allowed_output_paths
- required_artifact_types
- forbidden_capabilities
- scope_hash

### Epic G2 - Artifact authority map

Later track.

Each artifact type should have explicit authority, including source
artifacts, generated reports, approval manifests, generation manifests,
reason records, legacy traces, test fixtures, and smoke/temp outputs.

### Epic G3 - Operator-grade status model

Later track.

QRE should expose a stable operator-facing maturity dashboard and final
status normalizer so progress is derived from artifacts, not manual
labels.

## Track 2 - Evidence Production Maturity

Current: 25/100
Target: 100/100

Evidence production is 100/100 when QRE can generically:

- accept a bounded basket request;
- execute controlled generation / validation safely;
- produce screening evidence;
- produce OOS evidence;
- produce lineage evidence;
- write generation manifests;
- pass acceptance verification;
- show evidence-complete or exact fail-closed closure;
- repeat this across baskets without hardcoding.

### Epic E1 - Generic bounded evidence producer

This is the immediate next implementation track.

The next implementation order should be:

1. generic bounded basket request schema;
2. generic bounded command discovery;
3. generic bounded current-basket generation runner;
4. controlled validation adapter;
5. structured lineage artifacts;
6. structured OOS artifacts;
7. evidence acceptance integration;

### Epic E2 - Multi-basket evidence expansion

Later track.

Once the first generic evidence pipeline works, expand to request
planning, source/cache-first expansion, and OOS batch materialization
across additional baskets.

### Epic E3 - Evidence quality gates

Later track.

Add null-model, cost/slippage, and replayability requirements so
accepted evidence remains reproducible and falsifiable.

## Track 3 - Research Intelligence Maturity

Current: 30/100
Target: 100/100

Research intelligence is 100/100 when QRE can deterministically decide:

- which behaviors are interesting;
- which hypotheses should be tested;
- which sampling is informative;
- which failures map to which recovery actions;
- which prior evidence is relevant;
- which research paths are redundant.

### Step 7 - Research intelligence and candidate lifecycle

This is the next major capability after generic evidence production
stabilizes.

It should include:

- behavior catalog;
- hypothesis object model;
- preset feasibility mapping;
- routing score;
- dead-zone suppression;
- sampling plan;
- failure-to-action mapping;
- research memory / retrieval;
- candidate identity and lifecycle;
- promotion gates and review packets.

## Track 4 - Candidate Quality Maturity

Current: 5/100
Target: 100/100

Candidate quality is 100/100 when a candidate has:

- complete lineage;
- accepted screening and OOS evidence;
- cost/slippage robustness;
- null-model checks;
- failure history;
- promotion gates;
- reason records;
- replayability.

This track depends on the evidence-production track being generic and
reproducible first.

## Track 5 - Deployment / Live Readiness

Current: 0/100
Target: 100/100

Deployment/live readiness is only relevant after candidate quality is
materially stronger.

### Step 8 - Shadow / paper / live deferral

Shadow, paper, and live remain deferred until:

- evidence production is stable;
- candidate quality is materially higher;
- governance remains fail-closed;
- no runtime activation path is implied by documentation alone.

## Score progression targets

Milestones should be tracked as artifacts improve:

- M1: first generic evidence-complete basket
- M2: multiple evidence-complete baskets
- M3: routing and sampling use real evidence
- M4: first robust promotion candidates
- M5: shadow-ready candidate set
- M6: paper-ready system
- M7: controlled live-ready system

## Recommended build order

1. Generic bounded evidence production.
2. Artifact authority and reason-record contracts.
3. Research intelligence and candidate lifecycle.
4. Candidate quality and promotion gates.
5. Shadow, paper, and live deferral until the above are proven.

## Non-goals for this PR

This document does not implement:

- bounded request schemas;
- command discovery;
- artifact authority registries;
- runners;
- research intelligence modules;
- candidate lifecycle code;
- shadow/paper/live behavior.
