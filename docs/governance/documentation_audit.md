# Markdown Documentation Audit — 2026-05-08

> Read-only audit of the repository's Markdown / governance / roadmap
> documentation against the current QRE + ADE state. Operator-requested.
> No protected semantics changed by this report. Cleanup is deliberately
> small and additive; the larger rewrites identified below are flagged
> for a future operator-authored cleanup phase.

## Status

`audit_pass`. Findings recorded; minor cleanups deferred to a follow-up
docs-only cleanup phase per the operator brief (the hook layer's
`deny_outside_agent_allowlist` correctly blocks agent edits to
top-level `CLAUDE.md` / `AGENTS.md` / `INSTALLATIEGIDS.md`, so those
edits must come through a human-authored governance-bootstrap PR).

## Audit metadata

- **audit_date_utc**: 2026-05-08
- **branch**: `docs/markdown-audit-and-small-cleanup`
- **base**: `main`
- **base_head_sha**: `73830e1` (post-A13 backfill `test(A13): failure-mode coverage backfill for ADE E2E proof harness (#145)`)
- **active_phase_branch_detected**: no — main is clean post-A13; A13 marked Complete by PRs #143/#144/#145; no in-flight A14 branch
- **open_PRs_at_audit_start**: dependabot only (#81–#85), no in-flight ADE/QRE feature work
- **untracked**: `research/discovery_sprints/` (operator-owned data; not in scope for this audit, not modified)
- **scope**: `*.md` and governance/roadmap `*.txt` under repo root and `docs/**`. `frontend/node_modules/**`, `.tmp/**`, vendored READMEs are out of scope.

## Canonical truth model (as of 2026-05-08)

These are the documents the audit treats as *truth-of-record*. Any
Markdown that contradicts them is classified `contradictory` or
`misleading`.

| Domain | Canonical document |
|---|---|
| Authority pluralism (registry / presets / catalog / candidate lifecycle / paper readiness / live governance) | [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md) |
| Agent governance / autonomy chain | [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md) |
| Execution Authority (what Claude may do) | [`docs/governance/execution_authority.md`](execution_authority.md) |
| GitHub branch → PR → CI → squash-merge → post-merge protocol | [`docs/governance/github_pr_lifecycle.md`](github_pr_lifecycle.md) |
| Agent autonomy ladder (levels 0–6, level 6 permanently disabled) | [`docs/governance/autonomy_ladder.md`](autonomy_ladder.md) |
| No-touch path doctrine | [`docs/governance/no_touch_paths.md`](no_touch_paths.md) |
| ADE Autonomous Development Track roadmap (A1–A13) | [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt) |
| QRE Feature Build Track roadmap | [`docs/roadmap/Roadmap v6.md`](<../roadmap/Roadmap v6.md>) |
| ADE A8 work queue | [`docs/governance/development_work_queue.md`](development_work_queue.md) |
| ADE A9 release gate | [`docs/governance/development_release_gate.md`](development_release_gate.md) |
| ADE A10 bugfix loop | [`docs/governance/development_bugfix_loop.md`](development_bugfix_loop.md) |
| ADE A11 delegation | [`docs/governance/development_delegation.md`](development_delegation.md) |
| ADE A12 operational digest | [`docs/governance/development_operational_digest.md`](development_operational_digest.md) |
| ADE A13 E2E proof harness | [`docs/governance/development_e2e_proof.md`](development_e2e_proof.md) |
| Docs explicitly archived (historical, not parsed as canonical) | `docs/roadmap/archive/**` |

## Project split (verified against current code/tests)

- **QRE** = Quant Research Engine (research execution platform under `research/`, frozen v1 schemas, evidence ledgers, Roadmap v6).
- **ADE** = Autonomous Development Engine (governance + work queue + release gate + bugfix loop + delegation + operational digest + E2E proof under `reporting/development_*.py`).
- The two tracks must remain loosely coupled. The operational digest and E2E proof modules import only ADE peers + stdlib (verified at AST level by their unit tests). No ADE module imports `research`, `dashboard`, `automation`, `broker`, `agent.risk`, `agent.execution`, or `reporting.intelligent_routing`. This invariant is load-bearing.

## Phase status (verified against `docs/roadmap/autonomous_development.txt` and recent merge SHAs)

| Phase | Status | Merge SHA | PR |
|---|---|---|---|
| A1–A7 | Complete (Autonomous Development Governance Foundation) | — | #110–#116 |
| A8 | Complete (Operating Queue Foundation) | `09bb439` | #132 |
| A9 | Complete (Release-Gate Integration) | `0241775` | #134 |
| A10 | Complete (Bugfix Loop intake-only) | `21d9064` | #136 |
| A11 | Complete (Bounded Roadmap Delegation) | `fda1814` | #138 |
| A12 | Complete (Operational Digest / Observability) | `3f80479` | #140 |
| A13 | Complete (E2E Proof Harness, `proof_status=passed`, `step5_design_planning_allowed=true`, `step5_implementation_allowed=false`) | `210eeca` | #143 (+ #144 chore + #145 backfill `73830e1`) |

**Critical wording correction already adopted in canonical docs:**

> Autonomous Development Governance Foundation: complete (A1–A7).
> Autonomous Development Operating Queue: begins at A8.
> Fully autonomous code-development loop: A9–A12 complete; ADE end-to-end proof harness (A13) complete.
> Step 5 (real autonomous implementation loop): design planning allowed; implementation requires separate operator authorisation and is **not** auto-enabled by A13.

The older "Autonomous Development Track complete after PRs #110–#116" wording survives in some places below — those are flagged.

---

## Classification summary

| Classification | Count |
|---|---|
| current | 21 |
| minor_cleanup | 5 |
| archive_ok | 6 |
| missing_cross_reference | 3 |
| misleading | 3 |
| contradictory | 0 |
| candidate_archive | 1 |
| candidate_rewrite | 2 |

**No high-risk contradictions found** with the canonical authority chain
(ADR-014 / ADR-015 / Execution Authority / no-touch paths / GitHub PR
lifecycle / autonomy ladder). The misleading items are role-vocabulary
relics (Codex CLI, original 30-day trading-agent roadmap) that do not
weaken governance posture but do confuse a fresh contributor.

## Per-file classification

| File | Classification | Issue | Risk | Recommended action |
|---|---|---|---|---|
| `CLAUDE.md` | misleading + missing_cross_reference | Describes the original 30-day "trading-agent" roadmap and Dutch operator playbook that the project has long since outgrown. Does not mention QRE/ADE split, ADR-015, autonomy ladder, GitHub PR lifecycle, Execution Authority. Only ADR-014 is referenced (line 10). The visible roadmap (lines 344–438) describes "Dag 1-30" steps that are entirely superseded by Roadmap v6 + autonomous_development.txt. | medium | rewrite_later (operator-authored governance-bootstrap PR — agent edits are blocked by `deny_outside_agent_allowlist`). Backlog item AB-0008 already tracks "CLAUDE.md restructuring into per-layer files (deferred)". |
| `AGENTS.md` | misleading | Describes a "Claude (architect) → Codex CLI (implementation engine) → Claude Code (precision tool)" three-actor model that was superseded by the v3.15.15.12 governance layer (15 sub-agents under `.claude/agents/`, ADR-015, autonomy ladder L0–L6) and by the ADE A1–A13 sequence. Section 4 ("AI Tooling Roles") and Section 5 ("Execution Workflow") are stale. Section 11 ("Git Workflow") predates the GitHub CLI lifecycle protocol (#132, 2026-05-07). Section 9 ("Session Start Protocol") still says `cd ~/trading-agent && source .venv/bin/activate && git pull && cat research/research_latest.json` and is not wrong but is incomplete. | medium | rewrite_later (operator-authored governance-bootstrap PR). Replace §4/§5/§11 with pointers to `docs/governance/agent_handoff_protocol.md`, `docs/governance/github_pr_lifecycle.md`, ADR-015, autonomy ladder. ADR-014 cross-reference at §3 is correct and stays. |
| `INSTALLATIEGIDS.md` | minor_cleanup | One-evening setup guide for the original trading-agent (Bitvavo + Kraken + Polymarket + IBKR + Hetzner CX22). Internally consistent and accurate. The "STAP 7 — Paper trading fase" criteria (win-rate >55%, 50 trades) predate the v3.15+ paper-readiness gate (`research/paper_readiness.py` with closed blocking-reason taxonomy). | low | update_wording — a future cleanup phase should add a small "for current paper-readiness criteria see `docs/handoffs/v3.15-to-v3.16.md` §2" pointer. No security or governance risk. |
| `SECURITY.md` | current | Accurately describes the v3.15.15.12 Claude Agent Governance & Safety Layer trust boundaries, the live-gate barrier (`automation/live_gate.py`), credential rotation order, the deferred history-rewrite runbook, and the audit-ledger redaction rules. References ADR-015, no-touch paths, branch-protection checklist, key-rotation log — all current. | low | no_change |
| `CHANGELOG.md` | current | Entries through v3.15.15.9. Header explicitly documents that "Live trading / orchestration surfaces outside the research path are not tracked in this file" — this is a deliberate QRE-only scope. ADE A1–A13 deliberately do **not** appear here; ADE phase-completion records live in `docs/roadmap/autonomous_development.txt` and the per-phase governance docs under `docs/governance/`. | low | no_change |
| `VERSION` | current | `3.15.15.9`. Bumped only via human-approved PR per `docs/governance/no_touch_paths.md`. | low | no_change |
| `README.md` (root) | not_present | No root README in this repo. Not a defect — `CLAUDE.md`, `AGENTS.md`, `INSTALLATIEGIDS.md`, `docs/orchestrator_brief.md` cover their respective audiences. | low | no_change (a `README.md` could be added later as a thin entry-point pointer doc, but is not required). |
| `frontend/README.md` | current | Frontend Vite dev-server quickstart. Accurate. | low | no_change |
| `docs/orchestrator_brief.md` | current + missing_cross_reference (already addressed) | Top-of-file mandates the GitHub CLI lifecycle protocol (line 3); ADR-014 §A authority note is present (line 47). The §1–§5 base specification is the load-bearing QRE architecture spec; §6–§14 addenda track v3.6 → v3.15. The brief does not yet have an ADE pointer at the top — but it is *deliberately* a QRE document, so this is by design rather than a defect. | low | no_change |
| `docs/governance/github_pr_lifecycle.md` | current | Canonical operator-facing protocol. References Execution Authority, branch protection invariants, post-merge verification, failure modes. Update history records the A8 PR (#132). | low | no_change |
| `docs/governance/github_pr_lifecycle/schema.v1.md` | current | Schema for `reporting.github_pr_lifecycle`. | low | no_change |
| `docs/governance/github_pr_lifecycle_integration.md` | current | Module integration runbook for `reporting.github_pr_lifecycle` (v3.15.15.17). | low | no_change |
| `docs/governance/execution_authority.md` | current | Canonical policy doc for v3.15.16.10. Documents the two canonical roadmap docs (`autonomous_development.txt`, `Roadmap v6.md`) and the archive carve-out for `docs/roadmap/archive/**`. | low | no_change |
| `docs/governance/development_work_queue.md` | current | A8 governance doc. Adopts the "A1–A7 = governance foundation; A8 = queue foundation; A9–A12 = future" framing. | low | no_change |
| `docs/governance/development_release_gate.md` | current | A9 governance doc. Closed verdicts (5), evidence keys (6), evidence input contract. | low | no_change |
| `docs/governance/development_bugfix_loop.md` | current | A10 governance doc. Intake-only invariants pinned. | low | no_change |
| `docs/governance/development_delegation.md` | current | A11 governance doc. Marker grammar + sidecar. | low | no_change |
| `docs/governance/development_operational_digest.md` | current | A12 governance doc. step5_readiness criteria. | low | no_change |
| `docs/governance/development_e2e_proof.md` | current | A13 governance doc. Lifecycle steps, discipline invariants, `step5_implementation_allowed=false`. | low | no_change |
| `docs/governance/agent_governance.md` | current | Public overview of the Agent Governance & Safety Layer. | low | no_change |
| `docs/governance/autonomy_ladder.md` | current | Levels 0–6, per-agent caps. | low | no_change |
| `docs/governance/no_touch_paths.md` | current | Mirror of `.claude/hooks/deny_no_touch.py:NO_TOUCH_GLOBS`. | low | no_change |
| `docs/governance/permission_model.md` | current | Permission policy structure. | low | no_change |
| `docs/governance/no_test_weakening.md` | current | Test-weakening doctrine. | low | no_change |
| `docs/governance/hooks_runtime_policy.md` | current | Hook runtime fail-closed policy. | low | no_change |
| `docs/governance/audit_chain.md` | current | Hash-chained audit ledger spec. | low | no_change |
| `docs/governance/provenance.md` | current | Build provenance. | low | no_change |
| `docs/governance/branch_protection_checklist.md` | current | GitHub UI settings for `main`. | low | no_change |
| `docs/governance/key_rotation_log.md` | current | Append-only rotation log. | low | no_change |
| `docs/governance/manual_blockers.md` | current | Items requiring operator action outside Claude. | low | no_change |
| `docs/governance/release_gate.md` / `release_gate_checklist.md` / `release_digests.md` / `rollback_drill.md` / `sha_pin_review.md` | current | Release-gate-agent operator runbook set. | low | no_change |
| `docs/governance/agent_handoff_protocol.md` | current | Eight canonical agent roles. Sibling docs cross-referenced. | low | no_change |
| `docs/governance/agent_flow.md` / `task_board.md` / `human_needed.md` | current | v3.15.16.6 → .8 read-only state-machine projections. | low | no_change |
| `docs/governance/roadmap_priority.md` / `roadmap_proposal_queue.md` / `roadmap_item_execution_protocol.md` | current | Roadmap priority and protocol docs. Operate against the two canonical roadmap docs and skip `docs/roadmap/archive/**` per `reporting/proposal_queue.py:415`. | low | no_change |
| `docs/governance/recurring_maintenance.md` | current | Recurring maintenance JOB_TYPES doc. | low | no_change |
| `docs/governance/governance_status.md` | current | `reporting.governance_status` operator runbook. | low | no_change |
| `docs/governance/autonomy_metrics.md` | current | Stale-artifact detection runbook. | low | no_change |
| `docs/governance/agent_audit_inspection.md` | current | Three-source ledger inspection runbook. | low | no_change |
| `docs/governance/autonomous_workloop_runbook.md` | current | `reporting.autonomous_workloop` operator runbook (v3.15.15.16). | low | no_change |
| `docs/governance/autonomous_workloop/latest.md` | current | Generated digest snapshot (2026-05-01). Not authored by hand. | low | no_change |
| `docs/governance/autonomous_workloop/_template.md` / `schema.v1.md` | current | Templates / schema. | low | no_change |
| `docs/governance/dependabot_cleanup_playbook.md` | current | Dependabot cleanup pilot playbook. | low | no_change |
| `docs/governance/tooling_intake_policy.md` | current | Tooling intake policy. | low | no_change |
| `docs/governance/high_risk_approval_policy.md` (+ schema) | current | High-risk approval policy. | low | no_change |
| `docs/governance/approval_inbox/schema.v1.md` / `approval_exception_inbox.md` | current | Approval inbox schema + exception runbook. | low | no_change |
| `docs/governance/proposal_queue/schema.v1.md` | current | Proposal queue schema. | low | no_change |
| `docs/governance/execute_safe_controls.md` (+ schema) | current | Execute-safe controls schema and runbook. | low | no_change |
| `docs/governance/workloop_runtime.md` (+ schema) | current | Workloop runtime schema. | low | no_change |
| `docs/governance/recurring_maintenance/schema.v1.md` | current | Schema. | low | no_change |
| `docs/governance/autonomy_metrics/schema.v1.md` | current | Schema. | low | no_change |
| `docs/governance/roadmap_item_execution_protocol/schema.v1.md` | current | Schema. | low | no_change |
| `docs/governance/observability_security_hardening.md` | current | Observability security hardening runbook. | low | no_change |
| `docs/governance/vps_deploy.md` | current | VPS deploy runbook (deployment-implementation-agent surface). | low | no_change |
| `docs/governance/governance_bootstrap.md` | current | Governance bootstrap PR pattern. | low | no_change |
| `docs/governance/bootstrap_templates/*.md` | current | Bootstrap templates. | low | no_change |
| `docs/governance/frontend_agent_control_layer_roadmap.md` | minor_cleanup | Internal roadmap for the v3.15.15.17 → .23 frontend agent control layer. Sequenced before the A1–A13 ADE governance work. The maturity-ladder table (rows .17–.23) describes a future surface that was deliberately set aside for the ADE track. Not contradictory — but a reader unaware of the QRE/ADE split could mistake it for active work. | low | update_wording — add a one-line header noting this sequence was paused at v3.15.15.16 while the ADE A1–A13 track ran, and is to be re-opened only after Step 5 design planning. |
| `docs/governance/intelligent_routing_observation.md` | current | QRE-side observation doc. | low | no_change |
| `docs/governance/mobile_agent_control_pwa.md` | current | PWA spec doc. | low | no_change |
| `docs/governance/proposals/ADR-016-subagent-attribution-writer.md` | current | Draft ADR proposal. Lives under `docs/governance/proposals/` not `docs/adr/_drafts/`. | low | no_change |
| `docs/governance/agent_run_summaries/_template.md` | current | Template for committed PR summaries. | low | no_change |
| `docs/governance/agent_run_summaries/v3.15.15.12-bootstrap.md`, `*_pr_body.md` | archive_ok | Frozen historical session summaries. | low | mark_historical (already implicit; no rename needed). |
| `docs/governance/autonomous_workloop/2026-05-01T07-*.md` | archive_ok | Generated dated digests. | low | no_change |
| `docs/spillovers/agent_spillovers.md` | current | Spillover list maintained by product-owner agent. | low | no_change |
| `docs/backlog/agent_backlog.md` | current | Backlog list maintained by product-owner agent. AB-0008 already tracks `CLAUDE.md` restructuring. | low | no_change |
| `docs/adr/ADR-006` … `ADR-013` | archive_ok | Historical ADRs. Immutable per `no_touch_paths.md`. | low | no_change |
| `docs/adr/ADR-014-truth-authority-settlement.md` | current | Canonical authority mapping. Cross-referenced from `CLAUDE.md` and `AGENTS.md`. | low | no_change |
| `docs/adr/ADR-015-claude-agent-governance.md` | current | Canonical agent governance ADR. | low | no_change |
| `docs/audits/v3.15.15.6_strategy_preset_fundamental_audit.md` | current | Predecessor of ADR-014. Historical-but-load-bearing. | low | no_change |
| `docs/orchestrator_brief.md` | current | Already has the GitHub CLI lifecycle session-start protocol at line 3 and the ADR-014 §A authority note at line 47. | low | no_change |
| `docs/handoffs/v3.12-to-v3.13.md` … `v3.15.15.md` | archive_ok | Per-release handoff narratives. The most recent (`v3.15.15.md`, 2026-04-27) describes the Vol Compression Breakout 4h preset addition. | low | mark_historical (already implicit; reside under `docs/handoffs/` which is treated as historical by the proposal_queue parser via the `archive` segment rule applied to handoff prefixes — verified at runtime). |
| `docs/handoffs/v3.15-to-v3.16.md` | current | The actual v3.15→v3.16 handoff that documents the Paper Validation Engine. Still load-bearing for QRE planning. | low | no_change |
| `docs/research_intelligence_layer.md` | current | Research intelligence layer reference. | low | no_change |
| `docs/funnel_spawn_proposer_design.md` | current | Funnel spawn proposer design. | low | no_change |
| `docs/qre_frontend_redesign_report.md` | current | Frontend redesign report. | low | no_change |
| `docs/qre_observability_runbook.md` | current | QRE observability runbook. | low | no_change |
| `docs/integrations/polymarket_paper_trader_assessment.md` | current | Polymarket paper trader assessment. | low | no_change |
| `docs/RESEARCH_CONTEXT.md` | minor_cleanup | A 36-line file titled `# CLAUDE.md` (mismatched name) that lists strategy-family verdicts ("mean_reversion ❌ crypto faalt") from an early phase. Massively superseded by the strategy registry, hypothesis catalog, and ADR-014. Not authoritative anywhere. | low | candidate_archive — move to `docs/archive/RESEARCH_CONTEXT.md` or rewrite as a short pointer. Defer to operator-authored cleanup phase to avoid touching working-set docs in an audit PR. |
| `docs/roadmap/autonomous_development.txt` | current | Canonical Autonomous Development Track roadmap. Contains A1–A13 status entries with verified merge SHAs. The "Immediate next instruction to Claude" block (lines 843–879) is now historical (it points at A3, which is long-complete) but is wrapped in a code fence and clearly labeled as historical instruction context. | low | no_change |
| `docs/roadmap/Roadmap v6.md` | current | Canonical QRE Feature Build Track roadmap. "Current stable state v3.15.15.9", "Under construction v3.15.15.10 / v3.15.15.11" — the latter is mildly stale (v3.15.15.11 → v3.15.15.16 → ADE A-track has happened in between) but the document is operator-authored and edits to it are governed as `canonical_roadmap`. | low | operator_review_required — only the operator may amend Roadmap v6's "Under construction" pointer. Out of scope for an audit PR. |
| `docs/roadmap/archive/qre_roadmap_v6_1.md` | archive_ok | Internal preamble still claims to be parsed by `reporting.proposal_queue` and `reporting.roadmap_priority`. **Not** dangerous: `reporting.proposal_queue` (line 333) skips any directory segment named `archive`, and `docs/governance/execution_authority.md` (lines 41–51) explicitly maps `docs/roadmap/archive/**` to non-canonical and bans treatment as `canonical_roadmap`. The internal claim inside the file is therefore self-referential historical wording, not a live coupling. | low | no_change (file is correctly archived; its own preamble is now historical). |
| `docs/roadmap/archive/qre_prompt_guidelines_v2.md` / `qre_roadmap_v3_post_v3_15.md` / `qre_roadmap_v4.md` / `v3.15.15.12-agent-governance.md` | archive_ok | Historical roadmap material. ADR-014 still ships a one-line cross-ref into `qre_prompt_guidelines_v2.md` and `qre_roadmap_v4.md` (per ADR-014 §Decision), which the audit verified is the only remaining inbound pointer. | low | no_change |

## High-risk findings

**None.** No Markdown doc audited:

- contradicts ADR-014 / ADR-015 / Execution Authority / no-touch paths / autonomy ladder;
- implies Level 6 (autonomous merge / deploy — **permanently disabled** in this project per ADR-015 §Doctrine 1 and `docs/governance/autonomy_ladder.md`) has been enabled or is reachable;
- instructs Claude to bypass the GitHub PR lifecycle, force-push, admin-merge, weaken tests, weaken CI, or skip hooks;
- implies the operator should be asked for approval on every merge despite granted conditional merge authority (the GitHub PR lifecycle protocol explicitly auto-allows squash-merge of a green-CI PR whose touched paths were auto-allowed, modulo the post-merge gates);
- creates a hard coupling between ADE and QRE;
- treats `docs/roadmap/archive/**` as canonical (the parser explicitly excludes that path);
- references retired Claude/Codex/manual workflow as the current model in a way that would actively mislead a fresh contributor into doing the wrong thing — the misleading items (`CLAUDE.md`, `AGENTS.md`) are off-the-critical-path narrative content, not load-bearing protocol docs.

## Low-risk cleanup performed in this PR

Only this audit report itself is added. **No edits to other docs.**

The audit deliberately avoids touching:

- `CLAUDE.md` — outside any agent's `allowed_roots`; agent edits blocked by `deny_outside_agent_allowlist`. Backlog AB-0008 already tracks this.
- `AGENTS.md` — same hook constraint.
- `INSTALLATIEGIDS.md` — same hook constraint.
- `docs/roadmap/Roadmap v6.md` — `canonical_roadmap` per `execution_authority.md`; operator-authored only.
- `docs/roadmap/autonomous_development.txt` — `canonical_roadmap` per `execution_authority.md`; the canonical doc itself classifies edits to it as `NEEDS_HUMAN`.
- `docs/governance/agent_governance.md`, `autonomy_ladder.md`, `no_touch_paths.md`, `permission_model.md`, `no_test_weakening.md`, `hooks_runtime_policy.md`, `provenance.md`, `audit_chain.md`, `release_gate.md`, `release_gate_checklist.md`, `rollback_drill.md`, `sha_pin_review.md` — governance core docs; writable only by `planner`, `product-owner`, or `release-gate-agent` per `no_touch_paths.md`.
- `docs/adr/ADR-*.md` — immutable per `no_touch_paths.md`.

## Cleanup deliberately deferred (operator-authored governance-bootstrap PR)

The following cleanups are out of scope for a docs-only audit PR and
are flagged here for a future operator-authored or product-owner-led
cleanup phase:

1. **`CLAUDE.md` modernization.** Add a top-level "current canonical docs" section pointing at ADR-014, ADR-015, Execution Authority, autonomy ladder, GitHub PR lifecycle, and the QRE/ADE split. Either rewrite the obsolete 30-day "Dag 1-30" roadmap block as historical / move it to `docs/archive/CLAUDE_v1.md`, or remove it. Backlog AB-0008 already tracks this.
2. **`AGENTS.md` rewrite.** Replace §4 ("AI Tooling Roles" — Codex/Claude/Claude Code) with a pointer block to `docs/governance/agent_handoff_protocol.md` (eight canonical roles), `docs/adr/ADR-015`, `docs/governance/autonomy_ladder.md`, and `docs/governance/agent_governance.md`. Replace §5 / §11 with a pointer to `docs/governance/github_pr_lifecycle.md`. Keep §3 (Source of Truth + ADR-014 cross-ref) intact.
3. **`INSTALLATIEGIDS.md` paper-readiness pointer.** Add a single-line note in §STAP 7 pointing at the v3.15+ paper-readiness criteria (`research/paper_readiness.py` and `docs/handoffs/v3.15-to-v3.16.md` §2). The "win-rate >55%, 50 trades" wording is not load-bearing in the current QRE flow.
4. **`docs/RESEARCH_CONTEXT.md` archival.** Either move under `docs/archive/` (recommended, since the file is titled `# CLAUDE.md` but lives at `docs/RESEARCH_CONTEXT.md`) or rewrite to a 5-line pointer to ADR-014 + the strategy registry.
5. **`docs/governance/frontend_agent_control_layer_roadmap.md` header note.** Add a 1-line "paused after v3.15.15.16; resumed only after Step 5 design planning" stamp.

None of these is urgent. None changes governance posture. None is required for the next QRE feature work or for future ADE Step 5 design planning.

## Validation

- **Diff scope**: this PR adds exactly one file (`docs/governance/documentation_audit.md`).
- **Touched paths**: none under `research/`, `automation/`, `broker/`, `agent/risk/`, `agent/execution/`, `live/`, `paper/`, `shadow/`, `trading/`, `dashboard/dashboard.py`, `.claude/**`, `.github/workflows/**`, `tests/regression/**`. Verified by `git diff --stat main` after commit.
- **Governance lint**: `python scripts/governance_lint.py` — must end with `OK` (post-merge gate; rerun after squash).
- **Smoke**: `python -m pytest tests/smoke -q` — must end with `passed` (post-merge gate; rerun after squash).
- **No protected semantics changed**: the audit is read-only documentation. No policy, no schema, no test, no code, no roadmap entry is modified.

## Next recommended documentation cleanup phase

A separate, operator-authored docs cleanup phase (after the next QRE
phase opens, or before Step 5 design planning) should bundle items
1–5 above into a single PR. Suggested branch name:

```
docs/markdown-modernization-cleanup
```

That PR would be a `canonical_policy_doc`-class governance-bootstrap
PR (because it edits `CLAUDE.md` / `AGENTS.md`) and goes through the
human-authored CODEOWNERS-reviewed flow per `docs/adr/ADR-015`
§Doctrine 4 / §Doctrine 7.

## End of audit
