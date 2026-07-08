# QRE Funnel Visual Maps

This audit uses C4-style context/container/component diagrams, data-flow diagrams, integration/dependency diagrams, and sequence diagrams.

It does not prioritize infrastructure diagrams because this audit is about research architecture, artifact contracts, provider leakage, and funnel ownership, not servers, networks, load balancers, or deployment topology.

## Diagram 1 C4 Context: QRE Research System Boundary

```mermaid
flowchart LR
    Operator[Operator]
    Codex[ChatGPT / Codex workflow]
    GitHub[GitHub PR / CI]
    Repo[QRE repo]
    Providers[Data providers / adapters]
    Artifacts[Generated research artifacts]
    Digest[Daily digest / observability]
    NoLive[No broker / order / live authority]

    Operator --> Codex
    Codex --> Repo
    Repo --> GitHub
    Providers --> Repo
    Repo --> Artifacts
    Artifacts --> Digest
    Digest --> Operator
    Repo -. safety boundary .-> NoLive
```

## Diagram 2 C4 Container/Component: Current Detected Funnels

```mermaid
flowchart TB
    subgraph TiingoMiniLoop[Tiingo mini-loop]
        TGen[qre_tiingo_hypothesis_generator_e2e.py]
        TLife[qre_tiingo_hypothesis_lifecycle.py]
        TCand[qre_tiingo_candidate_research_loop.py]
        TArt[logs/qre_tiingo_*]
        TGen --> TLife --> TCand --> TArt
    end

    subgraph AlphaCampaign[Alpha discovery / Strategy IR / campaign funnel]
        Alpha[alpha discovery modules]
        StrategyIR[Strategy IR semantics]
        Campaign[campaign modules]
        Lessons[lesson / memory / disposition modules]
        Alpha --> StrategyIR --> Campaign --> Lessons
    end

    subgraph LegacyRun[Canonical or legacy run_research / registry / matrix funnel]
        Registry[registry.py]
        Strategies[agent/backtesting/strategies.py]
        RunResearch[research/run_research.py]
        Matrix[research_latest.json / strategy_matrix.csv]
        Registry --> RunResearch
        Strategies --> RunResearch --> Matrix
    end

    subgraph Observability[Daily digest observability funnel]
        Sidecars[logs/**/latest.json]
        Digest[qre_daily_status_digest.py]
        Summary[operator_summary.md]
        Sidecars --> Digest --> Summary
    end
```

## Diagram 3 Target Canonical Data-Flow Architecture

```mermaid
flowchart LR
    Adapter[DataProviderAdapter]
    SourceSnapshot[SourceSnapshot]
    ObservationSnapshot[ObservationSnapshot]
    Hypothesis[Hypothesis]
    Contract[ResearchInputContract]
    Candidate[CandidateSpec]
    Strategy[StrategySpec / Strategy IR]
    Preset[PresetSpec]
    Campaign[CampaignSpec]
    Run[CampaignRun / ScreeningResult]
    Evidence[EvidencePack / EvidenceLedger]
    Feedback[Disposition / FeedbackRecord / LessonMemory]
    Next[Next HypothesisBatch]

    Adapter --> SourceSnapshot --> ObservationSnapshot --> Hypothesis --> Contract --> Candidate --> Strategy --> Preset --> Campaign --> Run --> Evidence --> Feedback --> Next
    SourceSnapshot -. provider provenance allowed .-> Adapter
    Candidate -. provider-specific terms stop before here .- SourceSnapshot
    Preset -. provider agnostic required .- Campaign
```

Provider-specific terms stop at SourceSnapshot/provenance. PresetSpec and CampaignSpec must remain provider-agnostic.

## Diagram 4 Integration/Dependency Graph: Producer/Consumer Artifact Map

```mermaid
flowchart LR
    TGen[qre_tiingo_hypothesis_generator_e2e] -- adapter edge --> TGenArt[Tiingo generator latest.json]
    TGenArt -- artifact contract --> TLife[qre_tiingo_hypothesis_lifecycle]
    TLife -- sidecar --> TLifeArt[Tiingo lifecycle latest.json]
    TLifeArt -- adapter edge --> TCand[qre_tiingo_candidate_research_loop]
    Bars[bars.csv] -- adapter data --> TCand
    TCand -- sidecar --> TCandArt[candidate loop latest/evidence/feedback]
    TCandArt -- observability edge --> Digest[qre_daily_status_digest]
    Legacy[run_research / registry] -- canonical unknown --> Matrix[research_latest / strategy_matrix]
    Campaign[campaign / evidence / memory modules] -- suspicious or unknown edges --> Memory[lesson / research memory]
```

Canonical edges should converge through provider-agnostic contracts. Adapter edges can remain provider-specific. Observability edges must not become producers. Suspicious/unknown edges require settlement before being treated as canonical.

## Diagram 5 Sequence: Intended Full Canonical Loop

```mermaid
sequenceDiagram
    actor Operator
    participant HypothesisGenerator
    participant AdmissionBoundary
    participant CandidateMaterializer
    participant StrategySpecBuilder
    participant PresetBuilder
    participant CampaignPlanner
    participant CampaignRunner
    participant EvidenceEvaluator
    participant FeedbackMemory
    participant NextHypothesisGenerator
    participant DailyDigest

    Operator->>HypothesisGenerator: generate hypotheses
    HypothesisGenerator->>AdmissionBoundary: admit / reject
    AdmissionBoundary->>CandidateMaterializer: admitted contract
    CandidateMaterializer->>StrategySpecBuilder: candidate spec
    StrategySpecBuilder->>PresetBuilder: strategy spec
    PresetBuilder->>CampaignPlanner: preset spec
    CampaignPlanner->>CampaignRunner: bounded campaign spec
    CampaignRunner->>EvidenceEvaluator: screening / campaign result
    EvidenceEvaluator->>FeedbackMemory: evidence + disposition
    FeedbackMemory->>NextHypothesisGenerator: feedback memory
    DailyDigest->>Operator: report status

    Note over CampaignRunner,DailyDigest: No validation/promotion/paper/shadow/live.
    Note over Operator,DailyDigest: No broker/risk/order authority.
```

## Diagram 6 Provider Leakage Boundary

```mermaid
flowchart TB
    subgraph Allowed[Provider-specific allowed zone]
        Adapters[adapters]
        Manifests[source manifests]
        Snapshots[snapshots]
        Fingerprints[dataset fingerprints]
        Provenance[provenance]
    end

    subgraph Agnostic[Provider-agnostic required zone]
        CandidateSem[candidate semantics]
        StrategySpecs[strategy specs]
        Presets[presets]
        Campaigns[campaigns]
        EvidenceDecisions[evidence decisions]
        FeedbackDecisions[feedback decisions]
        Readiness[readiness / promotion policy]
    end

    Adapters --> Manifests --> Snapshots --> Fingerprints --> Provenance
    Provenance --> CandidateSem
    CandidateSem --> StrategySpecs --> Presets --> Campaigns --> EvidenceDecisions --> FeedbackDecisions
    Readiness -. must not depend on provider terms .- Adapters
```

