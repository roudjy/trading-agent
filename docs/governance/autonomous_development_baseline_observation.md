# Autonomous Development Lane — Baseline Observation Runbook

> **Status:** Operator-facing observation runbook for the
> autonomous-development-lane safe rest state. Phase 0 of the
> autonomous-development-lane phased plan.
>
> **Authority:** development-governance read-only documentation.
> This runbook grants ADE **zero** new authority. It documents the
> exact dry-run-only CLI sequence the operator runs on the VPS (or
> locally) to confirm that every component of the
> autonomous-development lane is at its documented safe rest state
> before a later phase is allowed to start.
>
> **Permanent denials (re-asserted):**
>
> * `step5_implementation_allowed = false` (unchanged)
> * `STEP5_ENABLED_SUBSTAGE = "none"` (unchanged)
> * Level 6 is permanently disabled per ADR-015 §Doctrine 1.
> * No autonomous merge / deploy / trade / approval.
> * No approval can happen from a notification click alone.
> * No `gh pr merge`, no `gh pr review --approve`, no `--admin`,
>   no branch-protection bypass, no force push, no
>   `seed.jsonl` / `generated_seed.jsonl` write, no `.claude/**`
>   edit, no `.gitleaks.toml` edit, no test weakening, no hook
>   bypass.
> * No `ADE_GENERATED_LANE_WRITER_ENABLED=true` export is
>   requested by this runbook. The A18b runtime activation is a
>   separate operator-only step gated behind the explicit
>   operator-go phrase
>   `GO enable A18b writer on VPS` (Phase 1 of the plan).
> * No `ADE_N5B_LIVE_EXECUTE_ENABLED=true` export is requested by
>   this runbook. N5b Phase 4 production merge requires its own
>   distinct high-risk operator-go.
> * No A18c admission integration is documented here; A18c remains
>   plan-only, gated by `GO A18c plan-only`.

---

## 1. Purpose

Phase 0 of the autonomous-development-lane plan is the **baseline
observation / safety inventory** step. Its purpose is to capture,
in a single durable artefact, the exact closed-vocab values the
operator must observe before any later phase is allowed to start.

The autonomous-development lane spans:

* **A18a** — `reporting.development_generated_lane` dry-run
  candidate projector (read-only).
* **A18b** — `reporting.development_generated_lane_writer` —
  default-disabled append-only writer for `generated_seed.jsonl`.
* **A18c** — admission integration into the A17 queue admission
  policy. **Not implemented.** Plan-only until a separate
  operator-go.
* **N5b Phase 1** — `reporting.development_merge_preflight` —
  dry-run merge-preflight projector (read-only).
* **N5b Phase 2/3/4** — token-bound dry-run / sacrificial-repo
  live merge / production live merge. **Not implemented.** Each
  later phase requires its own distinct operator-go per
  [`docs/governance/n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
  §10.
* **Step 5** — implementation planner / adapter / PR creation
  surfaces. **Not implemented.** Plan-only until a separate
  operator-go.
* **N4b** — approval-token runtime (already Phase B-active on
  VPS, claim-only, no autonomous action).

This runbook tells the operator how to verify that, at the
moment Phase 0 closes, **every** component listed above is at
its documented safe rest state and **no** later phase has
silently started.

This runbook is **not** an authorisation to start any later
phase. Each later phase requires its own explicit operator-go
phrase per the accepted plan.

---

## 2. Hard constraints

This runbook, the commands it prescribes, and any caller acting on
them must not:

* merge any PR;
* push to `main` or force-push any branch;
* call `gh pr merge`, `gh pr review --approve`, or any other
  GitHub mutation;
* call `git merge` against `main`, `git push`, or any equivalent
  mutating Git operation;
* mint or verify approval tokens (Phase 0 is pre-token, pre-N5b);
* execute an approve / reject decision (N4 + N5 execution
  territory);
* deploy anything;
* send any real push notification;
* register a Flask blueprint or wire into
  `dashboard/dashboard.py`;
* touch `frontend/**`;
* mutate any upstream artefact (Phase 0 is read-only by
  construction);
* edit canonical roadmap status fields;
* mark any roadmap phase complete;
* enable Step 5.1 or Step 5.2;
* flip `step5_implementation_allowed`;
* change `STEP5_ENABLED_SUBSTAGE`;
* raise Level 6 (Level 6 is permanently disabled per ADR-015 §Doctrine 1);
* change QRE behaviour;
* mutate research artifacts;
* touch live / paper / shadow / risk / broker / execution paths;
* edit `.claude/**`;
* edit `.gitleaks.toml`;
* weaken or bypass tests, hooks, gates, or pin-tests;
* export `ADE_GENERATED_LANE_WRITER_ENABLED=true`;
* export `ADE_N5B_LIVE_EXECUTE_ENABLED=true`;
* write a `seed.jsonl` or `generated_seed.jsonl` record;
* store secrets in repo.

---

## 3. The baseline observation chain (read-only)

Every command in this section is a dry-run inspection of an
existing component. None of them mutate disk, network, env, or
process state. Each command's expected output is **closed
vocabulary** — anything outside the closed set is treated as a
divergence the operator inspects manually and resolves before
any later phase is allowed to start.

| Step | Subsystem | What is observed | Where the source-of-truth lives |
|---|---|---|---|
| 1 | A18b writer artefact | `generated_seed.jsonl` is absent on disk | `reporting.development_generated_lane_writer.GENERATED_SEED_PATH` → `/root/trading-agent/generated_seed.jsonl` |
| 2 | A18b writer status | writer is default-disabled; `record_count=0`; Step 5 + Level 6 invariants intact | `reporting.development_generated_lane_writer._status_snapshot` |
| 3 | A18b writer env-gate on VPS | `ADE_GENERATED_LANE_WRITER_ENABLED` is unset in the dashboard container | `reporting.development_generated_lane_writer.ENV_WRITER_ENABLED` |
| 4 | N5b Phase 1 preflight | `dry_run_only=true`, `live_merge_implemented=false`, `deploy_coupled=false`, `level6_enabled=false`, `candidate_count=0`, Step 5 invariants intact | `reporting.development_merge_preflight` |
| 5 | Step 5 loop reporter | `step5_implementation_allowed=false`, `step5_enabled_substage="none"` | `reporting.development_step5_loop` |
| 6 | Operational digest | `step5_implementation_allowed=false` | `reporting.development_operational_digest` |
| 7 | Recurring maintenance registry | `refresh_merge_preflight` job present, enabled, LOW risk, no-gh, 30-minute interval | `reporting.recurring_maintenance` |
| 8 | Agent service on VPS | agent container is stopped | docker compose project state |

---

## 4. Operator workflow — VPS

Run the chain in order. Every step is dry-run only. Any
divergence from the expected closed-vocab values in §3 pauses
Phase 1 and beyond.

```sh
cd /root/trading-agent

# Step 1 — confirm A18b writer artefact is absent on the canonical path.
test -f /root/trading-agent/generated_seed.jsonl \
   && echo "generated_seed exists" \
   || echo "generated_seed absent"

# Step 2 — inspect A18b writer status snapshot (read-only; CLI never writes).
python3 -m reporting.development_generated_lane_writer --no-write

# Step 3 — confirm A18b writer env-gate is unset in the dashboard container.
docker compose -p trading-agent exec dashboard env \
   | grep -E '^ADE_GENERATED_LANE_WRITER_ENABLED=' \
   || echo "ADE_GENERATED_LANE_WRITER_ENABLED is unset (writer off)"

# Step 4 — inspect N5b Phase 1 preflight rest state.
python3 -m reporting.development_merge_preflight --no-write

# Step 5 — Step 5 loop reporter.
python3 -m reporting.development_step5_loop --no-write

# Step 6 — operational digest.
python3 -m reporting.development_operational_digest --no-write

# Step 7 — recurring maintenance registry posture.
python3 -m reporting.recurring_maintenance --list-jobs

# Step 8 — confirm agent service is stopped on VPS.
docker compose -p trading-agent ps agent
```

### 4.1 Expected closed-vocab values per step

**Step 1.** Stdout: exactly `generated_seed absent`.

**Step 2.** Snapshot JSON must include:

* `writer_enabled = false`
* `env_var_name = "ADE_GENERATED_LANE_WRITER_ENABLED"`
* `generated_seed_path = "/root/trading-agent/generated_seed.jsonl"`
* `record_count = 0`
* `max_records_cap = 256`
* `step5_implementation_allowed = false`
* `step5_enabled_substage = "none"`
* `level6_enabled = false`
* `discipline_invariants` dict present and all values match the
  module's `_DISCIPLINE_INVARIANTS` constant.

**Step 3.** Stdout: exactly
`ADE_GENERATED_LANE_WRITER_ENABLED is unset (writer off)`. The
`grep` exit code is non-zero when the var is unset; the `||`
branch fires the explicit confirmation message.

**Step 4.** Snapshot JSON must include:

* `dry_run_only = true`
* `live_merge_implemented = false`
* `deploy_coupled = false`
* `level6_enabled = false`
* `step5_implementation_allowed = false`
* `step5_enabled_substage = "none"`
* `candidate_count = 0`

`note` may legitimately be any closed-vocab value from the
projector's vocabulary (typically
`missing_merge_recommendation_artifact` or
`missing_pr_lifecycle_artifact` when the upstream A22 / A23
chain has not been refreshed — see
[`docs/governance/n5b_merge_preflight_runbook.md`](n5b_merge_preflight_runbook.md)).

**Step 5.** Snapshot JSON must include:

* `step5_implementation_allowed = false`
* `step5_enabled_substage = "none"`

**Step 6.** Snapshot JSON must include:

* `step5_implementation_allowed = false`

**Step 7.** The `jobs` list must contain a row with:

* `job_type = "refresh_merge_preflight"`
* `enabled = true`
* `risk_class = "LOW"`
* `needs_gh = false`
* `schedule.interval_seconds = 1800` (30 minutes)

**Step 8.** Docker shows the `agent` service as stopped (the
container row reports a non-running state). The dashboard
service may legitimately be running; this runbook is about the
agent service.

---

## 5. Operator workflow — local dry-run

For a local smoke pass without VPS access, run the equivalent
commands from the repo working tree. Steps 3 and 8 are VPS-only
(they inspect the live docker compose project) and are skipped
locally. All other steps run identically:

```sh
test -f generated_seed.jsonl \
   && echo "generated_seed exists" \
   || echo "generated_seed absent"
python -m reporting.development_generated_lane_writer --no-write
python -m reporting.development_merge_preflight --no-write
python -m reporting.development_step5_loop --no-write
python -m reporting.development_operational_digest --no-write
python -m reporting.recurring_maintenance --list-jobs
```

The CLI `--no-write` flag on the A18b writer is documented in
the module's `_build_parser()` docstring as a no-op accepted for
parity with sibling reporting modules; the writer's CLI never
writes regardless. The status snapshot is what the bare CLI
emits by default.

---

## 6. Stop conditions and divergence handling

If any closed-vocab value from §4.1 fails to match, the operator:

1. **Stops.** No later phase may start.
2. **Captures evidence.** Saves the divergent command output to a
   private operator note (never to a public artefact or PR body;
   the output may contain bounded diagnostic information about
   the host).
3. **Investigates.** Inspects the relevant source-of-truth
   module (see §3 table) to determine whether the divergence is
   a real drift, a transient artefact-absence (Step 4 can
   legitimately differ when the upstream A22/A23 chain has not
   been refreshed), or a tooling artefact (Step 3 grep semantics
   on different shells).
4. **Resolves manually** before re-running this runbook. Phase 1
   remains blocked until §4.1 closes green.

The §4.1 closed-vocab values are the only authorised "go-ahead"
signal for Phase 1.

---

## 7. Rollback

This runbook describes only read-only inspection commands.
"Rollback" therefore reduces to **revert the docs PR** that
shipped this runbook (single `git revert`). No on-disk
artefact, no env variable, and no docker state is mutated by
running the runbook commands, so there is nothing else to
rewind.

---

## 8. Step 5 and Level 6 invariants

Level 6 is **permanently disabled** per ADR-015 §Doctrine 1 and
is **never** raised by this runbook. The six invariants below are
re-asserted on every line of this runbook:

```
step5_implementation_allowed = false
STEP5_ENABLED_SUBSTAGE        = "none"
level6_enabled                = false
dry_run_only                  = true
live_merge_implemented        = false
deploy_coupled                = false
```

The autonomous-development-lane projectors emit these literal
values into their snapshot envelopes on every run. This runbook
does not authorise the operator to flip any of them. Any future
change to these invariants requires a separate operator-authored
ADR and a separate PR.

---

## 9. What this runbook does NOT do

* Does **not** activate the A18b writer. Activation is Phase 1
  of the plan and requires the exact operator-go phrase
  `GO enable A18b writer on VPS`. Phase 0 only **observes** that
  the writer is default-disabled.
* Does **not** write any production `generated_seed.jsonl`
  record. The Phase 2 controlled production write smoke is a
  separate operator-go: `GO A18b controlled production write smoke`.
* Does **not** plan or implement A18c. A18c remains plan-only,
  gated by `GO A18c plan-only`.
* Does **not** plan, implement, or activate any Step 5 substage.
  Step 5 surfaces remain plan-only, gated by `GO Step 5 plan-only`
  with each substage having its own subsequent go phrase. No
  flag flip happens in Phase 0.
* Does **not** introduce N5b Phase 2 token-bound dry-run, Phase
  3 sacrificial-repo live merge, or Phase 4 production merge.
  Each requires its own operator-go per
  [`n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md) §10.
* Does **not** grant ADE permission to merge any PR, push to
  `main`, force-push, deploy, mint an approval token, verify an
  approval token, send a real push notification, or open / close
  / comment on any PR.
* Does **not** modify, mark complete, or advance any roadmap
  status field.

---

## 10. Authority chain summary

| Capability | Today | After this runbook | After Phase 1 go (operator-only) | After Phase 4 (A18c, future, operator-go required) | After N5b Phase 4 (future, distinct operator-go required) |
|---|---|---|---|---|---|
| Read A18b writer status snapshot | yes (CLI) | yes (documented) | unchanged | unchanged | unchanged |
| Read N5b Phase 1 preflight artefact | yes (CLI, scheduled) | yes (documented) | unchanged | unchanged | unchanged |
| Append a `generated_seed.jsonl` record | does not exist (env-gated, off) | unchanged | yes (writer armed; no record written until Phase 2 go) | unchanged | unchanged |
| Project `generated_seed.jsonl` rows into queue candidates | does not exist | unchanged | unchanged | yes — A18c, default-disabled by env flag | unchanged |
| Mint approval token | yes (N4b Phase B active, claim-only) | unchanged | unchanged | unchanged | unchanged |
| Live merge of any PR | does not exist | unchanged | unchanged | unchanged | yes — single PR per invocation, distinct operator-go |
| Autonomous merge / deploy / trade | forbidden (Level 6 permanently disabled) | unchanged | unchanged | unchanged | unchanged |

This runbook grants ADE **zero** new authority. The baseline
observation is information, not authority.

---

## 11. Cross-references

* [`docs/governance/development_generated_lane.md`](development_generated_lane.md)
  — A18a / A18b governance and writer contract.
* [`docs/governance/n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
  — N5b governance / plan-only doc; §10 enumerates the four
  rollout phases and reasserts that each requires a separate
  operator-go.
* [`docs/governance/n5b_merge_preflight_runbook.md`](n5b_merge_preflight_runbook.md)
  — N5b Phase 1 dry-run preflight upstream-refresh runbook.
* [`docs/governance/recurring_maintenance.md`](recurring_maintenance.md)
  — typed scheduler that owns the
  `refresh_merge_preflight` job (Step 7 of the chain).
* [`docs/governance/n4b_runtime_activation.md`](n4b_runtime_activation.md)
  — the operator-only runbook for N4b Phase B activation
  (already complete; N4b is at Phase B).
* [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md)
  — authority doctrine.
* [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  — Level 6 permanently-disabled doctrine.
* [`docs/governance/execution_authority.md`](execution_authority.md)
  — per-action authority decisions.
* [`docs/governance/no_touch_paths.md`](no_touch_paths.md) — the
  protected paths.
