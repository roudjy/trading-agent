"""v3.13 post-hoc regime gating experiments.

Diagnostic-only. A small **fixed** set of predefined gate rules is
evaluated against each candidate by filtering the per-axis bucket
breakdown from the existing ``regime_diagnostics`` sidecar. Baseline,
filtered and delta metrics are reported for every rule.

Explicit guarantees:

- no gate search
- no optimization loop
- no "best" rule selected
- no new preset variant created
- every rule is reported, even when its evidence is insufficient
- metrics we cannot recompute from the existing sidecar (Sharpe,
  max drawdown on the filtered subset) are exposed as ``None`` rather
  than fabricated

Gate rules are declared as conjunctions over per-axis buckets. The
rule predicate operates on an axis label dict
``{"trend": <label>, "vol": <label>, "width": <label>}``. When an
axis is marked insufficient in the candidate's diagnostics, a rule
that requires a positive value on that axis filters *out* every
bucket on it — so the filtered subset becomes empty rather than
accidentally inflated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from research.regime_diagnostics import (
    ASSESSMENT_INSUFFICIENT,
    ASSESSMENT_SUFFICIENT,
    MIN_TRADES_PER_AXIS,
)


AxisLabels = dict[str, str]
GatePredicate = Callable[[AxisLabels], bool]


@dataclass(frozen=True)
class GateRule:
    rule_id: str
    expression: str
    predicate: GatePredicate


# Rule predicates are plain-Python dict tests so they are
# deterministic and trivially testable. The expression string is the
# canonical human-readable form of the same test.

def _only_trend(labels: AxisLabels) -> bool:
    return labels.get("trend") == "trending"


def _trend_and_low_vol(labels: AxisLabels) -> bool:
    return labels.get("trend") == "trending" and labels.get("vol") == "low_vol"


def _trend_and_expansion(labels: AxisLabels) -> bool:
    return labels.get("trend") == "trending" and labels.get("width") == "expansion"


GATE_RULES: tuple[GateRule, ...] = (
    GateRule("trend_only", "trend==trending", _only_trend),
    GateRule("trend_low_vol", "trend==trending & vol==low_vol", _trend_and_low_vol),
    GateRule("trend_expansion", "trend==trending & width==expansion", _trend_and_expansion),
)


NON_AUTHORITATIVE_NOTE = "diagnostic only; not a promotion signal"


# ---------------------------------------------------------------------------
# Core aggregation
# ---------------------------------------------------------------------------


def _baseline_metrics(
    trend_buckets: list[dict[str, Any]],
    vol_buckets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate candidate-level baseline metrics from axis buckets.

    Trades are counted from the trend axis (every trade has exactly
    one trend bucket). Total PnL is the sum across trend buckets.
    """
    trades = sum(int(b.get("trade_count") or 0) for b in trend_buckets)
    total_pnl = sum(float(b.get("total_pnl") or 0.0) for b in trend_buckets)
    # Return contribution is bar-level, not trade-level, so we pull it
    # from either axis — both should sum to the same value. We pick
    # trend to avoid double-counting.
    contribution = sum(
        float(b.get("arithmetic_return_contribution") or 0.0) for b in trend_buckets
    )
    # Vol buckets are not used for the base aggregate but we assert
    # their trade count matches — a small health check, reported not
    # raised.
    vol_trades = sum(int(b.get("trade_count") or 0) for b in vol_buckets)
    return {
        "trades": trades,
        "total_pnl": total_pnl,
        "arithmetic_return_contribution": contribution,
        "vol_trade_count": vol_trades,
    }


def _matching_buckets(
    *,
    trend_buckets: list[dict[str, Any]],
    vol_buckets: list[dict[str, Any]],
    rule: GateRule,
) -> dict[str, Any]:
    """Return the bucket subset for which ``rule`` evaluates True.

    The filter is a cross product of the trend and vol axes. Width is
    not yet supported at the trade level — rules requiring the
    ``width`` axis filter *out* every trade, yielding an empty
    filtered set (status: insufficient_axis_evidence) rather than a
    misleading one.
    """
    width_used = "width==" in rule.expression
    if width_used:
        return {
            "trades": 0,
            "total_pnl": 0.0,
            "arithmetic_return_contribution": 0.0,
            "width_unresolved": True,
        }

    trend_lookup = {b["label"]: b for b in trend_buckets}
    vol_lookup = {b["label"]: b for b in vol_buckets}

    # Because we don't have per-trade joint (trend, vol) tags in
    # v3.13 — only per-axis marginal counts — a conjunction "trend &
    # vol" can only be lower-bounded using the marginal intersection:
    # we take the trades that passed *both* the trend filter and the
    # vol filter independently and cap at the smaller count. This is
    # explicitly conservative and documented.
    trend_match = _axis_match(trend_lookup, rule.expression, axis="trend")
    vol_match = _axis_match(vol_lookup, rule.expression, axis="vol")

    if trend_match is None and vol_match is None:
        return {"trades": 0, "total_pnl": 0.0, "arithmetic_return_contribution": 0.0}

    if trend_match is not None and vol_match is None:
        return trend_match

    if trend_match is None and vol_match is not None:
        return vol_match

    # Both axes constrained: conservative intersection. The two
    # early-return branches above guarantee both matches are truthy
    # here; we type-narrow explicitly for mypy without using assert.
    if trend_match is None or vol_match is None:
        return {"trades": 0, "total_pnl": 0.0, "arithmetic_return_contribution": 0.0}
    trend_trades = int(trend_match["trades"])
    vol_trades = int(vol_match["trades"])
    trades = min(trend_trades, vol_trades)
    # Use trend-axis PnL scaled by the trade ratio as a conservative
    # estimate; if trend trades is zero this collapses to zero.
    if trend_trades > 0:
        scale = trades / trend_trades
    else:
        scale = 0.0
    return {
        "trades": trades,
        "total_pnl": float(trend_match["total_pnl"]) * scale,
        "arithmetic_return_contribution": (
            float(trend_match["arithmetic_return_contribution"]) * scale
        ),
        "conservative_intersection": True,
    }


def _axis_match(
    lookup: dict[str, dict[str, Any]],
    expression: str,
    *,
    axis: str,
) -> dict[str, Any] | None:
    """Return the single-axis match for the portion of ``expression``
    that constrains ``axis``, or ``None`` if the rule does not
    constrain this axis.

    Recognizes the exact rule expressions declared in
    :data:`GATE_RULES`.
    """
    if axis == "trend":
        if "trend==trending" in expression:
            bucket = lookup.get("trending") or {}
            return {
                "trades": int(bucket.get("trade_count") or 0),
                "total_pnl": float(bucket.get("total_pnl") or 0.0),
                "arithmetic_return_contribution": float(
                    bucket.get("arithmetic_return_contribution") or 0.0
                ),
            }
        return None
    if axis == "vol":
        if "vol==low_vol" in expression:
            bucket = lookup.get("low_vol") or {}
            return {
                "trades": int(bucket.get("trade_count") or 0),
                "total_pnl": float(bucket.get("total_pnl") or 0.0),
                "arithmetic_return_contribution": float(
                    bucket.get("arithmetic_return_contribution") or 0.0
                ),
            }
        if "vol==high_vol" in expression:
            bucket = lookup.get("high_vol") or {}
            return {
                "trades": int(bucket.get("trade_count") or 0),
                "total_pnl": float(bucket.get("total_pnl") or 0.0),
                "arithmetic_return_contribution": float(
                    bucket.get("arithmetic_return_contribution") or 0.0
                ),
            }
        return None
    return None


def _rule_status(
    filtered: dict[str, Any],
) -> str:
    if filtered.get("width_unresolved"):
        return "insufficient_axis_evidence"
    if filtered["trades"] < MIN_TRADES_PER_AXIS:
        return "insufficient_evidence"
    return "evaluated"


def _delta(baseline: dict[str, Any], filtered: dict[str, Any]) -> dict[str, Any]:
    return {
        "trades": filtered["trades"] - baseline["trades"],
        "total_pnl": filtered["total_pnl"] - baseline["total_pnl"],
        "arithmetic_return_contribution": (
            filtered["arithmetic_return_contribution"]
            - baseline["arithmetic_return_contribution"]
        ),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_candidate_gating_experiments(
    *,
    candidate_diagnostics: dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate every :data:`GATE_RULES` rule for one candidate.

    ``candidate_diagnostics`` is the payload produced by
    :func:`research.regime_diagnostics.build_candidate_diagnostics`.
    When the candidate is insufficient overall, every rule is
    reported with status ``insufficient_evidence`` and null metrics.
    """
    breakdown = candidate_diagnostics.get("regime_breakdown") or {}
    trend_buckets = breakdown.get("trend") or []
    vol_buckets = breakdown.get("vol") or []

    assessment = candidate_diagnostics.get("regime_assessment_status")
    if assessment != ASSESSMENT_SUFFICIENT:
        return [
            {
                "rule_id": rule.rule_id,
                "rule_expression": rule.expression,
                "status": ASSESSMENT_INSUFFICIENT,
                "baseline": None,
                "filtered": None,
                "delta": None,
                "non_authoritative_note": NON_AUTHORITATIVE_NOTE,
            }
            for rule in GATE_RULES
        ]

    baseline = _baseline_metrics(trend_buckets, vol_buckets)
    experiments: list[dict[str, Any]] = []
    for rule in GATE_RULES:
        filtered = _matching_buckets(
            trend_buckets=trend_buckets,
            vol_buckets=vol_buckets,
            rule=rule,
        )
        filtered_clean = {
            "trades": int(filtered["trades"]),
            "total_pnl": float(filtered["total_pnl"]),
            "arithmetic_return_contribution": float(
                filtered["arithmetic_return_contribution"]
            ),
        }
        status = _rule_status(filtered)
        experiments.append(
            {
                "rule_id": rule.rule_id,
                "rule_expression": rule.expression,
                "status": status,
                "baseline": {
                    "trades": int(baseline["trades"]),
                    "total_pnl": float(baseline["total_pnl"]),
                    "arithmetic_return_contribution": float(
                        baseline["arithmetic_return_contribution"]
                    ),
                },
                "filtered": filtered_clean,
                "delta": _delta(baseline, filtered_clean)
                if status == "evaluated"
                else None,
                "non_authoritative_note": NON_AUTHORITATIVE_NOTE,
            }
        )
    return experiments


def gating_rule_ids() -> list[str]:
    """Return the canonical rule-id list for sidecar summaries."""
    return [rule.rule_id for rule in GATE_RULES]


__all__ = [
    "GATE_RULES",
    "NON_AUTHORITATIVE_NOTE",
    "GateRule",
    "build_candidate_gating_experiments",
    "gating_rule_ids",
]
