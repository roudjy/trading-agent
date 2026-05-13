# Agent Activity Center — Push-Notification Safety Doctrine

> **Status: design / canonical_policy_doc only.** This document
> defines the load-bearing pins for any future push-notification
> publisher that surfaces Agent Activity Center events. **No
> publisher ships in B2.0.** Implementation is a future unit
> (B2.0e); this doctrine is what that unit must satisfy.
>
> Companion to [`agent_activity_center_design.md`](agent_activity_center_design.md).

---

## §1 The doctrine in one sentence

**Push-notification bodies never contain `required_phrase`, an
operator-go phrase, an API key, a token, a secret, a bearer
credential, or any other sensitive value.** Bodies are bounded,
non-actionable, and safe to render on a locked-screen preview.

---

## §2 Forbidden body content

Push notification bodies must NEVER include:

| Forbidden | Rationale |
|---|---|
| `required_phrase` field value from any HumanAction | Phrase grants authority when read aloud; leaking it on a lock-screen breaks the out-of-band assumption. |
| Any operator-go phrase string (e.g. `OPERATOR-GO ...`, `GO Batch ...`, `GO A18 ...`, `GO enable A18c on VPS`) | Same reason. |
| `api_key`, `apiKey`, `api-key` values | Direct credential leak. |
| `secret`, `client_secret`, `private_key` values | Same. |
| `token`, `access_token`, `refresh_token`, `bearer ...` values | Same. |
| `password`, `passcode` values | Same. |
| Any `state/*.secret` content | Same. |
| Any `.env`, `.env.*` content | Same. |
| Raw `seed.jsonl`, `generated_seed.jsonl`, `delegation_seed.jsonl` contents | Internal artefact leak; some lines may carry hashable seed material. |
| Internal git SHAs longer than 7 chars | Defence-in-depth — reduces fingerprinting surface. |
| Full filesystem paths beyond the canonical `logs/<group>/<name>.json` form | Defence-in-depth. |
| HTML / markdown that could render rich content | Lock-screen previews truncate inconsistently; plain text only. |

---

## §3 Canonical safe body shapes

### 3.1 Needs-human pings

```
N new item(s) need your review · <agent_role> · <risk_band>
```

Examples:

- `"1 new item needs your review · release_gate_agent · medium risk"`
- `"3 new items need your review · determinism_guardian · high risk"`
- `"1 new item needs your review · observability_guardian · low risk"`

### 3.2 Invariant-drift alerts (future)

```
Invariant drift detected · <invariant_key>
```

Example:

- `"Invariant drift detected · a18c_enabled"`

The invariant **key** is closed-vocab and safe (it does not
encode any secret).

### 3.3 Aggregator-failure alerts (future)

```
ADE aggregator failed · last good <relative-time>
```

Example:

- `"ADE aggregator failed · last good 11m ago"`

---

## §4 Tap behaviour

### 4.1 Deep-link only

Notification tap **always** opens a read-only deep-link inside
the authenticated PWA app shell:

- Needs-human ping → `/inbox` or `/item/<item_id>`.
- Invariant-drift alert → `/safety`.
- Aggregator-failure alert → `/artefacts`.

### 4.2 No tap approves

Tapping a notification **never**:

- Issues an operator-go phrase.
- Mutates server state.
- Marks an item reviewed (even local-only).
- Authenticates the operator (the operator must authenticate
  through the existing dashboard session cookie).

### 4.3 Authentication first

If the operator is not already authenticated, the deep-link first
routes through the existing login flow, then to the target view.
The notification body itself never carries an authentication
token.

---

## §5 Server-side body construction pins (future B2.0e)

The future push-publisher module must satisfy all of the
following. Each is enforced by a pin test in the B2.0e PR.

### 5.1 AST-level forbidden imports

- No `subprocess`, `socket`, `urllib`, `requests`, `httpx`,
  `aiohttp` imports beyond what is required to call the push
  vendor's HTTPS API.
- The push vendor's library is the only outbound network
  dependency permitted, and it is wrapped in a thin module that
  exposes a `publish(title, body)` shape — no leak surface.

### 5.2 Source-text rejection list

The publisher's source must not contain any of:

- `required_phrase`
- `operator_go_phrase`
- `api_key`
- `apiKey`
- `secret`
- `token`
- `bearer`
- `password`
- `OPERATOR-GO`
- `GO Batch`
- `GO A18`
- `GO enable`

Sweep is run on the publisher module's own source (via
`inspect.getsource`) AND on every module the publisher imports
transitively if the import is local to `reporting/`.

### 5.3 Body length cap

`body` is bounded:

- ≤ 80 chars (single-line; safe across all major push vendors'
  lock-screen previews).
- ASCII printable only (no embedded null bytes, no control
  characters, no rich-text markup).

### 5.4 Builder closed-vocab

The body builder accepts only closed-vocab inputs:

- `agent_role` from the 16-value role vocabulary (§5.5 of design doc).
- `risk_band` from `low / medium / high / critical`.
- `invariant_key` from the 9-value invariant vocabulary
  (§10 of aggregator schema).
- `count` from a bounded integer range (1–999).

Any input outside its closed vocab is rejected at the builder
boundary, not silently truncated.

---

## §6 Client-side handling pins (future B2.0d)

The PWA's service worker / notification-click handler must
satisfy:

### 6.1 No body interpretation

The handler reads only the `notification.data.deep_link` field
(URL string). It does not parse the `body` for any meaning beyond
display.

### 6.2 Deep-link validation

The handler validates that the `deep_link` field:

- Starts with `/` (relative path).
- Matches one of the closed prefixes: `/inbox`, `/item/`,
  `/pipeline`, `/safety`, `/artefacts`.
- Contains no `<script>` or HTML.
- Contains no `javascript:` scheme.

Any failure routes to `/safety` (the most defensible read-only
fallback).

### 6.3 No background sync triggers from notification

The handler must not register a background sync, must not start a
service-worker `fetch` other than for the deep-link target, and
must not write to IndexedDB / localStorage beyond updating an
"last notification at" timestamp.

---

## §7 Push-vendor configuration pins

When B2.0e ships, the operator configures the push vendor with:

- **No vendor template variables that interpolate user-bearing
  fields.** The publisher controls body construction; the vendor
  receives a complete plain-text string.
- **No vendor-side analytics opt-in** beyond what is necessary
  to confirm delivery. No body-text logging.
- **Transport: HTTPS only.** No HTTP. No vendor-specific protocols
  that lack TLS.
- **Vendor credentials live in `state/*.secret` or `.env.*`**
  per existing secret-handling doctrine. The publisher reads them
  through the existing config layer; they never reach the body.

---

## §8 Linting and CI

### 8.1 B2.0e lint hook

The lint hook scans:

- Every Python file under `reporting/` that imports the push
  vendor's library (or any wrapper around it).
- The publisher module's full source (recursive into its own
  helpers).

Failure mode: build fails with a closed-vocab error code:

```
push_body_safety_violation: token=<forbidden-substring> file=<path> line=<n>
```

### 8.2 CI integration

The lint hook runs in the existing `governance-lint` CI step
(non-blocking advisory) AND as a dedicated `push-body-safety`
step (blocking when B2.0e ships).

---

## §9 Test matrix (future B2.0e)

| Test | Pins |
|---|---|
| `test_publisher_imports_clean` | AST scan: no forbidden network imports beyond the push-vendor wrapper. |
| `test_publisher_source_rejects_required_phrase` | Source-text scan rejects `required_phrase`, `operator_go_phrase`, `OPERATOR-GO`, `GO Batch`, `GO A18`, `GO enable`. |
| `test_publisher_source_rejects_credentials` | Source-text scan rejects `api_key`, `apiKey`, `secret`, `token`, `bearer`, `password`. |
| `test_body_length_capped` | All canonical body shapes produce ≤ 80 chars. |
| `test_body_ascii_printable_only` | All canonical body shapes match `^[ -~]+$`. |
| `test_body_builder_closed_vocab` | Each invalid input (unknown `agent_role`, etc.) is rejected. |
| `test_deep_link_validation` | Service-worker handler accepts only the 5 closed-prefix forms; everything else routes to `/safety`. |
| `test_deep_link_rejects_javascript_scheme` | `javascript:`, `data:`, `<script>` are rejected. |
| `test_no_background_sync_from_notification` | Service-worker handler does not register a sync job. |

---

## §10 Operational discipline

### 10.1 What changes do NOT require a new B2.0e review

- Adding a new closed-vocab `risk_band` value (e.g. `critical`),
  provided the body builder remains within the 80-char cap.
- Adding a new `invariant_key` to the alert vocabulary.
- Translating canonical body shapes to additional locales,
  provided each translation passes the same length + ASCII pin
  (or its locale-appropriate equivalent).

### 10.2 What changes DO require a new B2.0e review

- Adding a new notification type beyond the 3 canonical shapes
  in §3.
- Increasing the body length cap above 80 chars.
- Introducing rich-text or markdown rendering.
- Adding a vendor template variable.
- Adding any field other than `title`, `body`, `data.deep_link`,
  and `data.notification_id` to the vendor payload.

---

## §11 Why this doctrine is load-bearing

ADR-015 governs agent execution authority. Operator-go phrases
are the explicit, signed-in-writing acts that grant new
capabilities. If a push-notification body included the phrase,
anyone with momentary access to a locked-screen preview could
read and reuse it — silently subverting the out-of-band assumption
that backs every gated action.

The doctrine in this document ensures that even if a future
maintainer is tempted to "include the phrase so the operator
doesn't have to look it up", the lint hook + pin tests reject the
change at build time. The phrase only ever exists inside the
authenticated PWA app shell, after the operator has presented a
valid session cookie.

---

## §12 What this doctrine is NOT

- Not an authorisation to ship a push publisher now. B2.0 does not
  ship code.
- Not a contract for any existing notification surface (the
  doctrine governs AAC notifications only).
- Not a substitute for the no-mutation doctrine — they complement
  each other. A push notification that mutated server state on
  tap would violate both doctrines.
- Not a request to disable push vendor analytics that operate on
  delivery metadata only (delivery confirmations, opt-outs).
- Not a PWA component contract — that lives in [`agent_activity_center_design.md`](agent_activity_center_design.md) §6.
- Not an API contract — see [`agent_activity_center_api_contract.md`](agent_activity_center_api_contract.md).
- Not a no-mutation specification — see [`agent_activity_center_no_mutation_doctrine.md`](agent_activity_center_no_mutation_doctrine.md).
