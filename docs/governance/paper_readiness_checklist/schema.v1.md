# Paper-Readiness Checklist — Schema v1

> Module: `reporting.paper_readiness_checklist` (planned).
> Module version: pinned at implementation PR.
> Schema version: `1`.
> Artifact path: `logs/paper_readiness_checklist/<candidate_id>.v1.json`
> Manifest path: `logs/paper_readiness_checklist/manifest.v1.json`
> Doctrine: [`../paper_readiness_checklist.md`](../paper_readiness_checklist.md).

## Top-level shape

```json
{
  "schema_version": 1,
  "report_kind": "paper_readiness_checklist",
  "module_version": "<pinned-at-impl>",
  "generated_at_utc": "<rfc3339-utc-seconds>",
  "candidate_id": "<str>",
  "checks": { /* see "Checks" */ },
  "overall": "yes|no",
  "multiplicity_n_eff": <int>,
  "dsr_value": <float>,
  "cost_assumptions_ref": "<pointer-to-cost-model-artifact>",
  "canonical_readiness_status": "<value-from-paper_readiness_latest.v1.json>",
  "divergence_from_canonical": "<null | structured note>",
  "notes": "<str, capped at 400 chars>"
}
```

## Checks (object)

| field | type | values | notes |
|---|---|---|---|
| `null_model_beat` | enum | `yes` / `no` / `n/a` | gate 1 |
| `tail_fragility_pass` | enum | `yes` / `no` / `n/a` | gate 2 |
| `entropy_regime_compatible` | enum | `yes` / `no` / `n/a` | gate 2 |
| `cost_adjusted_edge_positive` | enum | `yes` / `no` / `n/a` | gate 3 (see [`../cost_adjusted_promotion.md`](../cost_adjusted_promotion.md)) |
| `multiplicity_adjusted_dsr_pass` | enum | `yes` / `no` / `n/a` | gate 4 |
| `multi_asset_robust` | enum | `yes` / `no` / `n/a` | gate 5 |
| `multi_timeframe_robust` | enum | `yes` / `no` / `n/a` | gate 5 |
| `multi_regime_robust` | enum | `yes` / `no` / `n/a` | gate 5 |
| `single_source_dependency_clean` | enum | `yes` / `no` / `n/a` | gate 5 |
| `holdout_redteam_review_pass` | enum | `yes` / `no` / `n/a` | gate 6 |

A check returns `n/a` only when the source artifact:

- does not yet exist;
- explicitly returns "indeterminate" (e.g., the multi-regime
  check on a dataset with fewer regimes than the threshold).

A check that has data but fails returns `no`, never `n/a`.

## `overall` derivation

```python
def derive_overall(checks: dict[str, str]) -> str:
    values = list(checks.values())
    if any(v == "no" for v in values):
        return "no"
    if not any(v == "yes" for v in values):
        return "no"
    return "yes"
```

This is the same formula as
[`../paper_readiness_checklist.md`](../paper_readiness_checklist.md)
§5. The implementation PR pins this derivation function and a
parametrised test that walks every `{yes, no, n/a}^10` combination.

## `divergence_from_canonical`

Per ADR-014 §A, the canonical authority for paper-readiness is
`paper_readiness_latest.v1.json` `readiness_status`. When the
checklist's `overall` does not match the canonical field:

```json
"divergence_from_canonical": {
  "canonical_value": "<readiness_status>",
  "checklist_overall": "<overall>",
  "detected_at_utc": "<rfc3339-utc-seconds>",
  "resolution_rule": "canonical_wins_per_adr_014",
  "next_action": "regenerate_checklist_on_next_cycle"
}
```

The checklist is **not** authority. Per PR-I1 in
[`../paper_readiness_checklist.md`](../paper_readiness_checklist.md)
the canonical field wins; the checklist regenerates next cycle.
A persistent divergence is a stop-the-line event.

When the values match, `divergence_from_canonical` is `null`.

## Manifest shape

`logs/paper_readiness_checklist/manifest.v1.json`:

| field | type | notes |
|---|---|---|
| `schema_version` | int | `1` |
| `module_version` | string | pinned at impl PR |
| `generated_at_utc` | string | RFC3339 UTC, seconds resolution |
| `candidates_total` | int | count of per-candidate checklists |
| `candidates_overall_yes` | int | how many have `overall = yes` |
| `candidates_overall_no` | int | how many have `overall = no` |
| `divergence_count` | int | how many have a non-null `divergence_from_canonical` |
| `last_generated_at_utc` | string \| null | RFC3339 UTC of the most recent per-candidate checklist |
| `note` | string | one of `"no_candidates"`, `"candidates_present"`, `"divergence_detected"` |

## Validation summary

Every per-candidate artifact must satisfy:

- All top-level fields present, no extras.
- `checks` contains exactly the ten check keys, each with a
  value in `{yes, no, n/a}`.
- `overall` is `yes` or `no` (never `n/a`).
- `multiplicity_n_eff >= 0`.
- `dsr_value` is a finite float.
- `cost_assumptions_ref` is a non-empty string pointing at a
  cost-model artifact.
- `candidate_id` matches the file name stem.
- `divergence_from_canonical` is `null` or a complete structured
  note.
- `notes` ≤ 400 chars.
- No write occurred against a frozen contract during generation.

Any failure raises `ValueError` and produces a deterministic
error string. The atomic-write allowlist prefix is
`logs/paper_readiness_checklist/`.

## Test pin: `overall` truth table

The implementation PR ships a parametrised test that walks every
combination of `{yes, no, n/a}` across the ten checks (3^10 =
59049 combinations) and asserts `overall` matches the formula.
The test is fast (pure Python; no IO).

## Update history

- 2026-05-21: initial version (S8 detail spec).
