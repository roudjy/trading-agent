"""Deterministic QRE null-model baseline scaffold.

This module provides context-only baseline comparison helpers for QRE research
diagnostics. It does not promote candidates, register strategies, authorize
paper/shadow/live activation, or perform broker/risk/execution actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "1.0"


BASELINE_TYPES: tuple[str, ...] = (
    "zero_return",
    "buy_and_hold",
    "median_candidate",
    "randomized_label_placeholder",
    "unknown",
)


@dataclass(frozen=True)
class NullBaselineResult:
    baseline_type: str
    candidate_metric: float | None
    baseline_metric: float | None
    delta_vs_baseline: float | None
    comparison_state: str
    explanation: str


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compare_metric_to_baseline(
    *,
    candidate_metric: Any,
    baseline_metric: Any,
    baseline_type: str = "unknown",
) -> NullBaselineResult:
    """Compare a candidate metric to a deterministic null baseline.

    This is diagnostic context only. A favorable delta never authorizes
    promotion, routing, paper/shadow/live, or execution.
    """

    candidate = _to_float(candidate_metric)
    baseline = _to_float(baseline_metric)
    normalized_baseline_type = baseline_type if baseline_type in BASELINE_TYPES else "unknown"

    if candidate is None or baseline is None:
        return NullBaselineResult(
            baseline_type=normalized_baseline_type,
            candidate_metric=candidate,
            baseline_metric=baseline,
            delta_vs_baseline=None,
            comparison_state="insufficient_metric_data",
            explanation="Candidate and baseline metrics must both be numeric.",
        )

    delta = candidate - baseline
    if delta > 0:
        state = "candidate_above_baseline"
    elif delta < 0:
        state = "candidate_below_baseline"
    else:
        state = "candidate_equal_to_baseline"

    return NullBaselineResult(
        baseline_type=normalized_baseline_type,
        candidate_metric=candidate,
        baseline_metric=baseline,
        delta_vs_baseline=delta,
        comparison_state=state,
        explanation="Deterministic metric-vs-baseline comparison; context only, not authority.",
    )


def median_candidate_baseline(
    rows: Iterable[Mapping[str, Any]],
    *,
    metric_field: str,
) -> float | None:
    """Return a deterministic median-like baseline using sorted numeric values.

    For even counts this returns the arithmetic mean of the two middle values.
    """

    values = sorted(
        value
        for row in rows
        if isinstance(row, Mapping)
        for value in [_to_float(row.get(metric_field))]
        if value is not None
    )
    if not values:
        return None

    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return mean((values[mid - 1], values[mid]))


def null_model_manifest() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "baseline_types": list(BASELINE_TYPES),
        "authority": {
            "null_model_is_context_only": True,
            "not_alpha_authority": True,
            "not_candidate_promotion": True,
            "not_strategy_registration": True,
            "not_paper_shadow_live": True,
            "not_broker_execution": True,
            "does_not_fetch_data": True,
            "does_not_mutate_frozen_contracts": True,
        },
    }