# ADR-006: Thin Strategy Contract v2.0 Deferred

Status: Accepted
Date: 2026-04-21
Phase: v3.6 (multi-asset loader and feature-purity progression)
Supersedes: -
Superseded by: -

## Context

The thin strategy contract v1.0, landed in v3.5, has the signature:

```python
def func(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series
```

The strategy body is permitted to read `df.index` for return-index
alignment and nothing else from `df`. All actual data access flows
through `features`. The constraint is enforced by an AST test in
`tests/unit/test_thin_strategy_contract.py`.

v2.0 was originally sketched as a purer variant that drops `df` from
the signature entirely:

```python
def func(features: Mapping[str, pd.Series]) -> pd.Series
```

The engine would then pass only `features`, and the strategy would
receive the index from the feature series themselves.

During v3.6 planning we asked whether the multi-asset progression was
the right moment to migrate to v2.0.

## Decision

**v2.0 is deferred.** v3.6 lands pairs as a true Tier 1 baseline under
the v1.0 contract. No strategy in the project migrates to v2.0 in this
phase, and the engine introduces no `func(features)` routing branch.

The v3.5 constraint — "strategy body may read `df.index` and nothing
else" — remains the contract. The AST test keeps enforcing it.

## Rationale

- **No concrete triggering use case.** Every Tier 1 strategy today
  (including pairs, post-v3.6) is cleanly expressible under v1.0. The
  `df` argument is used only for `df.index`, which is trivially also
  available from any feature Series. v2.0 would be a stylistic
  improvement, not a capability unlock.
- **Dual routing is a liability during a refactor.** v3.6 already
  introduces a second feature-resolution path
  (`build_features_for_multi`) and an optional `reference_frame` on
  `AssetContext`. Adding a third routing variant on top of that — one
  with no live caller — multiplies the surface area of the change and
  dilutes the guarantees we actually want to pin (bytewise Tier 1,
  public output contract, integrity D4 boundary).
- **AST enforcement already approximates v2.0 purity.** The v1.0
  contract forbids reading any column off `df`. The practical
  difference between "can't read columns" and "doesn't receive `df`
  at all" is small; the compliance gain does not justify a dead code
  path.

## Trigger for revisiting

v2.0 lands when either of the following becomes true:

1. A strategy primitive genuinely cannot accept `df` — for example,
   a feature-first strategy composed purely from cross-asset
   primitives whose index is not derivable from any single input frame.
2. The fit/transform abstraction (tracked separately as a v3.7
   candidate: `feature/v3.7-fitted-feature-abstraction`) lands and
   introduces features that must be computed against train-only data.
   At that point, decoupling the strategy from its raw-frame view may
   be the cleaner migration path.

Either trigger would be documented in its own ADR before v2.0 is
introduced.

## Migration approach (when triggered)

- Add a second routing branch in `BacktestEngine._invoke_strategy`
  that detects a `_thin_contract_version == "2.0"` stamp and calls
  `func(features)` instead of `func(df, features)`.
- Migrate strategies one at a time. Each migration must carry its own
  bytewise pin (`tests/regression/test_tier1_bytewise_pin.py`).
- Keep v1.0 live throughout the migration; v2.0 is additive, not a
  replacement.

## Consequences

- Positive: v3.6 retains a single feature-resolution routing decision
  (single-frame vs multi-frame) with no third axis. Every bytewise pin
  from v3.5 stays load-bearing without interpretation.
- Positive: the v2.0 migration, when it happens, lands against a
  concrete use case and can be re-pinned cleanly.
- Negative: the transitional nature of v1.0 (documented in
  `thin_strategy.py`) remains visible in the codebase a while longer.
- Neutral: `df` stays in the strategy signature. No compliance risk
  because the AST test already prevents misuse.

## Thin contract maturity statement

As of v3.6: **v1.0 is production for all Tier 1 strategies, including
pairs. v2.0 is deferred to v3.7+ pending a concrete triggering use
case.**
