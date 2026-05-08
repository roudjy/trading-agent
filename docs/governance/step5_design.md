# Step 5 — Autonomous Implementation Loop — Design Document

> **Status: design planning only.** This document is the canonical
> design surface for the future Autonomous Implementation Loop
> ("Step 5"). It is **not** an implementation. It is **not** an
> authorisation. It does **not** flip any flag, change any policy,
> or enable any new capability. Step 5 implementation remains
> blocked behind explicit operator authorisation, the existing
> autonomy ladder ceiling, and the readiness gate defined in §12.
>
> Written 2026-05-08 against `main @ ae7e653` (post-PR #147 Step 5
> design readiness review). Predecessor reading list:
> [`docs/governance/step5_design_readiness.md`](step5_design_readiness.md),
> [`docs/governance/development_e2e_proof.md`](development_e2e_proof.md),
> [`docs/governance/development_operational_digest.md`](development_operational_digest.md),
> [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md),
> [`docs/governance/execution_authority.md`](execution_authority.md),
> [`docs/governance/autonomy_ladder.md`](autonomy_ladder.md).

## Status

`design_planning_only`. The matching ADR draft is
[`docs/adr/_drafts/ADR-017-step5-autonomous-implementation-loop.md`](../adr/_drafts/ADR-017-step5-autonomous-implementation-loop.md).
Promotion to a numbered ADR (`docs/adr/ADR-017-*.md`) requires an
operator-authored, CODEOWNERS-reviewed governance-bootstrap PR.

## Hard preamble — what design planning does and does not authorise

- This document **may** name future code paths, future tests, future
  vocabularies, future module versions, and future no-touch carve-outs.
- This document **may not** ship code, edit the live ADE modules,
  flip `step5_implementation_allowed`, edit any canonical_policy_doc
  or canonical_roadmap, or modify the autonomy ladder.
- This document **does not** lift any of the gates in
  [`docs/governance/step5_design_readiness.md`](step5_design_readiness.md) §Q2.
  Those gates remain held closed.
- Reading this document does not constitute operator authorisation
  for Step 5 implementation. Operator authorisation is a separate,
  signed-in-writing act in a future governance PR's body.

---

## §1 Definition

### 1.1 What the Autonomous Implementation Loop is

The Autonomous Implementation Loop (Step 5) is the future ADE
capability that turns operator-approved delegation entries (A11)
and bugfix candidates (A10) into **bounded, dry-run-first,
release-gate-evaluated, human-approved** code-modification
proposals on disposable feature branches. It is the smallest step
beyond A13 (which proves the loop is *possible* on synthetic
fixtures) toward a real loop that can edit allowlisted files,
run targeted tests, and surface a draft PR for human merge.

A successful Step 5 loop, when fully landed in a *future* phase,
produces:

- a feature branch that contains a single coherent diff bounded by
  an A11/A10 acceptance-criteria contract;
- a release-gate report (A9 verdict) on that branch;
- an operational digest entry (A12) referencing the work;
- an E2E proof entry (A13 lifecycle) reflecting the actual run;
- a draft PR opened for human review.

The loop **stops** at "draft PR opened". Merge and deploy remain
human acts.

### 1.2 What is included (in-scope for design)

| Capability | Phase Stage | Notes |
|---|---|---|
| Delegation pickup from A11 sidecar / canonical roadmap markers | Step 5.0 dry-run | Reads-only the existing `reporting.development_delegation` outputs. |
| Bugfix candidate pickup from A10 outputs | Step 5.0 dry-run | Reads-only the existing `reporting.development_bugfix_loop` outputs. |
| Bounded plan emission (planner sub-agent) | Step 5.0 dry-run | Plan written to `logs/step5_plan/<plan_id>.json` only. No branch creation. |
| Real branch creation, scoped to an allowlisted target path set | Step 5.1 (later) | Allowlist defined in §5. |
| Real file edits on a disposable feature branch | Step 5.2 (later) | Subject to A9 release-gate evaluation. |
| Targeted test execution on the branch | Step 5.2 (later) | `pytest tests/{smoke,unit}` only, no regression-pin tests, no live-trading tests. |
| Release-gate evaluation of the branch | Step 5.2 (later) | Re-uses the existing A9 evidence input contract. |
| Draft PR open for human review | Step 5.3 (later) | Uses the documented `gh CLI` lifecycle. PR opened as draft + `human_needed=true`. |
| Operator-visible digest entry | Step 5.3 (later) | A12 digest already aggregates this; Step 5 only emits, never mutates upstream artefacts. |

### 1.3 What is explicitly excluded

| Excluded | Rationale |
|---|---|
| Autonomous merge | Forbidden by ADR-015 §Doctrine 1 / autonomy ladder ceiling (Level 6 is permanently disabled). |
| Autonomous deploy | Same. |
| Pushing directly to `main` | Forbidden by `docs/governance/github_pr_lifecycle.md` and branch protection. |
| `--admin` merge | Forbidden by Execution Authority (`PERMANENTLY_DENIED`). |
| Force-push to any branch | Forbidden by Execution Authority (`PERMANENTLY_DENIED`). |
| Editing `automation/live_gate.py` | Permanently no-touch. |
| Editing `.claude/**` | Permanently no-touch. |
| Editing canonical_policy_doc / canonical_roadmap | `NEEDS_HUMAN`. |
| Editing frozen v1 schemas | Permanently no-touch. |
| Editing CI workflows from inside Step 5 | `NEEDS_HUMAN`; only `ci-guardian` may propose CI edits, in a dedicated CI-hardening task. |
| Touching live/paper/shadow/risk/trading/broker/execution code | Permanently no-touch. |
| Modifying QRE behavior (`research/**`, `dashboard/dashboard.py`, broker/execution) | Permanently no-touch under the Step 5 surface; QRE feature work uses the QRE Feature Build Track. |
| Reading credentials | Read-deny per `deny_config_read.py`. |
| Bypassing or modifying any hook | Forbidden. |
| Skipping or weakening tests | Forbidden by `docs/governance/no_test_weakening.md`. |
| Modifying Intelligent Routing scoring or queue ordering | Out-of-scope (QRE concern). |
| Modifying QRE v3.15.17 (Sampling Intelligence) work | Out-of-scope (QRE concern). |
| Initiating or accepting transactions on any chain or exchange | Trading execution authority is disjoint from agent execution authority (ADR-014 §C / autonomous_development.txt §2.2). |

---

## §2 Authority model

### 2.1 Authority surfaces consulted

Step 5 reuses two existing classifiers without modification:

- `reporting.execution_authority.classify(...)` — maps `(action_type, target_path, risk_class)` to one of `AUTO_ALLOWED` / `NEEDS_HUMAN` / `PERMANENTLY_DENIED`. Step 5 calls this once per intended action and obeys the classifier's output verbatim.
- `reporting.approval_policy.evaluate(...)` — maps the same triplet to a closed approval reason vocabulary.

Step 5 introduces **no** new authority decision logic. It is a *consumer* of the existing classifiers, not a co-author of policy.

### 2.2 AUTO_ALLOWED action types Step 5 may consume

These remain as already documented in `docs/governance/execution_authority.md`:

- `file_read`
- `test_run` (against `tests/{smoke,unit,functional}` only — see §10)
- `governance_lint_run`
- `protocol_dry_run`
- `branch_create` (auto-allowed when every touched path is auto-allowed)
- `commit_create` (same composite rule)
- `branch_push` (same composite rule)
- `pr_open` (same composite rule, **as draft**)

### 2.3 NEEDS_HUMAN action types Step 5 may *propose* but never auto-execute

- `pr_squash_merge` — even when CI is green and every touched path was AUTO_ALLOWED, the **merge act** is held human under the autonomy-ladder ceiling. The classifier's `pr_squash_merge=AUTO_ALLOWED` rule is a per-action cap; the *autonomy ladder* L4 (merge recommendation) and L5 (deploy recommendation) are independent caps that remain not-yet-unlocked. Step 5 emits a `merge_recommendation` token, not a merge.
- `roadmap_marker_change` — proposed only by appending to the A11 sidecar via human-approved seed edits, never by the loop.
- Any `protected_governance_change` — `NEEDS_HUMAN` and routed through the governance-bootstrap flow.

### 2.4 PERMANENTLY_DENIED — Step 5 must never attempt these

- `pr_force_push`
- `main_direct_push`
- `branch_protection_bypass`
- `pr_admin_merge`
- `git_filter_repo` (history rewrite)
- Any operation against a no-touch path
- Any read against a read-deny path
- Any subprocess invocation that loosens hooks, weakens tests, or extracts credentials

The Step 5 module must, at AST-level, refuse to import, name, or string-construct any token that resolves to one of these. The pin tests under §10 enforce this.

### 2.5 Authority chain at runtime

```
delegation/bugfix → planner draft → execution_authority.classify(...)
   AUTO_ALLOWED → continue                NEEDS_HUMAN / PERMANENTLY_DENIED → halt + emit
                                          human_needed event
```

Halts are loud (operator-facing entry in the operational digest) and idempotent (the same delegation re-evaluated produces the same halt reason).

---

## §3 Autonomy ladder compatibility

### 3.1 Current autonomy ladder ceiling

Per `docs/governance/autonomy_ladder.md` and ADR-015 §Doctrine 1:

| Level | Capability | Status |
|---|---|---|
| 0 | Plan / read only | always available |
| 1 | Docs + tests + frontend writes | available |
| 2 | Observability + CI writes (per-change approval) | available |
| 3 | Backend non-core writes (allowlist-only) | not enabled |
| 4 | Merge recommendation | locked, requires ≥30 days L1–3 stable + ADR-015 amendment |
| 5 | Deploy recommendation | locked, requires ≥60 days L1–4 stable + ADR-015 amendment |
| 6 | Autonomous merge / deploy | **permanently disabled** in this project |

### 3.2 How Step 5 fits inside the ladder without violating L6

Step 5 ships in **three sub-stages** mapped onto existing levels. None requires a new level above the current cap.

| Sub-stage | Effective level | What it does | What it does *not* do |
|---|---|---|---|
| Step 5.0 (dry-run / planner-only) | L0 (read-only) | Reads delegation + bugfix outputs, emits a `step5_plan/<plan_id>.json` artifact, produces a "would do" preview. | Creates no branches. Modifies no files. |
| Step 5.1 (bounded edits, allowlisted) | L1 (docs/tests/frontend) — possibly L2 (observability) | Creates a feature branch, makes scoped edits inside the §5 allowlist, runs targeted tests, opens a *draft* PR. | Does not merge. Does not deploy. Does not edit anything outside the §5 allowlist. |
| Step 5.2 (merge recommendation) | L4 — **requires ADR-015 amendment** | Flips `merge_recommendation` from "advisory" to "release-gate-bound". | Still does not merge. Humans merge. |

**Step 5 never reaches L5 or L6.** L5 (deploy recommendation) is independent of Step 5 and would require a separate amendment. L6 is permanently disabled per ADR-015 §Doctrine 1; an amendment to enable Level 6 is described in ADR-015 as auto-recommended `block` by the release-gate-agent and must be merged by humans deliberately overriding that recommendation, in full knowledge that they are doing so. Step 5 design explicitly **does not** propose flipping that ceiling.

### 3.3 Implementation loop allowed under the L6 prohibition

A loop that closes only at "draft PR opened" — never at "merged" or "deployed" — is fully compatible with L6 being permanently disabled. The autonomy-ladder L6 prohibition is about *who closes the loop*, not about *whether the loop runs*. Step 5 keeps human-merge at the top of every cycle.

---

## §4 ADE / QRE boundary

### 4.1 Loose-coupling invariant (carried forward from A8–A13)

ADE-core modules import only:

- Python stdlib;
- ADE peer modules under `reporting.development_*`;
- the two existing classifiers (`reporting.execution_authority`, `reporting.approval_policy`);
- the agent audit ledger writer (`reporting.agent_audit`) for hash-chained event recording.

ADE-core modules **never** import:

- `research`
- `dashboard.dashboard`
- `automation`
- `broker`
- `agent.risk` / `agent.execution`
- `reporting.intelligent_routing`

This is pinned by AST-level tests on every existing ADE module
(`tests/unit/test_development_*.py`). Step 5 modules **must** carry
the same pin.

### 4.2 No QRE artifact mutation

Step 5 must not write or mutate any of:

- `research/research_latest.json`
- `research/strategy_matrix.csv`
- `research/candidate_registry_*.json`
- `research/sleeve_registry_*.json`
- any `**/*_latest.v1.json` / `**/*_latest.v1.jsonl` frozen v1 contract
- `logs/development_work_queue/latest.json` (A8 owns it)
- `logs/development_release_gate/latest.json` (A9 owns it)
- `logs/development_bugfix_loop/latest.json` (A10 owns it)
- `logs/development_delegation/latest.json` (A11 owns it)
- `logs/development_operational_digest/latest.json` (A12 owns it)
- `logs/development_e2e_proof/latest.json` (A13 owns it)

Step 5 reads these via the documented read-only APIs and produces its own outputs under `logs/step5_*/...`. Pinned by the byte-comparison invariance test (see §10).

### 4.3 Future repository extraction

Step 5 modules must be importable as a stand-alone package whose only required dependencies are:

- Python stdlib;
- the four ADE-core peer modules;
- the two classifiers;
- the audit ledger writer.

If at a future date the operator decides to extract ADE into its own repository, the Step 5 import graph contains no QRE-internal symbol. The pin test in §10 (`test_step5_import_graph_does_not_contain_qre_symbols`) verifies this on every CI run.

---

## §5 Allowed surfaces (strict allowlist; never denylist)

Step 5 may *write* under exactly these path globs. Any write outside this list is a hook violation.

### 5.1 Step 5.0 (planner-only / dry-run) — write allowlist

- `logs/step5_plan/*.json` — per-plan artifact written atomically.
- `logs/step5_plan/history.jsonl` — bounded append-only history.
- `docs/governance/agent_run_summaries/*.md` — committed PR summaries (existing convention).

That is the entirety of Step 5.0's write surface. No branch creation. No file edits anywhere else.

### 5.2 Step 5.1 (bounded edits) — write allowlist

In addition to §5.1, Step 5.1 may write:

- on a feature branch only (never on `main`), under exactly these globs:
  - `tests/smoke/**`, `tests/unit/**`, `tests/integration/**`, `tests/functional/**`, `tests/resilience/**`
    (`tests/regression/**` is `ask`; Step 5 never auto-edits there)
  - `frontend/**` (UI-only, no backend wiring)
  - `docs/**`, excluding `docs/governance/**`, `docs/adr/**`, `docs/roadmap/**`
  - `reporting/**`, only if the per-action `target_path` is on a Step 5-specific allowlist seeded by the operator via the A11 delegation marker (out-of-band, human-approved)
- artifact paths under `logs/step5_*/...`.

This is intentionally narrower than the implementation-agent's full allowlist. Step 5 does not get the union; it gets a deliberately restricted subset that biases toward docs, tests, and reporting reads — the lowest-risk surfaces.

### 5.3 Step 5.2 (merge recommendation) — write allowlist

Same as §5.2, plus:

- the right to call `gh pr ready` to lift the draft state on a PR that has cleared the release gate.

Even Step 5.2 does not gain the right to merge. Merge stays human.

### 5.4 Allowlist enforcement

Each Step 5 sub-stage's write set is encoded as a Python tuple of fnmatch globs in the Step 5 module's source (named `STEP5_<n>_WRITE_ALLOWLIST`). The hook layer (`deny_outside_agent_allowlist.py`) plus a Step 5-specific source-text scan test verify the allowlist on every CI run. Adding a path requires a code change pinned by tests AND a docs update AND CODEOWNERS approval — the standard governance-bootstrap PR class.

---

## §6 Forbidden surfaces (defense-in-depth, not the only enforcement)

These paths are forbidden to Step 5 *in addition to* the existing
`docs/governance/no_touch_paths.md` doctrine. The forbidden list
below duplicates the no-touch list for legibility; it is **not**
intended to replace or weaken `no_touch_paths.md`.

### 6.1 Permanently no-touch (write- and create-deny)

- `automation/live_gate.py` and `automation/**`
- `research/**` (every QRE research path; full directory after no-touch R5)
- `agent/brain/**`, `agent/execution/**`, `agent/learning/**`, `agent/agents/**`, `agent/risk/**`, `agent/monitoring/**`
- `dashboard/dashboard.py`
- `execution/**`, `strategies/**`
- `orchestration/**`
- `agent/backtesting/engine.py`, `agent/backtesting/fitted_features.py`
- `docker-compose.prod.yml`, `scripts/deploy.sh`, `ops/systemd/**`, `ops/nginx/**`, `Dockerfile`
- `**/*_latest.v1.json`, `**/*_latest.v1.jsonl` (frozen v1 schemas)
- `docs/adr/ADR-*.md` (existing ADRs)
- `tests/regression/test_v3_*pin*.py`, `test_v3_15_artifacts_deterministic.py`, `test_authority_invariants.py`, `test_v3_15_8_canonical_dump_and_digest.py`
- `.claude/settings.json`, `.claude/hooks/**`, `.claude/agents/**`
- `.github/CODEOWNERS`
- `VERSION`
- `docs/governance/agent_governance.md`, `autonomy_ladder.md`, `no_touch_paths.md`, `permission_model.md`, `no_test_weakening.md`, `hooks_runtime_policy.md`, `provenance.md`, `audit_chain.md`, `release_gate.md`, `release_gate_checklist.md`, `rollback_drill.md`, `sha_pin_review.md`

### 6.2 Read-deny

- `config/config.yaml`
- `state/*.secret`
- `automation/*.secret`
- `.env`, `.env.*`

Plus the indirect-read denials enumerated in `docs/governance/no_touch_paths.md` (`python -c` / `eval` / `base64 -d` / redirect-reads / process substitution / etc.).

### 6.3 QRE-specific deny

- `research/**` — already in §6.1; restated here because the operator's question explicitly enumerates QRE.
- `reporting/intelligent_routing*.py` — Step 5 may not change Intelligent Routing scoring or queue ordering.
- `research/campaign_*.py` — QRE campaign queue; out of Step 5's authority.
- `reporting/proposal_queue.py` — QRE proposal queue; out of Step 5's authority.

### 6.4 v3.15.17 deny

Step 5 must not touch any path that would advance the next QRE feature (Sampling Intelligence) or change Intelligent Routing semantics. Concretely, Step 5 must not edit any module imported transitively by `research.run_research` or `research.intelligent_routing`. The v3.15.17 phase is operator-authored under the QRE Feature Build Track and is disjoint from the Autonomous Development Track.

---

## §7 Workflow

The Step 5 loop, when fully landed, executes the following sequence per delegation/bugfix candidate:

```
0. Trigger (operator-driven; never wall-clock auto-tick)
   └─ python -m reporting.development_step5_loop --plan-only
      OR a CI dispatch event from a green release_gate_artifact

1. Roadmap / delegation / bugfix pickup
   ├─ read logs/development_delegation/latest.json (A11)
   ├─ read logs/development_bugfix_loop/latest.json (A10)
   ├─ read logs/development_work_queue/latest.json (A8)
   └─ select at most ONE item per cycle; deterministic ordering
        (delegation_id ASC, then bugfix candidate_id ASC, then queue
        item_id ASC). Cycle ID = sha256 of selected item identity.

2. Agent planning (planner-style sub-agent, but bounded)
   ├─ classify the item via reporting.execution_authority.classify
   │    if NEEDS_HUMAN → emit human_needed event, halt
   │    if PERMANENTLY_DENIED → emit blocked event, halt
   │    if AUTO_ALLOWED → continue
   ├─ derive a target-path set from the item's acceptance_criteria
   ├─ verify EVERY target_path is inside §5.2 allowlist
   │    if any path is outside → halt; emit out_of_allowlist event
   ├─ produce a bounded plan artifact under logs/step5_plan/<cycle_id>.json
   └─ at Step 5.0 the loop STOPS HERE.

3. Bounded implementation draft (Step 5.1+)
   ├─ create feature branch step5/<cycle_id>
   │    branch_create AUTO_ALLOWED iff every target_path is AUTO_ALLOWED
   ├─ for each target_path in the plan:
   │    ├─ write the proposed edit
   │    ├─ no path outside §5.2 allowlist
   │    ├─ no edit larger than the plan-declared diff envelope
   │    └─ commit_create (one logical commit per step in the plan)
   └─ branch_push to origin

4. Tests
   ├─ pytest tests/smoke -q              MUST pass
   ├─ pytest tests/unit -q               MUST pass
   ├─ pytest <targeted-set-from-plan> -q MUST pass
   ├─ pytest tests/functional -q         optional, plan-declared
   └─ NEVER run tests/regression/** with weakened pins;
      NEVER run live/paper/shadow tests.

5. Release gate (re-uses A9)
   ├─ collect evidence into logs/release_gate_input/latest.json
   ├─ run reporting.development_release_gate
   ├─ verdict ∈ {go, go_with_followups,
   │            no_go_blocked, no_go_human_needed, not_evaluated}
   └─ verdict is the gate; a no_go halts the loop.

6. PR preparation
   ├─ pr_open (DRAFT) AUTO_ALLOWED iff every touched path was AUTO_ALLOWED
   ├─ PR body MUST include:
   │    cycle_id, delegation_id / bugfix_id / queue_item_id,
   │    plan_id, release_gate verdict, evidence digests,
   │    explicit "human_required: true" line
   └─ PR labels: "step5", "human_required".

7. Human / CI gate
   ├─ CI runs (existing fast-gate workflows).
   ├─ Human reviews the draft PR.
   ├─ Human marks PR ready (or closes / requests changes).
   └─ Human merges (squash + delete-branch).
   No part of Step 5 attempts to merge.

8. Report-out
   ├─ A12 digest tick that includes this cycle's
   │    {cycle_id, plan_id, branch, PR number, verdict, status}.
   ├─ A13 E2E proof tick on synthetic fixtures (operator-driven).
   └─ Audit ledger event recorded with autonomy_level_claimed = 1
      (or 2 if observability target_path was edited).
```

The loop has **no autonomous merge or deploy step** anywhere. The autonomy ladder amendment that would enable Level 6 (`docs/governance/autonomy_ladder.md`) is permanently disabled per ADR-015 §Doctrine 1; an amendment to enable Level 6 must be merged by humans deliberately overriding the release-gate-agent's auto-block recommendation. Step 5 design respects that ceiling.

---

## §8 Evidence contracts

### 8.1 Step 5 module versions (proposed)

- `reporting.development_step5_loop` — `module_version = "v3.15.16.A14"`
- (alternative naming: `reporting.development_implementation_loop` if the operator prefers — name is not load-bearing for this design)

### 8.2 Artifacts Step 5 produces

| Path | Schema | Owner | Mutates | Notes |
|---|---|---|---|---|
| `logs/step5_plan/<cycle_id>.json` | `step5_plan.v1.json` (closed; defined in §8.3) | Step 5 | append-only per cycle | Atomic write. Never overwritten. Never deleted by ADE. |
| `logs/step5_plan/history.jsonl` | `step5_plan_history.v1.jsonl` (closed) | Step 5 | bounded append-only, 90-entry rolling window | Atomic rewrite. Mirrors A12 history pattern. |
| `logs/step5_loop/latest.json` | `step5_loop_latest.v1.json` (closed) | Step 5 | one snapshot per cycle | Cycle-tip pointer, deterministic. |

The new schemas live under `**/*_latest.v1.json` and `**/*.v1.jsonl` and are themselves frozen v1 contracts (additive only, never breaking) — the same regime as A8–A13 outputs.

### 8.3 `step5_plan.v1.json` schema (closed)

```
schema_version: "1.0"
module_version: "v3.15.16.A14"
report_kind: "step5_plan"
generated_at_utc: <iso utc>
cycle_id: <sha256 of selected item identity>
source_kind: "delegation" | "bugfix" | "queue"
source_id: <opaque id from upstream artefact>
acceptance_criteria: list[str]  # bounded, ≤16 entries, ≤200 chars each
target_paths: list[str]          # every entry passes §5.2 allowlist
diff_envelope:
  max_files_touched: int
  max_lines_per_file: int
  max_total_lines: int
authority_decisions:
  - {action_type, target_path, decision, reason}
release_gate_required: true
human_required: true
mergeable_by_agent: false        # hard-pinned false
deployable_by_agent: false       # hard-pinned false
discipline_invariants:
  actually_modifies_target: <bool>     # false at Step 5.0
  creates_real_branches: <bool>        # false at Step 5.0
  opens_real_prs: <bool>               # false at Step 5.0
  mutates_qre_artifacts: false         # always false
  mutates_frozen_contracts: false      # always false
  mutates_protected_paths: false       # always false
  uses_subprocess_or_network: <bool>   # false at Step 5.0
  operator_step5_authorisation_required: true  # always true
```

### 8.4 Release-gate evidence input

Step 5 reuses the existing `logs/release_gate_input/latest.json`
contract from A9. No new evidence keys are added at Step 5.0. If
later sub-stages need new keys (e.g. `step5_plan_status`,
`step5_diff_envelope_status`), they are added additively per ADR-015
§Doctrine 12 (frozen-schema additive-only).

### 8.5 Determinism guarantees

- Pure scorer: same `(delegation, bugfix, queue, evidence_input, generated_at_utc, agents_root)` → byte-identical artefact.
- `cycle_id` is `sha256` of the selected item identity, stable across runs.
- Atomic writes only under `logs/step5_*/...`. The history file is rewritten atomically with the bounded window.
- Never reads upstream artefacts mutably (pinned by before/after byte comparison test).
- Determinism pin tests live at `tests/regression/test_v3_step5_artifacts_deterministic.py` once Step 5 lands; design phase only declares the contract.

---

## §9 Kill switch / rollback

### 9.1 Operator kill switch

Step 5 ships with three independent stop mechanisms. Any one is sufficient.

1. **Per-cycle stop** — operator deletes `logs/step5_plan/<cycle_id>.json` (or stages a deletion in a docs-only PR). The next cycle re-evaluates and either halts cleanly (if the upstream delegation was removed) or re-emits the plan idempotently.
2. **Step 5 sub-stage cap** — `STEP5_ENABLED_SUBSTAGE` is a closed-vocab constant in the Step 5 module: `{"none", "5.0", "5.1", "5.2"}`. Default is `"none"`. The operator flips the cap by amending the module (governance-bootstrap PR) — never at runtime.
3. **Global ADE shutdown** — operator removes the Step 5 module from the ADE-core import list in `reporting.development_operational_digest` (governance-bootstrap PR). The digest then reports `presence_count` minus one, A12's `step5_readiness` continues to function, and Step 5 cannot be invoked.

### 9.2 Unsafe-candidate rejection

Any cycle where the planner cannot satisfy *all* of the following halts and emits a `human_needed` event with a closed-vocab reason:

- every `target_path` is inside §5.2 allowlist;
- every `target_path`'s `execution_authority.classify(...)` is `AUTO_ALLOWED`;
- the diff envelope (`max_files_touched`, `max_lines_per_file`, `max_total_lines`) is non-zero and within the operator-defined cap;
- the acceptance criteria are bounded (≤16 entries, ≤200 chars each, no test-weakening tokens, no protected-path tokens);
- the bugfix scope (if applicable) is `bounded_in_repo` (never `protected_path`, `live_path`, `frozen_contract`, `requires_architecture_review`, `out_of_scope`).

### 9.3 Partial-branch abandonment

If a Step 5.1+ cycle creates a branch and any later step fails (test failure, release-gate `no_go`, hook deny), the loop:

1. emits a `cycle_aborted` event with the closed-vocab reason;
2. closes the draft PR (if one was opened) with a `step5_aborted` label and a comment that names the failing step;
3. **does not** delete the branch — operator inspects and decides whether to discard, merge with manual fixes, or escalate;
4. **never** force-pushes, never amends, never rewrites history.

The operator's first inspection lever is the audit ledger: `python -m reporting.agent_audit_summary --view timeline --since-cycle <cycle_id>` shows every action the loop attempted in that cycle, in order, with the exact deny reason for whatever halted.

---

## §10 Test strategy

The following tests **must exist and pass on `main`** *before* any Step 5 implementation PR may be opened. The test files live under `tests/unit/` and `tests/regression/` — paths declared here so the cleanup phase knows where they go.

| Test | Path (proposed) | Pin |
|---|---|---|
| Closed vocabularies cardinality | `tests/unit/test_development_step5_loop.py::test_closed_vocabularies_cardinality` | `STEP5_SUBSTAGES`, `STEP5_AGENT_ROLES`, `STEP5_HALT_REASONS`, `STEP5_OUTCOME_KINDS` are tuples of stable length. |
| No forbidden imports | `tests/unit/test_development_step5_loop.py::test_no_forbidden_imports` | AST scan of `reporting.development_step5_loop` rejects `research`, `dashboard`, `automation`, `broker`, `agent.risk`, `agent.execution`, `reporting.intelligent_routing`, `subprocess`, `socket`, `requests`, `urllib`. |
| No protected-path writes | `tests/unit/test_development_step5_loop.py::test_no_protected_path_writes` | The atomic-write helper refuses every path outside `logs/step5_*/...`. |
| No QRE coupling | `tests/unit/test_development_step5_loop.py::test_no_qre_coupling` | Source-text scan rejects `research/`, `dashboard/`, `automation/`, `broker/`, `intelligent_routing` substrings except in opaque docstrings. |
| No credential extraction | `tests/unit/test_development_step5_loop.py::test_no_credential_extraction` | Source-text scan rejects `os.environ`, `getenv`, `cred`, `secret`, `token`, `api_key` substrings outside the closed pin list. |
| No test weakening | `tests/unit/test_development_step5_loop.py::test_no_test_weakening_tokens` | Source-text scan rejects `skip`, `xfail`, `remove pin`, `weaken`, `relax`, `disable` outside the closed pin list. |
| Deterministic outputs | `tests/regression/test_v3_step5_artifacts_deterministic.py` | Same `(inputs, generated_at_utc)` → byte-identical artefacts. |
| Dry-run mode | `tests/unit/test_development_step5_loop.py::test_dry_run_does_not_create_branches` | Dry-run path never invokes git, never invokes gh, never opens a network connection. |
| Rollback simulation | `tests/unit/test_development_step5_loop.py::test_rollback_simulation` | Killed cycle leaves the upstream artefact byte-identical (before/after sha256 equality). |
| Release-gate integration | `tests/unit/test_development_step5_loop.py::test_release_gate_integration` | Step 5 → A9 produces the expected `release_gate_input/latest.json` shape; A9 verdict is consumed verbatim by Step 5. |
| Discipline invariants pin | `tests/unit/test_development_step5_loop.py::test_discipline_invariants_pinned` | The `discipline_invariants` block in every artefact contains the closed five keys with the closed values declared in §8.3. |
| `step5_implementation_allowed` is `False` constant | `tests/unit/test_development_step5_loop.py::test_step5_implementation_allowed_constant_is_false` | The literal `False` is the only value bound to this name in the Step 5.0 module path. |

### 10.1 Forbidden test surface

Step 5 tests must **not** exercise:

- `tests/regression/**` pin tests with weakened thresholds;
- live trading paths (`automation/live_gate.py`, `execution/**`, `broker/**`);
- QRE behavior under `research/**`;
- frozen v1 contracts under `**/*_latest.v1.json`.

### 10.2 Coverage requirement

A coverage line for `reporting.development_step5_loop` ≥ 95% is required before promoting Step 5.0 → Step 5.1. This bound mirrors the A8 / A9 / A12 thresholds.

---

## §11 Required documentation modernization

Per [`docs/governance/documentation_audit.md`](documentation_audit.md) and §Q6 of [`docs/governance/step5_design_readiness.md`](step5_design_readiness.md), the following docs must be modernized before any Step 5 *implementation* PR may be merged. None of these block Step 5 *design* (which is what this document is). Each is operator-authored and CODEOWNERS-reviewed (`canonical_policy_doc` class).

### 11.1 `CLAUDE.md` (root)

Status: `misleading + missing_cross_reference` (per audit). Does not reference ADR-015, the autonomy ladder, the GitHub PR lifecycle, the QRE/ADE split, or the Execution Authority. Contains an obsolete 30-day "Dag 1-30" trading-agent roadmap (lines 344–438) from the project's pre-QRE phase.

Required edits before Step 5 implementation:

- Add a top-level "current canonical docs" pointer block referencing ADR-014, ADR-015, Execution Authority, autonomy ladder, GitHub PR lifecycle, no-touch paths.
- Add a top-level "QRE vs ADE" clarification block.
- Move (or delete) the "Dag 1-30" roadmap block; if kept, mark it `## Historical (pre-v3.15) — superseded by Roadmap v6`.
- Add a one-line cross-reference to `docs/governance/github_pr_lifecycle.md` in the session-start protocol.
- Tracked by backlog item AB-0008.

### 11.2 `AGENTS.md` (root)

Status: `misleading` (per audit). §4 ("AI Tooling Roles") describes a stale "Claude → Codex CLI → Claude Code" three-actor model superseded by the v3.15.15.12 governance layer. §5 ("Execution Workflow") and §11 ("Git Workflow") predate the GitHub CLI lifecycle protocol.

Required edits before Step 5 implementation:

- Replace §4 entirely with a pointer to `docs/governance/agent_handoff_protocol.md` (eight canonical agent roles), `docs/adr/ADR-015`, and `docs/governance/autonomy_ladder.md`.
- Replace §5 with a pointer to `docs/governance/execute_safe_controls.md` and `docs/governance/agent_flow.md`.
- Replace §11 with a pointer to `docs/governance/github_pr_lifecycle.md`.
- Keep §3 (Source of Truth + ADR-014 cross-ref) intact.
- Add a §12 "Step 5" section once Step 5.0 lands; this design doc is the placeholder until then.

### 11.3 `INSTALLATIEGIDS.md` (root)

Status: `minor_cleanup` (per audit). The "STAP 7 — Paper trading fase" criteria (`win-rate >55%`, `50 trades`) predate the v3.15+ paper-readiness gate (`research/paper_readiness.py`). Not load-bearing for Step 5, but should be modernized in the same cleanup PR.

Required edit:

- Add a one-line note in §STAP 7 pointing at `docs/handoffs/v3.15-to-v3.16.md` §2 and `research/paper_readiness.py`.

### 11.4 `docs/RESEARCH_CONTEXT.md`

Status: `minor_cleanup` / `candidate_archive` (per audit). 36-line file titled `# CLAUDE.md` (mismatched name) listing strategy-family verdicts that have been superseded by the strategy registry, hypothesis catalog, and ADR-014.

Required edit (before Step 5 implementation; not before Step 5 design):

- Either move under `docs/archive/RESEARCH_CONTEXT.md`, or rewrite as a 5-line pointer to ADR-014 and the strategy registry.

### 11.5 `docs/governance/frontend_agent_control_layer_roadmap.md`

Status: `minor_cleanup` (per audit). Internal roadmap for v3.15.15.17–.23 frontend control surfaces, deliberately paused while ADE A1–A13 ran.

Required edit:

- Add a 1-line "paused after v3.15.15.16; resumed only after Step 5 design planning" header stamp.

### 11.6 Why these blocks Step 5 implementation but not Step 5 design

ADR-015 §Doctrine 4 ("Live trading code is human-only") and §Doctrine 7 ("Self-protected layer") together require that the human-readable contributor docs accurately describe what agents can and cannot do *before* a real autonomous-implementation surface ships. Letting Step 5 implementation land while contributors still see "Codex CLI implements" in §4 of `AGENTS.md` would create a documentation gap large enough that the reviewer convention which backs ADR-015 §Doctrine 7 starts to fray.

Step 5 *design* is a documentation activity that explicitly names these dependencies; it does not require them to be resolved first. The constraint is on implementation, not on design.

---

## §12 Implementation readiness gate

Before any Step 5 *implementation* PR (Step 5.0 or later) may be opened, **all** of the following measurable criteria must be true on `main`. This list is the operator's checklist; it is not auto-evaluated by ADE.

| # | Criterion | Verifier |
|---|---|---|
| G1 | Operational digest on `main` reports `step5_design_planning_allowed=true`. | `python -m reporting.development_operational_digest \| jq .step5_readiness.step5_design_planning_allowed` |
| G2 | Operational digest on `main` reports `step5_implementation_allowed=false` (this is the *expected* state — the gate is not "flip this flag" but "verify the current state matches the design's assumption that the flag is false"). | Same path. |
| G3 | E2E proof on `main` reports `proof_status=passed`, `protected_path_violations=[]`, `qre_coupling_violations=[]`, `missing_capabilities=[]`. | `python -m reporting.development_e2e_proof --no-write` |
| G4 | All 220+ ADE-core unit tests pass on `main`. | `python -m pytest tests/unit/test_development_*.py -q` |
| G5 | Governance lint clean. | `python scripts/governance_lint.py` |
| G6 | Smoke clean. | `python -m pytest tests/smoke -q` |
| G7 | Documentation modernization PR (per §11) has merged to `main`. | `git log --oneline main -- CLAUDE.md AGENTS.md INSTALLATIEGIDS.md docs/RESEARCH_CONTEXT.md docs/governance/frontend_agent_control_layer_roadmap.md` shows the cleanup commit. |
| G8 | A new ADR (proposed `ADR-017-step5-autonomous-implementation-loop.md`) has been promoted out of `_drafts/` and merged. | `ls docs/adr/ADR-017-*.md` exists; `_drafts/` no longer contains it. |
| G9 | An entry for Step 5 has been added to `docs/roadmap/autonomous_development.txt` by the operator (canonical_roadmap edit). | Roadmap doc grep. |
| G10 | The operator has signed an explicit authorisation in the Step 5.0 PR's body, naming the cycle scope and the kill-switch path. | PR body inspection. |
| G11 | The Step 5 module (`reporting.development_step5_loop` or operator-named equivalent) has all §10 tests committed and green on `main` *before* the implementation PR is opened. (i.e. tests-first; the implementation PR is a no-op until tests pin it). | `pytest tests/unit/test_development_step5_loop.py -q` is green. |
| G12 | A fresh release-gate report and a fresh rollback-drill log within the prior 14 days, recorded under `docs/governance/release_gates/` and `docs/governance/rollback_drill.md` respectively. | Path inspection. |

`step5_ready_to_implement = all(Gn for n in 1..12)`. The operator
verifies this checklist out-of-band. ADE does not auto-flip any of
the gates; each is a human act recorded in Git.

---

## §13 First implementation slice proposal — Step 5.0

The smallest possible first Step 5 implementation slice is the
**dry-run, planner-only, read-only** sub-stage. It is the minimum
viable surface that can be evaluated by A9, aggregated by A12, and
proven by A13. It performs **no** real edits, opens **no** real
PRs, makes **no** network calls.

### 13.1 Module layout

| Path | Purpose |
|---|---|
| `reporting/development_step5_loop.py` | Step 5.0 module. Stdlib + ADE peers + classifiers + audit ledger writer only. |
| `tests/unit/test_development_step5_loop.py` | All §10 unit tests. |
| `tests/regression/test_v3_step5_artifacts_deterministic.py` | Determinism pin. |
| `docs/governance/development_step5_loop.md` | Canonical governance doc for Step 5.0. |
| `docs/roadmap/autonomous_development.txt` (operator-authored) | New §A14 entry under "Future phases". |

### 13.2 What Step 5.0 does

```
python -m reporting.development_step5_loop --dry-run
```

1. Reads (atomically, no mutation) `logs/development_delegation/latest.json`, `logs/development_bugfix_loop/latest.json`, `logs/development_work_queue/latest.json`.
2. Selects at most one item per cycle by deterministic ordering.
3. Calls `reporting.execution_authority.classify(...)` for the implied actions.
4. Builds a `step5_plan.v1.json` artefact under `logs/step5_plan/<cycle_id>.json` with:
   - `creates_real_branches: false`
   - `opens_real_prs: false`
   - `actually_modifies_target: false`
   - `mergeable_by_agent: false`
   - `deployable_by_agent: false`
5. Updates `logs/step5_plan/history.jsonl` (bounded 90-entry rolling window).
6. Writes `logs/step5_loop/latest.json` snapshot.
7. Records a single audit-ledger event (`reporting.agent_audit.append_event`) with `autonomy_level_claimed=0` and the cycle_id.
8. Exits 0 even when the cycle halts on an authority deny — Step 5.0 is diagnostic, not gating.

### 13.3 What Step 5.0 does **not** do

- No git operations.
- No `gh` calls.
- No subprocess.
- No network.
- No file writes outside `logs/step5_*/`.
- No QRE artefact mutation (pinned by before/after sha256 byte equality test).
- No autonomous merge or deploy.

### 13.4 Step 5.0 invariants pinned by tests

```
mode = "dry_run_only"
creates_real_branches = false
opens_real_prs = false
actually_modifies_target = false
mutates_qre_artifacts = false
mutates_frozen_contracts = false
mutates_protected_paths = false
uses_subprocess_or_network = false
operator_step5_authorisation_required = true
step5_implementation_allowed = false
```

### 13.5 Acceptance criteria (Step 5.0 implementation PR)

- All §10 tests committed *first* in their own PR (test-first ordering).
- `reporting.development_step5_loop` lands in a follow-up PR that turns the tests green.
- Adjacent unit suite green.
- Smoke green.
- Governance lint green.
- Operational digest on the PR branch shows the new artefact present, A12 `step5_readiness.step5_implementation_allowed` still `false`.
- E2E proof on the PR branch reports `proof_status=passed`, `protected_path_violations=[]`, `qre_coupling_violations=[]`, `missing_capabilities=[]`, plus optionally a new flow step `step5_dry_run_pickup` if the operator chooses to extend the A13 lifecycle (out-of-scope for the design slice).
- PR body includes the operator's explicit authorisation (G10) and the kill-switch path.

### 13.6 What comes after Step 5.0

Step 5.1 (bounded edits on a feature branch, no merge) would be a
**separate** PR series at a later date. It requires:

- the §11 documentation modernization to have merged;
- a new ADR amendment opening L2 (observability + CI writes per-change approval) or proposing a Step 5-specific allowlist;
- a fresh release-gate report and rollback drill;
- explicit operator authorisation in the Step 5.1 PR body.

Step 5.2 (merge recommendation) requires the L4 unlock per
ADR-015 (≥30 days L1–3 stable + ADR amendment).

Step 5 **never** reaches L5 or L6.

---

## Appendix A — Cross-reference summary

| Topic | Document |
|---|---|
| Authority chain | [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md) |
| Truth-authority settlement | [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md) |
| Per-action authority decisions | [`docs/governance/execution_authority.md`](execution_authority.md) |
| Autonomy ladder L0–L6 | [`docs/governance/autonomy_ladder.md`](autonomy_ladder.md) |
| No-touch paths | [`docs/governance/no_touch_paths.md`](no_touch_paths.md) |
| Branch → PR → CI → merge protocol | [`docs/governance/github_pr_lifecycle.md`](github_pr_lifecycle.md) |
| Branch protection setup | [`docs/governance/branch_protection_checklist.md`](branch_protection_checklist.md) |
| ADE A8 work queue | [`docs/governance/development_work_queue.md`](development_work_queue.md) |
| ADE A9 release gate | [`docs/governance/development_release_gate.md`](development_release_gate.md) |
| ADE A10 bugfix loop | [`docs/governance/development_bugfix_loop.md`](development_bugfix_loop.md) |
| ADE A11 delegation | [`docs/governance/development_delegation.md`](development_delegation.md) |
| ADE A12 operational digest | [`docs/governance/development_operational_digest.md`](development_operational_digest.md) |
| ADE A13 E2E proof | [`docs/governance/development_e2e_proof.md`](development_e2e_proof.md) |
| Documentation audit | [`docs/governance/documentation_audit.md`](documentation_audit.md) |
| Step 5 design readiness review | [`docs/governance/step5_design_readiness.md`](step5_design_readiness.md) |
| Step 5 ADR draft | [`docs/adr/_drafts/ADR-017-step5-autonomous-implementation-loop.md`](../adr/_drafts/ADR-017-step5-autonomous-implementation-loop.md) |
| Autonomous Development Track roadmap | [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt) |
| QRE Feature Build Track roadmap | [`docs/roadmap/Roadmap v6.md`](<../roadmap/Roadmap v6.md>) |

## Appendix B — What this document is not

- Not a commitment to ship Step 5 on any timeline.
- Not an authorisation for any Step 5 implementation PR.
- Not a request to flip `step5_implementation_allowed` from its hard-pinned `False`.
- Not a request to amend ADR-015 or the autonomy ladder.
- Not a QRE deliverable. QRE work resumes at v3.15.16 / v3.15.17 under Roadmap v6 and is disjoint from this design.
- Not a deploy plan. Step 5 has no deploy step.

## End of design document
