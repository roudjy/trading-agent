# Roadmap v6.1 — Quant Research Engine

> Canonical, structured roadmap for the post-v3.15.16.0 phase of the
> Quant Research Engine. This document is parsed by
> `reporting.proposal_queue` (one H3 per shippable item) and consumed
> by `reporting.roadmap_priority` (which projects the safe-next-up
> item under the deterministic eligibility + ranking policy).
>
> Authoring rules (so the parser never produces noise):
>
> * One H1 — the document title.
> * One H2 per release group, with the release prefix in the title:
>   `## v3.15.16.x — <topic>`.
> * One H3 per shippable item, with the exact release id in the
>   title: `### v3.15.16.2 — <imperative title>`.
> * Body lines per item: a one-line summary, an `affected_files:`
>   line listing each path in `backticks` (so the parser picks them
>   up), a `risk_class:` line, a `status:` line (`proposed`, `done`,
>   `deferred`, `superseded`).
> * Done items stay in this document with `status: done` so the
>   prioritizer can skip them. Never delete items — supersede with a
>   linked successor.
>
> See `docs/governance/roadmap_priority.md` for the operator runbook
> and `reporting/roadmap_priority.py` for the deterministic
> prioritizer that consumes this document via the proposal queue.

---

## v3.15.16.x — Autonomous backlog & deploy plumbing

### v3.15.16.0 — First protocol-driven roadmap item — operator runbook for stale-artifact detection

Document the v3.15.15.27 stale-artifact detection surface in an
operator-facing runbook section.

* `affected_files`: `docs/governance/autonomy_metrics.md`,
  `docs/governance/observability_security_hardening.md`
* `risk_class`: LOW
* `proposal_type`: docs_only
* `status`: done

### v3.15.16.1 — VPS-side PR lifecycle artifact auto-refresh on deploy

Add a best-effort, non-fatal post-deploy step to
`scripts/deploy_vps_dashboard.sh` that runs the
github_pr_lifecycle dry-run reporter on the VPS host after every
merge to `main`. Result: `logs/github_pr_lifecycle/latest.json` is
fresh on the VPS and the Agent Control PWA's PRs tab has data.

* `affected_files`: `scripts/deploy_vps_dashboard.sh`,
  `docs/governance/vps_deploy.md`,
  `docs/governance/recurring_maintenance.md`
* `risk_class`: LOW
* `proposal_type`: observability_addition
* `status`: done

### v3.15.16.2 — Autonomous roadmap backlog ingestion and prioritization

Ship this canonical structured Roadmap v6.1 document and a new
read-only prioritizer module that joins the proposal queue with
the roadmap execution protocol to project a deterministic
chosen-next-up item plus its protocol plan summary into
`logs/roadmap_priority/latest.json`. The prioritizer is read-only
observability; it never starts work, never opens a branch, never
opens a PR, never merges, never calls `gh`. The
`recurring_maintenance` scheduler gains one new closed job entry
so the digest stays fresh on the VPS.

* `affected_files`: `docs/roadmap/qre_roadmap_v6_1.md`,
  `reporting/roadmap_priority.py`,
  `reporting/recurring_maintenance.py`,
  `tests/unit/test_roadmap_priority.py`,
  `tests/unit/test_recurring_maintenance.py`,
  `docs/governance/roadmap_priority.md`,
  `docs/governance/recurring_maintenance.md`
* `risk_class`: LOW
* `proposal_type`: observability_addition
* `status`: done

### v3.15.16.3 — VPS recurring maintenance automation on deploy

Append a best-effort, non-fatal post-deploy step to
`scripts/deploy_vps_dashboard.sh` that runs the existing typed
scheduler via `python3 -m reporting.recurring_maintenance
--run-due-once` on the VPS host after every successful merge to
`main`. Result: every Agent-Control-facing read-only artifact
(`logs/proposal_queue/latest.json`,
`logs/approval_inbox/latest.json`,
`logs/github_pr_lifecycle/latest.json`,
`logs/roadmap_priority/latest.json`,
`logs/workloop_runtime/latest.json`) is refreshed automatically
on every merge — no manual SSH, no operator command. The deploy
script does not pass `--enable-dependabot-execute-safe`, so the
only execute-capable job stays `blocked` by construction.

* `affected_files`: `scripts/deploy_vps_dashboard.sh`,
  `docs/governance/vps_deploy.md`,
  `docs/governance/recurring_maintenance.md`,
  `docs/roadmap/qre_roadmap_v6_1.md`
* `risk_class`: LOW
* `proposal_type`: observability_addition
* `status`: done

### v3.15.16.4 — Recurring-maintenance systemd timer (governance-bootstrap-gated)

Operator-authored governance-bootstrap PR that adds `ops/systemd/`
to an agent's allowlist union, then ships
`ops/systemd/trading-agent-recurring-maintenance.{service,timer}`
so the existing read-only scheduler runs on a fixed cadence on the
VPS for **between-merge** freshness without any manual `cron` /
`systemd` step. v3.15.16.3 already covers the merge-driven
cadence; v3.15.16.4 adds the continuous tick.

* `affected_files`: `.claude/agents/...`,
  `docs/governance/no_touch_paths.md`,
  `ops/systemd/trading-agent-recurring-maintenance.service`,
  `ops/systemd/trading-agent-recurring-maintenance.timer`,
  `ops/systemd/README.md`,
  `docs/governance/vps_deploy.md`
* `risk_class`: HIGH (governance-bootstrap; operator-authored)
* `proposal_type`: governance_change
* `status`: proposed

### v3.15.16.5 — PWA Next-Up card surfacing roadmap_priority digest

Add a new GET-only endpoint `/api/agent-control/next-up` backed
by `dashboard/api_roadmap_priority.py` and a read-only "Next up"
card on the Agent Control PWA's Inbox tab. The card surfaces
`logs/roadmap_priority/latest.json`: chosen_next_up,
final_recommendation pill, rationale, protocol_plan_summary,
filtered_out counts, needs_human indicator. Pure observability;
no action buttons; never wires `api_execute_safe_controls`.

The two-line `dashboard/dashboard.py` wiring required to activate
the route is **deferred to a separate operator-authored
governance-bootstrap PR** because the `deny_no_touch` hook blocks
the file-level write to `dashboard/dashboard.py` regardless of
in-chat operator approval — same shape that v3.15.15.21 used to
land the previous batch of agent-control wiring lines. Until that
bootstrap merges, the endpoint returns 404 and the PWA card
renders its `next-up-not-available` empty state.

* `affected_files`: `dashboard/api_roadmap_priority.py`,
  `frontend/src/api/agent_control.ts`,
  `frontend/src/routes/AgentControl.tsx`,
  `frontend/src/test/AgentControl.test.tsx`,
  `tests/unit/test_dashboard_api_roadmap_priority.py`,
  `tests/unit/test_observability_security_invariants.py`,
  `docs/governance/roadmap_priority.md`,
  `docs/roadmap/qre_roadmap_v6_1.md`
* `risk_class`: LOW
* `proposal_type`: observability_addition
* `status`: done

### v3.15.16.6 — Task board state machine for the autonomous loop

Ship `reporting/task_board.py` — a deterministic state-machine
projection over the roadmap-item lifecycle. Closed eight-state
vocabulary (backlog, refined, todo, in_progress, review, done,
blocked, human_needed). Closed eight-role owner_agent vocabulary
mirroring `reporting.roadmap_execution_protocol._AGENT_ROLES`.
First-match precedence rules mapping (proposal status, PR state,
priority eligibility, inbox severity) → state. Writes
`logs/task_board/latest.json`. JOB_REFRESH_TASK_BOARD added to
`recurring_maintenance` (LOW, no gh, default-enabled, 30-min
cadence). Pure observability; no git/gh, no mutation surface.
Phase 1 foundation for the v3.15.16.10 + v3.15.16.11 execution
authority + execution engine pair.

* `affected_files`: `reporting/task_board.py`,
  `reporting/recurring_maintenance.py`,
  `tests/unit/test_task_board.py`,
  `tests/unit/test_recurring_maintenance.py`,
  `docs/governance/task_board.md`,
  `docs/governance/recurring_maintenance.md`,
  `docs/roadmap/qre_roadmap_v6_1.md`
* `risk_class`: LOW
* `proposal_type`: observability_addition
* `status`: done

### v3.15.16.7 — Agent flow orchestration with explicit handoffs

Ship `reporting/agent_flow.py` — a deterministic orchestration
projection over the v3.15.16.6 task-board. For every task surfaces
`current_stage`, `responsible_agent`, `next_agent`,
`next_action_proposed` (closed eight-element enum:
select_next_task, generate_plan, implement, validate, review,
merge, escalate_human, no_op), `blocking_reason`,
`handoff_eligible`. The closed `next_action_proposed` enum is the
deterministic interface the v3.15.16.11 actuator will consume.
Writes `logs/agent_flow/latest.json`. JOB_REFRESH_AGENT_FLOW added
to `recurring_maintenance`. Pure observability; no git/gh, no
mutation surface.

* `affected_files`: `reporting/agent_flow.py`,
  `reporting/recurring_maintenance.py`,
  `tests/unit/test_agent_flow.py`,
  `tests/unit/test_recurring_maintenance.py`,
  `docs/governance/agent_flow.md`,
  `docs/governance/recurring_maintenance.md`,
  `docs/roadmap/qre_roadmap_v6_1.md`
* `risk_class`: LOW
* `proposal_type`: observability_addition
* `status`: done

### v3.15.16.8 — human_needed event detection with proposed_patch synthesis

Ship `reporting/human_needed.py` — pure read-only blocker detector.
Auto-detects every wiring gap (statically comparing
`register_*_routes` definitions in `dashboard/api_*.py` to call
sites in `dashboard/dashboard.py`, including multi-line imports)
and emits structured events with literal `proposed_patch` text.
Closed six-element reason vocabulary
(governance_bootstrap_required, no_touch_path_blocks_wiring,
allowlist_blocks_completion, release_gate_blocks_progression,
system_cannot_proceed_safely, decision_cannot_be_inferred). Closed
four-element impact / priority vocabulary (LOW / MEDIUM / HIGH /
CRITICAL). The v3.15.16.5 dashboard.py wiring gap is the canonical
first-detection case (pinned by unit test). Adds
`_build_from_human_needed` projection to
`reporting/approval_inbox.py` so each event surfaces in the
existing PWA Inbox card. JOB_REFRESH_HUMAN_NEEDED added to
`recurring_maintenance`. Pure observability; `proposed_patch` is
text only — never auto-applied. Future push notifications trigger
only on these events.

* `affected_files`: `reporting/human_needed.py`,
  `reporting/approval_inbox.py`,
  `reporting/recurring_maintenance.py`,
  `tests/unit/test_human_needed.py`,
  `tests/unit/test_approval_inbox.py`,
  `tests/unit/test_recurring_maintenance.py`,
  `docs/governance/human_needed.md`,
  `docs/governance/approval_exception_inbox.md`,
  `docs/governance/recurring_maintenance.md`,
  `docs/roadmap/qre_roadmap_v6_1.md`
* `risk_class`: LOW
* `proposal_type`: observability_addition
* `status`: proposed

---

## v3.15.17.x — Push notifications (operator-authored governance bootstrap required)

### v3.15.17.0 — Web Push alerts governance-bootstrap

OPERATOR-AUTHORED governance-bootstrap PR that lifts the
no-browser-push constraint for a strictly bounded alert-only Web
Push surface and prepares the policy ground for the v3.15.17.1+
implementation phases.

* `affected_files`: `AGENTS.md`, `CLAUDE.md`,
  `.claude/agents/...`,
  `docs/governance/agent_control_push_alerts.md`,
  `docs/governance/no_touch_paths.md`,
  `docs/governance/observability_security_hardening.md`,
  `docs/governance/mobile_agent_control_pwa.md`,
  `tests/unit/test_observability_security_invariants.py`,
  `requirements.txt`, `config/web_push_public_key.txt`
* `risk_class`: HIGH (governance-bootstrap; operator-authored)
* `proposal_type`: governance_change
* `status`: proposed

### v3.15.17.1 — Push backend foundation

`dashboard/api_push.py` (new), `reporting/web_push_dispatch.py`
(new), VAPID key plumbing. No SW changes, no event triggers, no
real push sent yet.

* `affected_files`: `dashboard/api_push.py`,
  `reporting/web_push_dispatch.py`,
  `state/web_push_subscriptions.json`,
  `tests/unit/test_web_push_dispatch.py`,
  `tests/unit/test_web_push_subscription_store.py`
* `risk_class`: MEDIUM (depends on v3.15.17.0)
* `proposal_type`: tooling_intake
* `status`: proposed

### v3.15.17.2 — Frontend SW push handler + permission UX

`frontend/public/sw.js` push event handler,
`frontend/src/components/PushPermissionPrompt.tsx`,
`frontend/src/api/agent_control_push.ts`. End-to-end works for
manually injected events.

* `affected_files`: `frontend/public/sw.js`,
  `frontend/src/api/agent_control_push.ts`,
  `frontend/src/components/PushPermissionPrompt.tsx`,
  `tests/integration/test_web_push_end_to_end.py`
* `risk_class`: MEDIUM (depends on v3.15.17.1)
* `proposal_type`: ux_gap
* `status`: proposed

### v3.15.17.3 — Event triggers + dispatch

`reporting/web_push_event_diff.py` and a closed-vocabulary list of
event kinds (PR opened/updated/merged, CI pass/fail, deploy
success/failure, approval_inbox new, proposal_queue new). First
real outbound push, throttled and feature-flagged.

* `affected_files`: `reporting/web_push_event_diff.py`,
  `reporting/recurring_maintenance.py`,
  `state/web_push_dispatch_enabled.flag`
* `risk_class`: MEDIUM (depends on v3.15.17.2)
* `proposal_type`: observability_addition
* `status`: proposed

---

## v3.15.18.x — Roadmap v6.1 §v3.15.16 — Intelligent Routing Layer

### v3.15.18.0 — Behavior-aware campaign routing scaffold

Make campaign routing behavior-aware instead of preset-count-aware.
Scaffold-only release: introduces the read-only routing-priority
projection without changing any active campaign selection.

* `affected_files`: `research/routing_priority.py`,
  `research/observability/routing_priority.v1.json`,
  `tests/unit/test_routing_priority.py`,
  `docs/governance/intelligent_routing.md`
* `risk_class`: LOW
* `proposal_type`: observability_addition
* `status`: proposed

---

## v3.15.19.x — Roadmap v6.1 §v3.15.17 — Sampling Intelligence

### v3.15.19.0 — Stratified sampling + low-information-region suppression scaffold

Scaffold-only release: introduces the deterministic stratified
sampling helper and the low-information-region detector as read-only
projections. No change to the active sampler.

* `affected_files`: `research/sampling_intelligence.py`,
  `research/observability/sampling_intelligence.v1.json`,
  `tests/unit/test_sampling_intelligence.py`,
  `docs/governance/sampling_intelligence.md`
* `risk_class`: LOW
* `proposal_type`: observability_addition
* `status`: proposed

---

## Authoring conventions

* `risk_class` MUST be one of `LOW`, `MEDIUM`, `HIGH`. The
  prioritizer filters HIGH out of the next-up surface; HIGH items
  are visible in the queue but are never auto-selected.
* `proposal_type` SHOULD match the canonical
  `reporting.proposal_queue` taxonomy: `observability_addition`,
  `observability_gap`, `testing_gap`, `ux_gap`, `ci_hygiene`,
  `dependency_cleanup`, `release_candidate`, `tooling_intake`,
  `governance_change`, `roadmap_adoption`, `roadmap_diff`,
  `approval_required`. The prioritizer never relies on
  `proposal_type` for risk decisions — those come from the
  `roadmap_execution_protocol`.
* `status: done` items remain in this document for traceability.
  The prioritizer ignores them. The proposal_queue parser converts
  them into proposals with `status="done"` derived from this
  marker; the prioritizer rejects any non-`proposed` candidate.
* Inter-item dependencies are captured by **release-id ordering**:
  an item under `## v3.15.17.x` is implicitly dependent on the
  preceding `## v3.15.16.x` group reaching `done` for the items
  this group depends on. The MVP prioritizer does not parse
  free-form `Depends on:` lines; that is a v3.15.16.4+ enhancement.

## Cross-references

* `docs/governance/roadmap_priority.md` — operator runbook for the
  prioritizer.
* `docs/governance/recurring_maintenance.md` — operator runbook for
  the scheduler that keeps `logs/roadmap_priority/latest.json`
  fresh on the VPS.
* `docs/governance/vps_deploy.md` — VPS deploy runbook (covers the
  `github_pr_lifecycle` post-deploy refresh from v3.15.16.1).
* `reporting/roadmap_priority.py` — prioritizer module.
* `reporting/proposal_queue.py` — markdown parser.
* `reporting/roadmap_execution_protocol.py` — per-item plan + risk
  arbiter.
