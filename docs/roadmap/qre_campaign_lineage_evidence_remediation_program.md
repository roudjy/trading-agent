# ADE-QRE-018 Campaign Lineage and Evidence Completeness Remediation Program

## Purpose

ADE-QRE-018 is the governed remediation program selected by
`ADE-QRE-017AD` after the final synthesis-readiness outcome
`CONTINUE_BLOCKED`.

It is a read-only evidence-remediation program. It may improve lineage,
identity, null-control, reason-record, evidence-completeness, campaign-ready
portfolio, and preregistration surfaces. It may not implement strategy
synthesis, generate executable strategy code, register strategies
automatically, or activate paper, shadow, live, broker, risk, or execution
paths. Those capabilities, if later admitted, require a separate governed
follow-on program that preserves `.claude/**` and `research/**` as protected
surfaces and uses isolated generated-research paths instead.

## Baseline

- completed baseline program: `ADE-QRE-017`
- final review-only readiness item: `ADE-QRE-017AD`
- authoritative readiness artifact: `qrsr_1ca565566a3c96e3`
- final readiness outcome: `CONTINUE_BLOCKED`
- exact next permitted action:
  `launch_separate_remediation_program_for_lineage_identity_controls_evidence_and_capacity_before_any_synthesis_design_review`

## Ordered remediation backlog carried forward

1. `campaign_lineage_establishment`
2. `identity_ambiguity_resolution`
3. `null_control_completion`
4. `evidence_completeness_population`
5. `data_source_readiness`
6. `independent_oos_capacity`
7. `replacement_hypothesis_planning`
8. `second_broad_preregistered_campaign`
9. `synthesis_design`

## Program items

### ADE-QRE-018A - Historical Queue and Baseline Reconciliation

- dependencies: `ADE-QRE-017AD done`
- scope: classify historical queue ambiguity, preserve audit history, establish
  one deterministic remediation-program baseline
- expected files:
  - `docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md`
  - `reporting/ade_queue_status_self_audit.py`
  - `tests/unit/test_ade_queue_status_self_audit.py`
- forbidden files:
  - generated queue projections
  - frozen contracts
  - runtime paths
- definition of done:
  - historical warnings remain visible and classified
  - current remediation selection is unambiguous
  - no historical evidence is fabricated

### ADE-QRE-018B - Blocked-Thesis Lineage Census

- dependencies: `ADE-QRE-018A done`
- scope: deterministic census for the six blocked theses
- expected files:
  - `reporting/qre_blocked_thesis_lineage_census.py`
  - `tests/unit/test_qre_blocked_thesis_lineage_census.py`
- definition of done:
  - machine-readable census
  - operator-readable report
  - stable census identity
  - closed lineage status vocabulary

### ADE-QRE-018C - Identity Ambiguity Resolution

- dependencies: `ADE-QRE-018B done`
- scope: thesis, strategy, preset, source, instrument, dataset, snapshot,
  campaign, and evidence identity resolution from authoritative repository
  evidence only
- expected files:
  - `reporting/qre_identity_ambiguity_resolution.py`
  - `tests/unit/test_qre_identity_ambiguity_resolution.py`
- definition of done:
  - deterministic resolution states
  - alias tracking and provenance
  - unresolved identities fail closed

### ADE-QRE-018D - Campaign Lineage Materialization

- dependencies: `ADE-QRE-018C done`
- scope: thesis -> mechanism -> strategy/preset -> universe -> source ->
  dataset -> snapshot -> campaign specification where evidence supports it
- expected files:
  - `reporting/qre_campaign_lineage_materialization.py`
  - `tests/unit/test_qre_campaign_lineage_materialization.py`
- definition of done:
  - complete versus incomplete lineage counts
  - explicit blockers for missing strategy, preset, dataset, or campaign scope

### ADE-QRE-018E - Null-Control Specification and Completeness

- dependencies: `ADE-QRE-018D done`
- scope: mechanistically appropriate null-control contracts and completeness
  states without fabricated empirical outcomes
- expected files:
  - `reporting/qre_null_control_readiness.py`
  - `tests/unit/test_qre_null_control_readiness.py`
- definition of done:
  - required controls, rationale, readiness state, and blockers are explicit

### ADE-QRE-018F - Evidence and Reason-Record Completion

- dependencies: `ADE-QRE-018E done`
- scope: reason-record completeness, evidence authority, freshness, and
  fail-closed missing-evidence reporting
- expected files:
  - `reporting/qre_evidence_reason_record_completion.py`
  - `tests/unit/test_qre_evidence_reason_record_completion.py`
- definition of done:
  - evidence and reason-record states distinguish authoritative, context-only,
    stale, contradicted, missing, blocked, and not-applicable

### ADE-QRE-018G - Validation, Reproducibility and Operator-Report Completion

- dependencies: `ADE-QRE-018F done`
- scope: consolidate validation, reproducibility, freshness, and
  operator-report completeness where evidence permits
- expected files:
  - `reporting/qre_validation_repro_operator_completion.py`
  - `tests/unit/test_qre_validation_repro_operator_completion.py`
- definition of done:
  - validation, reproducibility, and operator-report gates are explicit per
    thesis and in aggregate

### ADE-QRE-018H - Campaign-Ready Portfolio Reconstruction

- dependencies: `ADE-QRE-018G done`
- scope: rebuild a fail-closed portfolio from the remediated artifacts
- expected files:
  - `reporting/qre_campaign_portfolio_reconstruction.py`
  - `tests/unit/test_qre_campaign_portfolio_reconstruction.py`
- definition of done:
  - ready, blocked, insufficient-evidence, duplicate, dead-zone, and rejected
    states are explicit
  - no campaign execution is triggered

### ADE-QRE-018I - Replacement Hypothesis Planning

- dependencies: `ADE-QRE-018H done`
- scope: archive `trend_pullback_v1` as rejected and propose one genuinely
  distinct replacement thesis from the existing deterministic discovery
  mechanism
- expected files:
  - `reporting/qre_rejected_thesis_replacement_plan.py`
  - `tests/unit/test_qre_rejected_thesis_replacement_plan.py`
- definition of done:
  - rejection archive preserves historical evidence and consumed OOS windows
  - replacement thesis remains proposal-only and is not treated as
    campaign-ready without evidence

### ADE-QRE-018J - Second Broad Preregistered Campaign

- dependencies: `ADE-QRE-018I done`
- scope: execute the second preregistered campaign only after a canonically
  accepted ready-cell manifest exists
- expected files:
  - `reporting/qre_second_broad_campaign_prep.py`
  - `tests/unit/test_qre_second_broad_campaign_prep.py`
- definition of done:
  - execution remains blocked when no ready cells exist
  - preregistered campaign artifact is immutable if materialized

### ADE-QRE-018K - Second Synthesis-Readiness Review

- dependencies: `ADE-QRE-018J done`
- scope: re-run synthesis-readiness only after the second campaign produces new
  authoritative evidence
- expected files:
  - `reporting/qre_second_synthesis_readiness_review.py`
  - `tests/unit/test_qre_second_synthesis_readiness_review.py`
- definition of done:
  - no synthesis promotion occurs without satisfied mandatory gates

## Global restrictions

- never treat scaffold presence as readiness evidence
- never fabricate lineage, identity, OOS, null-control, or evidence authority
- never recycle `trend_pullback_v1` through threshold or parameter tuning
- never execute the second broad campaign in the remediation-admission PR
- never change frozen contracts or protected runtime paths

## Exit condition

The remediation program is considered successful only when the queue can
either:

- advance to `ADE-QRE-018J` with at least one genuinely ready preregistration
  cell; or
- record an exact fail-closed blocker state that preserves why no second
  campaign may execute yet.
