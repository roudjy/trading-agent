# N5b Phase 1 — Merge Preflight Upstream-Refresh Operator Runbook

> **Status:** Operator-facing runbook for the **read-only** N5b
> Phase 1 dry-run preflight projector
> ([`reporting/development_merge_preflight.py`](../../reporting/development_merge_preflight.py)).
>
> **Authority:** development-governance read-only documentation.
> This runbook grants ADE **zero** new authority. It documents the
> exact, dry-run-only CLI sequence the operator runs to refresh the
> chain of upstream artefacts the N5b Phase 1 projector reads, so
> that the preflight artefact stops reporting `candidate_count = 0`
> when there is, in fact, mergeable PR state to project.
>
> **Permanent denials (re-asserted):**
>
> * `step5_implementation_allowed = false` (unchanged)
> * `STEP5_ENABLED_SUBSTAGE = "none"` (unchanged)
> * Level 6 is permanently disabled per ADR-015 §Doctrine 1.
> * No autonomous merge / deploy / trade / approval.
> * No approval can happen from a notification click alone.
> * No `gh pr merge`, no `gh pr review --approve`, no `--admin`, no
>   branch-protection bypass, no force push, no
>   `seed.jsonl` / `generated_seed.jsonl` write, no `.claude/**`
>   edit, no `.gitleaks.toml` edit, no test weakening, no hook
>   bypass.
> * No `ADE_GENERATED_LANE_WRITER_ENABLED=true` is requested by
>   this runbook (that is A18b runtime activation territory and is
>   a separate operator-only step gated behind a separate
>   operator-go).
> * No `ADE_N5B_LIVE_EXECUTE_ENABLED=true` is requested by this
>   runbook (that is N5b Phase 4 territory and is permanently
>   denied until a separate explicit operator-go per
>   [`docs/governance/n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
>   §10).

---

## 1. Purpose

The N5b Phase 1 projector at
[`reporting/development_merge_preflight.py`](../../reporting/development_merge_preflight.py)
emits a closed-schema dry-run preflight artefact at
`logs/development_merge_preflight/latest.json` by joining two
existing read-only artefacts:

* **A22** — `logs/development_pr_lifecycle_observer/latest.json`
* **A23 / N5a** — `logs/development_merge_recommendation/latest.json`

A23 itself is a pure projector over **A22 + N3a**, where N3a is
the mobile-approval-inbox artefact at
`logs/mobile_approval_inbox/latest.json`. A22 in turn projects the
upstream GitHub-PR-lifecycle digest at
`logs/github_pr_lifecycle/latest.json`, which is the **only**
artefact in the chain whose producer calls `gh` (a subprocess +
network step).

If any link in this chain is absent, malformed, or stale, the N5b
Phase 1 projector default-denies and reports `candidate_count = 0`
with a closed-vocab warning. That is **safe** but **not useful**.
This runbook documents the exact dry-run-only CLI commands the
operator can run, in order, to refresh the chain on the VPS (or
locally) so the Phase 1 projector has fresh material to project.

This runbook is **not** an authorisation to ship Phase 2+. Each
Phase 2 / 3 / 4 of the N5b rollout plan
([`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md) §10)
requires its own separate explicit operator-go, in a separate PR,
with the full §9 test set.

---

## 2. Hard constraints

This runbook, the surfaces it documents, and the commands it
prescribes must not:

* merge any PR;
* push to `main` or force-push any branch;
* call `gh pr merge`, `gh pr review --approve`, or any other
  GitHub mutation outside the existing audited Dependabot
  execute-safe path (which is **not** invoked by this runbook);
* call `git merge` against `main`, `git push`, or any equivalent
  mutating Git operation;
* mint or verify approval tokens (N4 territory; preflight is
  pre-token);
* execute an approve / reject decision (N4 + N5 execution
  territory);
* deploy anything;
* send any real push notification (N2b–N3b territory);
* register a Flask blueprint or wire into `dashboard/dashboard.py`;
* touch `frontend/**`;
* mutate any upstream artefact (the projectors write only their
  own artefact path; the upstream is **read** by every step);
* edit canonical roadmap status fields;
* mark any roadmap phase complete;
* enable Step 5.1 or Step 5.2;
* flip `step5_implementation_allowed`;
* change `STEP5_ENABLED_SUBSTAGE`;
* enable Level 6 (Level 6 is permanently disabled per ADR-015 §Doctrine 1);
* change QRE behaviour;
* mutate research artifacts;
* touch live / paper / shadow / risk / broker / execution paths;
* edit `.claude/**`;
* edit `.gitleaks.toml`;
* weaken or bypass tests, hooks, gates, or pin-tests;
* write a `seed.jsonl` or `generated_seed.jsonl` record (A18b
  writer is a separate runtime that is **not** invoked by this
  runbook);
* store secrets in repo.

---

## 3. The refresh chain (read-only)

| Step | Module | Reads | Writes | Calls `gh` / net / subprocess? |
|---|---|---|---|---|
| 1 | [`reporting.github_pr_lifecycle`](../../reporting/github_pr_lifecycle.py) | `gh` GraphQL | `logs/github_pr_lifecycle/latest.json` | **Yes (`gh` CLI + subprocess).** Already invoked by `scripts/deploy_vps_dashboard.sh` post-deploy and by `reporting.recurring_maintenance` job `refresh_github_pr_lifecycle_dry_run`. |
| 2 | [`reporting.development_pr_lifecycle_observer`](../../reporting/development_pr_lifecycle_observer.py) (A22) | step 1's artefact | `logs/development_pr_lifecycle_observer/latest.json` | No. Pure stdlib projector. |
| 3 | [`reporting.mobile_approval_inbox`](../../reporting/mobile_approval_inbox.py) (N3a) | notification dispatch outbox | `logs/mobile_approval_inbox/latest.json` | No. Pure stdlib projector. |
| 4 | [`reporting.development_merge_recommendation`](../../reporting/development_merge_recommendation.py) (A23) | A22 + N3a | `logs/development_merge_recommendation/latest.json` | No. Pure stdlib projector. |
| 5 | [`reporting.development_merge_preflight`](../../reporting/development_merge_preflight.py) (N5b Phase 1) | A22 + A23 | `logs/development_merge_preflight/latest.json` | No. Pure stdlib projector. |

**Only step 1 talks to the network.** Steps 2–5 are pinned by
their own AST-level forbidden-import and source-text scans to
contain no `subprocess`, no `socket`, no `urllib`, no `requests`,
no `httpx`, no `aiohttp`, no `gh`, no `git`. The projectors are
deterministic functions of their on-disk inputs.

---

## 4. Operator workflow — VPS

Run the chain in order. Every step is dry-run only and writes
only its own artefact path. Any failure on a downstream step is
non-fatal for upstream steps (the file simply does not refresh on
that pass).

```sh
cd /root/trading-agent

# Step 1 — refresh the upstream gh digest (subprocess + gh).
#          Skipped here if a recent post-deploy / recurring tick
#          has already refreshed it; safe to re-run.
python3 -m reporting.github_pr_lifecycle --mode dry-run --no-smoke

# Step 2 — A22 read-only projector. No gh, no network.
python3 -m reporting.development_pr_lifecycle_observer

# Step 3 — N3a inbox read-only projector. No gh, no network.
python3 -m reporting.mobile_approval_inbox

# Step 4 — A23 read-only recommendation projector. No gh, no network.
python3 -m reporting.development_merge_recommendation

# Step 5 — N5b Phase 1 read-only preflight projector. No gh, no network.
python3 -m reporting.development_merge_preflight --no-write
```

The final `--no-write` invocation prints the snapshot to stdout
without persisting it. Drop `--no-write` to also persist
`logs/development_merge_preflight/latest.json`. Both shapes are
safe; neither calls `gh` or the network.

### 4.1 Expected closed-envelope shape from step 5

```jsonc
{
  "dry_run_only": true,
  "live_merge_implemented": false,
  "deploy_coupled": false,
  "level6_enabled": false,
  "step5_implementation_allowed": false,
  "step5_enabled_substage": "none",
  "candidate_count": <int>,
  "candidates": [ ... ],
  "validation_warnings": [ ... ],
  "note": "candidates_present" | "missing_merge_recommendation_artifact" | "missing_pr_lifecycle_artifact" | "no_recommendation_rows"
}
```

`candidate_count` may legitimately be `0` even after a clean
chain refresh — the universe of open PRs may simply not contain
any A23 row whose `recommendation_action == "recommend_human_merge"`
at that moment. That is also safe.

### 4.2 Operator verification commands (read-only)

```sh
jq '.dry_run_only,
    .live_merge_implemented,
    .deploy_coupled,
    .level6_enabled,
    .step5_implementation_allowed,
    .step5_enabled_substage,
    .candidate_count,
    .note,
    .validation_warnings' \
   logs/development_merge_preflight/latest.json

# Per-candidate verdict + stop conditions:
jq '.candidates[] | {pr_number, dry_run_verdict, stop_conditions}' \
   logs/development_merge_preflight/latest.json
```

Expected verifications:

* `.dry_run_only == true`
* `.live_merge_implemented == false`
* `.deploy_coupled == false`
* `.level6_enabled == false`
* `.step5_implementation_allowed == false`
* `.step5_enabled_substage == "none"`
* every candidate's `.dry_run_verdict` is one of
  `would_block`, `would_require_operator`,
  `would_be_live_candidate_if_authorized` (closed vocab pinned
  by the projector's tests)
* every candidate's `stop_conditions` includes
  `token_required_for_live` **and** `live_merge_not_implemented`
  (those two are informational reminders the projector emits on
  **every** row — see
  [`development_merge_preflight.py`](../../reporting/development_merge_preflight.py)
  §`_INFORMATIONAL_STOP_CONDITIONS`).

---

## 5. Operator workflow — local dry-run

For a smoke pass without VPS access, run the same chain from the
repo working tree. Step 1 still requires `gh` + GitHub auth in
the local shell; if that is not available, skip step 1 (steps
2–5 will project whatever digest is already on disk under
`logs/github_pr_lifecycle/`, or default-deny if nothing is there
yet).

```sh
# from the repo root, in an activated venv:
python -m reporting.development_pr_lifecycle_observer --no-write
python -m reporting.mobile_approval_inbox --no-write
python -m reporting.development_merge_recommendation --no-write
python -m reporting.development_merge_preflight --no-write
```

`--no-write` is the canonical safety flag; nothing is persisted.
Output is the closed-schema snapshot to stdout.

---

## 6. Stop conditions and safe envelopes

If step 5's snapshot reports:

| `note` | Operator action |
|---|---|
| `missing_merge_recommendation_artifact` | step 4 has not run on this host since step 5; re-run step 4 then step 5. |
| `missing_pr_lifecycle_artifact` | step 2 has not run on this host since step 5; re-run step 2 then step 5. |
| `no_recommendation_rows` | the upstream A22 + A23 projection ran cleanly but no PR satisfies A23's `recommend_human_merge` rule today. Safe; no action. |
| `candidates_present` | step 5 found at least one row to project. Inspect `.candidates[*].dry_run_verdict` and `.candidates[*].stop_conditions`. |

If a `would_block` or `would_require_operator` verdict appears,
the operator can read the closed-vocab `stop_conditions` (e.g.
`merge_state_not_clean`, `checks_not_green`,
`critical_inbox_rows_present`, `stale_recommendation`,
`head_sha_mismatch`, etc.) directly. **No N5b live merge route
exists**; the verdict is informational only.

---

## 7. Rollback

The runbook describes only read-only projector invocations.
"Rollback" means: drop the downstream artefacts. Subsequent runs
of step 5 will then report `missing_*` warnings and
`candidate_count = 0`, which is the canonical safe rest state.

```sh
# Optional safe-rest reset (operator-only). The projectors
# regenerate the files on the next invocation; no other
# subsystem reads these four directories outside the documented
# projector / dashboard read paths.
rm -f logs/development_merge_preflight/latest.json
rm -f logs/development_merge_recommendation/latest.json
rm -f logs/development_pr_lifecycle_observer/latest.json
rm -f logs/mobile_approval_inbox/latest.json
```

This rollback does **not** touch `logs/github_pr_lifecycle/`
(that artefact is consumed by other dashboards and the recurring
maintenance scheduler).

---

## 8. Step 5 and Level 6 invariants

Level 6 is **permanently disabled** per ADR-015 §Doctrine 1 and is
**never** raised by this runbook. The six invariants below are
re-asserted on every line of this runbook:

```
step5_implementation_allowed = false
STEP5_ENABLED_SUBSTAGE        = "none"
level6_enabled                = false
dry_run_only                  = true
live_merge_implemented        = false
deploy_coupled                = false
```

The N5b Phase 1 projector emits these literal values into its
artefact's `discipline_invariants` dict on every snapshot
([`reporting/development_merge_preflight.py`](../../reporting/development_merge_preflight.py)
§`_DISCIPLINE_INVARIANTS`). This runbook does not authorise the
operator to flip any of them. Any future change to those
invariants requires a separate operator-authored ADR and a
separate PR.

---

## 9. What this runbook does NOT do

* Does **not** schedule the refresh. The recurring-maintenance
  scheduler (`reporting.recurring_maintenance`) does **not**
  currently include A22 / N3a / A23 / N5b refresh jobs. A
  separate PR (the planned Task 2 in the operator's task plan)
  may add those jobs in a future change. **No** scheduler change
  is included in this PR.
* Does **not** add a dashboard API surface for the preflight
  artefact. (That is the planned Task 3.)
* Does **not** add a PWA surface for the preflight artefact.
  (That is the planned Task 4.)
* Does **not** activate the A18b
  `generated_seed.jsonl` writer on the VPS. (That is the planned
  Task 5, **operator-only**, and is gated behind a separate
  operator-go.)
* Does **not** introduce N5b Phase 2 (token-bound dry-run
  endpoint), Phase 3 (sacrificial-repo live execute), or Phase 4
  (production live execute). Each of those is denied unless and
  until the operator separately authorises it per
  [`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
  §10.
* Does **not** grant ADE permission to merge any PR, push to
  `main`, force-push, deploy, mint an approval token, verify an
  approval token, send a real push notification, or open / close
  / comment on any PR.

---

## 10. Authority chain summary

| Capability | Today | After this runbook | After Task 2 (future, separate PR) | After N5b Phase 2 (future, operator-go required) | After N5b Phase 4 (future, operator-go required) |
|---|---|---|---|---|---|
| Read step-1 gh digest | yes | unchanged | unchanged | unchanged | unchanged |
| Run step-2 A22 projector on demand | yes (CLI) | yes (documented) | yes (scheduled) | unchanged | unchanged |
| Run step-3 N3a projector on demand | yes (CLI) | yes (documented) | yes (scheduled) | unchanged | unchanged |
| Run step-4 A23 projector on demand | yes (CLI) | yes (documented) | yes (scheduled) | unchanged | unchanged |
| Run step-5 N5b Phase 1 preflight on demand | yes (CLI) | yes (documented) | yes (scheduled) | unchanged | unchanged |
| Mint approval token | does not exist | unchanged | unchanged | yes — operator-env-only via N4b | unchanged |
| Token-bound dry-run merge endpoint | does not exist | unchanged | unchanged | yes — operator-go required | unchanged |
| Live merge of any PR | does not exist | unchanged | unchanged | does not exist | yes — separate operator-go per §10 |
| Autonomous merge / deploy / trade | forbidden (Level 6 disabled) | unchanged | unchanged | unchanged | unchanged |

This runbook grants ADE **zero** new authority. The refresh
chain is information, not authority.

---

## 11. Cross-references

* [`docs/governance/n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md) —
  the N5b governance / plan-only doc; §10 enumerates the four
  rollout phases and re-asserts that each requires a separate
  operator-go.
* [`docs/governance/development_pr_lifecycle_observer.md`](development_pr_lifecycle_observer.md) —
  A22 read-only projector contract.
* [`docs/governance/development_merge_recommendation.md`](development_merge_recommendation.md) —
  A23 read-only recommendation projector contract.
* [`docs/governance/recurring_maintenance.md`](recurring_maintenance.md) —
  the typed scheduler that today refreshes step 1 (and not the
  downstream chain).
* [`docs/governance/vps_deploy.md`](vps_deploy.md) — the deploy
  surface; the post-deploy hook refreshes step 1 only.
* [`docs/governance/n4b_runtime_activation.md`](n4b_runtime_activation.md) —
  the operator-only runbook for N4b Phase B activation.
* [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md) —
  authority doctrine.
* [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md) —
  Level 6 permanently-disabled doctrine.
* [`docs/governance/execution_authority.md`](execution_authority.md) —
  per-action authority decisions.
* [`docs/governance/no_touch_paths.md`](no_touch_paths.md) — the
  protected paths.
