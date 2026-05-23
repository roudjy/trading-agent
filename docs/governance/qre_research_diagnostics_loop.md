# QRE Research Diagnostics Loop

## Purpose

ADE-QRE-006 adds a read-only diagnostics-loop digest that connects existing
screening failure attribution, failure-action mapping, data readiness, and
research memory sidecars into one operator-readable view.

The digest answers one bounded question: for each observed screening failure,
what existing evidence explains it, and what diagnostic should an operator
inspect next?

## Artifact

- module: `packages.qre_diagnostics.research_diagnostics_loop`
- latest sidecar: `logs/qre_research_diagnostics_loop/latest.json`
- history sidecar: `logs/qre_research_diagnostics_loop/history.jsonl`
- report kind: `qre_research_diagnostics_loop`

The sidecar is deterministic for a fixed input set and timestamp. It is not a
frozen public research contract.

## Inputs

The digest reads these existing local sidecars only:

- `research/screening_failure_attribution_latest.v1.json`
- `logs/failure_action_mapping_minimal/latest.json`
- `logs/qre_data_cache_manifest/latest.json`
- `logs/qre_data_source_quality_readiness/latest.json`
- `logs/qre_research_memory/latest.json`

Missing or invalid upstream sidecars are surfaced explicitly. If no diagnostic
chain can be built, the digest fails closed with
`stop_collect_upstream_sidecars`.

## Safety Boundaries

The diagnostics loop is advisory and read-only:

- no campaign queue mutation
- no routing mutation
- no strategy or preset mutation
- no dashboard mutation routes
- no adaptive learning side effects
- no live, paper, shadow, risk, broker, order-execution, or capital-allocation
  behavior

Stop recommendations such as `stop_until_evidence_improves` are operator-facing
diagnostic states only. They are not executable controls.

## Operator Use

Run a no-write preview:

```powershell
python -m packages.qre_diagnostics.research_diagnostics_loop --no-write --frozen-utc 2026-05-23T00:00:00Z
```

Check the latest written digest status:

```powershell
python -m packages.qre_diagnostics.research_diagnostics_loop --status
```
