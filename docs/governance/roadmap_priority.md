# Roadmap Priority — operator runbook

> Module: `reporting.roadmap_priority`
> Release: v3.15.16.2
> Sibling docs: `recurring_maintenance.md`,
> `roadmap_item_execution_protocol.md`, `autonomy_metrics.md`,
> `mobile_agent_control_pwa.md`.

## TL;DR

A pure, deterministic, read-only projection over the proposal
queue. For every proposal it calls
`reporting.roadmap_execution_protocol.plan_item` and applies a
fixed eligibility filter + a fixed ranking policy. It picks **at
most one** `chosen_next_up` item and writes the result to
`logs/roadmap_priority/latest.json`. The operator (or a strictly
later release) consumes the digest; this module never starts work.

```
proposal_queue/latest.json
        │  (read-only)
        ▼
roadmap_priority.collect_snapshot()
        │
        ├──► roadmap_execution_protocol.plan_item(p)   per proposal
        │           │
        │           ▼
        │    decision / implementation_allowed / requires_human
        │
        ▼
filter → rank → pick → atomic write
        │
        ▼
logs/roadmap_priority/latest.json
```

## Hard guarantees

| guarantee | enforcement |
| --- | --- |
| Stdlib-only | no subprocess, no `gh`, no `git`, no network |
| `safe_to_execute` is always `false` | hard-coded literal in source; pinned by a unit test |
| Missing source ≠ silently OK | `final_recommendation = "not_available"` |
| Malformed source ≠ silently OK | same as above, with `error` reason recorded |
| Determinism | two runs on the same input produce a byte-identical `chosen_next_up` (modulo `generated_at_utc`) |
| Risk classification | delegated 100% to `roadmap_execution_protocol.plan_item`; the prioritizer never re-classifies |
| Atomic writes | `tmp` + `os.replace`, mirrors the rest of `reporting/` |
| No mutation of upstream | the proposal_queue artifact is read with byte-identical content before/after |
| Output scope | writes only under `logs/roadmap_priority/` |

## Eligibility filters

A proposal must pass **all** of these to be considered:

| filter | reason emitted on rejection |
| --- | --- |
| `proposal_id` is a non-empty string | `invalid_proposal_shape` |
| `status == "proposed"` | `status_not_proposed` |
| `risk_class != "HIGH"` | `risk_high_excluded` |
| protocol call must not raise | `protocol_classification_error` |
| protocol `decision == "allowed_read_only"` | `protocol_decision_not_allowed_read_only` |
| protocol `implementation_allowed == True` | `protocol_implementation_not_allowed` |
| protocol `requires_human == False` | `protocol_requires_human` |
| protocol `safe_to_execute == False` | `protocol_safe_to_execute_true` (sanity — protocol never returns True; if it ever does, that is itself a contract breach we surface) |

The protocol module owns:

* item-type classification (docs_only / observability_addition /
  test_only / governance_change / live_paper_shadow_risk /
  external_account_or_secret / telemetry_or_data_egress / ...);
* the closed `ITEM_TYPES_OPEN_TO_IMPLEMENTATION` set that gates
  `implementation_allowed`;
* the `requires_human` decision.

The prioritizer never second-guesses any of these. If you want to
change them, change the protocol — the priority module will follow.

## Ranking policy

Within the eligible set, sort ascending by the tuple
`(risk_rank, type_rank, proposal_id)`:

1. **`risk_rank`**: LOW (0) → MEDIUM (1) → HIGH (2) → UNKNOWN (3).
   HIGH is filtered out before this step; its position here is
   defensive only.
2. **`type_rank`** (most-leveraged unblockers first):
   - `observability_addition` (0)
   - `observability_gap` (1)
   - `reporting_read_only` (2)
   - `docs_only` (3)
   - `testing_gap` (4)
   - `test_only` (5)
   - `ux_gap` (6)
   - `frontend_read_only` (7)
   - `ci_hygiene` (8)
   - `dependency_cleanup` (9)
   - `release_candidate` (10)
   - anything else: 99
3. **`proposal_id`** ascending — stable, deterministic across
   runs.

The first element of the sorted list becomes `chosen_next_up`.
Every other eligible item is in `candidates[]` with its rank.
Every rejected item is in `filtered_out[]` with its
`filter_reason`.

## Final recommendation enum

| value | meaning |
| --- | --- |
| `ready_for_implementation` | a `chosen_next_up` was picked; the operator can review the protocol plan summary and decide whether to start work |
| `nothing_ready` | the source artifact parsed, but no eligible candidate survived the filters |
| `not_available` | the proposal_queue artifact was missing / malformed / not an object — the prioritizer cannot produce a verdict |

## Integration with the recurring scheduler

`reporting.recurring_maintenance` (v3.15.15.23) gains one new
closed job entry in v3.15.16.2:

| `job_type` | risk | needs `gh`? | default interval | default enabled | what it does |
| --- | --- | --- | --- | --- | --- |
| `refresh_roadmap_priority` | LOW | no | 30 min | ✓ | runs `roadmap_priority.collect_snapshot()` + `write_outputs()` |

The job inherits all the supervisor-level safety rails of the
existing scheduler:

* per-job timeout (90 s default — well above the prioritizer's
  observed runtime);
* atomic state persistence;
* failed/blocked job projection into `approval_inbox`;
* `consecutive_failures >= 3` surfaces a `runtime_halt`.

## CLI

```
# Default: dry-run, write the digest, print to stdout.
python -m reporting.roadmap_priority

# Inspection only (no file write).
python -m reporting.roadmap_priority --no-write

# Read the latest digest without re-running.
python -m reporting.roadmap_priority --status

# Pin the timestamp (deterministic tests).
python -m reporting.roadmap_priority --frozen-utc 2026-05-04T12:00:00Z
```

There is **no execute-safe mode**. The CLI rejects any `--mode`
other than `dry-run`. The execute path is intentionally absent —
this release projects, the operator decides.

## Operator workflow

1. Refresh the upstream artifact (one of):
   * `python -m reporting.proposal_queue --mode dry-run` — direct
   * `python -m reporting.workloop_runtime --once` — bundles the
     queue refresh in the workloop tick
   * the `recurring_maintenance` scheduler — the canonical
     scheduled path; runs every 60 minutes for the queue and
     every 30 minutes for the priority projection.
2. Inspect the priority digest:
   ```
   python -m reporting.roadmap_priority --status
   ```
3. If `final_recommendation == "ready_for_implementation"`, the
   `chosen_next_up.protocol_plan_summary` block tells you the
   `proposed_branch`, `required_tests`, and `expected_artifacts`
   the protocol planner produced. The operator may then start
   implementation under that plan.
4. If `final_recommendation == "nothing_ready"`, every eligible
   proposal was rejected by a filter. Inspect `filtered_out[]`
   and `counts.filtered_out_by_reason` to find out why.
5. If `final_recommendation == "not_available"`, refresh the
   proposal queue first (step 1) and re-run.

## PWA card (v3.15.16.5)

The Agent Control PWA's **Inbox** tab gains a "Next up" card
backed by `dashboard/api_roadmap_priority.py` and the new GET-only
endpoint `/api/agent-control/next-up`. The endpoint is a strictly
bounded projection over `logs/roadmap_priority/latest.json`:

| field | source | shape |
| --- | --- | --- |
| `final_recommendation` | digest top-level | `"ready_for_implementation"` / `"nothing_ready"` / `"not_available"` |
| `safe_to_execute` | hard-coded `false` at the boundary | `false` (defensive — even if a corrupted upstream digest sets this to `true`, the boundary projection drops it back to `false`) |
| `chosen_next_up.{proposal_id,title,summary,proposal_type,risk_class,rationale}` | digest | bounded copy |
| `chosen_next_up.protocol_plan_summary.{decision,implementation_allowed,requires_human,risk_class,item_type,proposed_branch,proposed_release_id,required_tests,expected_artifacts}` | digest | bounded copy; the lists are capped at 8 elements each |
| `counts.{proposals_total,eligible_total,filtered_out_total,filtered_out_by_reason}` | digest | bounded copy |
| `needs_human` | derived | `true` when `final_recommendation in {"not_available","unsafe"}` OR the chosen item's protocol plan reports `requires_human=true` |

The full `candidates[]` and `filtered_out[]` arrays are NOT
projected to the PWA card. They stay in the artifact for
operators who need them.

The card never adds an action button. The only interactive
element on the Agent Control surface remains the global "Vernieuw"
refresh button. Operator decisions remain manual: read the card,
optionally re-run `python -m reporting.roadmap_execution_protocol
--plan-item <item> --dry-run` for the full record, then start
work by hand.

### Wiring shape (operator note)

`dashboard/dashboard.py` is on the no-touch list and the
`deny_no_touch` hook blocks the wiring write at the file level
even when the operator authorises it in chat. The two-line edit:

```python
from dashboard.api_roadmap_priority import register_roadmap_priority_routes
register_roadmap_priority_routes(app)
```

therefore lands as a separate one-shot operator-authored
governance-bootstrap PR after v3.15.16.5 merges — same shape that
v3.15.15.21 used to wire `register_agent_control_routes` /
`register_proposal_queue_routes` / `register_approval_inbox_routes`.

Until that bootstrap lands:

* `/api/agent-control/next-up` returns 404 from the dashboard;
* the PWA's frontend client collapses 404 into the standard
  `not_available` envelope;
* the Next-Up card renders its `next-up-not-available` empty
  state;
* nothing crashes, nothing leaks.

## What this module is NOT

* It is **not** an autonomous starter. It does not create a
  branch, open a PR, run tests, or invoke `gh`.
* It is **not** a risk arbiter. Risk classification belongs to
  `roadmap_execution_protocol`. The prioritizer mirrors the
  protocol's verdict.
* It is **not** an approval surface. Approvals go through
  `reporting.approval_inbox` (which already projects
  `failed_automation` / `unknown_state` rows from this module's
  recurring-maintenance integration).
* It is **not** a write target. Other modules must not write to
  `logs/roadmap_priority/` — only the prioritizer does.

## Forward roadmap (not shipped here)

| release | adds |
| --- | --- |
| **v3.15.16.2 (this)** | prioritizer module, recurring-maintenance integration, canonical Roadmap v6.1 doc, runbook |
| v3.15.16.3 | read-only `/api/agent-control/next-up` endpoint and a "Next up" PWA card |
| v3.15.16.4 | operator-authored governance-bootstrap to add `ops/systemd/` to an agent allowlist union, then a recurring-maintenance systemd timer for VPS-side ongoing freshness |
| later | optional explicit dependency declarations in the canonical roadmap doc; the MVP relies on release-id ordering |

## Files added by v3.15.16.2

```
docs/roadmap/Roadmap v6.md                (the canonical structured roadmap)
reporting/roadmap_priority.py             (the prioritizer module)
reporting/recurring_maintenance.py        (one new closed job entry)
tests/unit/test_roadmap_priority.py       (filter + rank + write tests)
tests/unit/test_recurring_maintenance.py  (registry assertion update)
docs/governance/roadmap_priority.md       (this file)
docs/governance/recurring_maintenance.md  (job table addition + cross-reference)
```

No new dependency. No `dashboard/dashboard.py` change. No
`.claude/` change. No frozen contract change. No live / paper /
shadow / risk path touch. No test weakening.

## Cross-references

* `reporting/roadmap_execution_protocol.py` — per-item plan + risk
  arbiter (the canonical source of `decision` /
  `implementation_allowed` / `requires_human`).
* `reporting/proposal_queue.py` — markdown parser that turns
  `docs/roadmap/*` into a typed proposal queue.
* `reporting/recurring_maintenance.py` — typed scheduler.
* `docs/governance/recurring_maintenance.md` — operator runbook
  for the scheduler.
* `docs/governance/roadmap_item_execution_protocol.md` — operator
  runbook for the per-item protocol module.
* `docs/roadmap/Roadmap v6.md` — the canonical structured
  Roadmap v6 the prioritizer ingests via the proposal queue.
