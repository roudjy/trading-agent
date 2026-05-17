# N5b Phase 3 — Recorded-Fixture Simulator: Implementation Plan (Plan-only)

> **Status:** Plan only. **Not implemented.**
>
> This document decomposes N5b Phase 3 (the operator-confirmed
> live-merge-in-simulator slice described in
> [`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
> §10 row 3) into ordered, auditable sub-units. It introduces
> **no runtime code, no new dashboard route, no real GitHub
> call, no network call, no audit-artefact write, and no
> governance escalation**.
>
> The plan-only status of this document is binding: a future PR
> that introduces runtime code under any sub-unit name (B2.9b /
> B2.9c / B2.9d / B2.9e) requires its own explicit operator-go
> phrase per §3.

---

## 1. Scope

### 1.1 What this plan covers

* The closed contracts (module path, route URL, request schema,
  response statuses, audit artefact paths, sub-unit
  decomposition, fixture schema) that any future N5b Phase 3
  implementation must satisfy.
* The hard preconditions that must be true before any runtime
  code-bearing sub-unit lands.
* The pin-test set in
  [`tests/unit/test_n5b_phase3_implementation_plan.py`](../../tests/unit/test_n5b_phase3_implementation_plan.py)
  that locks the contracts in this document.

### 1.2 What this plan does NOT cover

* It does **not** advance Phase 3 implementation.
* It does **not** introduce a sacrificial GitHub repository
  path — see §1.4.
* It does **not** activate any live-merge code path.
* It does **not** modify the N5b Phase 1 / Phase 2 surfaces
  (preflight projector + dry-run module + dry-run/history
  writers from B2.8a–B2.8e) other than possibly extending the
  parent-doc cross-reference section.
* It does **not** introduce the literal future-route URL or
  the forbidden shell-out / network tokens into any runtime
  source file under `dashboard/`, `reporting/`, `scripts/`, or
  `.github/workflows/`.
* It does **not** authorise N5b Phase 4 (production PR merge),
  which remains permanently denied for ADE per §5 of this plan.

### 1.3 Parent doc

The canonical plan for the full N5b execution surface (Phases
0/1/2/3/4, §3 preconditions, §6 audit artefacts, §7 stop
conditions, §8 security boundaries, §10 rollout, §11 permanent
denials) is
[`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md).
This sub-plan extends that doc; every contract here must be
consistent with the parent. Conflicts resolve in favour of the
parent.

### 1.4 Selected Phase 3 path: recorded-fixture simulator

Parent doc §10 row 3 offers two possible Phase 3 shapes:
sacrificial test repository OR recorded-fixture simulator. The
operator has selected the **recorded-fixture simulator** path.
The **sacrificial GitHub repository path is rejected** and
remains permanently deferred — it would require a real GitHub
PAT, a real `gh pr merge` invocation, real network traffic,
and ADE-side merge authority over a real (non-production)
repo. All four are incompatible with the doctrine "ADE must
never live trade; paper/shadow remains the maximum ADE end
state; Phase 3 simulator is the maximum allowed merge-like
surface". The sacrificial-repo path may not be revisited
without a separate operator-authored ADR.

The recorded-fixture simulator:

* Reads a closed-schema on-disk JSON fixture (operator-provided
  on the VPS, gitignored, never committed).
* Replays the fixture's pre-recorded `merge_response` envelope
  as if it had come from GitHub.
* Performs **no** outbound HTTP / GitHub API / shell-out / `gh`
  / `git` / subprocess / socket call of any kind.
* Writes a closed-schema simulation artefact to
  `logs/n5b_merge_execution/phase3_simulation/latest.json` and
  appends to
  `logs/n5b_merge_execution/phase3_simulation/history.jsonl`
  (same sentinel-restricted write prefix as B2.8c–e — no new
  prefix introduced).

---

## 2. Closed contracts for the future Phase 3 implementation

The strings, paths, and field names enumerated in this section
are **closed**. The future implementation must match them
byte-identical; the pin tests in
`tests/unit/test_n5b_phase3_implementation_plan.py` enforce
that.

### 2.1 Module paths

The future Phase 3 dashboard module is at exactly:

```
dashboard/api_merge_execution_simulate.py
```

The future Phase 3 reporting-side projector lives at exactly:

```
reporting/n5b_merge_execution_simulate.py
```

No other paths are permitted.

### 2.2 Route

Exactly one POST route:

```
POST /api/agent-control/merge-execution/simulate
```

* Method: POST only. GET / PUT / PATCH / DELETE return 405.
* Auth: session-protected + N4b token-gated (reuses the
  existing B2.8e dry-run token; no new N4b intent literal is
  added — `mobile_approval_dispatch` remains the only intent
  used by the merge-execution surface).
* Idempotency: NOT idempotent — each request either succeeds
  (one simulation artefact written, one history row appended)
  or fails with a precise stop-condition envelope. Operator
  re-mints to retry.

### 2.3 Request body schema (closed, JSON)

```
{
  "pr_number":                    <int>,
  "pr_head_sha":                  "<string>",
  "token":                        "<string>",
  "intent":                       "mobile_approval_dispatch",
  "evidence_hash":                "<string>",
  "operator_confirmation_marker": "simulator_execute_confirmed"
}
```

* Fields 1–5 mirror B2.8e's request body verbatim.
* `operator_confirmation_marker` is a closed-vocab singleton
  literal `"simulator_execute_confirmed"`. It is NOT a new
  N4b token. It proves the operator hit `/simulate` AFTER
  reviewing the B2.8e dry-run result; the act of POSTing this
  marker IS the second confirmation, mediated by the existing
  dashboard session auth and the N4b dry-run token.
* All six fields are required. Missing or unrecognised fields
  produce a closed-envelope rejection.

### 2.4 Response statuses (closed vocabulary)

The response envelope's `status` field is one of:

| status | Meaning |
|---|---|
| `ok` | every Phase 3 precondition satisfied; simulator ran end-to-end; simulation artefact + history written. **NEVER means** "real merge executed" / "PR mutated" / "deploy triggered" / "live execution authorized". |
| `rejected` | at least one precondition failed; `stop_condition` populated from §7 of the parent doc. |
| `configuration_missing` | `ADE_N5B_SIMULATOR_ENABLED` env unset, fixture file missing, or runtime not ready. No `stop_condition`. |
| `not_yet_implemented` | interim status returned by B2.9b sub-unit until the full simulator walker lands in B2.9c / B2.9d. |

No other status value is permitted.

### 2.5 Closed response invariants on `status="ok"`

The Phase 3 endpoint MUST emit the following discipline
invariants on every `ok` response — pinned by the behavioural
co-occurrence test in B2.9e:

* `dry_run_only = true`
* `live_merge_implemented = false`
* `deploy_coupled = false`
* `level6_enabled = false`
* `step5_implementation_allowed = false`
* `step5_enabled_substage = "none"`
* `target_classification = "recorded_fixture_simulator"`
* `mode = "simulate_only"`
* `would_proceed = true` — but **only as a dry-run-only proceed
  signal**, never as live merge authority.

### 2.6 Audit artefact paths (closed, under `logs/n5b_merge_execution/`)

| Artefact kind | Path | Writer |
|---|---|---|
| Phase 3 simulation (latest) | `logs/n5b_merge_execution/phase3_simulation/latest.json` | every Phase 3 invocation that produces a decision (`ok` or `rejected`) |
| Phase 3 simulation (history) | `logs/n5b_merge_execution/phase3_simulation/history.jsonl` | append-only, capped row count |

The B2.8e preflight + dry_run + history + failure artefacts
remain UNCHANGED — Phase 3 does NOT overwrite them. Phase 3
adds its own subdirectory `phase3_simulation/` under the same
sentinel-restricted prefix.

Phase 3 does NOT write a `n5b_execution` artefact (that
schema kind is reserved for the Phase 4 production-merge
endpoint, which is permanently denied for ADE per §5).

### 2.7 Closed fixture schema (operator-provided, on-disk)

The recorded-fixture file is read by the Phase 3 simulator
from a closed path. The fixture schema is:

```
{
  "fixture_schema_version": 1,
  "fixture_kind":           "n5b_phase3_recorded_merge_simulation",
  "merge_response": {
    "http_status":           <int>,
    "classification":        "<closed-vocab string>",
    "post_merge_head_sha":   "<string>",
    "merge_method":          "squash",
    "delete_branch":         <bool>
  },
  "generated_at_utc":        "<ISO 8601 string>",
  "fixture_notes":           "<bounded string; optional>"
}
```

Closed `classification` vocab:
`("merged_ok", "merged_with_warnings", "refused_by_github", "network_uncertain")`.

The fixture path is closed (operator cannot supply a path at
request time). Default location:
`state/n5b_simulator_fixture.json` (gitignored, never
committed). The path is configurable by the operator-set env
var `ADE_N5B_SIMULATOR_FIXTURE_PATH` (read-only by the
runtime; not a new mint/verify env var).

---

## 3. Sub-unit decomposition (exact)

N5b Phase 3 is delivered as the ordered sub-units below. Each
sub-unit may be a separate commit on a single branch OR a
separate PR — the operator selects per Phase 3 rollout.

| Unit | Scope | Mutates production | Operator-go status |
|---|---|---|---|
| **B2.9a** | this plan-doc + pin tests in `tests/unit/test_n5b_phase3_implementation_plan.py` + small cross-reference in the parent doc §13. No runtime code. | No | **given** for B2.9a only |
| **B2.9b** | reporting-side simulator core module `reporting/n5b_merge_execution_simulate.py` with closed-schema fixture replay + simulation artefact writers (`latest.json` + `history.jsonl`). Stdlib-only. No subprocess, no network, no env read. Pin tests cover deterministic replay, sentinel-restricted writes, `assert_no_secrets` before write. | No | **NOT given** by this plan-only PR |
| **B2.9c** | dashboard module `dashboard/api_merge_execution_simulate.py` (POST route, **UNWIRED** in `dashboard/dashboard.py`); session-protected + N4b dry-run-token-gated; operator-confirmation-marker validation; calls the B2.9b projector; returns `not_yet_implemented` on full success until B2.9e flips it. | No | **NOT given** by this plan-only PR |
| **B2.9d** | operator-applied wiring patch on `dashboard/dashboard.py` (B2.0c precedent — Claude blocked by `.claude/hooks/deny_no_touch.py`). Operator applies the 2-line wiring patch manually; Claude adds the corresponding test-pin update as a separate commit. | No | **NOT given** by this plan-only PR; operator-applied separately |
| **B2.9e** | flip B2.9c's `not_yet_implemented` → `status="ok"` on full success; integration tests against the recorded-fixture covering canonical `classification` values; parent-doc §10 row 3 status update to "Module implemented locally (simulator-only); dashboard wiring pending operator-applied patch"; §11 permanent denial addendum for Phase 4. | No (still no real merge; no PR mutated) | **NOT given** by this plan-only PR |

Sub-units B2.9b through B2.9e MUST land in this order. Skipping
order, splitting a unit further, or bundling two units into one
commit without an operator-go that updates this table is
forbidden.

---

## 4. Hard preconditions before any runtime sub-unit lands

Before B2.9b — or any subsequent code-bearing sub-unit — lands,
**ALL three** of the following must be true and explicitly
acknowledged by the operator in the commit/PR description for
that sub-unit. The operator is the sole authority on whether
each precondition is met.

### 4.1 Phase 2 observed-clean period elapsed

The N5b Phase 2 dry-run endpoint
(`dashboard/api_merge_execution_dry_run.py`,
`reporting/n5b_merge_execution_dry_run.py`) has been
merged + deployed + observed clean for a bounded period per
parent §10 row "Phase 2 must be merged + observed clean for a
bounded period before promotion".

### 4.2 N4b runtime + dry-run token verification observed clean on VPS

The existing B2.8c-pre N4b activation contract
([`n5b_phase2_precondition_readiness.md`](n5b_phase2_precondition_readiness.md))
continues to hold. Phase 3 reuses the existing N4b
`verify_runtime_for_dry_run` surface — no new mint/verify
contract is introduced.

### 4.3 Operator-provided fixture exists on VPS

The recorded-fixture JSON file exists on the live VPS at the
operator-configured path (default
`state/n5b_simulator_fixture.json`) and matches the §2.7
closed schema. The fixture is operator-only; it is **never**
committed to the repo. The B2.9 runtime tests inject synthetic
fixtures via monkeypatched paths — production behaviour without
a fixture deliberately returns `configuration_missing`.

---

## 5. Hard denials (binding on every sub-unit)

The future implementation modules introduced by B2.9b through
B2.9e MUST NOT:

* invoke a GitHub command-line tool shell-out (the parent
  doc's §7 / §8 enforcement applies);
* invoke a version-control command-line tool shell-out from
  any module touched by these sub-units;
* call `subprocess.run`, `subprocess.Popen`, `subprocess.call`,
  `subprocess.check_call`, `subprocess.check_output`,
  `os.system`, `os.popen`, or any other shell-spawning
  primitive;
* open a network socket directly (no `socket`, no `urllib`,
  no `requests`, no `httpx`, no `aiohttp` import outside the
  vetted `reporting.approval_token_runtime` import surface,
  which itself opens no socket);
* read any environment variable other than the ones already
  read by `reporting.approval_token_runtime` (i.e. only
  `ADE_APPROVAL_TOKEN_HMAC_SECRET`) and the new closed Phase 3
  config var `ADE_N5B_SIMULATOR_ENABLED` and
  `ADE_N5B_SIMULATOR_FIXTURE_PATH` (read by the dashboard
  module only, never a mint/verify secret);
* write any path outside the `logs/n5b_merge_execution/`
  subtree (no new write-prefix sentinel introduced);
* mutate any pull request, real or sacrificial — Phase 3 is
  simulator-only;
* touch `.claude/**`, `.github/**`, `live/**`, `paper/**`,
  `shadow/**`, `risk/**`, `broker/**`, `execution/**`,
  `research/**`, `seed.jsonl`, `generated_seed.jsonl`,
  `delegation_seed.jsonl`, or any other no-touch path enumerated
  in [`no_touch_paths.md`](no_touch_paths.md);
* change `step5_implementation_allowed` away from `False` or
  `STEP5_ENABLED_SUBSTAGE` away from `"none"`;
* introduce or reference any Level 6 capability marker (Level
  6 is permanently disabled per ADR-015 §Doctrine 1);
* trigger the deploy workflow — Phase 3 must terminate before
  the deploy workflow triggers and must never invoke the
  deploy workflow directly;
* emit `report_kind="n5b_execution"` in any artefact — that
  schema kind is reserved for the Phase 4 production-merge
  endpoint, which is permanently denied for ADE (§5.1 below);
* emit `target_classification="production_pr_merge"` — that
  literal is reserved for the Phase 4 production-merge
  endpoint, permanently denied for ADE (§5.1 below);
* reference `ADE_N5B_LIVE_EXECUTE_ENABLED` in any runtime
  source — that env flag is the Phase 4 gate, permanently
  denied for ADE (§5.1 below);
* add a new N4b intent literal beyond the existing
  `mobile_approval_dispatch` / `mobile_review_dispatch` —
  doing so would mutate the N4a frozen contract.

### 5.1 Phase 4 production merge permanently denied for ADE

N5b Phase 4 (production PR merge) is **permanently denied for
ADE**. Even with a hypothetical operator-go, ADE / Claude is
NOT the authority that may flip
`ADE_N5B_LIVE_EXECUTE_ENABLED=true` on any system. The
eventual Phase 4 authority (if it ever exists) must be a
non-ADE operator surface authored under a separate
operator-authored ADR.

Symmetry with the trading-side doctrine:

* Trading-side: live trading is permanently denied for ADE;
  paper/shadow is the maximum end state.
* Merge-side: Phase 4 production PR merge is permanently
  denied for ADE; Phase 3 recorded-fixture simulator is the
  maximum end state.

This §5.1 denial is added to the parent doc §11 (permanent
denials) by B2.9e.

---

## 6. Per-sub-unit test requirements

### 6.1 B2.9a — plan-doc pin tests

* The doc exists at exactly
  `docs/governance/n5b_phase3_implementation_plan.md`.
* The doc declares "Plan only" status and "Not implemented"
  status.
* The doc pins the future dashboard module path
  (`dashboard/api_merge_execution_simulate.py`) and reporting
  module path (`reporting/n5b_merge_execution_simulate.py`).
* The doc pins the future route URL
  `/api/agent-control/merge-execution/simulate` and POST
  method.
* The doc pins the closed request-body schema (6 fields)
  including the `operator_confirmation_marker` singleton
  literal.
* The doc pins the closed response-status vocab (`ok`,
  `rejected`, `configuration_missing`,
  `not_yet_implemented`).
* The doc pins the closed response invariants on `status="ok"`
  including `target_classification="recorded_fixture_simulator"`
  and `mode="simulate_only"`.
* The doc pins the closed artefact paths
  (`logs/n5b_merge_execution/phase3_simulation/latest.json` +
  `history.jsonl`).
* The doc pins the closed fixture schema with
  `fixture_kind="n5b_phase3_recorded_merge_simulation"`.
* The doc pins the rejection of the sacrificial-GitHub-repo
  path.
* The doc pins the Phase 4 permanent denial for ADE.
* The doc pins the §5 hard-denial doctrine (no
  GitHub API / `gh` / `git` / `subprocess` / `socket` /
  network / new N4b intent / Step 5 / Level 6).
* No N5b Phase 3 runtime module exists in the repo at the time
  of this PR (negative pin via Path.is_file() on the future
  module paths).
* No N5b Phase 3 route URL is registered in any runtime
  source at the time of this PR (negative pin via source-text
  scan on `dashboard/`, `reporting/`, `scripts/`).

### 6.2 B2.9b — simulator core

* Module exists at `reporting/n5b_merge_execution_simulate.py`.
* AST scan: no `subprocess`, `socket`, `urllib`, `requests`,
  `httpx`, `aiohttp`, `os.system`, `os.popen`,
  `reporting.approval_token_runtime`,
  `reporting.approval_token_gate`, `github`, `ghapi`,
  `PyGithub` imports.
* Source-text scan: no `gh pr merge` / `git merge ` /
  `--admin` / `--no-verify` / `merge_pull_request` /
  `mergePullRequest` literals.
* No env-var read (`os.environ`, `os.getenv`, `getenv(`).
* Closed fixture schema + closed snapshot schema (key-set
  check).
* Sentinel-restricted write: any path not containing
  `logs/n5b_merge_execution/` raises `ValueError`.
* `assert_no_secrets` runs on every payload before write.
* Atomic write via `tempfile.mkstemp` + `os.replace`.
* Bounded history compaction (matches B2.8e
  `MAX_HISTORY_ROWS` discipline).
* Closed `target_classification` singleton vocab
  `("recorded_fixture_simulator",)`.
* Closed `mode` singleton vocab `("simulate_only",)`.
* Closed `merge_response.classification` vocab matching parent
  §6.4: `("merged_ok", "merged_with_warnings", "refused_by_github", "network_uncertain")`.
* Deterministic fixture replay: given fixture X + walker
  inputs Y, snapshot output is byte-stable modulo timestamp
  fields.
* Step 5 invariants pinned in source: `Final[False]`,
  `Final["none"]`.
* The safety-invariants dict carries the closed booleans:
  `no_real_github_merge`, `no_production_merge`, `no_network`,
  `no_git_or_gh_or_subprocess`, `no_step5_runtime`,
  `no_level6`, `no_live_trading`, `no_paper_shadow_runtime` —
  every one always `True` for the simulator.

### 6.3 B2.9c — dashboard route module (UNWIRED)

* Module exists at
  `dashboard/api_merge_execution_simulate.py`.
* Exactly one POST route at
  `/api/agent-control/merge-execution/simulate`.
* GET / PUT / PATCH / DELETE return 405.
* Blueprint NOT registered in `dashboard/dashboard.py`
  (UNWIRED pin until B2.9d).
* AST forbidden imports same as §6.2 plus
  `reporting.github_pr_lifecycle` (uses `subprocess`).
* The route uses
  `reporting.approval_token_runtime.verify_runtime_for_dry_run`
  for the original dry-run token; **no new N4b intent**.
* Request body shape pinned to the closed §2.3 schema.
* `operator_confirmation_marker` is verified against the
  closed literal `"simulator_execute_confirmed"`.
* On missing fixture / env unset → `configuration_missing`.
* On failure-paths → `rejected` with closed `stop_condition`.
* On full success → `not_yet_implemented` until B2.9e flips
  it (B2.8d deferral pattern preserved).
* No env-var read in the module beyond
  `ADE_N5B_SIMULATOR_ENABLED` and
  `ADE_N5B_SIMULATOR_FIXTURE_PATH` (read by a closed reader
  with default + bounded length).

### 6.4 B2.9d — operator-applied wiring

* `dashboard/dashboard.py` is on the no-touch list per
  `docs/governance/no_touch_paths.md`. Claude cannot edit it
  (`.claude/hooks/deny_no_touch.py` blocks). Operator applies
  the 2-line wiring patch manually (B2.0c precedent).
* Claude commits the corresponding test-pin update on the
  same branch as a separate commit:
  - Replace the B2.9c UNWIRED pin with a positive
    `test_simulator_blueprint_registered_in_dashboard_py` pin.

### 6.5 B2.9e — flip + integration + docs

* Flip the B2.9c `not_yet_implemented` happy-path to
  `status="ok"` with the §2.5 closed invariants nailed.
* Behavioural co-occurrence pin: `would_proceed=true` ⇔ every
  §2.5 invariant true, in BOTH envelope AND persisted
  `phase3_simulation/latest.json` artefact.
* Integration parametrization across canonical fixture
  `classification` values.
* Parent doc §10 row 3 status update.
* Parent doc §11 permanent denial addendum for Phase 4.
* No retirement of any existing B2.8b–e UNWIRED / Phase-3-
  permanently-denied / no-merge-execution pin beyond the
  one operator-approved by-product of the wiring commit.

---

## 7. Permanent denials (re-iterated; binding on every sub-unit)

All §11 permanent denials from
[`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
apply to every Phase 3 sub-unit unchanged. The Phase 3
sub-batch adds the operator-authored Phase-4-permanently-
denied-for-ADE addendum (§5.1) to that §11 list as part of
B2.9e.

* **No Level 6.** Permanently disabled.
* **No autonomous merge.** No code path performs a real merge.
* **No autonomous deploy.** Phase 3 must not trigger deploy.
* **No autonomous trading.** Phase 3 must not touch
  `live/**`, `paper/**`, `shadow/**`, `risk/**`, `broker/**`,
  `execution/**`, `research/**`.
* **No Step 5 enablement.** Both Step 5 constants unchanged.
* **No `generated_seed.jsonl` writer coupling.**
* **No merge without exact operator confirmation.** Phase 3
  enforces the second-confirmation marker. Phase 4 remains
  permanently denied for ADE.
* **No new N4b intent literal.** N4a/N4b frozen contract
  preserved.
* **No `n5b_execution` artefact kind from Phase 3.** Reserved
  for the Phase 4 production-merge endpoint, permanently
  denied for ADE.
* **No `target_classification="production_pr_merge"`.** Phase
  3 uses only `"recorded_fixture_simulator"`.
* **No `ADE_N5B_LIVE_EXECUTE_ENABLED` reference in runtime
  source.** That env flag is the Phase 4 gate, permanently
  denied for ADE.
* **No sacrificial GitHub repository path.** Rejected per
  §1.4.

---

## 8. Carry-forward (open items NOT advanced by this PR)

After B2.9a lands, the following remain open and **not
authorised** by this PR:

* **B2.9b simulator core** — not done. Requires explicit
  operator-go AND the §4 hard preconditions acknowledged.
* **B2.9c dashboard route module (UNWIRED)** — not done.
  Requires explicit operator-go.
* **B2.9d operator-applied wiring** — not done. Requires
  operator manual patch on `dashboard/dashboard.py`.
* **B2.9e flip + integration + docs** — not done. Requires
  explicit operator-go.
* **Phase 4 production PR merge** — permanently denied for
  ADE per §5.1. No future sub-unit may revive this without a
  separate operator-authored ADR explicitly removing the
  denial from a non-ADE actor surface.
* **Sacrificial GitHub repository path** — rejected per §1.4.

---

## 9. Cross-references

* [`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
  — parent doc; canonical N5b plan covering Phases 0/1/2/3/4,
  §3 preconditions, §6 audit artefacts, §7 stop conditions,
  §8 security boundaries, §10 rollout, §11 permanent denials.
* [`n5b_phase2_implementation_plan.md`](n5b_phase2_implementation_plan.md)
  — B2.8 Phase 2 sub-plan (the upstream module Phase 3
  reuses).
* [`n5b_phase2_precondition_readiness.md`](n5b_phase2_precondition_readiness.md)
  — Phase 2 readiness contract (the upstream readiness Phase
  3 inherits).
* [`approval_token_gate.md`](approval_token_gate.md) — N4a
  pure callable mint/verify contract (used unchanged by Phase
  3).
* [`n4b_runtime_activation.md`](n4b_runtime_activation.md) —
  N4b runtime activation runbook (used unchanged by Phase 3).
* [`vps_deploy.md`](vps_deploy.md) — deploy workflow + script
  (the deploy surface Phase 3 must remain decoupled from).
* [`no_touch_paths.md`](no_touch_paths.md) — protected paths
  Phase 3 must refuse to touch.
* [`execution_authority.md`](execution_authority.md) —
  per-action authority decisions and "operator-only" markers
  Phase 3 must carry.
* [`../adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md)
  — authority doctrine.
* [`../adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  — Level 6 permanently-disabled doctrine.

---

## 10. Status

| Aspect | Status |
|---|---|
| Plan only | Yes |
| Not implemented | Yes |
| Runtime code in this PR | None |
| Operator-go for B2.9b / B2.9c / B2.9d / B2.9e | NOT given by this PR |
| Mutates production | No |
| step5_implementation_allowed | `false` |
| STEP5_ENABLED_SUBSTAGE | `"none"` |
| Level 6 | permanently disabled |
| Autonomous merge | denied |
| Autonomous deploy | denied |
| Autonomous trading | denied |
| Selected Phase 3 path | recorded-fixture simulator |
| Sacrificial GitHub repository path | rejected |
| Phase 4 production PR merge | permanently denied for ADE |
| Dry-run default | required across the entire Phase 3 surface |
| Deploy coupling | forbidden |
| Branch protection bypass | forbidden |
| Operator-go-only (this PR's go phrase) | given for B2.9a only |
| No runtime authority for live merge | yes — Phase 3 is simulator-only |
| No GitHub API / network / subprocess | yes — pinned by AST + source-text scans on every Phase 3 module |
| Maximum allowed merge-like ADE surface | Phase 3 recorded-fixture simulator |
| Symmetric trading-side doctrine | ADE never live trades; paper/shadow is the maximum trading-side ADE end state |
