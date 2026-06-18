# ADE Development-Lane Doctrine

> **Status:** canonical doctrine doc, subordinate to ADR-014 / ADR-015
> and to [`docs/governance/execution_authority.md`](execution_authority.md).
>
> Pins the load-bearing distinction between **ADE development authority**
> and **QRE runtime authority** (including any future paper/shadow/live
> trading execution authority). Reads as a single source of truth for the
> doctrine that the Autonomous Development Engine is a development
> workflow automation lane only — never a trading runtime, never paper /
> shadow / live execution.
>
> This document does **not** add new authority. It does **not** unlock,
> flip, or weaken any existing gate. It pins what the rest of the
> repository already enforces, in a form that future ADE / QRE roadmap
> work can cite without ambiguity.

---

## §1 One-sentence doctrine

**ADE authority = development workflow automation only. ADE must never
place, enable, authorize, or trigger live trades. Paper/shadow are
future QRE product capabilities, not ADE execution permission.**

---

## §2 Authority distinction (load-bearing)

The repository operates under three disjoint authority surfaces. Each is
governed by its own activation flow. None inherits from the others.

| Authority | Scope | Source of activation |
|---|---|---|
| **ADE authority = development workflow automation only.** Propose roadmap items, plan, decompose, create branches, open PRs, run tests, watch CI, perform governance checks, emit reports, support operator control. | Repository code-modification workflow only. | Per-action: [`reporting.execution_authority.classify(...)`](execution_authority.md). Per-agent: `.claude/agents/*.md` frontmatter. Per-stage: `docs/governance/github_pr_lifecycle.md`. |
| **QRE runtime authority is separate** from ADE authority. Govern routing, sampling, diagnostics, hypothesis discovery, evidence policy, candidate lifecycle, paper-readiness primitives, and (in future explicitly activated phases) paper/shadow/live runtime behavior. | Quant Research Engine product capability under `research/` and adjacent product surfaces. | Current sequencing: [`docs/roadmap/qre_maturity_roadmap_to_100.md`](../roadmap/qre_maturity_roadmap_to_100.md) + operator approval where required. Historical/reference context: [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap v6.md) and [`docs/roadmap/qre_roadmap_v6_ade_operating_manual.md`](../roadmap/qre_roadmap_v6_ade_operating_manual.md) §3 mandatory domain split. |
| **Trading execution authority is permanently outside ADE authority.** Place / cancel / amend real-money orders, mutate live positions, move capital, instantiate live broker connectors, or otherwise produce real-money side effects. | Real broker, real capital, real orders. | Future Roadmap v6 phase v6.x only, under a separately governed activation that is **not** ADE. ADE never receives this authority. |

The three authorities are listed in increasing distance from ADE. ADE
holds the first only. The second is governed by QRE phase activation.
The third is permanently outside ADE and remains gated by
[`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
Doctrine 1 (autonomy ladder Level 6 permanently disabled) and by
[`docs/governance/execution_authority.md`](execution_authority.md)
(`live_broker_call`, `live_capital_move`, `live_path` modifications all
`PERMANENTLY_DENIED`).

---

## §3 What ADE may do

ADE may, under PR governance and within the per-agent allowlist + the
per-action classifier verdict:

- propose roadmap items and decompose them into bounded units;
- plan exact diff-scope proposals;
- create branches off `main` following repo branch-naming convention;
- author code, docs, tests, and reporting modules within the allowlist;
- create commits and open PRs via the `gh` CLI portable lifecycle;
- run targeted tests, broader unit / smoke suites, and governance lint;
- watch CI to completion;
- emit append-only audit events through the existing audit pipeline;
- emit operational digests, release-gate reports, and bugfix-loop
  intake artefacts under `logs/`;
- surface read-only status to the operator via the Agent Activity
  Center read-only console (per A15 design).

---

## §4 What ADE must never do

ADE is **not a trading runtime**. ADE is **not paper/shadow/live
execution**. Under no circumstance — not under "paper mode", not under
"shadow mode", not under "sandbox mode", not under a feature flag, not
under a future flag flip in this lane, and not under any reading of any
future roadmap entry — does ADE perform any of the following:

- ADE does not run strategies.
- ADE does not place orders.
- ADE does not allocate capital.
- ADE does not activate paper/shadow/live runtime.
- ADE does not receive trading authority.
- ADE does not instantiate live broker connectors.
- ADE does not call broker order APIs.
- ADE does not move funds or change broker account state.
- ADE does not write to live execution paths
  (`automation/live_gate.py`, `broker/**`, `agent/risk/**`,
  `agent/execution/**`).
- ADE does not modify live broker credentials.
- ADE does not introduce hidden live-trading flags.
- ADE does not create a route from strategy output to live broker
  execution.

**ADE must never place, enable, authorize, or trigger live trades.**

---

## §5 Paper / shadow framing

**Paper/shadow are future QRE product capabilities, not ADE execution permission.**
Roadmap v6 phases v4.x (Shadow Trading) and v5.x (Paper Trading) describe
these capabilities as future QRE product work governed by separate phase
activation and separate operator approval. They are not ADE-runtime
authority and are not unlocked by ADE doctrine modifications.

ADE may develop future QRE paper/shadow code only under PR governance,
default-disabled, operator-gated, and audited. Concretely, any future
QRE paper/shadow product code authored under ADE PR governance must
satisfy all of:

- **default-disabled** at runtime via env-gating, operator-go gating,
  and readiness-report gating, so that absent explicit operator
  activation the code cannot execute its product behavior;
- **operator-gated** for activation, never auto-enabled by ADE;
- **audited** via append-only artefact emission per ADR-015 Doctrine 5
  and the existing audit-chain doctrine;
- **separately approved** at activation time by an operator-authored
  governance-bootstrap PR; the development PR alone does not activate
  product capability;
- **never grants trading authority to ADE**: the product capability,
  once developed, belongs to QRE runtime authority, not to ADE.

ADE may not, as part of developing such code:

- modify `automation/live_gate.py`, `broker/**`, `agent/risk/**`, or
  `agent/execution/**` (permanently denied per
  [`execution_authority.md`](execution_authority.md));
- create new files under `execution/live/**`, `automation/live/**`,
  `agent/execution/live/**`, or any path matched by
  `.claude/hooks/deny_live_connector.py:LIVE_CONNECTOR_GLOBS`;
- import Ethereum-account signing, raw transaction senders, the
  Polymarket CLOB client with a private key, or CCXT `create_order`
  without a paper-mode flag (denied by `deny_live_connector.py`);
- mutate `research/research_latest.json` or
  `research/strategy_matrix.csv` (frozen contracts, permanently
  denied);
- run paper/shadow/live behavior inside any ADE artefact or audit
  pipeline.

---

## §6 Step 5 and Level 6 reaffirmation

**Step 5 runtime remains blocked** unless a separate future
governance/ADR path explicitly authorizes it. The current state is
documented in [`docs/governance/step5_design.md`](step5_design.md) §12
(readiness gate G1–G12) and in
[`docs/adr/_drafts/ADR-017-step5-autonomous-implementation-loop.md`](../adr/_drafts/ADR-017-step5-autonomous-implementation-loop.md).
`step5_implementation_allowed` is a Final constant `False`. ADE may
neither flip this constant nor enable any Step 5 substage outside the
already-documented dry-run / tests-first surfaces.

**Level 6 remains permanently disabled** per ADR-015 Doctrine 1 and
[`docs/governance/autonomy_ladder.md`](autonomy_ladder.md). No ADE
artefact, no doctrine doc (including this one), and no future ADE
roadmap entry unlocks Level 6. An amendment proposing Level 6 must be
operator-authored, must explicitly override the release-gate-agent's
auto-block recommendation, and is outside ADE authority entirely.

---

## §7 N5b simulator cap

**N5b Phase 3 recorded-fixture simulator remains the maximum allowed merge-like ADE surface.**
Phase 3 was completed under PR #240 (merge SHA `352289c`, deployed
2026-05-17). The Phase 3 simulator reads a closed-schema on-disk JSON
fixture (operator-provided on the VPS, gitignored, never committed) and
emits a deterministic status artefact.
It performs no real `gh pr merge` invocation, no network traffic, and
no merge authority over any real (production or sacrificial)
repository. The sacrificial GitHub-repository alternative was
explicitly rejected and remains permanently deferred per
[`docs/governance/n5b_phase3_implementation_plan.md`](n5b_phase3_implementation_plan.md)
§1.4.

**N5b Phase 4 production merge remains permanently denied for ADE.**
Production merge of any PR remains a human-authored act per ADR-015
Doctrine 8 (human authority settlement) and per
[`docs/governance/github_pr_lifecycle.md`](github_pr_lifecycle.md).

---

## §8 Hard repository invariants reaffirmed

The following are pinned elsewhere; they are reaffirmed here so that
any future doctrine drift in this file fails an explicit test:

- **No `--admin`** merges. `branch_protection_bypass` is `PERMANENTLY_DENIED`
  per [`execution_authority.md`](execution_authority.md).
- **No force push** to any branch. `pr_force_push` is `PERMANENTLY_DENIED`.
- **No direct main push.** `main_direct_push` is `PERMANENTLY_DENIED`.
- **No hook bypass.** No environment variable, command-line flag, or
  session toggle re-enables a denied hook. Dry-run mode is permanently
  off per ADR-015 Doctrine 12.
- **No test weakening.** `test_weaken` is `PERMANENTLY_DENIED`.
- **No frozen-contract mutation.**
  `research/research_latest.json` and `research/strategy_matrix.csv`
  are byte-frozen.
- **No `.claude/**` mutation** unless explicitly operator-approved via
  a governance-bootstrap PR.
- **No `dashboard/dashboard.py` mutation** unless explicitly
  operator-approved via a governance-bootstrap PR.
- **No live/paper/shadow/risk/broker/execution path changes** under
  ADE authority. These remain permanently denied per
  [`execution_authority.md`](execution_authority.md) and
  [`no_touch_paths.md`](no_touch_paths.md).

---

## §9 Relationship to existing canon

This doctrine is subordinate to and consistent with:

- [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md)
  — canonical mapping of which subsystem owns truth for each domain.
- [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  — authority chain for Claude / agent code-modification capability.
- [`docs/governance/execution_authority.md`](execution_authority.md)
  — per-action AUTO_ALLOWED / NEEDS_HUMAN / PERMANENTLY_DENIED
  classifier policy.
- [`docs/governance/no_touch_paths.md`](no_touch_paths.md)
  — canonical no-touch path list.
- [`docs/governance/autonomy_ladder.md`](autonomy_ladder.md)
  — six autonomy levels; Level 6 permanently disabled.
- [`docs/governance/step5_design.md`](step5_design.md)
  — Step 5 readiness gate; implementation remains blocked.
- [`docs/governance/github_pr_lifecycle.md`](github_pr_lifecycle.md)
  — branch → PR → CI → squash-merge → post-merge protocol.
- [`docs/governance/n5b_merge_execution_plan.md`](n5b_merge_execution_plan.md)
  — parent doc for N5b phases.
- [`docs/governance/n5b_phase3_implementation_plan.md`](n5b_phase3_implementation_plan.md)
  — Phase 3 recorded-fixture simulator plan.
- [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt)
  — canonical ADE roadmap; A16 anchors this doc.
- [`docs/roadmap/qre_maturity_roadmap_to_100.md`](../roadmap/qre_maturity_roadmap_to_100.md)
  — canonical current QRE implementation sequence.
- [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap v6.md)
  — historical/supporting QRE product-roadmap reference.
- [`docs/roadmap/qre_roadmap_v6_ade_operating_manual.md`](../roadmap/qre_roadmap_v6_ade_operating_manual.md)
  — QRE Roadmap v6 + Addendum ADE operating manual.

Conflicts resolve in favour of the ADRs and canonical policy docs; this
doctrine doc never overrides them.

---

## §10 Modifying this document

This file lives under `docs/governance/`. Per
[`no_touch_paths.md`](no_touch_paths.md) governance-core-docs allowlist,
writes here are permitted only by the `planner`, `product-owner`, or
`release-gate-agent` agents via their frontmatter `allowed_roots`, and
in practice are operator-authored or operator-approved. Any
modification must preserve every load-bearing literal pinned by
[`tests/unit/test_ade_development_lane_doctrine.py`](../../tests/unit/test_ade_development_lane_doctrine.py)
unless that test is updated in the same PR with operator approval.

Modifications that would weaken the doctrine (e.g., introducing any
phrasing that grants ADE trading authority, removes the no-paper /
no-shadow / no-live framing, flips `step5_implementation_allowed`,
enables Level 6, weakens N5b Phase 4 denial, or removes any of the
hard-invariant reaffirmations in §8) are forbidden by structural pin
test and by reviewer discipline.
