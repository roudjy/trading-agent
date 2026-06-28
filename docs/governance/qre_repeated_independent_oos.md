# QRE Repeated Independent OOS

## Purpose

`reporting.qre_repeated_independent_oos` records whether any hypothesis is
currently eligible for repeated independent OOS evidence and fails closed when
the repository only shows blocked lineage or already-consumed rejected OOS
windows.

## Current 017AC behavior

- Source thesis registry artifact:
  `logs/qre_behavior_thesis_registry/latest.json`
- Source operator decision artifact:
  `logs/qre_operator_decision_report/latest.json`
- Source lineage artifact:
  `logs/qre_contradiction_hypothesis_lineage/latest.json`
- Source replay artifact:
  `logs/qre_same_input_replay/latest.json`
- Source preregistered multiwindow run artifact:
  `logs/qre_preregistered_multiwindow_evidence_run/latest.json`
- Source closure artifact:
  `logs/qre_multiwindow_evidence_closure/latest.json`
- Produces:
  - deterministic independent-OOS assessment identity
  - per-thesis independent-OOS eligibility status
  - explicit blockers when campaign lineage is missing
  - explicit consumed OOS windows when the only visible campaign already
    exhausted preregistered OOS without acceptance
  - contradiction, operator, and lineage update surfaces without mutating the
    source artifacts

## Authority boundary

- Read-only and context-only.
- Produces no campaign launch, no strategy generation, and no execution
  authority.
- Grants no paper, shadow, live, broker, risk, or trading authority.

## Outputs

- `logs/qre_repeated_independent_oos/latest.json`
- `logs/qre_repeated_independent_oos/latest.md`
