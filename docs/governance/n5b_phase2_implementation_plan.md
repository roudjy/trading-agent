# N5b Phase 2 — Token-Bound Dry-Run Endpoint: Implementation Plan (Plan-only)

> **Status:** Plan only. **Not implemented.**
>
> This document decomposes N5b Phase 2 (the token-bound dry-run
> endpoint described in
> [`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
> §4.2 and §10 line "Phase 2 — Token-bound dry-run") into
> ordered, auditable sub-units. It introduces **no runtime code,
> no new module, no new route, no token-verification call, no
> network call, no audit-artefact write, and no governance
> escalation**.
>
> The plan-only status of this document is binding: a future PR
> that introduces runtime code under any sub-unit name (B2.8b /
> B2.8c / B2.8d / B2.8e) requires its own explicit operator-go
> phrase per §3 and its own §4 precondition acknowledgement.

---

## 1. Scope

### 1.1 What this plan covers

* The closed contracts (module path, route URL, request schema,
  response statuses, audit artefact paths, sub-unit
  decomposition) that any future N5b Phase 2 implementation must
  satisfy.
* The hard preconditions that must be true before any runtime
  code-bearing sub-unit lands.
* The pin-test set in
  [`tests/unit/test_n5b_phase2_implementation_plan.py`](../../tests/unit/test_n5b_phase2_implementation_plan.py)
  that locks the contracts in this document.

### 1.2 What this plan does NOT cover

* It does **not** advance N5b Phase 2 implementation.
* It does **not** activate N4b Phase B on the VPS (operator-only
  step per
  [`n4b_runtime_activation.md`](n4b_runtime_activation.md)).
* It does **not** ship the N4c or any equivalent token mint/verify UI.
* It does **not** modify, weaken, or remove the existing N5b
  plan-only pin tests in
  [`tests/unit/test_n5b_merge_execution_plan.py`](../../tests/unit/test_n5b_merge_execution_plan.py).
* It does **not** introduce the literal future-route URL or the
  forbidden shell-out tokens into any runtime source file under
  `dashboard/`, `reporting/`, `scripts/`, or `.github/workflows/`.

### 1.3 Parent doc

The canonical plan for the full N5b execution surface (Phases
0/1/2/3/4, §3 preconditions, §6 audit artefacts, §7 stop
conditions, §8 security boundaries, §10 rollout, §11 permanent
denials) is
[`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md).
This sub-plan extends that doc; every contract here must be
consistent with the parent. Conflicts resolve in favour of the
parent.

---

## 2. Closed contracts for the future Phase 2 implementation

The strings, paths, and field names enumerated in this section
are **closed**. The future implementation must match them
byte-identical; the pin tests in
`tests/unit/test_n5b_phase2_implementation_plan.py` enforce that.

### 2.1 Module path

The future Phase 2 module is at exactly:

```
dashboard/api_merge_execution_dry_run.py
```

No other module path is permitted. The companion projector (the
artefact writer) lives at exactly:

```
reporting/n5b_merge_execution_dry_run.py
```

No other reporting-side module path is permitted.

### 2.2 Route

Exactly one POST route:

```
POST /api/agent-control/merge-execution/dry-run
```

* Method: POST only. GET / PUT / PATCH / DELETE return 405.
* Auth: session-protected + N4b token-gated.
* Idempotency: NOT idempotent — each request either succeeds
  (one dry-run artefact written) or fails with a precise
  stop-condition envelope. Operator re-mints to retry.

### 2.3 Request body schema (closed, JSON)

```
{
  "pr_number":     <int>,
  "pr_head_sha":   "<string>",
  "token":         "<string>",
  "intent":        "mobile_approval_dispatch",
  "evidence_hash": "<string>"
}
```

* `pr_number` — must equal the token's `pr_number` claim.
* `pr_head_sha` — must equal the token's `pr_head_sha` claim
  AND the current GitHub head SHA at evaluation time.
* `token` — the N4b approval token; verified via
  `reporting.approval_token_runtime.verify_runtime(...)`.
* `intent` — must equal the literal `mobile_approval_dispatch`.
* `evidence_hash` — must equal the token's `evidence_hash` claim.

All five fields are required. Missing or unrecognised fields
produce a closed-envelope rejection with `stop_condition` from
§7 of the parent doc.

### 2.4 Response statuses (closed vocabulary)

The response envelope's `status` field is one of:

| status | Meaning |
|---|---|
| `ok` | every precondition satisfied; `would_proceed = true`. |
| `rejected` | at least one precondition failed; `stop_condition` populated from §7 of the parent doc. |
| `configuration_missing` | N4b not activated on VPS (`is_configured()` returns False) or runtime not ready. No `stop_condition`. |
| `not_yet_implemented` | interim status returned by B2.8b sub-unit until the full precondition walker lands in B2.8c / B2.8d. |

No other status value is permitted.

### 2.5 Response envelope schema (closed, JSON)

```
{
  "status":                       "<closed-vocab string>",
  "stop_condition":               "<closed-vocab string>" | null,
  "preconditions_evaluated":      <int>,
  "preconditions_passed":         <int>,
  "would_proceed":                <bool>,
  "pr_number":                    <int>,
  "pr_head_sha":                  "<string>",
  "schema_version":               1,
  "module_version":               "<string>",
  "step5_implementation_allowed": false,
  "step5_enabled_substage":       "none",
  "level6_enabled":               false,
  "dry_run_only":                 true,
  "live_merge_implemented":       false,
  "deploy_coupled":               false,
  "generated_at_utc":             "<ISO 8601 string>"
}
```

The six invariant fields (`step5_implementation_allowed`,
`step5_enabled_substage`, `level6_enabled`, `dry_run_only`,
`live_merge_implemented`, `deploy_coupled`) match the existing
[`api_merge_preflight.py`](../../dashboard/api_merge_preflight.py)
envelope contract. The consumer always sees them, so the
operator-facing surface never has to infer Step 5 / Level 6 /
deploy-coupling state.

### 2.6 Audit artefact paths (closed, under `logs/n5b_merge_execution/`)

All artefact writes are restricted by a write-prefix sentinel to
the `logs/n5b_merge_execution/` subtree. The future
implementation writes:

| Artefact kind | Path | Writer |
|---|---|---|
| Preflight | `logs/n5b_merge_execution/preflight/latest.json` | every dry-run invocation, before the token verify call |
| Dry-run (latest) | `logs/n5b_merge_execution/dry_run/latest.json` | every dry-run invocation that produced a decision (`ok` or `rejected`) |
| Dry-run (history) | `logs/n5b_merge_execution/dry_run/history.jsonl` | append-only, capped row count |
| Failure | `logs/n5b_merge_execution/failure/<cycle_id>.json` | when any §7 stop condition triggers, with the redacted stop-reason |

* Atomic write via tmp + `os.replace` (the existing N5a
  projector pattern).
* Closed schema matching §6 of the parent doc (`n5b_preflight`,
  `n5b_dry_run`, `n5b_failure`).
* Every artefact is run through
  `reporting.agent_audit_summary.assert_no_secrets()` before write.
* No raw token, no HMAC secret, no PEM block, no VPS IP, no
  bearer header value, no PAT, no `ghp_` prefix.

The future writer module's allowlist forbids every write outside
the `logs/n5b_merge_execution/` subtree.

---

## 3. Sub-unit decomposition (exact)

N5b Phase 2 is delivered as the ordered sub-units below. Each
sub-unit:

* is a separate PR;
* requires its own explicit operator-go phrase;
* inherits every closed contract from §2 of this document;
* may not advance the §4 hard preconditions on its own.

| Unit | Scope | Mutates production | Operator-go status |
|---|---|---|---|
| **B2.8a** | this plan-doc + pin tests in `tests/unit/test_n5b_phase2_implementation_plan.py` + small cross-reference section in the parent doc. No runtime code. | No | **given** for B2.8a only |
| **B2.8b** | module skeleton UNWIRED — `dashboard/api_merge_execution_dry_run.py` exists; the POST route is registered in the blueprint but the blueprint is NOT yet registered in `dashboard/dashboard.py`; every request returns `status = not_yet_implemented`. Pin-tests assert no token verification, no GitHub call, no audit write yet. Existing N5b plan-only pin tests are narrowed (not weakened) so they allow exactly this one module path. | No | **NOT given** by this PR |
| **B2.8c** | token verification wired (preconditions 1–7 of the parent doc §3: N4b activated, operator-UI presence, token bound to pr_number / pr_head_sha / evidence_hash / intent / nonce). Audit preflight artefact written. `ok` / `rejected` returned based on those seven preconditions only; preconditions 8–17 still emit `not_yet_implemented`. | No | **NOT given** by this PR |
| **B2.8d** | GitHub-API-dependent preconditions 8–17 (N5a recommendation, `mergeStateStatus`, required checks, head-SHA advancement, base ref, freshness, inbox criticals, protected-path scan, Step-5 / Level-6 bypass scan). Mocked GitHub API only — no live GitHub call. Test fixtures cover every canonical `mergeStateStatus` value and every canonical check conclusion. | No | **NOT given** by this PR |
| **B2.8e** | integration tests against the mocked GitHub fixture + governance-status update + operator-applied wiring patch for `dashboard/dashboard.py` + parent-doc §5 / §10 update marking Phase 2 as Implemented + retirement of the now-redundant "no merge execution route exists" pin (replaced by a "exactly one merge execution route exists, and it is the dry-run route" pin). | No (still dry-run only; no PR is mutated) | **NOT given** by this PR |

Sub-units B2.8b through B2.8e MUST land in this order. Skipping
order, splitting a unit further, or bundling two units into one
PR requires a new explicit operator-go phrase that updates this
table.

---

## 4. Hard preconditions before any runtime sub-unit lands

Before B2.8b — or any subsequent code-bearing sub-unit — lands,
**ALL three** of the following must be true and explicitly
acknowledged by the operator in the PR description for that
sub-unit. The operator is the sole authority on whether each
precondition is met.

### 4.1 Phase 1 observed-clean period elapsed

The N5b Phase 1 preflight projector
(`reporting/development_merge_preflight.py` and the
`api_merge_preflight` blueprint) has been merged + deployed +
observed clean for a bounded period per §10 line "Phase 1 must
be merged + observed clean for a bounded period before
promotion" of the parent doc.

The operator declares the period elapsed; this plan does not
encode a numeric duration.

### 4.2 N4b Phase B activated on VPS

`ADE_APPROVAL_TOKEN_HMAC_SECRET` is exported in the VPS runtime
environment per
[`n4b_runtime_activation.md`](n4b_runtime_activation.md), and
`reporting.approval_token_runtime.is_configured()` returns True
at runtime against that secret.

The secret is operator-only. This plan does not advance N4b
Phase B activation; B2.8a remains read-only.

### 4.3 N4c or equivalent token mint/verify UI exists

The operator can mint and verify an N4b approval token in the
PWA (or an equivalent operator-facing surface) per §3 row 2 of
the parent doc — that is, **without a curl-only mint flow**.

The mint/verify interaction must have a documented, auditable
surface so the dry-run endpoint never receives a token whose
mint context is opaque.

### 4.4 Precondition summary

| Precondition | Owner | Status (as of B2.8a) |
|---|---|---|
| Phase 1 observed-clean period elapsed | operator | not declared |
| N4b Phase B activated on VPS | operator + VPS env | not activated |
| N4c / mint/verify UI exists | operator + UI ship | not implemented |

None of these are advanced by B2.8a. A future sub-unit that
attempts to land runtime code without all three preconditions
explicitly acknowledged in its PR description fails the §3 + §4
contracts and must be rejected by the operator.

---

## 5. Hard denials (re-iterated; binding on every sub-unit)

The future implementation modules introduced by B2.8b through
B2.8e MUST NOT:

* invoke a GitHub command-line tool shell-out (the parent doc's
  §7 / §8 enforcement applies);
* invoke a version-control command-line tool shell-out from any
  module touched by these sub-units;
* call `subprocess.run`, `subprocess.Popen`, `subprocess.call`,
  `subprocess.check_call`, `subprocess.check_output`,
  `os.system`, `os.popen`, or any other shell-spawning primitive;
* open a network socket directly (no `socket`, no `urllib`, no
  `requests`, no `httpx`, no `aiohttp` import outside the
  vetted `reporting.approval_token_runtime` import surface);
* read any environment variable other than the ones already
  read by `reporting.approval_token_runtime` (i.e. only
  `ADE_APPROVAL_TOKEN_HMAC_SECRET` and its kid-mapping siblings);
* write any path outside the `logs/n5b_merge_execution/` subtree;
* touch `.claude/**`, `.github/**`, `live/**`, `paper/**`,
  `shadow/**`, `risk/**`, `broker/**`, `execution/**`,
  `research/**`, `seed.jsonl`, `generated_seed.jsonl`,
  `delegation_seed.jsonl`, or any other no-touch path enumerated
  in [`no_touch_paths.md`](no_touch_paths.md);
* change `step5_implementation_allowed` away from `False` or
  `STEP5_ENABLED_SUBSTAGE` away from `"none"`;
* introduce or reference any Level 6 capability marker (Level 6
  is permanently disabled per ADR-015 §Doctrine 1);
* bypass branch protection — no `--admin` flag in any
  hypothetical merge call, no `admin:org` / `admin:repo_hook`
  scope on any token, no merge call that requires either;
* trigger the deploy workflow — the merge adapter must
  terminate before the deploy workflow triggers and must never
  invoke the deploy workflow directly;
* mutate any pull request — this is dry-run only; live
  execution is N5b Phase 3+ and remains permanently denied
  without a separate explicit operator-go;
* mint a token — the mint flow belongs to N4b / N4c and must
  not be duplicated in the merge-execution surface.

The pin tests in B2.8b through B2.8e must reproduce each denial
deterministically. A pin-test that silently weakens any denial
above fails the contract.

---

## 6. Per-sub-unit test requirements

### 6.1 B2.8b — skeleton UNWIRED

* The module exists at exactly `dashboard/api_merge_execution_dry_run.py`.
* The blueprint registers exactly one route (the POST dry-run route).
* GET / PUT / PATCH / DELETE on the same URL return 405.
* The blueprint is NOT yet registered in `dashboard/dashboard.py`.
* AST scan: no `subprocess`, `socket`, `urllib`, `requests`,
  `httpx`, `aiohttp`, `os.system`, `os.popen` imports anywhere
  in the module.
* Source-text scan: no GitHub CLI shell-out literal, no
  version-control CLI literal, no `--admin` literal.
* Every request body shape returns `status = not_yet_implemented`.
* Response envelope satisfies §2.5 closed schema exactly.

### 6.2 B2.8c — token-walker preconditions 1–7

* Each of parent-doc §3 preconditions 1–7 has a happy-path test
  and a failing-path test.
* Every parent-doc §7 stop condition emitted by this slice is
  reproduced deterministically: `token_missing`, `token_invalid`,
  `replay_detected`, `binding_mismatch` (drilled across
  `pr_number`, `pr_head_sha`, `evidence_hash`, `intent`, and
  the nonce dimension), `pr_number_mismatch`,
  `configuration_missing`.
* The preflight artefact is written before the verify call.
* The verify call routes through
  `reporting.approval_token_runtime.verify_runtime(...)` only.
* Replay test: the same token verifies once and is rejected on
  the second attempt with `replay_detected`.

### 6.3 B2.8d — GitHub-API-dependent preconditions 8–17

* A mocked GitHub API fixture returns the canonical
  `mergeStateStatus` values (`CLEAN`, `DIRTY`, `BLOCKED`,
  `UNSTABLE`, `BEHIND`, `HAS_HOOKS`, `UNKNOWN`); the adapter
  accepts only `CLEAN`.
* The mock returns each canonical check conclusion (`success`,
  `failure`, `cancelled`, `skipped`, `in_progress`, `null`);
  the adapter accepts only `success` for every required check.
* `head_sha_mismatch` test: the current head SHA differs from
  the token-bound head SHA; the adapter rejects with the closed
  stop_condition.
* `merge_state_not_clean`, `checks_not_green`,
  `branch_protection_not_satisfied`, `unexpected_files_touched`,
  `deploy_coupling_detected`, `step5_flag_changed`,
  `level_6_attempted`, `protected_path_violation`,
  `stale_recommendation`, `network_uncertain`,
  `audit_write_failure` — each reproduced deterministically and
  recorded in the failure artefact.
* No live GitHub call is made by any test in this sub-unit.

### 6.4 B2.8e — integration + wiring

* End-to-end test against the §6.3 mocked GitHub fixture: the
  happy path produces an `ok` envelope and the dry-run
  artefact; every §7 stop condition produces a failure
  artefact.
* Audit redaction tests via
  `reporting.agent_audit_summary.assert_no_secrets()`: a
  tampered fixture injecting a token-shaped string into any
  artefact field is detected and rejected.
* Operator-applied wiring patch registers the blueprint in
  `dashboard/dashboard.py`. The patch lives outside the agent's
  allowlist; the operator applies it manually (see the B2.0c
  precedent in this codebase).
* Parent-doc §5 / §10 are updated to mark Phase 2 as
  Implemented and to link to the concrete module(s).
* The existing parent-doc pin
  `test_doc_states_no_merge_execution_route_exists` is replaced
  in the same PR by a positive pin asserting "exactly one
  merge-execution route exists, and it is the dry-run route".
  No other existing pin is weakened.

### 6.5 All sub-units

* No new env-var name is introduced beyond what
  `reporting.approval_token_runtime` already consumes.
* No new write-prefix sentinel is introduced outside
  `logs/n5b_merge_execution/`.
* `step5_implementation_allowed` remains `False`.
* `STEP5_ENABLED_SUBSTAGE` remains `"none"`.
* `level6_enabled` is `False` in every response envelope.
* `dry_run_only` is `True` in every response envelope.
* `live_merge_implemented` is `False` in every response envelope.
* `deploy_coupled` is `False` in every response envelope.

---

## 7. Permanent denials (binding across the entire B2.8 sub-batch)

* **No Level 6.** Per ADR-015 §Doctrine 1, Level 6 is
  permanently disabled. None of the B2.8 sub-units may raise
  the autonomy ladder ceiling.
* **No autonomous merge.** Every merge requires the parent doc
  §3 / §10 operator confirmation moments. No "the agent has
  been good for N days, so it can merge now" rule.
* **No autonomous deploy.** The deploy workflow remains coupled
  only to `workflow_run` after the Fast pre-merge gate succeeds
  on `main`, and to operator-initiated `workflow_dispatch`. The
  dry-run endpoint must terminate before the deploy workflow
  triggers; the dry-run endpoint must never invoke the deploy
  workflow directly.
* **No autonomous trading.** N5b is a development-governance
  surface; none of the B2.8 sub-units may touch `live/**`,
  `paper/**`, `shadow/**`, `risk/**`, `broker/**`,
  `execution/**`, or `research/**`.
* **No Step 5 enablement.** `step5_implementation_allowed`
  remains `False` and `STEP5_ENABLED_SUBSTAGE` remains `"none"`
  unless a separate operator-authored ADR explicitly enables a
  substage. None of the B2.8 sub-units may change either flag.
* **No `generated_seed.jsonl` writer coupling.** A18b is
  independently gated and must not be triggered, prepared,
  staged, or implied by any B2.8 sub-unit. The exact operator
  phrase required to start A18b is:

  ```
  go a18b generated_seed writer
  ```

  (lowercased here to keep this document inert to push-body
  safety lints; the parent doc carries the canonical
  capitalisation as the activation marker.)

  Without that exact phrase from the operator, A18b must not be
  started, scoped, drafted, or stub-implemented.
* **No merge without exact operator confirmation.** Each
  hypothetical future live merge requires a separate operator
  confirmation marker at execution time, distinct from the
  operator's earlier token mint. The dry-run endpoint surfaced
  by this plan does not perform live merges, so this denial is
  binding on Phase 3+ rather than Phase 2 — but it is repeated
  here so the contract chain is unbroken.
* **No runtime authority.** This plan-doc grants no runtime
  authority. Reading or quoting any section of this doc does
  not authorise any sub-unit; only the operator's explicit go
  phrase for that sub-unit authorises it.

---

## 8. Carry-forward (open items NOT advanced by this PR)

After B2.8a lands, the following remain open and **not
authorised** by this PR:

* **B2.8b skeleton UNWIRED** — not done. Requires explicit
  operator-go AND the §4 hard preconditions acknowledged.
* **B2.8c token-walker preconditions 1–7** — not done.
  Requires explicit operator-go AND the §4 hard preconditions
  acknowledged.
* **B2.8d GitHub-dependent preconditions 8–17 (mocked)** — not
  done. Requires explicit operator-go AND the §4 hard
  preconditions acknowledged.
* **B2.8e integration + wiring + parent-doc update** — not
  done. Requires explicit operator-go AND the §4 hard
  preconditions acknowledged.
* **N4b Phase B activation** — operator-only VPS step. Not
  advanced by this PR.
* **N4c or equivalent mint/verify UI** — future slice. Not
  advanced by this PR.
* **N5b Phase 3 (operator-confirmed live merge in test repo /
  simulated harness)** — far future; permanently denied without
  a separate explicit operator-go per parent-doc §10 line
  "Phase 3 — Operator-confirmed live merge in test repo /
  simulated harness".
* **N5b Phase 4 (production PR merge)** — permanently denied
  without a separate explicit operator-go per parent-doc §10
  line "Phase 4 — Production PR merge, if ever approved".

---

## 9. Cross-references

* [`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
  — parent doc; canonical N5b plan covering Phases 0/1/2/3/4,
  §3 preconditions, §6 audit artefacts, §7 stop conditions, §8
  security boundaries, §10 rollout, §11 permanent denials.
* [`n5b_merge_preflight_runbook.md`](n5b_merge_preflight_runbook.md)
  — N5b Phase 1 operator runbook (read-only preflight
  upstream-refresh chain).
* [`n4b_runtime_activation.md`](n4b_runtime_activation.md) —
  N4b runtime activation runbook (operator VPS step; required
  by §4.2 above).
* [`approval_token_gate.md`](approval_token_gate.md) — N4a pure
  callable mint/verify contract (the contract N4b activates).
* [`development_merge_recommendation.md`](development_merge_recommendation.md)
  — N5a read-only merge recommendation projector (the upstream
  Phase 2 reads).
* [`vps_deploy.md`](vps_deploy.md) — deploy workflow + script
  (the deploy surface N5b must remain decoupled from).
* [`no_touch_paths.md`](no_touch_paths.md) — protected paths
  the dry-run endpoint must refuse to allow inside a PR's diff.
* [`execution_authority.md`](execution_authority.md) —
  per-action authority decisions and the "operator-only"
  markers the dry-run endpoint must carry.
* [`../adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md)
  — authority doctrine (which subsystem owns truth for each
  domain).
* [`../adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  — Level 6 permanently-disabled doctrine; autonomy-ladder
  authority chain.

---

## 10. Status

| Aspect | Status |
|---|---|
| Plan only | Yes |
| Not implemented | Yes |
| Runtime code in this PR | None |
| Operator-go for B2.8b / B2.8c / B2.8d / B2.8e | NOT given by this PR |
| Mutates production | No |
| step5_implementation_allowed | `false` |
| STEP5_ENABLED_SUBSTAGE | `"none"` |
| Level 6 | permanently disabled |
| Autonomous merge | denied |
| Autonomous deploy | denied |
| Autonomous trading | denied |
| Dry-run default | required for any future B2.8 sub-unit |
| Deploy coupling | forbidden across the entire B2.8 sub-batch |
| Branch protection bypass | forbidden |
| Operator-go-only (this PR's go phrase) | given for B2.8a only |
| No runtime authority | yes — this plan grants none |
| No merge execution route exists | yes — none added by this PR |
