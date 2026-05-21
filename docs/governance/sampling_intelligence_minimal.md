# Minimal v3.15.17 Sampling Intelligence — operator runbook

> **Status:** active. Operator runbook for
> [`reporting.sampling_intelligence_minimal`](../../reporting/sampling_intelligence_minimal.py)
> — the minimal v3.15.17 reset slice declared by queue item 3 in
> [`docs/development_work_queue/seed.jsonl`](../development_work_queue/seed.jsonl).
>
> **Sibling docs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md),
> [`reason_records.md`](reason_records.md),
> [`reason_records/schema.v1.md`](reason_records/schema.v1.md),
> [`intelligent_routing_minimal.md`](intelligent_routing_minimal.md),
> [`research_quality_kpis.md`](research_quality_kpis.md).

## TL;DR

A pure, deterministic, read-only projector over an operator-
provided list of stratum candidates. For each candidate the
module runs a six-rule decision ladder and emits exactly one
structured sampling reason record via
[`reporting.reason_records`](../../reporting/reason_records.py).
The module writes a small digest to
`logs/sampling_intelligence_minimal/latest.json` and a JSONL
history. The module **never executes anything**;
`safe_to_execute` is hard-coded `false` at the digest level.

This module is the **sampling sibling** to the
[`reporting.intelligent_routing_minimal`](../../reporting/intelligent_routing_minimal.py)
slice that shipped in PR #268. The two share the reason-record
mechanism (`reporting.reason_records`); they apply that mechanism
to the `routing` and `sampling` families respectively.

The minimal slice exists because the roadmap reset (ADR-018
draft) declared a minimal v3.15.17 path that emphasises
stratified-coverage sampling, null-baseline control sampling, and
sampling-reason-record emission with bounded scope. All
diagnostic-aware (Addendum 1), state/retrieval/knowledge-aware
(Addendum 2), and source-quality-aware (Addendum 3) sampling
surfaces are **DEFERRED**.

## Decision ladder (deterministic, first-match-wins)

For each stratum, evaluated in this precedence order:

1. `multiplicity_budget_remaining <= 0` → **`exclude_region`**
   (`multiplicity_budget_remaining`) — budget exhausted.
2. `null_baseline_required` is True → **`null_baseline`**
   (`null_baseline_required`) — operator declared a null-baseline
   draw is owed.
3. `regime_match` is False → **`exclude_region`**
   (`regime_mismatch`).
4. `coverage_actual + threshold < coverage_target` →
   **`upsample`** (`coverage_imbalance`).
5. `coverage_actual > coverage_target + threshold` →
   **`downsample`** (`coverage_imbalance`).
6. otherwise → **`stratify`** (`multiplicity_budget_remaining`).

The five decision values mirror the closed sampling decision
vocab in [`reason_records/schema.v1.md`](reason_records/schema.v1.md)
§2.2. The reason codes mirror §3.2.

## Hard guarantees (pinned by tests)

| Guarantee | Test pin |
|---|---|
| Stdlib-only; no subprocess / socket / requests / urllib | `test_module_is_stdlib_only_in_source` |
| No execution-side imports (agent.execution, agent.risk, automation.live, broker, live, paper, shadow, trading) | `test_module_does_not_import_execution_surfaces` |
| Determinism: byte-identical snapshot given the same inputs + frozen timestamp | `test_snapshot_is_byte_deterministic_with_frozen_timestamp` |
| Record-id determinism across runs | `test_record_ids_are_deterministic_across_runs` |
| Atomic-write allowlist substring `logs/sampling_intelligence_minimal/` | `test_write_outputs_refuses_outside_allowlist` |
| `safe_to_execute` hard-coded `false` | `test_safe_to_execute_is_hardcoded_false` |
| `mode` only `dry-run` | `test_mode_is_dry_run` |
| Exactly one sampling reason record per candidate | `test_each_candidate_emits_exactly_one_sampling_reason_record` |
| Six-rule precedence holds across edge cases | Six precedence-specific tests in `test_sampling_intelligence_minimal.py` |

## Input schema

The operator (or upstream caller) provides a list of stratum
candidates. Each candidate is a mapping with exactly these six
fields:

| Field | Type | Notes |
|---|---|---|
| `stratum_id` | str | Non-empty; ≤ 64 chars; used as the reason-record `subject_id` |
| `coverage_actual` | float | Bounded into `[0.0, 1.0]` defensively |
| `coverage_target` | float | Bounded into `[0.0, 1.0]` defensively |
| `regime_match` | bool | Strict bool; tests pin |
| `null_baseline_required` | bool | Strict bool; tests pin |
| `multiplicity_budget_remaining` | int | Coerced to int; `<= 0` triggers `exclude_region` |

The module rejects malformed inputs at `validate_candidates`.

## Output

`logs/sampling_intelligence_minimal/latest.json` (and a
timestamped copy + a JSONL history). Schema:

```json
{
  "schema_version": 1,
  "module_version": "v3.15.17-minimal-reset-2026-05-21",
  "report_kind": "sampling_intelligence_minimal_digest",
  "generated_at_utc": "<rfc3339-utc-seconds>",
  "mode": "dry-run",
  "safe_to_execute": false,
  "thresholds": {
    "coverage_imbalance_threshold": 0.10
  },
  "counts": {
    "total": <int>,
    "by_decision": {
      "stratify": <int>,
      "null_baseline": <int>,
      "exclude_region": <int>,
      "downsample": <int>,
      "upsample": <int>
    },
    "actionable": <int>
  },
  "items": [
    {
      "stratum_id": "<str>",
      "decision": "stratify|null_baseline|exclude_region|downsample|upsample",
      "priority_score": <float in [0,1]>,
      "rank": <int>,
      "reason_codes": ["<closed-vocab>"],
      "reason_text": "<str ≤ 300 chars>",
      "record_id": "rr_<hex16>"
    }
  ],
  "final_recommendation": "ready_for_sampling|nothing_ready",
  "note": "<framing string>"
}
```

The `record_id` of each item matches the matching entry in
`logs/reason_records/sampling_v1.jsonl`.

`counts.actionable` is the sum of decisions in
`{stratify, null_baseline, upsample, downsample}`; `exclude_region`
does not contribute to actionable counts.

## Ranking

`items` are sorted by:

1. `decision_rank` ASC where
   `stratify=0, null_baseline=1, upsample=2, downsample=3, exclude_region=4`;
2. `priority_score` DESC within the decision bucket
   (`priority_score` is the absolute coverage-imbalance magnitude);
3. `stratum_id` ASC (deterministic tiebreaker).

The `rank` field is the 0-indexed position after sorting.

## What this module is NOT

- Not authoritative. It does not promote, demote, or rank
  candidates for the funnel policy (ADR-014 §A).
- Not an execution surface. It does not feed any live / paper /
  shadow / broker / execution path (ADR-020 §2).
- Not a kill-switch.
- Not diagnostic-aware / tail-aware / entropy-aware /
  phase-transition-aware / barrier-aware / resonance-aware /
  network-aware / post-shock-aware. Those addendum surfaces are
  **DEFERRED** per
  [`roadmap_scope_status.md`](roadmap_scope_status.md) §5.
- Not state-aware / retrieval-aware / knowledge-aware
  (Addendum 2 — DEFERRED).
- Not source-quality-aware (Addendum 3 — DEFERRED).

## Integration

Per the reset doctrine, the minimal slice ships the module +
tests + this runbook. The actual wiring into existing
orchestration is a **separate operator-driven** PR (mirrors the
established `register_*_routes` pattern documented in
[`intelligent_routing_minimal.md`](intelligent_routing_minimal.md) §"Integration").

Until wiring lands:

- `python -m reporting.sampling_intelligence_minimal --status`
  returns `final_recommendation = "not_available"` if no
  snapshot has been written yet.
- The CLI dry-run accepts no candidate source; it runs over an
  empty input set and writes a minimal digest.
- Operator-driven Python callers can invoke
  `collect_snapshot(candidates=[...], frozen_utc=...)` directly.

## CLI

```text
# Default: dry-run on empty input, write the digest, print JSON.
python -m reporting.sampling_intelligence_minimal

# Inspection only; no file write.
python -m reporting.sampling_intelligence_minimal --no-write

# Read the latest digest without re-running.
python -m reporting.sampling_intelligence_minimal --status

# Pin the timestamp (deterministic tests).
python -m reporting.sampling_intelligence_minimal --frozen-utc 2026-05-21T00:00:00Z
```

There is **no execute-safe mode**. The CLI rejects any `--mode`
other than `dry-run`. The execute path is intentionally absent —
the module surfaces; the operator decides.

## Cross-references

- [`reporting/sampling_intelligence_minimal.py`](../../reporting/sampling_intelligence_minimal.py)
- [`reporting/reason_records.py`](../../reporting/reason_records.py)
- [`reporting/intelligent_routing_minimal.py`](../../reporting/intelligent_routing_minimal.py)
- [`tests/unit/test_sampling_intelligence_minimal.py`](../../tests/unit/test_sampling_intelligence_minimal.py)
- [`tests/unit/test_reason_records.py`](../../tests/unit/test_reason_records.py)
- [`docs/governance/reason_records.md`](reason_records.md)
- [`docs/governance/reason_records/schema.v1.md`](reason_records/schema.v1.md)
- [`docs/governance/intelligent_routing_minimal.md`](intelligent_routing_minimal.md)
- [`docs/governance/roadmap_scope_status.md`](roadmap_scope_status.md)
  — canonical active-vs-deferred index.
- [`docs/governance/research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
  — sprint plan that declared the sampling reason-record family.

## Update history

- 2026-05-21: initial version. Minimal v3.15.17 reset slice
  shipped on top of the v3.15.16 routing slice and the unified
  routing/sampling/scoring reason-records module.
