# Null-Pipeline Integration Test — specification

> **Status:** specification (S6 of the Research-Quality Hardening
> Sprint declared by ADR-018 draft).
>
> **Authority:** governance spec. Declares the test design, fixture
> contract, statistical method, CI placement, and failure semantics.
> Does not implement the test; the implementation lands in a later
> scoped PR.
>
> **Cross-refs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
> §8,
> [`research_quality_kpis.md`](research_quality_kpis.md),
> [`multiplicity_ledger.md`](multiplicity_ledger.md),
> [`paper_readiness_checklist.md`](paper_readiness_checklist.md).

## 1. Purpose

The null-pipeline integration test is the cheapest possible
falsifier of the entire research stack. It runs the full active
research pipeline on **surrogate data with no exploitable signal**
and asserts that zero candidates pass the cost-adjusted promotion
gate.

If the test fails on `main`, a downstream layer is producing
candidates from noise. That is a stop-the-line event.

## 2. Test name and placement

- Path: `tests/integration/test_null_pipeline.py` (planned).
- Suite: `integration` (slow CI lane).
- CI gate: failure blocks merge to `main`.
- Run frequency: every PR (existing `integration` CI job runs it).
- Local invocation: `python -m pytest tests/integration/test_null_pipeline.py -q`.

The test is **not** in the determinism-pin family
(`tests/regression/`). It is an integration test, not a digest pin.

## 3. Fixture contract

The test uses three classes of surrogate data:

### 3.1 Shuffled returns

For each of the three active assets
(per [`roadmap_scope_status.md`](roadmap_scope_status.md) §5.3),
take the real historical return series and apply a fixed-seed
shuffle to break temporal structure while preserving the marginal
return distribution.

- Seed: `0xN_U_L_L_2026` (or equivalent; pinned by the test).
- Window: same span as the smallest active validation window.
- Output: OHLCV-shaped data with the same first/last timestamps
  as the real series but shuffled return increments.

### 3.2 Geometric Brownian motion

Synthetic price paths with:

- Drift `mu = 0` (so no edge exists on average).
- Volatility `sigma = empirical estimate from the asset's real
  historical series` (so the noise scale is realistic).
- Fixed seed; deterministic.

### 3.3 Bootstrapped returns

IID resampling (with replacement) of the real historical return
series. Same fixed seed. Different from shuffled because it
destroys autocorrelation but allows for repeat extremes.

The test runs the pipeline on each of the three classes
sequentially. Failure on any class fails the test.

## 4. Pipeline coverage

The test invokes the **active** research pipeline as declared by
[`roadmap_scope_status.md`](roadmap_scope_status.md) §3:

1. Routing (v3.15.16 minimal slice, when it lands).
2. Sampling (v3.15.17 minimal slice, when it lands).
3. The three active diagnostics: null-model, tail asymmetry,
   entropy structure.
4. Hypothesis Discovery (v3.15.19 minimal slice, when it lands).
5. Validation gate chain
   ([`research_quality_kpis.md`](research_quality_kpis.md) §5)
   gates 1-4 (the hold-out red-team gate, gate 6, is **not** part
   of the null-pipeline test — it remains operator-authorised).

Until each slice lands, the test runs against the **highest
currently-available subset** and asserts the corresponding subset
of invariants. The implementation PR pins the subset as the
slices ship.

## 5. Assertions

The test asserts **all** of the following on each fixture class:

| ID | Assertion | Source |
|---|---|---|
| NP-A1 | Zero candidates pass the cost-adjusted promotion gate (validation gate 3). | `paper_readiness_checklist` or scoring-reason records |
| NP-A2 | Zero candidates reach paper-readiness (full checklist `overall=yes`). | `paper_readiness_checklist` artifact |
| NP-A3 | The candidate-scoring score distribution is statistically indistinguishable from the score distribution on a second independent surrogate (i.e. two independent null fixtures produce indistinguishable score distributions). | KS test, see §6 |
| NP-A4 | The diagnostic utility ledger records zero "moved survivor status" events for any of the three diagnostics. | diagnostic utility ledger (when it ships) |
| NP-A5 | The multiplicity ledger records the expected count of `event_kind: null_model_evaluation` events (one per candidate-asset-window combination tested). | [`multiplicity_ledger.md`](multiplicity_ledger.md) |
| NP-A6 | No write occurs against any frozen contract (`research_latest.json`, `strategy_matrix.csv`). | filesystem snapshot before/after |
| NP-A7 | No write occurs against any protected path. | filesystem snapshot before/after |

## 6. Statistical method (NP-A3)

The test uses a **two-sample Kolmogorov-Smirnov (KS) test** to
compare:

- Distribution A: scores from fixture class X on the active
  pipeline.
- Distribution B: scores from fixture class X on an independent
  surrogate with a different fixed seed.

The implementation PR pins:

- the significance level `alpha = 0.01`;
- the sample size requirement (minimum N per distribution);
- the deterministic seed pair used for the two independent
  surrogates;
- the exact KS test implementation
  (`scipy.stats.ks_2samp` is the planned default; if `scipy` is
  not in the dependency set, the implementation PR ships a pure
  Python KS).

The test passes when:

```text
ks_statistic_p_value > alpha
```

(i.e., we fail to reject the null hypothesis that the two
distributions are the same; the pipeline produces noise-like
scores on noise-like inputs).

A failing KS test means the pipeline is finding "edge" on
indistinguishable surrogate inputs — a downstream layer is
overfit.

## 7. Determinism

The test is deterministic:

- Fixed seeds for all surrogates.
- Fixed pipeline configuration.
- Fixed KS test parameters.
- Network and `subprocess` are forbidden during the test (mirrors
  the existing test-discipline pattern).

Two runs on the same commit produce byte-identical assertion
traces (modulo wall-clock timestamps in log records, which are
not inspected by the test).

## 8. CI placement

- Lane: `integration` (existing CI job named `integration` or
  added by the implementation PR if it doesn't exist yet).
- Timeout: implementation PR pins a generous default (planned:
  10 minutes).
- Required: yes. The job must be on the required-checks list for
  branch protection on `main`. Adding it to the required-checks
  list is an operator-driven governance-bootstrap PR.

## 9. Failure modes and operator actions

| Failure | Likely cause | Operator action |
|---|---|---|
| NP-A1 / NP-A2 fail | A downstream layer is producing candidates from noise | Block release. Bisect by disabling pipeline layers one-by-one. |
| NP-A3 fails | Score distribution depends on inputs in a way that breaks under noise | Inspect scoring-reason records for the surrogate run; look for non-monotone score behaviour. |
| NP-A4 fails | A diagnostic is mis-classifying noise as signal | Disable the offending diagnostic; investigate. |
| NP-A5 fails | Multiplicity ledger is miscounting | Inspect ledger manifest; replay deterministic surrogate. |
| NP-A6 / NP-A7 fail | A write escape happened during the run | Stop-the-line. Open a governance incident. |

## 10. What the test is NOT

- Not a benchmark. It does not measure throughput, memory, or
  latency.
- Not a substitute for OOS validation. It validates noise
  rejection, not signal acceptance.
- Not a substitute for the hold-out red-team review.
- Not an exhaustive test of every diagnostic interaction. It is
  the *single* end-to-end falsifier.

## 11. Maintenance discipline

- New slices (v3.15.16, .17, .18, .19) update the test in the
  same PR that ships them, expanding the pipeline coverage in
  §4.
- New diagnostics activated under promote-or-retire update the
  test fixture and assertions in the same PR that activates
  them.
- The KS test parameters do not change without a governance PR.
- The fixture seeds do not change without a governance PR.

## 12. Test-weakening protection

Per [`no_test_weakening.md`](no_test_weakening.md), the
following changes are **forbidden** without an operator-approved
governance PR:

- Removing any NP-Ax assertion.
- Increasing `alpha` from `0.01`.
- Reducing the fixture sample size.
- Disabling the test in CI.
- Marking the test as `xfail` or `skip`.

The CI workflow that runs `integration` must not be modified to
exclude this test outside a `ci-guardian` agent task.

## 13. Update history

- 2026-05-21: initial version (Research-Quality Hardening Sprint,
  S6 detail spec). Expands
  [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
  §8.
