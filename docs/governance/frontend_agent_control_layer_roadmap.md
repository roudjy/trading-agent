# Frontend Agent Control Layer — Roadmap (v3.15.15.17 → .23)

This document captures the post-v3.15.15.16 release sequence that
moves the operator's daily interaction from CLI / GitHub web UI to a
backend-mediated dashboard surface. Frontend remains UI-only;
backend / controller remains the policy surface; the autonomous
workloop controller (v3.15.15.16) remains the only place where PR /
Dependabot / roadmap decisions are made.

## Maturity ladder placement

| Release | Workloop level | Operator surface |
|---|---|---|
| v3.15.15.16 | B + C (plan + classify + safe local execution) | CLI |
| v3.15.15.17 | B (visibility) | dashboard read-only |
| v3.15.15.18 | B (visibility + intake) | dashboard read-only |
| v3.15.15.19 | D (GitHub-backed PR awareness) | CLI + dashboard read-only |
| v3.15.15.20 | D | dashboard approval inbox (read-only) |
| v3.15.15.21 | F (dashboard execute-safe controls) | dashboard write |
| v3.15.15.22 | G (scheduled / continuous runtime) | dashboard + VPS |
| v3.15.15.23 | E (safe PR automerge) | dashboard + GitHub |

## v3.15.15.17 — Frontend Agent Control Layer: read-only status

**Purpose**: surface the workloop digest in the dashboard so the
operator can see *which agent did what, what's queued, what's
blocked* without opening a terminal.

**Scope**:
- Add `dashboard/api_agent_control.py` registering four GET-only
  endpoints, mirroring the existing `dashboard/api_system_meta.py`
  idiom (filesystem inspection, no orchestrator imports, returns
  `{"available": false}` instead of raising when artifacts are
  missing):
  - `GET /api/agent-control/status` — top-level snapshot read from
    `logs/autonomous_workloop/latest.json`.
  - `GET /api/agent-control/activity` — agent activity timeline
    derived from
    `python -m reporting.agent_audit_summary --view timeline`
    (executed as a subprocess; output cached for at most 60 s).
  - `GET /api/agent-control/pr-queue` — `pr_queue` + `dependabot_queue`
    pulled from the same JSON.
  - `GET /api/agent-control/roadmap` — `roadmap_queue` from the same
    JSON.
- Three frontend panels (UI-only):
  - **Agent Activity Timeline** — last 50 events with redacted
    columns (timestamp, actor, tool, outcome, branch, session, target
    dir).
  - **PR Queue** — table with risk_class / checks / decision /
    next_action; row links open to the corresponding GitHub PR in a
    new tab.
  - **Roadmap Queue** — table with source / risk_class / next_action;
    no execute buttons.

**Out of scope**:
- Any POST / PUT / DELETE endpoint.
- Direct GitHub API call from backend.
- Direct `gh` invocation.
- Approval / merge actions.

**Backend artifacts**:
- New module: `dashboard/api_agent_control.py`.
- One-line registration in `dashboard/dashboard.py`:
  `register_agent_control_routes(app)`. *(Note: `dashboard/dashboard.py`
  is no-touch — the registration line will need to be added via a
  governance-bootstrap PR, OR `register_agent_control_routes` is
  invoked from the existing `register_observability_routes` block
  via a forward-compat hook. Decision deferred to v3.15.15.17
  planning.)*

**Frontend panels**:
- New: `frontend/src/components/agent-control/{Timeline,PrQueue,RoadmapQueue}.tsx`.
- New page route: `frontend/src/pages/AgentControl.tsx`.

**Tests**:
- Unit tests for `api_agent_control.py` mirroring
  `tests/unit/test_dashboard_api_system_meta.py`: GET-only,
  graceful-missing handling, no orchestrator imports.
- Frontend Vitest tests for each panel.
- Smoke test: dashboard renders the panels with a stub JSON file.

**Merge policy**:
- Standard PR review.
- The dashboard registration line in `dashboard.py` is itself a
  no-touch path; that line is added via a separate
  `governance-bootstrap` PR or by an alternative wiring strategy.
  This is the only operator-merge friction in v3.15.15.17.

**DoD**:
- All four endpoints respond 200 in dev with stub JSON.
- All three panels render in the dashboard.
- `python -m reporting.autonomous_workloop --mode execute-safe` →
  `cat logs/autonomous_workloop/latest.json | jq .` works as the
  data source.
- Frozen contracts byte-identical.
- No new dependency.

## v3.15.15.18 — Roadmap Queue & Agent Proposal Intake

**Purpose**: let bugfix / strategic / observability / refactor agents
*propose* roadmap items via committed markdown files; the operator
sees the inbox in the dashboard.

**Scope**:
- New directory: `docs/governance/autonomous_workloop/proposals/`.
- Proposal schema (markdown frontmatter):
  ```
  proposal_id, source_agent, title, problem, evidence,
  suggested_release_id, risk_class, expected_files, tests_required,
  estimated_operator_impact, recommended_action,
  approval_requirement
  ```
- `GET /api/agent-control/proposals` — list proposals with metadata.
- Agents may write proposals only under their `allowed_roots` (which
  may need extension — handled per-agent via `governance-bootstrap`
  PRs).

**Out of scope**:
- Auto-approval.
- Auto-merge.
- POST / write surface.

**Backend artifacts**:
- Proposal parser library: `reporting.proposals` (read-only,
  stdlib-only, mirrors the existing `subagent_attribution` parser).
- New endpoint in `dashboard/api_agent_control.py`.

**Frontend panels**:
- **Agent Proposal Inbox** — read-only list with proposal metadata.

**Tests**:
- Proposal parser tests (well-formed / malformed / missing field
  handling).
- Endpoint test mirroring v3.15.15.17 idiom.

**Merge policy**: standard.

**DoD**:
- Each agent type can write a proposal and have it appear in the
  inbox without code changes.
- Malformed proposals are flagged but never raise.
- No frozen-contract drift.

## v3.15.15.19 — GitHub-backed PR / Check Integration

**Purpose**: turn `checks_status` from `not_available` into a real
read. This is the unlock for Dependabot triage and for the safe
automerge release later.

**Scope**: choose **one** integration path (decision in this
release):
- **Path A**: install `gh` CLI on the operator's host and the VPS.
  Controller wraps `gh pr list / gh pr view --json` calls.
  Simplest; needs binary install.
- **Path B**: GitHub App with read-only PR / check scopes; backend
  authenticates via the App's installation JWT (no PAT in repo).
  Cleanest for production; needs App registration.
- **Path C**: GitHub REST via stdlib `urllib` + a PAT read from a
  per-host secret file (never logged, never in the ledger,
  redacted in digests). Lowest setup overhead; needs token rotation
  policy.

The choice gates the rest of v3.15.15.19's design and is the single
biggest architectural decision in this roadmap. The recommendation is
**Path B** for the production posture; **Path A** is acceptable for
the operator's laptop in interim.

**Out of scope**:
- Any merge action — this release only *reads*.
- Any write to PRs (no comments, no labels).

**Backend artifacts**:
- `reporting.github_backed.py` (or a similar location decided at
  build time). Reads PR metadata + check runs into the same JSON
  schema (`checks_status` becomes one of `green` / `red` /
  `pending` / `not_available`).
- Controller integration: `risk_class` upgrades from
  `*_safe_candidate` to `*_safe` *only* when checks_status is
  `green` AND no other gate fires.

**Frontend**: same panels; `checks_status` now shows actual values.

**Tests**:
- Network mocked end-to-end (no live API calls in CI).
- Failure-mode tests: token missing → `not_available`; rate-limited
  → `not_available`; API 5xx → `not_available`. Never `green`.

**Merge policy**:
- The integration path itself is a substantial scope. Open the PR
  with explicit operator approval for the chosen path.
- No new secrets in the repo; tokens / app keys live outside.

**DoD**:
- Real `checks_status` for at least one open PR (verified in dev).
- `safe_to_merge` becomes reachable for branches with green checks.
- The 10 final-report statements update to remove "gh / API not
  available — checks_status / mergeability are `not_available`".

## v3.15.15.20 — Operator Approval & Exception Inbox

**Purpose**: surface decisions that require human attention in one
place. Read-only display.

**Scope**:
- `GET /api/agent-control/approvals` — derived from the workloop
  digest's `needs_human` array, filtered for high-priority items
  (governance, contract, trading, financial, failed-gate override).
- Each row carries: kind, item_id, reason, evidence_links, severity.
- Read-only — POST is deferred to v3.15.15.21.

**Out of scope**:
- POST surface.
- Auto-approve.

**Backend artifacts**: one endpoint in
`dashboard/api_agent_control.py`.

**Frontend panels**: **Operator Approval Inbox** — read-only.

**Tests**: classifier test for severity; never empty when
`needs_human` is non-empty; never auto-resolves.

**Merge policy**: standard.

**DoD**: every needs-human row in the workloop digest is reachable
from the dashboard inbox without scrolling through CLI output.

## v3.15.15.21 — Dashboard Execute-Safe Controls

**Purpose**: replace `python -m reporting.autonomous_workloop` with
a click in the dashboard.

**Scope**:
- POST endpoints with explicit-confirmation tokens:
  - `POST /api/agent-control/workloop/dry-run`
  - `POST /api/agent-control/workloop/execute-safe`
  - `POST /api/agent-control/workloop/pause`
- Backend invokes `reporting.autonomous_workloop` as a **subprocess**
  (never imports — keeps `dashboard.py` side-effect-free).
- Rate limit: at most 1 invocation per 60 s per endpoint.
- Abort token: a long-running invocation can be cancelled by the
  same operator's session token.
- POST endpoints for approvals:
  - `POST /api/agent-control/approvals/<id>/approve` (typed reason
    required)
  - `POST /api/agent-control/approvals/<id>/reject`

**Out of scope**:
- Auto-merge (deferred to v3.15.15.23).
- Long-running scheduled runtime (v3.15.15.22).

**Backend artifacts**: extend `dashboard/api_agent_control.py` with
POST handlers; add audit hook for every POST (every action emits a
ledger event).

**Frontend panels**:
- Buttons on existing panels: dry-run / execute-safe / pause.
- Confirmation modal for high-severity actions.

**Tests**:
- POST without confirmation token → 400.
- POST after rate-limit window → 429.
- Subprocess invocation produces digest pair; backend re-reads.

**Merge policy**:
- Adds a write surface — extra reviewer scrutiny.
- No bypass of workloop policy from the frontend.

**DoD**: operator runs the workloop entirely from the dashboard.

## v3.15.15.22 — Long-Running Workloop Runtime

**Purpose**: keep the workloop ticking without a manual click.

**Scope**: choose **one**:
- **Option A**: tmux session on the operator's laptop + restart
  guard. Simplest; tied to the laptop being on.
- **Option B**: systemd timer / service on the Hetzner VPS, running
  `python -m reporting.autonomous_workloop --mode continuous
  --max-cycles N` on a configurable schedule. Survives laptop
  reboots; needs VPS deploy review.

For both, add:
- A lockfile to prevent concurrent runs.
- A cooldown window between cycles (default 15 min, clamped 5–60).
- Crash recovery: on restart, read the last digest's `cycle_id` and
  continue.
- Scheduled digest write timestamps so the dashboard shows "last
  cycle: N min ago".

**Out of scope**:
- Anything that requires capital allocation or trading-flow change.
- Anything that touches `automation/live_gate.py`.

**Backend artifacts**: a small CLI (`scripts/workloop_runtime.sh`
or `ops/systemd/workloop.service`).

**Tests**:
- Lockfile prevents concurrent invocation (subprocess fixture).
- Crash + restart resumes at the next cycle_id.

**Merge policy**:
- Touches `ops/systemd/**` (no-touch) — needs governance-bootstrap PR
  for that file. The CLI portion is autonomous-eligible.

**DoD**: the workloop runs unattended; digests update on schedule.

## v3.15.15.23 — Safe PR Automerge

**Purpose**: the workloop merges low-risk PRs autonomously, under
green-checks evidence. This is the first time the controller actually
performs a merge.

**Scope**:
- Merge only when **all** of the following hold:
  - `checks_status: green`;
  - `risk_class` is one of `dependabot_patch_safe` /
    `dependabot_minor_safe` (note: `_safe`, not `_safe_candidate` —
    requires v3.15.15.19 unlock);
  - branch is not on the always-needs-human list (no `react`, no
    `vite`, no `typescript`, no major-framework upgrades);
  - branch is not protected;
  - frozen contracts unchanged in the diff;
  - no test-weakening markers added in the diff;
  - operator has explicitly enabled automerge for this PR (label or
    typed token).
- All other merges remain operator-click.

**Out of scope**:
- High-risk dependency merges (always operator).
- Protected-path merges (always operator).
- Trading / live / paper / shadow code (always operator).

**Backend artifacts**:
- New CLI flag: `--mode automerge` (off by default).
- The merge call uses the chosen integration path from v3.15.15.19;
  never `git push origin main` directly (Doctrine 8 stays in force).

**Tests**:
- Every gate must fire in isolation.
- Audit ledger event for every automerge attempt — successful or
  blocked — with reason.
- "Operator opt-in" gate: no automerge unless opt-in evidence is
  present.

**Merge policy**:
- The opt-in mechanism is the single most sensitive surface in this
  whole roadmap. Open this PR with explicit operator approval and an
  ADR amendment that documents the opt-in semantics.

**DoD**:
- A green-check Dependabot patch PR merges within one cycle when the
  operator has opted in.
- Every other PR class continues to require operator click.
- Audit chain remains intact across automerge events.

## After v3.15.15.23

The project returns to the
[`docs/roadmap/qre_roadmap_v3_post_v3_15.md`](../roadmap/qre_roadmap_v3_post_v3_15.md)
sequence (research-platform / v6.1 / v7.x). The agent-control layer
remains a separately-versioned slice — additions to the dashboard
or the workloop go through their own ADR amendments.
