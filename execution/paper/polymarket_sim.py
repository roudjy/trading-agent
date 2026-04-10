"""Deterministic paper-execution simulator for Polymarket-style books."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Literal, Mapping

from execution.protocols import Fill, OrderIntent, PaperBrokerBase

POLYMARKET_FEE_BPS = 200
MAX_ENTRY_PRICE = 0.60


class NoLiquidityError(RuntimeError):
    """Raised when the relevant side of the book cannot fill any size."""


class MaxEntryPriceExceededError(RuntimeError):
    """Raised when a buy would exceed the configured Polymarket max entry price."""


class PolymarketPaperBroker(PaperBrokerBase):
    """Pure paper broker that walks a provided Polymarket order-book snapshot."""

    name = "polymarket-paper"

    def place_paper_order(self, intent: OrderIntent, market_snapshot: Mapping) -> Fill:
        book_side = _resolve_book_side(intent.instrument_id, market_snapshot)
        levels_key = f"{book_side}_{'asks' if intent.side == 'buy' else 'bids'}"
        levels = _normalize_levels(market_snapshot.get(levels_key, ()))
        if not levels:
            raise NoLiquidityError(f"No liquidity available on {levels_key} for {intent.instrument_id}")

        intended_price = float(levels[0][0])
        filled_size, fill_price = _walk_book(levels, intent.size)
        if filled_size <= 0:
            raise NoLiquidityError(f"No liquidity available on {levels_key} for {intent.instrument_id}")

        if intent.side == "buy" and fill_price > MAX_ENTRY_PRICE:
            raise MaxEntryPriceExceededError(
                f"Average fill price {fill_price:.4f} exceeds max entry price {MAX_ENTRY_PRICE:.2f}"
            )

        slippage_bps = _slippage_bps(intent.side, intended_price, fill_price)
        fee_amount = fill_price * filled_size * POLYMARKET_FEE_BPS / 10000
        timestamp_utc = _normalize_timestamp(market_snapshot["timestamp_utc"])

        return Fill(
            instrument_id=intent.instrument_id,
            side=intent.side,
            size=filled_size,
            intended_price=intended_price,
            fill_price=fill_price,
            slippage_bps=slippage_bps,
            fee_ccy="USDC",
            fee_amount=fee_amount,
            timestamp_utc=timestamp_utc,
            venue=intent.venue,
        )


def _resolve_book_side(instrument_id: str, market_snapshot: Mapping) -> Literal["yes", "no"]:
    snapshot_side = str(market_snapshot.get("book_side", "yes")).strip().lower()
    if snapshot_side in {"yes", "no"}:
        return snapshot_side

    normalized = instrument_id.strip().upper()
    if normalized.endswith(":NO") or normalized.endswith("-NO"):
        return "no"
    return "yes"


def _normalize_levels(raw_levels: Iterable[Iterable[float]]) -> tuple[tuple[float, float], ...]:
    levels: list[tuple[float, float]] = []
    for level in raw_levels:
        price, size = level
        price_value = float(price)
        size_value = float(size)
        if size_value <= 0:
            continue
        levels.append((price_value, size_value))
    return tuple(levels)


def _walk_book(levels: tuple[tuple[float, float], ...], requested_size: float) -> tuple[float, float]:
    remaining = float(requested_size)
    filled = 0.0
    notionals = 0.0

    for price, level_size in levels:
        take = min(remaining, level_size)
        if take <= 0:
            continue
        notionals += price * take
        filled += take
        remaining -= take
        if remaining <= 0:
            break

    if filled <= 0:
        return 0.0, 0.0

    return filled, notionals / filled


def _slippage_bps(side: Literal["buy", "sell"], intended_price: float, fill_price: float) -> float:
    if intended_price <= 0:
        raise ValueError("intended_price must be positive")

    if side == "buy":
        raw = (fill_price - intended_price) / intended_price * 10000
    else:
        raw = (intended_price - fill_price) / intended_price * 10000
    return round(max(raw, 0.0), 4)


def _normalize_timestamp(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
