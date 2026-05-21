# Reason Records — Schema v1

> Module: `reporting.reason_records` (planned).
> Module version: pinned at implementation PR.
> Schema version: `1`.
> Artifact paths:
> - `logs/reason_records/routing_v1.jsonl`
> - `logs/reason_records/sampling_v1.jsonl`
> - `logs/reason_records/scoring_v1.jsonl`
> Manifest path: `logs/reason_records/manifest.v1.json`
> Doctrine: [`../reason_records.md`](../reason_records.md).

## Record shape (JSONL)

Each line is exactly one JSON object with these fields. Field
order is alphabetical for byte-identical serialisation.

| field | type | values | notes |
|---|---|---|---|
| `decision` | enum | closed per `decision_kind` — see §2 | what the layer decided |
| `decision_kind` | enum | `routing` / `sampling` / `scoring` | which family |
| `inputs_digest` | string | `sha256` hex (≤ 64 chars) | hash of inputs |
| `reason_codes` | array | list of closed-vocab tags — see §3 | structured reasons |
| `reason_text` | string | ≤ 300 chars | short free text; no PII |
| `record_id` | string | `"rr_<hex16>"` | deterministic; RR-I4 |
| `schema_version` | int | `1` | constant |
| `subject_id` | string | `campaign_id` / `sampling_plan_id` / `candidate_id` (≤ 64 chars) | what the decision was about |
| `ts_utc` | string | RFC3339 UTC, seconds resolution | RR-I3 monotonic in-process |

Total serialised size cap per record: **2 KB**. Records that
exceed the cap are rejected by the writer (RR-I10).

## §1 `decision_kind`

Closed enum (RR-I5):

```text
routing
sampling
scoring
```

The writer rejects any value not in this list. Each
`decision_kind` is written to its own JSONL file (so consumers
that only care about one family do not need to filter).

## §2 `decision` closed vocabularies

### §2.1 routing

```text
prioritize
dead_zone_suppress
defer
reject
```

### §2.2 sampling

```text
stratify
null_baseline
exclude_region
downsample
upsample
```

### §2.3 scoring

```text
keep
filter_tail
filter_entropy
filter_null
filter_cost
undecided
```

The writer rejects any combination of
`(decision_kind, decision)` that is not in the table above.

## §3 `reason_codes` closed vocabularies

Anchor tags (binding minimum set; implementation PRs may add
tags inside the family-scoped set, never outside it):

### §3.1 routing

```text
info_gain_high
info_gain_low
dead_zone_dwell_exceeded
dependency_unmet
multiplicity_budget_exceeded
operator_directive
```

### §3.2 sampling

```text
coverage_imbalance
regime_mismatch
null_baseline_required
multiplicity_budget_remaining
operator_directive
```

### §3.3 scoring

```text
null_p_value_above_threshold
null_p_value_below_threshold
tail_fragility_high
tail_fragility_low
entropy_regime_compatible
entropy_regime_incompatible
cost_gate_pass
cost_gate_fail
dsr_threshold_pass
dsr_threshold_fail
operator_directive
```

The writer rejects any reason code not in the family-scoped
list. The list is finite; growth requires an operator-approved
governance PR.

## §4 `record_id` derivation

```text
record_id = "rr_" + sha256(
    decision_kind || 0x1F || subject_id || 0x1F || inputs_digest
).hexdigest()[:16]
```

Two records with the same
`(decision_kind, subject_id, inputs_digest)` produce the same
`record_id` and are idempotent on append (RR-I2).

## §5 `inputs_digest` derivation

The implementation PR pins the exact serialisation order. The
canonical form (planned):

```text
inputs_digest = sha256(
    canonical_json({
        "decision_kind":     <str>,
        "decision":          <str>,
        "subject_id":        <str>,
        "subject_kind":      <"campaign" | "sampling_plan" | "candidate">,
        "data_window":       {"start": <iso>, "end": <iso>} | null,
        "diagnostic_inputs": <sorted dict> | null,
        "cost_inputs":       <sorted dict> | null,
        "multiplicity_n_eff":<int> | null,
        "operator_directive_ref": <str> | null
    })
).hexdigest()
```

`canonical_json` is JSON with sorted keys, no whitespace, UTF-8.
The implementation PR pins this helper and its test.

## §6 Manifest record shape

`logs/reason_records/manifest.v1.json`:

| field | type | notes |
|---|---|---|
| `schema_version` | int | `1` |
| `module_version` | string | pinned at impl PR |
| `generated_at_utc` | string | RFC3339 UTC, seconds resolution |
| `total_records` | int | sum across the three JSONLs |
| `by_kind` | object | one int per `decision_kind` |
| `by_decision` | object | nested counts `{decision_kind: {decision: int}}` |
| `by_subject_id_top` | object | top-N subject_id counts (N pinned, planned: 16) |
| `first_record_ts_utc` | string \| null | RFC3339 UTC of first record across families |
| `last_record_ts_utc` | string \| null | RFC3339 UTC of most recent record |
| `note` | string | one of `"no_records"`, `"records_present"` |

The manifest is rebuilt by the writer on every successful
append. It is **derived** and is not the canonical source of
truth.

## §7 Validation summary

Every record must satisfy:

- All fields present, no extras.
- `decision_kind` in §1 closed vocab.
- `decision` in the family-scoped closed vocab from §2.
- Every entry in `reason_codes` in the family-scoped closed
  vocab from §3.
- `subject_id` ≤ 64 chars, non-empty.
- `inputs_digest` is a 64-char hex string.
- `record_id` matches the derivation formula in §4.
- `ts_utc` parses as RFC3339 UTC.
- `reason_text` ≤ 300 chars, no PII patterns.
- Total serialised record ≤ 2 KB.
- The (`record_id`, `ts_utc`) pair is unique within the JSONL
  (idempotence guarantee, RR-I2).

Any failure raises `ValueError` at append time with a
deterministic error string.

## §8 Reserved fields (v2)

The schema is `v1`. Future schema versions may add (never
remove) fields. v2 candidates under consideration:

- `parent_record_id`: pointer to a previous decision this one
  reverses or refines.
- `operator_handle`: when `operator_directive` is in
  `reason_codes`, name the operator.
- `multiplicity_ledger_event_id`: cross-link to the matching
  multiplicity-ledger event (when one exists).

A schema-version bump is governance-gated by an operator PR.

## Update history

- 2026-05-21: initial version (S9 detail spec).
