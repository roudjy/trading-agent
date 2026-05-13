# Agent Activity Center — Read-Only API Contract

> **Status: design / canonical_policy_doc only.** This document
> defines the closed contract for the six read-only `GET`
> endpoints under `/api/agent-control/activity/*`. **No Flask
> blueprint is registered in B2.0.** Implementation is a future
> unit (B2.0c); this contract is what that unit must satisfy.
>
> Companion to [`agent_activity_center_design.md`](agent_activity_center_design.md).

---

## §1 Closed verb set

| Verb | Allowed under `/api/agent-control/activity/*`? |
|---|---|
| `GET` | **yes** — read-only |
| `POST` | **no** |
| `PUT` | **no** |
| `PATCH` | **no** |
| `DELETE` | **no** |
| `OPTIONS` | only CORS preflight if cross-origin is later needed (default: same-origin only) |
| `HEAD` | acceptable for cache validation; behaves as `GET` without body |

**No mutation endpoint exists anywhere under `/api/agent-control/*`.**
See [`agent_activity_center_no_mutation_doctrine.md`](agent_activity_center_no_mutation_doctrine.md)
for the enforcement plan.

---

## §2 Endpoint inventory

Six endpoints, all `GET`, all return a slice of the canonical
aggregator output `logs/development_agent_activity_timeline/latest.json`.

| # | Path | Purpose |
|---|---|---|
| 1 | `GET /api/agent-control/activity/today` | Today cockpit data — counts + headline sections. |
| 2 | `GET /api/agent-control/activity/items` | Filterable WorkItem list. |
| 3 | `GET /api/agent-control/activity/items/<item_id>` | One WorkItem + its events + actions + referenced artefacts. |
| 4 | `GET /api/agent-control/activity/agents` | Per-role activity matrix. |
| 5 | `GET /api/agent-control/activity/artifacts` | ArtifactHealth list. |
| 6 | `GET /api/agent-control/activity/invariants` | InvariantStatus list. |

---

## §3 Endpoint contracts

### 3.1 `GET /api/agent-control/activity/today`

**Query parameters**: none.

**Response (200)**:

```json
{
  "counts": {
    "discovered": 1, "queued": 1, "delegated": 1, "planned": 1,
    "dry_run_ready": 1, "pr_proposed": 0, "pr_opened": 0,
    "ci_feedback": 1, "needs_human": 3, "merge_candidate": 1,
    "blocked": 1, "total_open": 10
  },
  "needs_human":     [ /* WorkItem records where human_needed=true; max 16 */ ],
  "merge_candidate": [ /* WorkItem records in stage merge_candidate; max 16 */ ],
  "ci_feedback":     [ /* WorkItem records in stage ci_feedback; max 16 */ ],
  "blocked":         [ /* WorkItem records in stage done_blocked; max 16 */ ],
  "recent_events":   [ /* last 16 AgentEvent records, newest first */ ],
  "freshness":       { /* per §4 of aggregator schema */ },
  "invariant_status":[ /* per §10 of aggregator schema */ ]
}
```

### 3.2 `GET /api/agent-control/activity/items`

**Query parameters** (all optional, all closed-vocab where
applicable):

| Param | Type | Allowed values |
|---|---|---|
| `stage` | string | One of 11 stage values. Repeatable. |
| `owner_role` | string | One of 16 agent-role values. Repeatable. |
| `human_needed` | boolean | `true` / `false`. |
| `updated_since` | string (ISO 8601 UTC) | Filters by `updated_at >= updated_since`. |

Unknown query keys are silently ignored. Unknown closed-vocab
values return `400 Bad Request` with a JSON body:

```json
{ "error": "invalid_enum", "param": "stage", "value": "<bad>" }
```

**Response (200)**:

```json
{
  "work_items": [ /* filtered WorkItem records; deterministic order */ ],
  "freshness":  { /* per §4 of aggregator schema */ }
}
```

Cap: response includes at most 256 records (matches the aggregator
cap in §13 of the schema). When the filter would yield more, the
response includes:

```json
{ "truncated": true, "total_matching": <count> }
```

### 3.3 `GET /api/agent-control/activity/items/<item_id>`

**Path parameter**: `item_id` (regex `^[A-Za-z0-9_.-]+$`, ≤ 128 chars).

**Response (200)**:

```json
{
  "work_item":              { /* one WorkItem record */ },
  "agent_events":           [ /* AgentEvent records for this item, sorted by timestamp ASC */ ],
  "human_actions":          [ /* HumanAction records for this item, sorted by created_at ASC */ ],
  "artefacts_referenced":   [ /* deduplicated artifact_path values from agent_events[].artifact_path + work_item.source_path */ ]
}
```

**Response (404)** when `item_id` not present in the latest
aggregator snapshot:

```json
{ "error": "not_in_last_snapshot", "item_id": "<id>" }
```

### 3.4 `GET /api/agent-control/activity/agents`

**Query parameters**: none.

**Response (200)**:

```json
{
  "rows": [
    {
      "role": "release_gate_agent",
      "new":         <int ≥ 0>,
      "planned":     <int ≥ 0>,
      "blocked":     <int ≥ 0>,
      "needs_human": <int ≥ 0>,
      "pr_ready":    <int ≥ 0>,
      "last_action": <AgentEvent record OR null>,
      "total":       <int ≥ 0>
    }
    /* …one row per agent_role; sorted by role ASC */
  ]
}
```

### 3.5 `GET /api/agent-control/activity/artifacts`

**Query parameters**: none.

**Response (200)**:

```json
{
  "artifact_health": [ /* all ArtifactHealth records; sorted by path ASC */ ]
}
```

### 3.6 `GET /api/agent-control/activity/invariants`

**Query parameters**: none.

**Response (200)**:

```json
{
  "invariant_status": [ /* all InvariantStatus records; sorted by key ASC */ ]
}
```

---

## §4 HTTP semantics

### 4.1 Cache headers (all six endpoints)

```
Cache-Control: private, max-age=10
ETag: "<hex-prefix-of-sha256(generated_at_utc)>"
```

### 4.2 Conditional requests

- Client sends `If-None-Match: "<etag>"`.
- Server returns `304 Not Modified` (empty body) when the ETag
  matches the current snapshot.
- Server returns `200 OK` with the new body otherwise.

### 4.3 Status codes

| Code | Meaning |
|---|---|
| `200` | OK — fresh snapshot in body. |
| `304` | Not Modified — client cache valid. |
| `400` | Bad Request — invalid query parameter / closed-vocab miss. |
| `401` | Unauthorized — no valid dashboard session. |
| `404` | Not Found — `item_id` not in last snapshot (only on endpoint 3.3). |
| `500` | Internal Server Error — aggregator failed. Body includes `{ "error": "aggregator_failed", "last_good_at": "<ISO timestamp>" }`. |
| `503` | Service Unavailable — aggregator artefact missing entirely. |

### 4.4 Aggregator-failure mode

When the aggregator cannot generate a fresh snapshot, the endpoint
returns `500` with a structured body that names the last
known-good `generated_at_utc`. The PWA shows a red banner
*"Aggregator failed to generate snapshot — showing last good"*
with a "see logs" link to the artefact explorer. The PWA does
**not** retry aggressively — exponential backoff with cap at
60 s.

---

## §5 Authentication & authorisation

- **Authentication**: existing dashboard session cookie. Same
  posture as other read-only dashboard endpoints.
- **Authorisation**: any authenticated dashboard user may read.
  No per-row authorisation in v0.1.
- **No additional approval scope** — the surface is read-only by
  construction, so no scope can elevate authority.
- **No bearer tokens, no API keys, no operator-go phrases** in
  request headers. The session cookie is the only credential.

---

## §6 Content negotiation

- Default response: `application/json; charset=utf-8`.
- `Accept: application/json` accepted.
- Any other `Accept` header returns `200` with the same JSON body
  (no other content type supported in v0.1).
- No XML, no HTML, no protobuf, no msgpack.

---

## §7 Pagination

Endpoints 3.1, 3.2, 3.3, 3.4, 3.5, 3.6 each have a hard array cap
matching the aggregator's bounded sizes (see §13 of the schema).

When a response would exceed the cap, the endpoint sets:

```json
{ "truncated": true, "total_matching": <count> }
```

The PWA renders a "see more in detail view" affordance that
deep-links to the appropriate filter on `/items`. No offset /
cursor parameters in v0.1.

---

## §8 Error responses (canonical)

All error responses use this shape:

```json
{
  "error":  "<closed-vocab error code>",
  "param":  "<optional; offending param name>",
  "value":  "<optional; offending value>",
  "detail": "<optional; ≤ 200 chars, never includes secrets>"
}
```

Closed error-code vocabulary:

| Code | When |
|---|---|
| `invalid_enum` | Query param outside closed vocab. |
| `invalid_format` | Query param violates regex (e.g. malformed `item_id`). |
| `not_in_last_snapshot` | Endpoint 3.3 path param resolves to no WorkItem. |
| `not_authenticated` | Missing or invalid session. |
| `aggregator_failed` | 500 case; aggregator could not produce a snapshot. |
| `aggregator_missing` | 503 case; the canonical artefact file does not exist. |

`detail` must never include `required_phrase`, an operator-go
phrase, an API key, a token, a secret, or any user-bearing
filesystem path beyond the canonical `logs/<group>/<name>.json`
form.

---

## §9 Closed-verb pin (load-bearing for future B2.0c)

The future blueprint implementation must register **only** `GET`
handlers under the `/api/agent-control/activity/*` route group.
The future pin test asserts, by introspection of the registered
URL rules, that for every URL pattern matching
`^/api/agent-control/activity/.*` the allowed methods set is
exactly `{"GET"}` (plus the implicit `{"HEAD", "OPTIONS"}`
auto-added by Flask).

Source-text scan in the same pin test rejects any
`methods=["POST"`, `methods=['POST'`, `methods=["PUT"`,
`methods=['PUT'`, `methods=["PATCH"`, `methods=['PATCH'`,
`methods=["DELETE"`, `methods=['DELETE'` literal under the
blueprint file.

---

## §10 Rate limiting

Out of scope for v0.1. The PWA's natural cadence (60 s background
refresh + on-demand reads) is well within any reasonable rate
limit. Future enhancement.

---

## §11 Versioning

The contract is **additive-only**. Same posture as the aggregator
schema (§15 of the schema doc).

- Adding a new endpoint: non-breaking. Document under §3.
- Adding a new optional response field: non-breaking; consumers
  must ignore unknown keys.
- Adding a new optional query parameter: non-breaking.
- Adding a new closed error code: non-breaking; consumers must
  fall back to neutral error.
- Removing or renaming an endpoint / required field / required
  param: **breaking**; requires a path prefix bump (e.g.
  `/api/agent-control/activity/v2/...`).

---

## §12 Out of scope (explicit)

- **No mutation endpoints anywhere.**
- **No subscription / websocket / SSE endpoints in v0.1** — the
  PWA polls at 60 s. Push notifications (server → client) are a
  separate concern; see [`agent_activity_center_push_notification_safety.md`](agent_activity_center_push_notification_safety.md).
- **No GraphQL.** Six closed-shape endpoints are simpler to audit.
- **No CSV / Excel export endpoints.** Use the artefact explorer's
  raw-JSON drawer for ad-hoc export.
- **No admin / management endpoints.** Dashboard session cookie
  is the only credential; there is no privileged scope.
- **No write endpoints under `/api/agent-control/*`** — the
  prefix is reserved for read-only views.

---

## §13 What this contract is NOT

- Not a request to implement the blueprint now.
- Not an authorisation for any new Flask route to land in this PR.
- Not a request to flip `step5_implementation_allowed` from `Final` `False`.
- Not a schema specification — see [`agent_activity_center_aggregator_schema.md`](agent_activity_center_aggregator_schema.md).
- Not a PWA component contract — that lives in [`agent_activity_center_design.md`](agent_activity_center_design.md) §6.
- Not a push-notification body specification — see [`agent_activity_center_push_notification_safety.md`](agent_activity_center_push_notification_safety.md).
