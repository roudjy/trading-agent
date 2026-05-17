# N5b — High-Risk Merge Execution Plan (Governance Doc)

> **Status:** Phase 0 + Phase 1 implemented. Phase 2 **module
> implemented locally (dry-run only); dashboard wiring pending
> operator-applied patch** — the dry-run route module exists at
> [`dashboard/api_merge_execution_dry_run.py`](../../dashboard/api_merge_execution_dry_run.py)
> with closed-schema preflight / failure / dry_run / history
> writers, but the blueprint is **NOT** registered in
> [`dashboard/dashboard.py`](../../dashboard/dashboard.py); no
> client can reach the route until the operator applies the
> two-line wiring patch separately (B2.0c precedent). Phase 3 +
> Phase 4 **Not implemented**. No runtime authority for live
> merge. Exactly one merge-execution route module exists, and
> it is the dry-run route. No UI action exists. No GitHub
> mutation exists. Phase 3 and Phase 4 remain plan only.
>
> **Authority:** development-governance documentation. This doc
> grants ADE **zero** authority over live merge / deploy / trade.
> The implemented Phase 2 dry-run endpoint emits
> `status="ok"` to mean *"dry-run checks passed and audit
> artefacts written"* — never *"merge executed"* or *"PR
> mutated"* or *"deploy triggered"* or *"live execution
> authorized"*. Every response envelope carries
> `dry_run_only=true`, `live_merge_implemented=false`,
> `deploy_coupled=false`.
>
> **Permanent denials (re-asserted):**
> * `step5_implementation_allowed = false` (unchanged)
> * `STEP5_ENABLED_SUBSTAGE = "none"` (unchanged)
> * Level 6 is permanently disabled per ADR-015 §Doctrine 1.
> * No autonomous merge / deploy / trade / approval.
> * No approval can happen from a notification click alone.
> * No live merge endpoint exists; Phase 3 + Phase 4 remain plan
>   only.

---

## 1. Status

* **Plan only** with respect to *live merge execution*. This
  document remains the design / governance / planning slice for
  any future live-merge implementation. Phase 3 and Phase 4 are
  **Not implemented**.
* **Phase 1 dry-run preflight projector is implemented**:
  `reporting/development_merge_preflight.py` emits the
  closed-schema `logs/development_merge_preflight/latest.json`
  artefact. **This phase remains read-only and dry-run only.**
* **Phase 2 module implemented locally (dry-run only); dashboard
  wiring pending operator-applied patch.** The dry-run route
  module exists at
  [`dashboard/api_merge_execution_dry_run.py`](../../dashboard/api_merge_execution_dry_run.py)
  with closed-schema preflight / failure / dry_run / history
  writers under `logs/n5b_merge_execution/`. The blueprint is
  **NOT** registered in
  [`dashboard/dashboard.py`](../../dashboard/dashboard.py): the
  module is on disk and importable, but no HTTP client can reach
  the route until the operator applies the 2-line wiring patch
  separately (B2.0c precedent). On `status="ok"` the dry-run
  endpoint signals *"dry-run checks passed and audit artefacts
  written"* — never *"merge executed"*, *"PR mutated"*,
  *"deploy triggered"*, or *"live execution authorized"*. Every
  response envelope carries `dry_run_only=true`,
  `live_merge_implemented=false`, `deploy_coupled=false`.
* **No GitHub mutation exists.** The repository contains no call
  to `gh pr merge`, `gh pr review --approve`, `git merge` (as a
  non-rebase operation against `main`), or any equivalent
  Git/GitHub mutation in production code paths outside the
  audited dashboard deploy script's idempotent
  `fetch + reset --hard origin/main` (which is a checkout
  refresh, not a PR mutation). The Phase 2 dry-run module
  reads on-disk upstream artefacts (N5a / A22 /
  github_pr_lifecycle) and writes only its own audit artefacts
  under `logs/n5b_merge_execution/`.
* **No runtime authority for live merge.** The Phase 1
  projector and Phase 2 dry-run module grant ADE no capability
  to merge, approve, reject, deploy, or trade. Live merge
  authority remains reserved for Phase 3+ and is not granted by
  the Phase 2 implementation.
* **No UI action exists.** The PWA's `/agent-control/*` surface
  must not render a merge / approve / reject / deploy button
  pointed at any N5b endpoint.
* **Phase 3 and Phase 4 and any live merge execution require
  separate explicit operator-go.** The B2.8a–B2.8e operator-go
  phrases authorised Phase 2 dry-run sub-units only. The
  operator-applied `dashboard/dashboard.py` wiring patch for the
  Phase 2 dry-run module is itself a distinct follow-up commit,
  **NOT given by the B2.8e PR**. Each future phase must obtain
  its own explicit operator-go in a separate PR per §10.

The companion pin-tests in
[`tests/unit/test_n5b_merge_execution_plan.py`](../../tests/unit/test_n5b_merge_execution_plan.py)
and
[`tests/unit/test_development_merge_preflight.py`](../../tests/unit/test_development_merge_preflight.py)
enforce these claims.

---

## 2. Scope

### 2.1 What N5b would eventually cover (if ever approved)

A bounded, operator-confirmed, token-gated **merge adapter** that
takes one specific pull request from "review-recommended" (per
N5a's read-only `recommend_human_merge`) to actually merged on
GitHub, **without** granting any agent autonomous merge authority.

The hypothetical adapter, if ever built, would:

* operate exclusively on a single PR per invocation, identified
  by an exact PR number and head SHA bound into an N4b approval
  token;
* require an explicit operator confirmation moment at execution
  time, in addition to the operator's earlier mint of the token;
* default to dry-run; live execution would require a separate
  confirmation flag and operator-go;
* never auto-trigger a deploy (deploy coupling is forbidden —
  see §8);
* write an immutable audit envelope before *and* after every
  decision boundary;
* refuse to operate when any §7 stop condition is true.

### 2.2 What N5b explicitly does not cover

* **Autonomous merge.** Forbidden. No code path may merge a PR
  without the exact operator confirmation moments described in
  §3 and §10.
* **Bulk / batch merge.** Forbidden. One PR per invocation.
* **Self-approval.** Forbidden. The CI surface that runs the
  Fast pre-merge gate must not approve or merge the PR whose
  gate it is.
* **Merge-then-deploy coupling.** Forbidden. The merge adapter,
  if ever built, must terminate before the deploy workflow's
  `workflow_run` trigger fires. Deploy is a separate operator
  surface (see `docs/governance/vps_deploy.md`).
* **Merge of any branch other than into `main`.** Forbidden. The
  only accepted base ref is `main`.
* **Merge under elevated privileges.** Forbidden. No
  `--admin` flag, no branch-protection bypass.
* **Generated-seed coupling.** A18b
  (`generated_seed.jsonl` writer) must not be triggered by
  any N5b code path. The two slices are independent and remain
  independently gated.
* **Trading-side authority.** N5b is a development-governance
  surface only. It never touches `live/**`, `paper/**`,
  `shadow/**`, `risk/**`, `broker/**`, `execution/**`,
  `research/**`, or any agent / strategy / portfolio module.

---

## 3. Preconditions for any future N5b implementation

Every one of these must be true at the moment N5b would execute a
real merge. Any false value is a hard stop (§7).

| # | Precondition | How it is verified |
|---|---|---|
| 1 | **N4b Phase B activated by operator** | `is_configured()` returns True on the VPS; secret was generated and exported per `docs/governance/n4b_runtime_activation.md`. |
| 2 | **Operator UI for token mint/verify exists** (N4c or equivalent) | The operator can mint a token *in the PWA* (rather than via curl) so the mint flow has a documented, auditable interaction surface. |
| 3 | **Token bound to PR number** | The token's `pr_number` claim equals the PR the adapter is about to operate on. |
| 4 | **Token bound to head SHA** | The token's `pr_head_sha` claim equals the PR's current `head_sha` *at execution time* (not just at mint time). |
| 5 | **Token bound to evidence_hash** | The token's `evidence_hash` claim equals the hash of the N5a recommendation row plus PR-state digest used at mint time. |
| 6 | **Token bound to intent** | The token's `intent` claim equals `mobile_approval_dispatch`. |
| 7 | **Token bound to nonce** | The token carries a unique nonce; the runtime's seen-nonce store does not yet contain it. |
| 8 | **N5a read-only recommendation says eligible** | `recommendation_action == "recommend_human_merge"` and `recommendation_reason == "pr_clean_and_no_blocking_inbox"` for the bound PR. |
| 9 | **mergeStateStatus = CLEAN** | The PR's GitHub mergeable state is `CLEAN`. Anything else (`BLOCKED`, `DIRTY`, `BEHIND`, `UNSTABLE`, `HAS_HOOKS`, `UNKNOWN`) is a stop. |
| 10 | **All required checks green** | Every check name listed in branch protection has a `success` conclusion for the head SHA. |
| 11 | **Current head SHA equals token-bound head SHA at execution time** | The PR has not advanced between mint and execution. |
| 12 | **Exact base branch is `main`** | The PR's `base_ref` is `main`. No other base is accepted. |
| 13 | **No stale PR state** | The N5a recommendation snapshot's `generated_at_utc` is within a bounded freshness window (e.g. ≤ 60 minutes; exact value pinned in the future implementation's tests). |
| 14 | **No unresolved critical inbox rows** | The mobile-approval-inbox snapshot's `counts.critical_attention == 0` for the bound PR. |
| 15 | **No protected-path violations** | The PR's file list contains no `.claude/**`, no `.gitleaks.toml`, no `live/`, `paper/`, `shadow/`, `risk/`, `broker/`, `execution/`, `research/`, no `seed.jsonl`, no `generated_seed.jsonl`. |
| 16 | **No Step 5 or Level 6 bypass** (Level 6 stays permanently disabled per ADR-015) | The PR does not change `step5_implementation_allowed`, does not change `STEP5_ENABLED_SUBSTAGE`, does not introduce a Level 6 capability marker — Level 6 is permanently disabled. |
| 17 | **Operator confirmation re-issued at execution time** | A second confirmation, distinct from the mint, is captured immediately before the merge call. |

Any precondition that becomes false between verification and the
actual `gh pr merge` call must abort the execution with no
mutation performed.

---

## 4. Proposed future architecture

> Every paragraph in this section is descriptive of a
> *hypothetical* future system. No code is added by this PR.

### 4.1 Read-only recommendation stays separate from execution

A23 / N5a remain the **recommendation surface**: they project
PR-lifecycle + inbox into a closed-vocabulary
`recommendation_action` and `recommendation_reason`. They never
take action.

The hypothetical N5b adapter would *read* the N5a artefact, never
*write* it. The recommendation surface and the execution surface
must remain in separate Python modules with separate test
suites, separate audit artefacts, and a one-way data flow
recommendation → adapter (never the reverse).

### 4.2 Execution adapter is operator-gated

A future N5b adapter, if approved, would:

* live in a new module under `dashboard/api_*` (the exact name
  pinned by the future implementation's own pin-test);
* register exactly one POST route — `dry_run` — and exactly one
  POST route — `execute` — both session-protected and
  token-gated by N4b;
* refuse to run unless the token verifies green per N4b and
  every §3 precondition holds;
* never expose an idempotent `safe to re-run` path: each
  invocation either succeeds (the PR is now merged or
  dry-run-evaluated) or fails with a precise stop-condition
  envelope. Operator must re-mint to retry.

### 4.3 Token verification = claim-only + nonce recording

The future adapter consumes the existing N4b
`approval_token_runtime.verify_runtime(...)` result. Verification
remains **claim-only** — the adapter does not infer any merge
authorisation from a green verify response. The adapter must
independently re-check every §3 precondition before calling the
GitHub merge API.

The nonce is recorded in the N4b seen-nonce store *before* the
GitHub merge call. A second attempt with the same token is
rejected with `replay_detected` — even if the first attempt
crashed mid-flight (the merge call must be the last operation;
replay-after-crash means the PR may or may not have merged, and
the operator inspects GitHub directly).

### 4.4 Merge adapter is "small, isolated, strict-allowlist"

The future adapter's allowlist would explicitly enumerate every
permitted operation: a single `gh pr merge --squash --delete-branch`
invocation against a single PR number on a single base branch.
Everything else is forbidden by the adapter's own AST-level
forbidden-import scan, source-text scan, and unit-test pin.

### 4.5 All mutation is auditable

Every decision boundary writes an immutable JSON artefact
(closed schema, redacted) to a write-prefix-protected log path
under `logs/n5b_merge_execution/` (the exact path pinned by the
future implementation's test). The artefact records
`pr_number`, `head_sha`, `mergeStateStatus`, `check_summary`,
`token_kid`, `nonce_hash`, `operator_actor`, timestamps, and the
stop condition (if any). Secret material is never written.

---

## 5. API shape

The N5b API surfaces below. **Exactly one merge-execution route
exists, and it is the dry-run route** — the module is on disk,
landed by the B2.8a-through-B2.8e sub-units per
[`n5b_phase2_implementation_plan.md`](n5b_phase2_implementation_plan.md).
The blueprint is **NOT** registered in
[`dashboard/dashboard.py`](../../dashboard/dashboard.py); no HTTP
client can reach the route until the operator applies the 2-line
wiring patch separately (B2.0c precedent).

* **`POST /api/agent-control/merge-execution/dry-run`** —
  **Module implemented locally; dashboard wiring pending
  operator-applied patch**, as
  [`dashboard/api_merge_execution_dry_run.py`](../../dashboard/api_merge_execution_dry_run.py).
  Session-protected, N4b-token-gated. Accepts the token + bound
  PR number + head SHA + evidence_hash + intent. Walks all §3
  preconditions 1–17 from on-disk upstream artefacts
  (`logs/development_merge_recommendation/latest.json`,
  `logs/development_pr_lifecycle_observer/latest.json`,
  `logs/github_pr_lifecycle/latest.json`). Returns a decision
  envelope (`status` ∈ {`ok`, `rejected`, `configuration_missing`,
  `not_yet_implemented`}). Writes preflight + dry_run +
  history artefacts under `logs/n5b_merge_execution/`. NEVER
  calls GitHub mutation APIs, NEVER mints a token, NEVER
  triggers deploy. On `status="ok"` the response means
  *"dry-run checks passed and audit artefacts written"* — not
  *"merge executed"*. **The `would_proceed=true` field is a
  dry-run-only proceed signal — it means *"all 17 §3
  preconditions pass at this moment"*, NOT *"the endpoint is
  about to merge"*, NOT *"the operator is authorised to
  click-through automatic merge"*, NOT live merge authority of
  any kind.** `would_proceed=true` always co-occurs with
  `dry_run_only=true`, `live_merge_implemented=false`,
  `deploy_coupled=false`, and the corresponding test pin
  enforces that co-occurrence in the response envelope. The
  blueprint is **NOT** registered in
  [`dashboard/dashboard.py`](../../dashboard/dashboard.py) by
  the B2.8e PR; the operator applies the 2-line wiring patch
  separately (B2.0c precedent). The wiring patch and the
  corresponding test-pin retirement are an operator-applied
  follow-up commit, **not given by the B2.8e PR**.

* `GET /api/agent-control/merge-execution/status` — **Not
  implemented.** Reserved for a future read-only status surface.
  Adding it requires a separate operator-go.

* `POST /api/agent-control/merge-execution/execute` — **Not
  implemented.** Reserved for N5b Phase 3 (operator-confirmed
  live merge in test repo / simulated harness) and Phase 4
  (production PR merge). Permanently denied without a separate
  explicit operator-go per §10. Would require the
  `ADE_N5B_LIVE_EXECUTE_ENABLED` env flag and the closed
  permanent-denial set in §11.

The Phase 2 dry-run endpoint has been exercised against the
mocked-upstream test fixture per §6.4 of the sub-plan; the
operator may now apply the wiring patch to activate the route
on the live dashboard.

---

## 6. Required audit artifacts

Every decision boundary in a future implementation writes one of
the artefact types below to a closed write-prefix path under
`logs/n5b_merge_execution/`. The schemas below are prose sketches
— no code is added in this PR.

### 6.1 Preflight artefact

Written before any GitHub API read against the bound PR. Captures
the preflight intent and the bound PR identity.

Fields (closed; future implementation's test must pin the exact
set):

* `report_kind = "n5b_preflight"`
* `pr_number` — int
* `pr_head_sha` — string (the token-bound head SHA)
* `pr_base_ref` — string (must equal `main`)
* `intent` — string (must equal `mobile_approval_dispatch`)
* `token_kid` — string
* `nonce_hash` — string (hash of the nonce; never the raw nonce
  in case the artefact is ever exposed)
* `operator_actor` — string (`session` or `operator_token`)
* `generated_at_utc` — ISO 8601
* `step5_implementation_allowed = false`
* `step5_enabled_substage = "none"`
* `discipline_invariants` — closed dict matching the existing
  N5a pattern (`calls_gh_cli`, `merges_or_deploys`,
  `mints_approval_token`, etc., **set per actual capability** —
  the preflight only reads, so `merges_or_deploys = false`).

### 6.2 Dry-run artefact

Written by the dry-run endpoint. Captures the result of every §3
precondition.

* `report_kind = "n5b_dry_run"`
* every field from the preflight artefact, plus:
* `preconditions` — closed dict, one boolean per §3 row.
* `recommendation_action_seen` — string from N5a artefact.
* `recommendation_reason_seen` — string from N5a artefact.
* `merge_state_status_seen` — string from the GitHub API read.
* `required_checks_summary` — closed dict
  `{check_name: conclusion}` for every check listed in branch
  protection.
* `protected_path_violations` — list of file paths (empty when
  clean).
* `would_proceed` — boolean (True iff every precondition is True).
* `stop_condition` — string from §7's closed vocabulary, or
  `null` when `would_proceed = True`.

### 6.3 Decision artefact

Written at the boundary where the future adapter decides to call
the merge API. Captures the final precondition snapshot used.

* `report_kind = "n5b_decision"`
* every field from the dry-run artefact.
* `operator_confirmation_marker` — closed-vocab string (e.g.
  `"second_confirmation_received"`) that proves the operator
  reaffirmed the merge after the dry-run.
* `head_sha_at_decision` — string (must equal `pr_head_sha`).

### 6.4 Execution artefact

Written **only** if §10 Phase 4 ever ships, and **only** by the
live execute endpoint.

* `report_kind = "n5b_execution"`
* every field from the decision artefact.
* `merge_method` — string (must equal `squash`).
* `delete_branch` — boolean (must equal `true`).
* `merge_response_status_code` — int (the HTTP status of the
  merge call).
* `merge_response_classification` — string from a closed vocab
  (`"merged_ok"`, `"merged_with_warnings"`, `"refused_by_github"`,
  `"network_uncertain"`).
* `post_merge_head_sha` — string (the SHA of `main` after the
  merge).

### 6.5 Failure artefact

Written when any stop condition triggers.

* `report_kind = "n5b_failure"`
* every field from the preflight artefact, plus:
* `stop_condition` — string from §7's closed vocabulary.
* `stop_reason` — bounded free-text human-readable explanation
  (redacted; never contains the token).

### 6.6 Common rules across all artefact kinds

* All schemas are closed and exact.
* Every artefact is validated against
  `reporting.agent_audit_summary.assert_no_secrets()` before
  write.
* No raw token, no HMAC secret, no PEM block, no VPS IP, no
  bearer header value, no PAT, no `ghp_` prefix.
* Atomic write via tmp + `os.replace`.
* Write-prefix sentinel restricts the write path to
  `logs/n5b_merge_execution/...`.
* Every artefact carries the Step 5 invariants and the closed
  `discipline_invariants` dict.

---

## 7. Stop conditions

The future adapter must abort, write a failure artefact (§6.5),
and return a closed-envelope rejection when any of the following
are detected. The strings below are the closed-vocab
`stop_condition` values the failure artefact must use.

| stop_condition | Trigger |
|---|---|
| `token_missing` | request body did not supply the token |
| `token_invalid` | N4b verify returned anything other than `outcome == "ok"` |
| `replay_detected` | N4b verify returned `outcome == "replay_detected"` |
| `binding_mismatch` | the token's claims do not match the body bindings (PR number, head SHA, evidence hash, intent, base ref) |
| `pr_number_mismatch` | the body's `pr_number` and the token's `pr_number` disagree |
| `head_sha_mismatch` | the current GitHub head SHA differs from the token-bound head SHA |
| `merge_state_not_clean` | the PR's `mergeStateStatus` is not `CLEAN` |
| `checks_not_green` | any required check is not `success` |
| `branch_protection_not_satisfied` | branch protection's required reviews / linear-history / signed-commits rule is unsatisfied |
| `unexpected_files_touched` | the PR's file list includes a §3.15 protected path |
| `deploy_coupling_detected` | the PR's diff includes a change to the deploy workflow or deploy script in a way that would couple this merge to a deploy |
| `step5_flag_changed` | the PR diff changes `step5_implementation_allowed` or `STEP5_ENABLED_SUBSTAGE` |
| `level_6_attempted` | the PR diff introduces a Level 6 capability marker (Level 6 is permanently disabled; ADR-015 forbids any such marker) |
| `protected_path_violation` | the PR touches any of the no-touch paths |
| `stale_recommendation` | the N5a artefact is older than the freshness window |
| `network_uncertain` | GitHub API responded with a 5xx, a 4xx that the adapter is not coded to translate, or the call timed out |
| `audit_write_failure` | the preflight or decision artefact failed to write atomically |
| `operator_confirmation_missing` | the second operator confirmation marker is not present at decision time |
| `live_execute_disabled` | the env flag `ADE_N5B_LIVE_EXECUTE_ENABLED` is not `true` and the request hit the live execute endpoint |
| `dry_run_required_first` | per §10, the bound PR has no prior `n5b_dry_run` artefact within the freshness window |

The closed list above is the **only** set of stop conditions the
future adapter must emit. Adding a new stop condition requires a
new PR that updates this doc and the future implementation's
test in the same commit.

---

## 8. Security boundaries

### 8.1 No secrets in logs

* The HMAC secret is never logged, printed, echoed, or persisted
  outside the VPS env. The runtime is already constrained by
  `reporting.approval_token_runtime` and
  `docs/governance/n4b_runtime_activation.md`.
* The raw token string is never persisted to disk. Only the
  `nonce_hash` (a hash of the nonce, not the nonce itself) is
  written to audit artefacts.

### 8.2 No token in URL

The token is carried in the request body of the POST endpoints.
It never appears in a query string, a path segment, a redirect
location, or any cookie set by the adapter.

### 8.3 No token in persisted public artifacts

The N5a recommendation snapshot, the operational digest, the
workloop runtime artifact, and every other read-only artefact
the dashboard / PWA serves must not include token material.

### 8.4 No branch protection bypass

* The adapter must call `gh pr merge` (or the equivalent
  authenticated GitHub API path) **without** the `--admin` flag.
* The adapter's token must not carry `admin:org` or
  `admin:repo_hook` scopes.
* If the configured token cannot satisfy branch protection, the
  merge call fails with the GitHub error and the failure
  artefact records `branch_protection_not_satisfied`.

### 8.5 No admin token

The credentials used by the adapter must be a fine-grained
GitHub PAT or a GitHub App installation token with **only** the
minimum scopes required to merge a PR (`pull_requests:write`).
No `admin:*` scope. No write access to org settings, secrets,
or workflows.

### 8.6 No PAT committed

No PAT, deploy token, or GitHub-App private key is ever
committed to the repository. The token (when activated) lives
only in the VPS env, exported by the operator per the same
mechanism used for `ADE_APPROVAL_TOKEN_HMAC_SECRET` (see N4b
runbook).

### 8.7 No `gh auth setup` in repo

The repository contains no `gh auth login`, no `gh auth setup-git`,
no encoded credentials in `.gh/`, no `.netrc` file. The future
adapter does not bundle credentials; it reads them at runtime
from the VPS env.

### 8.8 No deploy key reuse

The SSH deploy key used by the VPS dashboard auto-deploy workflow
(`VPS_SSH_PRIVATE_KEY` in GitHub Secrets, public half in the VPS
`authorized_keys`) is dedicated to deploying. It must never be
reused as a merge-authority credential. The merge adapter, if
ever built, uses a separate GitHub credential at the VPS env
layer.

### 8.9 No CI self-approval

The GitHub Actions identity that runs the Fast pre-merge gate
must not approve or merge the PR whose gate it is. The merge
adapter, if ever built, must run on the VPS (operator-paced),
not in CI.

### 8.10 No automatic loop from recommendation to merge

There must be no scheduled job, cron, recurring-maintenance
refresher, or queue projector that calls the future merge
endpoint without an operator-mediated step in between. The
operator is the only path from `recommend_human_merge` to an
actual merge.

---

## 9. Testing requirements for any future implementation

Every future PR that introduces N5b runtime code must ship the
following tests in the *same* PR, all failing-closed.

### 9.1 Unit tests
* Every §7 stop condition reproduces deterministically.
* Every §3 precondition has both a happy-path and a failing-path
  test.
* The decision-verb call shapes (the patterns this doc's pin-test
  forbids in production code) appear nowhere outside the
  adapter module — pinned by the same source-text scan.

### 9.2 Integration tests with mocked GitHub
* The adapter is exercised end-to-end against a mocked GitHub
  API. The mock returns canonical `CLEAN`, `DIRTY`, `BLOCKED`,
  `UNSTABLE`, `BEHIND`, and `UNKNOWN` `mergeStateStatus` values;
  the adapter responds correctly to each.
* The mock returns each of the canonical check conclusions
  (`success`, `failure`, `cancelled`, `skipped`,
  `in_progress`, `null`); the adapter accepts only `success`.

### 9.3 Source scans
* No `subprocess.run`, `subprocess.Popen`, or equivalent appears
  outside the adapter module.
* No `gh ` shell-out string appears outside the adapter module.
* No git-merge invocation appears in non-adapter production code.
* No new decision-verb call shape (the closed list the
  pin-tests enforce) appears outside the adapter module.

### 9.4 Branch protection invariants
* A test fixture creates a PR with branch protection set to
  require specific checks; the adapter is asked to merge it
  before those checks pass; the adapter refuses with
  `branch_protection_not_satisfied`.

### 9.5 Replay / binding tests
* The same token verifies once and is rejected on the second
  attempt with `replay_detected`.
* Binding drift in each of the five claim dimensions
  (pr_number, pr_head_sha, evidence_hash, intent, release_tag)
  is independently exercised and produces `binding_mismatch`.

### 9.6 Dry-run-default tests
* A request to the live execute endpoint without the
  `ADE_N5B_LIVE_EXECUTE_ENABLED` env flag is rejected with
  `live_execute_disabled`.
* A request to the live execute endpoint with the env flag
  set but no prior dry-run for the bound PR within the
  freshness window is rejected with `dry_run_required_first`.

### 9.7 Audit redaction tests
* Every artefact written by the adapter is passed through
  `assert_no_secrets`; a tampered fixture that injects a
  token-shaped string into an artefact field is detected and
  fails the test.

### 9.8 Negative tests for every stop condition
* For each row in §7, a unit test reproduces the trigger and
  asserts the closed-vocab `stop_condition` value is recorded
  in the failure artefact.

---

## 10. Rollout plan

| Phase | Status | What ships | Mutates production? | Operator-go needed? |
|---|---|---|---|---|
| **0 — Plan only** | **Implemented** | This doc + pin-tests. | No. | Already given for Phase 0. |
| **1 — Dry-run preflight only** | **Implemented (read-only)** | The preflight artefact writer (`reporting/development_merge_preflight.py`) emitting `logs/development_merge_preflight/latest.json`. No dashboard endpoint, no token gate, no GitHub call. | No. | Already given for Phase 1 alone. Future phases are NOT authorised by this go. |
| **2 — Token-bound dry-run** | **Module implemented locally (dry-run only); dashboard wiring pending operator-applied patch (blueprint UNWIRED in `dashboard/dashboard.py`)** | The dry-run route module at `POST /api/agent-control/merge-execution/dry-run` is implemented in [`dashboard/api_merge_execution_dry_run.py`](../../dashboard/api_merge_execution_dry_run.py), token-gated by N4b. Walks all §3 preconditions 1–17 from on-disk upstream artefacts; writes preflight + dry_run + history + failure artefacts under `logs/n5b_merge_execution/`. The blueprint is **NOT** registered in [`dashboard/dashboard.py`](../../dashboard/dashboard.py) by the B2.8e PR — it stays **UNWIRED** until the operator applies the 2-line wiring patch separately (B2.0c precedent); no HTTP client can reach the route in the meantime. On `status="ok"` and `would_proceed=true` the endpoint signals *"dry-run checks passed and audit artefacts written"* — never *"merge executed"*, *"PR mutated"*, *"deploy triggered"*, or *"live execution authorized"*. | No (dry-run only; no PR mutation). | Sub-unit operator-go phrases given on each of B2.8a–B2.8e PRs; the operator-applied `dashboard/dashboard.py` wiring patch is **NOT given by the B2.8e PR** — a distinct follow-up commit. |
| **3 — Operator-confirmed live merge in test repo / simulated harness** | Not implemented | The live execute endpoint, but pointed at a sacrificial test repository OR a recorded-fixture simulator. No production PR is touched. | No (production PRs are not touched). | **Yes — separate explicit operator-go required**. Phase 2 must be merged + observed clean. |
| **4 — Production PR merge, if ever approved** | Not implemented | The live execute endpoint pointed at the production repository, with the `ADE_N5B_LIVE_EXECUTE_ENABLED` env flag required. | Yes (a single PR per invocation). | **Yes — distinct, explicit operator-go phrase required**, recorded by name in the operator runbook update that ships with Phase 4. |

**Each phase requires:**

* a separate PR;
* an explicit operator-go in the issue / PR description (no
  implicit promotion);
* an updated §5 / §10 of this doc to reflect "Implemented:
  Phase N" (the doc itself is the canonical phase marker);
* the previous phase to have been merged AND deployed AND
  observed clean for a bounded period before promotion.

---

## 11. Permanent denials

The following are denied **permanently** in any current or future
N5b implementation. Any code path that introduces them must be
rejected by an existing or newly-added pin-test in the same PR.

* **No Level 6.** Per ADR-015 §Doctrine 1, Level 6 is permanently
  disabled. N5b must not raise the autonomy ladder ceiling.
* **No autonomous merge.** Every merge requires the §3 / §10
  operator confirmation moments. There is no "the agent has been
  good for N days, so it can merge now" rule.
* **No autonomous deploy.** The deploy workflow remains coupled
  only to `workflow_run` after the Fast pre-merge gate succeeds
  on main, and to operator-initiated `workflow_dispatch`. The
  merge adapter must terminate before the deploy workflow
  triggers; the merge adapter must never invoke the deploy
  workflow directly.
* **No autonomous trading.** N5b is a development-governance
  surface; it must not touch `live/**`, `paper/**`, `shadow/**`,
  `risk/**`, `broker/**`, `execution/**`, or `research/**`.
* **No Step 5 enablement.** `step5_implementation_allowed`
  remains `false` and `STEP5_ENABLED_SUBSTAGE` remains `"none"`
  unless a separate operator-authored ADR explicitly enables a
  substage. N5b must not change either flag.
* **No `generated_seed.jsonl` writer coupling.** A18b is
  independently gated and must not be triggered, prepared,
  staged, or implied by any N5b code path.
* **No merge without exact operator confirmation.** Each live
  merge requires a separate operator confirmation marker at
  execution time, distinct from the operator's earlier token
  mint.

---

## 12. Carry-forward

After this PR is merged, the following remain open and **not
authorised** by this PR:

* **N4b Phase B activation** — optional, operator-go required,
  not done in this PR. The repo-side runbook is at
  `docs/governance/n4b_runtime_activation.md`. The VPS env
  export is operator-only.
* **N4c UI for token mint/verify** — future slice after N4b
  Phase B is activated and observed clean. Not done in this PR.
* **N5b implementation** — not done. This PR is plan-only. Any
  implementation requires a separate PR per §10 Phase, with
  explicit operator-go and the full §9 test set.
* **A18b `generated_seed.jsonl` writer** — not authorised. The
  exact operator phrase required to start A18b is:

  ```
  GO A18b generated_seed writer
  ```

  Without that exact phrase from the operator, A18b must not be
  started, scoped, drafted, or stub-implemented.

---

## 13. Phase 2 implementation decomposition (sub-plan reference)

A separate plan-only sub-document decomposes any future N5b
Phase 2 implementation into ordered, auditable sub-units
(B2.8a / B2.8b / B2.8c / B2.8d / B2.8e):

* [`n5b_phase2_implementation_plan.md`](n5b_phase2_implementation_plan.md)

The sub-plan pins the closed contracts (future module path,
future route URL, request body schema, response statuses, audit
artefact paths under `logs/n5b_merge_execution/`) and the hard
preconditions (Phase 1 observed-clean period, N4b Phase B
activation, N4c-or-equivalent mint/verify UI) that **all** must
be true before any runtime code-bearing sub-unit may land.

The sub-plan itself adds **no runtime code**. The status table
in §5 of this parent doc remains "Phase 2 — Not implemented"
until B2.8e completes; only B2.8e is authorised to update the
status row.

---

## Cross-references

* `docs/governance/development_merge_recommendation.md` — N5a
  read-only merge recommendation projector (the upstream of any
  future N5b adapter).
* `docs/governance/approval_token_gate.md` — N4a pure callable
  mint/verify contract.
* `docs/governance/n4b_runtime_activation.md` — N4b runtime
  activation runbook (operator VPS step).
* `docs/governance/vps_deploy.md` — deploy workflow + script
  (the deploy surface N5b must remain decoupled from).
* `docs/governance/development_generated_lane.md` — A18a
  dry-run generated-queue-lane projector (the report-only
  precursor whose writer counterpart A18b remains forbidden).
* `docs/adr/ADR-014-truth-authority-settlement.md` — authority
  doctrine (which subsystem owns truth for each domain).
* `docs/adr/ADR-015-claude-agent-governance.md` — Level 6
  permanently-disabled doctrine; autonomy-ladder
  authority chain.
* `docs/governance/execution_authority.md` — per-action authority
  decisions and the "operator-only" markers N5b adapter must
  carry.
* `docs/governance/no_touch_paths.md` — the protected paths the
  adapter must refuse to allow inside a PR's diff.
