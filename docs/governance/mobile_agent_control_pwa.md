# Mobile-first Agent Control PWA — Operator Runbook

> Module: `dashboard.api_agent_control` (backend) + `frontend/src/routes/AgentControl.tsx` (frontend)
> Release: v3.15.15.18
> Sibling lifecycle modules: `reporting.autonomous_workloop`,
> `reporting.github_pr_lifecycle`

This is the operator-facing runbook for the v3.15.15.18 mobile-first
Agent Control PWA. It explains what the app shows, what it does NOT
do, how to install it on a phone, and the wiring step required to
move it from "ships in the build" to "served on production".

## What this is

A mobile-first, installable, **read-only** observability surface for
the autonomous development system. Five cards on one screen, all
auto-refreshable, all backed by JSON artifacts the rest of the
governance stack already emits:

| Card | Source | Purpose |
|---|---|---|
| **Status** | `reporting.governance_status` + frozen-contract sha256 | At-a-glance health of governance + frozen contracts |
| **Activity** | `reporting.agent_audit_summary` (timeline view, last 50 redacted events) | Who-did-what on today's audit ledger |
| **Workloop** | `logs/autonomous_workloop/latest.json` | Latest digest from the local workloop planner |
| **PR Lifecycle** | `logs/github_pr_lifecycle/latest.json` | Latest Dependabot queue snapshot |
| **Notifications** | placeholder | Empty-state. Browser push lands in v3.15.15.23. |

## What this is NOT

The release intentionally does NOT ship:

* execute / approve / reject / merge buttons (none in the rendered DOM — verified by test);
* browser push notifications (placeholder card only — release v3.15.15.23);
* a long-running runtime (one fetch on mount + one fetch on refresh);
* roadmap / proposal queues (release v3.15.15.19);
* approval inbox (release v3.15.15.20);
* execute-safe controls in the UI (release v3.15.15.21);
* metrics / external observability (release v3.15.15.25);
* any POST / PUT / PATCH / DELETE endpoint;
* any `gh` invocation from the dashboard process;
* any `git` invocation from the dashboard process;
* any external telemetry, analytics, or paid service.

## Architecture (thin layers)

```
┌─────────────────────┐          ┌────────────────────────────┐
│   Phone / Desktop   │  HTTPS   │  Flask (read-only routes)  │
│  AgentControl SPA   │ ───────► │ /api/agent-control/status   │
│  PWA shell + SW     │          │ /api/agent-control/activity │
│  Five cards         │          │ /api/agent-control/workloop │
│                     │          │ /api/agent-control/pr-...   │
│                     │          │ /api/agent-control/notif... │
└─────────────────────┘          └────────────┬───────────────┘
                                              │
                                  In-process module calls
                                              ▼
              reporting.governance_status / agent_audit_summary
              + filesystem reads of logs/*.json (read-only)
```

The frontend is the existing Vite/React SPA — same React Router
shell, same auth provider, same Flask `/` index route. The new
route lives at `/agent-control` and renders five cards inside the
existing `AppShell`.

## Hard guarantees (enforced by code AND tests)

| guarantee | enforcement |
|---|---|
| Backend GET-only | every route registers `methods=["GET"]`; `test_mutation_verbs_are_rejected` asserts 405 on POST/PUT/PATCH/DELETE |
| Backend never invokes `gh` or `git` | `test_no_gh_or_git_invocation_in_module` (static source check) |
| Backend never spawns a subprocess | `test_no_subprocess_imports_in_module` |
| Missing artifact → `not_available` | `test_workloop_missing_artifact_yields_not_available`, `test_pr_lifecycle_missing_artifact_yields_not_available` |
| Malformed artifact → `not_available` | `test_workloop_malformed_artifact_yields_not_available` |
| Secret redaction always runs | `test_payload_with_credential_string_is_refused` (response is 500, not leaking text) |
| SW only handles GET | runtime guard + `test_only_handles_get_requests` (static check) |
| SW never reaches external services | `test_does_not_reach_external_analytics_or_services` |
| Frontend has exactly one button | `test_contains_exactly_one_button` (the Vernieuw refresh button) |
| No execute / approve / merge button labels | `test_does_not_render_any_execute_approve_merge_button` |
| Cards fall back gracefully | `test_renders_not_available_everywhere_when_every_endpoint_404s` |

## Wiring step (manual, one line)

`dashboard/dashboard.py` is on the no-touch list (it reads operator
session and token secrets, see
`docs/governance/no_touch_paths.md`). The agent-control routes are
not auto-registered by this release; activating them requires one
line in `dashboard/dashboard.py` next to the other
`register_*_routes(app)` calls:

```python
# v3.15.15.18: read-only Agent Control PWA routes.
from dashboard.api_agent_control import register_agent_control_routes
register_agent_control_routes(app)
```

That edit is intentionally not shipped here. Until the operator
performs it, the PWA frontend treats every endpoint as
`not_available` and renders empty / placeholder states — by design,
not as an error.

## Installing the PWA on a phone

1. The dashboard at `https://<host>:8050/` is served behind HTTP
   Basic auth (existing flow). Log in once on the phone.
2. Navigate to `/agent-control` in the browser.
3. iPhone (Safari): tap *Share → Add to Home Screen*.
   Android (Chrome): tap *⋮ → Install app*.
4. The app installs with the icon from `agent-control-icon.svg`,
   opens to `/agent-control` (per `manifest.start_url`), runs in
   `display: standalone` mode (no browser chrome).

The service worker (`/sw.js`) handles offline gracefully:

* SPA shell is cached on install (`agent-control-shell-v1`).
* `/api/agent-control/*` is network-first with cache fallback —
  online users always see fresh data; offline users see the last
  cached payload (and a `not_available { reason: "offline" }`
  envelope when no cache exists).

## Running locally

```sh
# Backend (existing flow):
python -m dashboard.dashboard
# Frontend (existing flow):
npm --prefix frontend run dev
# Then visit http://localhost:5173/agent-control
```

In dev, Vite proxies `/api/*` to `http://localhost:8050`, so the
five endpoints are reachable as soon as `register_agent_control_routes`
is wired up.

## Mobile-first design choices

* Phone-portrait first; cards stack vertically on viewports
  < 720px; two-column grid from 720px+.
* Touch targets are >= 44x44 px (Apple HIG / WCAG 2.5.5).
* Status colors are semantic only:
  * teal = ok
  * amber = warn
  * red = blocked / danger
  * gray = not_available
* No dense desktop tables in the primary view.
* Safe-area insets respected for the iPhone notch.

## Tooling assessment

Adopted in this release:

| dependency | purpose | cost / license | external egress | rollback |
|---|---|---|---|---|
| (none new) | every tool in this release reuses what is already in `frontend/package.json` (Vite 5, React 18, Vitest 4) and Python stdlib + Flask. | n/a | none | revert the PR |

Specifically: no PWA library (e.g. `vite-plugin-pwa`, `workbox`),
no external icon set, no analytics SDK, no notification provider.
All PWA artifacts (`manifest.webmanifest`, `sw.js`,
`agent-control-icon.svg`) are hand-written and live under
`frontend/public/`.

If a future release wants better SW ergonomics, `vite-plugin-pwa`
is the canonical free + offline option (MIT license, no telemetry,
no signup). It would need its own tooling-policy ADR.

## Forward roadmap (not shipped here)

| release | adds |
|---|---|
| **v3.15.15.18 (this)** | mobile-first read-only PWA shell, 5 cards, manifest, SW |
| v3.15.15.19 | roadmap / proposal queue card |
| v3.15.15.20 | approval inbox (operator confirms execute requests) |
| v3.15.15.21 | execute-safe controls (the first *write* button — strictly gated) |
| v3.15.15.23 | browser push notifications for needs-human events only |
| v3.15.15.25 | metrics / observability dashboards |

Each subsequent release strictly adds capability; nothing in this
release walks back a guarantee.

## Files added by v3.15.15.18

```
dashboard/api_agent_control.py
docs/governance/mobile_agent_control_pwa.md   (this file)
frontend/index.html                           (manifest + theme-color tags only)
frontend/public/agent-control-icon.svg
frontend/public/manifest.webmanifest
frontend/public/sw.js
frontend/src/api/agent_control.ts
frontend/src/main.tsx                         (SW registration only)
frontend/src/routes/AgentControl.tsx
frontend/src/styles/agent_control.css
frontend/src/test/AgentControl.test.tsx
frontend/src/test/PWAManifest.test.tsx
frontend/src/vite-env.d.ts
tests/unit/test_dashboard_api_agent_control.py
```

No edit to `dashboard/dashboard.py` (no-touch). No edit to
`.claude/**`. No frozen-contract change. No live/paper/shadow/
trading/risk behavior change.
