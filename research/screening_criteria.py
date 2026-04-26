"""v3.15.7 — phase-aware screening criteria dispatch.

Pure module, no IO. Called from
``research.screening_runtime.execute_screening_candidate_samples``
after each engine sample. The caller owns the trade-count
pre-check (``engine.min_trades``) and the OOS-data pre-check
(``no_oos_samples``) — this helper assumes data validity and only
performs phase-specific gating on the metrics dict.

Funnel discipline:

- Screening zoekt — exploratory criteria minimaliseren false
  negatives so trend/momentum candidates with positive expectancy
  but low win_rate can pass for shortlist.
- Promotion bewijst — promotion_grade keeps the strict v3.15.6
  gates byte-identical (delegated to the engine ``goedgekeurd``
  AND-gate).
- Paper valideert — exploratory passes are downgraded to
  ``needs_investigation`` by ``promotion.classify_candidate`` so
  they NEVER auto-promote to paper.

Phase semantics:

- ``screening_phase == "exploratory"`` → exploratory criteria;
  win_rate is diagnostic-only (not a hard gate).
- ``screening_phase`` in {``"standard"``, ``"promotion_grade"``,
  ``None``} → legacy ``goedgekeurd`` AND-gate; behavior is
  byte-identical to pre-v3.15.7.

Threshold values are start-points; v3.15.8+ may recalibrate based
on empirical evidence. v3.15.7 introduces no
``EXPLORATORY_MIN_TRADES`` constant — the trade-count gate lives
upstream in ``screening_runtime`` via ``engine.min_trades`` to
avoid duplicate-gate drift.
"""

from __future__ import annotations

from typing import Any


EXPLORATORY_MIN_EXPECTANCY = 0.0           # strict > 0
EXPLORATORY_MIN_PROFIT_FACTOR = 1.05
EXPLORATORY_MAX_DRAWDOWN = 0.45            # absolute scale 0..1


def apply_phase_aware_criteria(
    metrics: dict[str, Any],
    screening_phase: str | None,
) -> tuple[bool, str | None]:
    """Return ``(passed, reason_code)`` for the given phase.

    The annotation on ``screening_phase`` is intentionally
    ``str | None`` (not Literal) so a future v3.15.8+ phase value
    can be added without an API break. Unknown values fall through
    to the legacy path (conservative); preset validation catches
    invalid phase upstream.
    """
    if screening_phase == "exploratory":
        return _exploratory_criteria(metrics)
    return _legacy_criteria(metrics)


def _legacy_criteria(metrics: dict[str, Any]) -> tuple[bool, str | None]:
    """Pre-v3.15.7 path: read engine ``goedgekeurd`` AND-gate."""
    if not metrics.get("goedgekeurd", False):
        return False, "screening_criteria_not_met"
    return True, None


def _exploratory_criteria(metrics: dict[str, Any]) -> tuple[bool, str | None]:
    """v3.15.7 discovery-friendly criteria; win_rate diagnostic-only."""
    expectancy = float(metrics.get("expectancy", 0.0))
    if not expectancy > EXPLORATORY_MIN_EXPECTANCY:
        return False, "expectancy_not_positive"

    profit_factor = float(metrics.get("profit_factor", 0.0))
    if profit_factor < EXPLORATORY_MIN_PROFIT_FACTOR:
        return False, "profit_factor_below_floor"

    max_drawdown = float(metrics.get("max_drawdown", 1.0))
    if max_drawdown > EXPLORATORY_MAX_DRAWDOWN:
        return False, "drawdown_above_exploratory_limit"

    return True, None
