# QRE Research Supervisor

The governed alpha research supervisor is the canonical long-running Linux entrypoint for bounded alpha discovery.

## Commands

```powershell
python -m reporting.qre_research_supervisor --run-once
python -m reporting.qre_research_supervisor --loop --interval-seconds 300 --max-iterations 24
python -m reporting.qre_research_supervisor --status
python -m reporting.qre_research_supervisor --healthcheck
```

## Persistent State

The container image carries code only. Mutable research state must remain on persistent volumes:

- `data/cache`
- `artifacts/cache`
- `generated_research`
- `logs`
- `research`

## Restart Behavior

- leases are bounded and stale-safe
- snapshot lineage remains immutable
- source qualifications remain reusable
- blocked experiments retain resume tokens
- supervisor no-change cycles skip duplicate research work
- restart does not reclassify a prior search exposure as a new hypothesis
