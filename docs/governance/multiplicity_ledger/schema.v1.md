# Multiplicity Ledger — Schema v1

> Module: `reporting.multiplicity_ledger` (planned).
> Module version: pinned at implementation PR.
> Schema version: `1`.
> Artifact path: `logs/multiplicity_ledger/v1.jsonl`
> Manifest path: `logs/multiplicity_ledger/manifest.v1.json`
> Doctrine: [`../multiplicity_ledger.md`](../multiplicity_ledger.md).

## Record shape (JSONL)

Each line is exactly one JSON object with these fields. Field
order is alphabetical for byte-identical serialisation.

| field | type | values | notes |
|---|---|---|---|
| `decision_kind` | enum | see below | what the event resolved the candidate to |
| `event_id` | string | `"mle_<hex16>"` | deterministic; ML-I4 |
| `event_kind` | enum | see below | what kind of effective test |
| `inputs_digest` | string | `sha256` hex (≤ 64 chars) | hash of relevant inputs |
| `notes` | string | ≤ 200 chars | short free text; no PII |
| `outputs_digest` | string | `sha256` hex (≤ 64 chars) | hash of relevant outputs |
| `schema_version` | int | `1` | constant |
| `scope` | string | `candidate_id` / `seed_id` / `family_id` (≤ 64 chars) | what the event counted against |
| `ts_utc` | string | RFC3339 UTC, seconds resolution | ML-I3 monotonic in-process |

Total serialised size cap per record: **2 KB**. Records that
exceed the cap are rejected by the writer (ML-I5).

## `event_kind` closed vocabulary

The writer rejects any value not in this list (ML-I6).

```text
diagnostic_evaluation      # diagnostic invocation that influenced
                            # a candidate's status
hypothesis_emission        # Hypothesis Discovery emitted a seed
candidate_scoring          # candidate scoring event that combined
                            # multiple inputs
oos_evaluation             # out-of-sample evaluation
null_model_evaluation      # null-model challenge evaluation
robustness_check           # multi-asset / multi-timeframe /
                            # multi-regime check
```

## `decision_kind` closed vocabulary

The writer rejects any value not in this list (ML-I7).

```text
filtered     # the event filtered the candidate (rejection)
kept         # the event kept the candidate (no demote)
null         # the event resolved to "indistinguishable from null"
undecided    # the event neither kept nor filtered (incomplete)
```

## `event_id` derivation

```text
event_id = "mle_" + sha256(
    event_kind || 0x1F || scope || 0x1F || inputs_digest
).hexdigest()[:16]
```

Two events with the same `(event_kind, scope, inputs_digest)`
produce the same `event_id` and are idempotent on append
(ML-I2).

## `inputs_digest` derivation

The implementation PR pins the exact serialisation order. The
canonical form (planned):

```text
inputs_digest = sha256(
    canonical_json({
        "data_window":       {"start": <iso>, "end": <iso>},
        "diagnostic_name":   <str>,
        "diagnostic_params": <sorted dict>,
        "candidate_id":      <str or null>,
        "seed_id":           <str or null>,
        "family_id":         <str or null>,
        "regime":            <str or null>
    })
).hexdigest()
```

`canonical_json` is JSON with sorted keys, no whitespace, UTF-8.
The implementation PR pins this helper and its test.

## `outputs_digest` derivation

Mirrors `inputs_digest` over:

```text
outputs_digest = sha256(
    canonical_json({
        "decision":         <decision_kind>,
        "score":            <float or null>,
        "score_units":      <str or null>,
        "n_eff_at_decision": <int or null>
    })
).hexdigest()
```

## Manifest record shape

`logs/multiplicity_ledger/manifest.v1.json`:

| field | type | notes |
|---|---|---|
| `schema_version` | int | `1` |
| `module_version` | string | pinned at impl PR |
| `generated_at_utc` | string | RFC3339 UTC, seconds resolution |
| `events_total` | int | count of records in `v1.jsonl` |
| `events_by_kind` | object | one int per `event_kind` |
| `first_event_ts_utc` | string \| null | RFC3339 UTC of first event |
| `last_event_ts_utc` | string \| null | RFC3339 UTC of last event |
| `last_event_id` | string \| null | `event_id` of the most recent event |
| `note` | string | one of `"no_events"`, `"events_present"` |

The manifest is rebuilt by the writer on every successful
append. It is **derived** and is not the canonical source of
truth; the JSONL is.

## Validation summary

Every record must satisfy:

- All fields present, no extras.
- `event_kind` in closed vocab.
- `decision_kind` in closed vocab.
- `scope` ≤ 64 chars, non-empty.
- `inputs_digest` and `outputs_digest` are 64-char hex strings.
- `event_id` matches the derivation formula.
- `ts_utc` parses as RFC3339 UTC.
- `notes` ≤ 200 chars.
- Total serialised record ≤ 2 KB.
- No secret-keyword pattern matches in any field
  (`API_KEY`, `SECRET`, `TOKEN`, etc.; full list pinned in
  the implementation PR).

Any failure raises `ValueError` at append time and produces a
deterministic error string for the operator.

## Reserved fields (v2)

The schema is `v1`. Future schema versions may add (never
remove) fields. v2 candidates under consideration (non-binding):

- `family_provenance`: pointer to the parent family for
  family-level aggregation.
- `regime_window_id`: a stable id for the regime the event was
  evaluated in.
- `corrected_score`: the deflation-adjusted score, written by
  the scoring layer on the same event.

A schema-version bump is governance-gated by an operator PR.

## Update history

- 2026-05-21: initial version (S4 detail spec).
