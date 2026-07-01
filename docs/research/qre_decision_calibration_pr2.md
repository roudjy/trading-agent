# QRE Decision Calibration PR 2

This branch adds a package-side calibration layer for empirical research decisions.

## Canonical semantics

- Evidence families now carry explicit `presence`, `applicability`, `sufficiency`, and `outcome` fields.
- `AVAILABLE` does not imply `SUFFICIENT`.
- Zero-trade cost evidence is treated as `NOT_EVALUABLE` / `INSUFFICIENT`, not as positive cost proof.
- Historical blockers are preserved for lineage, but active blockers are classified separately.
- `REJECTED_SCREENING` no longer overrides an insufficient-activity terminal state.

## Benchmark portfolio

- 10 deterministic benchmark cases are defined in `packages/qre_research/decision_calibration.py`.
- The only benchmark that opens synthesis is the robust survivor case.
- Benchmark candidates remain disabled and research-only.

## Current hypothesis

- `cross_sectional_momentum_v0` remains fail-closed.
- The current current-hypothesis disposition is `NEEDS_MORE_EVIDENCE`.
- The next action remains `launch_data_oos_capacity_expansion`.

