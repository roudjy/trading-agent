# N4b — Runtime Approval-Token Gate Activation (Operator Runbook)

> **Status:** documentation + invariant pin-tests only. The repo-side
> wiring (`from dashboard.api_approval_token_gate import
> register_approval_token_gate_routes` and the matching
> `register_approval_token_gate_routes(app)` call in
> `dashboard/dashboard.py`) is already merged. This runbook describes
> the **operator-only VPS step** needed to actually activate the
> runtime gate by exporting `ADE_APPROVAL_TOKEN_HMAC_SECRET` on the
> Hetzner VPS.
>
> **Step 5 invariants preserved:**
> `step5_implementation_allowed = false`,
> `STEP5_ENABLED_SUBSTAGE = "none"`,
> Level 6 permanently disabled.
> **This activation grants ADE zero new autonomous authority.**

---

## 1. What this runbook activates

After running the steps in this document, the three N4b endpoints
become *operationally* useful (mint produces a real token; verify
returns `outcome: "ok"` on a valid mint):

```
GET  /api/agent-control/approval-token/status
POST /api/agent-control/approval-token/mint
POST /api/agent-control/approval-token/verify
```

Each route is **session-protected** (requires
`session["operator_authenticated"] is True`, which is set by the
existing `/api/session/login` flow). Without an authenticated
operator session every route returns HTTP 401
`operator_session_required`.

---

## 2. What this runbook does NOT enable

This activation is **claim verification only**. It does *not*:

- merge any PR (no `gh pr merge` is invoked anywhere);
- approve / reject anything in the approval inbox;
- deploy anything;
- flip any roadmap-progress field;
- write to `seed.jsonl` or `generated_seed.jsonl`;
- enable Step 5.1 or Step 5.2;
- introduce Level 6;
- mint or push any non-test data to external systems;
- expose `ADE_APPROVAL_TOKEN_HMAC_SECRET` in any response body,
  audit log, or stdout/stderr line.

The verify endpoint records the nonce of a successfully verified
token to a bounded on-disk replay-protection store
(`state/approval_token_seen_nonces.jsonl`, gitignored, atomic
rewrite, bounded to `MAX_SEEN_NONCES = 1024` rows). The store
contains only the 16-byte hex nonce per row — **never** the secret,
**never** the claims body. Replay of a verified token returns
`outcome: "replay_detected"`.

Acting on a verified token (i.e., actually merging the bound PR) is
**N5 territory** and is not implemented in this stage.

---

## 3. Hard guarantees that must stay true after activation

| Invariant | Why it matters |
|---|---|
| `step5_implementation_allowed` remains `false` | Step 5 cap is the autonomy ceiling; N4b activation must not flip it. |
| `STEP5_ENABLED_SUBSTAGE` remains `"none"` | Same. |
| Level 6 stays permanently disabled | ADR-015 §Doctrine 1. |
| No autonomous merge / deploy / approve / reject | Verify ≠ action; N5 is unimplemented. |
| `ADE_APPROVAL_TOKEN_HMAC_SECRET` only on VPS env | Never in repo, never in compose, never echoed by any endpoint. |
| Seen-nonce store under `state/` only | `state/` is gitignored (line 25 of `.gitignore`). |
| Mint/verify refuses without env | HTTP 503 `configuration_missing` until activated. |
| Operator session required | HTTP 401 `operator_session_required` without it. |
| Body cap 4 KiB | HTTP 413 `payload_too_large` for oversized requests. |
| No approval from a notification click alone | The PWA re-auth flow stays the only path to a session. |

These invariants are pinned by the existing unit tests
(`tests/unit/test_api_approval_token_gate.py`,
`tests/unit/test_approval_token_runtime.py`,
`tests/unit/test_approval_token_gate.py`) and by this runbook's
pin-test (`tests/unit/test_n4b_runtime_activation_runbook.py`).

---

## 4. Phase B — operator VPS activation steps

> **All steps run on the VPS only.** None of them changes anything
> in the repo. None of them commits a secret. The operator runs each
> step manually and inspects the output before proceeding to the
> next.

### 4.1 SSH to the VPS

```sh
ssh root@23.88.110.92
cd /root/trading-agent
```

### 4.2 Generate the HMAC secret (once)

```sh
openssl rand -hex 32
```

This prints a 64-character hex string (= 32 bytes when decoded).
**Do not paste it into the repo, into a commit message, into Slack,
or into any file that is tracked by git.** Copy it into the
operator's existing env mechanism (e.g. a private file outside
`/root/trading-agent`, or the operator's `~/.bashrc`).

The runtime accepts the secret as **hex**, **base64url**, or **raw
≥32-byte string**. Hex is recommended because `openssl rand -hex 32`
is the canonical generator.

### 4.3 Export the secret in the dashboard container's environment

The exact mechanism depends on how the operator currently injects
env vars into the dashboard container. Two common patterns:

**(a) Per-operator env file passed to `docker compose`** — set
`ADE_APPROVAL_TOKEN_HMAC_SECRET=<the hex string>` in the env file
already used by the dashboard service. The file must live outside
the repo (or be gitignored).

**(b) Explicit `--env` on `docker compose up`** — pass the variable
directly when recreating the container (see 4.4).

Whichever path is chosen, **never** commit the value, **never**
write it to `docker-compose.yml`, `docker-compose.override.yml`,
`config/*`, or any other tracked file.

### 4.4 Recreate the dashboard so the env propagates

```sh
docker compose up -d --force-recreate dashboard
```

> The exact compose service name may be `agent` or `dashboard`
> depending on the operator's compose file. Use whichever service
> hosts `dashboard/dashboard.py`.

### 4.5 Authenticate the operator session

Log into the PWA at `https://23.88.110.92:8050/login` (or the
operator's chosen URL) so the cookie jar holds a valid
`operator_authenticated` session. If the operator prefers `curl`,
post to `/api/session/login` first with the standard credentials
and store the session cookie in `-b/-c` files.

### 4.6 Confirm `is_configured: true`

```sh
curl -s -b cookies.txt https://23.88.110.92:8050/api/agent-control/approval-token/status | jq
```

Expected envelope:

```json
{
  "kind": "approval_token_status",
  "status": "ok",
  "is_configured": true,
  "current_kid": "k1",
  "step5_implementation_allowed": false,
  "step5_enabled_substage": "none"
}
```

If `"is_configured": false` is returned, the env did not propagate
to the dashboard container — re-check step 4.3 / 4.4.

### 4.7 Mint a smoke-test token

```sh
curl -s -b cookies.txt \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "intent": "mobile_approval_dispatch",
    "event_id": "evt_smoke",
    "evidence_hash": "smoke"
  }' \
  https://23.88.110.92:8050/api/agent-control/approval-token/mint | jq
```

Expected: `"status": "ok"`, a `token` field containing the
`<claims>.<signature>` string, `kid: "k1"`, the same `event_id`,
and bounded `issued_at_utc` / `expires_at_utc` (TTL = 15 minutes by
default).

Capture the returned `token` value for the verify step.

### 4.8 Verify the token (claim verification only)

```sh
curl -s -b cookies.txt \
  -X POST -H "Content-Type: application/json" \
  -d '{
    "token": "<paste minted token here>",
    "expected_event_id": "evt_smoke",
    "expected_evidence_hash": "smoke"
  }' \
  https://23.88.110.92:8050/api/agent-control/approval-token/verify | jq
```

Expected: `{ "status": "ok", "outcome": "ok", "reason": "verified" }`.

This response confirms only that the signature is valid and the
bindings match. **No underlying action is taken.**

### 4.9 Replay test — must reject

Run the **same** verify call a second time (same token, same
bindings). Expected: `{ "status": "rejected", "outcome":
"replay_detected", ... }`. The nonce is now recorded in
`state/approval_token_seen_nonces.jsonl`.

### 4.10 Binding-mismatch test — must reject

Mint a fresh token with `event_id = "evt_smoke_2"`, then verify with
`expected_event_id = "evt_smoke_OTHER"` (anything different).
Expected: `"outcome": "binding_mismatch"`. Drift in any binding
(event_id, pr_number, pr_head_sha, evidence_hash, release_tag)
invalidates the token.

### 4.11 Audit checklist after activation

Run on the VPS:

- [ ] `cat state/approval_token_seen_nonces.jsonl` shows JSONL lines
      shaped `{"nonce":"<16-byte hex>"}` — no secret, no claims body.
- [ ] `docker compose logs dashboard --since 10m | grep -iE
      "(ADE_APPROVAL_TOKEN_HMAC_SECRET|BEGIN PRIVATE KEY|p256dh)"`
      returns **no** matches.
- [ ] `git status` in `/root/trading-agent` is **clean** (no
      tracked file changed by the activation).
- [ ] No new row in the mobile-approval inbox was created by the
      smoke test (verify is claim-only).
- [ ] No `gh pr ...` command was issued by the dashboard process.
- [ ] No write under `seed.jsonl` / `generated_seed.jsonl` /
      `delegation_seed.jsonl`.

If any of the above fails, stop and roll back (§5).

---

## 5. Rollback

The runtime gate is fully reversible by unsetting the env and
restarting the container:

```sh
# In the operator's env mechanism, remove the ADE_APPROVAL_TOKEN_HMAC_SECRET line.
docker compose up -d --force-recreate dashboard

# Optional: clear the seen-nonce store so a future activation starts clean.
rm -f /root/trading-agent/state/approval_token_seen_nonces.jsonl
```

After rollback the status endpoint reports `"is_configured": false`
and mint/verify return HTTP 503 `configuration_missing` again. No
codepath in the dashboard is broken by the rollback — N4b is purely
env-gated.

---

## 6. Secret rotation

To rotate the secret, repeat steps 4.2 / 4.3 / 4.4 with a new value.
The active key id stays `k1` for the smallest safe slice; rotating
to a new `kid` (`k2`, …) is a deliberate **code change** that
extends `secrets_by_kid()` in `reporting/approval_token_runtime.py`
and adds a pinned test. The operator must not edit kid values in
production env files alone.

Tokens minted under the old secret remain *invalid* the moment the
new secret takes effect — `verify_outcome` becomes
`signature_invalid` for them. The operator must coordinate any
rotation with whoever holds outstanding tokens (today: nobody —
there is no live caller of mint outside this runbook).

---

## 7. What this activation explicitly does NOT promote

- It does **not** turn on autonomous merging. Verify ≠ merge.
- It does **not** turn on autonomous approval. No row in the
  mobile-approval inbox is flipped by verify.
- It does **not** flip `step5_implementation_allowed` from `false`.
- It does **not** change `STEP5_ENABLED_SUBSTAGE` from `"none"`.
- It does **not** raise the autonomy ladder ceiling.
- It does **not** introduce Level 6 (permanently disabled).
- It does **not** add any UI for mint/verify (N4c future slice).
- It does **not** add a merge button (N5b future slice — plan-only
  until explicitly authorised).

---

## 8. Authority chain after activation

| Capability | Before activation | After activation |
|---|---|---|
| Status endpoint reachable for authed session | yes (returns `is_configured: false`) | yes (returns `is_configured: true`) |
| Mint endpoint | 503 `configuration_missing` | 200 with a real token (auth + bindings required) |
| Verify endpoint | 503 `configuration_missing` | 200 / 400 with closed-vocab outcome |
| Autonomous approve / merge / deploy | does not exist | does not exist |
| Operator-paced approve / merge / deploy | does not exist | does not exist (N5b unimplemented) |
| Read env secret | only `approval_token_runtime` module | unchanged |
| Touch seed files | forbidden | unchanged (forbidden) |
| Touch dashboard.py / .claude / .gitleaks.toml | forbidden | unchanged (forbidden) |
| Flip Step 5 / Level 6 | forbidden | unchanged (forbidden) |

---

## 9. Related runbooks and tests

- `tests/unit/test_api_approval_token_gate.py` — pins the 3 routes,
  401 / 503 / 413 envelopes, mint+verify roundtrip with synthetic
  secret, replay rejection, binding-mismatch rejection, no secret
  leakage.
- `tests/unit/test_approval_token_runtime.py` — pins the env-driven
  runtime: only this module reads the secret, bounded seen-nonce
  store, atomic rewrite.
- `tests/unit/test_approval_token_gate.py` — pins the pure N4a
  callable: closed claim schema, closed outcomes, no env read.
- `tests/unit/test_n4b_runtime_activation_runbook.py` — pins **this
  runbook** against the canonical phrases that must never drift.
- `docs/governance/approval_token_gate.md` — N4a doctrine.
- `docs/adr/ADR-015-claude-agent-governance.md` — Level 6 doctrine.

---

## 10. Stop conditions for the operator

Halt the activation and notify the on-call human owner if any of
the following happens during steps 4.6–4.10:

- `is_configured: true` but mint returns `configuration_missing`
  (env-decode failure → secret is shorter than 32 bytes or
  malformed);
- mint returns a token but verify returns `signature_invalid` on
  the same response (clock skew / process restart between mint and
  verify);
- the seen-nonce JSONL file appears under any path other than
  `state/approval_token_seen_nonces.jsonl`;
- any response body contains the string
  `ADE_APPROVAL_TOKEN_HMAC_SECRET` or any PEM-style header
  (`BEGIN PRIVATE KEY`, `BEGIN EC PRIVATE KEY`, etc.);
- a new row appears in the mobile-approval inbox after verify;
- the dashboard container restarts repeatedly or crashes after
  setting the env.

In every halt case, run §5 (rollback) before debugging.
