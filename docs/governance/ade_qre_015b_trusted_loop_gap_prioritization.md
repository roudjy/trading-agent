# ADE-QRE-015B - Trusted-Loop Gap Prioritization

> Status: read-only prioritization record.
>
> Scope: governance documentation only. This record ranks gaps surfaced by
> `ADE-QRE-015A`; it does not activate roadmap work, strategy synthesis,
> Addendum runtime, routing, sampling, campaign mutation, shadow, paper, live,
> broker, risk, execution, approval mutation, dashboard mutation, or frozen
> contract changes.

## Deterministic Ranking Method

Each gap is scored on the same four fields:

| Field | Score meaning |
| --- | --- |
| Operator value | 1 low, 2 medium, 3 high value for deciding the next safe queue direction. |
| Safety value | 1 low, 2 medium, 3 high value for preventing unsupported authority or readiness claims. |
| Evidence impact | 1 low, 2 medium, 3 high impact on making future recommendations evidence-backed. |
| Implementation risk | 1 low, 2 medium, 3 high risk if addressed later. Lower risk ranks higher. |

Priority score is computed as:

```text
operator_value + safety_value + evidence_impact + (4 - implementation_risk)
```

Ties are ordered by stable gap id. Priority bands are:

| Band | Score |
| --- | --- |
| High | 10-12 |
| Medium | 7-9 |
| Low | 4-6 |

## Ranked Gaps

| Rank | Gap id | Gap | Evidence basis | Scores | Priority | Why this rank |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `GAP-015B-01` | Reason-record evidence is absent or too thin. | `ADE-QRE-015A` records 014O evidence of `record_count=0` and `records_with_evidence_refs=0`. | operator 3, safety 3, evidence 3, risk 2, total 11 | High | Without reason records, later recommendations risk becoming unsupported trust claims. |
| 2 | `GAP-015B-02` | Research-quality KPI values are not promotion-ready. | `ADE-QRE-015A` records 014O evidence that 0 of 7 research-quality KPI values were complete. | operator 3, safety 3, evidence 3, risk 2, total 11 | High | KPI doctrine exists, but promotion or return-readiness claims need numeric evidence or explicit substitute criteria. |
| 3 | `GAP-015B-03` | Routing readiness remains non-ready. | `ADE-QRE-015A` records routing `final_recommendation=nothing_ready`, `total=0`, and readiness score 0.0. | operator 3, safety 3, evidence 2, risk 2, total 10 | High | Return to v3.15.16 Intelligent Routing would be unsafe if current routing evidence is treated as readiness. |
| 4 | `GAP-015B-04` | Sampling readiness remains non-ready. | `ADE-QRE-015A` records sampling `final_recommendation=nothing_ready`, `total=0`, and readiness score 0.0. | operator 3, safety 3, evidence 2, risk 2, total 10 | High | Sampling gaps can invalidate feature-track return even if routing documentation is improved. |
| 5 | `GAP-015B-05` | Trust classifications are uneven across scaffold, working capability, and narrow queue-decision trust. | `ADE-QRE-015A` classifies most 014B-O outputs as working read-only capabilities and only 014N/014O as narrow operator-trusted queue-decision surfaces. | operator 2, safety 3, evidence 2, risk 1, total 10 | High | 015C must not collapse read-only working capability into broader runtime or feature-track trust. |
| 6 | `GAP-015B-06` | Failure-action mapping has no actionable failure population. | `ADE-QRE-015A` records `total_failures=0` and `actionable_failure_count=0`. | operator 2, safety 3, evidence 2, risk 2, total 9 | Medium | The surface is visible, but current evidence cannot prove reroute/action usefulness. |
| 7 | `GAP-015B-07` | Historical queue evidence still contains non-current audit warnings. | `reporting.ade_queue_status_self_audit --no-write` reports missing done-evidence warnings for historical items `ADE-QRE-007`, `ADE-QRE-008`, and `ADE-QRE-014A`. | operator 1, safety 2, evidence 1, risk 1, total 7 | Medium | These warnings do not block 015B because the next eligible item is deterministic, but they limit blanket claims about historical audit completeness. |

## Operator-Visible Priority Groups

High-priority gaps:

- reason-record evidence density;
- research-quality KPI numeric readiness;
- routing readiness;
- sampling readiness;
- trust-boundary precision.

Medium-priority gaps:

- failure-action population/actionability;
- historical audit warning cleanup, only if a later item explicitly scopes it.

Low-priority gaps:

- none identified from `ADE-QRE-015A`.

## Consequence for ADE-QRE-015C

`ADE-QRE-015C` should evaluate return readiness against the high-priority gaps
first. The prioritization does not force a branch outcome. It only says that a
safe readiness recommendation must explain whether these high-priority gaps are
acceptable, deferred, or blocking.

This record does not start QRE Feature Build Track implementation, does not
implement v3.15.16 Intelligent Routing, and does not select any branch item
under `ADE-QRE-015D` through `ADE-QRE-015G`.

## Rejected Actions

This prioritization does not:

- activate automatic roadmap work;
- enable strategy synthesis;
- mutate routing, sampling, campaigns, approvals, or dashboards;
- use retrieval as authority;
- treat source quality as alpha;
- lower evidence standards because a gap has high operator value;
- touch frozen research outputs, `registry.py`, strategy implementations, or
  execution-sensitive paths.

