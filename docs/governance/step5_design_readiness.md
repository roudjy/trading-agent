# Step 5 Design Readiness Review — 2026-05-08

> Read-only review against the post-A13 / post-PR-#146 state. Operator-
> requested. **No Step 5 implementation is performed by this report.**
> No QRE behavior changed. No research artifact mutated. No
> Intelligent Routing change. ADE/QRE loose coupling preserved.

## Status

`design_readiness_review_complete`. Step 5 design planning may begin.
Step 5 implementation remains explicitly blocked behind two
independent operator-controlled gates (governance-bootstrap docs
cleanup AND explicit operator authorisation), neither of which is
auto-resolvable by ADE.

## Audit metadata

- **review_date_utc**: 2026-05-08
- **branch**: `docs/step5-design-readiness-review`
- **base**: `main`
- **base_head_sha**: `277ab6a` (post-PR #146 — markdown documentation audit)
- **predecessor merge SHAs**:
  - `73830e1` — A13 failure-mode coverage backfill (#145)
  - `f27db1c` — A13 mark Complete + ADE E2E proof PASSED (#144)
  - `210eeca` — A13 E2E proof harness (#143)
  - `3f80479` — A12 operational digest (#140)
  - `fda1814` — A11 bounded delegation (#138)
  - `21d9064` — A10 bugfix loop (#136)
  - `0241775` — A9 release gate (#134)
  - `09bb439` — A8 operating queue foundation (#132)
- **canonical authority docs consulted**:
  - [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md)
  - [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  - [`docs/governance/execution_authority.md`](execution_authority.md)
  - [`docs/governance/autonomy_ladder.md`](autonomy_ladder.md)
  - [`docs/governance/no_touch_paths.md`](no_touch_paths.md)
  - [`docs/governance/github_pr_lifecycle.md`](github_pr_lifecycle.md)
  - [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt)
  - [`docs/governance/development_operational_digest.md`](development_operational_digest.md)
  - [`docs/governance/development_e2e_proof.md`](development_e2e_proof.md)
  - [`docs/governance/documentation_audit.md`](documentation_audit.md) (PR #146)

## Live evidence (run against `main` @ `277ab6a`)

### A12 operational digest output

`logs/development_operational_digest/latest.json` regenerated 2026-05-08T08:33:20Z.

- `note`: `all_upstream_artifacts_present`
- `presence_count`: `4 / 4` (queue + release_gate + bugfix_loop + delegation)
- `module_versions`: queue `v3.15.16.A8`, release_gate `v3.15.16.A9`, bugfix_loop `v3.15.16.A10`, delegation `v3.15.16.A11`, digest `v3.15.16.A12`
- `discipline_invariants`:
  - `auto_authorises_step5: false`
  - `mutates_upstream_artifacts: false`
  - `operator_step5_authorisation_required: true`
  - `sends_notifications: false`
  - `writes_dashboard: false`
- `step5_readiness`:
  - `step5_design_planning_allowed: true`
  - `step5_implementation_allowed: false`
  - `step5_implementation_blocker: readiness_criteria_not_satisfied`
  - `step5_ready: false`

### A13 E2E proof harness output

`reporting.development_e2e_proof --no-write` against current main:

- `module_version`: `v3.15.16.A13`
- `proof_status`: `passed`
- `autonomous_development_possible`: `true`
- `flow_steps`: 8/8 passed (`roadmap_pickup`, `agent_refinement`, `prioritisation`, `execution_readiness`, `bounded_execution_or_simulation`, `validation`, `release_gate`, `digest_report_out`)
- `protected_path_violations`: `[]`
- `qre_coupling_violations`: `[]`
- `missing_capabilities`: `[]`
- `human_needed_items`: `0`
- `step5_design_planning_allowed`: `true`
- `step5_implementation_allowed`: `false`
- `discipline_invariants`:
  - `actually_modifies_target: false`
  - `creates_real_branches: false`
  - `mutates_production_artifacts: false`
  - `opens_real_prs: false`
  - `operator_step5_authorisation_required: true`
  - `uses_subprocess_or_network: false`
- `final_operator_summary`: "ADE end-to-end autonomous development loop is possible in proof-harness mode. Step 5 design planning is allowed; Step 5 implementation requires separate operator authorisation."

### ADE-core unit tests

`pytest tests/unit/test_development_{work_queue,release_gate,bugfix_loop,delegation,operational_digest,e2e_proof}.py -q` — **220 passed** in 6.94s.

### Documentation audit (PR #146)

`docs/governance/documentation_audit.md` records: 0 contradictory docs, 0 high-risk findings, 5 deferred minor cleanups (CLAUDE.md / AGENTS.md / INSTALLATIEGIDS.md / docs/RESEARCH_CONTEXT.md / frontend_agent_control_layer_roadmap.md).

---

## Question 1: Is Step 5 design planning allowed?

**Yes.**

| Source | Field | Value |
|---|---|---|
| `reporting.development_operational_digest` | `step5_readiness.step5_design_planning_allowed` | `true` |
| `reporting.development_e2e_proof` | `step5_design_planning_allowed` | `true` |
| `docs/governance/development_operational_digest.md` | "operator-authored design planning is unrestricted" | binding |
| `docs/governance/development_e2e_proof.md` | "Step 5 design planning is allowed" | binding |
| `docs/roadmap/autonomous_development.txt` §A13 "After A13 completes" | "Step 5 design planning is allowed." | binding |

**Implication:** the operator (or an operator-driven product-owner / planner sub-agent invocation) may begin authoring a Step 5 design document. The natural location is `docs/governance/step5_design_*.md`, `docs/adr/_drafts/ADR-017-step5-*.md`, or a new section in `docs/roadmap/autonomous_development.txt` (the latter is `canonical_roadmap` and remains operator-authored only).

## Question 2: Is Step 5 implementation allowed?

**No.**

Three independent code-level / doctrine-level gates must be cleared before any Step 5 implementation can land. **All three are currently held closed.**

| Gate | Currently | Source of truth |
|---|---|---|
| **Gate A — operational digest readiness** (`step5_ready=true`) | `false` | `step5_readiness.step5_ready` is `false` because `queue_human_needed_signal_meaningful=false` (the operator-authored `docs/development_work_queue/seed.jsonl` is currently empty by design). All other 9 criteria are `true`. Resolved by the operator seeding the queue with at least one item that legitimately requires either human attention or `ready_for_autonomous_action` — the current empty state is correct for "no work in flight". |
| **Gate B — explicit operator authorisation** | absent | Hard-pinned in `reporting.development_operational_digest._evaluate_step5` (`step5_implementation_allowed=False`) and `reporting.development_e2e_proof._project_step5_signals` (`step5_implementation_allowed: digest['step5_readiness']['step5_implementation_allowed']`). The flag is wired to a literal `False` constant in the code path; flipping it requires a code change pinned by tests, **not** a runtime input. The operator can only authorise Step 5 implementation by amending the relevant ADE module(s) and the `docs/roadmap/autonomous_development.txt` §A13 closing block, both of which are `canonical_policy_doc` / `canonical_roadmap` and require human-authored CODEOWNERS-reviewed PRs. |
| **Gate C — autonomy ladder Level 6** | `permanently_disabled` | Per `docs/adr/ADR-015-claude-agent-governance.md` §Doctrine 1 and `docs/governance/autonomy_ladder.md`: Level 6 ("autonomous merge / deploy") is **permanently disabled** in this project. Step 5 implementation that performs *real* merges or deploys is therefore architecturally bounded by that ceiling. Any Step-5 design that does not respect the L6 ceiling is out-of-scope by ADR-015. |

**Implication:** Step 5 implementation is doubly held — by the digest's `step5_implementation_allowed=false` constant *and* by the autonomy-ladder L6 prohibition. Neither can be auto-flipped by ADE; both require explicit human-authored PRs.

## Question 3: Which A9–A13 criteria are satisfied?

### A9 release-gate criteria (closed verdicts, evidence keys)

| Property | Live |
|---|---|
| Module version | `v3.15.16.A9` |
| Closed verdict vocabulary | 5 verdicts (`go`, `go_with_followups`, `no_go_blocked`, `no_go_human_needed`, `not_evaluated`) |
| Evidence input present | `false` (no operator-supplied evidence input on this main; expected — A9 evidence collectors are an out-of-core surface) |
| `release_gate_artifact_present` | ✅ |
| `release_gate_no_protected_surface_leakage` | ✅ |
| `protected_surface` count | `0` |

### A10 bugfix-loop criteria

| Property | Live |
|---|---|
| Module version | `v3.15.16.A10` |
| Discipline invariants | `auto_modifies_code=false`, `auto_creates_branches=false`, `auto_opens_prs=false`, `operator_promotion_required=true`, `writes_to_seed_jsonl=false`, `writes_to_bugfix_seed_jsonl=false` |
| `bugfix_loop_artifact_present` | ✅ |
| `bugfix_loop_no_test_weakening_proposals` | ✅ |
| Failure-mode coverage backfill | merged via PR #145 (commit `73830e1`) |

### A11 delegation criteria

| Property | Live |
|---|---|
| Module version | `v3.15.16.A11` |
| Discipline invariants | `fuzzy_parsing=false`, `operator_promotion_required=true`, `writes_to_delegation_seed_jsonl=false` |
| `delegation_artifact_present` | ✅ |
| `delegation_no_fuzzy_parsing_evidence` | ✅ |

### A12 operational digest criteria

| Property | Live |
|---|---|
| Module version | `v3.15.16.A12` |
| Discipline invariants | `auto_authorises_step5=false`, `mutates_upstream_artifacts=false`, `sends_notifications=false`, `writes_dashboard=false`, `operator_step5_authorisation_required=true` |
| `presence_count` | `4 / 4` |
| `note` | `all_upstream_artifacts_present` |
| `step5_readiness` reported | yes |
| 9-of-10 closed criteria | ✅ |

### A13 end-to-end proof criteria

| Property | Live |
|---|---|
| Module version | `v3.15.16.A13` |
| `proof_status` | `passed` |
| `autonomous_development_possible` | `true` |
| 8 flow steps passed | ✅ |
| `protected_path_violations` | `[]` |
| `qre_coupling_violations` | `[]` |
| `missing_capabilities` | `[]` |
| Discipline invariants | `actually_modifies_target=false`, `creates_real_branches=false`, `opens_real_prs=false`, `mutates_production_artifacts=false`, `uses_subprocess_or_network=false`, `operator_step5_authorisation_required=true` |
| Failure-mode coverage backfill | included via PR #145 (commit `73830e1`) |

### Aggregate

| Bucket | Status |
|---|---|
| ADE A8–A13 modules present and tested | ✅ (220/220 ADE-core unit tests pass on `277ab6a`) |
| ADE/QRE loose coupling | ✅ (no `research`, `dashboard`, `automation`, `broker`, `agent.risk`, `agent.execution`, `reporting.intelligent_routing` import from any ADE module — pinned by AST-level test) |
| Frozen contract integrity | ✅ (release_gate `frozen_hash_status` evidence keys closed; protected-path delta checks closed) |
| GitHub PR lifecycle protocol | ✅ (PRs #143 / #144 / #145 / #146 all followed canonical flow) |
| Documentation contradictions vs canonical authority chain | ✅ none (per PR #146) |

## Question 4: Which readiness criteria remain unsatisfied?

### Code-level (digest `step5_ready` math)

Only **one** of the ten closed `STEP5_CRITERIA` is currently false:

- `queue_human_needed_signal_meaningful` — `false`. The operator-authored `docs/development_work_queue/seed.jsonl` is empty by default (correct, by design). The criterion fires `true` when at least one queue item carries `requiring_human_operator > 0` OR `ready_for_autonomous_action > 0`. With zero items, both counts are zero, so the criterion stays `false`.

This is **not** a defect of ADE; it is the queue truthfully reporting "no work currently in flight". The criterion is intentionally written so an empty queue cannot accidentally flip `step5_ready` to `true`.

### Doctrine-level (independent of digest math)

The following gates are independent of the digest and remain held closed regardless of queue state:

1. **`step5_implementation_allowed`** is hard-pinned to `False` in `reporting.development_operational_digest._evaluate_step5` and read-only in `reporting.development_e2e_proof._project_step5_signals`. Flipping this flag requires a code change pinned by tests AND an amendment of `docs/governance/development_operational_digest.md` AND an entry in `docs/roadmap/autonomous_development.txt` — all `canonical_policy_doc` / `canonical_roadmap` per `docs/governance/execution_authority.md`.
2. **Autonomy ladder Level 6** is permanently disabled per ADR-015 §Doctrine 1.
3. **`automation/live_gate.py`** is no-touch and CODEOWNERS-protected per ADR-015 §Doctrine 4 + `docs/governance/no_touch_paths.md`. Step 5 implementation must not, by design, modify the live-gate barrier.
4. **No real branch / PR creation** in any ADE-core module, pinned at AST level by tests on `reporting.development_e2e_proof` (`creates_real_branches=false`, `opens_real_prs=false`, `uses_subprocess_or_network=false`). Step 5 implementation that introduces a real branch / PR creation surface must clear the no-touch + governance-bootstrap path.

### Bookkeeping (does not gate anything but is worth resolving before Step 5 design ships)

- **Deferred docs cleanup from PR #146**:
  - `CLAUDE.md` modernization (backlog AB-0008).
  - `AGENTS.md` §4 / §5 / §11 rewrite (Codex CLI relics).
  - `INSTALLATIEGIDS.md` paper-readiness pointer.
  - `docs/RESEARCH_CONTEXT.md` archival.
  - `docs/governance/frontend_agent_control_layer_roadmap.md` "paused" header note.

These do not satisfy or unsatisfy any closed criterion. See Q5 / Q6 below for how they relate to Step 5.

## Question 5: Does deferred CLAUDE.md / AGENTS.md modernization block Step 5 *design*?

**No.**

Rationale:

- Neither `step5_design_planning_allowed` nor any of the ten `STEP5_CRITERIA` evaluates the content of `CLAUDE.md` or `AGENTS.md`. Both are reported as `true` in the live digest.
- `docs/governance/development_e2e_proof.md` and `docs/roadmap/autonomous_development.txt` §A13 explicitly state design planning is unblocked once A13 is complete. A13 is complete (`f27db1c`, `210eeca`, `73830e1`).
- The audit (PR #146) found **0 contradictory** docs in the canonical authority chain. The misleading items (CLAUDE.md, AGENTS.md narrative) are off-the-critical-path and do not invalidate any policy doc, ADR, classifier output, or hook.
- Step 5 design is itself a *document-authoring* activity. It can name CLAUDE.md / AGENTS.md as future cleanup dependencies without being blocked by them.

**Operator note:** if the Step 5 design surfaces any *new* requirement that tightens CLAUDE.md / AGENTS.md semantics (for example, a new agent role, a new authority gate, or a new no-touch carve-out), the design doc should explicitly call out the dependency so the cleanup phase can be scoped to satisfy it. None of the criteria below currently demand that.

## Question 6: Does deferred CLAUDE.md / AGENTS.md modernization block Step 5 *implementation*?

**Yes — soft-block, alongside the harder gates.**

Reasoning:

- Step 5 implementation introduces *real* autonomous code-modification capability into the development loop. ADR-015 §Doctrine 4 ("Live trading code is human-only") and §Doctrine 11 ("Run-summary doctrine") require that the human-readable contributor docs accurately describe what agents can and cannot do *before* such capability is enabled.
- `AGENTS.md` §4 currently describes a stale three-actor model (Claude architect / Codex CLI / Claude Code). Letting Step 5 ship while contributors still see "Codex CLI implements" would create a documentation gap large enough that the reviewer convention which backs ADR-015 §Doctrine 7 ("Self-protected layer") starts to fray.
- `CLAUDE.md` does not currently reference ADR-015, the autonomy ladder, the GitHub PR lifecycle, the QRE/ADE split, or the Execution Authority. A real autonomous-implementation loop must not be enabled while the load-bearing session-start doc still describes a 30-day "Dag 1-30" trading-agent roadmap from the project's pre-QRE phase.

**However**, this is a *soft* block: it is recoverable by a single human-authored governance-bootstrap PR. It is not in itself sufficient to authorise Step 5 implementation — it is necessary. The harder gates (`step5_implementation_allowed=false` constant, L6 disabled, no-touch live-gate) remain.

**Suggested ordering:** the docs cleanup PR can be authored at any time after Step 5 *design* lands, as long as it precedes Step 5 *implementation*. It does not need to be done first.

## Question 7: What is the minimal safe next sequence?

The following sequence preserves all invariants (ADE/QRE loose coupling, no-touch paths, autonomy ladder, frozen contracts, no QRE behavior change, no Intelligent Routing change, no v3.15.17 work) and lands Step 5 design without exposing Step 5 implementation surface.

```
Step 1 — Step 5 Design Document (operator-authored or product-owner agent)
  Branch:   docs/step5-design-doc
  Surface:  docs/governance/step5_design.md  (new)  AND/OR
            docs/adr/_drafts/ADR-017-step5-autonomous-implementation-loop.md (new)
  Touches:  docs only; no code; no canonical_roadmap edit
  Constraints: must answer
    - what "Step 5 implementation" actually means, scope-bounded
    - which AUTO_ALLOWED action types it is allowed to perform
    - what its mandatory readiness criteria additions to STEP5_CRITERIA would be
    - which paths it is allowed to write to (allowlist, never denylist)
    - which paths it is forever forbidden from (live-gate, frozen
      contracts, .claude/**, branch-protection config, deploy script,
      authority surface, secrets)
    - what its rollback story is
    - what its evidence-collection contract is (pure, deterministic)
    - what its kill-switch is
  Test plan: governance_lint + smoke
  PR lifecycle: standard (gh CLI, squash-merge, post-merge gates)

Step 2 — Documentation modernization (governance-bootstrap PR; operator-authored)
  Branch:   docs/markdown-modernization-cleanup
  Surface:  CLAUDE.md, AGENTS.md, INSTALLATIEGIDS.md,
            docs/RESEARCH_CONTEXT.md,
            docs/governance/frontend_agent_control_layer_roadmap.md
  Class:    canonical_policy_doc (because it edits CLAUDE.md / AGENTS.md)
  Required by: ADR-015 §Doctrine 4 + §Doctrine 7; CODEOWNERS-reviewed
  Operator action: human authorship; agent-driven edits are blocked
                   by .claude/hooks/deny_outside_agent_allowlist.py.

Step 3 — Operator Step 5 readiness review
  Operator opens or runs:
    - python -m reporting.development_operational_digest
    - python -m reporting.development_e2e_proof --no-write
  Confirms:
    - step5_design_planning_allowed: true
    - step5_implementation_allowed: false (still)
    - step5_ready: true OR false (operator decides whether to seed
      the work queue first; an empty queue is acceptable for review)
    - protected_path_violations / qre_coupling_violations: []
    - documentation_audit.md flagged items resolved or knowingly deferred

Step 4 — Operator authorisation decision
  Operator decides (out of band, signed in writing in the next
  governance PR's body) whether to:
    a. Approve Step 5 implementation entry into the roadmap
       (canonical_roadmap edit to docs/roadmap/autonomous_development.txt
       opening a new "Step 5" section), OR
    b. Defer Step 5 implementation indefinitely.

Step 5 implementation (only after Step 4a)
  Out of scope for this readiness review.
  Will require:
    - a code change in reporting.development_operational_digest
      (or a new ADE module) to expose step5_implementation_allowed
      with a more precise gate than the current literal False
    - new closed-vocabulary additions pinned by tests
    - new no-touch carve-outs as needed via a governance-bootstrap PR
    - explicit ADR amendment if any autonomy-ladder semantics change
    - a fresh release-gate report and rollback drill before any
      capability switch flips
```

The key property of this sequence is that it **never** asks ADE to authorise its own escalation. Every transition that increases agent capability is human-authored, CODEOWNERS-reviewed, and recorded in the canonical authority chain.

## Out of scope for this report

- Implementing Step 5.
- Modifying QRE behavior.
- Starting v3.15.17 (Sampling Intelligence).
- Changing Intelligent Routing.
- Mutating research artifacts (`research/research_latest.json`, `research/strategy_matrix.csv`, frozen v1 schemas).
- Editing `CLAUDE.md`, `AGENTS.md`, `INSTALLATIEGIDS.md`, or any canonical_policy_doc / canonical_roadmap.
- Editing `.claude/**`, branch protection, CI workflows, security policy.
- Coupling ADE to QRE or vice-versa.

## Validation

- `python scripts/governance_lint.py` — `OK`.
- `python -m pytest tests/smoke -q` — `18 passed`.
- `python -m pytest tests/unit/test_development_{work_queue,release_gate,bugfix_loop,delegation,operational_digest,e2e_proof}.py -q` — `220 passed`.
- `python -m reporting.development_operational_digest` — produces digest with `step5_design_planning_allowed=true`, `step5_implementation_allowed=false`, `step5_ready=false`.
- `python -m reporting.development_e2e_proof --no-write` — `proof_status=passed`, `autonomous_development_possible=true`, `protected_path_violations=[]`, `qre_coupling_violations=[]`.
- Diff scope of this PR: one new file (`docs/governance/step5_design_readiness.md`); no protected paths touched.

## End of report
