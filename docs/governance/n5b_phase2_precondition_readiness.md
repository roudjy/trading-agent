# N5b Phase 2 — Precondition Readiness Report (Governance-only, no runtime activation)

> **Status:** Governance + machine-checkable evidence only. **No
> runtime activation.** No VPS interaction. No environment
> variable read. No token verification. No precondition walker.
> No GitHub API call. No subprocess. No `logs/n5b_merge_execution/`
> write. No `dashboard.py` wiring.

> **Parent docs (cited by merge SHA on `main` at time of writing):**
>
> * [`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
>   — canonical N5b plan (Phases 0/1/2/3/4).
> * [`n5b_phase2_implementation_plan.md`](n5b_phase2_implementation_plan.md)
>   — B2.8a doc (merge SHA `8832f57`, [PR #231](https://github.com/roudjy/trading-agent/pull/231)).
> * B2.8b skeleton UNWIRED — merge SHA `03e228e`,
>   [PR #232](https://github.com/roudjy/trading-agent/pull/232).

> **Step 5 invariants preserved:**
> `step5_implementation_allowed` remains `Final[False]`,
> `STEP5_ENABLED_SUBSTAGE` remains `Final["none"]`,
> Level 6 remains permanently disabled.

---

## 1. Purpose

This report locks the **precondition state** for N5b Phase 2
implementation into a SHA-anchored, machine-checkable artefact.
Any future code-bearing sub-unit (B2.8c / B2.8d / B2.8e) must
cite this doc in its PR description and set the three
operator-declared fields in §6 to the explicit values that
unlock the next step.

The report does not advance Phase 2 implementation. It does not
activate N4b on the VPS. It does not ship a new endpoint, a new
runtime module, a new env var, or a new audit artefact path.

The report is governance-only. Its only outputs are:

* this Markdown document under `docs/governance/`;
* a parallel pin-test file under `tests/unit/`;
* a small back-pointer §11 in
  [`n5b_phase2_implementation_plan.md`](n5b_phase2_implementation_plan.md).

---

## 2. §4.1 — Phase 1 observed-clean period

**Source contract:**
[`n5b_phase2_implementation_plan.md`](n5b_phase2_implementation_plan.md)
§4.1 — "The N5b Phase 1 preflight projector ... has been
merged + deployed + observed clean for a bounded period."
"The operator declares the period elapsed; this plan does not
encode a numeric duration."

### 2.1 Repo evidence

| Artefact | Status | Reference |
|---|---|---|
| N5b Phase 1 preflight projector (`reporting/development_merge_preflight.py`) | merged on `main` | [PR #204](https://github.com/roudjy/trading-agent/pull/204) merged 2026-05-12 |
| N5b Phase 1 operator runbook | merged on `main` | [PR #207](https://github.com/roudjy/trading-agent/pull/207) merged 2026-05-13 |
| N5b Phase 1 PWA read-only UI | merged on `main` | [PR #211](https://github.com/roudjy/trading-agent/pull/211) |
| Elapsed at time of writing | ≥ 3 calendar days since PR #204 | Authoritative answer is the **operator's** declaration, not a numeric threshold |

### 2.2 Operator-only declaration

The "observed clean for a bounded period" judgment is **not
machine-checkable from the repo**. The operator declares it in
the B2.8c PR description by setting:

```
phase_1_observed_clean: <YES | NO | NOT_YET_DECLARED>
phase_1_observed_clean_comment: <bounded free text, optional>
```

* Default value in this doc and in any PR description that has
  not been explicitly updated by the operator: `NOT_YET_DECLARED`.
* Any B2.8c (or later) PR that omits the field, sets it to
  `NO`, or leaves it at `NOT_YET_DECLARED` is rejected by the
  contract.

---

## 3. §4.2 — N4b Phase B activation on VPS

**Source contract:**
[`n5b_phase2_implementation_plan.md`](n5b_phase2_implementation_plan.md)
§4.2 — "`ADE_APPROVAL_TOKEN_HMAC_SECRET` is exported in the VPS
runtime environment, and
`reporting.approval_token_runtime.is_configured()` returns True
at runtime against that secret."

### 3.1 Repo evidence

| Artefact | Status | Reference |
|---|---|---|
| N4b runtime module (`reporting/approval_token_runtime.py`) | merged | `is_configured()` returns `True` iff the env secret is set + decodes to ≥ 32 bytes |
| N4b dashboard blueprint (`dashboard/api_approval_token_gate.py`) | merged + wired | mint / verify / status routes are operator-session-protected |
| N4b operator runbook | merged | [`n4b_runtime_activation.md`](n4b_runtime_activation.md) §4 |
| VPS env export status | **operator-only — not machine-checkable from repo** | The env var lives only on the Hetzner VPS; the runbook §4.3 / §4.4 describes the operator-only export step |

### 3.2 Why this is not machine-checkable from repo

* `ADE_APPROVAL_TOKEN_HMAC_SECRET` is **never** committed,
  **never** in `docker-compose.yml`, **never** in `config/*`,
  **never** in any tracked file (per the N4b runbook §4.3
  hard guarantee).
* `is_configured()` returns `True` only when called inside the
  VPS process that has the env var set. From the repo CI, from
  a developer laptop, or from any process without the env, it
  returns `False` by definition.
* There is no committed status artefact, no committed nonce
  store, no logged "N4b activated" marker in the repo. The
  state lives only on the live VPS.
* The runbook §4.6 documents the operator-only verification
  step: run `curl /api/agent-control/approval-token/status` on
  the VPS and confirm `is_configured: true`.

### 3.3 Operator-only declaration

The operator declares the activation state in the B2.8c PR
description by setting:

```
n4b_phase_b_activated_on_vps: <YES | NO | UNKNOWN>
n4b_phase_b_evidence_ref: <bounded reference text, optional>
```

* `YES` is permitted only after the operator has personally
  verified `is_configured: true` against the VPS endpoint per
  N4b runbook §4.6.
* `n4b_phase_b_evidence_ref` may carry a redacted reference
  (e.g. an internal note timestamp, a runbook step number) —
  **never** the secret, **never** a captured token, **never** a
  raw `curl` response that contains a token, **never** any
  literal byte from the env value. The runbook §4.11 audit
  checklist is the canonical post-activation hygiene gate.
* Default value in this doc and in any PR description that has
  not been explicitly updated by the operator: `UNKNOWN`.
* Any B2.8c (or later) PR that omits the field, sets it to
  `NO`, or leaves it at `UNKNOWN` is rejected by the contract.

### 3.4 What this doc does NOT do

This doc does not import `reporting.approval_token_runtime`,
does not call `is_configured()`, does not read any environment
variable, does not interact with the VPS, does not consume any
N4b artefact. It records the source contracts and the
operator-only declaration shape.

---

## 4. §4.3 — N4c or equivalent token mint/verify UI

**Source contract:**
[`n5b_phase2_implementation_plan.md`](n5b_phase2_implementation_plan.md)
§4.3 — "The operator can mint and verify an N4b approval token
in the PWA (or an equivalent operator-facing surface) ...
without a curl-only mint flow. The mint/verify interaction
must have a documented, auditable surface."

### 4.1 Repo evidence — **machine-confirmed satisfied**

| Artefact | Status | Reference |
|---|---|---|
| N4c PWA component | merged on `main` | [PR #203](https://github.com/roudjy/trading-agent/pull/203) merged 2026-05-12; component path `frontend/src/routes/AgentControl/ApprovalTokenDiagnostics.tsx` |
| N4c route registration | wired | `/agent-control/approval-token-diagnostics` registered in `frontend/src/App.tsx` behind `RequireAuth` |
| N4c test surface | merged | `frontend/src/test/AgentControlApprovalTokenDiagnostics.test.tsx` |
| Mint / verify / replay / binding-mismatch flows | present | per component docstring §3 of the component file |
| Claim-only by construction | yes | component carries no approve / reject / merge / deploy / execute action verb |

The pin tests in
[`tests/unit/test_n5b_phase2_precondition_readiness.py`](../../tests/unit/test_n5b_phase2_precondition_readiness.py)
re-assert all four lines on every CI run.

### 4.2 No operator declaration required

§4.3 is satisfied at the repo level. The B2.8c PR description
nonetheless echoes the field for record-keeping symmetry:

```
n4c_or_equivalent_mint_verify_ui: YES
n4c_ui_route: /agent-control/approval-token-diagnostics
n4c_ui_component: frontend/src/routes/AgentControl/ApprovalTokenDiagnostics.tsx
```

The pin tests fail-closed if the component file is renamed or
the route literal is removed from `App.tsx`. Any change to
those facts requires updating both this doc and the pin tests
in the same PR.

---

## 5. What unlocks B2.8c

B2.8c may **NOT** start until all three of the following are
explicitly true in the B2.8c PR description:

```
phase_1_observed_clean: YES
n4b_phase_b_activated_on_vps: YES
n4c_or_equivalent_mint_verify_ui: YES
```

Any other combination is a contract violation. The B2.8c PR
that opens without these three `YES` lines is rejected; the
B2.8c PR that hand-waves or paraphrases is rejected.

This doc does not declare any of the three fields. This doc
does not provide an operator-go phrase for B2.8c. The B2.8c
operator-go is a **separate, explicit** instruction issued by
the operator after the three fields are personally verified.

---

## 6. Closed declaration schema (machine-checkable shape)

The B2.8c PR description must carry the declaration block in
exactly this shape (no extra fields, no missing fields). The
schema below shows the **default values** this governance doc
records — `NOT_YET_DECLARED` and `UNKNOWN` for the operator-only
fields, the machine-confirmed values for §4.3. The B2.8c PR
description flips the operator-only fields to `YES` once the
operator has personally verified them per §5:

```yaml
n5b_phase2_precondition_declaration:
  phase_1_observed_clean: NOT_YET_DECLARED   # operator flips to YES in the B2.8c PR
  phase_1_observed_clean_comment: ""

  n4b_phase_b_activated_on_vps: UNKNOWN      # operator flips to YES in the B2.8c PR
  n4b_phase_b_evidence_ref: ""

  n4c_or_equivalent_mint_verify_ui: YES
  n4c_ui_route: /agent-control/approval-token-diagnostics
  n4c_ui_component: frontend/src/routes/AgentControl/ApprovalTokenDiagnostics.tsx
```

Pin tests in this slice assert:

* the schema keys appear in this doc verbatim;
* the default values are the non-`YES` sentinels (so the doc
  itself never claims preconditions are met);
* future doc edits that flip any value to `YES` in this
  governance file are detected and rejected (only the B2.8c PR
  *description* may carry `YES` values; the governance doc
  records the schema, not the operator decision).

---

## 7. What this report does NOT do (binding non-goals)

* Does **not** import `reporting.approval_token_runtime`.
* Does **not** call `is_configured()`.
* Does **not** read any environment variable.
* Does **not** interact with the VPS — no `curl`, no
  `os.environ`, no `os.getenv`, no socket, no `urllib`, no
  `requests`, no `httpx`, no `aiohttp`.
* Does **not** invoke any GitHub API.
* Does **not** spawn a subprocess.
* Does **not** write to `logs/n5b_merge_execution/` or any
  other audit path.
* Does **not** wire `dashboard.py`.
* Does **not** modify the B2.8b skeleton at
  `dashboard/api_merge_execution_dry_run.py`.
* Does **not** modify the existing B2.8a pin tests beyond the
  small §11 back-pointer in the parent plan-doc.
* Does **not** modify the existing N5b parent plan pin tests.
* Does **not** declare any §4 precondition `YES`. The declaration
  is reserved for the B2.8c PR description, not this doc.
* Does **not** change `step5_implementation_allowed` or
  `STEP5_ENABLED_SUBSTAGE`. Both remain at their pinned values.
* Does **not** flip Level 6 from its permanently-disabled state.

---

## 8. Permanent denials (re-stated)

* **No Level 6.** Per ADR-015 §Doctrine 1, Level 6 is
  permanently disabled.
* **No autonomous merge.** Every merge requires the
  parent-doc §3 / §10 operator confirmation moments.
* **No autonomous deploy.** The deploy workflow remains
  coupled only to `workflow_run` after the Fast pre-merge gate
  succeeds on `main`, and to operator-initiated
  `workflow_dispatch`.
* **No autonomous trading.** No `live/**`, `paper/**`,
  `shadow/**`, `risk/**`, `broker/**`, `execution/**`,
  `research/**` touched.
* **No Step 5 enablement.** `step5_implementation_allowed`
  remains `False` and `STEP5_ENABLED_SUBSTAGE` remains `"none"`.
* **No `generated_seed.jsonl` writer coupling.** A18b is
  independently gated; this readiness report has no effect on
  the A18b activation gate.
* **No runtime authority.** This report grants no runtime
  authority.

---

## 9. Cross-references

* [`n5b_phase2_implementation_plan.md`](n5b_phase2_implementation_plan.md)
  — B2.8a Phase 2 implementation plan (the source of §4
  preconditions).
* [`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
  — N5b canonical parent plan (Phases 0/1/2/3/4).
* [`n4b_runtime_activation.md`](n4b_runtime_activation.md) —
  N4b operator runbook (the source of the §4.2 activation
  step).
* [`approval_token_gate.md`](approval_token_gate.md) — N4a pure
  callable mint/verify contract.
* [`no_touch_paths.md`](no_touch_paths.md) — protected paths
  every B2.8 sub-unit must refuse to allow.
* [`execution_authority.md`](execution_authority.md) —
  per-action authority decisions and "operator-only" markers.
* [`../adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md)
  — authority doctrine.
* [`../adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  — Level 6 permanently-disabled doctrine.

---

## 10. Status

| Aspect | Status |
|---|---|
| Governance-only | Yes |
| Runtime activation | No |
| Mutates production | No |
| Imports `reporting.approval_token_runtime` | No |
| Reads env var | No |
| VPS interaction | No |
| Writes `logs/n5b_merge_execution/` | No |
| Wires `dashboard.py` | No |
| Modifies B2.8b skeleton | No |
| §4.1 declaration | left as `NOT_YET_DECLARED` (operator-only) |
| §4.2 declaration | left as `UNKNOWN` (operator-only) |
| §4.3 evidence | machine-confirmed satisfied |
| Operator-go for B2.8c | NOT given by this PR |
| step5_implementation_allowed | `false` |
| STEP5_ENABLED_SUBSTAGE | `"none"` |
| Level 6 | permanently disabled |
