# Minimal v3.15.16 Intelligent Routing — operator runbook

> **Status:** active. Operator runbook for
> [`reporting.intelligent_routing_minimal`](../../reporting/intelligent_routing_minimal.py)
> — the minimal v3.15.16 reset slice declared by queue item 2 in
> [`docs/development_work_queue/seed.jsonl`](../development_work_queue/seed.jsonl).
>
> **Sibling docs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md),
> [`reason_records.md`](reason_records.md),
> [`research_quality_kpis.md`](research_quality_kpis.md).

## TL;DR

A pure, deterministic, read-only projector over an operator-
provided list of routing candidates. For each candidate the
module runs a five-rule decision ladder and emits exactly one
structured routing reason record via
[`reporting.reason_records`](../../reporting/reason_records.py).
The module writes a small digest to
`logs/intelligent_routing_minimal/latest.json` and a JSONL
history. The module **never executes anything**;
`safe_to_execute` is hard-coded `false` at the digest level.

This module is a **sibling** to the pre-existing
[`reporting.intelligent_routing`](../../reporting/intelligent_routing.py)
(the v3.15.16 advisory layer). They coexist:

| Module | Purpose |
|---|---|
| `reporting.intelligent_routing` | Reads existing research artefacts; emits an advisory digest with `routing_effect == "advisory_only"`; no decision ladder, no reason-records emission. |
| `reporting.intelligent_routing_minimal` (this) | Deterministic five-rule decision ladder over operator-provided candidate input; emits one routing reason record per candidate. |

The minimal slice exists because the roadmap reset (ADR-018
draft) declared a new minimal v3.15.16 path that emphasises
reason-records emission, dead-zone suppression, and bounded scope.
The advisory layer remains for the artefact-projection role.

## Decision ladder (deterministic, first-match-wins)

For each candidate, evaluated in this precedence order:

1. `multiplicity_budget_remaining <= 0` → **`reject`**
   (`multiplicity_budget_exceeded`).
2. `dependency_unmet` → **`defer`** (`dependency_unmet`).
3. `dead_zone_dwell >= dead_zone_threshold` →
   **`dead_zone_suppress`** (`dead_zone_dwell_exceeded`).
4. `info_gain_estimate < low_info_threshold` → **`defer`**
   (`info_gain_low`).
5. otherwise → **`prioritize`** (`info_gain_high`).

The four decision values mirror the closed routing decision
vocab in [`reason_records/schema.v1.md`](reason_records/schema.v1.md)
§2.1. The reason codes mirror §3.1.

## Hard guarantees (pinned by tests)

| Guarantee | Test pin |
|---|---|
| Stdlib-only; no subprocess / socket / requests / urllib | `test_module_is_stdlib_only_in_source` |
| No execution-side imports (agent.execution, agent.risk, automation.live, broker, live, paper, shadow, trading) | `test_module_does_not_import_execution_surfaces` |
| Determinism: byte-identical snapshot given the same inputs + frozen timestamp | `test_snapshot_is_byte_deterministic_with_frozen_timestamp` |
| Record-id determinism across runs | `test_record_ids_are_deterministic_across_runs` |
| Atomic-write allowlist substring `logs/intelligent_routing_minimal/` | `test_write_outputs_refuses_outside_allowlist` |
| `safe_to_execute` hard-coded `false` | `test_safe_to_execute_is_hardcoded_false` |
| `mode` only `dry-run` | `test_mode_is_dry_run` |
| Exactly one routing reason record per candidate | `test_each_candidate_emits_exactly_one_routing_reason_record` |
| Five-rule precedence holds across edge cases | Six precedence-specific tests in `test_intelligent_routing_minimal.py` |

## Input schema

The operator (or upstream caller) provides a list of candidates.
Each candidate is a mapping with exactly these five fields:

| Field | Type | Notes |
|---|---|---|
| `campaign_id` | str | Non-empty; ≤ 64 chars; used as the reason-record `subject_id` |
| `info_gain_estimate` | float | Bounded into `[0.0, 1.0]` defensively |
| `dead_zone_dwell` | int | Non-negative ticks; coerced to int |
| `dependency_unmet` | bool | Strict bool; tests pin |
| `multiplicity_budget_remaining` | int | Coerced to int; `<= 0` triggers reject |

The module rejects malformed inputs at `validate_candidates`.

## Output

`logs/intelligent_routing_minimal/latest.json` (and a
timestamped copy + a JSONL history). Schema:

```json
{
  "schema_version": 1,
  "module_version": "v3.15.16-minimal-reset-2026-05-21",
  "report_kind": "intelligent_routing_minimal_digest",
  "generated_at_utc": "<rfc3339-utc-seconds>",
  "mode": "dry-run",
  "safe_to_execute": false,
  "thresholds": {
    "dead_zone_dwell_threshold": 3,
    "low_info_gain_threshold": 0.15
  },
  "counts": {
    "total": <int>,
    "by_decision": {
      "prioritize": <int>,
      "dead_zone_suppress": <int>,
      "defer": <int>,
      "reject": <int>
    }
  },
  "items": [
    {
      "campaign_id": "<str>",
      "decision": "prioritize|defer|dead_zone_suppress|reject",
      "priority_score": <float in [0,1]>,
      "rank": <int>,
      "reason_codes": ["<closed-vocab>"],
      "reason_text": "<str ≤ 300 chars>",
      "record_id": "rr_<hex16>"
    }
  ],
  "final_recommendation": "ready_for_implementation|nothing_ready",
  "note": "<framing string>"
}
```

The `record_id` of each item matches the matching entry in
`logs/reason_records/routing_v1.jsonl`.

## Ranking

`items` are sorted by:

1. `decision_rank` ASC where
   `prioritize=0, defer=1, dead_zone_suppress=2, reject=3`;
2. `priority_score` DESC within the decision bucket;
3. `campaign_id` ASC (deterministic tiebreaker).

The `rank` field is the 0-indexed position after sorting.

## What this module is NOT

- Not authoritative. It does not promote, demote, or rank
  candidates for the funnel policy (ADR-014 §A).
- Not an execution surface. It does not feed any live / paper /
  shadow / broker / execution path (ADR-020 §2).
- Not a kill-switch.
- Not a substitute for the advisory layer
  (`reporting.intelligent_routing`); they ship side-by-side.
- Not diagnostic-aware / state-aware / retrieval-aware /
  source-quality-aware. Those addendum surfaces are
  **DEFERRED** per
  [`roadmap_scope_status.md`](roadmap_scope_status.md) §5.

## Integration

Per the reset doctrine, the minimal slice ships the module +
tests + this runbook. The actual wiring into existing
orchestration is a **separate operator-driven** PR (mirrors the
established `register_*_routes` pattern documented in
[`roadmap_priority.md`](roadmap_priority.md) §"Wiring shape").

Until wiring lands:

- `python -m reporting.intelligent_routing_minimal --status`
  returns `final_recommendation = "not_available"` if no
  snapshot has been written yet.
- The CLI dry-run accepts no candidate source; it runs over an
  empty input set and writes a minimal digest.
- Operator-driven Python callers can invoke
  `collect_snapshot(candidates=[...], frozen_utc=...)` directly.

## CLI

```text
# Default: dry-run on empty input, write the digest, print JSON.
python -m reporting.intelligent_routing_minimal

# Inspection only; no file write.
python -m reporting.intelligent_routing_minimal --no-write

# Read the latest digest without re-running.
python -m reporting.intelligent_routing_minimal --status

# Pin the timestamp (deterministic tests).
python -m reporting.intelligent_routing_minimal --frozen-utc 2026-05-21T00:00:00Z
```

There is **no execute-safe mode**. The CLI rejects any `--mode`
other than `dry-run`. The execute path is intentionally absent —
the module surfaces; the operator decides.

## Cross-references

- [`reporting/intelligent_routing_minimal.py`](../../reporting/intelligent_routing_minimal.py)
- [`reporting/reason_records.py`](../../reporting/reason_records.py)
- [`tests/unit/test_intelligent_routing_minimal.py`](../../tests/unit/test_intelligent_routing_minimal.py)
- [`tests/unit/test_reason_records.py`](../../tests/unit/test_reason_records.py)
- [`docs/governance/reason_records.md`](reason_records.md)
- [`docs/governance/reason_records/schema.v1.md`](reason_records/schema.v1.md)
- [`docs/governance/roadmap_scope_status.md`](roadmap_scope_status.md)
  — canonical active-vs-deferred index.
- [`docs/governance/research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
  — sprint plan that declared the routing reason-record family.

## Update history

- 2026-05-21: initial version. Minimal v3.15.16 reset slice
  shipped alongside the routing/sampling/scoring reason-records
  module.
