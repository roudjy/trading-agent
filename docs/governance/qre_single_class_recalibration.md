# QRE Single-Class Recalibration

## Purpose

`reporting.qre_single_class_recalibration` evaluates whether `017Z` produced
enough evidence to justify exactly one criterion-class change, and fails closed
to a no-change preregistration when it did not.

## Current 017AA behavior

- Source diagnosis artifact:
  `logs/qre_broad_campaign_funnel_diagnosis/latest.json`
- Source execution artifact:
  `logs/qre_broad_campaign_execution/latest.json`
- Source manifest artifact:
  `logs/qre_preregistered_campaign_manifest/latest.json`
- Produces:
  - deterministic recalibration identity
  - candidate criterion-class rows and blocker reasons
  - a preregistered no-change or single-class-only decision record
  - explicit forbidden concurrent changes, adoption criteria, rejection
    criteria, and reversal plan

## Authority boundary

- Read-only and context-only.
- Produces no campaign launch, no strategy generation, and no criteria
  mutation.
- Grants no paper, shadow, live, broker, risk, or trading authority.

## Outputs

- `logs/qre_single_class_recalibration/latest.json`
- `logs/qre_single_class_recalibration/latest.md`
