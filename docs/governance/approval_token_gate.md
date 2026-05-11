# Approval Token Gate — N4a (pure mint/verify; no live wiring)

> **Status:** Implemented (pure callable; **no live wiring**).
>
> **Module:** [`reporting/approval_token_gate.py`](../../reporting/approval_token_gate.py)
>
> **Authority:** development-governance read-only.
> N4a is a **callable surface** that exposes the closed cryptographic
> contract. It does not read any environment variable, register
> any Flask blueprint, or call any HTTP / GitHub / push surface.
> The future operator-action-only **N4b** slice will wire this
> gate into a live endpoint behind explicit operator authorisation.
> Level 6 stays permanently disabled per ADR-015 §Doctrine 1.
> **No approval can happen from a notification click alone.**

---

## 1. Purpose

N4a defines the **closed cryptographic contract** the future mobile
approval flow will use:

- HMAC-SHA256 signature over a closed-schema JSON claims envelope;
- per-token random nonce + caller-managed replay-protected
  seen-set;
- bindings: `(event_id, pr_number, pr_head_sha, evidence_hash,
  release_tag)` — drift in any binding invalidates the token;
- short default lifetime: `DEFAULT_TTL_SECONDS = 900` (15 min);
- hard cap: `MAX_TTL_SECONDS = 900`;
- minimum secret length: `MIN_SECRET_LENGTH_BYTES = 32` (256 bits);
- kid-rotated secret lookup supplied by the caller — never read
  from env by N4a itself.

Today N4a is consulted by no one in production. It is a pure
callable that exposes the contract. Tests supply a synthetic
32-byte secret via `secrets.token_bytes(32)`. Production wiring
(N4b) is **operator-action only**.

---

## 2. Hard constraints

N4a, in this PR and at runtime, must not:

- read `ADE_APPROVAL_TOKEN_HMAC_SECRET` (or any other env var) —
  the literal name does not appear in the module's executable code;
- register a Flask blueprint or wire into `dashboard/dashboard.py`;
- execute approve / reject / merge / deploy anything;
- send a real push (N2b-3b territory);
- call any HTTP / GitHub / push surface;
- persist tokens to a server-side store (the seen-nonce set is
  caller-managed; N4a does not own state);
- mutate any upstream artefact;
- edit canonical roadmap status fields;
- mark any roadmap phase complete;
- enable Step 5.1 or Step 5.2;
- flip `step5_implementation_allowed`;
- change `STEP5_ENABLED_SUBSTAGE`;
- change QRE behaviour;
- mutate research artifacts;
- touch live / paper / shadow / risk / broker / execution paths;
- edit `.claude/**`;
- store secrets in repo.

N4a ships its own AST-level forbidden-import scan and
source-text scan to enforce the relevant bullets.

---

## 3. Closed vocabularies

Pinned in [`reporting/approval_token_gate.py`](../../reporting/approval_token_gate.py):

### `token_intent` (2 values)

| Value                      | Meaning                                                                                          |
| -------------------------- | ------------------------------------------------------------------------------------------------ |
| `mobile_approval_dispatch` | the operator presents this token to *initiate* a merge dispatch via the future N5 surface       |
| `mobile_review_dispatch`   | the operator presents this token to *initiate* a review dispatch (read-only inspection action)   |

**Critical design choice:** neither value uses `approve` / `merge`
/ `deploy` as a verb. The intent describes the *purpose* for which
the token may be presented, not the action a caller can take.
Pinned by `test_token_intents_avoid_decision_verb`.

### `verify_outcome` (8 values)

```
ok  expired  signature_invalid  binding_mismatch
intent_unknown  malformed_envelope  replay_detected  unknown_kid
```

### Claims schema (11 keys, closed and exact)

```
schema_version  intent  event_id
pr_number  pr_head_sha  evidence_hash  release_tag
kid  nonce
issued_at_utc  expires_at_utc
```

### Bindings (verified at `verify_token` time)

```
event_id  pr_number  pr_head_sha  evidence_hash  release_tag
```

Drift in **any** of these between mint time and verify time yields
`binding_mismatch` and the operator must mint a fresh token.

---

## 4. Mint / verify contract

### `mint_token(*, intent, event_id, pr_number, pr_head_sha, evidence_hash, release_tag, kid, secret, ttl_seconds=900, now=None) -> str`

- All keyword-only arguments — no positional ambiguity.
- `secret` is `bytes`, supplied by the caller, validated to be
  ≥ 32 bytes. **Never read from env by N4a.**
- `ttl_seconds` ≤ `MAX_TTL_SECONDS = 900`; `mint_token` raises
  `ValueError` on larger.
- Returns a string of the form
  `<base64url(claims_json)>.<base64url(signature)>`.

### `verify_token(token, *, expected_event_id, expected_pr_number, expected_pr_head_sha, expected_evidence_hash, expected_release_tag, secrets_by_kid, seen_nonces=None, now=None) -> VerifyResult`

- All keyword-only arguments.
- `secrets_by_kid` is `dict[str, bytes]` — the caller's kid-rotation
  lookup. N4a uses constant-time comparison via `hmac.compare_digest`.
- `seen_nonces` is `set[str] | None` — caller-managed replay
  protection. N4a does **not** mutate the set; the caller decides
  whether to record a verified nonce.
- Returns a closed-vocab `VerifyResult(outcome, claims, reason)`.

---

## 5. Discipline invariants (in module + pinned by tests)

```
reads_environment_variable           = false   (AST + source-text pinned)
registers_flask_blueprint            = false
executes_approve_or_reject           = false
merges_or_deploys                    = false
sends_real_push                      = false
calls_http_or_github                 = false
persists_seen_nonces                 = false   (caller-managed only)
operator_promotion_required          = true
step5_implementation_allowed         = false
step5_enabled_substage               = "none"
diagnostics_do_not_trade             = true
no_approval_from_notification_click_alone = true
```

---

## 6. CLI

There is **no CLI** in N4a. The module is a Python callable. Tests
exercise it directly; future N4b wiring will pass the env-supplied
secret bytes via the kid-rotation map.

---

## 7. Authority chain summary

| Capability                                              | Today (post-A23) | After N4a                                | After N4b (future, operator-authored) | After N5 (future, operator-authored) |
| ------------------------------------------------------- | ---------------- | ---------------------------------------- | --------------------------------------- | ------------------------------------- |
| Mint approval token                                      | does not exist   | yes — `mint_token(...)` callable (no env wiring) | yes — operator-env-only secret rotation | unchanged                          |
| Verify approval token                                    | does not exist   | yes — `verify_token(...)` callable        | yes — operator-env-only                  | unchanged                             |
| Execute approve / reject                                 | does not exist   | does not exist                           | does not exist                          | yes — bounded merge adapter, token-gated |
| Autonomous merge / deploy                                | forbidden, Level 6 | unchanged — Level 6 permanently disabled | unchanged                               | unchanged                             |
| Read env secret                                          | does not exist   | **does not exist in N4a**                | yes — N4b reads `ADE_APPROVAL_TOKEN_HMAC_SECRET` from VPS env | unchanged                             |

N4a grants ADE **zero** new authority. It is a cryptographic
*surface* the operator can inspect before authorising the live
wiring.

---

## 8. Test coverage

Pinned in [`tests/unit/test_approval_token_gate.py`](../../tests/unit/test_approval_token_gate.py):

- closed `TOKEN_INTENTS` (2), `VERIFY_OUTCOMES` (8),
  `TOKEN_CLAIM_KEYS` (11) pinned exactly;
- `test_token_intents_avoid_decision_verb` — no intent name
  contains `approve` / `reject` / `merge` / `deploy`;
- mint → verify round-trip on every binding combination;
- every `verify_outcome` row reproduces (expired,
  signature_invalid, binding_mismatch per each of the 5 bindings,
  intent_unknown, malformed_envelope, replay_detected, unknown_kid);
- `MAX_TTL_SECONDS = 900` enforced;
- `MIN_SECRET_LENGTH_BYTES = 32` enforced;
- secret-shorter-than-min raises ValueError;
- non-bytes secret raises TypeError;
- replay-set adds a nonce → verify with same nonce →
  `replay_detected`;
- atomic write refused — N4a has no write path at all (no
  `_atomic_write_json` exists);
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `subprocess`, `socket`, `urllib`,
  `requests`, `httpx`, `aiohttp`, `gh`, `git`;
- source-text scan: no `os.environ` / `os.getenv` reference;
- source-text scan: no `ADE_APPROVAL_TOKEN_HMAC_SECRET` literal;
- source-text scan: no Flask blueprint registration;
- importing the module does not flip Step 5 invariants;
- this doc states "no approval from notification click alone" and
  "Level 6 stays permanently disabled".

---

## 9. What N4a does NOT do

- N4a never reads `ADE_APPROVAL_TOKEN_HMAC_SECRET` or any other env.
- N4a never registers a Flask blueprint.
- N4a never executes approve / reject / merge / deploy.
- N4a never calls HTTP / GitHub / push.
- N4a never persists state.
- N4a never writes to `dashboard/dashboard.py` or `frontend/**`.
- N4a never writes to any seed file.
- N4a never edits canonical roadmap status fields.
- N4a does not flip `step5_implementation_allowed`.
- N4a does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- N4b live wiring (env secret, blueprint, audit hooks) remains
  unimplemented and operator-action-only.
- N5 merge execution / deploy adapter remain unimplemented.
- Level 6 stays permanently disabled.
