"""Closed canonical failure taxonomy for the v3.15.3 hypothesis catalog.

This module is intentionally separate from ``research.rejection_taxonomy``
(which owns the v3.11 promotion-layer rejection codes). The two
vocabularies serve different layers:

- ``rejection_taxonomy`` = per-candidate promotion screening codes
  (insufficient_trades, oos_collapse, low_statistical_defensibility, ...).
  Pinned by the v3.11 / v3.13 contract and consumed by
  ``candidate_registry_v2``.
- ``strategy_failure_taxonomy`` (this module) = per-strategy *campaign*
  failure modes consumed by the v3.15.2 Campaign Operating Layer when
  it deprioritizes / cooldowns / freezes a hypothesis. Strategy-specific
  raw codes (e.g. ``trend_pullback_cost_fragile``) collapse to canonical
  codes for policy evaluation.

Keeping the modules disjoint protects the v3.11 contract and lets the
campaign layer evolve its taxonomy without touching the promotion
layer's pinned vocabulary.
"""

from __future__ import annotations

from typing import Final


CANONICAL_FAILURE_CODES: Final[tuple[str, ...]] = (
    "insufficient_trades",
    "cost_fragile",
    "parameter_fragile",
    "asset_singleton",
    "oos_collapse",
    "no_baseline_edge",
    "overtrading",
    "drawdown_unacceptable",
    "liquidity_sensitive",
    "baseline_underperform",
)


# Strategy-specific raw codes that collapse to a canonical code. The
# left side is the raw code emitted by a strategy/campaign module; the
# right side is the canonical entry the campaign policy reasons over.
STRATEGY_SPECIFIC_ALIASES: Final[dict[str, str]] = {
    "trend_pullback_cost_fragile": "cost_fragile",
    "trend_pullback_parameter_fragile": "parameter_fragile",
    "trend_pullback_no_baseline_edge": "no_baseline_edge",
}


class UnknownFailureCodeError(ValueError):
    """Raised when a code is neither canonical nor a known alias."""


def is_canonical(code: str) -> bool:
    """Return True if ``code`` is one of the canonical failure codes."""
    return code in CANONICAL_FAILURE_CODES


def canonicalize(raw_code: str) -> str:
    """Return the canonical failure code for ``raw_code``.

    Accepts either a canonical code (returned as-is) or a known
    strategy-specific alias (returned mapped to its canonical form).
    Raises ``UnknownFailureCodeError`` on anything else so the campaign
    policy never silently treats an unknown code as a no-op.
    """
    if raw_code in CANONICAL_FAILURE_CODES:
        return raw_code
    if raw_code in STRATEGY_SPECIFIC_ALIASES:
        return STRATEGY_SPECIFIC_ALIASES[raw_code]
    raise UnknownFailureCodeError(
        f"unknown failure code {raw_code!r}; canonical="
        f"{sorted(CANONICAL_FAILURE_CODES)}; aliases="
        f"{sorted(STRATEGY_SPECIFIC_ALIASES)}"
    )


def list_aliases_for(canonical_code: str) -> list[str]:
    """Return all raw aliases that map to ``canonical_code``.

    Useful for tests pinning the alias surface and for the campaign
    metadata sidecar's ``failure_mode_mapping`` payload.
    """
    if not is_canonical(canonical_code):
        raise UnknownFailureCodeError(
            f"{canonical_code!r} is not a canonical failure code"
        )
    return sorted(
        raw for raw, canonical in STRATEGY_SPECIFIC_ALIASES.items()
        if canonical == canonical_code
    )


def _validate_aliases() -> None:
    """Raise at import time if any alias targets a non-canonical code."""
    for raw, canonical in STRATEGY_SPECIFIC_ALIASES.items():
        if canonical not in CANONICAL_FAILURE_CODES:
            raise UnknownFailureCodeError(
                f"alias {raw!r} targets non-canonical {canonical!r}; "
                f"canonical={sorted(CANONICAL_FAILURE_CODES)}"
            )


_validate_aliases()


__all__ = [
    "CANONICAL_FAILURE_CODES",
    "STRATEGY_SPECIFIC_ALIASES",
    "UnknownFailureCodeError",
    "canonicalize",
    "is_canonical",
    "list_aliases_for",
]
