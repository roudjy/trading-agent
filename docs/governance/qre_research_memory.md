# QRE Research Memory

`packages.qre_research.research_memory` builds a deterministic read-only index
over existing local artifacts so prior hypotheses, failures, queue/campaign
state, and policy actions can be retrieved before new research is proposed.

The helper is advisory. It does not grant authority, mutate campaigns, enqueue
work, generate strategies, use embeddings, call an LLM, use a graph database,
use network access, or call subprocesses.

## Commands

Dry-run the memory report:

```powershell
python -m packages.qre_research.research_memory --no-write --frozen-utc 2026-05-23T00:00:00Z
```

Query local memory:

```powershell
python -m packages.qre_research.research_memory --no-write --query "unknown screening failure"
```

Read latest status:

```powershell
python -m packages.qre_research.research_memory --status
```

Write deterministic sidecars under `logs/qre_research_memory/`:

```powershell
python -m packages.qre_research.research_memory
```

## Indexed Local Artifacts

- `research/research_latest.json`
- `research/strategy_matrix.csv`
- `docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md`
- `logs/qre_data_cache_manifest/latest.json`
- `logs/qre_data_source_quality_readiness/latest.json`

Missing optional sidecars are reported as missing artifacts. If no local
entries can be indexed, the report fails closed.

## Inactive Scope

This helper does not activate Addendum 2, embeddings, rerankers, cross-encoders,
state models, knowledge graph databases, strategy generation, routing mutation,
live trading, paper trading, shadow trading, broker integration, risk-engine
behavior, or execution paths.
