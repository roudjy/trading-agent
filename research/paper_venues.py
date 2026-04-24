"""v3.15 paper venue definitions.

Maps ``asset_type`` (as produced by
:mod:`research.asset_typing`) to a :class:`ScenarioSpec` from
:mod:`agent.backtesting.cost_sensitivity`. The scenarios are
deliberately venue-delta oriented: the engine baseline already
applies ``kosten_per_kant``; v3.15 never replaces or stacks
costs. Instead it re-runs the cost-sensitivity harness with a
venue-specific multiplier + slippage, yielding a delta vs
baseline per candidate.

Design invariants (v0.1):

- Constants are named and ultimately sourced from
  ``CLAUDE.md``. Every artifact that uses an IBKR scenario
  echoes ``VENUE_IBKR_EQUITY_ASSUMED_NOTIONAL_EUR`` in its
  payload so consumers can audit the conversion from the
  flat €1 fee to a percentage model.
- ``unknown`` / ``futures`` / ``index_like`` return ``None``.
  Downstream readiness translates that into an explicit
  ``insufficient_venue_mapping`` blocking reason — v3.15
  never silently substitutes a fallback venue.
- Polymarket is defined for completeness but not applied:
  no Polymarket candidates reach the research pipeline in
  v3.15. The constants are reserved for v3.16+ when the Bot
  / DataArbitrage agents gain research integration.

This module has no external dependencies beyond
:mod:`agent.backtesting.cost_sensitivity`. It does not import
anything from ``agent.broker*``, ``execution.live*`` or
``agent.execution`` — the v3.15 "no live" invariant is
enforced by
:mod:`tests.unit.test_paper_no_live_invariant`.
"""

from __future__ import annotations

from agent.backtesting.cost_sensitivity import ScenarioSpec


PAPER_VENUES_VERSION: str = "v0.1"

# ---------------------------------------------------------------------------
# Bitvavo (crypto spot) — CLAUDE.md: 0.25% per kant
# ---------------------------------------------------------------------------
VENUE_BITVAVO_CRYPTO_FEE_PER_SIDE: float = 0.0025
VENUE_BITVAVO_CRYPTO_SLIPPAGE_BPS: float = 10.0

# ---------------------------------------------------------------------------
# IBKR (equities) — CLAUDE.md: €1/order flat
#
# v3.15 converts the flat fee into a per-side percentage by
# assuming an average notional. The assumed notional is echoed
# in every artifact that uses the IBKR scenario so consumers
# can re-derive or recalibrate.
# ---------------------------------------------------------------------------
VENUE_IBKR_EQUITY_ASSUMED_NOTIONAL_EUR: float = 2000.0
VENUE_IBKR_EQUITY_FEE_FLAT_EUR: float = 1.0
VENUE_IBKR_EQUITY_FEE_PER_SIDE: float = (
    VENUE_IBKR_EQUITY_FEE_FLAT_EUR / VENUE_IBKR_EQUITY_ASSUMED_NOTIONAL_EUR
)  # = 0.0005  (5 bps)
VENUE_IBKR_EQUITY_SLIPPAGE_BPS: float = 10.0

# ---------------------------------------------------------------------------
# Polymarket (defined, not applied in v3.15)
# ---------------------------------------------------------------------------
VENUE_POLYMARKET_FEE_PER_SIDE: float = 0.01  # 2% spread / 2 kanten
VENUE_POLYMARKET_SLIPPAGE_BPS: float = 10.0


# ---------------------------------------------------------------------------
# Baseline cost reference
#
# Every v3.15 scenario encodes a delta vs the engine baseline.
# The engine uses ``kosten_per_kant`` per candidate; we need a
# shared reference to convert venue_fee_per_side into the
# ``fee_multiplier`` the cost-sensitivity harness expects.
#
# Concretely: the harness does
#   per_fill_adjustment = (1 - fee_multiplier * kosten_per_kant)
#                       * (1 - slippage_bps / 10_000)
#                       / (1 - kosten_per_kant)
# so ``fee_multiplier = venue_fee_per_side / kosten_per_kant``
# reproduces a venue-cost regime exactly. The conversion
# happens in :func:`venue_scenario_for` at call time because
# ``kosten_per_kant`` is candidate-specific.
# ---------------------------------------------------------------------------


def venue_name_for_asset_type(asset_type: str) -> str | None:
    """Return the canonical v3.15 venue name for an asset type.

    Returns ``None`` for asset types without a defined venue
    mapping (``unknown``, ``futures``, ``index_like``). The
    readiness layer turns ``None`` into an
    ``insufficient_venue_mapping`` blocking reason — no
    fallback substitution.
    """
    normalized = (asset_type or "").strip().lower()
    if normalized == "crypto":
        return "crypto_bitvavo"
    if normalized == "equity":
        return "equity_ibkr"
    return None


def venue_scenario_for(
    asset_type: str,
    *,
    baseline_kosten_per_kant: float,
) -> ScenarioSpec | None:
    """Build a :class:`ScenarioSpec` for the given asset type.

    Parameters
    ----------
    asset_type:
        Normalized asset type (see
        :mod:`research.asset_typing`).
    baseline_kosten_per_kant:
        The engine's baseline per-side cost for this candidate.
        Used to convert ``venue_fee_per_side`` into the
        ``fee_multiplier`` expected by
        :mod:`agent.backtesting.cost_sensitivity`.

    Returns
    -------
    ``None`` when no venue mapping exists (unknown asset_type
    or non-positive baseline). Otherwise a validated
    :class:`ScenarioSpec` whose name identifies the venue.
    """
    venue = venue_name_for_asset_type(asset_type)
    if venue is None:
        return None
    if not isinstance(baseline_kosten_per_kant, (int, float)):
        return None
    if baseline_kosten_per_kant <= 0.0:
        return None
    if venue == "crypto_bitvavo":
        fee_per_side = VENUE_BITVAVO_CRYPTO_FEE_PER_SIDE
        slippage_bps = VENUE_BITVAVO_CRYPTO_SLIPPAGE_BPS
    elif venue == "equity_ibkr":
        fee_per_side = VENUE_IBKR_EQUITY_FEE_PER_SIDE
        slippage_bps = VENUE_IBKR_EQUITY_SLIPPAGE_BPS
    else:
        return None
    fee_multiplier = float(fee_per_side) / float(baseline_kosten_per_kant)
    return ScenarioSpec(
        name=venue,
        fee_multiplier=fee_multiplier,
        slippage_bps=float(slippage_bps),
    )


def venue_metadata() -> dict[str, object]:
    """Return the auditable venue metadata embedded in v3.15
    artifact payloads.

    Consumers can inspect the assumed IBKR notional,
    Polymarket reservation, and Bitvavo fee without having to
    re-derive them.
    """
    return {
        "paper_venues_version": PAPER_VENUES_VERSION,
        "bitvavo_crypto": {
            "fee_per_side": VENUE_BITVAVO_CRYPTO_FEE_PER_SIDE,
            "slippage_bps": VENUE_BITVAVO_CRYPTO_SLIPPAGE_BPS,
        },
        "equity_ibkr": {
            "fee_per_side": VENUE_IBKR_EQUITY_FEE_PER_SIDE,
            "fee_flat_eur": VENUE_IBKR_EQUITY_FEE_FLAT_EUR,
            "assumed_notional_eur": VENUE_IBKR_EQUITY_ASSUMED_NOTIONAL_EUR,
            "slippage_bps": VENUE_IBKR_EQUITY_SLIPPAGE_BPS,
        },
        "polymarket_binary": {
            "fee_per_side": VENUE_POLYMARKET_FEE_PER_SIDE,
            "slippage_bps": VENUE_POLYMARKET_SLIPPAGE_BPS,
            "applied_in_v3_15": False,
            "reason_not_applied": (
                "no Polymarket candidates in research pipeline"
            ),
        },
        "unmapped_asset_types": ["unknown", "futures", "index_like"],
    }


__all__ = [
    "PAPER_VENUES_VERSION",
    "VENUE_BITVAVO_CRYPTO_FEE_PER_SIDE",
    "VENUE_BITVAVO_CRYPTO_SLIPPAGE_BPS",
    "VENUE_IBKR_EQUITY_ASSUMED_NOTIONAL_EUR",
    "VENUE_IBKR_EQUITY_FEE_FLAT_EUR",
    "VENUE_IBKR_EQUITY_FEE_PER_SIDE",
    "VENUE_IBKR_EQUITY_SLIPPAGE_BPS",
    "VENUE_POLYMARKET_FEE_PER_SIDE",
    "VENUE_POLYMARKET_SLIPPAGE_BPS",
    "venue_name_for_asset_type",
    "venue_scenario_for",
    "venue_metadata",
]
