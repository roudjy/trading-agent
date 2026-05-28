# ADE-QRE-016C - Missing Evidence Fail-Closed Coverage

> Status: read-only coverage note.
>
> Scope: reporting/tests/docs only. This does not create runtime promotion
> logic, strategy synthesis, Addendum runtime activation, routing/campaign
> mutation, dashboard mutation, approval mutation, shadow, paper, live, broker,
> risk, execution, or frozen contract changes.

## Purpose

`ADE-QRE-016B` tightened the distinction between scaffold, working capability,
and operator-trusted capability. This item adds explicit read-only coverage that
missing evidence across the trusted-loop surfaces remains blocking and cannot be
interpreted as readiness.

## Coverage Added

The read-only reporter
`reporting.trusted_loop_missing_evidence_fail_closed` aggregates existing
evidence surfaces and classifies each required surface as either `ready` or
`fail_closed`.

Required surfaces:

- reason records;
- research-quality KPIs;
- routing readiness;
- sampling readiness;
- diagnostics loop;
- retrieval coverage;
- queue status.

Missing, malformed, incomplete, unknown, empty, or warning-only evidence remains
`fail_closed`. The report may show a bounded current queue selection separately,
but that does not upgrade broader queue-status trust when done evidence or other
queue evidence is incomplete.

## Non-Authority

The reporter is evidence-only:

- it does not write artifacts;
- it does not emit reason records;
- it does not mutate queue status;
- it does not mutate routing or sampling;
- it does not modify strategies, `registry.py`, frozen contracts, or research
  outputs;
- it does not enable strategy synthesis;
- it does not activate Addendum runtime layers;
- it does not touch shadow, paper, live, broker, risk, or execution behavior.

## Validation

Targeted tests prove that missing reason-record, KPI, routing, sampling,
diagnostics, retrieval, and queue-status evidence all fail closed. The tests also
pin that a single visible next queue item does not override missing done
evidence, and that the reporter remains read-only and serializable.
