# ADE-QRE-016F - Return-to-Feature-Track Criteria Refinement

> Status: docs-only return criteria.
>
> Scope: governance documentation only. This criteria record does not implement
> v3.15.16, mutate the roadmap, activate strategy synthesis, add routing or
> campaign behavior, activate Addendum runtime layers, touch shadow, paper,
> live, broker, risk, execution paths, or change frozen contracts.

## Criteria Result

The QRE Feature Build Track is not ready to resume implementation from the
current trusted-loop evidence.

Future return is allowed only when every required evidence gate below is
complete, reproducible, and fail-closed. A missing, empty, stale, or
context-only evidence surface must block return-readiness rather than be
interpreted as partial readiness.

This document refines criteria only. It does not start the selected future
direction, does not authorize v3.15.16 implementation, and does not change any
runtime gate into authority.

## Required Evidence Gates

| Gate | Required evidence before return | Current status | Blocking reason |
| --- | --- | --- | --- |
| `RTF-01` reason-record evidence | Durable reason records exist for the relevant feature-track entry point, include evidence references, and missing records are counted explicitly. | Not met | `ADE-QRE-016A` keeps `GAP-015B-01` open with `record_count=0` and `records_with_evidence_refs=0` as the current basis. |
| `RTF-02` research-quality KPI evidence | Every required research-quality KPI is either numerically complete and reproducible or has an explicit operator-approved substitute criterion. | Not met | `ADE-QRE-016A` keeps `GAP-015B-02` open because 0 of 7 KPI values were complete in the reviewed state. |
| `RTF-03` routing readiness evidence | Routing readiness is backed by a non-empty read-only snapshot, explicit readiness score, blocker list, and fail-closed behavior for missing snapshots. | Not met | Routing currently reports `final_recommendation=nothing_ready`, `total=0`, and readiness score 0.0. |
| `RTF-04` sampling readiness evidence | Sampling readiness is backed by non-empty candidate evidence, explicit sampling quality criteria, and fail-closed behavior for missing snapshots. | Not met | Sampling currently reports `final_recommendation=nothing_ready`, `total=0`, and readiness score 0.0. |
| `RTF-05` trust classification evidence | The proposed return surface is classified as operator-trusted, not merely scaffold or working read-only capability, using the `ADE-QRE-016B` criteria. | Not met | `ADE-QRE-016E` states the trusted loop is not operator-trusted end to end. |
| `RTF-06` missing-evidence fail-closed coverage | Missing reason records, KPI values, routing snapshots, sampling snapshots, retrieval context, and diagnostics evidence all block readiness in reporting/tests. | Partially met | `ADE-QRE-016C` and `ADE-QRE-016D` improve coverage, but remaining upstream evidence gaps still block return. |
| `RTF-07` retrieval and diagnostics authority boundary | Retrieval and diagnostics are documented and validated as context/evidence surfaces only, with no approval, routing, synthesis, or execution authority. | Partially met | Current docs preserve the boundary, but the return decision still requires all evidence gates to pass. |
| `RTF-08` queue and governance evidence | The current queue item is done, dependencies are deterministic, historical warnings are either non-blocking or explicitly scoped, and no protected paths are touched. | Partially met | Current ADE-QRE-016 sequencing is deterministic, but historical audit warnings still block broad audit-completeness claims. |

## Return Decision Rule

A future return-to-feature-track recommendation may be selected only if:

- all `RTF-01` through `RTF-08` gates are `met`;
- the evidence source for each gate is committed, reviewable, and reproducible;
- fail-closed behavior is demonstrated for missing evidence on every required
  surface;
- no required criterion depends on strategy synthesis, Addendum runtime
  activation, shadow, paper, live, broker, risk, or execution behavior;
- no required criterion depends on approval mutation, dashboard mutation,
  autonomous authority expansion, external data adapters, new datafeeds, or
  frozen contract mutation;
- routing and sampling evidence are treated as readiness inputs only, not as
  campaign behavior or implementation authority.

If any gate is missing, stale, empty, ambiguous, or context-only, the
recommendation must remain one of:

- `continue_trusted_loop_maturity`;
- `operator_review_required`;
- `no_eligible_work_remains`.

## Evidence Sources

| Source | Use in return criteria |
| --- | --- |
| `docs/governance/ade_qre_015c_qre_feature_track_return_readiness_check.md` | Establishes that return was previously rejected because high-priority evidence gaps remained open. |
| `docs/governance/ade_qre_016a_evidence_gap_closure_inventory.md` | Maps prioritized gaps to closure candidates and preserves open evidence status. |
| `docs/governance/ade_qre_016b_operator_trust_criteria.md` | Defines measurable trust levels used by `RTF-05`. |
| `reporting/trusted_loop_missing_evidence_fail_closed.py` and tests | Provide current read-only fail-closed coverage used by `RTF-06`. |
| `reporting/trusted_loop_consistency_audit.py` and tests | Provide current cross-surface consistency evidence used by `RTF-06` and `RTF-07`. |
| `docs/governance/ade_qre_016e_trusted_loop_operator_summary_v2.md` | States the current operator-facing ready, blocked, deferred, not-trusted, and no-synthesis reasons. |

## Non-Return Conditions

The following conditions are explicit blockers, not warnings:

- reason-record evidence remains absent or too thin;
- KPI values remain incomplete without operator-approved substitute criteria;
- routing or sampling evidence remains empty or non-ready;
- a surface is only scaffold or working read-only capability;
- missing evidence is interpreted as readiness;
- retrieval, diagnostics, or source quality is used as authority;
- throughput is used to lower evidence standards;
- source quality is treated as alpha;
- return requires strategy synthesis, runtime Addendum activation, routing
  implementation, campaign mutation, approval mutation, dashboard mutation,
  autonomous authority expansion, external data adapters, new datafeeds,
  shadow, paper, live, broker, risk, or execution behavior.

## Current Recommendation

Current return criteria status: `not_met`.

The next decision item, `ADE-QRE-016G`, may use these criteria to select one
allowed next-sprint recommendation. This document does not make that selection
and does not start any selected direction.

## Safety Invariants

- Strategy synthesis remains blocked.
- Addendum 1, Addendum 2, Addendum 3, and Addendum 4 remain reference-only and
  inactive at runtime.
- Addendum 4 remains `DEFERRED / REFERENCE-ONLY`.
- Shadow, paper, live, broker, risk, and execution paths remain inactive.
- `registry.py`, strategy implementations, frozen research outputs, approval
  mutation, dashboard mutation routes, routing implementation, campaign
  mutation, external data adapters, and new datafeeds remain out of scope.
