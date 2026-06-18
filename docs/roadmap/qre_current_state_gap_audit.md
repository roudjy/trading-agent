# QRE Current State Gap Audit

> Status note: This audit is retained as historical/reference material.
> Its repository state, HEAD SHA, and next-action guidance predate PRs
> #558 through #563. Current QRE implementation sequencing is governed
> by `docs/roadmap/qre_maturity_roadmap_to_100.md`; after this
> roadmap-authority cleanup, the next implementation item is Phase 7C:
> `feat: add routing score scaffold`.

## 1. Executive Summary for Operator

### Where are we?

QRE is currently in a **research-only, read-only, fail-closed** phase.

The repository has a meaningful amount of working infrastructure:

- a bounded real-basket diagnosis loop;
- read-only routing/sampling readiness projections;
- controlled discovery grid diagnostics and explainability modules;
- an equity research front door with universe, factor, recipe, readiness, seed, and controlled-evaluation scaffolds;
- provider-candidate and source-manifest policy scaffolds.

The repository is **not** at paper, shadow, or live readiness.

### What works?

- The current non-execution governance and safety envelope is strong and explicit.
- The equity research front door artifacts generate deterministically and fail closed.
- The pre-shadow/paper readiness summary generates deterministically and explicitly keeps synthesis blocked.
- Research-memory, failure-retrieval, and trusted-loop KPI scaffolds exist and are tested.
- Source/provider selection and source-manifest/license policy are now represented as governed read-only artifacts.

### What is still blocked?

- No basket is routing-ready.
- No basket is sampling-ready.
- No candidate is promotion-ready.
- Equity recipes, hypothesis seeds, and controlled factor evaluation remain blocked by source/data/policy gaps.
- Local controlled-grid evidence bridging is currently blocked because the local repository state does not contain `research/controlled_discovery_grid_runs/`; the bridge therefore resolves to `blocked_no_grid_match`.
- Candidate/campaign lineage remains incomplete in the readiness loop.
- Fundamental source manifests exist only as deterministic stubs and do not unlock trust.

### Why are we not at paper/shadow/live?

Because the repository still lacks the required evidence density, lineage closure, trusted source policy, point-in-time/report-lag/restatement policy, and operator-trusted maturity gates. The existing code explicitly keeps runtime activation forbidden.

### What is the next critical path?

The shortest critical path is:

1. source-manifest hardening and point-in-time/report-lag/restatement policy;
2. factor field coverage and source-quality closure;
3. grid candidate/campaign lineage closure and source/cache sidecar materialization;
4. targeted readiness reruns with real local artifacts;
5. only then reconsider routing/sampling maturity and later controlled factor evaluation.

## 2. Executive Summary for Solution Architect

### Current implemented layers

- **Governance / authority:** strong, explicit, operator-gated, fail-closed.
- **QRE readiness loop:** implemented as read-only diagnosis, evidence coverage, routing/sampling readiness, candidate explanations, KPI rollups, and pre-shadow/paper readiness reporting.
- **Controlled discovery diagnostics:** implemented as materialization, source identity, metric consistency, preset executability, and survivor-stage attribution layers.
- **Equity research front door:** implemented as deterministic universe catalog, universe quality, factor catalog, screener recipes, operator report, data readiness gate, hypothesis-seed adapter, controlled factor evaluation scaffold, provider candidate registry, and source manifest/license policy.
- **Research memory / retrieval:** lightweight keyword/index/tag based coverage exists.

### Missing layers

- No implemented knowledge graph, entity resolution engine, hybrid retrieval index, or rank-fusion stack.
- No implemented point-in-time/report-lag/restatement policy layer yet.
- No implemented factor field coverage closure with real trusted manifests.
- No implemented grid candidate/campaign lineage bridge module.
- No implemented operator-trusted routing/sampling closure on local evidence.

### Layer boundary risks

- AGENTS.md still says `registry.py`, but the actual strategy registration authority is `research/registry.py`.
- Some roadmap/addendum surfaces exist as **schema/projector or reporter scaffolds**, not as active research-decision engines.
- Prior VPS-based interpretations can overstate current local capability when local artifacts are absent.

### Source-of-truth boundaries

- Strategy registration authority: [`research/registry.py`](../../research/registry.py)
- Strategy implementations: [`agent/backtesting/strategies.py`](../../agent/backtesting/strategies.py)
- Research orchestration: [`research/run_research.py`](../../research/run_research.py)
- Frozen public contracts: [`research/research_latest.json`](../../research/research_latest.json), [`research/strategy_matrix.csv`](../../research/strategy_matrix.csv)

### Governance constraints

Governance documents override roadmap ambition. Passing CI does not imply roadmap maturity. Addendum-inspired diagnostics do not grant runtime authority. External/public data is still treated as unvalidated prior.

### Maturity interpretation

The current repo is best described as:

- **working capability** for deterministic read-only research infrastructure;
- **working scaffold** for many front-door and trusted-loop surfaces;
- **not operator-trusted** for execution-adjacent phases;
- **blocked by governance/data** for source trust and factor evaluation.

## 3. Executive Summary for Engineer

### Modules present

- QRE readiness: [`research/qre_pre_shadow_paper_research_readiness.py`](../../research/qre_pre_shadow_paper_research_readiness.py), [`research/qre_real_basket_diagnosis.py`](../../research/qre_real_basket_diagnosis.py), [`research/qre_real_basket_evidence_coverage.py`](../../research/qre_real_basket_evidence_coverage.py), [`research/qre_grid_evidence_readiness_bridge.py`](../../research/qre_grid_evidence_readiness_bridge.py), [`research/qre_routing_readiness_from_basket.py`](../../research/qre_routing_readiness_from_basket.py), [`research/qre_sampling_readiness_from_basket.py`](../../research/qre_sampling_readiness_from_basket.py), [`research/qre_candidate_explanation_rows.py`](../../research/qre_candidate_explanation_rows.py), [`research/qre_hypothesis_seed_feasibility.py`](../../research/qre_hypothesis_seed_feasibility.py), [`research/qre_trusted_loop_operator_kpis.py`](../../research/qre_trusted_loop_operator_kpis.py)
- Grid diagnostics: [`research/qre_discovery_basket_grid_evidence_materialization.py`](../../research/qre_discovery_basket_grid_evidence_materialization.py), [`research/qre_discovery_source_identity_diagnostics.py`](../../research/qre_discovery_source_identity_diagnostics.py), [`research/qre_controlled_discovery_metric_consistency_audit.py`](../../research/qre_controlled_discovery_metric_consistency_audit.py), [`research/qre_controlled_discovery_preset_executability.py`](../../research/qre_controlled_discovery_preset_executability.py), [`research/qre_controlled_discovery_survivor_stage_attribution.py`](../../research/qre_controlled_discovery_survivor_stage_attribution.py)
- Equity front door: universe, factors, recipes, readiness, hypothesis seeds, controlled factor eval, provider registry, source manifest policy
- Memory/retrieval: [`research/qre_research_memory_coverage.py`](../../research/qre_research_memory_coverage.py), [`packages/qre_research/research_memory.py`](../../packages/qre_research/research_memory.py), [`packages/qre_research/retrieval_coverage.py`](../../packages/qre_research/retrieval_coverage.py)

### Artifacts present

- Universe artifacts in [`artifacts/universe/`](../../artifacts/universe/)
- Factor artifacts in [`artifacts/equity_factors/`](../../artifacts/equity_factors/)
- Readiness artifacts in [`artifacts/data_readiness/`](../../artifacts/data_readiness/)
- Hypothesis-seed artifacts in [`artifacts/hypothesis_discovery/`](../../artifacts/hypothesis_discovery/)
- Provider/source artifacts in [`artifacts/external_intelligence/`](../../artifacts/external_intelligence/)
- Readiness/log artifacts in [`logs/qre_pre_shadow_paper_research_readiness/`](../../logs/qre_pre_shadow_paper_research_readiness/)

### Tests present

- Front-door unit tests for universe, factor, recipe, readiness, seed, controlled eval, provider, source manifest
- Readiness-loop unit tests for basket diagnosis, coverage, bridge, routing, sampling, candidate explanations, KPIs, research memory
- Architecture and smoke suites

### Failing or missing integrations

- Local grid-evidence bridge is currently blocked by missing local controlled-grid run artifacts.
- Current local universe operator report is stale relative to newer readiness/hypothesis artifacts and reports them as missing.
- No local trusted-loop KPI or research-memory artifact is currently present on disk, even though the modules/tests exist.
- No candidate/campaign lineage bridge module is present.

### Concrete next PRs

- point-in-time / report-lag / restatement policy
- factor field coverage manifest hardening
- source-manifest hardening for SEC Companyfacts and OpenFIGI
- grid candidate/campaign lineage bridge
- source/cache sidecar materialization and readiness rerun

### Technical blockers

- missing trusted source policy;
- missing local grid-run artifacts;
- missing lineage closure;
- missing factor field coverage closure;
- missing operator-trusted evidence density.

## 4. Source Documents Reviewed

| Document | Path | Found | Status | Notes |
|---|---|---|---|---|
| AGENTS | [`AGENTS.md`](../../AGENTS.md) | yes | governance | Contains session and architecture rules; source-of-truth wording partly stale because actual registry file is `research/registry.py`. |
| CLAUDE | [`CLAUDE.md`](../../CLAUDE.md) | yes | governance | Confirms post-package QRE feature track and addendum/runtime guardrails. |
| GitHub PR lifecycle | [`docs/governance/github_pr_lifecycle.md`](../governance/github_pr_lifecycle.md) | yes | governance | Canonical PR/CI/squash-merge protocol. |
| No-touch paths | [`docs/governance/no_touch_paths.md`](../governance/no_touch_paths.md) | yes | governance | Important context, but current doc states `research/**` no-touch even though recent repo history contains research PRs; treat as governance intent, not this audit’s edit surface. |
| Execution authority | [`docs/governance/execution_authority.md`](../governance/execution_authority.md) | yes | governance | Canonical safety/authority hierarchy. |
| ADR-014 | [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md) | yes | governance | Canonical truth-authority mapping. |
| ADR-015 | [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md) | yes | governance | Agent-governance authority chain. |
| Roadmap scope status | [`docs/governance/roadmap_scope_status.md`](../governance/roadmap_scope_status.md) | yes | governance/reference | Critical for determining which addendum items are active vs deferred/reference-only. |
| Roadmap v6 | [`docs/roadmap/Roadmap v6.md`](Roadmap%20v6.md) | yes | canonical | Product sequence authority. |
| Roadmap v6 Addendum 1 | [`docs/roadmap/Roadmap v6 Addendum.md`](Roadmap%20v6%20Addendum.md) | yes | addendum | Mechanistic diagnostics + external intelligence intake. |
| Roadmap v6 Addendum 2 | [`docs/roadmap/Roadmap v6 Addendum 2 - State Sequential Knowledge Retrieval.md`](Roadmap%20v6%20Addendum%202%20-%20State%20Sequential%20Knowledge%20Retrieval.md) | yes | addendum | State, sequential, knowledge, retrieval. |
| Roadmap v6 Addendum 3 | [`docs/roadmap/Roadmap v6 Addendum 3 - Source Identity Data Quality and Throughput Intelligence.md`](Roadmap%20v6%20Addendum%203%20-%20Source%20Identity%20Data%20Quality%20and%20Throughput%20Intelligence.md) | yes | addendum | Source identity, data quality, throughput. |
| Roadmap v6 Addendum 4 | [`docs/roadmap/Roadmap v6 Addendum 4 - Trusted Loop Readiness and Operator Trust.md`](Roadmap%20v6%20Addendum%204%20-%20Trusted%20Loop%20Readiness%20and%20Operator%20Trust.md) | yes | addendum | Maturity interpretation and trusted-loop framing. |
| ADE operating manual | [`docs/roadmap/qre_roadmap_v6_ade_operating_manual.md`](qre_roadmap_v6_ade_operating_manual.md) | yes | reference | Operationalizes roadmap execution but does not override product sequence. |
| QRE_ADE How-To | [`docs/strategy/QRE_ADE_How_To_Target_State_Roadmap.md`](../strategy/QRE_ADE_How_To_Target_State_Roadmap.md) | yes | reference | Target-state and implementation strategy document; not canonical runtime authority. |
| Autonomous development track | [`docs/roadmap/autonomous_development.txt`](autonomous_development.txt) | yes | canonical ADE | ADE governance track. |
| Step 5 design | [`docs/governance/step5_design.md`](../governance/step5_design.md) | yes | reference_only | Design planning only; implementation blocked. |

### Conflict resolution used in this audit

- Governance docs override implementation authority and safety.
- Roadmap v6 governs product sequence.
- Addenda extend planning scope but do not by themselves authorize runtime behavior.
- `roadmap_scope_status.md` is treated as the clearest repo-local statement of what addendum work is active, deferred, or reference-only.
- Actual repository modules/artifacts/tests override assumptions and prior chat history.

## 5. Current Repository Evidence

- HEAD SHA: `294a71800dc4e491d658f5bb86888cbe43ca2592`
- Branch at audit start: `docs/qre-roadmap-gap-audit-current-state`
- `origin/main` at audit start: `294a71800dc4e491d658f5bb86888cbe43ca2592`
- Latest relevant merges in history:
  - `#489` source manifest schema and license policy
  - `#488` provider candidate registry
  - `#487` controlled factor evaluation scaffold
  - `#485` hypothesis seed adapter
  - `#484` fundamental readiness gate
  - `#483` operator universe report
  - `#482` screener recipe library
  - `#478` grid evidence readiness bridge
  - `#477` controlled discovery evidence diagnostics

### Key current local artifacts

- Readiness: [`logs/qre_pre_shadow_paper_research_readiness/latest.json`](../../logs/qre_pre_shadow_paper_research_readiness/latest.json)
- Grid bridge: [`logs/qre_grid_evidence_readiness_bridge/latest.json`](../../logs/qre_grid_evidence_readiness_bridge/latest.json)
- Grid materialization: [`logs/qre_discovery_basket_grid_evidence_materialization/latest.json`](../../logs/qre_discovery_basket_grid_evidence_materialization/latest.json)
- Universe: [`artifacts/universe/equity_universe_summary_latest.v1.json`](../../artifacts/universe/equity_universe_summary_latest.v1.json)
- Universe quality: [`artifacts/universe/equity_universe_quality_latest.v1.json`](../../artifacts/universe/equity_universe_quality_latest.v1.json)
- Factor catalog: [`artifacts/equity_factors/equity_factor_catalog_latest.v1.json`](../../artifacts/equity_factors/equity_factor_catalog_latest.v1.json)
- Recipe catalog: [`artifacts/equity_factors/equity_factor_recipes_latest.v1.json`](../../artifacts/equity_factors/equity_factor_recipes_latest.v1.json)
- Fundamental readiness: [`artifacts/data_readiness/fundamental_readiness_latest.v1.json`](../../artifacts/data_readiness/fundamental_readiness_latest.v1.json)
- Hypothesis seeds: [`artifacts/hypothesis_discovery/equity_factor_hypothesis_seeds_latest.v1.json`](../../artifacts/hypothesis_discovery/equity_factor_hypothesis_seeds_latest.v1.json)
- Controlled factor evaluation readiness: [`artifacts/equity_factors/controlled_factor_evaluation_readiness_latest.v1.json`](../../artifacts/equity_factors/controlled_factor_evaluation_readiness_latest.v1.json)
- Provider summary: [`artifacts/external_intelligence/fundamental_provider_summary_latest.v1.json`](../../artifacts/external_intelligence/fundamental_provider_summary_latest.v1.json)
- Source manifest quality: [`artifacts/external_intelligence/source_manifest_quality_latest.v1.json`](../../artifacts/external_intelligence/source_manifest_quality_latest.v1.json)

### Important local-state caveat

The local repository currently has **no** `research/controlled_discovery_grid_runs/` directory. The grid materialization and grid bridge therefore fail closed locally as:

- `no_grid_run_found` in materialization;
- `blocked_no_grid_match` in the readiness bridge.

That means current local evidence is more conservative than prior VPS-based interpretations.

## 6. Roadmap v6 Gap Matrix

| Topic | Roadmap intent | Current implementation | Category | Evidence | What is missing | Next action | Priority |
|---|---|---|---|---|---|---|---|
| v3.x research intelligence loop | behavior-first, deterministic research engine | real-basket diagnosis, coverage, routing/sampling projections, readiness rollup exist | WORKING_CAPABILITY_NEEDS_EXPANSION | [`research/qre_pre_shadow_paper_research_readiness.py`](../../research/qre_pre_shadow_paper_research_readiness.py), [`logs/qre_pre_shadow_paper_research_readiness/latest.json`](../../logs/qre_pre_shadow_paper_research_readiness/latest.json) | evidence density, lineage closure, trusted source closure | integrate | P0 critical path |
| Intelligent routing layer | behavior-aware routing | read-only routing readiness plus routing signal schema/reporters exist; no runtime routing mutation | WORKING_SCAFFOLD | [`research/qre_routing_readiness_from_basket.py`](../../research/qre_routing_readiness_from_basket.py), [`reporting/intelligent_routing_diagnostic_signals.py`](../../reporting/intelligent_routing_diagnostic_signals.py) | local evidence closure, actual deterministic integration if later authorized | harden | P1 next |
| Sampling intelligence | intelligent sampling selection | read-only sampling readiness exists; zero ready locally | WORKING_SCAFFOLD | [`research/qre_sampling_readiness_from_basket.py`](../../research/qre_sampling_readiness_from_basket.py), [`logs/qre_pre_shadow_paper_research_readiness/latest.json`](../../logs/qre_pre_shadow_paper_research_readiness/latest.json) | evidence-ready rows | integrate | P1 next |
| Research observability | operator-readable loop state | strong read-only summaries exist | WORKING_CAPABILITY_NEEDS_EXPANSION | readiness/operator reports, KPIs, provider reports, universe report | more complete current artifacts and trusted KPI surfaces | harden | P1 next |
| Hypothesis discovery | behavior- and evidence-aware seed generation | behavior hypothesis and equity factor seed surfaces exist, both blocked/fail-closed | WORKING_SCAFFOLD | [`research/qre_hypothesis_seed_feasibility.py`](../../research/qre_hypothesis_seed_feasibility.py), [`research/hypothesis_discovery/equity_factor_hypothesis_adapter.py`](../../research/hypothesis_discovery/equity_factor_hypothesis_adapter.py) | data/source readiness, more real evidence linkage | integrate | P1 next |
| Failure to action mapping | preserve negative results and route next action | implemented in bounded read-only basket/failure/reason record layers | WORKING_CAPABILITY_NEEDS_EXPANSION | [`research/qre_candidate_explanation_rows.py`](../../research/qre_candidate_explanation_rows.py), [`research/qre_research_memory_coverage.py`](../../research/qre_research_memory_coverage.py) | richer reason density and decision usefulness | harden | P1 next |
| Shadow trading | later-phase runtime validation | intentionally not active | DEFERRED_BY_ROADMAP | governance and readiness invariants across modules | later-phase only | defer | DEFERRED |
| Paper trading | later-phase simulated deployment | intentionally not active | DEFERRED_BY_ROADMAP | same | later-phase only | defer | DEFERRED |
| Live trading | controlled live deployment | intentionally hard-disabled | DEFERRED_BY_ROADMAP | same | later-phase only | defer | DEFERRED |

## 7. Addendum 1 Gap Matrix — Mechanistic Diagnostics

| Topic | Roadmap intent | Current implementation | Category | Evidence | What is missing | Next action | Priority |
|---|---|---|---|---|---|---|---|
| Tail diagnostics | detect fragility/tail asymmetry | referenced in routing schema/docs; separate real tail diagnostic engine not verified here | PRESENT_BUT_NOT_WORKING | [`reporting/intelligent_routing_diagnostic_signals.py`](../../reporting/intelligent_routing_diagnostic_signals.py), [`docs/governance/roadmap_scope_status.md`](../governance/roadmap_scope_status.md) | implemented research diagnostic module with current artifacts | build | P2 later |
| Entropy diagnostics | detect structure/disorder | same state as tail: schema/reference, not proven as live research capability in this audit | PRESENT_BUT_NOT_WORKING | same | actual evidence-producing module | build | P2 later |
| Criticality diagnostics | phase-transition intelligence | schema-only routing family; explicitly deferred in scope-status doc | DEFERRED_BY_ROADMAP | [`docs/governance/roadmap_scope_status.md`](../governance/roadmap_scope_status.md), [`reporting/intelligent_routing_diagnostic_signals.py`](../../reporting/intelligent_routing_diagnostic_signals.py) | implementation | defer | DEFERRED |
| Barrier diagnostics | barrier/breakout pressure | schema-only routing family; deferred | DEFERRED_BY_ROADMAP | same | implementation | defer | DEFERRED |
| Resonance diagnostics | cycle/resonance intelligence | schema-only routing family; deferred | DEFERRED_BY_ROADMAP | same | implementation | defer | DEFERRED |
| Null-model diagnostics | no-edge baseline as read-only guardrail | referenced in hypothesis scoring, routing schemas, diagnostics loop blockers; not a full current capability | WORKING_SCAFFOLD | [`research/equity_factors/controlled_factor_evaluation.py`](../../research/equity_factors/controlled_factor_evaluation.py), [`research/hypothesis_discovery/opportunity_scoring.py`](../../research/hypothesis_discovery/opportunity_scoring.py), [`tests/unit/test_hypothesis_discovery_minimal.py`](../../tests/unit/test_hypothesis_discovery_minimal.py) | real null-model evidence generation and integration | build | P1 next |
| Network diagnostics | network-state intelligence | schema-only/reference-only | DEFERRED_BY_ROADMAP | scope-status + routing schema | implementation | defer | DEFERRED |
| Adversarial diagnostics | adversarial market behavior | schema-only/reference-only | DEFERRED_BY_ROADMAP | same | implementation | defer | DEFERRED |
| Seismic / turbulence / quorum / market language | specialized diagnostics | mostly schema-only or reference-only; quorum appears in some diagnostics-loop docs/tests but not yet operator-trusted | WORKING_SCAFFOLD | [`packages/qre_diagnostics/research_diagnostics_loop.py`](../../packages/qre_diagnostics/research_diagnostics_loop.py), [`tests/unit/test_qre_research_diagnostics_loop.py`](../../tests/unit/test_qre_research_diagnostics_loop.py), scope-status doc | current artifacts and decision usefulness | harden | P2 later |

## 8. Addendum 2 Gap Matrix — State, Sequential, Knowledge & Retrieval

| Topic | Roadmap intent | Current implementation | Category | Evidence | What is missing | Next action | Priority |
|---|---|---|---|---|---|---|---|
| State transition diagnostics | transition-aware intelligence | no dedicated research state-transition diagnostics module found | NOT_PRESENT | repo search, roadmap task docs only | implementation | build | P2 later |
| Regime duration diagnostics | duration / dwell-time intelligence | no verified module | NOT_PRESENT | repo search | implementation | build | P2 later |
| Martingale / random-walk baseline | null-process baseline | referenced in docs/task catalogs and blocked controlled-eval needs; not implemented as working module | WORKING_SCAFFOLD | [`research/equity_factors/controlled_factor_evaluation.py`](../../research/equity_factors/controlled_factor_evaluation.py), roadmap task docs | actual baseline engine | build | P1 next |
| FSM lifecycle helpers | closed-vocab lifecycle modeling | no dedicated QRE implementation verified | NOT_PRESENT | repo search | implementation | build | P2 later |
| Queueing diagnostics | throughput / queueing modeling | no dedicated QRE research implementation verified | NOT_PRESENT | repo search, task docs only | implementation | build | P3 optional |
| Ontology | canonical taxonomy / ontology | lightweight `ontology_tags` exist in memory packages, but no standalone ontology module | WORKING_SCAFFOLD | [`packages/qre_research/research_memory.py`](../../packages/qre_research/research_memory.py) | explicit ontology layer and tests as separate capability | build | P2 later |
| Knowledge graph | linked research memory graph | not present | NOT_PRESENT | repo search | implementation | build | P2 later |
| Entity resolution | cross-artifact entity resolution | not present beyond lightweight matching | NOT_PRESENT | repo search | implementation | build | P2 later |
| Retrieval index | deterministic retrieval over memory | lightweight retrieval exists | WORKING_SCAFFOLD | [`packages/qre_research/research_memory.py`](../../packages/qre_research/research_memory.py), [`packages/qre_research/retrieval_coverage.py`](../../packages/qre_research/retrieval_coverage.py), [`tests/unit/test_qre_research_memory.py`](../../tests/unit/test_qre_research_memory.py) | broader coverage and authority-safe usefulness | harden | P1 next |
| Rank fusion | hybrid retrieval/rank fusion | not present | NOT_PRESENT | repo search | implementation | build | P3 optional |
| Related failure retrieval | retrieve similar failures | implemented in lightweight form | WORKING_CAPABILITY_NEEDS_EXPANSION | [`research/qre_research_memory_coverage.py`](../../research/qre_research_memory_coverage.py), [`tests/unit/test_qre_research_memory_coverage.py`](../../tests/unit/test_qre_research_memory_coverage.py) | more real current artifacts, broader linkage | harden | P1 next |

## 9. Addendum 3 Gap Matrix — Source Identity, Data Quality & Throughput

| Topic | Roadmap intent | Current implementation | Category | Evidence | What is missing | Next action | Priority |
|---|---|---|---|---|---|---|---|
| Source candidate registry | govern candidate providers | implemented | OPERATOR_TRUSTED_FOR_CURRENT_PHASE | [`research/external_intelligence/fundamental_provider_registry.py`](../../research/external_intelligence/fundamental_provider_registry.py), [`artifacts/external_intelligence/fundamental_provider_summary_latest.v1.json`](../../artifacts/external_intelligence/fundamental_provider_summary_latest.v1.json) | expansion and later operator review | harden | P1 next |
| Source manifest schema | manifest contract for future sources | implemented, deterministic, fail-closed | OPERATOR_TRUSTED_FOR_CURRENT_PHASE | [`research/external_intelligence/source_manifest_schema.py`](../../research/external_intelligence/source_manifest_schema.py), [`research/external_intelligence/source_manifest_registry.py`](../../research/external_intelligence/source_manifest_registry.py) | more reviewed manifests | harden | P1 next |
| License policy | deterministic license/terms policy | implemented, fail-closed | OPERATOR_TRUSTED_FOR_CURRENT_PHASE | [`research/external_intelligence/source_license_policy.py`](../../research/external_intelligence/source_license_policy.py), [`artifacts/external_intelligence/source_license_policy_latest.v1.json`](../../artifacts/external_intelligence/source_license_policy_latest.v1.json) | reviewed terms and approvals | operator review | P1 next |
| Source quality gates | quality-gated activation eligibility | present only as blocked policy surface; no provider eligible | BLOCKED_BY_GOVERNANCE_OR_DATA | source manifest quality artifact | reviewed manifests, PIT/report-lag/restatement/source-quality policy | write policy | P0 critical path |
| Identity / symbology layer | deterministic identity handling | implemented for discovery and equity universe ambiguity gating | WORKING_CAPABILITY_NEEDS_EXPANSION | [`research/qre_discovery_source_identity_diagnostics.py`](../../research/qre_discovery_source_identity_diagnostics.py), [`research/equity_universe_identity.py`](../../research/equity_universe_identity.py) | stronger provider manifests and broader linkage | harden | P1 next |
| Local cache manifests | deterministic local cache readiness | implemented under `packages.qre_data.cache_manifest`; used by readiness loop | WORKING_CAPABILITY_NEEDS_EXPANSION | [`docs/governance/qre_data_cache_manifest.md`](../governance/qre_data_cache_manifest.md), [`tests/unit/test_qre_data_cache_manifest.py`](../../tests/unit/test_qre_data_cache_manifest.py) | current local generated artifacts, stronger integration | generate data | P1 next |
| Parquet / DuckDB / Polars throughput layer | higher-throughput data handling | cache manifest covers parquet visibility; no dedicated DuckDB/Polars throughput layer verified | WORKING_SCAFFOLD | cache-manifest docs/tests | actual throughput layer | build | P2 later |
| Source usefulness ledger | usefulness scoring over sources | not found | NOT_PRESENT | repo search | implementation | build | P3 optional |
| Factor field coverage | factor-to-field readiness coverage | implemented, but still all blocked | WORKING_SCAFFOLD | [`research/data_readiness/factor_field_coverage.py`](../../research/data_readiness/factor_field_coverage.py), [`artifacts/data_readiness/fundamental_readiness_latest.v1.json`](../../artifacts/data_readiness/fundamental_readiness_latest.v1.json) | real source/field manifests | write policy | P0 critical path |
| Fundamental provider candidate registry | governed provider candidate surface | implemented | OPERATOR_TRUSTED_FOR_CURRENT_PHASE | provider summary artifact/tests | future manifest hardening | harden | P1 next |

## 10. Addendum 4 Gap Matrix — Trusted Loop Readiness & Operator Trust

| Topic | Roadmap intent | Current implementation | Category | Evidence | What is missing | Next action | Priority |
|---|---|---|---|---|---|---|---|
| Reason-record density | sufficient explainability | present, but current readiness report still says `candidate_blockers_explainable=false` | WORKING_CAPABILITY_NEEDS_EXPANSION | [`logs/qre_pre_shadow_paper_research_readiness/latest.json`](../../logs/qre_pre_shadow_paper_research_readiness/latest.json) | higher-density current records and candidate closure | harden | P1 next |
| Routing/sampling readiness density | enough evidence to trust zero-ready result | present and fail-closed | WORKING_CAPABILITY_NEEDS_EXPANSION | same | real ready rows or clearer blockers on local artifacts | run validation | P1 next |
| KPI coverage | operator-readable KPI surface | implemented | WORKING_SCAFFOLD | [`research/qre_trusted_loop_operator_kpis.py`](../../research/qre_trusted_loop_operator_kpis.py), tests | current generated artifacts in repo and broader completeness | harden | P2 later |
| Strategy synthesis readiness gate | keep synthesis blocked until justified | implemented as blocked | OPERATOR_TRUSTED_FOR_CURRENT_PHASE | readiness summary `synthesis_still_blocked=true` | none for current phase | defer | DEFERRED |
| Operator-trusted capability | current-phase trust | not achieved for broader trusted loop | BLOCKED_BY_GOVERNANCE_OR_DATA | Addendum 4 doctrine + current readiness outputs | evidence density, policy, lineage, source/data closure | operator review | P0 critical path |

## 11. QRE_ADE How-To Target State Gap Matrix

| Topic | Roadmap intent | Current implementation | Category | Evidence | What is missing | Next action | Priority |
|---|---|---|---|---|---|---|---|
| Minimal loop | prove deterministic loop first | implemented | OPERATOR_TRUSTED_FOR_CURRENT_PHASE | current diagnosis/coverage/readiness stack | ongoing maintenance | harden | P2 later |
| Trusted loop | full operator-trusted loop | partial only | WORKING_CAPABILITY_NEEDS_EXPANSION | readiness summary `trusted_loop_maturity_state=working_capability` | lineage/data/policy/operator trust | integrate | P0 critical path |
| Data foundation | reliable data manifests and coverage | partial front-door + source/cache scaffolds | WORKING_SCAFFOLD | readiness artifacts + provider/source artifacts | trusted manifests and reviewed source policies | write policy | P0 critical path |
| Research memory | preserve learnings and retrieve failures | lightweight implementation exists | WORKING_CAPABILITY_NEEDS_EXPANSION | research-memory modules/tests | broader coverage and better current artifacts | harden | P1 next |
| Failure attribution | explain failures and next actions | implemented in bounded scope | WORKING_CAPABILITY_NEEDS_EXPANSION | failure/reason/candidate explanation modules | more current evidence density | harden | P1 next |
| Routing/sampling calibration | calibration on real evidence | zero ready locally; projections exist | WORKING_SCAFFOLD | routing/sampling readiness modules + local readiness artifact | local artifact closure and calibration policy | run validation | P1 next |
| Operator-grade observability | clear operator read surfaces | partial and improving | WORKING_CAPABILITY_NEEDS_EXPANSION | universe/provider/readiness reports | stronger consolidated reporting | harden | P2 later |
| Adaptive learning | self-prioritizing learning loop | not implemented as active capability | NOT_PRESENT | target-state docs only | implementation | build | P2 later |
| Valkuilenregister / decision journal / architecture reset | anti-pitfall and operator journal discipline | not found as explicit current modules/artifacts | NOT_PRESENT | repo search | documentation/governance surfaces | build | P2 later |

## 12. Cross-Document Consolidated Gap List

### Not present

- knowledge graph
- entity resolution engine
- rank fusion
- queueing diagnostics
- explicit state-transition diagnostics
- regime-duration diagnostics
- adaptive learning loop
- explicit decision journal / valkuilenregister surface
- grid candidate/campaign lineage bridge module
- source usefulness ledger

### Present but not working

- local grid evidence materialization against current local repo state
- local grid readiness bridge against current local repo state
- local universe operator report freshness relative to newer front-door artifacts
- tail/entropy as proven current local research capabilities

### Working scaffold

- routing readiness projection
- sampling readiness projection
- equity screener recipes
- factor readiness gate
- equity factor hypothesis seed adapter
- controlled factor evaluation scaffold
- source quality gate eligibility surface
- source manifest and license-policy stubs
- lightweight ontology-tag based research memory
- routing diagnostic signal schema/projector

### Working capability needing expansion

- real-basket diagnosis
- basket evidence coverage
- candidate explanation rows
- trusted-loop readiness rollup
- failure retrieval
- provider candidate registry
- discovery source identity diagnostics
- preset executability diagnostics
- metric consistency audit
- equity universe foundation and quality gates

### Operator-trusted / done for current phase

- governance envelope keeping paper/shadow/live inactive
- frozen-contract preservation discipline
- deterministic equity universe catalog
- deterministic factor catalog
- deterministic provider candidate registry
- deterministic source manifest schema
- deterministic source license policy
- strategy synthesis blocking doctrine

### Deferred by roadmap

- shadow runtime
- paper runtime
- live runtime
- broker/risk/execution activation
- broad Addendum 1 diagnostics families beyond current schema/reporter surfaces
- most Addendum 2 knowledge/state/retrieval ambitions

### Blocked by governance or data

- provider activation beyond candidate/staging/manual
- feasible equity recipes
- feasible equity hypothesis seeds
- controlled factor evaluation readiness
- operator-trusted trusted loop
- point-in-time/report-lag/restatement dependent factor evaluation

## 13. Current Critical Path

1. Point-in-time / report-lag / restatement policy
2. Factor field coverage manifest
3. SEC Companyfacts source manifest hardening
4. OpenFIGI identity manifest hardening
5. Grid candidate/campaign lineage bridge
6. Source/cache sidecar materialization on local current state
7. Controlled discovery grid rerun or local artifact restoration
8. Targeted readiness rerun on current local artifacts
9. Candidate blocker explainability closure
10. Evidence-complete basket closure
11. Research-memory current-artifact generation
12. Trusted-loop KPI current-artifact generation
13. Consolidated operator-grade observability report
14. Null-model baseline framework
15. State-transition diagnostics scaffold
16. Ontology/entity-resolution scaffold
17. Related failure retrieval hardening
18. Routing calibration on real evidence
19. Sampling calibration on real evidence
20. Final current-phase trusted-loop review

## 14. What Not To Do Yet

- strategy synthesis
- automatic strategy invention
- real factor evaluation without trusted manifests
- paper / shadow / live activation
- broker / risk / execution / capital allocation work
- paid/vendor data activation without policy and review
- hidden ML/RL selectors
- treating provider availability as alpha

## 15. Validation/Falsification of Prior Working Interpretation

| Claim | Validated / Rejected | Evidence | Correction |
|---|---|---|---|
| No current paper/shadow/live activation | validated | readiness and front-door safety invariants across modules | none |
| Diagnostics do not trade | validated | routing schema module and readiness modules explicitly forbid trading authority | none |
| Universe foundation exists | validated | universe modules + artifacts | none |
| Factor catalog exists | validated | factor modules + artifacts | none |
| Recipes exist | validated | recipe catalog artifact shows 15 | none |
| Fundamental data readiness gate exists | validated | readiness modules + artifacts | none |
| Hypothesis seed adapter exists | validated | adapter module + artifact | none |
| Controlled factor evaluation scaffold exists | validated | eval module + artifact | none |
| Provider candidate registry exists | validated | provider modules + artifacts | none |
| Source manifest/license policy exists | validated | source manifest modules + artifacts | none |
| Grid evidence is partially readiness-visible now | rejected for current local repo state | local bridge summary is `blocked_no_grid_match` for all 15 baskets | prior statement was environment-specific or stale; not true for current local checkout |
| Screening evidence rows total is currently >0 in readiness | rejected for current local repo state | current readiness artifact shows `screening_evidence_rows_total=0` | local state is more conservative than earlier VPS run |
| Source/cache readiness is currently a blocker | partially validated | readiness artifact says source readiness linked and `source_ready_basket_pct=33.33`, but many baskets still blocked by source/cache/lineage gaps | blocker exists but not as a total local zero-state anymore |
| Candidate/campaign lineage remains a blocker | validated | readiness coverage missing taxonomy and `candidate_blockers_explainable=false` | none |
| No provider is quality_gated or active_read_only | validated | provider and source-manifest artifacts | none |
| Trusted loop exists as operator-trusted capability | rejected | readiness artifact says `trusted_loop_maturity_state=working_capability`, not operator-trusted | it is a working capability, not an operator-trusted phase completion |

## 16. Recommended Next Master Roadmap Structure

The next roadmap should be organized into epic-sized PR units and commit-sized user stories, with the top tracks:

- Track A: source manifests, PIT/report-lag/restatement, field coverage
- Track B: grid lineage and readiness closure
- Track C: research memory and retrieval hardening
- Track D: null models and diagnostics maturity
- Track E: routing/sampling/hypothesis maturity
- Track F: operator trust and governance reporting
- Track G: explicitly deferred runtime phases

The detailed proposed blueprint is in:

- [`docs/roadmap/qre_next_master_roadmap_blueprint.md`](qre_next_master_roadmap_blueprint.md)
