# Minimal v3.15.18 Research Observability — operator runbook

> **Status:** active. Operator runbook for
> [`reporting.research_observability_minimal`](../../reporting/research_observability_minimal.py)
> — the minimal v3.15.18 reset slice declared by queue item 4 in
> [`docs/development_work_queue/seed.jsonl`](../development_work_queue/seed.jsonl).
>
> **Sibling docs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_kpis.md`](research_quality_kpis.md),
> [`candidate_quality_dashboard.md`](candidate_quality_dashboard.md),
> [`reason_records.md`](reason_records.md),
> [`reason_records/schema.v1.md`](reason_records/schema.v1.md),
> [`intelligent_routing_minimal.md`](intelligent_routing_minimal.md),
> [`sampling_intelligence_minimal.md`](sampling_intelligence_minimal.md).

## TL;DR

A pure, deterministic, read-only aggregator over the
currently-shipping research observability surfaces. The module
joins:

| Source | Artefact |
|---|---|
| Routing minimal digest | `logs/intelligent_routing_minimal/latest.json` |
| Sampling minimal digest | `logs/sampling_intelligence_minimal/latest.json` |
| Unified reason-records manifest | `logs/reason_records/manifest.v1.json` |
| Research-quality KPI doctrine | `docs/governance/research_quality_kpis.md` |

into one operator-readable digest at
`logs/research_observability_minimal/latest.json` and a JSONL
history. The module **never executes anything**;
`safe_to_execute` is hard-coded `false` at the digest level.

This module is the **observability sibling** to the v3.15.16
routing slice (PR #268) and the v3.15.17 sampling slice (PR #270).
It does not modify either upstream module; it only reads their
output and the unified reason-records ledger.

The minimal slice exists because the roadmap reset (ADR-018
draft) declared a minimal v3.15.18 path that emphasises
operator-readable summaries of existing surfaces with an
enforced operator-attention budget (OAB). The full
candidate-quality dashboard spec
([`candidate_quality_dashboard.md`](candidate_quality_dashboard.md))
includes additional surfaces (multiplicity ledger, paper-readiness
checklist, per-candidate KPI rendering) that are **not yet
implemented**; the minimal slice intentionally surfaces only what
the active queue has already produced.

All Addendum 1 / 2 / 3 surfaces (KG visualisation, retrieval debug,
full lineage UI, source-quality dashboards) are **DEFERRED**.

## What this aggregator surfaces

### Operator-Attention Budget (OAB) enforcement

For each `subject_id` that appears in any reason-records family,
the aggregator counts the number of distinct families with at
least one record (routing / sampling / scoring). The pinned cap is
`DEFAULT_VISIBLE_SURFACES_PER_CAMPAIGN_CAP = 3`. Subjects above
the cap are reported in `attention_overflow_subjects`; subjects at
the cap are reported in `near_cap_subjects`.

This implements the OAB KPI from
[`research_quality_kpis.md`](research_quality_kpis.md) §3 at the
read layer. It does **not** suppress or hide records; it surfaces
the overflow so the operator can act.

### Cross-family subject lineage

The aggregator emits a `cross_family_subjects.top_by_surface_count`
block listing the top-N subjects by distinct-family count. This is
the minimal lineage surface declared by the queue item — it
joins subjects across families without introducing a new authority
domain.

### Source digests

Each upstream artefact is surfaced as an `available: true|false`
entry under `sources`. Missing artefacts never raise; they yield
deterministic placeholders so the digest stays operator-readable
even before any v3.15.x slice has written its latest.

### KPI doctrine pointer

The aggregator surfaces the seven KPI identifiers
(`TTFPRC`, `OOS_DSR`, `MASQ`, `NMBR`, `DZCR`, `OAB`, `CRSR`) and a
pointer to the doctrine document. Numeric KPI values are
**not** computed by this slice — they require a canonical KPI
artefact that ships in a separate operator-driven PR.

## Hard guarantees (pinned by tests)

| Guarantee | Test pin |
|---|---|
| Stdlib-only; no subprocess / socket / requests / urllib | `test_module_is_stdlib_only_in_source` |
| No execution-side imports (agent.execution, agent.risk, automation.live, broker, live, paper, shadow, trading) | `test_module_does_not_import_execution_surfaces` |
| Determinism: byte-identical snapshot given the same inputs + frozen timestamp | `test_snapshot_is_byte_deterministic_with_frozen_timestamp` |
| Atomic-write allowlist substring `logs/research_observability_minimal/` | `test_write_outputs_refuses_outside_allowlist` |
| `safe_to_execute` hard-coded `false` | `test_safe_to_execute_is_hardcoded_false` |
| `mode` only `dry-run` | `test_mode_is_dry_run` |
| OAB cap is enforced; subjects above cap appear in `attention_overflow_subjects` | `test_attention_overflow_enforced_when_subject_exceeds_cap` |
| No `dashboard/dashboard.py` mutation (CQD-I2) | `test_module_does_not_modify_dashboard_dashboard_py_source` |
| All four upstream sources are surfaced (closed source-ids set) | `test_sources_block_carries_closed_source_id_set` |
| Source-id set is pinned at `SOURCE_IDS` | `test_source_ids_are_pinned` |

## Output

`logs/research_observability_minimal/latest.json` (and a
timestamped copy + a JSONL history). Schema:

```json
{
  "schema_version": 1,
  "module_version": "v3.15.18-minimal-reset-2026-05-21",
  "report_kind": "research_observability_minimal_digest",
  "generated_at_utc": "<rfc3339-utc-seconds>",
  "mode": "dry-run",
  "safe_to_execute": false,
  "operator_attention_budget": {
    "visible_surfaces_per_campaign_cap": 3,
    "subjects_observed": <int>,
    "attention_overflow_subjects": ["<subject_id>", "..."],
    "near_cap_subjects": ["<subject_id>", "..."],
    "attention_overflow_count": <int>,
    "near_cap_count": <int>
  },
  "sources": {
    "routing_minimal": {
      "source_id": "routing_minimal",
      "available": <bool>,
      "path": "logs/intelligent_routing_minimal/latest.json",
      "generated_at_utc": "<rfc3339|null>",
      "module_version": "<str|null>",
      "counts": {
        "total": <int>,
        "by_decision": { "...": <int> }
      },
      "final_recommendation": "<str|null>"
    },
    "sampling_minimal": { ... },
    "reason_records": {
      "source_id": "reason_records",
      "available": <bool>,
      "manifest_path": "logs/reason_records/manifest.v1.json",
      "total_records": <int>,
      "by_kind": { "routing": <int>, "sampling": <int>, "scoring": <int> },
      "by_decision": { ... },
      "by_subject_id_top": { "<subject_id>": <int> },
      "first_record_ts_utc": "<rfc3339|null>",
      "last_record_ts_utc": "<rfc3339|null>"
    },
    "research_quality_kpis_doc": {
      "source_id": "research_quality_kpis_doc",
      "available": <bool>,
      "path": "docs/governance/research_quality_kpis.md",
      "kpi_ids": ["TTFPRC", "OOS_DSR", "MASQ", "NMBR", "DZCR", "OAB", "CRSR"],
      "kpi_values_available": false,
      "note": "<framing string>"
    }
  },
  "cross_family_subjects": {
    "total": <int>,
    "top_by_surface_count": { "<subject_id>": <int> }
  },
  "final_recommendation": "operator_review_available|nothing_to_review",
  "note": "<framing string>"
}
```

## What this module is NOT

- Not a promotion path. Promotion happens via the funnel policy
  (ADR-014 §A).
- Not a kill-switch.
- Not the candidate-quality dashboard. The full dashboard spec
  ([`candidate_quality_dashboard.md`](candidate_quality_dashboard.md))
  includes surfaces (multiplicity ledger, per-candidate
  paper-readiness, KPI numeric values, dead-zone share trend) that
  this minimal slice does **not** ship.
- Not a wiring into `dashboard/dashboard.py`. Per CQD-I2, the
  dashboard registration is a separate operator-driven
  governance-bootstrap PR (mirrors the `register_*_routes`
  pattern). The minimal slice ships the read-only aggregator only.
- Not a new authority. All numbers are derived from existing
  canonical / derived artefacts.
- Not state-aware / retrieval-aware / knowledge-aware
  (Addendum 2 — DEFERRED).
- Not source-quality-aware (Addendum 3 — DEFERRED).
- Not adaptive. The aggregator does not modify routing,
  sampling, scoring, or any other surface based on what it reads.

## CLI

```text
# Default: aggregate, write the digest, print JSON.
python -m reporting.research_observability_minimal

# Inspection only; no file write.
python -m reporting.research_observability_minimal --no-write

# Read the latest digest without re-running.
python -m reporting.research_observability_minimal --status

# Pin the timestamp (deterministic tests).
python -m reporting.research_observability_minimal --frozen-utc 2026-05-21T00:00:00Z
```

There is **no execute-safe mode**. The CLI rejects any `--mode`
other than `dry-run`. The execute path is intentionally absent —
the module surfaces; the operator decides.

## Cross-references

- [`reporting/research_observability_minimal.py`](../../reporting/research_observability_minimal.py)
- [`reporting/reason_records.py`](../../reporting/reason_records.py)
- [`reporting/intelligent_routing_minimal.py`](../../reporting/intelligent_routing_minimal.py)
- [`reporting/sampling_intelligence_minimal.py`](../../reporting/sampling_intelligence_minimal.py)
- [`tests/unit/test_research_observability_minimal.py`](../../tests/unit/test_research_observability_minimal.py)
- [`docs/governance/reason_records.md`](reason_records.md)
- [`docs/governance/reason_records/schema.v1.md`](reason_records/schema.v1.md)
- [`docs/governance/candidate_quality_dashboard.md`](candidate_quality_dashboard.md)
- [`docs/governance/research_quality_kpis.md`](research_quality_kpis.md)
- [`docs/governance/intelligent_routing_minimal.md`](intelligent_routing_minimal.md)
- [`docs/governance/sampling_intelligence_minimal.md`](sampling_intelligence_minimal.md)
- [`docs/governance/roadmap_scope_status.md`](roadmap_scope_status.md)
  — canonical active-vs-deferred index.

## Update history

- 2026-05-21: initial version. Minimal v3.15.18 reset slice
  shipped on top of the v3.15.16 routing slice and v3.15.17
  sampling slice.
