# Global Multiplicity Ledger — specification

> **Status:** specification (S4 of the Research-Quality Hardening
> Sprint declared by ADR-018 draft).
>
> **Authority:** governance spec. Declares *what* the multiplicity
> ledger is, *how* it is consumed, and *what invariants it must
> hold*. Does not implement runtime code; the implementation lands
> in a later scoped PR.
>
> **Schema:** [`multiplicity_ledger/schema.v1.md`](multiplicity_ledger/schema.v1.md).
>
> **Cross-refs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
> §6,
> [`research_quality_kpis.md`](research_quality_kpis.md),
> [`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](../adr/_drafts/ADR-018-roadmap-execution-reset.md),
> [`docs/adr/_drafts/ADR-019-hypothesis-discovery-doctrine.md`](../adr/_drafts/ADR-019-hypothesis-discovery-doctrine.md).

## 1. Purpose

Without a global multiplicity ledger:

- Deflated Sharpe corrections operate on a constant `N` (or no `N`
  at all), which is wrong as soon as more than one hypothesis is
  tested per release.
- The addendums multiply tests geometrically (14 diagnostic
  families × N hypotheses × M assets × K timeframes × regimes ×
  null variants); without counting, false discovery is
  uncontrolled.
- KPI `OOS-DSR` and KPI `MASQ`
  ([`research_quality_kpis.md`](research_quality_kpis.md) §3)
  cannot be computed faithfully.

The multiplicity ledger is an append-only event log that counts
every effective hypothesis test. It is the canonical source of
the **effective number of trials** `N_eff(c)` used by Deflated
Sharpe and by every multiplicity-aware downstream KPI.

## 2. Scope

The ledger records:

- diagnostic evaluations whose output influences a candidate's
  status (kept / filtered / undecided);
- hypothesis seed emissions from Hypothesis Discovery;
- candidate scoring events that combine multiple inputs;
- out-of-sample (OOS) evaluation events;
- null-model evaluation events;
- robustness check events (multi-asset / multi-timeframe /
  multi-regime).

It does **not** record:

- raw price reads or data fetches;
- routing decisions that did not produce a scoring event
  (use [`reason_records.md`](reason_records.md) instead);
- sampling decisions that did not produce a scoring event
  (use [`reason_records.md`](reason_records.md) instead);
- diagnostic invocations that did not influence any candidate's
  status (a diagnostic that ran and produced "n/a" is not a
  test for multiplicity purposes; the ledger records only
  *effective* tests).

## 3. Authority

The ledger is **lineage**, not authority.

- It does **not** promote, demote, or rank candidates.
- It does **not** select hypotheses for evaluation.
- It does **not** alter routing or sampling decisions.
- It does **not** feed any live / paper / shadow / broker /
  execution surface. Per ADR-020 draft, this is doctrinal.

Write authority is restricted to the diagnostic / scoring /
evaluation runtime layer in `research/` and `reporting/`. ADE /
planner / product-owner / human_operator do **not** write to it.

Read authority is open: every downstream consumer that needs
`N_eff(c)` reads the ledger via a pure, side-effect-free reader.

## 4. Invariants

The ledger satisfies these invariants. The implementation PR
must include tests that pin each invariant.

| ID | Invariant | Enforcement |
|---|---|---|
| ML-I1 | **Append-only.** No UPDATE, no DELETE, no in-place edit, no reordering of existing records. | Writer rejects any operation that is not an append. Atomic-write helper that writes a temp file and renames; refuses any write that does not preserve the previous bytes. |
| ML-I2 | **Idempotent on `event_id`.** A second write with the same `event_id` is a no-op (the second event is not appended). | Writer reads the existing ledger and skips appends whose `event_id` already exists. |
| ML-I3 | **Monotonic timestamps.** Within a single process, `ts_utc` is non-decreasing. Across processes, ordering is by `(ts_utc, event_id)` lex. | Writer asserts `ts_utc >= last_ts_utc` within process. |
| ML-I4 | **Deterministic `event_id`.** `event_id` is a deterministic hash over `(event_kind, scope, inputs_digest)`. Two runs on the same inputs produce byte-identical IDs. | Pure helper; unit-tested. |
| ML-I5 | **Bounded record size.** Each record fits within a soft cap (planned: 2 KB serialised) so the ledger remains operator-readable. | Writer rejects records exceeding the cap. |
| ML-I6 | **Closed `event_kind` vocabulary.** Only the six values declared in [`schema.v1.md`](multiplicity_ledger/schema.v1.md) are accepted. | Writer validates. |
| ML-I7 | **Closed `decision_kind` vocabulary.** Only the four values declared in [`schema.v1.md`](multiplicity_ledger/schema.v1.md) are accepted. | Writer validates. |
| ML-I8 | **No PII / secrets.** Records contain no API keys, tokens, account IDs, or user-identifiable strings. | Writer rejects records whose fields match the secret-keyword denylist. |
| ML-I9 | **Reader purity.** The canonical reader has no IO side effects, no network, no `subprocess`, no `gh`, no `git`. | Source-text test pins. |
| ML-I10 | **No frozen-contract mutation.** The ledger never writes to `research/research_latest.json` or `research/strategy_matrix.csv`. | Atomic-write allowlist; tests pin the write path prefix. |

## 5. Effective number of trials `N_eff(c)`

For a survivor `c`:

```text
N_eff(c) = count(
    event_kind in {candidate_scoring, oos_evaluation,
                   null_model_evaluation, robustness_check}
    AND scope in {c, c's parent family}
)
```

Diagnostic evaluations are counted at the family level (so that
when a diagnostic challenges many candidates in a family, the
shared challenge is not multiply-counted at the candidate level
but is counted at the family level). The exact aggregation rule
is pinned by the implementation PR's unit tests.

## 6. Deflated Sharpe consumption

Deflated Sharpe `DSR(c)` is computed as:

```text
DSR(c) = deflate(SR(c), N_eff(c), other params)
```

where `deflate(...)` is the standard Bailey-Lopez de Prado
correction (formula pinned in the implementation PR). The
ledger contributes `N_eff(c)` only; SR and other parameters
come from the candidate's evidence ledger.

A reader function `N_eff(scope: str) -> int` is the only public
API exposed by the multiplicity-ledger module to downstream
scoring code.

## 7. Storage layout

- Path: `logs/multiplicity_ledger/v1.jsonl` (append-only).
- Companion: `logs/multiplicity_ledger/manifest.v1.json` (records
  total events, first/last `ts_utc`, schema version; rebuilt by
  the writer on every append; idempotent).
- Atomic-write allowlist substring: `logs/multiplicity_ledger/`.
  Writes outside this prefix raise `ValueError`. (Mirrors the
  pattern used by `reporting/roadmap_priority.py`.)
- The directory is created by the writer on first use; the
  repo-committed file is the empty manifest.
- The ledger is **not** a frozen v1 artifact. It is operationally
  read-write (append-only) and is not pinned by determinism
  tests except for the closed schema.

## 8. Reader API (planned)

```python
# reporting/multiplicity_ledger.py (planned, not in this PR)

def N_eff(scope: str, ledger_path: Path | None = None) -> int:
    """Return the effective number of trials counted against `scope`.

    Pure, deterministic, side-effect-free. Reads only.
    """

def append(event: dict) -> None:
    """Atomic append of one validated event. Idempotent on event_id.

    Raises ValueError on schema violation, oversize record, or
    forbidden write target.
    """

def collect_manifest(ledger_path: Path | None = None) -> dict:
    """Return a stat-summary of the ledger (total events, kinds,
    first/last ts). Pure read."""
```

The implementation PR pins this API.

## 9. CLI (planned)

```text
# Dry-run report (no append):
python -m reporting.multiplicity_ledger --status

# Append one event from a JSON file (operator/runtime use):
python -m reporting.multiplicity_ledger --append path/to/event.json
```

There is no execute-safe mode for the CLI: appends require an
explicit `--append` flag, the CLI rejects anything else. Mirrors
the `roadmap_priority` discipline (`safe_to_execute` always
`false`).

## 10. Test plan (for the implementation PR)

- Property test: ML-I1 append-only (random fuzz of operations;
  every non-append is rejected).
- Idempotence test: ML-I2 (same `event_id` appended twice is a
  no-op; total count unchanged).
- Monotonicity test: ML-I3 (in-process `ts_utc` never decreases).
- Determinism test: ML-I4 (same inputs → same `event_id`).
- Size-cap test: ML-I5 (oversized record raises `ValueError`).
- Closed-vocab tests: ML-I6, ML-I7 (every unknown enum value is
  rejected).
- Secret-deny test: ML-I8 (records containing secret-keyword
  patterns are rejected).
- Reader-purity source-text test: ML-I9 (no `subprocess`, no
  `socket`, no `requests`, no `gh`, no `git`).
- Atomic-write allowlist test: ML-I10 (writes outside
  `logs/multiplicity_ledger/` raise `ValueError`).
- KPI-consistency test: synthetic ledger inputs produce the
  expected `N_eff(c)` for the KPIs `OOS-DSR` and `MASQ`.

## 11. Out of scope (for the spec)

- Distributed coordination across processes / hosts. The ledger
  is single-host append-only.
- Compression / archival. The implementation PR may add a
  compaction tool later; this spec does not require it.
- Visualisation. The candidate-quality dashboard
  ([`candidate_quality_dashboard.md`](candidate_quality_dashboard.md))
  consumes the ledger via the manifest only; it does not render
  raw records.

## 12. Update history

- 2026-05-21: initial version (Research-Quality Hardening Sprint,
  S4 detail spec). Expands
  [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
  §6 into a standalone specification with formal invariants and
  test plan.
