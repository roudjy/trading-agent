# QRE Canonical Funnel Verification

`packages/qre_research/canonical_funnel_verification.py` provides static,
fixture-only proof that the QRE research loop has one provider-agnostic route:

```text
Hypothesis
-> ResearchInputContract
-> CandidateSpec
-> StrategySpec
-> StrategyIR
-> PresetSpec
-> CampaignSpec
-> CampaignRun
-> ScreeningResult
-> EvidencePack
-> EvidenceLedger
-> Disposition
-> FeedbackRecord
-> LessonMemory
-> ResearchMemory
-> NextHypothesisBatch
```

The final `NextHypothesisBatch` is a read model emitted from `ResearchMemory`;
it is not introduced as a new canonical owner.

The verifier checks:

- each stage consumes only the prior stage output;
- each stage emits only the declared next object or read model;
- provider-specific fields do not leak into canonical semantic objects;
- fixture records remain fixture-only and cannot count as empirical evidence;
- observability-only, fixture-only, legacy, closed-world, and maturity
  boundaries remain enforced.

The verifier does not run research, create production candidates, create
strategies, create presets, create campaigns, run screening, mutate frozen
outputs, or grant strategy synthesis, shadow, paper, live, broker, risk, order,
or capital authority.
