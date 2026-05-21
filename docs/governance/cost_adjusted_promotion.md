# Cost-Adjusted Promotion Criteria — specification

> **Status:** specification (Research-Quality Hardening Sprint
> S-extra; declared as part of the sprint's expected scope).
>
> **Authority:** governance spec. Declares the per-regime cost
> model, the cost-adjusted edge promotion gate, the cost-model
> artifact, and the deterministic computation rules. Does not
> modify the canonical authority for candidate promotion (ADR-014
> §A; the funnel policy). Does not implement runtime code; the
> implementation lands in a later scoped PR.
>
> **Cross-refs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
> §6 + §9,
> [`research_quality_kpis.md`](research_quality_kpis.md) §5
> (validation gate 3),
> [`paper_readiness_checklist.md`](paper_readiness_checklist.md)
> (gate `cost_adjusted_edge_positive`),
> [`docs/adr/ADR-008-execution-realism-and-evaluation-hardening.md`](../adr/ADR-008-execution-realism-and-evaluation-hardening.md),
> [`docs/adr/_drafts/ADR-020-paper-shadow-live-separation.md`](../adr/_drafts/ADR-020-paper-shadow-live-separation.md),
> [`../../CLAUDE.md`](../../CLAUDE.md) §"Backtesting Valkuilen".

## 1. Purpose

A candidate's edge is meaningful only **net of round-trip
transaction costs and slippage**. Without an explicit cost model
and a cost-adjusted promotion gate:

- Candidates with raw positive edge but negative net edge promote
  to paper readiness.
- Operators carry the cost realism in their heads.
- Paper deployment loses meaning the first time it runs.

The cost-adjusted promotion criteria turn cost realism into a
named gate (validation gate 3 in
[`research_quality_kpis.md`](research_quality_kpis.md) §5) backed
by a deterministic cost model that the gate consumes.

## 2. Scope

The criteria apply to:

- Every promotion candidate (every candidate that has cleared
  gates 1 and 2 — null-model beat and tail/entropy filters).
- Every asset class in the active universe.

They do **not** apply to:

- Exploratory candidates not in a promotion path.
- Backtest reports that do not feed the funnel policy.
- Live / paper / shadow / broker / execution behaviour (per
  ADR-020 they do not feed live).

## 3. Authority

The cost model is **lineage**, not authority.

- It does not promote, demote, or rank candidates.
- It produces a deterministic per-trade cost estimate that the
  promotion gate consumes.
- It does not feed any live / paper / shadow / broker /
  execution surface (ADR-020 §2).
- It does not mutate `paper_readiness_latest.v1.json`,
  `research_latest.json`, or `strategy_matrix.csv`.

The canonical authority for "this candidate is paper-ready"
remains `paper_readiness_latest.v1.json` `readiness_status` per
ADR-014 §A. The cost-adjusted edge gate is one input to that
authority via the paper-readiness checklist.

## 4. Cost model

### 4.1 Per-venue per-side baseline

The baseline costs are the values declared in
[`../../CLAUDE.md`](../../CLAUDE.md) §"Backtesting Valkuilen"
(restated here for traceability):

| Venue | Round-trip cost | Notes |
|---|---|---|
| Bitvavo (crypto, EUR) | **0.50 %** | 0.25 % per side; round-trip = 2 × 0.25 % |
| IBKR (equities) | **€1 per order** | flat per-order; round-trip = 2 × €1 = €2 |
| Polymarket (binary markets) | **2.0 %** | average spread, round-trip |
| Slippage (all venues) | **+0.10 %** | additive simulation on every trade |

For crypto on Bitvavo, total cost per round trip:

```text
cost_rt_bitvavo = 0.005 + 0.001 = 0.006   # 0.6 %
```

For equities on IBKR, total cost is flat plus slippage:

```text
cost_rt_ibkr(position_eur) = 2.0 + (position_eur * 0.001)
```

For Polymarket binary markets, total cost per round trip:

```text
cost_rt_polymarket = 0.020 + 0.001 = 0.021   # 2.1 %
```

### 4.2 Per-regime refinement

When evidence supports it (sufficient OOS data per regime), the
baseline cost is **refined** by a per-regime multiplier:

```text
cost_rt(venue, regime) = cost_rt(venue) * regime_multiplier(venue, regime)
```

The regime multipliers are deterministic and live in the
cost-model artifact (§5). Allowed regimes for v3.15.x match the
sampling layer's regime taxonomy (pinned by v3.15.17 minimal
slice when it ships); until that lands, the multiplier is `1.0`
for all regimes.

Permitted regime multiplier ranges:

| Venue | Min multiplier | Max multiplier | Reason |
|---|---|---|---|
| Bitvavo | 0.8 | 3.0 | Volume-thin weekends, news shocks |
| IBKR | 0.9 | 2.5 | Open/close volatility, low-volume hours |
| Polymarket | 0.7 | 4.0 | Low-liquidity binary outcomes |

A multiplier outside these ranges requires an explicit operator
governance PR. The implementation PR pins these as schema
validators.

### 4.3 Per-trade cost computation

For a candidate's evaluated trade `t`:

```text
trade_cost(t) = position_eur(t) * cost_rt(venue(t), regime(t))
              + (flat_cost(venue(t)) if applicable)
```

Sum over all evaluated trades to get the candidate's total cost
exposure.

## 5. Cost-model artifact

Path: `state/cost_model.v1.json`.

Operator-authored (mirrors the hold-out manifest discipline).
Agents do not modify it.

Shape:

```json
{
  "schema_version": 1,
  "module_version": "spec-2026-05-21",
  "generated_at_utc": "<rfc3339-utc-seconds>",
  "venues": {
    "bitvavo": {
      "round_trip_rate": 0.005,
      "slippage_additive": 0.001,
      "flat_per_order_eur": 0.0
    },
    "ibkr": {
      "round_trip_rate": 0.0,
      "slippage_additive": 0.001,
      "flat_per_order_eur": 1.0
    },
    "polymarket": {
      "round_trip_rate": 0.020,
      "slippage_additive": 0.001,
      "flat_per_order_eur": 0.0
    }
  },
  "regime_multipliers": {
    "bitvavo": { /* regime: multiplier */ },
    "ibkr":    { /* regime: multiplier */ },
    "polymarket": { /* regime: multiplier */ }
  },
  "notes": "Baseline costs from CLAUDE.md backtesting section."
}
```

## 6. Cost-adjusted edge gate

For a candidate `c`:

```text
gross_edge(c)   = expected_pnl_per_trade(c)     # from candidate evidence
total_trades(c) = expected_number_of_trades(c)  # from candidate evidence
cost_per_trade(c) = average_trade_cost(c)       # from §4.3 over c's evaluated trades

net_edge(c)     = gross_edge(c) - cost_per_trade(c)
```

The gate passes when:

```text
net_edge(c) > release_threshold_net_edge
AND
p_value(net_edge(c) > 0) <= release_threshold_p_value
```

Where:

- `release_threshold_net_edge` is **0** by default; raised per
  release at operator discretion.
- `release_threshold_p_value` is **0.05** by default;
  tightened per release at operator discretion. Loosening
  requires an operator-approved governance PR.

The gate fails closed: if any required input is missing
(cost model artifact absent, regime not in multiplier table,
evidence ledger missing trades), the gate returns `no` (not
`n/a`).

## 7. Per-regime cost sensitivity

A candidate that passes the gate at the baseline must also
pass at:

```text
cost_per_trade(c) * 1.25   # 25 % cost-sensitivity headroom
```

A candidate that passes baseline but fails at 1.25x is recorded
with `reason_code: cost_gate_pass_borderline` in the scoring
reason record (per
[`reason_records.md`](reason_records.md) §6.3). It still
passes the gate (since the baseline check passed), but the
borderline tag surfaces the fragility to the operator.

A candidate that fails at the baseline produces a
`reason_code: cost_gate_fail` scoring reason record and the
paper-readiness check `cost_adjusted_edge_positive: no`.

## 8. Invariants

| ID | Invariant | Enforcement |
|---|---|---|
| CP-I1 | Cost model artifact is operator-authored. No agent / hook / runtime writes to it. | `state/cost_model.v1.json` is added to the operator-only allowlist; tests pin. |
| CP-I2 | Regime multipliers stay within the §4.2 per-venue ranges. | Schema validator. |
| CP-I3 | The gate computation is pure and deterministic. | Source-text test (no `subprocess`, no `socket`, no `requests`); byte-identical-output test. |
| CP-I4 | The gate fails closed on missing inputs. | Unit test. |
| CP-I5 | The gate does not feed any execution-side surface (ADR-020 §2). | Source-text test (no import of execution modules). |
| CP-I6 | The 25 % cost-sensitivity check is always run when the baseline passes. | Unit test. |
| CP-I7 | The gate writes exactly one `cost_gate_pass`, `cost_gate_fail`, or `cost_gate_pass_borderline` reason code per evaluation. | Unit test. |
| CP-I8 | The gate's release thresholds are pinned by release; loosening requires an operator-approved governance PR. | `tests/governance/test_cost_thresholds.py` (planned). |

## 9. Operator workflow

1. Operator authors / updates `state/cost_model.v1.json` (per
   the constraints in §4 and §5).
2. As candidates produce trade-level evidence, the cost-gate
   evaluator computes per-trade cost and net edge.
3. The evaluator writes a scoring reason record per candidate.
4. The paper-readiness checklist regenerates with
   `cost_adjusted_edge_positive: yes|no|n/a` based on the
   reason record.
5. Operator inspects borderline candidates via the
   candidate-quality dashboard
   ([`candidate_quality_dashboard.md`](candidate_quality_dashboard.md)).

## 10. Test plan (for the implementation PR)

- Schema test for `state/cost_model.v1.json` (CP-I1, CP-I2).
- Gate-computation determinism test (CP-I3).
- Gate fail-closed test (CP-I4): missing cost model →
  gate returns `no`.
- Execution-import-deny source-text test (CP-I5).
- 25 %-sensitivity test (CP-I6): synthetic candidate passes
  baseline, fails 1.25×; assert `cost_gate_pass_borderline`.
- Reason-record-emission test (CP-I7).
- Threshold-pin test (CP-I8): a release threshold change in
  source raises a governance-lint warning unless an operator
  governance PR marker is present.
- Property test: net_edge monotone in gross_edge with
  cost_per_trade fixed; monotone (decreasing) in cost_per_trade
  with gross_edge fixed.

## 11. What this spec is NOT

- Not a backtest report. Backtest evidence feeds the gate.
- Not a kill-switch. The gate filters before promotion; it does
  not stop a live candidate.
- Not a venue-routing decision. The cost model is per-venue;
  venue selection happens upstream of the gate.
- Not a substitute for the funnel policy. The gate is one input;
  the funnel policy decides promotion.

## 12. Update history

- 2026-05-21: initial version (Research-Quality Hardening Sprint
  extra). Anchored to
  [`../../CLAUDE.md`](../../CLAUDE.md) §"Backtesting Valkuilen"
  baseline costs.
