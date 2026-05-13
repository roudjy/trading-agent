# Agent Activity Center — Aggregator Schema

> **Status: design / canonical_policy_doc only.** This document
> defines the closed schema for the future aggregator output
> `logs/development_agent_activity_timeline/latest.json`. **No
> module emits this artefact yet.** The aggregator implementation
> is a future unit (B2.0b); this schema is the contract that unit
> must satisfy.
>
> Companion to [`agent_activity_center_design.md`](agent_activity_center_design.md).

---

## §1 Artefact path

```
logs/development_agent_activity_timeline/latest.json
```

The artefact is written atomically by the aggregator (future B2.0b).
Module version anchor: `aat.v0.1`. Schema version: `1`.

---

## §2 Read-only invariants (load-bearing)

The aggregator implementation (B2.0b) must satisfy all of the
following. Each is enforced by a future pin test.

- **Sentinel-restricted write path.** The aggregator's atomic-write
  helper must refuse any path whose POSIX form does not contain
  `logs/development_agent_activity_timeline/`. Pattern mirrors
  `reporting.development_step5_loop._atomic_write_json`'s
  `logs/step5_*/` sentinel.
- **Never writes to seed files.** The module must contain no code
  path that opens `seed.jsonl`, `generated_seed.jsonl`, or
  `delegation_seed.jsonl` for writing. AST-level pin.
- **Stdlib + ADE peers only.** No imports of `subprocess`,
  `socket`, `urllib`, `requests`, `httpx`, `aiohttp`. No imports
  of `research`, `dashboard.dashboard`, `automation`, `broker`,
  `agent.risk`, `agent.execution`, `reporting.intelligent_routing`.
- **Deterministic output.** Sorted keys, indented JSON. Same
  upstream artefact contents + same injected `generated_at_utc`
  → byte-identical aggregator output.
- **Read-only over upstreams.** The aggregator must not modify any
  upstream artefact. Future pin test: before/after sha256
  comparison of every upstream artefact across a single aggregator
  run.
- **No `gh` / `git` invocation.** AST + source-text scan.

---

## §3 Top-level envelope schema

```json
{
  "schema_version": 1,
  "module_version": "aat.v0.1",
  "report_kind": "agent_activity_timeline",
  "generated_at_utc": "<ISO 8601 UTC timestamp>",
  "freshness": { /* see §4 */ },
  "counts": { /* see §5 */ },
  "work_items": [ /* see §6 */ ],
  "agent_events": [ /* see §7 */ ],
  "human_actions": [ /* see §8 */ ],
  "artifact_health": [ /* see §9 */ ],
  "invariant_status": [ /* see §10 */ ],
  "vocabularies": { /* echo of closed vocabularies; see §11 */ }
}
```

All top-level keys are **required**. Field order in the on-disk
JSON is alphabetical (sorted keys).

---

## §4 `freshness`

| Key | Type | Required | Description |
|---|---|---|---|
| `generated_at_utc` | string (ISO 8601) | required | Matches the envelope `generated_at_utc`. |
| `oldest_artifact_age_seconds` | integer | required | Age of the oldest upstream artefact in seconds. |
| `any_stale` | boolean | required | At least one upstream artefact is past its TTL. |
| `any_malformed` | boolean | required | At least one upstream artefact failed to parse. |
| `background_refreshing` | boolean | required | Aggregator is mid-cycle. |
| `ttl_seconds_by_path` | object | required | Per-artefact TTL in seconds. Closed map; keys are canonical artefact paths. |

Example:

```json
{
  "freshness": {
    "generated_at_utc": "2026-05-13T08:42:00Z",
    "oldest_artifact_age_seconds": 900,
    "any_stale": true,
    "any_malformed": false,
    "background_refreshing": false,
    "ttl_seconds_by_path": {
      "logs/development_delegation/latest.json": 900,
      "logs/development_work_queue/latest.json": 600
    }
  }
}
```

---

## §5 `counts`

Required keys (all integers ≥ 0). One per closed stage value plus
two derived counters (`needs_human`, `total_open`).

| Key | Description |
|---|---|
| `discovered` | Items in stage `discovered`. |
| `queued` | Items in stage `queued`. |
| `delegated` | Items in stage `delegated`. |
| `planned` | Items in stage `planned`. |
| `dry_run_ready` | Items in stage `dry_run_ready`. |
| `pr_proposed` | Items in stage `pr_proposed`. |
| `pr_opened` | Items in stage `pr_opened`. |
| `ci_feedback` | Items in stage `ci_feedback`. |
| `needs_human` | Items with `human_needed=true` (cross-stage). |
| `merge_candidate` | Items in stage `merge_candidate`. |
| `blocked` | Items in stage `done_blocked`. |
| `total_open` | Items not in stage `done_blocked`. |

---

## §6 `work_items[]`

Each WorkItem record:

| Field | Type | Required | Closed-vocab | Description |
|---|---|---|---|---|
| `item_id` | string | required | no | Opaque stable id (regex `^[A-Za-z0-9_.-]+$`). |
| `title` | string | required | no | ≤ 200 chars. |
| `source_kind` | string | required | yes | One of: `roadmap_v6`, `work_queue`, `delegation`, `bugfix_loop`, `release_gate`, `generated_lane`, `generated_lane_promotion`, `step5_plan`, `step5_loop`, `ci_feedback`, `merge_preflight`, `operational_digest`, `addendum_loop`. |
| `source_path` | string | required | no | Canonical `logs/<group>/<name>.json` or `roadmap_v6/...` path. |
| `current_stage` | string | required | yes | One of the 11 stage values (§10 of design doc). |
| `owner_role` | string | required | yes | One of the 16 agent roles (§5.5 of design doc). |
| `risk` | string | required | yes | `low / medium / high / critical`. |
| `human_needed` | boolean | required | no | True if a HumanAction is open for this item. |
| `latest_verdict` | string | required | no | ≤ 200 chars. Free-text; mono-rendered. |
| `next_action` | string | required | no | ≤ 200 chars. |
| `updated_at` | string (ISO 8601) | required | no | UTC. |
| `summary` | string | required | no | ≤ 600 chars. |
| `event_ids` | array of string | optional | no | Cross-reference into `agent_events[]`. |

Per-record byte stability: same upstream rows + same
`generated_at_utc` → byte-identical WorkItem record (sorted keys).

---

## §7 `agent_events[]`

Each AgentEvent record:

| Field | Type | Required | Closed-vocab | Description |
|---|---|---|---|---|
| `event_id` | string | required | no | Opaque stable id (regex `^ev_[A-Za-z0-9_]+$`). |
| `item_id` | string | required | no | Matches a `work_items[].item_id`. |
| `timestamp` | string (ISO 8601) | required | no | UTC. |
| `agent_role` | string | required | yes | One of the 16 agent roles. |
| `module` | string | required | no | ADE-core module name (e.g. `development_work_queue`, `step5_loop`, `generated_lane_a18c`). |
| `event_type` | string | required | yes | `discovered / annotated / queued / delegated / plan_drafted / review / verdict / generated / detected / ci_result / rerun_queued / dry_run / preflight / quarantined / in_review / surfaced`. |
| `summary` | string | required | no | ≤ 200 chars. |
| `decision` | string | required | yes | One of the 16 decision values (§10 of design doc). |
| `reason` | string | required | no | ≤ 200 chars. |
| `artifact_path` | string | required | no | Canonical artefact path the event derives from. |
| `severity` | string | required | yes | `info / warn / human / error`. |

---

## §8 `human_actions[]`

Each HumanAction record:

| Field | Type | Required | Closed-vocab | Description |
|---|---|---|---|---|
| `action_id` | string | required | no | Opaque stable id (regex `^ha_[A-Za-z0-9_]+$`). |
| `item_id` | string | required | no | Matches a `work_items[].item_id`. |
| `severity` | string | required | yes | `low / medium / high`. |
| `title` | string | required | no | ≤ 200 chars. |
| `why_required` | string | required | no | ≤ 600 chars. Plain-language reason. |
| `required_phrase` | string OR null | optional | no | Operator-go phrase, copy-only. **Never surfaced in push notification bodies** — see [`agent_activity_center_push_notification_safety.md`](agent_activity_center_push_notification_safety.md). |
| `safe_to_ignore` | boolean | required | no | True for informational items. |
| `copy_only` | boolean | required | no | Always `true` for v0.1; reserved for future expansion. |
| `source_artifact_path` | string | required | no | Canonical artefact path the action derives from. |
| `suggested_role` | string | required | yes | One of the 16 agent roles. |
| `created_at` | string (ISO 8601) | required | no | UTC. |

Pin: when `safe_to_ignore=true`, `required_phrase` must be `null`.

---

## §9 `artifact_health[]`

Each ArtifactHealth record:

| Field | Type | Required | Closed-vocab | Description |
|---|---|---|---|---|
| `path` | string | required | no | Canonical artefact path. |
| `group` | string | required | yes | `queue / loops / step5 / gates / generated / digest / seed`. |
| `fresh` | boolean | required | no | Past `ttl_seconds_by_path` ⇒ false. |
| `parse_ok` | boolean | required | no | JSON / JSONL parsed cleanly. |
| `row_count` | integer | required | no | Rows in the artefact (`0` for snapshots). |
| `last_modified` | string (ISO 8601) | required | no | UTC. |
| `module_version` | string | required | no | Producer module version anchor (e.g. `wq.v4.2`, `s5.v6.1`). |
| `has_summary` | boolean | required | no | The artefact carries a `summary` or equivalent at the top level. |
| `parse_error` | string | optional | no | Present iff `parse_ok=false`. ≤ 200 chars. |
| `read_only_warning` | string | optional | no | Present for `seed` group entries: `"Read-only · UI must not write"`. |

---

## §10 `invariant_status[]`

Each InvariantStatus record:

| Field | Type | Required | Closed-vocab | Description |
|---|---|---|---|---|
| `key` | string | required | yes | One of: `level_6`, `step5_substage`, `step5_implementation_allowed`, `live_merge_implemented`, `deploy_coupled`, `a18c_enabled`, `a18b_writer_enabled`, `n5b_live_execute`, `agent_service`. |
| `label` | string | required | no | Human-readable label. |
| `value` | string OR boolean | required | no | Current value. |
| `tone` | string | required | yes | `on / off / danger_off / info / unknown`. |
| `detail` | string | required | no | ≤ 200 chars. Long-form description for the pill tooltip. |

Pin: `level_6.value` must always be `"permanently_disabled"` and
`level_6.tone` must always be `"danger_off"`. Pin: when
`step5_implementation_allowed.value` is `false`, the tone must be
`"off"` (never `"on"`).

---

## §11 `vocabularies`

Echo of all eight closed status vocabularies (§10 of design doc).
Lets the PWA verify it understands every value at hand and fall
back to neutral gray on missing-case.

```json
"vocabularies": {
  "stage":           ["discovered", "queued", "delegated", "planned",
                      "dry_run_ready", "pr_proposed", "pr_opened",
                      "ci_feedback", "needs_human", "merge_candidate",
                      "done_blocked"],
  "severity":        ["info", "warn", "human", "error"],
  "decision":        ["queue", "delegate", "plan", "generate",
                      "approve_dry_run", "require_human", "flag",
                      "flag_flaky", "quarantine", "review", "rerun",
                      "surface", "advise_merge", "no_op", "ingest",
                      "annotate"],
  "risk":            ["low", "medium", "high", "critical"],
  "freshness":       ["fresh", "stale", "missing", "malformed"],
  "artifact_health": ["ok", "stale", "malformed", "missing", "unreadable"],
  "human_action":    ["operator_go_required", "review_recommended",
                      "copy_only", "informational"],
  "invariant_state": ["on", "off", "danger_off", "info", "unknown"]
}
```

---

## §12 Determinism guarantees

- The pure scorer accepts an injectable `generated_at_utc`. With
  the same upstream artefact contents and the same injected
  timestamp, output bytes are identical.
- All arrays are sorted by a deterministic key:
  - `work_items[]` → sorted by `item_id` ASC.
  - `agent_events[]` → sorted by `(timestamp ASC, event_id ASC)`.
  - `human_actions[]` → sorted by `action_id` ASC.
  - `artifact_health[]` → sorted by `path` ASC.
  - `invariant_status[]` → sorted by `key` ASC.
- Atomic write: write to `<path>.tmp`, `os.replace(...)` into place.
- Determinism pin test (future B2.0b): byte-identical artefact
  across two consecutive calls with the same injected timestamp.

---

## §13 Bounded sizes

| Array | Cap | Behaviour when over cap |
|---|---|---|
| `work_items[]` | 256 | Older items (by `updated_at`) dropped silently; counter remains accurate. |
| `agent_events[]` | 2048 | Older events dropped (paginated to detail view via `items/<item_id>` endpoint). |
| `human_actions[]` | 64 | Older actions dropped; banner warns "more in inbox". |
| `artifact_health[]` | 64 | Unbounded in practice; closed-set list. |
| `invariant_status[]` | 32 | Closed-set list. |

Cap values are bytewise-pinned constants in the future aggregator
module. Changing a cap requires a pinned test update.

---

## §14 Examples

### 14.1 Minimal valid artefact (no work in flight)

```json
{
  "schema_version": 1,
  "module_version": "aat.v0.1",
  "report_kind": "agent_activity_timeline",
  "generated_at_utc": "2026-05-13T08:42:00Z",
  "freshness": {
    "generated_at_utc": "2026-05-13T08:42:00Z",
    "oldest_artifact_age_seconds": 0,
    "any_stale": false,
    "any_malformed": false,
    "background_refreshing": false,
    "ttl_seconds_by_path": {}
  },
  "counts": {
    "discovered": 0, "queued": 0, "delegated": 0, "planned": 0,
    "dry_run_ready": 0, "pr_proposed": 0, "pr_opened": 0,
    "ci_feedback": 0, "needs_human": 0, "merge_candidate": 0,
    "blocked": 0, "total_open": 0
  },
  "work_items": [],
  "agent_events": [],
  "human_actions": [],
  "artifact_health": [],
  "invariant_status": [
    {
      "key": "level_6", "label": "Level 6",
      "value": "permanently_disabled", "tone": "danger_off",
      "detail": "Level 6 capabilities are permanently disabled per ADR-015 Doctrine 1."
    }
  ],
  "vocabularies": { /* … see §11 */ }
}
```

### 14.2 Stale + malformed envelope (graceful degradation)

```json
{
  "freshness": {
    "oldest_artifact_age_seconds": 9900,
    "any_stale": true,
    "any_malformed": true
  },
  "artifact_health": [
    {
      "path": "logs/development_addendum_loop/latest.json",
      "group": "loops",
      "fresh": false,
      "parse_ok": false,
      "row_count": 0,
      "last_modified": "2026-05-13T05:57:00Z",
      "module_version": "add.v1.8",
      "has_summary": false,
      "parse_error": "line 12: unterminated string"
    }
  ]
}
```

The PWA renders the row visibly with a red *malformed* badge; the
detail drawer shows the parse error and notes "quarantined · lane
unaffected".

---

## §15 Schema versioning

Schema additions are non-breaking and operate under an
*additive-only* regime — same posture as A8/A9/A12 outputs and the
existing `**/*_latest.v1.json` frozen v1 contracts:

- Adding a new top-level key: non-breaking; consumers must ignore
  unknown keys.
- Adding a new field to an existing record: non-breaking; the new
  field is `optional`.
- Adding a new closed-vocab value: requires a code change in the
  vocabularies block AND in the producer module AND a pinned test.
- Removing or renaming a key: **breaking**; requires a schema
  version bump from `1` to `2` and a docs-modernisation cycle.

`schema_version` is a numeric integer, monotonically increasing.

---

## §16 What this schema is NOT

- Not a request to implement the aggregator now.
- Not an authorisation for any new module to land in this PR.
- Not a request to flip `step5_implementation_allowed` from `Final` `False`.
- Not a Flask blueprint contract — see [`agent_activity_center_api_contract.md`](agent_activity_center_api_contract.md).
- Not a PWA component contract — that lives in [`agent_activity_center_design.md`](agent_activity_center_design.md) §6.
- Not a push-notification body specification — see [`agent_activity_center_push_notification_safety.md`](agent_activity_center_push_notification_safety.md).
