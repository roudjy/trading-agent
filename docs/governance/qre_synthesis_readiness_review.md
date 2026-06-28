# QRE Synthesis-Readiness Review

## Purpose

`reporting.qre_synthesis_readiness_review` materializes the review-only
ADE-QRE-017AD synthesis-readiness decision. It does not implement synthesis,
generate executable strategy code, register strategies, or mutate campaign
results.

## Current 017AD behavior

- Reads the authoritative readiness artifacts from maturity, evidence density,
  reason-record maturity, routing, sampling, suppression, source/data
  readiness, lineage, decay, operator decisioning, campaign portfolio,
  preregistered manifest, broad execution, diagnosis, recalibration, replay,
  and repeated independent OOS.
- Produces:
  - deterministic synthesis-readiness identity
  - machine-readable readiness matrix for mandatory gates
  - operator-readable blocking summary
  - per-thesis synthesis eligibility state
  - ordered remediation backlog with synthesis design held last and blocked
  - complete provenance for the review-only decision

## Closed outcome vocabulary

- `CONTINUE_BLOCKED`
- `ELIGIBLE_FOR_SEPARATE_SYNTHESIS_DESIGN_REVIEW`
- `INSUFFICIENT_EVIDENCE`

## Authority boundary

- Read-only and context-only.
- Produces no campaign launch, no strategy synthesis, no strategy registration,
  and no trading authority.
- Grants no paper, shadow, live, broker, risk, or capital-allocation
  authority.

## Outputs

- `logs/qre_synthesis_readiness_review/latest.json`
- `logs/qre_synthesis_readiness_review/latest.md`
