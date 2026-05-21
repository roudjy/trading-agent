# Paper-Readiness Checklist — specification

> **Status:** specification (S8 of the Research-Quality Hardening
> Sprint declared by ADR-018 draft).
>
> **Authority:** governance spec. Replaces today's single
> readiness flag (`paper_readiness_latest.v1.json`,
> `readiness_status`) with an explicit per-candidate YES/NO
> checklist that an operator can read in seconds. Does not
> modify ADR-014. The checklist is a **derived view**; the
> canonical authority for paper-readiness remains
> `paper_readiness_latest.v1.json` per ADR-014 §A.
>
> **Schema:** [`paper_readiness_checklist/schema.v1.md`](paper_readiness_checklist/schema.v1.md).
>
> **Cross-refs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
> §9,
> [`research_quality_kpis.md`](research_quality_kpis.md) §5,
> [`multiplicity_ledger.md`](multiplicity_ledger.md),
> [`holdout_discipline.md`](holdout_discipline.md),
> [`cost_adjusted_promotion.md`](cost_adjusted_promotion.md),
> [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md),
> [`docs/adr/_drafts/ADR-020-paper-shadow-live-separation.md`](../adr/_drafts/ADR-020-paper-shadow-live-separation.md).

## 1. Purpose

The current `paper_readiness_latest.v1.json` carries a single
`readiness_status` field. That answers "is the candidate
paper-ready?" but not "why?". For an operator who must approve
paper promotion, *why* matters more than the bit.

The checklist:

- enumerates every gate the candidate must pass;
- records the pass/fail state of each gate explicitly;
- records the inputs that produced each gate (multiplicity-
  adjusted Deflated Sharpe, null-beat, cost-adjusted edge,
  multi-asset / multi-timeframe / multi-regime, hold-out
  red-team review);
- is regenerated deterministically from upstream artifacts;
- is **derived**, not canonical (ADR-014 unchanged).

## 2. Authority

Per ADR-014 §A:

| Truth domain | Canonical authority | Derived view |
|---|---|---|
| "this candidate is paper-ready" | `paper_readiness_latest.v1.json` `readiness_status` field | `paper_readiness_checklist.v1.json` `overall` field |

The checklist's `overall` field **must** match
`readiness_status` when both exist. If they diverge, the
canonical field wins per ADR-014 §A; the checklist regenerates
on the next cycle.

## 3. Scope

The checklist exists per candidate. There is one
`paper_readiness_checklist.v1.json` per candidate_id, regenerated
whenever any input artifact changes.

The checklist:

- does **not** trade;
- does **not** authorise live, paper, or shadow deployment;
- does **not** mutate `paper_readiness_latest.v1.json`;
- does **not** mutate `research_latest.json` or
  `strategy_matrix.csv`;
- does **not** feed any execution-side surface (ADR-020 §2.5).

## 4. Gate definitions

The checklist tracks the validation gates declared by
[`research_quality_kpis.md`](research_quality_kpis.md) §5,
expanded into ten explicit checks.

| Check | Source artifact | Pass condition |
|---|---|---|
| `null_model_beat` | scoring-reason records ([`reason_records.md`](reason_records.md)) with `decision_kind: filter_null` for the candidate | candidate's null-model evaluation score exceeds the candidate's actual score with `p_value <= 0.05` (or pinned threshold) |
| `tail_fragility_pass` | scoring-reason records with `decision_kind: filter_tail` | candidate is not single-outlier-dependent (top-1 trade contributes < 25% of edge; pinned in impl) |
| `entropy_regime_compatible` | scoring-reason records with `decision_kind: filter_entropy` | candidate's directional bias is compatible with the regime's entropy state |
| `cost_adjusted_edge_positive` | [`cost_adjusted_promotion.md`](cost_adjusted_promotion.md) cost model + candidate's evidence ledger | expected edge net of round-trip cost > 0 with `p_value <= 0.05` |
| `multiplicity_adjusted_dsr_pass` | [`multiplicity_ledger.md`](multiplicity_ledger.md) `N_eff(candidate)` + candidate's Sharpe | Deflated Sharpe `DSR > pinned_threshold` for the release |
| `multi_asset_robust` | per-asset evaluation records | candidate survives on ≥ N alternate assets (N pinned per release) |
| `multi_timeframe_robust` | per-timeframe evaluation records | candidate survives on ≥ N alternate timeframes |
| `multi_regime_robust` | per-regime evaluation records | candidate survives on ≥ N alternate regimes |
| `single_source_dependency_clean` | source-lineage records | candidate does not depend on a single source whose disagreement with peers exceeds threshold |
| `holdout_redteam_review_pass` | [`holdout_discipline.md`](holdout_discipline.md) `logs/holdout_reviews/<window_id>/<candidate_id>.v1.json` | review decision is `pass` |

A check evaluates to:

- `yes` — pass;
- `no` — fail;
- `n/a` — gate not yet evaluable (e.g., hold-out review not yet
  performed; multi-regime check requires more regimes than exist
  in current data).

## 5. Overall

```text
overall = yes  iff  all(check in {yes, n/a}) AND at_least_one(check == yes)
overall = no   otherwise
```

The "at least one yes" requirement is the safety against a
candidate that has no evaluable checks (a checklist of all `n/a`s
must not promote).

## 6. Derivation rules

The checklist is derived from upstream artifacts. It is **never**
written by hand.

```text
checklist(candidate_id) = derive_from({
    scoring_reason_records[candidate_id],
    multiplicity_ledger.N_eff(candidate_id),
    candidate_evidence_ledger[candidate_id],
    holdout_reviews[*][candidate_id],
    source_lineage_records[candidate_id],
    cost_model_artifact
})
```

The derivation is:

- **Pure.** No IO outside reading the named upstream artifacts.
  No network, no `subprocess`, no `gh`, no `git`.
- **Deterministic.** Two runs over the same upstream artifacts
  produce byte-identical checklists (modulo `generated_at_utc`).
- **Idempotent.** Re-generating with no input changes produces
  no diff.

## 7. Storage

| Path | Owner | Content |
|---|---|---|
| `logs/paper_readiness_checklist/<candidate_id>.v1.json` | derivation module | one checklist per candidate |
| `logs/paper_readiness_checklist/manifest.v1.json` | derivation module | rolled-up index of all checklists |
| `paper_readiness_latest.v1.json` | (canonical, unchanged per ADR-014) | the single `readiness_status` flag |

Atomic-write allowlist substring: `logs/paper_readiness_checklist/`.
Writes outside this prefix raise `ValueError`. Mirrors the
multiplicity-ledger discipline.

## 8. Invariants

| ID | Invariant | Enforcement |
|---|---|---|
| PR-I1 | Checklist is **derived**, not canonical. Cannot diverge from `readiness_status` in a way that mutates the canonical artifact. | Implementation PR's tests pin both fields and the divergence rule (canonical wins). |
| PR-I2 | `overall = yes` requires at least one `yes` and no `no`. | Schema test. |
| PR-I3 | `n/a` is allowed only when the gate's source artifact does not yet exist or explicitly returns "indeterminate". | Schema test. |
| PR-I4 | Derivation is pure and deterministic. | Source-text test (no `subprocess`, no `socket`, no `requests`); byte-identical-output test. |
| PR-I5 | The schema is versioned. v2 may add fields; never remove. | Schema test. |
| PR-I6 | No mutation of frozen contracts. | Atomic-write allowlist; tests pin write paths. |
| PR-I7 | No feed to execution-side surfaces. The checklist is read-only to live / paper / shadow / broker / execution. | Source-text test (no import of execution modules). |

## 9. Operator workflow

1. Operator selects a candidate whose evidence shows promise.
2. Operator runs (or schedules) the gate chain
   ([`research_quality_kpis.md`](research_quality_kpis.md) §5).
3. As each gate's source artifact lands, the checklist
   regenerates with that gate's pass/fail.
4. When `holdout_redteam_review_pass` is the only remaining
   `n/a`, the operator initiates the hold-out red-team review
   per [`holdout_discipline.md`](holdout_discipline.md) §6.
5. After the review writes its artifact, the checklist
   regenerates with the final result.
6. If `overall = yes`, the operator may proceed to paper
   promotion per ADR-014 and a future operator-driven paper
   readiness PR. **Paper promotion remains operator-gated;
   no agent auto-promotes**.

## 10. Test plan (for the implementation PR)

- Schema tests (every field present, types correct).
- Derivation purity test (no IO).
- Determinism test (two runs over the same inputs → byte-
  identical checklist modulo `generated_at_utc`).
- `overall` derivation tests (every combination of
  `{yes, no, n/a}` across the 10 checks).
- Idempotence test.
- Divergence test (when `readiness_status` and `overall`
  disagree, canonical wins and a structured divergence note is
  written to the checklist).
- Frozen-contract-untouched test.
- Execution-import-deny test (the module imports nothing from
  `agent/execution/`, `automation/`, `broker/`, `live/`,
  `paper/`, `shadow/`, `trading/`, `execution/`).

## 11. What this checklist is NOT

- Not a promotion path. ADR-014's funnel policy is.
- Not a kill-switch. The checklist informs the operator;
  kill-switches live in the live-risk envelope (ADR-020 §2.8;
  ADR-023 will define).
- Not a backtest report. Backtest evidence feeds into the
  upstream evidence ledger, which feeds into the gate checks.
- Not a substitute for the funnel policy
  (`research/campaign_funnel_policy.py`).

## 12. Update history

- 2026-05-21: initial version (Research-Quality Hardening Sprint,
  S8 detail spec). Expands
  [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
  §9.
