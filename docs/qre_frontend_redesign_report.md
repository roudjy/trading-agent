# QRE Frontend Redesign — Implementation Report

**Branch:** `feat/qre-frontend-redesign`
**Scope:** UI-only port of the Claude Design "QRE 8-bit Control Room"
handoff into the production React frontend, plus three new read-only
backend metadata endpoints.

---

## 1. UI-only proof

### 1.1 No backend behavior changed

```
$ git status --short
 M dashboard/dashboard.py                       (registration of new blueprint, +6 lines)
 M frontend/...                                 (UI files)
?? dashboard/api_system_meta.py                 (NEW read-only module)
?? frontend/...                                 (NEW UI files)
?? tests/unit/test_dashboard_api_system_meta.py (NEW targeted tests)
```

Files NOT touched (verified by grep on `git status`):

* `agent/`, `strategies/`, `orchestration/`, `execution/`,
  `automation/`, `state/`, `research/` (other than the existing
  `research/discovery_sprints/` artifact dir that was already
  untracked at session start)
* `dashboard/api_campaigns.py`, `dashboard/api_research_intelligence.py`,
  `dashboard/research_runner.py`, `dashboard/research_artifacts.py`
* All frozen contracts (`research/research_latest.json`,
  `research/strategy_matrix.csv`)

The diff in `dashboard/dashboard.py` is exactly two additions: the
import of the new blueprint and a call to register it. No existing
route handler was modified.

### 1.2 No mutating endpoints added; existing ones preserved

```
$ grep -REn "method:\s*['\"]POST|method:\s*['\"]PUT|method:\s*['\"]DELETE|method:\s*['\"]PATCH" frontend/src/
frontend/src/api/client.ts:184:      method: "POST",     # /api/presets/{name}/run (pre-existing)
frontend/src/api/client.ts:215:      method: "POST",     # /api/session/login (pre-existing)
frontend/src/api/client.ts:219:    method: "POST"        # /api/session/logout (pre-existing)
```

Only the three pre-existing POSTs survived: `runPreset` (existing
operator capability — not a new control), `login`, `logout`. No new
mutating fetch was introduced.

### 1.3 No prototype globals leak into the production bundle

```
$ grep -REn "QRE_DATA|QRE_UI|QRE_SHELL|QRE_PAGES_A|QRE_PAGES_B|QRE_NOW|useTweaks|TweaksPanel|tweaks-panel|mock-data" frontend/dist/
(no matches)
```

Items explicitly stripped from the prototype before porting:

* CDN React/ReactDOM UMD scripts
* Babel-standalone in-browser transpiler
* `<script type="text/babel">` blocks
* `app.jsx` custom `useState` router (replaced with react-router-dom)
* `tweaks-panel.jsx` (entire file, including the `useTweaks` hook)
* `mock-data.js` (every shape comes from a real API response)
* `window.QRE_*` globals (replaced with ES module imports)
* `window.QRE_NOW` fixed timestamp (replaced with `Date.now()`)
* The data-state selector that demoed healthy/warning/error/empty
  scenarios — real API status drives render branches

### 1.4 No campaign / sprint / policy controls added

The only button that triggers a backend mutation is the pre-existing
`Run preset` button on `/presets`, which calls the pre-existing
`/api/presets/{name}/run` endpoint — same behavior as before the
redesign. The seven new pages (Overview, Sprint, Campaigns, Failures,
Artifacts, Health, Version) are read-only views of existing artifacts.

### 1.5 New backend module is verifiably read-only

`dashboard/api_system_meta.py` import surface:

```python
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from flask import Flask, jsonify
```

No imports from `research.campaign_*`, `research.discovery_sprint`,
`research.candidate_*`, `agent.*`, `strategies.*`, `orchestration.*`,
`execution.*`, `automation.*`, `state.*`. The single
`subprocess.run([...])` call is constrained to
`["git", "rev-parse", "HEAD"]`. The module:

* exposes only GET routes;
* never opens, mutates, classifies, or decides anything;
* returns `{"available": false}` / null fields when artifacts are
  missing so the frontend renders an `EmptyStatePanel` instead of
  raising;
* is covered by 11 targeted tests (see §2.3) including a static
  import-surface check that fails the build if a forbidden module is
  ever imported.

---

## 2. Validation results

### 2.1 Frontend build

```
$ npm --prefix frontend run build
> tsc -b && vite build
✓ 72 modules transformed.
dist/assets/index-84hQZuwv.css   18.66 kB │ gzip:  4.19 kB
dist/assets/index-wlMgEHlc.js   235.09 kB │ gzip: 70.60 kB
✓ built in 3.97s
```

Zero TS errors. Bundle ≈ 235 KB JS + 19 KB CSS.

### 2.2 Frontend tests

```
$ npm --prefix frontend test
Test Files  4 passed (4)
     Tests 17 passed (17)
```

All pre-existing tests green:

* `src/components/__tests__/StaleArtifactBanner.test.tsx` (4 tests)
* `src/components/__tests__/ResearchIntelligenceCard.test.tsx` (6 tests)
* New `src/test/AuthFlow.test.tsx` (4 tests) — proves login form
  renders, submitting credentials calls only `/api/session/login`,
  failed login surfaces the error, no other mutating endpoints exist
  on the `api` object surface.

### 2.3 Backend tests (targeted)

```
$ pytest tests/unit/test_dashboard_api_system_meta.py -q
11 passed in 2.65s
```

Coverage of the new module:

* **GET-only**: each endpoint tested for 200 on GET and rejected on
  POST/PUT/DELETE/PATCH (Flask returns 405; the dashboard's catch-all
  handler reshapes that as 500 — the test accepts both and verifies
  the body says `Method Not Allowed`).
* **No mutation**: `test_artifact_index_does_not_mutate` snapshots
  the artifact dir before and after a GET to prove read-only.
* **Graceful degradation**: missing version file, missing artifact
  dir, missing sprint artifacts each return well-formed payloads
  rather than raising.
* **Pass-through correctness**: writing a synthetic
  `sprint_registry_latest.v1.json` round-trips through the endpoint
  unchanged.
* **Static import-surface check**:
  `test_module_import_surface_excludes_orchestration_modules` parses
  the source and fails the test if any forbidden subsystem is
  imported.

### 2.4 Existing dashboard API tests (regression)

```
$ pytest tests/unit/test_dashboard_api_public_artifact_status.py \
         tests/unit/test_dashboard_api_v310.py \
         tests/unit/test_dashboard_api_v312.py \
         tests/unit/test_dashboard_api_v313.py \
         tests/unit/test_dashboard_api_v314.py -q
30 passed in 2.33s
```

The blueprint registration order is unchanged. No regression.

### 2.5 Diff scope

```
$ git status --short  (excluding pre-existing .gitignored or untracked dirs)
 M dashboard/dashboard.py
 M frontend/src/{App.tsx,main.tsx,api/client.ts}
 M frontend/src/routes/{Candidates,Dashboard,History,Login,Presets,Reports}.tsx
?? dashboard/api_system_meta.py
?? frontend/src/api/{adapters/, system.ts}
?? frontend/src/components/{layout/, pixel/}
?? frontend/src/lib/
?? frontend/src/routes/{Artifacts,Campaigns,Failures,Health,Sprint,Version}.tsx
?? frontend/src/styles/
?? frontend/src/test/AuthFlow.test.tsx
?? tests/unit/test_dashboard_api_system_meta.py
```

All scope rules from the plan are honored.

---

## 3. Pages delivered

| Page | Route | Real APIs | Empty-state behavior |
|---|---|---|---|
| Overview | `/` | `/api/health`, `/api/research/run-status`, `/api/report/latest`, `/api/research/public-artifact-status`, `/api/research/intelligence-summary`, `/api/campaigns/digest` | Loading panel; per-section fall-through |
| Discovery Sprint | `/sprint` | `/api/research/sprint-status` (new) | `EmptyStatePanel("No Active Sprint")` when artifact missing |
| Campaigns | `/campaigns` | `/api/campaigns/registry`, `/digest`, `/queue` | `EmptyStatePanel("No Campaigns Yet")` when registry empty |
| Failure Modes | `/failures` | `/api/campaigns/evidence`, `/api/research/intelligence-summary` | Falls back to ledger summary, then `EmptyStatePanel("No Failures Recorded")` |
| Artifacts | `/artifacts` | `/api/research/artifact-index` (new), `/api/research/public-artifact-status` | `EmptyStatePanel("No Artifacts Found")` when dir empty |
| System Health | `/health` | `/api/health`, `/api/research/run-status`, `/api/research/intelligence-summary` | Per-card placeholders |
| Version / Deploy | `/version` | `/api/system/version` (new), `/api/health` | Per-card placeholders |

Existing pages (`/presets`, `/history`, `/reports`, `/candidates`)
were re-skinned with the retro design but their data flow is
identical to before.

---

## 4. CSS scoping

`frontend/src/styles/retro.css` is loaded after `styles.css` in
`main.tsx`. Every selector in the file is scoped under `.qre-app`
or a child class within the QRE shell. The `*` reset, body
typography, dot-grid and scanline backgrounds, color-palette CSS
variables, and intensity / pixelfont attribute selectors all live
under `.qre-app` ancestors. Pre-existing rules in `styles.css` (used
by login fallbacks and the legacy components inside re-skinned
pages) are unaffected.

`prefers-reduced-motion: reduce` disables coin-spin / blink /
pulse-dot / hop animations and the dot-grid scanline background.

Fonts (Press Start 2P, VT323, JetBrains Mono) load from Google
Fonts via `@import` per the approved decision. If CSP/network/
privacy issues arise, the fallback chain in each font-family
declaration drops cleanly to system mono — self-hosting is out of
scope for this release.

---

## 5. Auth flow proof (Login restyle)

`frontend/src/test/AuthFlow.test.tsx`:

* `/login` renders the new retro form with username + password
  inputs and a Sign In button.
* Submitting credentials calls only `api.login("joery", "secret")`,
  which targets `/api/session/login` — the pre-existing endpoint.
* On `{ ok: false, error: ... }` the error is rendered; no
  `api.logout` is called and no other endpoint fires.
* `Object.keys(api)` is asserted to contain no unexpected
  mutator-named functions (only `login`, `logout`, `runPreset` are
  allowed) — this guards against accidental new POST endpoints in
  follow-up edits.

`frontend/src/auth.tsx` was not modified — the auth context, probe,
login, and logout logic are byte-for-byte the same as before. Only
the visual wrapper around the form changed.

---

## 6. Rollback note

This branch lands as a single coherent change. To roll the
dashboard look back to the pre-redesign state:

```
git revert -m 1 <merge-commit-of-feat/qre-frontend-redesign>
```

The revert removes:

* the visual restyle and the seven new routes,
* the read-only `dashboard/api_system_meta.py` module + its tests,
* the blueprint registration in `dashboard/dashboard.py`.

It does NOT touch any campaign / sprint / policy / strategy code,
because none of that was modified in the first place. After a
revert the backend reverts to its pre-merge behavior with zero side
effects.

---

## 7. Sprint / campaign safety

* No sprint was started during the implementation.
* No manual campaign was started during the implementation.
* The discovery sprint artifact dir is read with filesystem
  primitives only; the orchestrator module
  (`research/discovery_sprint.py`) is never imported by the new
  blueprint or by any frontend code path.
* The new sidebar legend explicitly displays "READ-ONLY MODE — UI
  cannot mutate state. Frozen contracts protected." so operators
  see the contract at a glance.

---

## 8. Known follow-ups (NOT done in this release)

These were intentionally left out of the redesign branch to keep
scope tight:

* Optional self-hosting of pixel fonts.
* Container CPU/Mem live charts on `/health` (no existing metric
  source — the design rendered mock data; the new page renders only
  what real APIs expose).
* Operator console for sprint start/stop (out of scope by
  contract — UI is read-only).
