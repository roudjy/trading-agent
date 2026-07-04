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

The supervisor is intentionally isolated from the regular trading agent:

- `qre-research-supervisor` has no `depends_on: agent`
- targeted `docker compose up -d --no-deps qre-research-supervisor` must not start `agent`
- the supervisor healthcheck is the native CLI probe:
  `python -m reporting.qre_research_supervisor --healthcheck`

## Restart Behavior

- leases are bounded and stale-safe
- snapshot lineage set identity is canonical and deterministic across roots, ordering, and restart
- lineage identity includes semantic snapshot content only:
  dataset family, acquisition batches, parent linkage, instruments, timeframe, time range, row counts, fingerprint, source, qualification status, immutability, compatibility status, lineage depth
- lineage identity excludes non-semantic runtime metadata:
  absolute paths, temporary roots, directory enumeration order, JSON key order, `created_at_utc`, filesystem mtimes, and audit-only partition paths
- source qualifications remain reusable
- blocked experiments retain resume tokens
- coherent legacy epoch IDs are reconciled atomically into the published runtime epoch state
- genuine epoch mismatches remain fail-closed and unhealthy
- supervisor no-change cycles skip duplicate research work
- restart does not reclassify a prior search exposure as a new hypothesis

## Runtime Secrets

- the research supervisor does not require trading secrets
- Polymarket runtime secrets are injected only into the regular trading agent via environment variables or `*_FILE` secret paths
- supported names:
  `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_PRIVATE_KEY_FILE`, `POLYMARKET_ALCHEMY_RPC_URL`, `POLYMARKET_ALCHEMY_RPC_URL_FILE`, `POLYMARKET_PROXY_WALLET`, `POLYMARKET_PROXY_WALLET_FILE`
- when Polymarket is active and required runtime secrets are missing, the trading agent fails closed without partial initialization
