# QRE Same-Input Replay

## Purpose

`reporting.qre_same_input_replay` records the `017AB` replay outcome for the
exact same preregistered inputs, or the canonical no-change control
confirmation when `017AA` did not approve any criterion-class change.

## Current 017AB behavior

- Source recalibration artifact:
  `logs/qre_single_class_recalibration/latest.json`
- Source diagnosis artifact:
  `logs/qre_broad_campaign_funnel_diagnosis/latest.json`
- Source execution artifact:
  `logs/qre_broad_campaign_execution/latest.json`
- Source manifest artifact:
  `logs/qre_preregistered_campaign_manifest/latest.json`
- Produces:
  - deterministic replay assessment identity
  - before/after funnel counts
  - threshold-distance, validation, OOS, null-control, false-positive, and
    compute comparisons
  - regression checks confirming the input identities remained fixed

## Authority boundary

- Read-only and context-only.
- Produces no campaign launch, no strategy generation, and no criteria
  mutation.
- Grants no paper, shadow, live, broker, risk, or trading authority.

## Outputs

- `logs/qre_same_input_replay/latest.json`
- `logs/qre_same_input_replay/latest.md`
