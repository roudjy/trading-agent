# ARCH-000 - Architecture Diagnosis Gate

Status: proposed diagnosis  
Date: 2026-05-22  
Branch: `docs/arch-000-architecture-diagnosis-gate`  
Strategy input: `docs/strategy/QRE_ADE_How_To_Target_State_Roadmap.md`

## 1. Purpose

ARCH-000 decides whether the repository should:

- A. keep the current layout and add stronger boundaries;
- B. gradually extract ADE/QRE/Execution packages;
- C. use a strangler architecture with new packages next to legacy code;
- D. start a clean-slate rebuild using the current repo as reference/test oracle.

This is a diagnosis gate only. No files are moved, no runtime behavior is
changed, no product capability is activated, no Addendum 1/2/3 scope is
activated, and no authority semantics are changed.

## 2. Evidence Base

Static evidence inspected for this diagnosis:

- `docs/strategy/QRE_ADE_How_To_Target_State_Roadmap.md`
- `docs/adr/ADR-014-truth-authority-settlement.md`
- `docs/adr/ADR-015-claude-agent-governance.md`
- `docs/governance/no_touch_paths.md`
- tracked file inventory for the requested source and governance paths
- `.claude/agents/*.md`
- AST import scan over 727 tracked Python files
- existing static boundary tests:
  - `tests/functional/test_static_import_surface.py`
  - `tests/unit/test_observability_static_import_surface.py`
  - `tests/unit/test_intelligent_routing_import_safety.py`

Repository shape from tracked files:

| Path | Tracked files | Python files | Notes |
|---|---:|---:|---|
| `dashboard/` | 30 | 23 | Flask/API control-plane surface plus research/status adapters. |
| `reporting/` | 83 | 83 | ADE governance/reporting plus some QRE advisory helpers. |
| `research/` | 112 | 110 | QRE core, diagnostics, policies, candidate lifecycle, paper readiness surfaces. |
| `agent/` | 37 | 37 | Legacy agents, backtesting, brain, execution, risk, learning. |
| `broker/` | 0 | 0 | No tracked top-level package. |
| `paper/` | 0 | 0 | No tracked top-level package; paper concepts exist under `research/` and `execution/paper/`. |
| `shadow/` | 0 | 0 | No tracked top-level package. |
| `live/` | 0 | 0 | No tracked top-level package; live gate exists under `automation/`. |
| `docs/governance/` | 139 | 0 | ADE doctrine, execution protocol, agent governance, release gates. |
| `docs/roadmap/` | 12 | 0 | Roadmap v6 and addenda. |
| `tests/` | 428 | 421 | Dense regression/unit/functional/integration coverage. |
| `artifacts/` | 2 | 0 | Schema and placeholder only in tracked state. |
| `.claude/agents/` | 16 | 0 | Agent role and allowlist definitions. |
| `automation/` | 2 | 2 | Includes `automation/live_gate.py`. |
| `execution/` | 4 | 4 | Protocols and paper simulator. |
| `frontend/` | 93 | 0 | SPA control-plane frontend. |
| `orchestration/` | 7 | 7 | Execution/orchestration framework separate from `research/run_research.py`. |

## 3. Current-State Domain Inventory

| Path | Current domain | Suspected mixed responsibilities | Runtime criticality | Test coverage confidence | Target domain candidate | Migration risk | Unknowns |
|---|---|---|---|---|---|---|---|
| `dashboard/` | Control-plane/API. | Imports both ADE reporting and QRE research modules; some endpoints expose campaign/research intelligence directly. | Medium-high because operator visibility and controls flow through it. | Medium: many unit tests exist for dashboard APIs, but architecture ownership is not fully pinned. | `/apps/control-plane` plus thin adapters to ADE/QRE APIs. | Medium-high if endpoints are moved before contracts are pinned. | Which routes are pure read-only observability versus control actions should be enumerated. |
| `reporting/` | ADE governance/reporting, release, queue, authority, observability. | Contains QRE advisory helpers such as intelligent routing and hypothesis discovery summaries. | High for governance and development conveyor decisions. | Medium-high: broad unit coverage, specific import-safety tests for some modules. | `/packages/ade_governance` with QRE advisory adapters extracted or renamed. | Medium because authority semantics and release gate behavior are governance-critical. | Transitive imports from ADE to QRE are not fully machine-inventoried yet. |
| `research/` | QRE research product. | Includes candidate lifecycle, campaign policy, diagnostics, paper readiness, paper ledgers, and execution bridge definitions. | Very high for reproducibility and frozen research outputs. | High around artifacts/schema/pins; medium for newer intelligence slices. | `/packages/qre_research`, `/packages/qre_data`, `/packages/qre_artifacts`, `/packages/qre_diagnostics`, `/packages/qre_policy`, `/packages/qre_execution_sim`. | High due to ADR-014 authority surfaces and frozen contracts. | Exact module-to-package cutlines need import and artifact authority maps before movement. |
| `agent/` | Legacy trading/research runtime. | Backtesting, strategy agents, brain/orchestrator, execution, risk, learning, monitoring all sit under one root. | High where backtesting/execution/risk are imported; high migration blast radius. | Medium: many unit/regression tests, but ownership is mixed. | Split between QRE research/backtesting and future Execution packages. | High because execution/risk imports appear in legacy agent modules. | Whether `agent/brain` is still active runtime or legacy reference needs proof. |
| `broker/` | Absent as tracked top-level path. | None at top level. | Unknown. | None. | Future `/packages/qre_live` or broker adapter package only after live phase. | Low now; very high if introduced prematurely. | Existing broker concepts may be embedded by naming in tests/docs rather than path. |
| `paper/` | Absent as tracked top-level path. | Paper behavior exists under `research/` and `execution/paper/`. | Medium-high for paper readiness and simulated orders. | Medium-high for current tests. | `/packages/qre_paper` later, after package boundaries and readiness doctrine are explicit. | High if split before paper/live authority is settled. | Need decide whether `research/paper_*` remains QRE policy or moves to execution simulation. |
| `shadow/` | Absent as tracked top-level path. | Shadow concepts are mostly future roadmap/governance. | Low in current runtime. | Low. | `/packages/qre_shadow` only after v4 readiness. | Medium future risk. | No current package inventory exists. |
| `live/` | Absent as tracked top-level path. | Live gate exists under `automation/live_gate.py`; live eligibility is hard-pinned false by ADR-014. | Very high if touched. | High for no-live invariants, but no live product surface is active. | `/packages/qre_live` only in controlled live phase. | Very high and not justified now. | None needed for ARCH-000; live remains out of scope. |
| `docs/governance/` | ADE governance doctrine and protocols. | Also contains QRE research quality docs and observability minimal docs. | High for authority and agent behavior. | Medium: governance docs have unit tests, but docs are broad. | `/packages/ade_governance` docs authority, with QRE docs cross-referenced. | Medium-high because governance docs are protected/no-touch in places. | Which docs are canonical ADE versus QRE reference needs tagging. |
| `docs/roadmap/` | Roadmap/product strategy. | QRE roadmap, ADE operating manual, addenda in same path. | Medium. | Low-medium: mostly documentation. | Strategy/reference docs, not runtime packages. | Low for documentation only; high if used to activate addenda. | Addendum reference-only status must remain explicit. |
| `tests/` | Cross-domain validation. | Tests currently encode research, governance, dashboard, execution, regression, and smoke concerns in one tree. | Very high for safe migration. | High overall. | Keep as repo-level tests initially; add architecture tests before package moves. | Medium: path moves can break test discovery and imports. | Need ownership labels for architecture/gov/QRE/execution test slices. |
| `artifacts/` | Build/runtime artifact schemas and placeholders. | Sparse tracked state; runtime artifacts mostly generated elsewhere or under research. | Medium-high when schema-backed. | Medium for schema file; generated artifacts are not all tracked. | `/packages/qre_artifacts` schema definitions later. | Medium if artifact path contracts are changed. | Need full artifact producer/consumer map. |
| `.claude/agents/` | ADE agent governance definitions. | Agent scopes mention frontend, deployment, tests, docs, and read-only QRE architecture review. | High for governance and future migrations. | Medium-high: governed by hooks/tests; now also pinned by ARCH-000 smoke test. | ADE governance authority surface. | High because definitions are self-protected and require governance-bootstrap/operator approval. | Need richer machine-readable domain labels per agent before migration waves. |

## 4. Import and Dependency Risk Inventory

An AST scan over tracked Python files produced 38 conservative findings.
The scan was static and direct-import only; it did not resolve transitive
imports, dynamic imports, runtime plugin loading, or file IO.

### 4.1 ADE/reporting importing QRE runtime or execution paths

Direct reporting-to-QRE imports found:

| Module | Imported domain modules | Risk |
|---|---|---|
| `reporting/hypothesis_discovery_summary.py` | `research.hypothesis_discovery` | ADE reporting has direct QRE product knowledge. Acceptable as a temporary reporting adapter, but not a clean package boundary. |
| `reporting/intelligent_routing.py` | `research.presets` | Reporting owns an advisory surface that reads QRE preset authority. Existing import-safety tests reduce runtime risk, but physical extraction would need an adapter. |

No direct `reporting/development*.py` imports of broker/live/paper/shadow
modules were found. This is now pinned by
`tests/architecture/test_domain_boundary_smoke.py`.

### 4.2 QRE modules importing dashboard/control-plane or execution paths

No direct `research/` imports of `dashboard` were found in the static scan.
No direct `research/diagnostics/` imports of broker/live/paper/shadow/risk/order
paths were found. This is now pinned by
`tests/architecture/test_domain_boundary_smoke.py`.

QRE does contain execution-adjacent modules by concept and naming:

- `research/execution_bridge/agent_definition.py`
- `research/paper_divergence.py`
- `research/paper_ledger.py`
- `research/paper_readiness.py`
- `research/paper_validation_sidecars.py`
- `research/paper_venues.py`

These are not necessarily violations. They indicate that package extraction
must distinguish QRE policy/readiness artifacts from actual execution,
paper-order simulation, shadow logging, and live trading.

### 4.3 Diagnostics importing broker/live/paper/shadow/risk/order paths

No direct violations were found under `research/diagnostics/`. Existing test
coverage already prevents diagnostics from importing decision/runtime modules
more broadly in `tests/unit/test_observability_static_import_surface.py`.
ARCH-000 adds a narrower smoke test focused on execution-domain imports.

### 4.4 Dashboard/control-plane owning research logic

Dashboard imports domain modules directly:

| Module | Imported domain modules | Risk |
|---|---|---|
| `dashboard/api_agent_control.py` and related agent-control APIs | multiple `reporting.*` modules | Control-plane routes are coupled to ADE internals. |
| `dashboard/api_campaigns.py` | `research.campaign_*` modules | Control-plane directly knows campaign policy/queue/registry modules. |
| `dashboard/api_observability.py` | `research.diagnostics.paths` | Likely acceptable read-only adapter, but still direct QRE package coupling. |
| `dashboard/api_research_intelligence.py` | `research.dead_zone_detection`, `research.funnel_spawn_proposer`, `research.information_gain`, `research.research_evidence_ledger`, `research.stop_condition_engine`, `research.viability_metrics` | Control-plane endpoint owns knowledge of multiple QRE intelligence slices. |
| `dashboard/dashboard.py` | `reporting`, `research.presets` | Protected dashboard file remains a mixed read surface. |
| `dashboard/research_runner.py` | `research.run_state` | Dashboard has direct run-state coupling. |

Diagnosis: dashboard is currently a control-plane facade with direct domain
imports. That is workable in the current repo but argues against a clean
package move before API contracts are introduced.

### 4.5 Execution-related modules imported outside explicit execution contexts

Direct execution/risk imports outside `agent/execution/` and `agent/risk/`
were found in legacy `agent/` modules and tests:

- `agent/agents/*` import `agent.risk.risk_manager`
- `agent/brain/agent.py` imports `agent.execution.order_executor` and `agent.risk.risk_manager`
- `agent/brain/orchestrator.py` imports `agent.execution.order_executor` and `agent.risk.risk_manager`
- `agent/brain/signal_aggregator.py` imports `agent.risk.risk_manager`
- several tests import `agent.execution.order_executor` and/or `agent.risk.risk_manager`

Diagnosis: legacy `agent/` is not a clean execution package and not a clean
research package. It is a high-risk extraction area and should be migrated only
after import boundaries and active-runtime status are established.

### 4.6 ARCH-001 scanner requirement

ARCH-000 adds a minimal executable smoke test. ARCH-001 should build a fuller
scanner with these exact requirements:

- parse all tracked Python files only;
- build direct import edges using `ast`;
- normalize relative imports to absolute module names;
- emit a deterministic JSON or Markdown report;
- classify source and target module domains: ADE, QRE, control-plane,
  execution, test, governance tooling, unknown;
- support allowlist entries with justification and sunset criteria;
- fail CI only for closed, agreed forbidden edges;
- report, but do not fail, legacy edges until migration units address them;
- optionally add transitive closure checks for selected entry points:
  dashboard APIs, reporting development modules, research diagnostics, and
  `research/run_research.py`.

## 5. Claude Agent Domain Inventory

Agent definitions were inspected under `.claude/agents/`. They were not
modified.

| Agent | Classification | Mandate | Roots | Max autonomy | Current effective domain | Target domain | Correctly scoped? | Scope risk | Migration participation | Approval expectation |
|---|---|---|---|---:|---|---|---|---|---|---|
| `adversarial-reviewer` | Cross-domain guardian | Read-only red-team review for governance, security, determinism. | allowed `[]`; excludes none; ask none. | 0 | Cross-domain review. | Cross-domain guardian. | Yes. | Low; read-only. | May review migration PRs. | Changes require operator/governance-bootstrap because `.claude/agents/**` is self-protected. |
| `architecture-guardian` | Cross-domain guardian | Enforce ADR-009/014/015 invariants. | allowed `[]`; excludes none; ask none. | 0 | Architecture authority gate. | Cross-domain guardian. | Yes. | Low operational risk; high blocking authority. | Must gate all architecture migration PRs. | Agent changes require operator/governance-bootstrap. |
| `ci-guardian` | Release/CI/evidence gate | Review CI changes; only agent allowed to propose workflow edits in CI hardening tasks. | allowed `.github/workflows/`, `pyproject.toml`, `docs/governance/sha_pin_reviews/`; excludes none; ask none. | 2 | CI/governance. | Release/CI/evidence gate. | Mostly yes. | Workflow access is sensitive and should remain task-specific. | May participate in CI-related migration units only. | Changes require operator/governance-bootstrap. |
| `deployment-implementation-agent` | Execution/deployment | Dashboard-only VPS deploy surface. | allowed `scripts/deploy_vps_dashboard.sh`, `.github/workflows/deploy-vps-dashboard.yml`, `docs/governance/vps_deploy.md`; excludes none; ask none. | 1 | Dashboard deployment only. | Execution/deployment, but not trading execution. | Yes. | Low if kept dashboard-only; high if broadened. | May participate only in deploy-surface units, not package extraction. | Changes require operator/governance-bootstrap. |
| `deployment-safety-agent` | Execution/deployment | Read-only production posture review. | allowed `[]`; excludes none; ask none. | 0 | Deployment safety. | Execution/deployment guardian. | Yes. | Low; read-only. | May review deploy-impacting migrations. | Changes require operator/governance-bootstrap. |
| `determinism-guardian` | Release/CI/evidence gate | Run pin tests and report drift; no auto-fixes. | allowed `[]`; excludes none; ask none. | 0 | Determinism evidence. | Release/CI/evidence gate. | Yes. | Low; read-only. | Must review artifact/schema-sensitive moves. | Changes require operator/governance-bootstrap. |
| `evidence-verifier` | Release/CI/evidence gate | Verify ledger schemas and append-only audit-chain integrity. | allowed `[]`; excludes none; ask none. | 0 | Evidence integrity. | Release/CI/evidence gate. | Yes. | Low; read-only. | Should review artifact/evidence package moves. | Changes require operator/governance-bootstrap. |
| `frontend-agent` | Control-plane/frontend | Frontend-only React/Vite/Vitest implementation. | allowed `frontend/`; excludes `frontend/node_modules/`, `frontend/dist/`; ask none. | 1 | SPA frontend only. | Control-plane/frontend. | Yes. | Low if backend writes remain forbidden. | May participate in control-plane UI units only. | Changes require operator/governance-bootstrap. |
| `implementation-agent` | QRE research/product plus control-plane/docs/tests | Implement planner-approved task within allowlist. | allowed `dashboard/`, `tests/`, `frontend/`, `docs/`, `docs/adr/_drafts/`; excludes `dashboard/api_observability.py`, regression pins, `docs/governance/`, existing ADRs; ask none. | 3 | Broad implementation across control-plane/docs/tests and non-core backend surfaces. | Needs narrower per-migration unit role. | Partly. Too broad for package extraction because `docs/`, `dashboard/`, `frontend/`, and `tests/` span multiple target domains. | Medium-high: can unintentionally couple migration docs/tests/control-plane changes in one unit. | May participate only with explicit per-unit allowlist and architecture-guardian sign-off. | Changes require operator/governance-bootstrap. |
| `observability-guardian` | Cross-domain guardian | Logging, audit events, healthchecks with limited write scope. | allowed `reporting/`, `dashboard/api_observability.py`, selected observability tests/docs; excludes none; ask none. | 2 | ADE observability and one dashboard endpoint. | Cross-domain observability guardian. | Mostly yes. | Medium: spans reporting and dashboard, but narrow. | May participate in observability boundary units. | Changes require operator/governance-bootstrap. |
| `planner` | ADE governance | Decompose roadmap item into tasks with no-touch flags and tests. | allowed `docs/governance/plan_*.md`, `docs/governance/agent_run_summaries/`; excludes none; ask none. | 1 | Planning only. | ADE governance. | Yes. | Low if it does not implement. | Can safely decompose architecture transformation units. | Changes require operator/governance-bootstrap. |
| `product-owner` | ADE governance | Curate backlog/spillover lists. | allowed `docs/backlog/`, `docs/spillovers/`, `docs/governance/agent_run_summaries/`; excludes none; ask none. | 1 | Backlog governance. | ADE governance. | Yes. | Low. | May sequence migration backlog only. | Changes require operator/governance-bootstrap. |
| `quant-research-architect` | QRE research/product | Read-only research authority and ledger correctness review. | allowed `[]`; excludes none; ask none. | 0 | QRE architecture guardian. | QRE research/product guardian. | Yes. | Low operational risk; high blocking role for QRE moves. | Must gate all QRE package moves. | Changes require operator/governance-bootstrap. |
| `release-gate-agent` | Release/CI/evidence gate | Evidence-backed go/no-go reports; never execute transition. | allowed `docs/governance/release_gates/`, `docs/governance/release_digests.md`; excludes none; ask none. | 0 | Release recommendation. | Release/CI/evidence gate. | Yes. | Low if recommendation-only remains true. | Must report on migration PR release gates. | Changes require operator/governance-bootstrap. |
| `strategic-advisor` | Cross-domain guardian | Long-horizon tradeoffs and architectural risks. | allowed `[]`; excludes none; ask none. | 0 | Strategy review. | Cross-domain guardian. | Yes. | Low; read-only. | May review migration strategy. | Changes require operator/governance-bootstrap. |
| `test-agent` | Release/CI/evidence gate | Test authoring in non-regression test roots; regression ask-only; pin/digest/authority tests denied. | allowed `tests/smoke/`, `tests/unit/`, `tests/integration/`, `tests/resilience/`, `tests/functional/`; excludes none; ask `tests/regression/`. | 1 | Test implementation. | Release/CI/evidence gate. | Mostly yes. | Medium: architecture tests in `tests/architecture/` are not currently in its allowlist. | May add tests only in allowed roots unless agent scope is amended. | Changes require operator/governance-bootstrap. |

Explicit agent assessments:

- `implementation-agent` is too broad for package extraction work unless each
  migration unit narrows its write set outside the static role definition.
- `planner` can safely decompose architecture transformation units because it
  writes plans only and must include no-touch analysis and stop conditions.
- `architecture-guardian` must gate all architecture migration PRs.
- `quant-research-architect` must gate all QRE package moves.
- Deployment agents are currently isolated from live/paper/shadow/risk/broker
  behavior by narrow scopes and explicit forbidden actions.
- `frontend-agent` remains control-plane only and should not receive backend
  authority for package extraction.
- `release-gate-agent` remains recommendation-only and does not execute merge
  or deploy.

## 6. Decision Matrix

| Option | Benefit | Risk | Migration complexity | CI/deploy risk | QRE continuity risk | ADE continuity risk | Data-throughput impact | Reversibility | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| A. Boundary hardening only | Fastest; preserves current imports and runtime; low immediate churn. | Leaves domain coupling in place; dashboard/reporting/research remain physically entangled. | Low. | Low. | Low short-term, medium long-term. | Low short-term, medium long-term. | Neutral. | High. | Not recommended as final state; useful first step. |
| B. Phased package extraction | Aligns physical boundaries with ADE/QRE/Execution target while preserving tests and frozen contracts. | Requires disciplined sequencing and adapters; high risk if authority surfaces are moved too early. | Medium-high. | Medium if each move is small and gated. | Medium, manageable with artifact pins and import tests. | Medium, manageable with governance gates. | Positive long-term; neutral short-term. | Medium-high if each unit is two-way-door and adapters remain. | Recommended. |
| C. Strangler sidecar packages | Avoids moving legacy code initially; new packages can be clean from day one. | Creates duplicate authority and two implementations unless strict adapters are enforced; risks bypassing registry/ADR-014. | Medium. | Medium. | Medium-high due to duplicated QRE surfaces. | Medium. | Potentially positive but only after data contracts exist. | Medium. | Not recommended now; use selectively only for new non-authoritative sidecars. |
| D. Clean-slate rebuild | Cleanest conceptual architecture. | Highest loss of replay confidence, governance history, frozen contract behavior, and failure memory. | Very high. | Very high. | Very high. | Very high. | Negative for a long period. | Low. | Not recommended. |

## 7. Recommendation

Recommendation: `PHASED_PACKAGE_EXTRACTION`.

Evidence:

- The repository already has strong governance and research invariants, so a
  clean-slate rebuild would discard the most valuable safety asset: tests,
  frozen contracts, ADR-014 authority settlement, and agent governance.
- Boundary hardening only is insufficient because direct imports already cross
  the conceptual target domains, especially dashboard-to-QRE and
  reporting-to-QRE.
- A strangler approach is risky as the default because QRE has canonical
  authority surfaces where duplicate sidecar implementations would create truth
  pluralism, the exact issue ADR-014 settled.
- Phased extraction can start with executable architecture scans, adapters, and
  ownership labels before any file move. It matches the strategy document's
  preference for stabilizing the minimal loop, preserving reproducibility, and
  adding explainability before autonomy or execution growth.

This recommendation does not mean immediate physical moves. It means the next
architecture units should prepare, measure, and then extract only when objective
criteria are met.

## 8. Stop/Go Criteria

Physical package extraction is justified when all are true:

- direct and transitive import edges for the candidate package are known;
- the package has a single target domain owner;
- frozen artifact schemas and public outputs remain byte-stable;
- package consumers can use a stable adapter/API during the move;
- architecture-guardian and, for QRE moves, quant-research-architect approve;
- targeted tests and existing regression pins pass;
- rollback is a path-only revert or adapter revert, not a behavior rewrite.

Physical package extraction is not justified when any are true:

- the module owns or mutates ADR-014 authority surfaces without a migration ADR;
- imports are unknown or dynamic enough that behavior cannot be bounded;
- the move would mix research logic with dashboard/control-plane behavior;
- the move would touch live/paper/shadow/risk/broker behavior outside an
  explicit execution phase;
- tests require weakening, fixture churn, or frozen contract changes;
- the package boundary is based on naming rather than measured dependency
  evidence.

Clean-slate rebuild should be reconsidered only if at least two of these occur:

- package extraction cannot proceed after multiple small, well-tested attempts;
- current architecture prevents preserving frozen outputs or replay invariants;
- CI time or dependency coupling becomes unmanageable even after boundary
  hardening;
- a measured data-throughput bottleneck cannot be resolved with Python,
  DuckDB/Polars, or package extraction;
- governance and QRE authority cannot be reconciled without repeated ADR
  exceptions.

Current feature work may resume when:

- ARCH-000 is merged;
- the architecture smoke test passes;
- ARCH-001 scanner scope is accepted or explicitly deferred;
- no active PR has changed execution authority, frozen contracts, live/paper/
  shadow/risk/broker behavior, or dashboard mutation authority;
- the next feature unit states its ADE/QRE/Control-plane/Execution domain and
  forbidden paths.

## 9. First Three Implementation Units After ARCH-000

### Unit 1 - ARCH-001 Domain Import Scanner

Purpose: replace ad hoc import inspection with a deterministic repo-local
architecture scanner.

Scope:

- add a scanner under tests or reporting tooling;
- parse tracked Python files;
- classify direct imports by source/target domain;
- emit a deterministic report;
- add closed forbidden-edge tests for agreed boundaries.

Out of scope:

- moving files;
- changing imports;
- changing runtime behavior;
- changing authority semantics.

Expected files:

- `tests/architecture/test_domain_import_scanner.py`
- optionally `reporting/architecture_import_scan.py`
- `docs/architecture/ARCH-001-domain-import-scanner.md`

Forbidden files:

- `research/**` authority/runtime files;
- `agent/execution/**`, `agent/risk/**`, `automation/**`, `execution/**`;
- frozen artifacts and regression pin tests;
- `.claude/agents/**`.

Risk class: low-medium.

Authority expectation: planner scopes it; architecture-guardian reviews; no
governance-bootstrap required unless `.claude/**` or protected docs change.

Tests required:

- new architecture scanner tests;
- existing static import tests;
- targeted governance tests if reporting tooling is added.

Acceptance criteria:

- scanner output is deterministic;
- known legacy edges are reported, not hidden;
- CI has at least one failing-on-new-forbidden-edge test;
- no runtime imports are executed during scanning.

Rollback plan: remove the scanner/test/report files; no runtime rollback
needed.

### Unit 2 - ARCH-002 Domain Ownership and Adapter Contract Map

Purpose: define package cutlines and adapter contracts before moving files.

Scope:

- map each `research/`, `reporting/`, `dashboard/`, `agent/`, `execution/`,
  and `automation/` module to ADE, QRE, Control-plane, Execution, Test, or
  Unknown;
- define allowed dependency direction;
- identify first candidate extraction package with lowest risk;
- document adapter contracts for dashboard-to-domain calls.

Out of scope:

- file moves;
- changing imports;
- dashboard mutation routes;
- changes to research outputs or authority semantics.

Expected files:

- `docs/architecture/ARCH-002-domain-ownership-map.md`
- optionally a static data file under `tests/architecture/fixtures/`.

Forbidden files:

- execution/live/paper/shadow/risk/broker paths;
- `.claude/agents/**`;
- frozen contracts;
- active queue seeds unless a separate approved governance task requires it.

Risk class: low.

Authority expectation: architecture-guardian gates; quant-research-architect
gates QRE domain classifications.

Tests required:

- architecture scanner should validate that every known source root has a
  domain label;
- docs/governance tests if docs link to governance protocols.

Acceptance criteria:

- every major path has a domain owner;
- unknowns are explicit;
- first extraction candidate is justified by import evidence and test coverage;
- no runtime behavior changes.

Rollback plan: revert the documentation/fixture additions.

### Unit 3 - ARCH-003 First Read-Only Adapter Boundary

Purpose: reduce dashboard direct coupling by introducing one read-only adapter
boundary without moving domain files.

Scope:

- choose one dashboard endpoint with low mutation risk;
- route it through a thin adapter module;
- keep response schema byte-compatible;
- add tests proving behavior equivalence.

Out of scope:

- file moves into `/packages`;
- dashboard mutation routes;
- research policy changes;
- paper/shadow/live/risk/broker behavior.

Expected files:

- one `dashboard/api_*.py` endpoint or adjacent adapter;
- matching unit tests;
- architecture documentation update.

Forbidden files:

- `research/**` authority surfaces unless explicitly approved;
- `agent/execution/**`, `agent/risk/**`, `automation/**`, `execution/**`;
- frozen artifacts and regression pin tests;
- `.claude/agents/**`.

Risk class: medium.

Authority expectation: planner scopes; architecture-guardian gates; if the
endpoint touches QRE intelligence, quant-research-architect also gates.

Tests required:

- existing endpoint unit tests;
- new behavior-equivalence test;
- architecture scanner/smoke tests.

Acceptance criteria:

- dashboard response remains unchanged;
- direct domain import count decreases or is documented as unchanged with a
  reason;
- adapter has read-only authority;
- no runtime capability is activated.

Rollback plan: revert the adapter and endpoint wiring; no data migration.

## 10. ARCH-000 Validation Added

ARCH-000 adds `tests/architecture/test_domain_boundary_smoke.py`.

The test is deliberately conservative:

- `reporting/development*.py` must not import execution-domain modules;
- `research/diagnostics/*.py` must not import execution-domain modules;
- implementation agent scopes are pinned away from execution roots;
- deployment implementation scope remains dashboard-deploy only.

This is not the full architecture scanner. It is the first executable boundary
pin.
