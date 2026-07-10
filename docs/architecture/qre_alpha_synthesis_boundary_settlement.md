# QRE Alpha/Synthesis Boundary Settlement

PR11 settles the two remaining QRE architecture governance blockers without
granting executable synthesis or deployment authority.

## Alpha Discovery Generated Lifecycle

`alpha_discovery_generated_lifecycle` is settled as a governance-only
bridge/read-model surface. It may connect to the canonical funnel only through
explicit bridge/read-model contracts. It may consume canonical contract names
and emit bridge/readiness read models, but it does not own canonical object
semantics.

It may not independently own:

- `Hypothesis`
- `CandidateSpec`
- `StrategySpec`
- `PresetSpec`
- `CampaignSpec`
- `EvidencePack`
- `Disposition`
- `FeedbackRecord`
- `LessonMemory`
- `ResearchMemory`

## Bounded Strategy Synthesis Readiness

`bounded_strategy_synthesis_readiness` is settled as governance-only
non-executable synthesis consideration. It may report readiness, eligibility,
and dispositions. It may not execute strategy synthesis or create production
strategies, presets, or campaigns.

## Authority Statement

Neither settled surface grants:

- executable strategy synthesis authority
- shadow authority
- paper authority
- live authority
- broker authority
- risk authority
- order authority
- capital allocation authority
- dashboard mutation authority

Future escalation beyond read-model reporting requires a separate
operator-approved roadmap phase.
