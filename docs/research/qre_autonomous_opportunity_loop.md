# QRE Autonomous Opportunity Loop

The canonical bounded opportunity loop lives in [packages/qre_research/autonomous_opportunity_loop.py](/C:/Users/joery.van.rooij/trading-agent/packages/qre_research/autonomous_opportunity_loop.py).

## Entrypoint

Use the existing QRE control surface:

```bash
python -m reporting.qre_research_operations opportunity-loop-run-once
python -m reporting.qre_research_operations opportunity-loop-run-once --max-cycles 2
python -m reporting.qre_research_operations opportunity-loop-status
```

The invocation is bounded and resumable. It does not run as a daemon and does not busy-wait.

## State Model

The loop persists a single canonical state machine:

```text
WAITING_FOR_TRIGGER
-> MATERIAL_CHANGE_CHECK
-> OPPORTUNITY_DISCOVERY
-> HYPOTHESIS_GENERATION
-> HYPOTHESIS_ADMISSION
-> CAMPAIGN_CELL_MATERIALIZATION
-> PORTFOLIO_ADMISSION
-> EMPIRICAL_EXECUTION
-> EVIDENCE_AND_LEARNING
-> WAITING_FOR_TRIGGER
```

Exit states remain bounded:

```text
NO_MATERIAL_CHANGE -> WAITING_FOR_NOVELTY
PERSISTENT_GENERIC_CAPABILITY_GAP -> CAPABILITY_REQUESTED
NEEDS_HUMAN -> OPERATOR_REVIEW_REQUIRED
READY_FOR_SYNTHESIS -> existing research-only synthesis gate
```

## Budgets

The loop enforces conservative per-invocation limits:

- `maximum_cycles_per_run = 3`
- `maximum_generated_hypotheses_per_cycle = 8`
- `maximum_campaign_cells_per_run = 8`
- `maximum_campaign_executions_per_run = 3`

## Material Change Detection

The persisted watermark captures:

- source manifest identities
- dataset fingerprints
- latest complete bars
- usable history and OOS boundaries
- source quality and identity status
- regime signature
- primitive, capability, hypothesis-catalog, and memory versions
- cooldown state

`NO_MATERIAL_CHANGE` is a hard early stop. In that path the loop does not generate hypotheses, materialize campaign cells, execute campaigns, or duplicate ADE requests.

## Hypothesis and Campaign Boundaries

Generated hypotheses stay declarative. The loop reuses the canonical hypothesis generator and lifecycle modules. It does not generate executable Python strategy code, new indicator implementations, arbitrary expression trees, stochastic mutations, or unconstrained LLM strategies.

Campaign cells are materialized from existing canonical readiness and executor mappings. A new campaign ID is not novelty. The novelty gate requires a changed frozen research question, such as a new real OOS period or a new admitted mechanism context.

## ADE Handoff Boundary

Persistent generic capability gaps are written as canonical ADE request artifacts and bridged into the existing QRE development intake and admission-policy projectors.

This loop does not activate Step 5. `AUTO_ALLOWED` only means the request is classified and visible to ADE governance. The loop never edits repository code at runtime, never creates branches, and never opens or merges PRs.

## Runtime Artifacts

The loop writes canonical artifacts under `generated_research/orchestration/opportunity_loop/`:

- watermark and material change detection
- opportunity registry
- generated hypothesis batch and novelty decisions
- campaign cell registry and novelty decisions
- loop state and latest run
- capability gap registry
- ADE development requests and resolution feedback
- continuation plan
