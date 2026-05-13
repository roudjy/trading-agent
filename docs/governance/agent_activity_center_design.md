# Agent Activity Center — Design Specification

> **Status: design / canonical_policy_doc only.** This document is
> the canonical mobile-first PWA-ready design specification for the
> Agent Activity Center (AAC). It is **not** an implementation. It
> introduces **zero** runtime authority, **zero** mutation endpoints,
> **zero** new modules, **zero** new env gates. Implementation lives
> in future units (B2.0b aggregator, B2.0c Flask blueprint, B2.0d
> PWA frontend, B2.0e push-notification body lint hook), each of
> which is a distinct future PR with its own operator-go phrase.
>
> Written 2026-05-13 against `main @ <merge-sha-of-this-PR>` as the
> Visual ADE Control Plane anchor for Revised Batch 2 (`A15` in
> `docs/roadmap/autonomous_development.txt`). Predecessor reading list:
> [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md),
> [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md),
> [`docs/governance/autonomy_ladder.md`](autonomy_ladder.md),
> [`docs/governance/no_touch_paths.md`](no_touch_paths.md),
> [`docs/governance/execution_authority.md`](execution_authority.md),
> [`docs/governance/step5_design.md`](step5_design.md),
> [`docs/governance/github_pr_lifecycle.md`](github_pr_lifecycle.md),
> [`docs/governance/frontend_agent_control_layer_roadmap.md`](frontend_agent_control_layer_roadmap.md).

---

## §1 Status & scope

### 1.1 Status

`design / canonical_policy_doc only`. The matching canonical-roadmap
anchor is [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt)
§A15. Implementation requires four separate operator-go phrases
(B2.0b / B2.0c / B2.0d / B2.0e) issued in future PRs.

### 1.2 What B2.0 ships

- This document.
- [`agent_activity_center_aggregator_schema.md`](agent_activity_center_aggregator_schema.md) — closed schema for the future aggregator output.
- [`agent_activity_center_api_contract.md`](agent_activity_center_api_contract.md) — 6 read-only `GET` endpoint contracts.
- [`agent_activity_center_no_mutation_doctrine.md`](agent_activity_center_no_mutation_doctrine.md) — forbidden client-side handlers + server-side verbs.
- [`agent_activity_center_push_notification_safety.md`](agent_activity_center_push_notification_safety.md) — push body safety pins (no `required_phrase`, no secrets, no approval on tap).
- One additive canonical-roadmap entry (§A15).
- One structural pin test (file-existence + load-bearing-literal pins).

### 1.3 What B2.0 does NOT ship

- No module under `reporting/`, `dashboard/`, `frontend/`, `automation/`, `agent/`, `broker/`, `research/`, `scripts/`.
- No aggregator implementation. The artefact `logs/development_agent_activity_timeline/latest.json` is **specified** but **not emitted** by any code that lands in B2.0.
- No Flask blueprint, no route registration, no dashboard wiring.
- No PWA frontend code (no React component, no service worker, no manifest).
- No recurring-maintenance entry.
- No env flip.
- No `step5_implementation_allowed` flip; stays `Final` `False`.
- No `STEP5_ENABLED_SUBSTAGE` flip; stays `Final` `"none"`.
- No autonomy-ladder amendment. Level 6 stays permanently disabled per ADR-015 §Doctrine 1.
- No `git` / `gh` / `subprocess` / network code path.
- No mutation endpoint, no approval button, no push-notification publisher.
- No writes to `seed.jsonl`, `delegation_seed.jsonl`, `generated_seed.jsonl`.
- No edits to `.claude/**`, `.github/**`, frozen v1 schemas, ADRs, no-touch paths, `tests/regression/`, live/paper/shadow/risk/broker/execution paths.

### 1.4 Audience

- The repo operator, who reads this spec to confirm the design before authorising implementation.
- Future implementation-agent runs (B2.0b/c/d/e), which build against this spec.
- External reviewers of the visual control plane's safety posture.

---

## §2 Design principles

1. **Read-only by construction.** Every button labels its effect: *"View trace"*, *"Copy phrase"*, *"Mark reviewed (local)"*. No "Approve and execute" anywhere.
2. **Calm operator console.** Dense but quiet. Red is reserved for invariant drift AND the Level 6 "permanently disabled" banner only. Amber for human-needed. Neutral grays / accent blue for everything else.
3. **Status-driven.** All status surfaces use closed vocabularies (§10). No free-text status. Unknown enum values render neutral gray + console warning, never crash.
4. **Mobile-first.** Operator can be on-call. Today + Inbox must answer "is anything broken?" in 10 seconds on a phone.
5. **Every visible thing links back.** Every card and event links to at least one source artefact path. Audit trail is one tap away.
6. **Graceful absence.** Missing, stale, or malformed artefacts render visibly without breaking the page.
7. **Surface ≠ approval.** A "merge candidate" is a *candidate*. It is not "ready to merge". The visual control plane never closes a gate.

---

## §3 Information architecture

Three normalised concepts power every view:

### 3.1 WorkItem

A logical development unit. One per roadmap entry / queue row / generated-lane row / bugfix candidate / Step 5 cycle / PR / merge candidate.

Required fields: `item_id`, `title`, `source_kind`, `source_path`, `current_stage`, `owner_role`, `risk`, `human_needed`, `latest_verdict`, `next_action`, `updated_at`, `summary`. Optional: `event_ids[]` for cross-reference.

### 3.2 AgentEvent

A timeline event linked to a WorkItem.

Required fields: `event_id`, `item_id`, `timestamp`, `agent_role`, `module`, `event_type`, `summary`, `decision`, `reason`, `artifact_path`, `severity`.

### 3.3 HumanAction

An operator attention item.

Required fields: `action_id`, `item_id`, `severity`, `title`, `why_required`, `safe_to_ignore`, `copy_only`, `source_artifact_path`, `suggested_role`, `created_at`. Optional: `required_phrase` (string, copy-only, never surfaced in push bodies — see [`agent_activity_center_push_notification_safety.md`](agent_activity_center_push_notification_safety.md)).

### 3.4 Eight views compose the three concepts

| View | Mobile role | Desktop role |
|---|---|---|
| **Today** | mobile homepage / cockpit | metric tiles + sections |
| **Approval Inbox** | human-action queue (copy-only) | filtered list |
| **Pipeline Board** | horizontal stage chips + stacked active-stage cards | 11-column kanban |
| **WorkItem Trace** | full-screen vertical timeline | left timeline + right inspector |
| **Agents** | role cards w/ 5-stat strip | matrix table |
| **Artefact Explorer** | grouped path list + bottom-sheet drawer | left list + right drawer |
| **System Safety** | invariant cards + "what this UI cannot do" | same |
| **Design Spec** | in-app browsable doc | same |

---

## §4 Mobile-first navigation

### 4.1 Mobile

- **Bottom tab bar** (always visible, 5 primaries): Today · Inbox · Pipeline · Agents · More.
- **"More" hub** expands to 4 drilldowns: Trace · Artefacts · Safety · Spec.
- **Top bar per screen**: title, optional back chevron, search and filter icons. No hamburger.
- **Safe-area insets**: status bar respected; home indicator clearance reserved.
- **Touch targets**: ≥44×44 px (see §12).

### 4.2 Desktop (≥1100 px)

- **Left sidebar** with all 8 entries grouped into "Cockpit" (Today · Inbox · Pipeline · Agents) + "Drilldown" (Trace · Artefacts · Safety · Spec).
- **Persistent top invariant strip** showing Level 6 pill (red, permanently disabled), Step 5 substage, A18c lane, live merge state, N5b live-execute state, agent service health.
- **Main content** fills the rest.
- **Right-side inspector** is available on Trace (and may be added to Pipeline later).

### 4.3 Breakpoints

| Range | Mode | Layout |
|---|---|---|
| `≤599 px` | mobile (default phone) | bottom tab + top bar |
| `600–959 px` | mobile-wide | single column, sticky filters |
| `≥960 px` | tablet | kanban appears; sidebar collapsed to icons |
| `≥1100 px` | desktop | sidebar labels visible, full invariant strip |

### 4.4 Navigation pins

- No hamburger menu anywhere. Discoverability beats density.
- Every screen reachable in ≤2 taps from Today.
- Deep-links (`/inbox`, `/pipeline?stage=needs_human`, `/item/<id>`, `/safety`) survive PWA cold-start.

---

## §5 Screen-by-screen specification

### 5.1 Today (mobile homepage)

Layout (mobile, top → bottom):

1. Top bar: *Today*, sub *Mon · May 13 · read-only cockpit*.
2. Horizontal scrollable compact invariant strip: `L6 disabled` · `S5.implementation` · `a18c on`.
3. Freshness banner (Fresh / Stale / Offline) with refresh icon.
4. Metric tile grid (2×3):
   - Needs human
   - Blocked
   - Merge candidate
   - CI feedback
   - Planned
   - Dry-run ready
   - Tile tap deep-links to filtered Pipeline/Inbox.
5. Needs-human section — up to 3 attention cards inline, "see all N in inbox" button if more.
6. Merge candidates section, with explicit reminder: *"Live merge is permanently disabled. Surfaced for operator visibility only."*
7. CI feedback section.
8. Blocked section.
9. Recent activity — last 6 events with role + module + timestamp.
10. Read-only footer disclosure.

**10-second test**: if `needs_human ≥ 1`, that section sits above the fold on phone.

Desktop layout reshuffles the same components: tiles span a wider grid; right column shows recent activity in a sticky inspector.

### 5.2 Approval Inbox

Filter pills: `All / Required / Informational`.

Each **AttentionCard** shows:

- Title, stage badge, severity, risk, suggested role.
- Plain-language reason human action is required.
- If required: **copy operator-go phrase** pill (dashed amber border).
- If informational: a no-phrase informational note.
- Source artefact path · relative timestamp.
- Actions: *View trace*, *Mark reviewed (local)*. **No "Approve" button.**

Mark reviewed is local-only — it dims the card in this session. It does **not** approve, gate, or unblock any backend action. Operator-go phrases must be issued out-of-band.

Disclosure footer reasserts the local-only nature.

### 5.3 Pipeline Board

**Stages (11, closed-vocab):**

`discovered → queued → delegated → planned → dry_run_ready → pr_proposed → pr_opened → ci_feedback → needs_human → merge_candidate → done_blocked`

**Desktop**: horizontal kanban, 11 columns × 260 px wide, scrollable.

**Mobile**: horizontal stage chip strip + stacked WorkItem cards for the active stage. Tapping a chip changes the active stage; horizontal scroll reveals all 11 chips.

Empty stages render their canonical phrase. Example: `done_blocked` when empty renders **"No promotable candidates"** — never "0 errors", never red. The empty state is the *expected* steady state when invariants block promotion.

### 5.4 WorkItem Trace

Header card:

- Stage badge, human-needed badge (if applicable), risk badge, source-kind badge.
- Item title, summary.
- Metadata grid: `item_id`, `owner_role`, `source_path`, `latest_verdict`, `next_action`, `updated_at`.
- **CopyOperatorPhraseButton** pill if `human_actions[].required_phrase` is set (clipboard-only, no network).

Below: vertical timeline.

**TimelineNode anatomy**: rail dot (severity-tinted); header row `ts · module · decision badge · agent_role badge · invariant badge (if relevant)`; summary headline; reason line; artefact path with raw-JSON drilldown.

Footer: source-artefacts list (deduped from `agent_events[].artifact_path`).

### 5.5 Agents

**Desktop**: dense matrix table with columns `Role · New · Planned · Blocked · Human · PR-ready · Last action`.

**Mobile**: one card per role with a 5-cell mini-stats row and the most recent action below. Card header carries the role name (mono) and last-action chip.

Closed-vocab role list (16, see [`step5_design.md`](step5_design.md) §A8): `product_owner · strategic_advisor · quant_research_architect · planner · architecture_guardian · ci_guardian · implementation_agent · frontend_agent · test_agent · determinism_guardian · evidence_verifier · observability_guardian · deployment_safety_agent · adversarial_reviewer · release_gate_agent · human_operator`.

### 5.6 Artefact Explorer

Top: 4 summary tiles (Fresh / Stale / Malformed / Read-only).

Below: grouped file list. Groups: `queue · loops · step5 · gates · generated · digest · seed`.

Each row shows path (mono, truncated), sub-line (row count or parse error), freshness badge, optional "summary" badge, relative age. Tap opens **RawArtifactDrawer** (bottom sheet on mobile, right inspector on desktop) with sampled raw JSON. The drawer is read-only; no edit affordances.

The `seed` group includes `generated_seed.jsonl` with an explicit `read_only_warning` chip: **"Read-only · UI must not write"**.

### 5.7 System Safety

Top: red-tinted Level 6 banner: **"Level 6 — permanently disabled. Level 6 capabilities cannot be re-enabled by this UI or any agent. This is a build-time invariant."**

Below: invariant cards in a 2-column grid (mobile) / wider grid (desktop). Each card carries:

- Label (uppercase muted)
- Value (mono, tone-tinted: green for `on`, gray for `off`, red for `danger_off`, blue for `info`)
- Status swatch (top-right corner)
- Detail line (one sentence)

Closed invariant list (initial 9; can be extended additively):

- `level_6` (danger_off)
- `step5_substage` (info)
- `step5_implementation_allowed` (off)
- `live_merge_implemented` (off)
- `deploy_coupled` (off)
- `a18c_enabled` (on)
- `a18b_writer_enabled` (off)
- `n5b_live_execute` (off)
- `agent_service` (on)

Bottom: explicit list of "what this UI cannot do":

- Approve or execute any gated operation
- Admit any work to the queue or generated lane
- Open, merge, or close a pull request
- Trigger or roll back a deploy
- Flip `step5_implementation_allowed`
- Mint or verify tokens
- Write to `seed.jsonl`, `generated_seed.jsonl`, or `delegation_seed.jsonl`
- Re-enable Level 6 (Level 6 stays permanently disabled per ADR-015 §Doctrine 1)

### 5.8 Design Spec (in-app)

Browsable rendering of this document. Built from the same canonical Markdown source. No external links rewritten; cross-references render as anchors.

---

## §6 Component library

13 atoms / patterns. Built once, reused across screens. All accept a `size` where it makes sense (`xs / md / lg`) and a `tone` from the closed vocabulary.

### 6.1 InvariantStrip

Horizontal row of invariant pills. Renders compact on mobile (3 pills: L6, substage, a18c) and full on desktop (6 pills + agent service). Each pill tooltip reveals the long-form description. **L6 pill is always present and red-tinted.**

### 6.2 MetricTile

Props: `label, value, sub, tone, icon, onClick`. Tone changes the value color and the left accent stripe. Tap navigates to a filtered list. Touch target 88×88+.

### 6.3 AttentionCard

Used in Inbox and Today's Needs-human section. Always amber-left-accent. Includes copy-phrase pill when `required_phrase` is set; informational note otherwise. Reviewed state dims the card; locally persisted in session only.

### 6.4 WorkItemCard

Used in Pipeline and on Today's blocked/merge/CI sections. Compact (mobile chip-row variant) and large (active-stage variant). Always exposes `owner_role` and `latest_verdict` in mono.

### 6.5 PipelineStage (column)

Header: stage label, item count. Body: scrollable WorkItemCard stack. Empty body shows the canonical "—" or stage-specific phrase. Column width 260 px desktop.

### 6.6 TimelineNode

Rail dot (severity tint), header row (`ts · module · decision badge · role · invariant badge`), summary, reason, artefact, raw-JSON toggle. Spacing 28 px between nodes.

### 6.7 AgentRoleCard

Role name (mono), last-action chip in header, 5-stat strip (`new · planned · blocked · human · PR-ready`), single-line latest-action footer.

### 6.8 ArtefactHealthRow

Path (mono, truncated), sub-line (row count or parse error), freshness badge, optional "summary" badge, relative age. Tap opens RawArtifactDrawer.

### 6.9 FreshnessBadge

States: `fresh` (green), `stale` (amber), `malformed` (red), `missing` (gray, italic).

### 6.10 RiskBadge · DecisionBadge · SeverityBadge · StageBadge

All share the Badge atom; each carries a closed vocabulary (see §10). Sizes `xs / md / lg`.

### 6.11 CopyOperatorPhraseButton

**Clipboard-only.** Dashed amber pill with mono code + Copy. On click: `navigator.clipboard.writeText(phrase)` + ✓ flash for 1.6 s. **No backend call.** **No network request.** Pinned by future B2.0d test that the component's source contains no `fetch`/`XMLHttpRequest`/`axios` import.

### 6.12 RawArtifactDrawer

Bottom sheet (mobile) / right inspector (desktop). Shows artefact metadata + sampled raw JSON, or the parse error if malformed. Read-only — no edit affordances.

### 6.13 EmptyState · StaleDataBanner

**EmptyState**: glyph, title, optional body. **StaleDataBanner**: 3 modes (fresh / stale / offline) with optional refresh button.

---

## §7 Data contract for the aggregator

The visual control plane consumes a single canonical read-only artefact:

```
logs/development_agent_activity_timeline/latest.json
```

The aggregator (future unit B2.0b) reads the existing ADE-core artefacts and writes its own `latest.json`. **It never writes to** `seed.jsonl`, `generated_seed.jsonl`, or `delegation_seed.jsonl`.

See [`agent_activity_center_aggregator_schema.md`](agent_activity_center_aggregator_schema.md) for the full closed schema, including per-record shapes for WorkItem, AgentEvent, HumanAction, ArtifactHealth, and InvariantStatus.

Read-only invariant pin (future B2.0b test): the aggregator's atomic-write helper refuses every path whose POSIX form does not contain `logs/development_agent_activity_timeline/`.

---

## §8 Read-only API surface

All endpoints are `GET`, read-only, return a slice of the canonical artefact. No `POST`, `PUT`, `PATCH`, or `DELETE` exists anywhere under `/api/agent-control/*`.

| Endpoint | Response shape (summary) |
|---|---|
| `GET /api/agent-control/activity/today` | `{ counts, needs_human[], merge_candidate[], ci_feedback[], blocked[], recent_events[], freshness, invariant_status }` |
| `GET /api/agent-control/activity/items?stage=&owner_role=&human_needed=&updated_since=` | `{ work_items[], freshness }` |
| `GET /api/agent-control/activity/items/<item_id>` | `{ work_item, agent_events[], human_actions[], artefacts_referenced[] }` |
| `GET /api/agent-control/activity/agents` | `{ rows: [{ role, new, planned, blocked, needs_human, pr_ready, last_action }] }` |
| `GET /api/agent-control/activity/artifacts` | `{ artifact_health[] }` |
| `GET /api/agent-control/activity/invariants` | `{ invariant_status[] }` |

HTTP semantics: `Cache-Control: private, max-age=10`; `ETag` based on `generated_at_utc`; `304` on identical snapshot.

See [`agent_activity_center_api_contract.md`](agent_activity_center_api_contract.md) for the full contract, including authentication model, error responses, and the closed verb-set pin.

---

## §9 PWA / offline / push behaviour

- **Installable app shell.** Manifest + service worker. Shell pre-cached; data fetched fresh.
- **Offline cache.** Last `activity/today` response cached. On launch with no network, app shows cached snapshot + *"Offline · last snapshot {age}"* banner.
- **Background refresh.** 60 s heartbeat when foregrounded. Banner shows a thin loading line during refresh; never blocks the UI.
- **Stale data is visually obvious.** Both globally (banner) and per-artefact (FreshnessBadge).
- **Push notifications (future, read-only).** Strategy: server publishes "needs_human +1" pings; the tap deep-links to `/inbox` or `/item/<id>`. **The notification body never contains the operator-go phrase or any secret.** Body example: *"1 new item needs your review · release_gate_agent · medium risk"*. Copy-phrase is available only inside an authenticated dashboard session.
- **Notification tap never approves.** Tapping always opens a read-only detail view.

See [`agent_activity_center_push_notification_safety.md`](agent_activity_center_push_notification_safety.md) for the load-bearing push body doctrine.

---

## §10 Status vocabularies

All vocabularies are closed sets. Unknown values fall back to neutral gray. Adding a value requires a code change pinned by an updated test.

| Domain | Values |
|---|---|
| `stage` | `discovered · queued · delegated · planned · dry_run_ready · pr_proposed · pr_opened · ci_feedback · needs_human · merge_candidate · done_blocked` |
| `severity` | `info · warn · human · error` |
| `decision` | `queue · delegate · plan · generate · approve_dry_run · require_human · flag · flag_flaky · quarantine · review · rerun · surface · advise_merge · no_op · ingest · annotate` |
| `risk` | `low · medium · high · critical` |
| `freshness` | `fresh · stale · missing · malformed` |
| `artifact_health` | `ok · stale · malformed · missing · unreadable` |
| `human_action_type` | `operator_go_required · review_recommended · copy_only · informational` |
| `invariant_state` | `on · off · danger_off · info · unknown` |

---

## §11 User flows

### 11.1 Morning open

1. Operator opens PWA → Today.
2. Within 2 s the freshness banner + invariant strip render from cache.
3. Within 4 s the live snapshot arrives; tiles animate to current counts.
4. Operator scans *Needs human* tile; if zero, scrolls to Recent activity. If non-zero, taps the tile.

### 11.2 Approving (NOT approving in-UI — surfacing only)

1. Inbox → tap AttentionCard → View trace.
2. Trace shows event timeline; operator reads decisions and invariants.
3. Operator copies the operator-go phrase (or notes that none is required).
4. **Operator issues the phrase through the existing out-of-band operator channel.** The UI plays no role beyond surfacing.
5. (Optional) returns to Inbox → Mark reviewed (local). Card dims for the session.

### 11.3 Tracing a roadmap item

1. Today → Recent activity → tap event linked to roadmap item.
2. Trace renders timeline starting at the roadmap discovery event, through addendum, queue, delegation, Step 5 plan, adversarial review, release-gate verdict.
3. Each node exposes raw JSON drilldown for audit.

### 11.4 Verifying no autonomous merge/deploy

1. More → System Safety.
2. Confirm L6 disabled banner; `live_merge_implemented = false`; `deploy_coupled = false`; `n5b_live_execute = false`.
3. Optionally Pipeline → "Merge candidate" column to confirm items there have no autonomous progression.

### 11.5 Inspecting a blocked item

1. Today → Blocked section → tap card → Trace.
2. Timeline shows the blocking event (often a release-gate verdict `require_human` or a promotion-report `admission_decision=needs_human`).
3. Operator reads the invariant badge on the blocking node to confirm *why*.

### 11.6 Future push notification flow

1. Push arrives: *"1 new item needs your review · release_gate_agent · medium risk"*.
2. Tap → deep-link to `/item/wi_...` inside the authenticated app shell.
3. Operator authenticates (session cookie). The card renders with the copy-phrase pill *inside* the app — never inside the notification.

### 11.7 Offline on mobile

1. Operator launches PWA, no network.
2. Cached `activity/today` renders; banner reads *"Offline · showing last cached snapshot · age {N}m"*.
3. All buttons remain rendered. Trace pages load from cache when the item exists in the snapshot; otherwise show *"Not in last cached snapshot"*.
4. No copy-phrase is hidden by offline mode — phrases are already part of the cached snapshot — but operator-go remains out-of-band, so connectivity is irrelevant.

---

## §12 Accessibility

- Target sizes ≥ 44×44 px for all tap targets.
- **Color never used as the only signal** — every status pill carries a label and an optional dot/icon.
- Focus rings: 2 px solid `--accent` with 2 px offset, visible on all interactive elements.
- Live regions: freshness banner uses `aria-live="polite"`. Push-driven updates announce *"N new items"*.
- Reduced motion: skeleton pulse and entry transitions respect `prefers-reduced-motion`.
- Dark + light themes both meet WCAG AA on body text (4.5:1) and AA-large on metric values.
- Mono code blocks are selectable; copy actions also work via long-press.
- All icons that carry meaning have an adjacent label or `aria-label`.

---

## §13 Error / empty / stale / loading states

- **Loading**: skeletons that match the metric tile grid + 3 card placeholders. No spinners.
- **Empty** (genuinely zero):
  - Inbox: *"Inbox zero — no operator attention items right now."*
  - Today / Needs-human: *"Nothing needs you right now."*
  - Pipeline / Done-Blocked when `promotable_row_count=0`: *"No promotable candidates"* (NOT an error).
- **Stale**: amber banner with oldest age. Individual artefacts show stale FreshnessBadge inline.
- **Malformed**: artefact shows red *"malformed"* badge. The row stays visible. Detail drawer shows the parse error and notes *"quarantined · lane unaffected"*.
- **Missing** artefact: row appears italic with *"missing"* badge; never breaks the page.
- **Offline**: red-tinted banner; last-snapshot age front and centre; no refresh icon.
- **Error** (aggregator crash): red banner *"Aggregator failed to generate snapshot — showing last good"* with a "see logs" link to the artefact explorer.

---

## §14 Design tokens

### 14.1 Colour (OKLCH, dark default + light override)

| Token | Role |
|---|---|
| `--bg / --bg-2` | Page and shell backgrounds |
| `--surface / --surface-2 / --surface-hi` | Card surfaces (three depths) |
| `--border / --border-2` | Hairlines (default + emphasised) |
| `--text / --text-2 / --text-3 / --text-4` | Foreground (four steps of mute) |
| `--accent / --accent-2` | Active / info (calm blue) |
| `--human / --human-bg` | Human-needed (amber) |
| `--blocked / --blocked-bg` | Blocked (muted red) |
| `--danger` | Invariant drift / Level 6 (sharper red) — restricted use |
| `--merge / --merge-bg` | Merge candidate (green) |
| `--planned / --planned-bg` | Planned (lavender) |
| `--stale` | Stale (yellow-brown) |
| `--disabled` | Disabled controls (neutral) |

Theme: dark default; `html[data-theme="light"]` override.

### 14.2 Type

- **Sans**: Geist (300 / 400 / 500 / 600 / 700).
- **Mono**: Geist Mono (400 / 500 / 600).
- Font features: `cv11`, `ss01`, `ss03`.
- Mono used for: artefact paths, item IDs, module versions, invariant values, operator-go phrases, timestamps.

### 14.3 Radius

- `--radius-sm: 6px` — chips, small badges.
- `--radius: 10px` — cards, buttons.
- `--radius-lg: 14px` — primary containers.

### 14.4 Shadows

- `--shadow-1` — inset hairline + small lift (cards in default state).
- `--shadow-2` — inset hairline + richer lift (elevated cards, drawers).

### 14.5 Density

`--density: 1` custom property. Future implementation units may expose a density toggle.

### 14.6 Naming conventions

- **CSS**: BEM-ish (`.btn--ghost`, `.card--accent-human`, `.badge--xs`).
- **React**: PascalCase function components (`AttentionCard`, `TimelineNode`).
- **CSS classes**: lowercase-dash (`.tr-rail`, `.am-table`).
- **Closed-vocab string tokens**: snake_case (`needs_human`, `merge_candidate`).
- **Artefact paths**: canonical `logs/<group>/<name>.json` form.
- **Module version anchors**: snake_case prefix + dotted version (`wq.v4.2`, `s5.v6.1`, `a18c.v1.3`).

---

## §15 Artefact-to-screen mapping

| Source artefact (existing on `main`) | Surfaces on | Group | source_kind |
|---|---|---|---|
| `logs/development_work_queue/latest.json` (A8) | Today / Pipeline / Trace / Artefacts | queue | `work_queue` |
| `logs/development_delegation/latest.json` (A11) | Pipeline / Trace / Artefacts | queue | `delegation` |
| `logs/development_bugfix_loop/latest.json` (A10) | Inbox / Pipeline / Trace / Artefacts | loops | `bugfix_loop` |
| `logs/development_release_gate/latest.json` (A9) | Today / Inbox / Trace / Artefacts | gates | `release_gate` |
| `logs/step5_loop/latest.json` (A14) | Pipeline / Trace / Artefacts | step5 | `step5_loop` |
| `logs/step5_plan/<cycle_id>.json` + `history.jsonl` | Trace / Artefacts | step5 | embedded in `step5_loop` |
| `logs/development_generated_lane_a18c/latest.json` (A18c) | Pipeline / Trace / Artefacts | generated | `generated_lane_a18c` |
| `logs/development_generated_lane_promotion_report/latest.json` (A18 phase 5a) | Today (blocked) / Trace / Artefacts | generated | `generated_lane_promotion` |
| `logs/development_merge_preflight/latest.json` (N5b Phase 1) | Today (merge candidate) / Trace / Artefacts | gates | `merge_preflight` |
| `logs/development_operational_digest/latest.json` (A12) | Today / Artefacts | digest | `operational_digest` |
| `logs/step5_ci_feedback/<timestamp>.json` (future B2.6) | Today (CI feedback) / Trace / Artefacts | step5 | `ci_feedback` |
| `generated_seed.jsonl` (READ-ONLY warning) | Artefacts only | seed | n/a |
| Future `logs/development_addendum_loop/latest.json` (out of scope for B2.0) | Artefacts (handles malformed gracefully) | loops | `addendum_loop` |

All A8/A9/A10/A11/A12/A13/A14/A18a/A18b/A18c/A18-promotion/N5b-Phase-1 artefacts already exist on `main`. **B2.0 introduces no new upstream artefact**; the aggregator output (`logs/development_agent_activity_timeline/latest.json`) is specified here and emitted by future B2.0b.

---

## §16 Implementation handoff (future units)

| Unit | Purpose | Operator-go phrase (proposed) |
|---|---|---|
| **B2.0b** | Aggregator module (`reporting/development_agent_activity_timeline.py`). Read-only emitter writing `logs/development_agent_activity_timeline/latest.json`. Default-enabled scheduling entry in `reporting/recurring_maintenance.py` (LOW risk, no_gh, 30-min cadence; follows B1.1/B1.2/B1.4 pattern). | `GO Batch 2 Unit B2.0b aggregator module` |
| **B2.0c** | Read-only Flask blueprint exposing the 6 GET endpoints under `/api/agent-control/activity/*`. CI check + pin tests forbid any new mutation route under that prefix. | `GO Batch 2 Unit B2.0c Flask blueprint` |
| **B2.0d** | `frontend/` PWA implementation (React 18 + Vite, OKLCH tokens, service worker, manifest, 8 screens, 13 components). Pins: clipboard-only `CopyOperatorPhraseButton`, no `fetch` in notification body builders, no mutation handlers. | `GO Batch 2 Unit B2.0d PWA frontend` |
| **B2.0e** | Push-notification body lint hook. Source-text + AST scan rejects `required_phrase`, `operator_go_phrase`, `api_key`, `secret`, `token`, `bearer` token literals inside any module that imports the push library. | `GO Batch 2 Unit B2.0e push body lint` |

Each is a distinct future PR with its own operator-go phrase. **None are part of B2.0.**

---

## §17 Non-goals (explicit; load-bearing)

- **No autonomous execution of any kind.**
- **No queue admission, no PR creation, no merge, no deploy** from the UI.
- **No Step 5 flag flip.** `step5_implementation_allowed` stays `Final` `False`. `STEP5_ENABLED_SUBSTAGE` stays `Final` `"none"`.
- **No token mint / verify UI.** Approval tokens are minted out-of-band; the visual control plane never surfaces a mint affordance.
- **No writes to seed JSONL files.** `seed.jsonl`, `generated_seed.jsonl`, `delegation_seed.jsonl` are never write targets of any AAC code.
- **No "Approve and execute" button.** Every button labels its effect; effects are read or copy-to-clipboard only.
- **No restoring Level 6** — permanently disabled per ADR-015 §Doctrine 1.
- **No editing of artefacts in this UI.** All artefact views are read-only.
- **No assigning work to roles from the UI.** Delegation is owned by the planner / delegation module — surfaced, not authored, by the UI.
- **No mutation endpoint anywhere under `/api/agent-control/*`.**
- **No push-notification body that includes `required_phrase`, an operator-go phrase, an API key, a token, a secret, or any other sensitive value.**

---

## §18 Acceptance criteria (for future implementation units)

1. On mobile, the operator can identify within **10 s** whether any action is required.
2. No card or button can execute a gated operation. (Code-review enforced — UI has no mutation endpoints.)
3. Every visible item links back to ≥ 1 source artefact.
4. Every timeline event renders module + timestamp + decision/reason.
5. Missing artefacts do not break the page; they render as *missing* rows.
6. Stale data is visually obvious globally and per-artefact.
7. Level 6 permanently disabled is always visible on Today (compact strip) and on System Safety (banner).
8. A `needs_human` item can never be styled as success — only amber/human accent.
9. `promotable_row_count = 0` renders as "No promotable candidates", never as an error.
10. An A18c row with `admission_decision = needs_human` appears as blocked/human-needed, never PR-ready.
11. Future PR runtime states (`pr_opened`, `pr_proposed`) are visually distinct from PR dry-run (`dry_run_ready`).
12. `CopyOperatorPhraseButton` writes to clipboard only — it makes no network request.

---

## §19 Open questions / risks

- **Q**. Should "Mark reviewed (local)" ever sync to a backend in a future read-only personal list? *Default: no.*
- **Q**. Where do operator-go phrases originate — `release_gate_agent` emits them, or a separate operator phrase service? Schema reserves `required_phrase` as a string; origin is implementation-defined in B2.0b.
- **R**. Push notifications could leak operator-go phrases if a future maintainer expands the body. **Mitigation**: B2.0e lint hook + pin tests forbidding `required_phrase` in notification payload code paths.
- **R**. Aggregator could drift from artefact schemas. **Mitigation**: each entry in the aggregator output carries `module_version`; UI shows raw JSON drilldown so the operator can audit.
- **R**. Closed vocabularies may need expansion as new lanes appear. **Mitigation**: unknown enum values render neutral gray and emit a console warning — not a crash.
- **Q**. Should the trace expose latency between events to spot stuck items? *Future enhancement; out of scope for B2.0.*
- **Q**. Multi-operator review — out of scope for v0.1; reviewed-state stays local.

---

## Appendix A — Cross-reference summary

| Topic | Document |
|---|---|
| Authority chain | [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md) |
| Truth-authority settlement | [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md) |
| Per-action authority decisions | [`execution_authority.md`](execution_authority.md) |
| Autonomy ladder L0–L6 | [`autonomy_ladder.md`](autonomy_ladder.md) |
| No-touch paths | [`no_touch_paths.md`](no_touch_paths.md) |
| Branch → PR → CI → merge protocol | [`github_pr_lifecycle.md`](github_pr_lifecycle.md) |
| Step 5 design | [`step5_design.md`](step5_design.md) |
| Frontend control-layer roadmap (paused) | [`frontend_agent_control_layer_roadmap.md`](frontend_agent_control_layer_roadmap.md) |
| ADE A8 work queue | [`development_work_queue.md`](development_work_queue.md) |
| ADE A9 release gate | [`development_release_gate.md`](development_release_gate.md) |
| ADE A10 bugfix loop | [`development_bugfix_loop.md`](development_bugfix_loop.md) |
| ADE A11 delegation | [`development_delegation.md`](development_delegation.md) |
| ADE A12 operational digest | [`development_operational_digest.md`](development_operational_digest.md) |
| ADE A13 E2E proof | [`development_e2e_proof.md`](development_e2e_proof.md) |
| ADE A14 Step 5.0 dry-run | [`development_step5_loop.md`](development_step5_loop.md) |
| AAC aggregator schema (companion) | [`agent_activity_center_aggregator_schema.md`](agent_activity_center_aggregator_schema.md) |
| AAC read-only API contract (companion) | [`agent_activity_center_api_contract.md`](agent_activity_center_api_contract.md) |
| AAC no-mutation doctrine (companion) | [`agent_activity_center_no_mutation_doctrine.md`](agent_activity_center_no_mutation_doctrine.md) |
| AAC push-notification safety (companion) | [`agent_activity_center_push_notification_safety.md`](agent_activity_center_push_notification_safety.md) |
| Canonical-roadmap anchor | [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt) §A15 |

## Appendix B — What this document is not

- Not a commitment to ship the Agent Activity Center on any timeline.
- Not an authorisation for any AAC implementation PR.
- Not a request to flip `step5_implementation_allowed` from its hard-pinned `False`.
- Not a request to amend ADR-015 or the autonomy ladder.
- Not a QRE deliverable. QRE work resumes at v3.15.16 / v3.15.17 under Roadmap v6 and is disjoint from this design.
- Not a deploy plan. AAC has no deploy step.

## End of design document
