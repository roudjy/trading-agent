# ADE-QRE-016B - Operator Trust Criteria Tightening

> Status: read-only trust criteria.
>
> Scope: governance documentation only. These criteria do not create runtime
> gates, approval authority, dashboard mutation, strategy synthesis, Addendum
> runtime, routing mutation, campaign mutation, shadow, paper, live, broker,
> risk, execution, or frozen contract changes.

## Purpose

`ADE-QRE-015A` separated trusted-loop evidence into scaffold, working
capability, and narrow operator-trusted capability. `ADE-QRE-016A` then mapped
the remaining evidence gaps to closure candidates without marking any gap
closed. This document tightens the criteria for those trust levels so later
queue items cannot treat thin evidence or read-only reporting as broader
readiness.

## Trust Level Criteria

| Trust level | Required evidence | Measurable criteria | Fail-closed conditions | Explicitly not authorized |
| --- | --- | --- | --- | --- |
| Scaffold | A doc, taxonomy, fixture, schema outline, or planning note exists and is traceable to a queue item. | Source document exists; queue id is cited; scope and non-goals are stated; no runtime path is modified. | Missing source doc, unclear queue id, missing non-goals, or any runtime/protected-path requirement keeps the surface at `not_trusted`. | Scaffold does not prove readiness, does not authorize implementation, and does not override blocked/deferred queue status. |
| Working capability | Deterministic read-only reporting, tests, fixtures, or validation can inspect state without mutation. | Report/test command is identified; output is deterministic or schema-pinned; missing inputs are visible; protected/frozen paths remain untouched; `forbidden_edge_count=0` where architecture scanning applies. | Missing artifact, stale artifact without explicit status, empty population, malformed input, unknown status, or missing evidence reference must return a blocked/not-ready result. | Working capability does not grant promotion authority, operator approval authority, routing/campaign authority, synthesis readiness, or execution readiness. |
| Operator-trusted capability | Evidence is complete enough to support one bounded operator decision without hidden missing inputs or unsupported claims. | The decision question is named; all required evidence rows are present; each blocker is resolved, explicitly accepted by an operator record, or remains blocking; validation evidence is cited; downstream scope remains dependency-gated. | Any missing required evidence, unresolved blocker, ambiguous recommendation, unapproved substitute criterion, or needed runtime authority keeps the result below operator-trusted. | Operator trust is limited to the named decision and does not generalize to future items, runtime activation, approvals, dashboard mutation, or autonomous authority expansion. |

## Evidence Requirements By Surface

| Surface | Minimum level currently supported by 015/016A evidence | Upgrade requirement before operator-trusted use | Current fail-closed reason |
| --- | --- | --- | --- |
| Reason records | Working capability for density inspection only. | Durable reason records with evidence references, record counts, missing-reference reasons, and validation showing absent records stay blocked. | `ADE-QRE-015A` recorded `record_count=0` and `records_with_evidence_refs=0`; `ADE-QRE-016A` kept `GAP-015B-01` open. |
| Research-quality KPIs | Working capability for KPI doctrine and fail-closed visibility. | Numeric KPI values for each required KPI, or explicit operator-approved substitute criteria with rationale. | `ADE-QRE-015A` recorded 0 of 7 complete KPI values; KPI doctrine is not numeric readiness. |
| Routing readiness | Working capability for read-only non-ready evidence. | Non-empty routing evidence, readiness calculation, and validation that missing snapshots fail closed before any v3.15.16 planning claim. | Routing evidence reported `final_recommendation=nothing_ready`, `total=0`, and readiness score 0.0. |
| Sampling readiness | Working capability for read-only non-ready evidence. | Non-empty sampling evidence, readiness calculation, and validation that missing snapshots fail closed before any feature-track return claim. | Sampling evidence reported `final_recommendation=nothing_ready`, `total=0`, and readiness score 0.0. |
| Failure-action mapping | Working capability for visibility only. | An actual failure population with actionable/non-actionable classification and no invented cause. | `total_failures=0` and `actionable_failure_count=0`; no action usefulness can be proven from an empty population. |
| Queue sequencing | Operator-trusted capability for bounded queue selection only. | Current queue item has complete done evidence; dependencies are done; exactly one eligible ready item exists; stale historical ready items are explicitly non-selectable. | Trust does not expand beyond queue sequencing and does not authorize implementation outside the selected item. |

## Fail-Closed Decision Rules

A trusted-loop surface must be classified below operator-trusted when any of the
following is true:

- a required artifact is missing, stale, malformed, or schema-unknown;
- an evidence population is empty and the claim depends on observed examples;
- a blocker is unresolved and lacks explicit operator acceptance;
- a substitute criterion is proposed without written operator approval;
- more than one recommendation or ready item is selected;
- validation evidence is absent for the relevant claim;
- the claim would require strategy synthesis, Addendum runtime activation,
  routing/campaign mutation, approval mutation, dashboard mutation, autonomous
  authority expansion, or execution-sensitive behavior.

## Current Trust Boundaries

The current ADE-QRE-016 state supports:

- operator-trusted queue sequencing for selecting `ADE-QRE-016B` after
  `ADE-QRE-016A` was marked done;
- working read-only evidence visibility for reason records, KPIs, routing,
  sampling, diagnostics, retrieval, and failure-action surfaces;
- scaffold-level planning for future closure candidates.

The current state does not support:

- operator-trusted end-to-end trusted-loop capability;
- return to QRE Feature Build Track implementation;
- v3.15.16 Intelligent Routing implementation;
- strategy synthesis eligibility;
- Addendum 1, 2, 3, or 4 runtime activation;
- shadow, paper, live, broker, risk, or execution behavior;
- dashboard mutation routes, approval mutation, or autonomous authority
  expansion.

## Queue Consequence

After this item is merged and marked done through the queue lifecycle,
`ADE-QRE-016C - Missing Evidence Fail-Closed Coverage` may become eligible. It
must use these criteria to prove that missing evidence cannot be interpreted as
readiness across the key trusted-loop surfaces.
