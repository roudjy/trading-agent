# QRE Canonical Contract Map

## Settlement Position

The current repo should be treated as several partial funnels, not one proven provider-agnostic canonical loop.

The Tiingo candidate research loop is valuable and should be kept, but as a provider adapter / research-only mini-loop until its artifacts are bridged to provider-agnostic contracts.

The daily digest is observability-only. It must not become a producer of research objects.

The run_research / registry / strategy_matrix path may still be an important canonical legacy surface, but this audit does not prove it owns the modern QRE Hypothesis, CandidateSpec, EvidenceLedger, FeedbackRecord, PresetSpec, or CampaignSpec vocabulary.

PR A settlement now records the canonical vocabulary in:

```text
docs/architecture/qre_canonical_contract_vocabulary.md
packages/qre_research/canonical_contracts.py
```

This settlement defines names, required fields, owner/status/recommendation metadata, and provider-leakage boundaries. It does not bridge any existing artifact yet.

PR B adds the first provider-adapter bridge:

```text
packages/qre_research/tiingo_canonical_bridge.py
```

This bridge maps Tiingo HypothesisSeed, ResearchInputContract, and CandidateSpec records into canonical Hypothesis, ResearchInputContract, and CandidateSpec payloads. Tiingo-specific identifiers stay in `provenance`; canonical semantics remain provider-agnostic.

PR C adds the provider-agnostic planning bridge:

```text
packages/qre_research/candidate_planning_bridge.py
```

This bridge maps canonical CandidateSpec records into StrategySpec, PresetSpec, and bounded CampaignSpec payloads. It is planning-only: no registry mutation, campaign execution, screening run, validation, promotion, paper, shadow, live, broker, risk, or order authority.

PR D adds the evidence and memory bridge:

```text
packages/qre_research/evidence_memory_bridge.py
```

This bridge maps campaign or screening evidence into EvidencePack, EvidenceLedger, Disposition, FeedbackRecord, LessonMemory, and ResearchMemory payloads. It preserves negative and contradictory evidence and remains memory-only: no synthesis, promotion, validation, paper, shadow, live, broker, risk, order, or execution authority.

PR E adds deterministic memory-aware hypothesis ordering:

```text
packages/qre_research/memory_aware_hypothesis_generation.py
```

This adapter lets canonical FeedbackRecord, LessonMemory, and ResearchMemory influence the next hypothesis batch by suppressing repeated failures, deprioritizing dead zones, and boosting near-pass families. Every influence is explainable and deterministic. It does not synthesize strategies, invent indicators, create candidates, promote candidates, or grant execution authority.

PR F adds the funnel classification registry:

```text
packages/qre_research/funnel_classification.py
```

This registry quarantines duplicate funnel claims. It records exactly one canonical provider-agnostic contract/bridge/memory loop at the contract level, keeps Tiingo as a provider adapter, keeps daily digest as observability-only, protects legacy `research/research_latest.json` and `research/strategy_matrix.csv`, and marks fixture/smoke funnels as fixture-only. It does not delete legacy code or change runtime behavior.

## Canonical Object Ownership

| Object | Current audit status | Current owner evidence | Recommendation |
|---|---|---|---|
| DataProvider | inferred | source manifest and provider modules | DEFINE_CANONICAL_SCHEMA |
| SourceManifest | present | external intelligence/source manifest modules | KEEP |
| SourceSnapshot | present | source snapshot provenance fields | KEEP |
| DatasetFingerprint | inferred | source/data profile digest fields | DEFINE_CANONICAL_SCHEMA |
| ObservationSnapshot | missing or ambiguous | no single owner proven | DEFINE_CANONICAL_SCHEMA |
| Hypothesis | bridged from Tiingo provider adapter; broader ownership still ambiguous | Tiingo bridge plus older discovery modules | BRIDGE |
| HypothesisSeed | present | Tiingo lifecycle | BRIDGE |
| ResearchInputContract | bridged from Tiingo provider adapter | Tiingo candidate loop plus canonical bridge | BRIDGE |
| CandidateSpec | bridged from Tiingo provider adapter; canonical semantic owner still settling | Tiingo candidate loop plus canonical bridge | GENERALIZE |
| StrategySpec | bridged from canonical CandidateSpec; broader legacy owner still ambiguous | candidate planning bridge plus older strategy paths | BRIDGE |
| StrategyIR | ambiguous | alpha discovery / Strategy IR references | OPERATOR_DECISION_REQUIRED |
| PresetSpec | bridged from canonical StrategySpec; broader legacy owner still ambiguous | candidate planning bridge plus preset modules | BRIDGE |
| CampaignSpec | bridged from canonical PresetSpec; execution owner still separate | candidate planning bridge plus campaign modules | BRIDGE |
| CampaignRun | inferred | campaign run/report modules | DEFINE_CANONICAL_SCHEMA |
| ScreeningResult | present | Tiingo candidate loop and other screening modules | GENERALIZE |
| EvidencePack | bridged from canonical screening/campaign evidence | evidence memory bridge plus campaign/evidence modules | BRIDGE |
| EvidenceLedger | bridged from canonical screening/campaign evidence | Tiingo candidate loop plus evidence memory bridge | BRIDGE |
| Disposition | bridged from EvidencePack | evidence memory bridge plus disposition modules | BRIDGE |
| FeedbackRecord | bridged from Disposition | Tiingo candidate loop plus evidence memory bridge | BRIDGE |
| LessonMemory | bridged from FeedbackRecord; broader memory owner still ambiguous | evidence memory bridge plus lesson/memory modules | BRIDGE |
| ResearchMemory | bridged from LessonMemory; broader memory store owner still ambiguous | evidence memory bridge plus research memory modules | BRIDGE |
| DailyDigestInput | present | daily digest sidecars | KEEP_AS_OBSERVABILITY |
| OperatorSummary | present | digest and sidecar summaries | KEEP_AS_OBSERVABILITY |
| RegistryEntry | present | registry.py | KEEP_PENDING_SCOPE_CONFIRMATION |
| StrategyMatrixRow | present | research/strategy_matrix.csv | KEEP_AS_LEGACY_OUTPUT_CONTRACT |

## Funnel Reconciliation Table

| Funnel | Current status | Canonicality | Provider specificity | Keep/Bridge/Deprecate decision | Required future PR |
|---|---|---|---|---|---|
| Canonical provider-agnostic contract/bridge/memory loop | contract-level loop | canonical_contract_loop | provider_agnostic | KEEP_AS_CANONICAL | PR A-E complete: vocabulary, Tiingo bridge, planning bridge, evidence/memory bridge, and memory-aware next hypothesis ordering |
| Tiingo candidate research loop | research-only mini-loop | provider adapter | provider_specific | KEEP_AS_PROVIDER_ADAPTER + BRIDGE_TO_CANONICAL | Bridge complete through canonical Hypothesis, ResearchInputContract, CandidateSpec, Evidence/Feedback, and memory-aware next-run context |
| Daily digest | read-only aggregation | observability_only | mixed | OBSERVABILITY_ONLY | Keep consuming sidecars; do not let digest produce research objects |
| Alpha discovery / Strategy IR / campaign / lesson funnel | partial funnel | unknown | mixed | BRIDGE_TO_CANONICAL or UNKNOWN_REQUIRES_OPERATOR_DECISION | Map StrategyIR, CampaignSpec, EvidencePack, Disposition, LessonMemory, and ResearchMemory ownership |
| run_research / registry / strategy_matrix | legacy protected output path | legacy_protected | mixed | KEEP_AS_LEGACY_OUTPUT_CONTRACT | Frozen outputs remain protected; separate operator-scoped settlement required before ownership changes |
| test/smoke fixture funnels | fixture semantics | test_fixture_only | unknown | TEST_FIXTURE_ONLY | Fixture-only claims are quarantined and cannot masquerade as canonical |

## Recommended PR Sequence

1. PR A: settle canonical contract vocabulary. Status: complete in this vocabulary settlement PR.
2. PR B: bridge Tiingo artifacts to canonical Hypothesis/CandidateSpec. Status: complete for Hypothesis, ResearchInputContract, and CandidateSpec.
3. PR C: bridge canonical CandidateSpec to StrategySpec/PresetSpec/CampaignSpec. Status: complete at planning-contract level.
4. PR D: connect campaign evidence to FeedbackMemory/LessonMemory. Status: complete at contract/memory bridge level.
5. PR E: make next hypothesis generation consume canonical memory. Status: complete at deterministic ordering/context level.
6. PR F: deprecate or quarantine duplicate legacy funnels. Status: complete at classification/quarantine level.

After PR F, the provider-agnostic QRE research loop is reconciled at the contract, bridge, memory, and funnel-classification level. This does not mean strategy-authoritative, validation-ready, paper-ready, shadow-ready, live-ready, or trading-ready.

## Rules For Future Work

- Provider-specific terms stop at adapter, source manifest, snapshot, dataset fingerprint, and provenance layers.
- CandidateSpec, StrategySpec, PresetSpec, CampaignSpec, EvidencePack, FeedbackRecord, and readiness policy must be provider-agnostic.
- Observability modules consume artifacts and summarize status; they do not create research objects.
- Legacy run_research outputs remain protected and must not be mutated by architecture audit work.

