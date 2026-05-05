# Mobile-first Agent Control PWA — Operator Runbook

> Module: `dashboard.api_agent_control` (backend) + `frontend/src/routes/AgentControl.tsx` (frontend)
> Release: v3.15.15.26 (mobile-first IA rebuild on top of v3.15.15.18); v3.15.16.9b adds Loop closure subsection; v3.15.16.9c adds canonical bootstrap event surfacing
> Sibling lifecycle modules: `reporting.autonomous_workloop`,
> `reporting.github_pr_lifecycle`,
> `reporting.workloop_runtime`,
> `reporting.recurring_maintenance`,
> `reporting.approval_policy`,
> `reporting.autonomy_metrics`,
> `reporting.human_needed` (v3.15.16.8),
> `reporting.governance_bootstrap` (v3.15.16.9)

## v3.15.16.9b — Loop closure subsection on the Status card

The Overview tab's existing Status card gains a "Loop closure"
subsection that surfaces the autonomous-loop closure state at a
glance. Read-only; no new endpoint; no `dashboard/dashboard.py`
change (the `/api/agent-control/status` route is already wired
since v3.15.15.21 — v3.15.16.9b only **extends the existing
payload**).

### What the subsection shows

| field | source artifact | meaning |
| --- | --- | --- |
| `loop_state` | derived | `open` / `resolved` / `stale` |
| `human_needed` count | `logs/human_needed/latest.json` | `counts.events_total` |
| `top_blocking_component` | `logs/human_needed/latest.json` | first event's `blocking_component` (only when `events_total > 0`) |
| `governance_bootstrap` count | `logs/governance_bootstrap/latest.json` | `counts.templates_total` |
| `top_branch_name` | `logs/governance_bootstrap/latest.json` | first template's `branch_name` (only when `templates_total > 0`) |
| `approval_inbox` derived rows | `logs/approval_inbox/latest.json` | count of `items` whose `source` startswith `human_needed:` |
| `last_refreshed_utc` | derived | lexicographic max of the three `generated_at_utc` fields |

### State derivation rules (pinned by tests)

| rule | resulting state |
| --- | --- |
| any source missing / malformed / no `generated_at_utc` | transport: `not_available` |
| any of the three counts > 0 | `data.loop_state: open` |
| all three counts == 0 AND timestamps within consistency window (10 min) | `data.loop_state: resolved` |
| all three counts == 0 BUT timestamps spread > 10 min | `data.loop_state: stale` |

The 10-minute consistency window is a relative spread check, not
an absolute clock check. There is **no recurring 30-minute timer
in v3.15.16.x** — the current cadence is the v3.15.16.3
post-deploy hook only. The operator compares `last_refreshed_utc`
against their last known deploy time to assess freshness; the
`stale` indicator only flags inconsistency between the three
artifacts within the same tick window.

### Bounded payload

The `loop_closure` envelope **never** carries `proposed_patch`,
`pr_body`, `file_diff`, full `events[]`, or full `templates[]`
lists. Only safe summary fields. Pinned by a defensive guard test
that asserts the exact set of allowed keys.

### Canonical use case

Bootstrap-PR validation for the v3.15.16.5 wiring gap: the
operator opens the Overview tab BEFORE the bootstrap PR merges
and sees `loop_state: open` with
`top_blocking_component: dashboard/dashboard.py:register_roadmap_priority_routes`.
After the bootstrap PR merges and the auto-deploy completes, the
operator refreshes and sees `loop_state: resolved` with all three
counts at zero. That two-state visual flip is the canonical
Phase 1 end-to-end proof — no log inspection required.

> **Aggregate vs canonical proof:** the `loop_state` field above is
> an aggregate over *all* `human_needed` events. With many unrelated
> blockers in flight, a single bootstrap PR may not flip
> `loop_state` to `resolved`. v3.15.16.9c adds an independent
> `roadmap_priority_wiring` subsection (see below) that is filtered
> to one canonical `(reason, blocking_component)` pair, so the
> specific v3.15.16.5 wiring gap can flip open→resolved without the
> aggregate clearing.

## v3.15.16.9c — `roadmap_priority_wiring` subsection (specific bootstrap proof)

The Loop closure subsection now also carries a sibling field at
the envelope level — `loop_closure.roadmap_priority_wiring` —
that reports a single, *specific* canonical bootstrap event by
exact `(reason, blocking_component)` match. It is independent of
the aggregate `loop_state` so the operator can validate one
bootstrap PR's effect without being drowned out by 200+ unrelated
`human_needed` events.

### Closed vocabulary

`state ∈ {open, resolved, not_available}`. Three values, no fourth.

`reason` is `null` when `state ∈ {open, resolved}`. When
`state == "not_available"`, `reason` is one of the eight closed
values:

| reason | meaning |
| --- | --- |
| `human_needed_missing` | `logs/human_needed/latest.json` not present |
| `human_needed_malformed` | artifact present but `events` is not a list |
| `governance_bootstrap_missing` | `logs/governance_bootstrap/latest.json` not present |
| `governance_bootstrap_malformed` | artifact present but `templates` is not a list |
| `approval_inbox_missing` | `logs/approval_inbox/latest.json` not present |
| `approval_inbox_malformed` | artifact present but `items` is not a list |
| `event_id_missing` | a matching event was found but its `event_id` is empty |
| `governance_bootstrap_lags_human_needed` | mid-refresh inconsistency: a matching template exists but no matching event |

### Detection rules

| step | rule |
| --- | --- |
| canonical literals | `REASON = "governance_bootstrap_required"`; `COMPONENT = "dashboard/dashboard.py:register_roadmap_priority_routes"` |
| open | `human_needed.events[*]` contains an entry with `reason == REASON` AND `blocking_component == COMPONENT` AND a non-empty `event_id` |
| open primary event | the lex-smallest matching `event_id` |
| open template branch | first `governance_bootstrap.templates[*].branch_name` whose `source_event_id == event_id` AND `source_reason == REASON` (PRIMARY match by `source_event_id`) |
| open inbox row present | any `approval_inbox.items[*]` whose `source == f"human_needed:{event_id}"` (exact equality, no substring) |
| resolved | all three artifacts valid AND no `human_needed` event matches AND no `governance_bootstrap` template matches `(source_reason, evidence.blocking_component)` |
| not_available | any artifact missing/malformed; or matching event with no `event_id`; or template-without-event mid-refresh |

### Acceptance contract

**Pre-bootstrap (current operator state):**

```
roadmap_priority route wiring: open
  event_id: h_<10hex>
  blocking_component: dashboard/dashboard.py:register_roadmap_priority_routes
  source_reason: governance_bootstrap_required
  template branch: governance-bootstrap/h_<10hex>
  approval_inbox row: present
```

**Post-bootstrap (after operator's dashboard.py wiring PR merges and the
recurring-maintenance refresh completes):**

```
roadmap_priority route wiring: resolved
```

The flip happens **independently** of the aggregate `loop_state`.
Other `human_needed` events may persist; the aggregate may stay
`open`. The canonical proof is the specific subsection.

This is the operator-facing runbook for the Agent Control PWA.
It explains what the app shows, what it does NOT do, how it is
laid out for thumb-first mobile use, and the wiring step required
to move it from "ships in the build" to "served on production".

## v3.15.15.26.2 — Standalone PWA shell

The v3.15.15.26 mobile-first IA was visible in the live PWA after
the v3.15.15.26.1 cache fix shipped, but it was rendered INSIDE
the legacy dashboard shell — the operator saw the new five-tab
layout wrapped by the old sidebar / topbar / ticker. That hybrid
is not what a standalone mobile PWA should look like.

**Fix in v3.15.15.26.2**:

* `frontend/src/App.tsx` lifts `/agent-control` out of the
  wildcard route that wraps `<AppShell>`. `/agent-control` is
  now a parallel top-level route, wrapped only by
  `<RequireAuth>`.
* The legacy dashboard routes (`/`, `/sprint`, `/campaigns`,
  `/observability`, etc.) continue to render inside `<AppShell>`
  via the wildcard route — nothing about the legacy desktop
  experience changed.
* `SW_VERSION` bumped to `v3.15.15.26.2` so an installed PWA
  invalidates the cached embedded-shell HTML and picks up the
  new standalone shell on the next refresh.

**Architecture (after .26.2)**:

```
<App>
  <Routes>
    <Route path="/login" element={<Login />} />

    {/* Standalone — no AppShell chrome. */}
    <Route path="/agent-control" element={
      <RequireAuth>
        <AgentControl />
      </RequireAuth>
    } />

    {/* Legacy desktop routes — wrapped in <AppShell>. */}
    <Route path="*" element={
      <RequireAuth>
        <AppShell>
          <Routes>
            <Route index element={<Dashboard />} />
            <Route path="/sprint" .../>
            ...
          </Routes>
        </AppShell>
      </RequireAuth>
    } />
  </Routes>
</App>
```

**Operator reinstall steps**:

1. Confirm the deployed Flask container has been rebuilt /
   restarted from the latest main SHA. The `frontend/dist/`
   bundle inside the running container must be the v3.15.15.26.2
   build.
2. On the phone: pull-to-refresh `/agent-control`. The new
   `SW_VERSION=v3.15.15.26.2` SW activates during this load and
   purges the v3.15.15.26.1 caches. The next refresh paints the
   standalone shell — no Sidebar / TopBar / Ticker around the
   five-tab nav.
3. If the home-screen icon was installed against the old shell:
   uninstall and reinstall via the browser's "Add to Home
   Screen" prompt. The `manifest.webmanifest` `start_url` is
   `/agent-control`, so the freshly installed PWA opens directly
   to the standalone surface.
4. If still stale: clear site data for the dashboard host, or
   (desktop Chrome) DevTools -> Application -> Service Workers
   -> Unregister, then hard reload.

## v3.15.15.26.1 — Service worker cache-versioning fix

After v3.15.15.26 was merged, the operator reported **no visible
UX change** in the live PWA. Root cause analysis identified the
service worker:

* `frontend/public/sw.js` hard-coded the cache name to
  `agent-control-shell-v1` and never bumped it between releases.
* The `activate` handler only deleted caches NOT named `v1`, so a
  new SW with the same cache name purged nothing.
* `/agent-control` was served cache-first, so an already-installed
  PWA kept replaying the cached pre-26 HTML — which still
  referenced the OLD content-hashed asset bundle filenames.
* Net effect: even after the dashboard served the fresh bundle,
  the user's browser kept rendering the v3.15.15.21.1 UI until
  they manually cleared site data.

**Fix in v3.15.15.26.1**:

* Added a single `SW_VERSION` constant pinned to the release
  (e.g. `v3.15.15.26.1`). All cache names embed it
  (`agent-control-shell-${SW_VERSION}`).
* `activate` now uses an inclusive set of known cache names and
  deletes any cache whose name does not match — including the
  legacy `v1` caches from a pre-26 install.
* SPA shell (`/`, `/agent-control`, `/manifest.webmanifest`,
  `/agent-control-icon.svg`) is now served via
  **stale-while-revalidate**. The user gets the cached UI
  immediately *and* the SW fetches the latest in the background;
  the next refresh shows the new UI.
* Hashed assets under `/assets/` remain cache-first (safe — they
  are content-addressed; a new build produces a new filename
  which is fetched as a cache miss).
* `/api/agent-control/*` remains **network-first** so the
  operator never sees stale data.
* `install` keeps `self.skipWaiting()` and `activate` keeps
  `self.clients.claim()` so a freshly installed SW takes over on
  the very next page load.

**Operator instructions to verify v3.15.15.26 UX**:

1. Confirm the deployed Flask container has been rebuilt /
   restarted from the latest main SHA. The `frontend/dist/`
   bundle inside the running container must contain the
   v3.15.15.26 IA. Locally:
   `npm --prefix frontend run build` produces fresh
   `dist/assets/index-<hash>.{js,css}`.
2. Open `/agent-control` on the phone. If the UI still looks
   like the old grid layout:
   * Pull-to-refresh once (the new SW will activate during this
     load and the next refresh will paint the new UI).
   * If still stale: Settings → site data → clear cache for the
     dashboard host, then re-open. As a more thorough reset on
     desktop Chrome: DevTools → Application → Service Workers →
     Unregister, then hard reload.
3. The new mobile-first UX must show:
   * a 5-tab bottom navigation (`Overview / Inbox / Runtime /
     PRs / About`) on phone-portrait;
   * a `read-only` safety badge under the title;
   * the new section grouping (one section visible per tab);
   * a footer reading `v3.15.15.26 — read-only`.

If all three are visible, v3.15.15.26.1 has propagated. If not,
the deployment has not yet pushed the latest bundle to the
serving container — `git pull && docker compose up -d --build` on
the VPS, then refresh.

## v3.15.15.26 — Mobile-first IA rebuild

The PWA now uses a **5-tab bottom navigation** on mobile (top
sticky tabs ≥ 720px) and groups its existing read-only cards
into operator-meaningful sections instead of a single long grid.

| Tab | Purpose | Cards |
|---|---|---|
| **Overview** | Is the system healthy? | Status (governance + frozen + workloop runtime + recurring maintenance + approval policy + autonomy metrics, all as compact rows) |
| **Inbox** | What needs Joery? | Approval Inbox + Proposal Queue |
| **Runtime** | Background telemetry | Autonomous Workloop digest + Activity (audit timeline) |
| **PRs** | Code lifecycle (read-only) | GitHub PR Lifecycle + Execute-safe Catalog |
| **About** | Meta | Notifications placeholder |

The header carries a small **read-only badge** below the title
to re-affirm the safety posture; the page summary banner remains
the primary at-a-glance signal.

Hard guarantees preserved:

* Touch targets ≥ 44 px (Apple HIG / WCAG 2.5.5).
* No horizontal scroll on phone-portrait.
* Inactive sections are `hidden` (excluded from the AT tree but
  still queryable from React Testing Library so the existing
  card test suite continues to work).
* No new external dependencies. No new network egress. No new
  service-worker scope. No browser push.
* No execute / approve / reject / merge buttons anywhere in the
  rendered DOM (verified by a regression test that scans every
  `<button>` for those verbs).
* PWA manifest, service worker, install behavior, and the
  `/agent-control` deep link are unchanged.

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

## Wiring status (as of v3.15.15.21)

`dashboard/dashboard.py` is on the no-touch list (it reads operator
session and token secrets, see
`docs/governance/no_touch_paths.md`). The agent-control routes
were not auto-registered by v3.15.15.18 and required an explicit
operator-led `governance-bootstrap` PR.

**That PR landed in v3.15.15.21**: the operator-authored commit
`41a9566` on the v3.15.15.21 release branch added the import and
register lines for the three approved read-only modules
(`api_agent_control`, `api_proposal_queue`, `api_approval_inbox`)
plus the `/agent-control` SPA-fallback route so the PWA deep-link
survives a hard reload. As of v3.15.15.21 main, the PWA cards
backed by those three modules resolve to real data.

The fourth route module — `api_execute_safe_controls` — ships in
v3.15.15.21 but is **intentionally not wired** in production. Its
gated POST endpoint is the v3.15.15.22 milestone (after the auth
surface lands), and the read-only catalog endpoint will be wired
together with the POST endpoint so they ship as a single coherent
release. Until then, the Execute-safe card on the PWA renders
`not_available` for the catalog and the runbook
[`execute_safe_controls.md`](execute_safe_controls.md) documents
how to drive the catalog from the CLI.

The approval inbox auto-clears `manual_route_wiring_required`
items as soon as `dashboard.py` contains both the `from ... import`
and the `register_...(app)` call for a known module — so an
operator who lands future wiring (e.g. for execute-safe in
v3.15.15.22) does not need to touch the inbox builder.

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
