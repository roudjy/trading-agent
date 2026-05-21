# Research-Quality KPIs

> **Status:** governance specification. Declares the measurable
> success criteria that the QRE/ADE optimises for during and after
> the 2026-05-21 roadmap reset.
>
> **Authority:** read-only specification. Declares what is measured.
> Does not grant implementation, runtime, trading, paper, shadow,
> broker, risk, or live authority.
>
> **Cross-refs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md).

## 1. Purpose

Without measurable KPIs, "research advantage" is unfalsifiable.
Architectural milestones will be mistaken for research progress.
This document declares the seven KPIs that drive release decisions
during and after the reset. Each KPI has:

- a one-line definition;
- a directional goal (minimise / maximise);
- a deterministic computation method;
- a reporting cadence;
- a stop-or-simplify threshold.

## 2. Why seven

Five is too few to capture both quality (signal) and cost
(complexity/attention/compute). Ten is too many for an operator to
hold in mind per release. Seven keeps the dashboard small, the
operator decision frequency low, and the trade-offs explicit.

## 3. KPI table

| KPI | Direction | Definition | Computation | Cadence | Stop-or-simplify threshold |
|---|---|---|---|---|---|
| Time-to-first-paper-ready-candidate (TTFPRC) | minimise | Calendar days from sprint exit to the first candidate whose paper-readiness checklist evaluates `overall=yes` | event timestamp on first `paper_readiness_checklist.v1.json` with `overall=yes` minus the sprint-exit merge timestamp | per release | >180 days → simplify further per §6 |
| OOS Deflated Sharpe of survivors (OOS-DSR) | maximise | Deflated Sharpe of survivors on the sequestered hold-out, multiplicity-adjusted via the global multiplicity ledger | for each survivor c, compute DSR using `N_eff(c)` from the multiplicity ledger; aggregate as the empirical distribution; report median + IQR | per release | median ≤ 0 over two consecutive releases → stop-or-simplify per §6 |
| Multiplicity-adjusted survivor quality (MASQ) | maximise | Median multiplicity-adjusted Sharpe across active survivors (not OOS-restricted) | identical to OOS-DSR but on full validation window | per release | trending down across three releases → halt new test generation; investigate scoring/sampling |
| Null-model-beating rate (NMBR) | maximise | Fraction of promotion candidates that beat the null-model diagnostic at chosen confidence on the hold-out | numerator: count of candidates with null-beat YES; denominator: count of promotion candidates | per release | <50% over two consecutive releases → re-tune diagnostics or halt |
| Dead-zone compute reduction (DZCR) | minimise | Percentage of campaign compute spent on dead zones, baseline = the quarter prior to the reset | dead-zone-flagged compute over total campaign compute (`logs/campaign_*` telemetry) | per release | not trending down for two consecutive releases → re-examine routing slice |
| Operator attention burden (OAB) | minimise | Operator-visible artifacts per campaign × operator decisions per week | (count of visible surfaces in operator dashboard) × (count of decisions in workloop runtime ledger) | per release | trending up across two releases → cap visible surfaces harder; defer v3.15.18 expansion |
| Candidate robustness survival rate (CRSR) | maximise | Percentage of promotion candidates that survive multi-asset + multi-timeframe + multi-regime checks | numerator: count of candidates with all three robustness checks YES; denominator: count of promotion candidates | per release | <30% over two consecutive releases → strengthen robustness checklist; do not add new diagnostics |

## 4. Reporting

Per release, the ADE release-gate report
([`release_gate_checklist.md`](release_gate_checklist.md)) includes
a KPI snapshot block. A future scoped follow-up may add a
`docs/governance/research_quality_kpis/<version>.md` per-version
record file under the existing release-gate convention. The
release-gate-agent owns that path under
[`agent_run_summaries`](agent_run_summaries) equivalents per
existing allowlist rules.

## 5. Validation gate chain (cross-reference)

KPIs are computed over candidates that have entered the validation
gate chain. The chain is operator-visible and deterministic:

1. **Null-model gate** — candidate beats null at chosen confidence.
2. **Tail / entropy filter gate** — candidate is not
   single-outlier-dependent; entropy regime is compatible with
   candidate direction.
3. **Cost-adjusted edge gate** — expected edge net of round-trip
   cost > threshold (per-regime cost model where evidence
   supports it; defaults from
   [`../../CLAUDE.md`](../../CLAUDE.md) §"Backtesting Valkuilen").
4. **OOS Deflated Sharpe gate** — multiplicity-adjusted DSR on
   training+validation window > release threshold.
5. **Robustness gate** — multi-asset + multi-timeframe +
   multi-regime survival.
6. **Hold-out red-team gate** — single authorised read on the
   sequestered window per
   [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
   §7.4.
7. **Paper-readiness checklist gate** — every check YES per
   [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
   §9.

A candidate that fails any gate halts; the failure is recorded in
scoring-reason records
([`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
§10) and contributes to the relevant KPIs.

## 6. Stop-or-simplify protocol

If a KPI crosses a stop-or-simplify threshold, the next sprint
begins with a simplification PR before adding new feature work.
Concrete simplifications considered in order of severity:

1. Defer the diagnostic that contributed most to the failed KPI
   under the promote-or-retire rule.
2. Defer the most recent v3.15.x slice that did not improve the
   failed KPI.
3. Reduce active diagnostics below three (smallest reduction first).
4. Restrict sampling to a smaller asset universe to control
   multiplicity.
5. Halt new feature merges to `main` for one release; produce a
   simplification ADR.

The protocol explicitly avoids:

- relaxing any gate;
- raising the diagnostic count without retiring an existing one;
- reactivating any deferred addendum subsection.

## 7. KPI lifecycle

- The seven KPIs are pinned by this document. Adding or removing
  a KPI requires an operator-approved governance PR.
- Direction (minimise / maximise) is pinned and may not be
  inverted without a governance PR.
- Stop-or-simplify thresholds may be tightened without a
  governance PR; loosening requires one.

## 8. What this document is NOT

- It is not a benchmark plan. KPIs measure research quality;
  throughput / latency / cost-of-compute are observability
  surfaces, not KPIs.
- It is not a candidate-promotion authority. The validation gate
  chain (§5) does that.
- It is not an adaptive feedback loop. KPI trends inform
  simplification decisions; they do not change diagnostics,
  routing, or scoring automatically.

## 9. Update history

- 2026-05-21: initial version, written as part of the roadmap
  reset.
