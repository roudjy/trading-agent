# ADR-017 — Step 5 Autonomous Implementation Loop

> **Accepted ADR.** Promoted from `docs/adr/_drafts/` via operator-authored
> governance-bootstrap PR. Sits beside ADR-014 (truth-authority settlement)
> and ADR-015 (Claude Agent Governance) as the third pillar of the project's
> authority chain. Pairs with the canonical Step 5 design document at
> [`docs/governance/step5_design.md`](../../governance/step5_design.md).
> Acceptance does **not** authorise Step 5 implementation; that requires the
> separate readiness-gate criteria (G1–G12) of `docs/governance/step5_design.md` §12.

## Status

Accepted — 2026-05-08. Promoted via operator-authored governance-bootstrap
PR. Pairs with the canonical Step 5 design document at
[`docs/governance/step5_design.md`](../../governance/step5_design.md).
Step 5 implementation remains gated by the readiness criteria in
`docs/governance/step5_design.md` §12 and by explicit operator authorisation;
acceptance of this ADR alone does **not** authorise implementation.

## Context

ADR-014 (truth-authority settlement) and ADR-015 (Claude Agent
Governance) together establish what is canonical and who is allowed
to change it. The Autonomous Development Engine (A1–A13) has been
proven end-to-end on synthetic fixtures (A13 PR #143/#144/#145, merge
SHAs `210eeca`, `f27db1c`, `73830e1`). The operational digest reports
`step5_design_planning_allowed=true` and `step5_implementation_allowed=false`.

The natural next question is: *what is the smallest implementation
loop the operator can authorise that respects the existing autonomy-
ladder ceiling?* This ADR proposes a layered sub-stage model
(Step 5.0 → Step 5.1 → Step 5.2) where the loop closes at "draft PR
opened for human review" and never at "merged" or "deployed".

## Decision (proposed; pending operator authorisation)

Adopt the **dry-run-first, layered, human-merge-only** Step 5
architecture as defined in [`docs/governance/step5_design.md`](../../governance/step5_design.md).

The matching invariants:

1. **Step 5 never autonomously merges or deploys.** The autonomy-
   ladder Level 6 ("autonomous merge / deploy") is permanently
   disabled per ADR-015 §Doctrine 1; an amendment to enable Level 6
   must be merged by humans deliberately overriding the release-gate-
   agent's auto-block recommendation. ADR-017 design respects this
   ceiling and does not propose flipping it.
2. **Step 5.0 is read-only / planner-only.** It produces only
   `logs/step5_plan/<cycle_id>.json`, `logs/step5_plan/history.jsonl`,
   `logs/step5_loop/latest.json`, and an audit-ledger event. It does
   not create branches, does not invoke git or gh, does not call
   subprocess or network.
3. **Step 5.1 introduces bounded edits on a feature branch.** The
   write surface is the §5.2 allowlist of the design doc, intentionally
   narrower than the implementation-agent's allowlist (docs, tests,
   reporting reads — biased toward the lowest-risk surfaces). It
   opens *draft* PRs only.
4. **Step 5.2 introduces merge recommendation.** It requires an
   ADR-015 amendment to unlock autonomy-ladder Level 4. Even then,
   humans merge.
5. **Step 5 modules carry the same loose-coupling AST pin as the
   ADE-core peers.** No imports from `research`, `dashboard`,
   `automation`, `broker`, `agent.risk`, `agent.execution`,
   `reporting.intelligent_routing`. No subprocess, no socket, no
   network.
6. **Step 5 reuses the existing classifiers.** It calls
   `reporting.execution_authority.classify(...)` and
   `reporting.approval_policy.evaluate(...)` and obeys the output
   verbatim. It does not add new authority decision logic.
7. **Step 5 reuses the existing release gate.** The A9 evidence input
   contract is unchanged at Step 5.0; additive evidence keys for
   Step 5.1+ are added per the existing additive-only schema regime.
8. **Step 5 implementation is gated by §12 of the design doc.**
   Twelve measurable criteria (G1–G12) must all be true on `main`
   before any Step 5.0 implementation PR opens. None of those gates
   is auto-flipped by ADE.

## Consequences

### Positive

- A real autonomous implementation loop becomes possible without ever
  exposing autonomous merge / deploy.
- Every transition that increases agent capability remains
  human-authored, CODEOWNERS-reviewed, and recorded in Git.
- The architecture extends the already-proven A8–A13 pattern
  (deterministic, AST-pinned, stdlib + ADE peers only) one layer
  higher in the stack without architectural drift.
- ADE remains extractable from the QRE repo; the §4 boundary is
  preserved.

### Negative / cost

- Step 5 introduces a third closed vocabulary set (`STEP5_SUBSTAGES`,
  `STEP5_HALT_REASONS`, `STEP5_OUTCOME_KINDS`). Each set requires a
  pin test and a docs entry, so future amendments cost a code+test+
  docs PR, not just a config tweak. This cost is intentional.
- Step 5.1 onward introduces a new attack surface (the loop creates
  branches and runs targeted tests). The §10 test matrix and the
  operator kill switch (§9) must hold to prevent escape.

### Neutral / out-of-scope

- This ADR draft does **not** authorise Step 5 implementation.
- This ADR draft does **not** amend the autonomy ladder.
- This ADR draft does **not** modify QRE behavior or Roadmap v6.
- This ADR draft does **not** propose an L5 (deploy recommendation)
  or L6 (autonomous merge / deploy) unlock — both remain held
  closed.

## Forward-looking amend triggers (mirror of ADR-015)

An amendment that proposes any of the following will auto-recommend
`block` from the release-gate-agent's checklist and must be merged by
humans deliberately overriding that recommendation:

- enabling Step 5.2 (merge recommendation) without first satisfying
  the L4 unlock per ADR-015 (≥30 days L1–3 stable);
- enabling autonomous merge or deploy (Level 6 stays
  permanently disabled in this project);
- removing any §10 test pin;
- removing the AST-level "no QRE imports" pin;
- expanding the §5 allowlist beyond `docs/`, `tests/`, `frontend/`,
  `reporting/`, and `logs/step5_*/` without an explicit operator-
  authored carve-out.

## References

- [`docs/governance/step5_design.md`](../../governance/step5_design.md) — canonical Step 5 design (this ADR's main body lives there).
- [`docs/governance/step5_design_readiness.md`](../../governance/step5_design_readiness.md) — readiness review (PR #147).
- [`docs/governance/documentation_audit.md`](../../governance/documentation_audit.md) — markdown audit (PR #146).
- [`docs/adr/ADR-015-claude-agent-governance.md`](../ADR-015-claude-agent-governance.md) — authority chain.
- [`docs/adr/ADR-014-truth-authority-settlement.md`](../ADR-014-truth-authority-settlement.md) — truth authority.
- [`docs/governance/autonomy_ladder.md`](../../governance/autonomy_ladder.md) — autonomy ladder.
- [`docs/governance/execution_authority.md`](../../governance/execution_authority.md) — execution authority classifier.
- [`docs/governance/no_touch_paths.md`](../../governance/no_touch_paths.md) — no-touch doctrine.
- [`docs/governance/github_pr_lifecycle.md`](../../governance/github_pr_lifecycle.md) — PR protocol.
- [`docs/roadmap/autonomous_development.txt`](../../roadmap/autonomous_development.txt) — Autonomous Development Track roadmap (canonical).

## Promotion checklist (when this draft is ready for acceptance)

1. Operator-authored governance-bootstrap PR moves the file from
   `docs/adr/_drafts/ADR-017-step5-autonomous-implementation-loop.md`
   to `docs/adr/ADR-017-step5-autonomous-implementation-loop.md`.
2. Set `Status:` to `Accepted` and add `Date:` line.
3. Cross-reference the accepted ADR from
   `docs/governance/step5_design.md` Appendix A.
4. Add a roadmap entry for Step 5 in
   `docs/roadmap/autonomous_development.txt` (canonical_roadmap edit).
5. Run `python scripts/governance_lint.py` and the smoke suite.
6. Squash-merge per `docs/governance/github_pr_lifecycle.md`.

Until step 1 ships, this file remains a **draft** and has no
authoritative effect.
