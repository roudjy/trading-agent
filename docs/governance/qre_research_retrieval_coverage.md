# QRE Research Retrieval Coverage

`packages.qre_research.retrieval_coverage` measures whether trusted-loop
reasons, failures, blockers, and actions are retrievable from local artifacts
with explicit link signals.

The report uses Roadmap v6 Addendum 2 only as a reference taxonomy for memory
and retrieval coverage. It does not activate Addendum 2 at runtime, grant
authority, mutate routing or sampling, create strategies, use embeddings, call
network services, or use a vector database.

## Commands

Dry-run the coverage report:

```powershell
python -m packages.qre_research.retrieval_coverage --no-write --frozen-utc 2026-05-25T00:00:00Z
```

Read latest status:

```powershell
python -m packages.qre_research.retrieval_coverage --status
```

Write deterministic sidecars under `logs/qre_research_retrieval_coverage/`:

```powershell
python -m packages.qre_research.retrieval_coverage
```

## Operator Output

The output reports:

- which trusted-loop surfaces can be retrieved;
- which surfaces have matches but lack required link signals;
- which local artifacts are missing;
- that retrieval is context only and cannot route, sample, approve, synthesize,
  or mutate campaigns.
