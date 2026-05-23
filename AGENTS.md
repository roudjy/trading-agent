# AGENTS.md

## 1. Purpose

This project builds an automated research platform to discover which strategies work across 
asset Ãƒâ€” timeframe Ãƒâ€” regime.

The system must remain:

* hypothesis-driven
* reproducible
* extensible across assets and strategy families

---

## 2. Core Principles

* Quality over speed
* No brute-force parameter searches
* Every strategy must have a clear hypothesis
* Preserve negative results (failure memory)
* Keep changes minimal and reviewable
* Maintain reproducibility of research runs

---

## 3. System Architecture Rules

The system must enforce a clear and modular structure aligned with the defined layers.

### Source of Truth

- `registry.py` is the single source of truth for strategy registration
- Strategy implementations live in `agent/backtesting/strategies.py`
- Research orchestration lives in `research/run_research.py`
- See `docs/adr/ADR-014-truth-authority-settlement.md` for the canonical authority map across registry, presets, hypothesis catalog, candidate lifecycle, campaign registry, and paper readiness Ã¢â‚¬â€ and for the formal definitions of `enabled`, `bundle_active`, `active_discovery`, and `live_eligible`.

### Output Contracts

All research runs must produce:

- `research_latest.json`
- `strategy_matrix.csv`

These outputs must:
- be deterministic
- be reproducible
- follow a stable schema

### Constraints

- Do not duplicate strategy definitions
- Do not bypass the registry
- Do not embed research logic in the runner
- Do not mix orchestration and strategy logic

---

## 4. Agent roles and authority

Agent role separation has moved from the original "Claude / Codex CLI
/ Claude Code" three-actor model to the v3.15.15.12 governance layer's
sixteen-role model, plus the eight canonical handoff roles defined in
`reporting.roadmap_execution_protocol`. The full mapping lives in:

- `docs/governance/agent_handoff_protocol.md` Ã¢â‚¬â€ eight canonical
  handoff roles (product_owner, strategic_advisor, planner,
  implementation_agent, architecture_guardian, ci_guardian,
  security/governance_guardian, human_operator).
- `docs/governance/autonomy_ladder.md` Ã¢â‚¬â€ six autonomy levels (L0Ã¢â‚¬â€œL6).
  Level 6 is permanently disabled.
- `docs/adr/ADR-015-claude-agent-governance.md` Ã¢â‚¬â€ authority chain.
- `.claude/agents/` Ã¢â‚¬â€ per-agent frontmatter with `allowed_roots`,
  `tools`, and `max_autonomy_level`.

Agent capability is bounded at every layer (policy, hooks,
CODEOWNERS, branch protection). No agent role overrides
`reporting.execution_authority.classify(...)`. Step 5 design (the
future autonomous implementation loop) is documented in
`docs/governance/step5_design.md` and remains implementation-blocked.

The original "Claude / Codex CLI / Claude Code" three-actor model is
**superseded** and should not be cited as current. Cross-reference
`docs/governance/agent_governance.md` for the public-facing overview.

---

## 5. Execution workflow

The canonical execution workflow is defined in:

- `docs/governance/roadmap_item_execution_protocol.md` Ã¢â‚¬â€ protocol
  per roadmap item.
- `docs/governance/agent_flow.md` Ã¢â‚¬â€ closed `next_action_proposed`
  vocabulary.
- `docs/governance/task_board.md` Ã¢â‚¬â€ read-only state-machine
  projection.
- `docs/governance/github_pr_lifecycle.md` Ã¢â‚¬â€ branch Ã¢â€ â€™ PR Ã¢â€ â€™ CI Ã¢â€ â€™
  squash-merge Ã¢â€ â€™ post-merge protocol.

No agent may bypass `reporting.execution_authority.classify(...)`
or skip the GitHub PR lifecycle. The previous prose ("Claude
designs Ã¢â€ â€™ Codex implements Ã¢â€ â€™ Human validates") is superseded.

---

## 6. Guardrails

* Do not mix reasoning and implementation in one step
* Do not let Codex invent strategies
* Do not let Claude perform large refactors
* Do not introduce changes without a clear hypothesis or goal
* Do not break existing output formats without explicit intent

---

## 7. Research Discipline

* Focus on one hypothesis at a time
* Do not expand strategy families prematurely
* Prefer improving signal quality over adding complexity
* Trade management changes must be justified separately from entry logic

Current direction:

* Trend-based strategies are the primary focus
* Mean reversion is deprioritized for crypto intraday

---

## 8. Engineering Direction (Current Phase)

Current phase: **Post-package QRE Feature Build Track**.

The dedicated architecture sequence is closed:

* ARCH-000 through ARCH-006 are complete.
* EXTRACT-001 through EXTRACT-002 are complete.
* PACKAGE-MIGRATION-001 through PACKAGE-MIGRATION-010 are complete.
* `PACKAGE-MIGRATION-010` selected `PACKAGE_MIGRATION_READY_FOR_QRE_FEATURE_TRACK`.

Feature work may resume, but only inside the new package-boundary discipline.

Canonical post-package layout:

* `apps/control-plane/` — control-plane / dashboard-facing read surfaces.
* `packages/ade_governance/` — ADE governance and development-control contracts.
* `packages/control_plane_qre_adapter_contract/` — read-only adapter contract between control-plane and QRE.
* `packages/qre_research/` — QRE research boundary.
* `packages/qre_data/` — QRE data boundary.
* `packages/qre_artifacts/` — QRE artifacts boundary.
* `packages/qre_diagnostics/` — QRE diagnostics boundary.
* `packages/qre_policy/` — QRE policy/read-only policy boundary.
* `packages/qre_execution_sim/` — execution-simulation boundary only.
* `packages/qre_shadow/` — future-only; inactive until the appropriate roadmap phase.
* `packages/qre_paper/` — future-only; inactive until the appropriate roadmap phase.
* `packages/qre_live/` — hard-disabled until Roadmap v6 live-governance approval.

Priorities:

* resume QRE feature work from a concrete product/research goal;
* keep changes bounded and hypothesis-driven;
* reduce legacy/report-only edges only when tied to concrete feature or cleanup scope;
* preserve deterministic research outputs and package-boundary tests;
* use the package boundaries above as the default import direction for new work.

Do not:

* restart ARCH, EXTRACT, or PACKAGE-MIGRATION without a concrete blocker;
* perform broad file moves or broad refactors;
* bypass the architecture scanner or PR lifecycle;
* activate shadow, paper, live, broker, risk, or execution behavior;
* add live-trading capability;
* change frozen contracts without explicit scope and tests;
* weaken tests or hide legacy/report-only findings with broad allowlists.

## 9. Session Start Protocol

At the start of every session:

* activate environment
* pull latest changes
* inspect latest results

```
cd ~/trading-agent
source .venv/bin/activate
git pull
cat research/research_latest.json
```

Then continue from the current system state.

---

## 10. Commit Discipline

* Commit only meaningful changes
* Keep commits small and atomic
* Use clear messages:

  * `feat:` new hypothesis or feature
  * `refactor:` structural change
  * `fix:` bug fix

## 11. Git workflow

Canonical: `docs/governance/github_pr_lifecycle.md`.

- Never commit directly to `main`.
- Branch naming: `feature/`, `feat/`, `fix/`, `chore/`, `docs/`,
  `refactor/` per the existing repo convention.
- Merge strategy: squash-merge only (`gh pr merge --squash
  --delete-branch`).
- No `--admin` merge.
- No force push.
- No hook bypass (`--no-verify`, `--no-gpg-sign`, etc.).
- Pre-commit and pre-push hooks run on every commit and push.
- CI must be green before merge; post-merge gates must pass before
  a roadmap entry is flipped to `Complete`.

The GitHub CLI portable lives at
`C:\Users\joery.van.rooij\tools\gh\bin\gh.exe`. Absence of `gh` on
PATH is **never** justification to fall back to manual PRs.

## 12. Enforcement

Any violation of:
- layer boundaries
- registry usage
- configuration rules
- orchestrator specification

must result in:
- rejection of the change
- explicit explanation of the violation
