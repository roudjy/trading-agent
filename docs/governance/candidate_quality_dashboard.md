# Candidate-Quality Dashboard — specification

> **Status:** specification (Research-Quality Hardening Sprint;
> sprint plan §3-item-S7 and §6.2 of
> [`roadmap_scope_status.md`](roadmap_scope_status.md)).
>
> **Authority:** governance spec. Declares a read-only dashboard
> surface that aggregates the sprint's KPI / multiplicity-ledger /
> reason-records / paper-readiness output for one-glance operator
> review. Does not implement runtime code; the implementation
> lands in a later scoped PR. Does not modify
> `dashboard/dashboard.py`; the dashboard wiring is a separate
> operator-driven governance-bootstrap PR (mirrors the existing
> `register_*_routes` pattern in
> [`roadmap_priority.md`](roadmap_priority.md) §"Wiring shape").
>
> **Cross-refs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md),
> [`research_quality_kpis.md`](research_quality_kpis.md),
> [`multiplicity_ledger.md`](multiplicity_ledger.md),
> [`paper_readiness_checklist.md`](paper_readiness_checklist.md),
> [`reason_records.md`](reason_records.md),
> [`cost_adjusted_promotion.md`](cost_adjusted_promotion.md),
> [`docs/adr/_drafts/ADR-020-paper-shadow-live-separation.md`](../adr/_drafts/ADR-020-paper-shadow-live-separation.md).

## 1. Purpose

The sprint produces several artifacts that each illuminate a
different angle of research quality:

- KPI snapshot ([`research_quality_kpis.md`](research_quality_kpis.md)
  §3) — seven numbers per release.
- Multiplicity ledger ([`multiplicity_ledger.md`](multiplicity_ledger.md))
  — `N_eff(c)` per candidate.
- Per-candidate paper-readiness checklist
  ([`paper_readiness_checklist.md`](paper_readiness_checklist.md))
  — 10 yes/no checks per candidate.
- Routing / sampling / scoring reason records
  ([`reason_records.md`](reason_records.md)) — why each decision
  was made.

An operator must currently visit four locations. The dashboard
gives them one location.

## 2. Scope

The dashboard surfaces:

- **Release KPI block** — the seven KPIs from
  [`research_quality_kpis.md`](research_quality_kpis.md) §3.
- **Candidate quality table** — one row per active candidate with
  `paper_readiness_checklist.overall`, `multiplicity_n_eff`,
  `dsr_value`, and pointers to the per-candidate checklist.
- **Reason-records summary** — top-N most frequent reason codes
  across the three families (routing / sampling / scoring),
  filterable by subject_id.
- **Dead-zone and attention block** — current operator-attention
  budget consumption and dead-zone compute share.

The dashboard is **read-only**:

- It does not promote, demote, or rank candidates.
- It does not write to any artifact.
- It does not feed any live / paper / shadow / broker /
  execution surface (ADR-020 §2.5).
- It does not modify `dashboard/dashboard.py`. The wiring
  follows the existing `register_*_routes` pattern.

## 3. Authority

The dashboard is **derived presentation**, not authority.

- All inputs are read from existing canonical / derived
  artifacts.
- All numeric values are deterministic functions of inputs.
- The dashboard does not introduce a new truth surface; it joins
  existing ones.

Per ADR-014, the dashboard does not create a new authority
domain. Its derived view fields are pinned by the implementation
PR's tests so the dashboard can never diverge silently from the
canonical artifacts.

## 4. Surface composition

The dashboard panel is built from these read-only API endpoints
(planned). Each endpoint maps 1:1 to an existing artifact.

| Endpoint | Source artifact | Shape (planned) |
|---|---|---|
| `/api/agent-control/research-quality-kpi` | `logs/research_quality_kpis/<version>.md` (and `latest`) | seven KPI values + units + direction |
| `/api/agent-control/candidate-quality-table` | `logs/paper_readiness_checklist/manifest.v1.json` + per-candidate checklists | rows: `{candidate_id, overall, n_eff, dsr, last_updated}` |
| `/api/agent-control/reason-records-summary` | `logs/reason_records/manifest.v1.json` | top-N counts per family + per decision |
| `/api/agent-control/operator-attention` | `logs/development_work_queue/latest.json` + `logs/autonomous_workloop/latest.json` | OAB KPI + open decision count |
| `/api/agent-control/dead-zone-share` | `logs/campaign_*` (existing) | DZCR KPI + trend over last N releases |

The endpoints follow the existing read-only `/api/agent-control/*`
pattern (mirrors [`roadmap_priority.md`](roadmap_priority.md)
§"PWA card"). Every endpoint:

- Returns JSON only.
- Has no side effects.
- Returns 404 with a structured envelope when the source artifact
  is missing.
- Carries `safe_to_execute: false` defensively at the boundary,
  even though the read can't execute anything.

## 5. Page layout (operator-facing)

The dashboard panel is a single PWA tab named **"Research
quality"**. From top to bottom:

```text
┌─ Release KPI snapshot ────────────────────────────────────┐
│ Time-to-first-paper-ready-candidate:  <days> (target: ↓) │
│ OOS Deflated Sharpe of survivors:     <median> [IQR]     │
│ Multiplicity-adjusted survivor quality: <median>          │
│ Null-model-beating rate:              <pct>               │
│ Dead-zone compute reduction:          <pct vs baseline>   │
│ Operator attention burden:            <ratio>             │
│ Candidate robustness survival rate:   <pct>               │
└────────────────────────────────────────────────────────────┘

┌─ Candidate quality table ─────────────────────────────────┐
│ candidate_id   overall  n_eff  dsr      updated_at         │
│ ────────────   ───────  ─────  ───      ──────────         │
│ <id>           yes/no   <int>  <float>  <iso>              │
│ ...                                                        │
└────────────────────────────────────────────────────────────┘

┌─ Reason-records summary (top 16 codes) ───────────────────┐
│ routing.dead_zone_dwell_exceeded: <count>                 │
│ scoring.cost_gate_fail:           <count>                 │
│ scoring.null_p_value_above_thresh:<count>                 │
│ ...                                                        │
└────────────────────────────────────────────────────────────┘

┌─ Operator attention budget ───────────────────────────────┐
│ Visible surfaces per campaign cap: <int>                  │
│ Current load:                     <int>                   │
│ Decisions per week (4-wk avg):    <float>                 │
└────────────────────────────────────────────────────────────┘

┌─ Dead-zone share trend ───────────────────────────────────┐
│ Latest release:    <pct>                                  │
│ Baseline (pre-reset): <pct>                              │
│ Trend:             ↓ <pct points over <N> releases>      │
└────────────────────────────────────────────────────────────┘
```

The panel adds **no interactive buttons** (mirrors
[`roadmap_priority.md`](roadmap_priority.md) §"PWA card"). Only
"Vernieuw" (refresh) remains as the global control.

## 6. Operator-attention budget

The OAB KPI ([`research_quality_kpis.md`](research_quality_kpis.md)
§3, KPI OAB) is enforced by the dashboard via a cap on visible
surfaces per campaign:

```text
visible_surfaces_per_campaign_cap = <pinned by release>
```

When the cap is exceeded, the dashboard:

- Surfaces a top-priority "attention overflow" indicator.
- Collapses lower-priority surfaces into a "more" affordance
  (no information lost; one click reveals them).
- Emits a `reason_code: operator_directive` reason record (per
  [`reason_records.md`](reason_records.md) §6) tagging the
  collapse event for auditability.

The cap value is operator-tunable per release via a governance
PR; loosening requires governance approval.

## 7. Invariants

| ID | Invariant | Enforcement |
|---|---|---|
| CQD-I1 | Read-only. No endpoint writes. | Source-text test (no atomic-write helpers imported). |
| CQD-I2 | No `dashboard/dashboard.py` mutation. Wiring is a separate operator-driven governance-bootstrap PR. | `dashboard/dashboard.py` remains in the no-touch globs unchanged. |
| CQD-I3 | No execution-side feed. The module imports nothing from `agent/execution/`, `automation/`, `broker/`, `live/`, `paper/`, `shadow/`, `trading/`, `execution/`. | Source-text test. |
| CQD-I4 | Every endpoint returns 404 with a structured envelope when the source artifact is missing. | Endpoint tests. |
| CQD-I5 | Every endpoint carries `safe_to_execute: false` at the boundary. | Endpoint tests. |
| CQD-I6 | The dashboard does not introduce a new truth surface; all numbers are derived from existing canonical / derived artifacts. | Source-cross-reference test. |
| CQD-I7 | The visible-surfaces-per-campaign cap is honoured. | Unit test with synthetic over-cap inputs. |
| CQD-I8 | No frozen-contract mutation. | Atomic-write allowlist test (the implementation does not import the write helper for frozen paths). |

## 8. What this dashboard is NOT

- Not a promotion path. Promotion happens via the funnel policy
  (ADR-014 §A).
- Not a kill-switch. Kill-switches live in the live-risk
  envelope (ADR-020 §2.8; ADR-023 will define).
- Not a backtest UI. Backtest evidence feeds via the per-
  candidate paper-readiness checklist.
- Not a substitute for the candidate evidence ledger.

## 9. Test plan (for the implementation PR)

- Endpoint shape tests (CQD-I1, CQD-I4, CQD-I5) per endpoint.
- No-`dashboard/dashboard.py`-touch source-text test (CQD-I2).
- Execution-import-deny source-text test (CQD-I3).
- Derivation-cross-reference test (CQD-I6): each KPI value
  rendered on the dashboard equals the canonical artifact's
  value.
- Attention-budget enforcement test (CQD-I7): synthetic
  over-cap state produces the collapse indicator and emits the
  operator_directive reason record.
- Frozen-contract-untouched test (CQD-I8).
- PWA-card-shape test (mirrors the existing
  `api_roadmap_priority.py` tests if a similar reusable harness
  exists; the implementation PR pins the harness).

## 10. Wiring follow-up (operator-driven)

The dashboard registration follows the established pattern from
[`roadmap_priority.md`](roadmap_priority.md) §"Wiring shape":

- The implementation PR ships the read-only endpoints and the
  PWA frontend code.
- A separate one-shot operator-authored governance-bootstrap PR
  registers the endpoints in `dashboard/dashboard.py`:

```python
from dashboard.api_research_quality import (
    register_research_quality_routes,
)
register_research_quality_routes(app)
```

Until that bootstrap lands:

- The endpoints return 404 from the dashboard;
- The PWA collapses 404 into the standard `not_available`
  envelope;
- The Research-quality tab renders the empty state;
- Nothing crashes, nothing leaks.

## 11. Update history

- 2026-05-21: initial version (Research-Quality Hardening Sprint
  detail spec).
