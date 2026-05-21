# Routing / Sampling / Scoring Reason Records — doctrine

> **Status:** specification (S9 of the Research-Quality Hardening
> Sprint declared by ADR-018 draft).
>
> **Authority:** governance spec. Declares the unified
> append-only reason-record family that makes routing, sampling,
> and scoring decisions inspectable, auditable, and replayable.
> Does not implement runtime code; the implementation lands in
> later scoped PRs (one per decision_kind family).
>
> **Schema:** [`reason_records/schema.v1.md`](reason_records/schema.v1.md).
>
> **Cross-refs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
> §10,
> [`multiplicity_ledger.md`](multiplicity_ledger.md),
> [`paper_readiness_checklist.md`](paper_readiness_checklist.md),
> [`docs/adr/ADR-019-hypothesis-discovery-doctrine.md`](../adr/ADR-019-hypothesis-discovery-doctrine.md).

## 1. Purpose

Routing, sampling, and scoring are three places where hidden
authority can grow if decisions are not recorded. The roadmap
v6 doctrine explicitly forbids hidden ranking authority and
hidden routing authority
([`roadmap_scope_status.md`](roadmap_scope_status.md) §5.7
"Permanent denials"), but doctrine alone does not enforce
inspection.

Reason records are the enforcement mechanism. Every routing,
sampling, and scoring decision emits one record. The record:

- names the decision;
- names the inputs that produced it;
- names the deterministic reason codes;
- is append-only;
- carries no hidden state.

If a decision is not recorded, the decision did not happen — the
implementation PR's tests pin this invariant.

## 2. Scope

The doctrine applies to three decision families:

| Family | Decision-maker | Examples |
|---|---|---|
| **routing** | v3.15.16 minimal routing slice (planned) | prioritise campaign C; suppress dead-zone D; defer C until D completes |
| **sampling** | v3.15.17 minimal sampling slice (planned) | stratify by regime; sample null baseline window W; exclude region R |
| **scoring** | v3.15.19 minimal Hypothesis Discovery slice (planned) + the three active diagnostics | keep candidate C; filter C by null model; filter C by tail; filter C by cost gate |

The doctrine does **not** apply to:

- Data fetches (no decision; use source manifests).
- Multiplicity-ledger appends (use the ledger directly).
- Frozen-contract reads (no decision).
- Funnel-policy promotion decisions (these have their own
  evidence-ledger discipline in
  `research/campaign_funnel_policy.py`).

## 3. Authority

Reason records are **lineage**, not authority.

- They do not change the routing / sampling / scoring decision
  itself; they record it.
- They do not promote, demote, or rank candidates.
- They do not feed any live / paper / shadow / broker /
  execution surface (ADR-020 §2.5).
- They do not mutate `paper_readiness_latest.v1.json`,
  `research_latest.json`, or `strategy_matrix.csv`.

Write authority is restricted to the routing / sampling /
scoring runtime modules. ADE / planner / product-owner / human
operator do **not** write to them.

Read authority is open: the candidate-quality dashboard
([`candidate_quality_dashboard.md`](candidate_quality_dashboard.md)),
the paper-readiness checklist
([`paper_readiness_checklist.md`](paper_readiness_checklist.md)),
and operators consume the records freely.

## 4. Unified schema

The three families share **one** schema with a `decision_kind`
discriminator. This keeps spec surface small and operator
cognitive load low (one record shape instead of three).

The full schema is in
[`reason_records/schema.v1.md`](reason_records/schema.v1.md).
Key shape:

```json
{
  "schema_version": 1,
  "record_id": "rr_<hex16>",
  "ts_utc": "<rfc3339-utc-seconds>",
  "decision_kind": "routing|sampling|scoring",
  "subject_id": "<campaign_id|sampling_plan_id|candidate_id>",
  "inputs_digest": "<sha256-hex>",
  "decision": "<closed-vocab-per-kind>",
  "reason_codes": ["<closed-vocab-tags>"],
  "reason_text": "<short free text, capped at 300 chars>"
}
```

## 5. Closed `decision` vocabularies

Each decision-kind family pins its own closed `decision` vocab.

### 5.1 Routing decisions

```text
prioritize          # raise the priority of this subject
dead_zone_suppress  # the routing layer detected a dead zone and suppressed
defer               # delay until a blocker clears
reject              # do not route at all
```

### 5.2 Sampling decisions

```text
stratify            # apply stratification
null_baseline      # sample as a null/control region
exclude_region     # exclude a region (insufficient data, ambiguity, etc.)
downsample         # reduce sampling density
upsample           # increase sampling density
```

### 5.3 Scoring decisions

```text
keep               # the candidate survives this scoring event
filter_tail        # filtered by tail/asymmetry diagnostic
filter_entropy     # filtered by entropy/structure diagnostic
filter_null        # filtered by null-model diagnostic
filter_cost        # filtered by the cost-adjusted promotion gate
undecided          # incomplete data; cannot decide yet
```

The writer rejects any value outside these closed lists.

## 6. Closed `reason_codes` vocabularies

Each `decision_kind` × `decision` combination may carry a
bounded list of structured reason codes. The implementation PR
pins the full enumeration; this spec names the canonical anchor
tags so downstream consumers can plan against them.

Anchor tags (binding; the implementation PR adds tags inside
this set, never outside it):

- `routing` × any decision: `info_gain_high`, `info_gain_low`,
  `dead_zone_dwell_exceeded`, `dependency_unmet`,
  `multiplicity_budget_exceeded`, `operator_directive`.
- `sampling` × any decision: `coverage_imbalance`,
  `regime_mismatch`, `null_baseline_required`,
  `multiplicity_budget_remaining`, `operator_directive`.
- `scoring` × any decision: `null_p_value_above_threshold`,
  `null_p_value_below_threshold`, `tail_fragility_high`,
  `tail_fragility_low`, `entropy_regime_compatible`,
  `entropy_regime_incompatible`, `cost_gate_pass`,
  `cost_gate_fail`, `dsr_threshold_pass`, `dsr_threshold_fail`,
  `operator_directive`.

`operator_directive` is the explicit "an operator forced this
decision via a one-shot governance lever" tag. The
implementation PR pins how this lever is recorded.

## 7. Invariants

| ID | Invariant | Enforcement |
|---|---|---|
| RR-I1 | Append-only. No UPDATE, no DELETE. | Atomic-write helper rejects any non-append; tests pin. |
| RR-I2 | Idempotent on `record_id`. A second write with the same `record_id` is a no-op. | Writer reads existing ledger and skips appends. |
| RR-I3 | Monotonic in-process `ts_utc`. | Writer asserts. |
| RR-I4 | Deterministic `record_id` over `(decision_kind, subject_id, inputs_digest)`. | Pure helper; unit-tested. |
| RR-I5 | Closed `decision_kind`, closed `decision`, closed `reason_codes` set. | Writer validates. |
| RR-I6 | One record per decision. If no record is written, the decision did not happen. | Routing / sampling / scoring layers' tests pin this: every decision path must call the writer. |
| RR-I7 | Reader purity. No IO side effects, no network, no `subprocess`. | Source-text test. |
| RR-I8 | No frozen-contract mutation. | Atomic-write allowlist; tests pin write paths. |
| RR-I9 | No execution-side feed. The modules import nothing from `agent/execution/`, `automation/`, `broker/`, `live/`, `paper/`, `shadow/`, `trading/`, `execution/`. | Source-text test. |
| RR-I10 | Bounded record size (≤ 2 KB serialised). | Writer rejects oversize. |

## 8. Storage layout

Each decision-kind family has its own append-only JSONL plus a
manifest. Operators read them through a single helper module
that fuses the three families by `ts_utc`.

| Path | Owner | Content |
|---|---|---|
| `logs/reason_records/routing_v1.jsonl` | routing layer | routing decisions |
| `logs/reason_records/sampling_v1.jsonl` | sampling layer | sampling decisions |
| `logs/reason_records/scoring_v1.jsonl` | scoring layer | scoring decisions |
| `logs/reason_records/manifest.v1.json` | reader helper | rolled-up counts per family + per decision |

Atomic-write allowlist substring: `logs/reason_records/`.

## 9. Reader API (planned)

```python
# reporting/reason_records.py (planned)

def append(record: dict) -> None:
    """Atomic append of one validated record. Idempotent.

    Raises ValueError on schema violation, oversize record, or
    forbidden write target.
    """

def read_kind(decision_kind: str, subject_id: str | None = None) -> list[dict]:
    """Pure read. Returns records for the named decision_kind,
    optionally filtered by subject_id."""

def collect_manifest() -> dict:
    """Stat-summary of the three reason-record JSONLs."""

def fused_for_subject(subject_id: str) -> list[dict]:
    """Pure read. Returns the time-ordered union of records
    that reference subject_id across all three families."""
```

The implementation PRs (one per family, plus one for the reader)
pin this API.

## 10. CLI (planned)

```text
python -m reporting.reason_records --status
python -m reporting.reason_records --subject <id>
python -m reporting.reason_records --kind routing|sampling|scoring
```

There is no execute-safe mode for the CLI; the CLI cannot write.

## 11. Test plan (for the implementation PRs)

Per family (routing, sampling, scoring) + one fused-reader PR:

- Append-only invariant test (RR-I1).
- Idempotence test (RR-I2).
- Monotonicity test (RR-I3).
- Determinism test (RR-I4).
- Closed-vocab test for `decision_kind`, `decision`, and the
  family-specific `reason_codes` (RR-I5).
- Decision-coverage test: every code path in the routing /
  sampling / scoring layer that makes a decision is covered by
  a test that asserts a matching reason record was appended
  (RR-I6).
- Reader-purity source-text test (RR-I7).
- Atomic-write allowlist test (RR-I8).
- Execution-import-deny source-text test (RR-I9).
- Size-cap test (RR-I10).

## 12. Operator workflow

1. Operator inspects a candidate's lineage via the
   candidate-quality dashboard
   ([`candidate_quality_dashboard.md`](candidate_quality_dashboard.md)).
2. The dashboard surfaces the fused reason records for the
   candidate's subject_id.
3. Operator can answer "why was C suppressed in routing? why
   was C filtered by scoring? what entropy code triggered?"
   without reading source code.
4. If the operator disagrees with a decision, the operator can
   open a governance PR that explicitly overrides via an
   `operator_directive` reason code. The override is itself a
   reason record.

## 13. What this doctrine is NOT

- Not a promotion path. Funnel policy is.
- Not a multiplicity ledger
  (see [`multiplicity_ledger.md`](multiplicity_ledger.md);
  multiplicity events are a separate ledger).
- Not a log file. Reason records are structured records with
  closed vocab; plain-text logs are not a substitute.
- Not an audit chain in the AGENTS.md sense; the audit chain
  (`docs/governance/audit_chain.md`) is for agent activity, not
  research decisions.

## 14. Update history

- 2026-05-21: initial version (Research-Quality Hardening Sprint,
  S9 detail spec). Expands
  [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
  §10.
