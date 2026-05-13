# Agent Activity Center — No-Mutation Doctrine

> **Status: design / canonical_policy_doc only.** This document
> defines the load-bearing list of forbidden client-side and
> server-side patterns under the Agent Activity Center surfaces.
> Future implementation units (B2.0b/c/d) must obey this doctrine,
> enforced by pin tests + CI checks + lint rules.
>
> Companion to [`agent_activity_center_design.md`](agent_activity_center_design.md).

---

## §1 The doctrine in one sentence

**No code path under the Agent Activity Center surfaces ever
mutates server state, opens a PR, merges, deploys, admits a queue
row, flips an env flag, writes a seed JSONL, or issues an
operator-go phrase as an authority token.** The AAC is read-only
by construction.

---

## §2 Forbidden server-side patterns

### 2.1 Route methods

Under `/api/agent-control/*` (the full prefix, not only `activity/*`):

- No `methods=["POST", …]`
- No `methods=["PUT", …]`
- No `methods=["PATCH", …]`
- No `methods=["DELETE", …]`
- No quoted-variant equivalents (`'POST'`, `'PUT'`, etc.)

`GET` and `HEAD` are the only acceptable verbs. `OPTIONS` is
implicit (Flask auto-adds it for CORS preflight).

### 2.2 Forbidden module surface for AAC server-side code

Per the aggregator schema (§2 read-only invariants) and the
api-contract pin (§9), the future B2.0b aggregator module and
the future B2.0c Flask blueprint must NOT import or reference:

- `subprocess`
- `socket`
- `urllib`, `urllib.request`, `urllib.parse`
- `requests`
- `httpx`
- `aiohttp`
- `http.client`
- `research` (QRE — disjoint domain)
- `dashboard.dashboard` (no shared mutation surface)
- `automation` (live-gate guard)
- `broker` (live-broker guard)
- `agent.risk` / `agent.execution` (capital risk guard)
- `reporting.intelligent_routing` (QRE routing)

AST-level pin in the future B2.0b / B2.0c test suite.

### 2.3 Forbidden write targets

The future B2.0b aggregator's atomic-write helper must refuse
every path whose POSIX form does not contain
`logs/development_agent_activity_timeline/`. Specifically:

- **No write** to `seed.jsonl`.
- **No write** to `generated_seed.jsonl`.
- **No write** to `delegation_seed.jsonl`.
- **No write** to any path under `research/`, `live/`, `paper/`,
  `shadow/`, `broker/`, `agent/risk/`, `agent/execution/`.
- **No write** to any frozen v1 schema file (`**/*_latest.v1.json`,
  `**/*_latest.v1.jsonl`).
- **No write** to `.claude/**`, `.github/**`, `automation/**`,
  `dashboard/dashboard.py`, no-touch paths.
- **No write** to any path the existing
  `.claude/hooks/deny_no_touch.py` and
  `.claude/hooks/deny_outside_agent_allowlist.py` already deny.

Sentinel-restricted write path mirrors the pattern of
`reporting.development_step5_loop._atomic_write_json` (sentinel:
`logs/step5_*/`) and `reporting.development_generated_lane_a18c`
(sentinel: `logs/development_generated_lane_a18c/`).

### 2.4 Forbidden invocations

The future B2.0b / B2.0c code must contain no:

- `subprocess.run` / `subprocess.Popen` / `os.system` / `os.popen`
- `shell=True` anywhere
- `gh ` invocation (with or without leading space — covers all
  GitHub CLI verbs)
- `git ` invocation (covers all version-control CLI verbs)
- `--admin` flag construction
- `--no-verify` flag construction
- `--force` / `-f` flag construction in a git context
- Direct network connection (`socket.connect`, `urlopen`,
  `requests.get`, `httpx.get`, etc.)

Source-text + AST scan in the future B2.0b / B2.0c test suite.

---

## §3 Forbidden client-side patterns

### 3.1 No mutation handlers anywhere under `frontend/agent-activity-center/**`

Under the future B2.0d PWA component tree:

- No `fetch(..., {method: "POST" | "PUT" | "PATCH" | "DELETE"})`.
- No `axios.post`, `axios.put`, `axios.patch`, `axios.delete`.
- No `XMLHttpRequest` with non-`GET` method.
- No form submission to any AAC endpoint.
- No mutation handler in any onClick / onSubmit / onChange callback
  that targets `/api/agent-control/*`.

### 3.2 `CopyOperatorPhraseButton` is clipboard-only

The component's source must:

- Use `navigator.clipboard.writeText(phrase)` only.
- **Not import** `fetch`, `axios`, `XMLHttpRequest`, or any HTTP
  client library.
- Not depend on any network module transitively.

Pin: B2.0d test asserts the component's source contains no
network-library import.

### 3.3 No approval affordances

No component named `ApprovalButton`, `Approve*`, `*ExecuteButton`,
`*MergeButton`, `*DeployButton`, `*FlipFlagButton`,
`*ApproveAndExecuteButton`, or any synonym thereof exists under
the AAC component tree.

Source-text scan in the future B2.0d test suite rejects any
file name and any exported symbol matching those patterns.

### 3.4 No edit affordances on artefact views

The `RawArtifactDrawer` component is read-only. No textarea, no
contenteditable, no `<input type="text">` or `type="file">`
elements appear inside the drawer's render tree.

---

## §4 Forbidden cross-system interactions

### 4.1 No approval-inbox mutation

The AAC may read the operational digest and surface human-action
items. It must **never**:

- Write to `logs/approval_inbox/*`.
- Update an approval-inbox row's status from the UI.
- Surface an "approve" button that hits the existing approval
  inbox.

### 4.2 No queue admission

The AAC may surface queue rows. It must **never**:

- Promote an A18c row.
- Admit a generated-lane row to the queue.
- Write to `logs/development_work_queue/*`.

### 4.3 No PR / merge / deploy authority

The AAC may surface merge candidates and PR dry-run shapes. It
must **never**:

- Open a PR.
- Mark a PR ready (lift draft state).
- Merge a PR.
- Trigger a deploy.
- Roll back a deploy.

### 4.4 No Step 5 flag mutation

The AAC may surface Step 5 substage and implementation-allowed
state. It must **never**:

- Flip `step5_implementation_allowed` (which is `Final` `False`
  in the module source anyway — the constraint is doubly enforced).
- Flip `STEP5_ENABLED_SUBSTAGE` (which is `Final` `"none"` in the
  module source anyway).
- Issue any operator-go phrase as an authority token.

### 4.5 No token mint / verify

The AAC must **never**:

- Mint an approval token.
- Verify an approval token.
- Surface a UI for either operation.

Approval tokens are minted out-of-band; the visual control plane
never surfaces a mint affordance.

### 4.6 No Level 6 enablement

Level 6 is permanently disabled per ADR-015 §Doctrine 1. The AAC
must **never**:

- Surface a UI affordance to re-enable Level 6.
- Send a request to re-enable Level 6.
- Display Level 6 as "available" or "enableable" in any way. The
  System Safety screen MUST display Level 6 as "permanently
  disabled" with a red banner.

---

## §5 Enforcement plan

### 5.1 Pin tests (mandatory in future implementation units)

| Test | Lives in | Pins |
|---|---|---|
| `test_aggregator_imports_clean` | `tests/unit/test_development_agent_activity_timeline.py` (future B2.0b) | AST scan: no forbidden imports. |
| `test_aggregator_atomic_write_guard` | same | Sentinel-restricted write path. |
| `test_aggregator_no_seed_writes` | same | Source-text scan for `seed.jsonl` / `generated_seed.jsonl` / `delegation_seed.jsonl` write paths. |
| `test_blueprint_only_get_methods` | `tests/unit/test_api_agent_control_activity.py` (future B2.0c) | Flask URL rule introspection: all routes under prefix have method set `{"GET"}` (plus implicit `HEAD`/`OPTIONS`). |
| `test_blueprint_source_no_post_put_patch_delete` | same | Source-text scan for `methods=["POST"`, etc. |
| `test_pwa_copy_phrase_clipboard_only` | `frontend/agent-activity-center/__tests__/CopyOperatorPhraseButton.test.tsx` (future B2.0d) | Component source contains no `fetch` / `axios` / `XMLHttpRequest` import. |
| `test_pwa_no_mutation_handlers` | same suite | Grep across component tree for any non-`GET` HTTP method targeting `/api/agent-control/*`. |
| `test_pwa_no_approve_button_components` | same suite | No file name or exported symbol matching `Approve*` / `*ExecuteButton` / `*MergeButton` / `*DeployButton`. |

### 5.2 CI checks (mandatory in future implementation units)

- `lint(ruff)` — already in the CI matrix. Future B2.0b / B2.0c modules pass.
- `governance_lint.py` — already in the CI matrix. Future docs / module updates pass.
- `hook-tests (governance hooks)` — already in the CI matrix. Future writes obey `deny_no_touch.py` and `deny_outside_agent_allowlist.py`.
- **New (future B2.0c)**: blueprint-method audit. A CI step that imports the dashboard blueprint registry and asserts the closed verb set under `/api/agent-control/activity/*`.
- **New (future B2.0d)**: ESLint rule (custom) forbidding non-`GET` HTTP method literals in any file under `frontend/agent-activity-center/**`.

### 5.3 Code review checklist (operator-authored)

When reviewing any future PR that lands AAC code, the operator
asks:

1. Does any new file under `frontend/agent-activity-center/**` import a network library other than `fetch` constrained to `GET`?
2. Does any new Flask route under `/api/agent-control/*` declare a method other than `GET`?
3. Does any new module import the aggregator's write helper for a non-canonical path?
4. Does any commit add a button labelled `Approve`, `Execute`, `Merge`, `Deploy`, `Flip`, or any synonym?
5. Does any commit add a push-notification publisher? (If yes, route to B2.0e review.)
6. Does any commit reference `step5_implementation_allowed = True` or `STEP5_ENABLED_SUBSTAGE = "5...`? (Reject unconditionally.)

---

## §6 Why this doctrine is load-bearing

ADR-015 §Doctrine 1 makes Level 6 permanently disabled. ADR-015
§Doctrine 4 makes live-trading code human-only. ADR-015
§Doctrine 7 establishes the self-protected layer. The Agent
Activity Center is the **visible** control plane the operator
uses to verify those doctrines in real time.

A mutation endpoint hiding under `/api/agent-control/*` would
silently subvert the visual reassurance the operator relies on.
The doctrine in this document is the structural guarantee that
no such endpoint can exist without an explicit governance-bootstrap
PR explicitly weakening it — which would itself be visible in
docs/governance/ history.

The doctrine also generalises beyond the AAC. The patterns above
(closed verb set under a read-only prefix, sentinel-restricted
write paths, AST-pinned forbidden imports, clipboard-only copy
components) are reusable for any future read-only operator
surface.

---

## §7 Scope of this doctrine

### 7.1 In scope

- All code under `frontend/agent-activity-center/**` (future).
- All code under `dashboard/api_agent_control_activity*.py` (future).
- The aggregator module `reporting/development_agent_activity_timeline.py` (future).
- The push-notification body builder for AAC notifications (future).

### 7.2 Out of scope

- Existing dashboard mutation endpoints under other route prefixes
  (those are governed by their own contracts; this doctrine does
  not weaken or strengthen them).
- Existing approval-inbox surfaces (governed by
  `docs/governance/approval_inbox/`).
- Existing approval-token surfaces (governed by
  `docs/governance/approval_token_gate.md`).
- The QRE feature build track (disjoint).

---

## §8 What this doctrine is NOT

- Not a request to remove any existing mutation endpoint elsewhere
  in the dashboard.
- Not a request to weaken any existing safety hook.
- Not an authorisation for any future PR to add a mutation
  endpoint under any other route prefix.
- Not a substitute for the existing no-touch / autonomy / authority
  doctrines — it complements them.
- Not a PWA component contract — that lives in [`agent_activity_center_design.md`](agent_activity_center_design.md) §6.
- Not a push-notification body specification — see [`agent_activity_center_push_notification_safety.md`](agent_activity_center_push_notification_safety.md).
